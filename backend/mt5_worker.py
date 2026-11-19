"""Local Stratix MT5 demo agent. Run one isolated process per terminal/account.

This module is inert when imported. main() is the only connection entry point.
"""
import argparse
import math
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

import pandas as pd

from backend import copy_trading as store
from backend.backtester import Backtester
from backend.indicators import indicator_engine
from backend.strategy import Strategy
from backend.data_manager import SUPPORTED_SYMBOLS
from backend.ea_bridge import BridgeReadUnavailable

TF_SECONDS = {'30m':1800, '1h':3600, '4h':14400, '1d':86400}


class LeaseLost(RuntimeError):
    pass


class MarketDataUnavailable(RuntimeError):
    pass


def floor_volume(value, info):
    if not math.isfinite(value) or value <= 0 or info.volume_step <= 0:
        raise ValueError('Volumen o paso inválido')
    step = Decimal(str(info.volume_step))
    volume = float((Decimal(str(min(value, info.volume_max))) / step).to_integral_value(rounding=ROUND_DOWN)*step)
    if volume < info.volume_min:
        raise ValueError('El riesgo permitido no alcanza el lote mínimo; no se redondea hacia arriba')
    return volume


class MT5Worker:
    def __init__(self, mt5, account):
        self.mt5, self.account = mt5, account
        self.owner = uuid.uuid4().hex
        self.signals = Backtester()
        self.ready_algorithms=set()

    def verify(self):
        info = self.mt5.account_info()
        terminal = self.mt5.terminal_info()
        if info is None or terminal is None or not terminal.connected:
            raise RuntimeError('MT5 desconectado')
        if int(info.login) != int(self.account['login']) or info.server != self.account['server']:
            raise RuntimeError('El login/servidor del terminal no coincide con la cuenta registrada')
        if info.trade_mode != self.mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Este conector solo permite cuentas DEMO; no enviará órdenes reales')
        if info.margin_mode != self.mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING:
            raise RuntimeError('Se requiere cuenta demo HEDGING; netting aún no soportado para atribución de posiciones')
        return info, terminal

    def positions(self):
        positions = self.mt5.positions_get()
        if positions is None:
            raise RuntimeError(f'No se pudieron consultar posiciones: {self.mt5.last_error()}')
        return list(positions)

    def tick(self, symbol, deployment, opening=False):
        if not self.mt5.symbol_select(symbol, True):
            raise RuntimeError(f'Símbolo MT5 no disponible: {symbol}; configura mapeo explícito')
        info, tick = self.mt5.symbol_info(symbol), self.mt5.symbol_info_tick(symbol)
        if info is None or tick is None or tick.bid <= 0 or tick.ask < tick.bid:
            raise RuntimeError(f'Sin cotización válida: {symbol}')
        if time.time()-tick.time > 30:
            raise MarketDataUnavailable(f'Cotización obsoleta: {symbol}')
        if opening and (tick.ask-tick.bid)/info.point > deployment['max_spread_points']:
            raise RuntimeError(f'Spread excedido: {symbol}')
        return info, tick

    def bars(self, symbol, timeframe):
        if not self.mt5.symbol_select(symbol, True):
            raise RuntimeError(f'Símbolo MT5 no disponible: {symbol}; configura su nombre exacto en el bróker')
        tf = {'30m':self.mt5.TIMEFRAME_M30, '1h':self.mt5.TIMEFRAME_H1,
              '4h':self.mt5.TIMEFRAME_H4, '1d':self.mt5.TIMEFRAME_D1}[timeframe]
        rates = self.mt5.copy_rates_from_pos(symbol, tf, 1, 1000)
        if rates is None or len(rates) < 200:
            raise RuntimeError(f'Histórico insuficiente en MT5: {symbol}/{timeframe} (mínimo 200 velas cerradas)')
        frame = pd.DataFrame(rates)
        frame.index = pd.to_datetime(frame.pop('time'), unit='s', utc=True).dt.tz_localize(None)
        frame = frame.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','tick_volume':'Volume'})
        return frame[['Open','High','Low','Close','Volume']].sort_index()

    def local_state(self, deployment):
        try:
            return store.get('runtime', deployment['id'])
        except KeyError:
            return {'bars':{}, 'positions':{}, 'baseline_master':None}

    def send(self, deployment, key, request):
        if not store.lease(self.account['id'],self.owner):
            raise LeaseLost('El worker perdió la exclusividad de la cuenta')
        account_info,terminal=self.verify()  # Recheck identity before every broker mutation.
        pending_action = getattr(self.mt5, 'TRADE_ACTION_PENDING', 5)
        opening = (request.get('action') in (self.mt5.TRADE_ACTION_DEAL, pending_action)
                   and not request.get('position'))
        if opening:
            current=store.get('deployment',deployment['id'])
            if current['state'] != 'ACTIVE' or not self.risk_allowed(current,account_info):
                return None
        with store.connect() as db:
            pending = db.execute("SELECT id FROM actions WHERE id LIKE ? AND state IN ('SENDING','UNKNOWN') LIMIT 1",(deployment['id']+':%',)).fetchone()
        if pending:
            current=store.get('deployment',deployment['id'])
            current['state']='PAUSED'
            store.put('deployment',current['id'],current)
            raise RuntimeError(f'Orden pendiente de reconciliación manual: {pending["id"]}. No se reenvía ni se abren nuevas órdenes.')
        if not account_info.trade_allowed or not terminal.trade_allowed:
            raise RuntimeError('Trading automático no permitido en la cuenta/terminal')
        request['magic'] = int(deployment['magic'])
        request['comment'] = 'STX'+uuid.uuid5(uuid.NAMESPACE_OID, key).hex[:20]
        with store.connect() as db:
            if db.execute('SELECT 1 FROM actions WHERE id=?',(key,)).fetchone():return None
        # OrderCheck is read-only. A timeout here must not become an uncertain sent order.
        check = self.mt5.order_check(request)
        if check is None or check.retcode != 0:
            message = f'order_check rechazado: {check}'
            if store.claim_action(key,request):store.finish_action(key,'REJECTED',{'message':message})
            store.log(self.account['id'], deployment['id'], message)
            return None
        if not store.lease(self.account['id'],self.owner):raise LeaseLost('El worker perdió la exclusividad antes de enviar')
        if opening and store.get('deployment',deployment['id'])['state']!='ACTIVE':return None
        if not store.claim_action(key, request):return None
        try:
            result = self.mt5.order_send(request)
            if result is None:
                raise RuntimeError(f'Resultado incierto de order_send: {self.mt5.last_error()}')
            result_dict = result._asdict()
            accepted = (self.mt5.TRADE_RETCODE_DONE, self.mt5.TRADE_RETCODE_DONE_PARTIAL)
            if request.get('action') == pending_action:
                accepted += (getattr(self.mt5, 'TRADE_RETCODE_PLACED', 10008),)
            if result.retcode not in accepted:
                if result.retcode in (getattr(self.mt5,'TRADE_RETCODE_TIMEOUT',10012), getattr(self.mt5,'TRADE_RETCODE_CONNECTION',10031), getattr(self.mt5,'TRADE_RETCODE_PLACED',10008)):
                    raise RuntimeError(f'Orden con resultado incierto: {result.retcode}')
                store.finish_action(key, 'REJECTED', result_dict)
                store.log(self.account['id'], deployment['id'], f'Orden rechazada: {result.retcode} {result.comment}')
                return None
            if request.get('action')==pending_action and result.volume<=0:
                from backend.ea_bridge import EAResult
                result=EAResult(**dict(result_dict,volume=request['volume']))
                result_dict=result._asdict()
            store.finish_action(key, 'EXECUTED', result_dict)
            store.log(self.account['id'], deployment['id'], f'{deployment.get("name","STX")} · Ejecución {getattr(self.mt5,"platform","MT5")}: {request["comment"]}; acción={request["action"]}; retcode={result.retcode}; orden={result.order}; volumen={result.volume}')
            return result
        except Exception as error:
            store.finish_action(key, 'UNKNOWN', {'error':str(error)})
            # Ambiguous mutations must be inspected/reconciled, never blindly retried.
            current = store.get('deployment', deployment['id'])
            current['state'] = 'PAUSED'
            store.put('deployment', current['id'], current)
            raise

    def filling(self, info):
        if info.filling_mode & 2:
            return self.mt5.ORDER_FILLING_IOC
        if info.filling_mode & 1:
            return self.mt5.ORDER_FILLING_FOK
        if info.trade_exemode == getattr(self.mt5,'SYMBOL_TRADE_EXECUTION_MARKET',2):
            raise RuntimeError('El símbolo no anuncia FOK/IOC para Market Execution')
        return self.mt5.ORDER_FILLING_RETURN

    def open_position(self, deployment, key, symbol, direction, sl, tp, weight=1.,source_volume=None,source_equity=None,
                      entry_order_type='MARKET',entry_price=None,expiration=0):
        if store.get('deployment',deployment['id'])['state'] != 'ACTIVE':
            return None
        pending=entry_order_type!='MARKET'
        orders=list(self.mt5.orders_get() or []) if pending else []
        if len(self.positions())+len(orders) >= deployment['max_positions']:
            raise RuntimeError('Límite de posiciones alcanzado')
        info, tick = self.tick(symbol, deployment, opening=True)
        kind = self.mt5.ORDER_TYPE_BUY if direction == 'BUY' else self.mt5.ORDER_TYPE_SELL
        price = tick.ask if direction == 'BUY' else tick.bid
        if pending:
            if entry_order_type not in ('LIMIT','STOP'):raise RuntimeError('Tipo de entrada no admitido')
            if expiration and not (getattr(info,'expiration_mode',0)&4):raise RuntimeError('El símbolo/EA no anuncia expiración de pendientes; actualiza el conector')
            if expiration and expiration<=tick.time:raise RuntimeError('La orden pendiente ya está vencida')
            price=round(float(entry_price),info.digits)
            distance=info.trade_stops_level*info.point
            reference=tick.ask if direction=='BUY' else tick.bid
            sign=1 if direction=='BUY' else -1
            offset=sign*(price-reference)
            if (entry_order_type=='LIMIT' and offset>=-distance) or (entry_order_type=='STOP' and offset<=distance):
                raise RuntimeError('El precio pendiente no cumple la distancia mínima del bróker')
        if not all(math.isfinite(v) and v > 0 for v in (price, sl, tp)):
            raise RuntimeError('SL/TP inválidos; no se abrirá una posición sin protección')
        stop_distance = info.trade_stops_level*info.point
        reference = price if pending else (tick.bid if direction == 'BUY' else tick.ask)
        if (direction == 'BUY' and (sl >= reference-stop_distance or tp <= reference+stop_distance)) or (direction == 'SELL' and (sl <= reference+stop_distance or tp >= reference-stop_distance)):
            raise RuntimeError('SL/TP no cumplen la distancia mínima del bróker')
        account_info=self.mt5.account_info()
        equity = account_info.equity
        one_lot_loss = self.mt5.order_calc_profit(kind, symbol, 1., price, sl)
        if one_lot_loss is None or one_lot_loss >= 0:
            raise RuntimeError('No se pudo calcular el riesgo en moneda de la cuenta')
        cash_risk = equity*deployment['risk_percent']/100*weight
        strategy_sizing=deployment.get('strategy_sizing_mode')
        if source_volume is None and strategy_sizing in ('FIXED_RISK','FIXED_CASH'):
            multiplier=deployment.get('strategy_risk_multiplier',1.)
            if not math.isfinite(multiplier) or multiplier<=0:raise RuntimeError('Multiplicador de riesgo inválido')
            if strategy_sizing=='FIXED_CASH':
                if account_info.currency!='USD':raise RuntimeError('Riesgo fijo USD requiere cuenta denominada en USD')
                cash_risk=deployment['strategy_cash_risk']*weight
            cash_risk*=multiplier
            if not math.isfinite(cash_risk) or cash_risk<=0 or cash_risk>equity*.05:
                raise RuntimeError('Riesgo efectivo inválido o superior al máximo de 5% por entrada')
        requested = deployment['fixed_lot']*weight if deployment['fixed_lot'] else cash_risk/abs(one_lot_loss)
        if deployment.get('risk_mode')=='RISK_PERCENT':
            requested=cash_risk/abs(one_lot_loss)
        if source_volume is not None:
            mode=deployment.get('risk_mode','RISK_PERCENT')
            source_volume*=deployment.get('quantity_ratio') or 1.
            if mode=='RISK_PERCENT':
                requested=cash_risk/abs(one_lot_loss)
            elif mode=='FIXED_LOT':
                requested=deployment['fixed_lot']
            elif mode=='MULTIPLIER':
                requested=source_volume*deployment.get('multiplier',1.)
            elif mode=='MIRROR':
                requested=source_volume
            elif mode=='PROPORTIONAL':
                if not source_equity or source_equity<=0:
                    raise RuntimeError('Equity master no disponible para sizing proporcional')
                requested=source_volume*equity/source_equity
        volume = floor_volume(min(requested, deployment['max_lot']), info)
        if deployment.get('partial_exit_pct') is not None:
            fraction=deployment['partial_exit_pct']/100
            try:
                partial=floor_volume(volume*fraction,info)
            except ValueError:
                raise RuntimeError('El lote calculado no permite el cierre parcial configurado; aumenta el tamaño o cambia la salida')
            if not 0<fraction<1 or volume-partial<info.volume_min-1e-9:
                raise RuntimeError('El cierre parcial dejaría un volumen inferior al mínimo del bróker')
        existing=self.positions()
        exposure_symbol=sum(p.volume for p in existing if p.symbol==symbol)
        exposure_total=sum(p.volume for p in existing)
        if deployment.get('max_exposure_per_symbol',0)>0 and exposure_symbol+volume>deployment['max_exposure_per_symbol']+1e-9:
            raise RuntimeError('Exposición máxima por símbolo excedida')
        if deployment.get('max_total_exposure',0)>0 and exposure_total+volume>deployment['max_total_exposure']+1e-9:
            raise RuntimeError('Exposición máxima total excedida')
        if volume*abs(one_lot_loss) > cash_risk+1e-8:
            raise RuntimeError('El lote fijo excede el riesgo máximo configurado')
        request=dict(action=self.mt5.TRADE_ACTION_DEAL,symbol=symbol,type=kind,volume=volume,price=price,
            sl=round(sl,info.digits),tp=round(tp,info.digits),deviation=deployment['deviation_points'],
            type_time=self.mt5.ORDER_TIME_GTC,type_filling=self.filling(info))
        if pending:
            request.update(action=5,type={('BUY','LIMIT'):2,('SELL','LIMIT'):3,('BUY','STOP'):4,('SELL','STOP'):5}[(direction,entry_order_type)],
                type_time=2 if expiration else 0,expiration=int(expiration),type_filling=2)
        return self.send(deployment,key,request)

    def close_position(self, deployment, position, fraction=1., reason='close'):
        if reason=='partial':
            # Check the one-shot exit before calculating half of the residual lot.
            # A successful .02 -> .01 exit must not repeatedly attempt .005 lots.
            with store.connect() as db:
                if db.execute('SELECT 1 FROM actions WHERE id=?',
                              (f'{deployment["id"]}:{position.ticket}:partial',)).fetchone():return None
        info, tick = self.tick(position.symbol, deployment)
        volume = position.volume if fraction == 1 else floor_volume(position.volume*fraction, info)
        if fraction < 1 and position.volume-volume < info.volume_min:
            raise RuntimeError('El cierre parcial dejaría menos del lote mínimo')
        buy = position.type == self.mt5.POSITION_TYPE_BUY
        # A partially filled full-close can continue against the reduced volume.
        # TP1 remains one-shot regardless of residual volume.
        operation = reason if reason == 'partial' else f'{reason}:{position.volume}'
        return self.send(deployment, f'{deployment["id"]}:{position.ticket}:{operation}',
                         dict(action=self.mt5.TRADE_ACTION_DEAL, position=int(position.ticket),
                              symbol=position.symbol, volume=volume,
                              type=self.mt5.ORDER_TYPE_SELL if buy else self.mt5.ORDER_TYPE_BUY,
                              price=tick.bid if buy else tick.ask, deviation=deployment['deviation_points'],
                              type_time=self.mt5.ORDER_TIME_GTC, type_filling=self.filling(info)))

    def modify(self, deployment, position, sl, tp):
        if not all(math.isfinite(float(v)) and float(v)>0 for v in (sl,tp)):
            raise RuntimeError('No se eliminan protecciones SL/TP con valores inválidos o cero')
        info, tick = self.tick(position.symbol, deployment)
        sl, tp = round(float(sl), info.digits), round(float(tp), info.digits)
        if abs(sl-position.sl) < info.point and abs(tp-position.tp) < info.point:
            return
        distance = max(info.trade_stops_level, info.trade_freeze_level)*info.point
        buy = position.type == self.mt5.POSITION_TYPE_BUY
        if (buy and (sl >= tick.bid-distance or tp <= tick.bid+distance)) or (not buy and (sl <= tick.ask+distance or tp >= tick.ask-distance)):
            return
        revision_key=f'{deployment["id"]}:{position.ticket}'
        try:revision=store.get('protection_revision',revision_key)
        except KeyError:revision={'number':0,'desired':None}
        if revision['desired']!=[sl,tp]:
            revision=dict(number=revision['number']+1,desired=[sl,tp]);store.put('protection_revision',revision_key,revision)
        self.send(deployment, f'{deployment["id"]}:{position.ticket}:modify:{revision["number"]}',
                  dict(action=self.mt5.TRADE_ACTION_SLTP, position=int(position.ticket),symbol=position.symbol,sl=sl,tp=tp))

    def risk_allowed(self, deployment, info):
        key = self.account['id']
        today = datetime.now(timezone.utc).date().isoformat()
        try:
            risk = store.get('risk', key)
        except KeyError:
            risk = {'day':today,'day_equity':info.equity,'peak':info.equity}
        if risk['day'] != today:
            risk.update(day=today,day_equity=info.equity)
        risk['peak'] = max(risk['peak'], info.equity)
        store.put('risk', key, risk)
        daily = 100*(risk['day_equity']-info.equity)/max(risk['day_equity'],1e-9)
        dd = 100*(risk['peak']-info.equity)/max(risk['peak'],1e-9)
        gain_limit=deployment.get('max_daily_gain_pct',0)
        equity_floor=deployment.get('equity_protection',0)
        total_gain=deployment.get('max_account_gain_pct',0)
        initial_equity=deployment.get('initial_equity') or 0
        return ((deployment['max_daily_loss_pct']<=0 or daily < deployment['max_daily_loss_pct'])
                and (deployment['max_drawdown_pct']<=0 or dd < deployment['max_drawdown_pct'])
                and (total_gain<=0 or (initial_equity>0 and 100*(info.equity-initial_equity)/initial_equity<total_gain))
                and (gain_limit<=0 or -daily<gain_limit)
                and (equity_floor<=0 or info.equity>equity_floor))

    def algorithm(self, deployment, runtime, item, index, may_open):
        strategy = Strategy.from_dict(item['strategy'])
        symbol = deployment['symbol_map'].get(strategy.symbol, strategy.symbol)
        self.tick(symbol, deployment)
        bars = self.bars(symbol, strategy.timeframe)
        macro = [name[6:] for name in strategy.get_used_indicators() if name.startswith('MACRO_')]
        if macro:
            from backend.macro_manager import macro_manager
            bars = macro_manager.attach_macro(bars, macro)
        buys, sells = self.signals.generate_signal_arrays(bars, strategy)
        buy, sell = bool(buys[-1]), bool(sells[-1])
        if strategy.mtf_timeframe:
            higher = self.bars(symbol, strategy.mtf_timeframe)
            if macro:
                higher = macro_manager.attach_macro(higher, macro)
            # HTF bars must have closed no later than the decision bar's close.
            decision_time = bars.index[-1] + pd.Timedelta(seconds=TF_SECONDS[strategy.timeframe])
            higher = higher[higher.index + pd.Timedelta(seconds=TF_SECONDS[strategy.mtf_timeframe]) <= decision_time]
            if len(higher) < 200:
                raise RuntimeError('Sin historial HTF cerrado suficiente')
            hb, hs = self.signals.generate_signal_arrays(higher, strategy)
            buy, sell = buy and bool(hb[-1]), sell and bool(hs[-1])
        atr = float((indicator_engine.atr_smoothed(bars,14,50) if strategy.exit_mode == 'ATR_SMOOTHED' else indicator_engine.atr(bars,14)).iloc[-1])
        if not math.isfinite(atr) or atr <= 0:
            raise RuntimeError('ATR no disponible')
        tag = f'{deployment["id"]}:algo:{index}'
        if tag not in self.ready_algorithms:
            store.log(self.account['id'],deployment['id'],f'ALGORITMO LISTO · {strategy.name} · {symbol}/{strategy.timeframe} · {len(bars)} velas cerradas · salida {strategy.exit_mode}')
            self.ready_algorithms.add(tag)
        magic = deployment['magic']+index
        sub = dict(deployment, magic=magic,name=strategy.name)
        if strategy.exit_mode=='PARTIAL_TP':sub['partial_exit_pct']=strategy.partial_pct
        if deployment.get('uses_source_risk') and deployment.get('origin_type','strategy')=='strategy':
            sub.update(strategy_sizing_mode=strategy.sizing_mode,strategy_risk_multiplier=strategy.risk_multiplier,
                       strategy_cash_risk=strategy.fixed_cash_risk,risk_percent=strategy.risk_per_trade_pct,
                       risk_mode='FIXED_LOT' if strategy.sizing_mode=='FIXED_LOT' else 'RISK_PERCENT',
                       fixed_lot=strategy.fixed_lot if strategy.sizing_mode=='FIXED_LOT' else 0)
        positions = [p for p in self.positions() if p.magic == magic]
        orders=[o for o in self.mt5.orders_get() if o.magic==magic] if strategy.entry_order_type!='MARKET' else []
        now = datetime.now(timezone.utc)
        daily_key=tag+':'+now.date().isoformat()
        for ticket,ref in list(runtime.get('pending_entries',{}).items()):
            if ref['tag']!=tag:continue
            if any(p.comment==ref['comment'] for p in positions):
                counts=runtime.setdefault('entry_counts',{});counts[daily_key]=counts.get(daily_key,0)+1
                del runtime['pending_entries'][ticket]
            elif not any(str(o.ticket)==ticket for o in orders):del runtime['pending_entries'][ticket]
        for position in positions:
            is_buy = position.type == self.mt5.POSITION_TYPE_BUY
            _, tick = self.tick(symbol, sub)
            price = tick.bid if is_buy else tick.ask
            move = price-position.price_open if is_buy else position.price_open-price
            if (strategy.close_before_weekend and now.weekday()==4 and now.hour>=20) or (strategy.close_before_ny_close and now.hour==20 and now.minute>=55):
                self.close_position(sub,position,reason='schedule')
                continue
            entry_bar=(position.time//TF_SECONDS[strategy.timeframe])*TF_SECONDS[strategy.timeframe]
            closed_bars=int(((bars.index.astype('int64')//10**9)>=entry_bar).sum())
            if strategy.exit_mode == 'TIME_EXIT' and closed_bars>=strategy.max_bars:
                self.close_position(sub,position,reason='time')
                continue
            if (is_buy and sell) or (not is_buy and buy):
                self.close_position(sub,position,reason='opposite')
                continue
            sl = position.sl
            def improve(candidate):
                return max(sl,candidate) if is_buy else min(sl,candidate)
            if strategy.exit_mode == 'TRAILING_ATR' or strategy.modifier_trailing:
                sl = improve(price-atr*strategy.trail_atr if is_buy else price+atr*strategy.trail_atr)
            if (strategy.exit_mode == 'BREAKEVEN' or strategy.modifier_breakeven) and move >= atr*strategy.be_atr:
                sl = improve(position.price_open)
            if strategy.exit_mode == 'STRUCTURE_SWING':
                sl = improve(float(bars['Low'].tail(strategy.swing_bars).min()) if is_buy else float(bars['High'].tail(strategy.swing_bars).max()))
            if strategy.exit_mode == 'PARTIAL_TP' and move >= atr*strategy.partial_tp1_atr:
                self.close_position(sub,position,fraction=strategy.partial_pct/100,reason='partial')
                sl = improve(position.price_open)
            self.modify(sub,position,sl,position.tp)
        # One entry per closed bar, persisted before any broker request.
        bar = bars.index[-1].isoformat()
        old_bar = runtime['bars'].get(tag)
        if orders:
            if old_bar is not None and old_bar!=bar:
                from backend.mt5_diagnostic import cancel_pending
                for order in orders:cancel_pending(self,sub,order)
            store.put('runtime',deployment['id'],runtime)
            return
        runtime['bars'][tag] = bar
        store.put('runtime',deployment['id'],runtime)
        if not may_open or positions or old_bar == bar:
            return
        if time.time() - (bars.index[-1].timestamp()+TF_SECONDS[strategy.timeframe]) > TF_SECONDS[strategy.timeframe]:
            return
        if strategy.close_before_weekend and now.weekday() >= 4 and now.hour >= 20:
            return
        if not buy and not sell:
            store.log(self.account['id'],deployment['id'],f'SIN SEÑAL · {strategy.name} · vela cerrada {bar}')
            return
        if strategy.max_daily_trades>0 and runtime.get('entry_counts',{}).get(daily_key,0)>=strategy.max_daily_trades:
            return
        direction = 'BUY' if buy else 'SELL'
        if deployment.get('direction_filter','BOTH') not in ('BOTH',direction):
            return
        symbols=deployment.get('symbol_whitelist',[])
        symbol_filter=deployment.get('symbol_filter','WHITELIST')
        if symbols and ((symbol_filter=='WHITELIST' and strategy.symbol not in symbols)
                        or (symbol_filter=='BLACKLIST' and strategy.symbol in symbols)):
            return
        info, tick = self.tick(symbol,sub,opening=True)
        entry = tick.ask if direction=='BUY' else tick.bid
        if strategy.entry_order_type!='MARKET':
            entry+=(1 if direction=='BUY' else -1)*atr*.2*(-1 if strategy.entry_order_type=='LIMIT' else 1)
        pip = SUPPORTED_SYMBOLS.get(strategy.symbol,{}).get('pip_size',info.point*(10 if info.digits in (3,5) else 1))
        sl_distance, tp_distance = atr*strategy.sl_atr, atr*strategy.tp_atr
        if strategy.exit_mode == 'PIPS_FIXED':
            sl_distance,tp_distance = pip*strategy.sl_pips,pip*strategy.tp_pips
        elif strategy.exit_mode == 'PCT_EXIT':
            sl_distance,tp_distance = entry*strategy.sl_pct/100,entry*strategy.tp_pct/100
        elif strategy.exit_mode == 'ATR_SMOOTHED':
            sl_distance,tp_distance = atr*strategy.sl_smooth_mult,atr*strategy.tp_smooth_mult
        elif strategy.exit_mode == 'PARTIAL_TP':
            tp_distance = atr*strategy.partial_tp2_atr
        if strategy.fixed_rr > 0:
            tp_distance = sl_distance*strategy.fixed_rr
        if deployment.get('sl_tp_mode')=='CUSTOM':
            sl_distance,tp_distance=pip*deployment['custom_sl_pips'],pip*deployment['custom_tp_pips']
        if strategy.reward_risk_ratio > 0:
            tp_distance=max(tp_distance,sl_distance*strategy.reward_risk_ratio)
        sign = 1 if direction=='BUY' else -1
        key=f'{tag}:{bar}'
        conditions=strategy.buy_conditions if direction=='BUY' else strategy.sell_conditions
        store.log(self.account['id'],deployment['id'],f'SEÑAL {direction} · {strategy.name} · vela cerrada {bar} · '+
                  ' Y '.join(c.to_human_string() for c in conditions))
        result=self.open_position(sub,key,symbol,direction,entry-sign*sl_distance,entry+sign*tp_distance,item['weight'],
            entry_order_type=strategy.entry_order_type,entry_price=entry,
            expiration=int(bars.index[-1].timestamp())+2*TF_SECONDS[strategy.timeframe])
        if result:
            if strategy.entry_order_type=='MARKET':
                counts=runtime.setdefault('entry_counts',{})
                counts[daily_key]=counts.get(daily_key,0)+1
                runtime['entry_counts']={k:v for k,v in counts.items() if k.endswith(now.date().isoformat())}
            else:
                comment='STX'+uuid.uuid5(uuid.NAMESPACE_OID,key).hex[:20]
                runtime.setdefault('pending_entries',{})[str(result.order)]={'tag':tag,'comment':comment}
            store.put('runtime',deployment['id'],runtime)

    def account_copy(self, deployment, runtime, may_open):
        source = store.get('snapshot',deployment['source_id'])
        if time.time()-source['at'] > 15 or not source.get('verified_demo'):
            raise RuntimeError('Master desconectada/obsoleta: no se infieren cierres ni se abren copias')
        master = {str(p['ticket']):p for p in source['positions']}
        if deployment.get('copy_source_symbol'):
            master={ticket:p for ticket,p in master.items() if p['symbol']==deployment['copy_source_symbol']}
        instance=source.get('source_instance')
        if runtime.get('source_instance') and runtime['source_instance']!=instance:
            raise RuntimeError('Master NT8 reiniciada: crea una nueva copia tras reconciliar posiciones; no se infieren cierres')
        if instance:runtime['source_instance']=instance
        if runtime['baseline_master'] is None:
            runtime['baseline_master'] = list(master)
            if not deployment.get('copy_source_symbol'):store.put('runtime',deployment['id'],runtime)
        if not may_open:
            runtime['baseline_master']=list(set(runtime['baseline_master']).union(master))
        from backend.pending_copy import synchronize_pending
        pending_sources=synchronize_pending(self,deployment,runtime,source,may_open)
        positions = self.positions()
        for ticket, ref in list(runtime['positions'].items()):
            local = next((p for p in positions if p.magic==deployment['magic'] and p.comment==ref['comment']),None)
            if local is None:
                continue  # Broker/manual closure is respected; never reopen it.
            ref['target_ticket']=local.ticket
            origin = master.get(ticket)
            if origin is None:
                self.close_position(deployment,local,reason='master-close')
            else:
                if deployment.get('sl_tp_mode','PROVIDER')=='PROVIDER':
                    sl,tp=origin['sl'],origin['tp']
                    if ref.get('translated'):
                        sl=ref['target_entry']+(sl-ref['source_entry'])*ref['price_scale'] if sl else 0
                        tp=ref['target_entry']+(tp-ref['source_entry'])*ref['price_scale'] if tp else 0
                    if sl>0 and tp>0:self.modify(deployment,local,sl,tp)
                target = ref['initial_local_volume']*origin['volume']/ref['initial_master_volume']
                info = self.mt5.symbol_info(local.symbol)
                if local.volume-target >= info.volume_step*.99:
                    fraction = min(1.,(local.volume-target)/local.volume)
                    self.close_position(deployment,local,fraction,reason=f'master-volume-{origin["volume"]}')
        if may_open:
            for ticket, origin in master.items():
                if ticket in runtime['positions'] or ticket in runtime['baseline_master'] or ticket in pending_sources:
                    continue
                if len(self.positions()) >= deployment['max_positions']:
                    break
                # Do not chase old master entries after a reconnect.
                if time.time()-origin['time'] > deployment.get('max_order_age_seconds',30):
                    continue
                symbols=deployment.get('symbol_whitelist',[])
                symbol_filter=deployment.get('symbol_filter','WHITELIST')
                if symbols and ((symbol_filter=='WHITELIST' and origin['symbol'] not in symbols)
                                or (symbol_filter=='BLACKLIST' and origin['symbol'] in symbols)):
                    continue
                direction='BUY' if origin['type']==0 else 'SELL'
                if deployment.get('direction_filter','BOTH') not in ('BOTH',direction):
                    continue
                custom=deployment.get('sl_tp_mode','PROVIDER')=='CUSTOM'
                if not custom and (origin['sl'] <= 0 or origin['tp'] <= 0):
                    raise RuntimeError('Señal master sin SL/TP: copia rechazada')
                symbol = deployment['symbol_map'].get(origin['symbol'],origin['symbol'])
                if deployment.get('cross_platform') and origin['symbol'] not in deployment['symbol_map']:
                    continue
                sl,tp=origin['sl'],origin['tp']
                translated=deployment.get('cross_platform') or deployment.get('price_scale',1)!=1
                target_entry=None
                if translated:
                    info,tick=self.tick(symbol,deployment,opening=True)
                    target_entry=tick.ask if direction=='BUY' else tick.bid
                    sl=target_entry+(sl-origin['price_open'])*deployment.get('price_scale',1)
                    tp=target_entry+(tp-origin['price_open'])*deployment.get('price_scale',1)
                    if getattr(self.mt5,'platform','MT5')=='NT8':
                        sl=round(sl/info.point)*info.point
                        tp=round(tp/info.point)*info.point
                if custom:
                    info,tick=self.tick(symbol,deployment,opening=True)
                    pip=info.point*(10 if info.digits in (3,5) else 1)
                    price=tick.ask if direction=='BUY' else tick.bid
                    sign=1 if direction=='BUY' else -1
                    sl=price-sign*deployment['custom_sl_pips']*pip
                    tp=price+sign*deployment['custom_tp_pips']*pip
                key = f'{deployment["id"]}:master:{ticket}'
                comment = 'STX'+uuid.uuid5(uuid.NAMESPACE_OID,key).hex[:20]
                result = self.open_position(deployment,key,symbol,direction,sl,tp,
                                            source_volume=origin['volume'],source_equity=source.get('equity'))
                if result:
                    matched=next((p for p in self.positions() if p.magic==deployment['magic'] and p.comment==comment),None)
                    runtime['positions'][ticket] = dict(comment=comment,source_ticket=ticket,target_order=result.order,
                        target_native_order_id=getattr(result,'native_order_id',None),
                        target_ticket=matched.ticket if matched else None,
                        source_symbol=origin['symbol'],target_symbol=symbol,initial_master_volume=origin['volume'],
                        initial_local_volume=result.volume,translated=bool(translated),target_entry=matched.price_open if matched and translated else target_entry,
                        source_entry=origin.get('price_open'),price_scale=deployment.get('price_scale',1))
                    store.log(self.account['id'],deployment['id'],f'COPY {ticket} → {result.order} · {origin["symbol"]} {origin["volume"]} → {symbol} {result.volume}')
                    if not deployment.get('copy_source_symbol'):store.put('runtime',deployment['id'],runtime)
        if not deployment.get('copy_source_symbol'):store.put('runtime',deployment['id'],runtime)

    def cycle(self):
        if not store.lease(self.account['id'],self.owner):
            raise LeaseLost('Ya existe otro conector para esta cuenta')
        account, _ = self.verify()
        positions = self.positions()
        pending_orders=list(self.mt5.orders_get() or [])
        store.put('snapshot',self.account['id'],dict(at=time.time(),verified_demo=True,
                  login=account.login,server=account.server,balance=account.balance,equity=account.equity,
                  currency=account.currency,positions=[{k:getattr(p,k) for k in
                  ('ticket','symbol','type','volume','price_open','sl','tp','magic','comment','time')}
                  | {'identifier':getattr(p,'identifier',p.ticket),'source_order':getattr(p,'identifier',p.ticket)} for p in positions],
                  orders=[vars(o) if hasattr(o,'__dict__') else o._asdict() for o in pending_orders],
                  quotes={symbol:vars(t) if hasattr(t,'__dict__') else t._asdict() for symbol in
                    {p.symbol for p in positions}.union(o.symbol for o in pending_orders)
                    if (t:=self.mt5.symbol_info_tick(symbol)) is not None}))
        for deployment in store.listing('deployment'):
            if deployment['account_id'] != self.account['id'] or deployment['state']=='STOPPED':
                continue
            try:
                runtime = self.local_state(deployment)
                magics = range(deployment['magic'],deployment['magic']+max(1,len(deployment['strategies'])))
                managed = [p for p in self.positions() if p.magic in magics]
                if deployment['state']=='CLOSING':
                    if hasattr(self.mt5, 'orders_get'):
                        from backend.mt5_diagnostic import pending_orders, cancel_pending
                        for order in pending_orders(self):
                            if order.magic in magics:
                                cancel_pending(self,dict(deployment,magic=order.magic),order)
                    for p in managed:
                        self.close_position(dict(deployment,magic=p.magic),p,reason='stop')
                    remaining_orders = [o for o in self.mt5.orders_get() if o.magic in magics] if hasattr(self.mt5,'orders_get') else []
                    if not managed and not remaining_orders:
                        current=store.get('deployment',deployment['id'])
                        current['state']='STOPPED'
                        store.put('deployment',deployment['id'],current)
                    continue
                allowed = self.risk_allowed(deployment,account)
                may_open = deployment['state']=='ACTIVE' and allowed and len(self.positions()) < deployment['max_positions']
                if not allowed and deployment['state']=='ACTIVE':
                    current=store.get('deployment',deployment['id'])
                    if current['state']=='ACTIVE':
                        current['state']='PAUSED'
                        store.put('deployment',deployment['id'],current)
                    store.log(self.account['id'],deployment['id'],'Pausa por límite de equity diario/drawdown; posiciones siguen protegidas por SL/TP')
                if deployment['source_type']=='diagnostic':
                    from backend.mt5_diagnostic import run
                    run(self,deployment,may_open)
                elif deployment['source_type']=='account':
                    self.account_copy(deployment,runtime,may_open)
                else:
                    for index,item in enumerate(deployment['strategies']):
                        self.algorithm(deployment,runtime,item,index,may_open)
            except Exception as error:
                message=str(error)
                if deployment['source_type']=='diagnostic':
                    state=store.get('diagnostic',deployment['id'])
                    if isinstance(error,(MarketDataUnavailable,BridgeReadUnavailable)):
                        message='Esperando cotización reciente; no se envían órdenes con precios obsoletos: '+message
                        if state['phase']=='WAIT' and not state.get('opening_ticket'):
                            state['phase']='OPEN'
                    elif state['phase']=='OPEN' and not state.get('audit_complete'):
                        message='Esperando datos para iniciar el algoritmo: '+message
                    else:
                        state.update(phase='CLEANUP',outcome='FAIL',detail=message)
                    store.put('diagnostic',deployment['id'],state)
                try:
                    previous=store.get('last_error',deployment['id'])
                except KeyError:
                    previous={}
                if previous.get('message')!=message or time.time()-previous.get('at',0)>60:
                    store.log(self.account['id'],deployment['id'],message)
                    store.put('last_error',deployment['id'],dict(message=message,at=time.time()))


def main():
    parser=argparse.ArgumentParser(description='Stratix MT5 demo connector')
    parser.add_argument('--account',required=True)
    args=parser.parse_args()
    account=store.get('account',args.account)
    if account.get('connection_mode') == 'EA':
        from backend.ea_bridge import EABroker
        mt5 = EABroker(account)
    else:
        import MetaTrader5 as mt5
    worker=MT5Worker(mt5,account)
    if not store.lease(account['id'],worker.owner):
        raise SystemExit('Ya existe un worker para esta cuenta')
    while True:
        try:
            if store.get('worker_control',account['id']).get('stop'):
                break
        except KeyError:
            pass
        try:
            if not store.lease(account['id'],worker.owner):
                break
            if not mt5.initialize(account['terminal_path'],timeout=10000):
                raise RuntimeError(f'No se pudo inicializar MT5: {mt5.last_error()}')
            worker.cycle()
        except KeyboardInterrupt:
            break
        except LeaseLost:
            break
        except Exception as error:
            store.log(account['id'],'',str(error))
            store.put('snapshot',account['id'],dict(at=0,verified_demo=False,error=str(error),positions=[]))
            mt5.shutdown()
        time.sleep(2)
    mt5.shutdown()
    with store.connect() as db:
        owned=db.execute('DELETE FROM leases WHERE account=? AND owner=?',(account['id'],worker.owner)).rowcount
    if owned:
        store.put('snapshot',account['id'],dict(at=0,verified_demo=False,error='Conector detenido',positions=[]))


if __name__=='__main__':
    main()

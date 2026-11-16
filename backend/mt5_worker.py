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

TF_SECONDS = {'30m':1800, '1h':3600, '4h':14400, '1d':86400}


class LeaseLost(RuntimeError):
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
            raise RuntimeError(f'Cotización obsoleta: {symbol}')
        if opening and (tick.ask-tick.bid)/info.point > deployment['max_spread_points']:
            raise RuntimeError(f'Spread excedido: {symbol}')
        return info, tick

    def bars(self, symbol, timeframe):
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
        self.verify()  # Recheck identity immediately before every broker mutation.
        opening = request.get('action') == self.mt5.TRADE_ACTION_DEAL and not request.get('position')
        if opening:
            current=store.get('deployment',deployment['id'])
            if current['state'] != 'ACTIVE' or not self.risk_allowed(current,self.mt5.account_info()):
                return None
        with store.connect() as db:
            pending = db.execute("SELECT id FROM actions WHERE id LIKE ? AND state IN ('SENDING','UNKNOWN') LIMIT 1",(deployment['id']+':%',)).fetchone()
        if pending:
            current=store.get('deployment',deployment['id'])
            current['state']='PAUSED'
            store.put('deployment',current['id'],current)
            raise RuntimeError(f'Orden pendiente de reconciliación manual: {pending["id"]}. No se reenvía ni se abren nuevas órdenes.')
        if not self.mt5.account_info().trade_allowed or not self.mt5.terminal_info().trade_allowed:
            raise RuntimeError('Trading automático no permitido en la cuenta/terminal')
        request['magic'] = int(deployment['magic'])
        request['comment'] = 'STX'+uuid.uuid5(uuid.NAMESPACE_OID, key).hex[:20]
        if not store.claim_action(key, request):
            return None
        try:
            check = self.mt5.order_check(request)
            if check is None or check.retcode != 0:
                message = f'order_check rechazado: {check}'
                store.finish_action(key, 'REJECTED', {'message':message})
                store.log(self.account['id'], deployment['id'], message)
                return None
            result = self.mt5.order_send(request)
            if result is None:
                raise RuntimeError(f'Resultado incierto de order_send: {self.mt5.last_error()}')
            result_dict = result._asdict()
            if result.retcode not in (self.mt5.TRADE_RETCODE_DONE, self.mt5.TRADE_RETCODE_DONE_PARTIAL):
                if result.retcode in (getattr(self.mt5,'TRADE_RETCODE_TIMEOUT',10012), getattr(self.mt5,'TRADE_RETCODE_CONNECTION',10031), getattr(self.mt5,'TRADE_RETCODE_PLACED',10008)):
                    raise RuntimeError(f'Orden con resultado incierto: {result.retcode}')
                store.finish_action(key, 'REJECTED', result_dict)
                store.log(self.account['id'], deployment['id'], f'Orden rechazada: {result.retcode} {result.comment}')
                return None
            store.finish_action(key, 'EXECUTED', result_dict)
            store.log(self.account['id'], deployment['id'], f'Ejecución MT5: {request["comment"]}; retcode={result.retcode}; orden={result.order}; volumen={result.volume}')
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

    def open_position(self, deployment, key, symbol, direction, sl, tp, weight=1.,source_volume=None,source_equity=None):
        if store.get('deployment',deployment['id'])['state'] != 'ACTIVE':
            return None
        if len(self.positions()) >= deployment['max_positions']:
            raise RuntimeError('Límite de posiciones alcanzado')
        info, tick = self.tick(symbol, deployment, opening=True)
        kind = self.mt5.ORDER_TYPE_BUY if direction == 'BUY' else self.mt5.ORDER_TYPE_SELL
        price = tick.ask if direction == 'BUY' else tick.bid
        if not all(math.isfinite(v) and v > 0 for v in (price, sl, tp)):
            raise RuntimeError('SL/TP inválidos; no se abrirá una posición sin protección')
        stop_distance = info.trade_stops_level*info.point
        reference = tick.bid if direction == 'BUY' else tick.ask
        if (direction == 'BUY' and (sl >= reference-stop_distance or tp <= reference+stop_distance)) or (direction == 'SELL' and (sl <= reference+stop_distance or tp >= reference-stop_distance)):
            raise RuntimeError('SL/TP no cumplen la distancia mínima del bróker')
        equity = self.mt5.account_info().equity
        one_lot_loss = self.mt5.order_calc_profit(kind, symbol, 1., price, sl)
        if one_lot_loss is None or one_lot_loss >= 0:
            raise RuntimeError('No se pudo calcular el riesgo en moneda de la cuenta')
        cash_risk = equity*deployment['risk_percent']/100*weight
        requested = deployment['fixed_lot']*weight if deployment['fixed_lot'] else cash_risk/abs(one_lot_loss)
        if deployment.get('risk_mode')=='RISK_PERCENT':
            requested=cash_risk/abs(one_lot_loss)
        if source_volume is not None:
            mode=deployment.get('risk_mode','RISK_PERCENT')
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
        existing=self.positions()
        exposure_symbol=sum(p.volume for p in existing if p.symbol==symbol)
        exposure_total=sum(p.volume for p in existing)
        if deployment.get('max_exposure_per_symbol',0)>0 and exposure_symbol+volume>deployment['max_exposure_per_symbol']+1e-9:
            raise RuntimeError('Exposición máxima por símbolo excedida')
        if deployment.get('max_total_exposure',0)>0 and exposure_total+volume>deployment['max_total_exposure']+1e-9:
            raise RuntimeError('Exposición máxima total excedida')
        if volume*abs(one_lot_loss) > cash_risk+1e-8:
            raise RuntimeError('El lote fijo excede el riesgo máximo configurado')
        return self.send(deployment, key, dict(action=self.mt5.TRADE_ACTION_DEAL, symbol=symbol,
                         type=kind, volume=volume, price=price, sl=round(sl, info.digits), tp=round(tp, info.digits),
                         deviation=deployment['deviation_points'], type_time=self.mt5.ORDER_TIME_GTC,
                         type_filling=self.filling(info)))

    def close_position(self, deployment, position, fraction=1., reason='close'):
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
        self.send(deployment, f'{deployment["id"]}:{position.ticket}:modify:{sl}:{tp}',
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
        return (daily < deployment['max_daily_loss_pct'] and dd < deployment['max_drawdown_pct']
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
        magic = deployment['magic']+index
        sub = dict(deployment, magic=magic)
        positions = [p for p in self.positions() if p.magic == magic]
        now = datetime.now(timezone.utc)
        for position in positions:
            is_buy = position.type == self.mt5.POSITION_TYPE_BUY
            _, tick = self.tick(symbol, sub)
            price = tick.bid if is_buy else tick.ask
            move = price-position.price_open if is_buy else position.price_open-price
            if (strategy.close_before_weekend and now.weekday()==4 and now.hour>=20) or (strategy.close_before_ny_close and now.hour==20 and now.minute>=55):
                self.close_position(sub,position,reason='schedule')
                continue
            if strategy.exit_mode == 'TIME_EXIT' and time.time()-position.time >= strategy.max_bars*TF_SECONDS[strategy.timeframe]:
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
        runtime['bars'][tag] = bar
        store.put('runtime',deployment['id'],runtime)
        if not may_open or positions or old_bar == bar:
            return
        if time.time() - (bars.index[-1].timestamp()+TF_SECONDS[strategy.timeframe]) > TF_SECONDS[strategy.timeframe]:
            return
        if strategy.close_before_weekend and now.weekday() >= 4 and now.hour >= 20:
            return
        if not buy and not sell:
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
        if strategy.reward_risk_ratio > 0 and tp_distance/sl_distance < strategy.reward_risk_ratio:
            return
        sign = 1 if direction=='BUY' else -1
        self.open_position(sub, f'{tag}:{bar}',symbol,direction,entry-sign*sl_distance,entry+sign*tp_distance,item['weight'])

    def account_copy(self, deployment, runtime, may_open):
        source = store.get('snapshot',deployment['source_id'])
        if time.time()-source['at'] > 15 or not source.get('verified_demo'):
            raise RuntimeError('Master desconectada/obsoleta: no se infieren cierres ni se abren copias')
        master = {str(p['ticket']):p for p in source['positions']}
        if runtime['baseline_master'] is None:
            runtime['baseline_master'] = list(master)
            store.put('runtime',deployment['id'],runtime)
        positions = self.positions()
        for ticket, ref in list(runtime['positions'].items()):
            local = next((p for p in positions if p.magic==deployment['magic'] and p.comment==ref['comment']),None)
            if local is None:
                continue  # Broker/manual closure is respected; never reopen it.
            origin = master.get(ticket)
            if origin is None:
                self.close_position(deployment,local,reason='master-close')
            else:
                if deployment.get('sl_tp_mode','PROVIDER')=='PROVIDER':
                    self.modify(deployment,local,origin['sl'],origin['tp'])
                target = ref['initial_local_volume']*origin['volume']/ref['initial_master_volume']
                info = self.mt5.symbol_info(local.symbol)
                if local.volume-target >= info.volume_step*.99:
                    fraction = min(1.,(local.volume-target)/local.volume)
                    self.close_position(deployment,local,fraction,reason=f'master-volume-{origin["volume"]}')
        if may_open:
            for ticket, origin in master.items():
                if ticket in runtime['positions'] or ticket in runtime['baseline_master']:
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
                sl,tp=origin['sl'],origin['tp']
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
                    runtime['positions'][ticket] = dict(comment=comment,initial_master_volume=origin['volume'],initial_local_volume=result.volume)
                    store.put('runtime',deployment['id'],runtime)
        store.put('runtime',deployment['id'],runtime)

    def cycle(self):
        if not store.lease(self.account['id'],self.owner):
            raise LeaseLost('Ya existe otro conector para esta cuenta')
        account, _ = self.verify()
        positions = self.positions()
        store.put('snapshot',self.account['id'],dict(at=time.time(),verified_demo=True,
                  login=account.login,server=account.server,balance=account.balance,equity=account.equity,
                  currency=account.currency,positions=[{k:getattr(p,k) for k in
                  ('ticket','symbol','type','volume','price_open','sl','tp','magic','comment','time')} for p in positions]))
        for deployment in store.listing('deployment'):
            if deployment['account_id'] != self.account['id'] or deployment['state']=='STOPPED':
                continue
            try:
                runtime = self.local_state(deployment)
                magics = range(deployment['magic'],deployment['magic']+max(1,len(deployment['strategies'])))
                managed = [p for p in self.positions() if p.magic in magics]
                if deployment['state']=='CLOSING':
                    for p in managed:
                        self.close_position(dict(deployment,magic=p.magic),p,reason='stop')
                    if not managed:
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
                if deployment['source_type']=='account':
                    self.account_copy(deployment,runtime,may_open)
                else:
                    for index,item in enumerate(deployment['strategies']):
                        self.algorithm(deployment,runtime,item,index,may_open)
            except Exception as error:
                message=str(error)
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
    import MetaTrader5 as mt5
    account=store.get('account',args.account)
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

"""One-shot demo diagnostic, persisted between worker cycles. Not a trading strategy."""
import time

from pydantic import BaseModel, Field

from backend import copy_trading as store

CASES = [dict(direction=d,entry='MARKET',exit=e) for d in ('BUY','SELL')
         for e in ('CLOSE','PARTIAL','MODIFY','TIME','SL','TP','BREAKEVEN','TRAILING')]
CASES += [dict(direction=d,entry=e,exit='MODIFY_CANCEL') for e in ('LIMIT','STOP') for d in ('BUY','SELL')]
PROFILE='stx_demo_diagnostic_v1'


def save_test_algorithm():
    from backend.strategy import Strategy
    from backend.portfolio import StrategyRecord
    strategy=Strategy(strategy_id=PROFILE,name='STX · Test integral demo',symbol='EURUSD',timeframe='30m',
        close_before_weekend=False,risk_per_trade_pct=.1,fixed_lot=.02,
        max_daily_loss_pct=0,max_weekly_loss_pct=0,max_monthly_loss_pct=0,max_account_loss_pct=0)
    record=StrategyRecord(dict(strategy=strategy.to_dict(),metrics={},execution_profile=PROFILE,
        description='Diagnóstico demo de 20 casos; no es una estrategia de inversión ni tiene backtest de rentabilidad.',
        diagnostic_config=dict(symbol='EURUSD',timeout_seconds=45,risk_percent=.1),test_cases=CASES))
    return record.save(folder='Pruebas demo')


def configure(record,req):
    record.update(source_type='diagnostic',execution_profile=PROFILE,
        diagnostic_symbol=record.get('symbol_map',{}).get(req.symbol,req.symbol),
        diagnostic_timeout=req.timeout_seconds,audit_indicators=True,
        risk_percent=min(record['risk_percent'],req.risk_percent,.1),max_lot=min(record['max_lot'],.02),
        max_positions=1,fixed_lot=0,risk_mode='RISK_PERCENT')
    store.put('diagnostic',record['id'],dict(index=0,phase='OPEN',results=[]))
    return record


class DiagnosticRequest(BaseModel):
    symbol: str = Field(default='EURUSD',pattern=r'^[A-Za-z0-9_.#-]{1,40}$')
    risk_percent: float = Field(default=.1,gt=0,le=.25)
    timeout_seconds: int = Field(default=45,ge=15,le=300)


def install_routes(app):
    @app.get('/api/copy/diagnostics/{key}')
    def report(key: str):
        try: audit=store.get('indicator_audit',key)
        except KeyError: audit=None
        with store.connect() as db:
            events=[dict(r) for r in db.execute('SELECT created,message FROM events WHERE deployment=? ORDER BY seq DESC LIMIT 200',(key,))]
        return dict(plan=CASES,indicator_audit=audit,events=events,**store.get('diagnostic',key))


def pending_orders(worker):
    result=worker.mt5.orders_get()
    if result is None:
        raise RuntimeError('No se pudieron consultar las órdenes pendientes')
    return list(result)


def cancel_pending(worker,d,order):
    return worker.send(d,f'{d["id"]}:cancel:{order.ticket}',
        dict(action=8,order=int(order.ticket),symbol=order.symbol))


def run(worker,d,may_open):
    state=store.get('diagnostic',d['id'])
    if d.get('audit_indicators') and not state.get('audit_complete'):
        if not may_open: return
        from backend.indicator_audit import audit_frame
        audit=audit_frame(worker.bars(d['diagnostic_symbol'],'30m'))
        platform=getattr(worker.mt5,'platform','MT5')
        store.put('indicator_audit',d['id'],dict(dataset=platform+' closed M30 bars',**audit))
        state['audit_complete']=True
        store.put('diagnostic',d['id'],state)
        store.log(d['account_id'],d['id'],f'Auditoría indicadores {platform}: {audit["passed"]}/{audit["checks"]}, fallos {audit["failed"]}')
        if audit['failed']:
            state['audit_complete']=False
            store.put('diagnostic',d['id'],state)
            current=store.get('deployment',d['id']);current['state']='PAUSED';store.put('deployment',d['id'],current)
            return
    if state['index']>=len(CASES):
        current=store.get('deployment',d['id']);current['state']='STOPPED'
        store.put('deployment',d['id'],current)
        return
    case=CASES[state['index']]
    symbol=d['diagnostic_symbol']
    positions=[p for p in worker.positions() if p.magic==d['magic']]
    orders=[p for p in pending_orders(worker) if p.magic==d['magic']] if case['entry']!='MARKET' else []
    def save(): store.put('diagnostic',d['id'],state)
    def finish(outcome,detail):
        detail=detail.replace('MT5',getattr(worker.mt5,'platform','MT5'))
        state['results'].append(dict(**case,outcome=outcome,detail=detail,at=time.time()))
        store.log(d['account_id'],d['id'],f'Diagnóstico {state["index"]+1}/{len(CASES)} {case}: {outcome} · {detail}')
        next_index=state['index']+1
        results=state['results']
        state.clear()
        state.update(index=next_index,phase='OPEN',results=results,audit_complete=True)
        save()
    if state['phase']=='OPEN':
        if not may_open: return
        if positions or orders:
            raise RuntimeError('El diagnóstico espera limpieza de su caso anterior')
        info,tick=worker.tick(symbol,d,opening=True)
        sign=1 if case['direction']=='BUY' else -1
        price=tick.ask if sign==1 else tick.bid
        distance=max(info.trade_stops_level*info.point*3,(tick.ask-tick.bid)*4,info.point*30)
        if case['entry']!='MARKET':
            price=round(price+sign*distance*(-1 if case['entry']=='LIMIT' else 1),info.digits)
            if getattr(worker.mt5,'platform','MT5')=='NT8':
                price=round(price+sign*distance*7*(-1 if case['entry']=='LIMIT' else 1),info.digits)
        sl,tp=price-sign*distance*2,price+sign*distance*2
        if case['exit']=='SL': sl=price-sign*distance
        if case['exit']=='TP': tp=price+sign*distance
        if getattr(worker.mt5,'platform','MT5')=='NT8':
            # Use a nearby tested boundary and a distant alternative so a
            # native SL/TP case is less likely to finish via the opposite exit.
            reference=tick.bid if sign==1 else tick.ask
            if case['exit']=='SL':sl=reference-sign*info.point*3;tp=price+sign*distance*8
            elif case['exit']=='TP':tp=reference+sign*max(info.point*4,tick.ask-tick.bid+info.point*2);sl=price-sign*distance*4
            elif case['exit'] in ('PARTIAL','BREAKEVEN','TRAILING'):sl=price-sign*distance*4;tp=price+sign*distance*8
        store.log(d['account_id'],d['id'],f'INICIO {state["index"]+1}/{len(CASES)} · {case["direction"]} {case["entry"]} · salida {case["exit"]}')
        # Persist intent before requesting; ambiguous sends never restart a case.
        state.update(phase='WAIT',started=time.time(),distance=distance,entry=price)
        save()
        key=f'{d["id"]}:case:{state["index"]}'
        if state.get('attempt'):key+=f':attempt:{state["attempt"]}'
        if case['entry']=='MARKET':
            result=worker.open_position(d,key,symbol,case['direction'],sl,tp)
        else:
            if worker.positions() or pending_orders(worker):
                raise RuntimeError('Diagnóstico de pendientes requiere cuenta sin otras posiciones/órdenes')
            volume=info.volume_min
            if volume>d['max_lot']: raise RuntimeError('Lote mínimo excede el máximo del diagnóstico')
            loss=worker.mt5.order_calc_profit(0 if sign==1 else 1,symbol,volume,price,sl)
            if loss is None or loss>=0 or abs(loss)>worker.mt5.account_info().equity*d['risk_percent']/100:
                raise RuntimeError('La pendiente mínima supera el presupuesto de riesgo')
            kind={('BUY','LIMIT'):2,('SELL','LIMIT'):3,('BUY','STOP'):4,('SELL','STOP'):5}[(case['direction'],case['entry'])]
            result=worker.send(d,key,dict(action=5,symbol=symbol,type=kind,price=price,volume=volume,
                sl=round(sl,info.digits),tp=round(tp,info.digits),type_time=0,type_filling=2))
        if result is None:
            finish('FAIL','Entrada rechazada; consultar registro del bróker')
        else:
            state['opening_ticket']=int(result.order)
            save()
        return
    elapsed=time.time()-state['started']
    if state['phase']=='CLEANUP':
        for order in orders: cancel_pending(worker,d,order)
        for p in positions: worker.close_position(d,p,reason=f'diag-clean-{state["index"]}')
        if not positions and not orders:
            finish(state['outcome'],state['detail'])
        return
    def cleanup(outcome,detail):
        state.update(phase='CLEANUP',outcome=outcome,detail=detail);save()
    if case['entry']!='MARKET':
        if positions:
            cleanup('INCONCLUSIVE','Pendiente ejecutada antes de completar modificación/cancelación');return
        if not orders:
            if getattr(worker.mt5,'platform','MT5')=='NT8' and worker.mt5.history_deals_get(position=state.get('opening_ticket')):
                cleanup('INCONCLUSIVE','Pendiente activada y cerrada antes de modificar; ejecución nativa confirmada');return
            cleanup('FAIL','Pendiente no encontrada tras aceptación');return
        if not state.get('modified'):
            o=orders[0];sign=1 if case['direction']=='BUY' else -1
            delta=sign*state['distance']*(-1 if case['entry']=='LIMIT' else 1)
            info,_=worker.tick(symbol,d)
            request=dict(action=7,order=int(o.ticket),symbol=symbol,price=round(o.price_open+delta,info.digits),
                sl=round(o.sl+delta,info.digits),tp=round(o.tp+delta,info.digits),type_time=0)
            result=worker.send(d,f'{d["id"]}:pending-modify:{o.ticket}',request)
            if not result:
                if any(p.magic==d['magic'] for p in worker.positions()):cleanup('INCONCLUSIVE','Pendiente activada antes del cambio; rechazo confirmado sin reenviar')
                else:cleanup('FAIL','Modificación pendiente rechazada')
                return
            state['modified']=True;state['pending_price']=request['price'];save();return
        info,_=worker.tick(symbol,d)
        if abs(orders[0].price_open-state['pending_price'])>=info.point:
            cleanup('FAIL','El precio pendiente no refleja la modificación');return
        cleanup('PASS','Pendiente colocada y modificada; cancelación se verifica en limpieza');return
    if not positions:
        if case['exit'] in ('BREAKEVEN','TRAILING','MODIFY') and state.get('target_sl') is not None and getattr(worker.mt5,'platform','MT5')=='NT8':
            deals=worker.mt5.history_deals_get(position=state.get('opening_ticket'))
            point=worker.mt5.symbol_info(symbol).point
            if any(deal.reason==4 and deal.stop_price is not None and abs(deal.stop_price-state['target_sl'])<=point/2 for deal in deals):
                cleanup('PASS','SL modificado y ejecutado antes de la siguiente consulta; precio del stop confirmado en NT8');return
        if case['exit'] in ('SL','TP') and state.get('opening_ticket'):
            deals=worker.mt5.history_deals_get(position=state['opening_ticket'])
            reason=4 if case['exit']=='SL' else 5
            if deals and any(deal.reason==reason for deal in deals):
                cleanup('PASS',f'Salida {case["exit"]} confirmada en historial del bróker');return
        cleanup('INCONCLUSIVE','Posición cerrada sin motivo esperado confirmado en historial MT5');return
    p=positions[0]
    if case['exit'] in ('CLOSE','TIME') and elapsed>= (8 if case['exit']=='TIME' else 2):
        cleanup('PASS','Cierre programado del diagnóstico; se verifica desaparición en limpieza');return
    if case['exit']=='PARTIAL':
        if not state.get('partial_volume'):
            before=p.volume
            result=worker.close_position(d,p,.5,reason='partial')
            if not result: cleanup('FAIL','Parcial rechazado');return
            state['partial_volume']=before;save();return
        if p.volume<state['partial_volume']:
            cleanup('PASS','Reducción de volumen confirmada en MT5');return
    if case['exit'] in ('MODIFY','BREAKEVEN','TRAILING'):
        info,tick=worker.tick(symbol,d)
        buy=p.type==0;current=tick.bid if buy else tick.ask
        distance=max(info.trade_stops_level,info.trade_freeze_level)*info.point+info.point*2
        target=p.price_open if case['exit']=='BREAKEVEN' else (current-state['distance'] if buy else current+state['distance'])
        improves=target>p.sl if buy else target<p.sl
        valid=target<current-distance if buy else target>current+distance
        if state.get('target_sl') is not None and abs(p.sl-state['target_sl'])<info.point:
            cleanup('PASS','Modificación de SL confirmada en MT5');return
        if improves and valid and state.get('target_sl') is None:
            target=round(target,info.digits)
            worker.modify(d,p,target,p.tp)
            state['target_sl']=target;save();return
    if elapsed>d['diagnostic_timeout']:
        cleanup('INCONCLUSIVE','Tiempo agotado sin condición de precio confirmada; se limpia el caso')

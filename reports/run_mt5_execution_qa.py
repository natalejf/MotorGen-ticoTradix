"""Single-account DEMO/HEDGING integration checks through the installed EA.

Run from the workspace: python -m reports.run_mt5_execution_qa --execute-demo
No broker password is read. Results are checkpointed after every case.
"""
import argparse
import json
import time
import uuid
from pathlib import Path

from backend import copy_trading as store
from backend.ea_bridge import EABroker, ensure_ea_worker
from backend.indicator_audit import audit_frame
from backend.mt5_worker import MT5Worker
from backend.mt5_diagnostic import cancel_pending
from backend.strategy import Strategy, Condition

OUT=Path(__file__).with_name('mt5_execution_qa.json')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute-demo',action='store_true')
    args=parser.parse_args()
    accounts=store.listing('account')
    if len(accounts)!=1:raise RuntimeError('Seleccione explícitamente una única cuenta de pruebas')
    account=accounts[0];broker=EABroker(account);worker=MT5Worker(broker,account)
    info,_=worker.verify()
    report=dict(started=time.time(),account=account['name'],login=info.login,server=info.server,
                equity_before=info.equity,cases=[],scope='Una demo; copy diferido por el usuario')
    def save():OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    report['indicators']=audit_frame(worker.bars('EURUSDm','30m'));save()
    print('INDICATORS',report['indicators']['passed'],report['indicators']['checks'],flush=True)
    if not args.execute_demo:return
    if any(d['state']!='STOPPED' for d in store.listing('deployment') if d['account_id']==account['id']):
        raise RuntimeError('Hay asignaciones ajenas en ejecución')
    if broker.positions_get() or broker.orders_get():raise RuntimeError('La cuenta debe estar vacía al comenzar')
    store.put('worker_control',account['id'],{'stop':True})
    deadline=time.time()+45
    while time.time()<deadline:
        with store.connect() as db:lease=db.execute('SELECT expires FROM leases WHERE account=?',(account['id'],)).fetchone()
        if not lease or lease['expires']<=time.time():break
        time.sleep(1)
    if not store.lease(account['id'],worker.owner):raise RuntimeError('Worker anterior aún activo')
    key='qa_'+uuid.uuid4().hex
    deployment=dict(id=key,name='QA · motor normal MT5',account_id=account['id'],source_type='strategy',
        source_id='qa_normal_engine',origin_type='strategy',state='ACTIVE',magic=850000000,
        strategies=[],symbol_map={'EURUSD':'EURUSDm'},risk_percent=.1,fixed_lot=0,max_lot=.04,
        max_daily_loss_pct=0,max_drawdown_pct=0,max_positions=1,max_spread_points=50.,
        deviation_points=20,uses_source_risk=True)
    store.put('deployment',key,deployment)
    report['deployment']=key;save()
    def owned_positions():return [p for p in broker.positions_get() if p.magic==deployment['magic']]
    def cleanup():
        for order in broker.orders_get():
            if order.magic==deployment['magic']:cancel_pending(worker,deployment,order)
        for position in owned_positions():worker.close_position(deployment,position,reason='qa-cleanup')
        if owned_positions() or any(o.magic==deployment['magic'] for o in broker.orders_get()):
            raise RuntimeError('No se confirmó limpieza de órdenes QA')
    def record(name,fn):
        started=time.time()
        try:
            detail=fn()
            report['cases'].append(dict(name=name,status='PASS',seconds=round(time.time()-started,2),detail=detail))
        except Exception as error:
            report['cases'].append(dict(name=name,status='FAIL',seconds=round(time.time()-started,2),error=str(error)))
            if store.get('deployment',key)['state']=='PAUSED':raise
        finally:save()
        cleanup()
        print(report['cases'][-1]['status'],name,flush=True)
    counter=0
    def run_normal(direction,mode='ATR_CLASSIC',entry='MARKET',**sizing):
        nonlocal counter
        counter+=1
        condition=Condition('PRICE',{},'GREATER_THAN',target_value=0)
        strategy=Strategy(strategy_id=f'qa-{counter}',symbol='EURUSD',timeframe='30m',
            direction='LONG_ONLY' if direction=='BUY' else 'SHORT_ONLY',
            buy_conditions=[condition] if direction=='BUY' else [],sell_conditions=[condition] if direction=='SELL' else [],
            close_before_weekend=False,entry_order_type=entry,exit_mode=mode,
            sizing_mode=sizing.pop('sizing_mode','FIXED_LOT'),fixed_lot=sizing.pop('fixed_lot',.02),
            risk_per_trade_pct=sizing.pop('risk_per_trade_pct',.1),sl_atr=3,tp_atr=6,
            sl_pips=10,tp_pips=20,sl_pct=.05,tp_pct=.1,sl_smooth_mult=3,tp_smooth_mult=6,
            trail_atr=.5,partial_tp1_atr=.1,max_daily_trades=1,**sizing)
        runtime=worker.local_state(deployment);runtime['bars']={}
        item={'strategy':strategy.to_dict(),'weight':1}
        # Unique persisted idempotency keys per case, through the ordinary algorithm path.
        case_deployment=dict(deployment,id=key+f'_{counter}')
        store.put('deployment',case_deployment['id'],case_deployment)
        try:
            worker.algorithm(case_deployment,runtime,item,0,True)
            positions=owned_positions();orders=[o for o in broker.orders_get() if o.magic==deployment['magic']]
            if len(positions)+len(orders)!=1:raise AssertionError('No hay exactamente una entrada atribuida al caso')
            trade=(positions+orders)[0]
            if trade.sl<=0 or trade.tp<=0 or trade.volume>.04000001:raise AssertionError('Protecciones/volumen inválidos')
            evidence=dict(ticket=trade.ticket,volume=trade.volume,sl=trade.sl,tp=trade.tp,
                kind='position' if positions else 'pending',entry=entry,exit=mode,direction=direction,
                meaning='Entrada/protecciones y cierre de limpieza reales; no certifica disparo natural de esta salida')
            # Observe the management path and ensure repeated evaluation cannot duplicate entry.
            worker.algorithm(case_deployment,runtime,item,0,False)
            evidence['after_management']=[dict(ticket=p.ticket,volume=p.volume,sl=p.sl,tp=p.tp) for p in owned_positions()]
            return evidence
        finally:
            current=store.get('deployment',case_deployment['id'])
            if current['state']=='PAUSED':
                deployment['state']='PAUSED';store.put('deployment',key,deployment)
            else:
                current['state']='STOPPED';store.put('deployment',current['id'],current)
    try:
        for direction in ('BUY','SELL'):
            for mode in ('ATR_CLASSIC','PIPS_FIXED','PCT_EXIT','TRAILING_ATR','BREAKEVEN',
                         'STRUCTURE_SWING','TIME_EXIT','PARTIAL_TP','ATR_SMOOTHED'):
                record(f'{direction} MARKET {mode}',lambda d=direction,m=mode:run_normal(d,m))
        for entry in ('LIMIT','STOP'):
            for direction in ('BUY','SELL'):
                record(f'{direction} {entry}',lambda d=direction,e=entry:run_normal(d,entry=e))
        for mode in ('FIXED_RISK','FIXED_CASH'):
            for multiplier in (1,2):
                record(f'{mode} multiplier={multiplier}',lambda m=mode,k=multiplier:
                    run_normal('BUY','PIPS_FIXED',sizing_mode=m,risk_multiplier=k,
                        risk_per_trade_pct=.03,fixed_cash_risk=1.5))
        record('FIXED_LOT .01',lambda:run_normal('SELL','PIPS_FIXED',fixed_lot=.01))
    finally:
        try:cleanup();report['cleanup']='CONFIRMED_EMPTY'
        except Exception as error:report['cleanup']=str(error)
        deployment['state']='STOPPED' if report.get('cleanup')=='CONFIRMED_EMPTY' else 'CLOSING'
        store.put('deployment',key,deployment)
        report.update(finished=time.time(),equity_after=broker.account_info().equity);save()
        with store.connect() as db:db.execute('DELETE FROM leases WHERE account=? AND owner=?',(account['id'],worker.owner))
        store.put('worker_control',account['id'],{'stop':False});ensure_ea_worker(account['id'])


if __name__=='__main__':main()

"""Assign a genuine generated strategy, then replace it with the saved portfolio."""
import json
import time

from reports.create_demo_genetic_portfolio import api,OUT
from backend import copy_trading as store
from backend.ea_bridge import EABroker
from backend.mt5_worker import MT5Worker
from backend.strategy import Strategy
from backend.portfolio import StrategyRecord,Portfolio


def main():
    report=json.loads(OUT.read_text(encoding='utf-8'))
    account=store.get('account',report['account_id']);broker=EABroker(account)
    worker=MT5Worker(broker,account);worker.verify()
    if broker.positions_get() or broker.orders_get():raise RuntimeError('La cuenta debe comenzar sin operaciones')
    def save():OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    structure=[c for c in api('/api/candidates') if not store.compatibility(Strategy.from_dict(c['strategy']))
               and c['metrics'].get('holdout',{}).get('net_profit',0)>0
               and c['metrics'].get('holdout',{}).get('trades',0)>=5]
    structure.sort(key=lambda c:c['metrics']['tn_score'],reverse=True)
    if not structure:raise RuntimeError('No hay candidato estructural con tramo reservado positivo')
    candidate=structure[0]
    candidate['strategy']['name']='STX Demo L3.3 Estructura · selección MT5'
    candidate['demo_search_config']=report['batches'][2]['config']
    api('/api/strategy/save',dict(candidate_data=candidate,folder=report['batches'][2]['folder']))
    report['batches'][2]['saved'].append(dict(id=candidate['strategy']['id'],name=candidate['strategy']['name'],
        metrics=candidate['metrics'],strategy=candidate['strategy']))
    selected=[]
    for batch in report['batches']:
        eligible=[c for c in batch['saved'] if c['metrics'].get('holdout',{}).get('net_profit',0)>0
                  and c['metrics'].get('holdout',{}).get('trades',0)>=5]
        if not eligible:raise RuntimeError('Un lote no tiene candidato con revisión positiva')
        selected.append(max(eligible,key=lambda c:c['metrics']['tn_score']))
    records=[StrategyRecord.load(c['id']).data for c in selected]
    old=Portfolio.load(report['portfolio']['id'])
    portfolio=Portfolio(name=old.name,strategies=records,weights=[1/3]*3,risk_budget=.3,
        portfolio_id=old.id,created_at=old.created_at,folder=old.folder)
    portfolio.save()
    report['portfolio']=portfolio.to_dict()
    report['selected']=[dict(id=c['id'],name=c['name'],score=c['metrics']['tn_score'],
        holdout=c['metrics']['holdout']) for c in selected]
    frame=worker.bars('EURUSDm','30m')
    signals=[]
    for candidate in selected:
        strategy=Strategy.from_dict(candidate['strategy'])
        buy,sell=worker.signals.generate_signal_arrays(frame,strategy)
        signals.append(dict(id=strategy.id,buy=bool(buy[-1]),sell=bool(sell[-1])))
    live_ids={r['id'] for r in signals if r['buy'] or r['sell']}
    single=next((c for c in sorted(selected,key=lambda c:c['metrics']['tn_score'],reverse=True) if c['id'] in live_ids),None)
    if not single:raise RuntimeError('No hay señal actual: esperar mercado, no forzar reglas')
    report['native_signals']=signals;save()
    def wait_open(deployment,seconds=100):
        deadline=time.time()+seconds
        while time.time()<deadline:
            current=store.get('deployment',deployment['id'])
            with store.connect() as db:
                rows=db.execute("SELECT id,state,body FROM actions WHERE id LIKE ?",(deployment['id']+':algo:%',)).fetchall()
            successful=[dict(id=row['id'],result=json.loads(row['body'])) for row in rows if row['state']=='EXECUTED']
            if successful:
                snapshot=store.get('snapshot',account['id'])
                return dict(actions=successful,snapshot=snapshot,at=time.time())
            if current['state']!='ACTIVE':raise RuntimeError('La asignación dejó de estar activa: '+current['state'])
            time.sleep(2)
        with store.connect() as db:
            events=[dict(r) for r in db.execute('SELECT message FROM events WHERE deployment=? ORDER BY seq DESC LIMIT 8',(deployment['id'],))]
        raise RuntimeError('No se confirmó entrada: '+str(events))
    deployment=api('/api/execution/start',dict(source_id=single['id'],account_id=account['id']))
    report['single_session']=deployment;save();print('SINGLE ASSIGNED',single['id'],flush=True)
    report['single_execution']=wait_open(deployment);save()
    print('SINGLE EXECUTED',json.dumps(report['single_execution']['actions']),flush=True)
    api(f'/api/execution/sessions/{deployment["id"]}/close-stop',{})
    deadline=time.time()+100
    while store.get('deployment',deployment['id'])['state']!='STOPPED':
        if time.time()>deadline:raise RuntimeError('No se confirmó cierre de la sesión individual')
        time.sleep(2)
    report['single_stopped']=time.time();save()
    if broker.positions_get() or broker.orders_get():raise RuntimeError('No se inicia portafolio encima de operaciones anteriores')
    deployment=api('/api/execution/start',dict(source_type='portfolio',source_id=portfolio.id,account_id=account['id']))
    report['portfolio_session']=deployment;save();print('PORTFOLIO ASSIGNED',deployment['id'],flush=True)
    report['portfolio_execution']=wait_open(deployment);save()
    # Let the worker finish the remaining strategy evaluations before capturing broker state.
    time.sleep(12)
    report['positions']=[vars(p) for p in broker.positions_get()]
    report['orders']=[vars(o) for o in broker.orders_get()]
    report['account_after']=vars(broker.account_info());report['finished']=time.time()
    save();print('PORTFOLIO EXECUTED',json.dumps(report['positions']),flush=True)


if __name__=='__main__':main()

"""Explicit demo-only group setup and bounded trials using normal native signals."""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reports.cross_terminal_qa import api,wait

OUT=Path(__file__).resolve().parents[1]/'data/copy_logs/pass_groups_qa_context.json'


def state(ns,key=None):
    c=next(c for c in api('/api/'+ns+'/status')['connections'] if c['id']==key) if key else next(c for c in api('/api/'+ns+'/status')['connections'] if c['connected'])
    if not c['connected']:raise RuntimeError(ns+': native telemetry is stale')
    return c


def guard(c,names,flat=False):
    rows={a['name']:a for a in c['snapshot']['accounts']}
    assert all(rows[n]['provider']=='Simulator' and rows[n]['execution_allowed'] for n in names)
    if flat:assert all(not rows[n]['position_quantity'] and not rows[n]['working_orders'] for n in names)
    return [rows[n] for n in names]


def command(ns,key,path):
    sent=api('/api/'+ns+'/connections/'+key+'/'+path,{})
    def ack():
        c=state(ns,key);r=next((r for r in c['commands'] if r['id']==sent['id']),{})
        if r.get('state') in ('REJECTED','EXPIRED'):raise RuntimeError(str(r))
        return c if r.get('state')=='APPLIED' else None
    return wait(ack,'Native '+path+' confirmation',seconds=40)


def prepare():
    context={}
    prop=state('ninja');names=[a['name'] for a in prop['snapshot']['accounts'] if a['provider']=='Simulator']
    guard(prop,names,True);assert not prop['snapshot']['master_enabled']
    command('ninja',prop['id'],'release')
    for ns,names,symbol,label in [('rocket',['Sim101']+['SimAccount'+str(i) for i in range(2,6)],'MNQ DEC26','RocketPass · Demo 1–5 · MNQ 4'),('ninja',['SimAccount'+str(i) for i in range(6,11)],'NQ DEC26','PropPass · Demo 6–10 · NQ 4')]:
        c=state(ns);guard(c,names,True)
        settings=dict(accounts=names,symbol=symbol,lots=4,tp_usd=1500,sl_usd=2000,target=1500,max_loss=2000,start_balance=50000,daily_profit_limit=0,daily_loss_limit=0,time_filter=False)
        if ns=='rocket':settings.update(trend_period=40,limit_count=3,stop_count=3,limit_contracts=4,stop_contracts=4,max_contracts=40,grid_same_as_initial=True)
        existing=next((g for g in api('/api/'+ns+'/status')['groups'] if g['settings']['accounts']==names),None)
        if existing:
            req=urllib.request.Request('http://127.0.0.1:8000/api/'+ns+'/groups/'+existing['id'],data=json.dumps(dict(name=label,settings=settings)).encode(),headers={'Content-Type':'application/json'},method='PUT')
            with urllib.request.urlopen(req,timeout=15) as response:g=json.load(response)
        else:g=api('/api/'+ns+'/groups',dict(name=label,settings=settings))
        c=command(ns,c['id'],'groups/'+g['id']+'/reset')
        context[ns]=dict(connection=c['id'],group=g['id'],accounts=names,settings=g['settings'])
        OUT.write_text(json.dumps(context,indent=2),encoding='utf-8')
        print(ns,json.dumps({'applied':True,'data_ready':c['snapshot'].get('data_ready'),'closed_bars':c['snapshot'].get('closed_bars'),'version':c['snapshot'].get('version')}),flush=True)


def trial(ns,seconds):
    context=json.loads(OUT.read_text());config=context[ns];key=config['connection'];gid=config['group'];names=config['accounts']
    c=state(ns,key);guard(c,names,True)
    if ns=='rocket':wait(lambda:state(ns,key)['snapshot'].get('closed_bars',0)>=40,'40 historical M5 candles',seconds=90)
    wait(lambda:state(ns,key)['snapshot'].get('data_ready'),'Recent instrument ticks',seconds=90)
    result={'started':time.time(),'events':[]};context[ns]['trial']=result
    # Independent services may be tested concurrently; never overwrite the other result.
    result_path=OUT.with_name('pass_groups_qa_'+ns+'_results.json')
    def save():result_path.write_text(json.dumps(context[ns],indent=2),encoding='utf-8')
    save()
    try:
        command(ns,key,'groups/'+gid+'/start')
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            c=state(ns,key);rows=guard(c,names)
            active=[r for r in rows if r['position_quantity']]
            assert len(active)<=1,'Sequential group opened simultaneous accounts'
            if active:
                row=active[0];orders=row['working_orders'];qty=row['position_quantity']
                result['entry']=dict(account=row['name'],quantity=qty,orders=orders,at=time.time(),snapshot=c['snapshot'])
                if ns=='rocket':
                    grid=[o for o in orders if o['name'].startswith(('ROCKET_LIMIT_','ROCKET_STOP_'))]
                    assert all(o['quantity']==4 for o in grid)
                    assert len({o['name'] for o in grid})==len(grid)
                    assert qty+sum(o['quantity'] for o in grid)<=40
                    if len(grid)==6 and qty==4:
                        assert sum(o['type']=='Limit' for o in grid)==3
                        assert sum(o['type']=='StopMarket' for o in grid)==3
                        result['grid_verified']=True
                prefix='ROCKET_' if ns=='rocket' else ''
                protected=all(any(o['name'].startswith(prefix+name+'_') for o in orders) for name in ('TP','SL'))
                if protected and (ns!='rocket' or result.get('grid_verified')):
                    result['result']='ENTRY_AND_PROTECTION_CONFIRMED';save();print(ns,result['result'],row['name'],qty,flush=True);break
            if not c['snapshot']['master_enabled']:raise RuntimeError('Native entries paused: '+str(c['snapshot'].get('pause_reason')))
            save();time.sleep(2)
        else:result['result']='NO_COMPLETE_ENTRY_WITHIN_WINDOW';save();print(ns,result['result'],flush=True)
    except Exception as error:
        result['error']=str(error);save();raise
    finally:
        command(ns,key,'groups/'+gid+'/close-stop')
        wait(lambda:all(not a['position_quantity'] and not a['working_orders'] for a in guard(state(ns,key),names)),'Flat and no orders after trial',seconds=60)
        result['flat_verified']=True;result['ended']=time.time();save();print(ns,'FLAT_VERIFIED',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--phase',choices=['prepare','rocket','ninja'],required=True);parser.add_argument('--seconds',type=int,default=660)
    args=parser.parse_args()
    if not args.run:raise SystemExit('Explicit authorization for demo tests and --run required')
    prepare() if args.phase=='prepare' else trial(args.phase,args.seconds)

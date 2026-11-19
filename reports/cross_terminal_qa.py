"""Explicitly armed cross-terminal demo QA. Never targets a live or evaluation account."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request
import uuid
from types import SimpleNamespace as NS

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import copy_trading as store
from backend.ninja_rpc import NinjaBroker
import MetaTrader5 as mt

LOG=ROOT/'data'/'copy_logs'/'cross_terminal_qa_results.json'
MAGIC=190900001


def api(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:8000'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=15) as response:return json.load(response)


def wait(check,label,seconds=70):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:value=check()
        except KeyError:value=None
        if value:return value
        time.sleep(1)
    raise TimeoutError(label)


class MT5Source:
    def __init__(self,account):self.account=account;self.symbol='USTECm';self.volume=.1
    def guard(self):
        a=mt.account_info()
        assert a and a.login==self.account['login'] and a.server==self.account['server']
        assert a.trade_mode==mt.ACCOUNT_TRADE_MODE_DEMO and a.margin_mode==mt.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING
    def tick(self):
        self.guard();t=mt.symbol_info_tick(self.symbol);assert t and t.bid>0 and time.time()-t.time<30;return t
    def state(self):return dict(positions=[p._asdict() for p in mt.positions_get() if p.magic==MAGIC],orders=[o._asdict() for o in mt.orders_get() if o.magic==MAGIC])
    def send(self,request):
        self.guard();request.update(symbol=self.symbol,magic=MAGIC,comment='STXQA-CROSS')
        r=mt.order_send(request)
        if not r or r.retcode not in (10008,10009,10010):raise RuntimeError('MT5 source rejected '+str(r))
        return r
    def open(self,kind,distance=80):
        t=self.tick();sign=1 if kind in (0,2,4) else -1;price=t.ask if sign==1 else t.bid
        if kind>=2:price+=sign*distance*(-1 if kind in (2,3) else 1)
        i=mt.symbol_info(self.symbol);fill=1 if i.filling_mode&2 else 0
        return self.send(dict(action=5 if kind>=2 else 1,type=kind,volume=self.volume,price=round(price,2),sl=round(price-sign*100,2),tp=round(price+sign*150,2),deviation=200,type_time=0,type_filling=2 if kind>=2 else fill))
    def modify(self,obj,pending=False,shift=0):
        sign=1 if obj['type'] in (0,2,4) else -1
        r=dict(action=7 if pending else 6,sl=round(obj['sl']+shift+sign*10,2),tp=round(obj['tp']+shift+sign*10,2))
        if pending:r.update(order=obj['ticket'],price=round(obj['price_open']+shift,2),type_time=0)
        else:r['position']=obj['ticket']
        self.send(r);return r
    def cancel(self,obj):return self.send(dict(action=8,order=obj['ticket']))
    def close(self,obj,fraction=1):
        t=self.tick();i=mt.symbol_info(self.symbol)
        return self.send(dict(action=1,position=obj['ticket'],type=1 if obj['type']==0 else 0,volume=round(obj['volume']*fraction,2),price=t.bid if obj['type']==0 else t.ask,deviation=200,type_filling=1 if i.filling_mode&2 else 0))


class NativeSource:
    def __init__(self,connection):
        self.connection=connection;self.symbol='MNQ DEC26';self.volume=2
        self.broker=NinjaBroker(connection,'Sim101',uuid.uuid4().hex,self.symbol,MAGIC+1)
        self.guard();self.broker.rpc('claim',copy_mode=1)
    def guard(self):
        snapshot=store.get('ninja_snapshot',self.connection)
        row=next(a for a in snapshot['accounts'] if a['name']=='Sim101')
        assert time.time()-snapshot['at']<10 and row['provider']=='Simulator' and row['execution_allowed']
    def state(self):self.broker.invalidate();return self.broker.state()
    def tick(self):
        self.guard();s=self.state();assert s['bid']>0 and time.time()-s['tick_time']<30;return NS(**s)
    def send(self,request):
        self.guard();request.update(comment='STXQA-NATIVE',magic=MAGIC+1)
        r=self.broker.order_send(request)
        if r.retcode not in (10008,10009,10010):raise RuntimeError('Native source rejected '+str(r))
        return r
    def open(self,kind,distance=80):
        t=self.tick();sign=1 if kind in (0,2,4) else -1;price=t.ask if sign==1 else t.bid
        if kind>=2:price+=sign*distance*(-1 if kind in (2,3) else 1)
        return self.send(dict(action=5 if kind>=2 else 1,type=kind,volume=2,price=price,sl=price-sign*100,tp=price+sign*150,type_time=0,type_filling=2))
    def modify(self,obj,pending=False,shift=0):
        sign=1 if obj['type'] in (0,2,4) else -1
        request=dict(action=7 if pending else 6,sl=obj['sl']+shift+sign*5,tp=obj['tp']+shift+sign*15)
        if pending:request.update(order=obj['ticket'],price=obj['price_open']+shift,type_time=0)
        else:request['position']=obj['ticket']
        self.send(request);return request
    def cancel(self,obj):return self.send(dict(action=8,order=obj['ticket']))
    def close(self,obj,fraction=1):
        t=self.tick()
        return self.send(dict(action=1,position=obj['ticket'],type=1 if obj['type']==0 else 0,volume=int(obj['volume']*fraction),price=t.bid if obj['type']==0 else t.ask,type_time=0,type_filling=2))
    def release(self):self.broker.rpc('release')


def snapshot_positions(account,magic):
    try:s=store.get('snapshot',account)
    except KeyError:return []
    if time.time()-s.get('at',0)>20:raise RuntimeError('Destination snapshot is stale; flat state cannot be inferred')
    return [p for p in s.get('positions',[]) if p['magic']==magic]


def pending_ref(deployment):
    try:r=store.get('runtime',deployment)
    except KeyError:return None
    legs=list(r.get('copy_legs',{}).values()) or [r]
    return next((ref for leg in legs for ref in leg.get('pending_copies',{}).values() if not ref.get('terminal')),None)


def native_orders(deployment,connection):
    orders=[]
    for r in store.listing('ninja_copy_leg'):
        if r['parent']!=deployment or r.get('state')=='RELEASED':continue
        d=store.get('deployment',deployment)
        b=NinjaBroker(connection,'Sim101',r['id'],r['symbol'],d['magic'],parent=deployment)
        try:orders.extend(b.state()['orders'])
        except RuntimeError:
            if store.get('ninja_copy_leg',r['id']).get('state')!='RELEASED':raise
    return orders


def forward_pending(args):
    account=store.get('account',args.mt5_account);assert mt.initialize(path=r'C:\Program Files\MetaTrader 5\terminal64.exe')
    source=MT5Source(account);source.guard();assert not mt.positions_get() and not mt.orders_get()
    target=api('/api/copy/native-accounts',dict(connection=args.connection,account='Sim101'))
    d=api('/api/copy/deployments',dict(name='QA · MT5 pendientes → NinjaTrader',account_id=target['id'],source_type='account',source_id=args.mt5_account,
        symbol_map={'USTECm':'MNQ DEC26'},risk_mode='FIXED_LOT',fixed_lot=2,max_lot=2,risk_percent=1,max_order_age_seconds=90,max_positions=5))
    results=json.loads(LOG.read_text()) if LOG.exists() else []
    (LOG.parent/'cross_qa_forward_pending_context.json').write_text(json.dumps(dict(deployment=d['id'],target=target['id'],source=args.mt5_account,connection=args.connection)),encoding='utf-8')
    try:
        wait(lambda:store.get('runtime',d['id']).get('copy_legs',{}).get('0',{}).get('baseline_master')==[], 'Native baseline ready')
        api('/api/copy/deployments/'+d['id']+'/resume',{})
        for kind in (2,3,4,5):
            opened=source.open(kind);record(results,'forward_pending_source',type=kind,source_ticket=opened.order)
            dest=wait(lambda:native_orders(d['id'],args.connection),'Forward pending placement')
            assert len(dest)==1 and dest[0]['type']==kind and dest[0]['volume']==2
            original=source.state()['orders'][0];before=dest[0]
            record(results,'forward_pending_place_'+str(kind),status='PASS',target_ticket=dest[0]['ticket'])
            shift=-10 if kind in (2,5) else 10;change=source.modify(original,True,shift)
            def updated():
                o=native_orders(d['id'],args.connection)
                return o and all(abs((o[0][k]-before[k])-(change[key]-original[k]))<=.5 for k,key in [('price_open','price'),('sl','sl'),('tp','tp')])
            wait(updated,'Forward pending price/SL/TP changes')
            record(results,'forward_pending_modify_'+str(kind),status='PASS')
            source.cancel(source.state()['orders'][0]);wait(lambda:not native_orders(d['id'],args.connection),'Forward pending cancellation')
            record(results,'forward_pending_cancel_'+str(kind),status='PASS')
    except Exception as error:record(results,'failure',status='FAIL',error=str(error));raise
    finally:
        for o in source.state()['orders']:source.cancel(o)
        for p in source.state()['positions']:source.close(p)
        api('/api/copy/deployments/'+d['id']+'/close-stop',{});mt.shutdown()


def forward_activation(args):
    account=store.get('account',args.mt5_account);assert mt.initialize(path=r'C:\Program Files\MetaTrader 5\terminal64.exe')
    source=MT5Source(account);source.guard();assert not mt.positions_get() and not mt.orders_get()
    target=api('/api/copy/native-accounts',dict(connection=args.connection,account='Sim101'))
    d=api('/api/copy/deployments',dict(name='QA · Activación pendiente MT5 → Ninja',account_id=target['id'],source_type='account',source_id=args.mt5_account,
        symbol_map={'USTECm':'MNQ DEC26'},risk_mode='FIXED_LOT',fixed_lot=2,max_lot=2,risk_percent=1,max_order_age_seconds=90,max_positions=5))
    results=json.loads(LOG.read_text())
    (LOG.parent/'cross_qa_activation_context.json').write_text(json.dumps(dict(deployment=d['id'],target=target['id'],source=args.mt5_account,connection=args.connection)),encoding='utf-8')
    try:
        wait(lambda:store.get('runtime',d['id']).get('copy_legs',{}).get('0',{}).get('baseline_master')==[], 'Native baseline ready')
        api('/api/copy/deployments/'+d['id']+'/resume',{})
        opened=source.open(4);wait(lambda:native_orders(d['id'],args.connection),'Activation: destination pending accepted')
        record(results,'forward_activation_pending',source_ticket=opened.order)
        t=source.tick();price=round(t.ask+.25,2)
        source.send(dict(action=7,order=opened.order,price=price,sl=round(price-100,2),tp=round(price+150,2),type_time=0))
        origin=wait(lambda:source.state()['positions'],'Source stop execution',seconds=45)
        record(results,'forward_activation_source_filled',source_ticket=origin[0]['ticket'])
        dest=wait(lambda:snapshot_positions(target['id'],d['magic']),'Destination pending execution/catch-up',seconds=75)
        assert len(dest)==1 and dest[0]['volume']==2
        record(results,'forward_activation_no_duplicate',status='PASS',contracts=dest[0]['volume'],target_ticket=dest[0]['ticket'])
        source.close(source.state()['positions'][0]);wait(lambda:not snapshot_positions(target['id'],d['magic']),'Activated position close')
        record(results,'forward_activation_close',status='PASS')
    except Exception as error:record(results,'failure',status='FAIL',error=str(error));raise
    finally:
        for o in source.state()['orders']:source.cancel(o)
        for p in source.state()['positions']:source.close(p)
        api('/api/copy/deployments/'+d['id']+'/close-stop',{});mt.shutdown()


def reverse(args):
    account=store.get('account',args.mt5_account);assert mt.initialize(path=r'C:\Program Files\MetaTrader 5\terminal64.exe')
    MT5Source(account).guard();assert not mt.positions_get() and not mt.orders_get()
    previous=json.loads((LOG.parent/'cross_qa_previous_states.json').read_text())
    for item in previous:
        d=store.get('deployment',item['id']);assert d['state'] in ('PAUSED','STOPPED');d['state']='STOPPED';store.put('deployment',d['id'],d)
    master=api('/api/copy/native-accounts',dict(connection=args.connection,account='Sim101'))
    if not any(m['account_id']==master['id'] for m in store.listing('master')):api('/api/copy/masters',dict(name='QA · Ninja demo',account_id=master['id']))
    source=NativeSource(args.connection)
    d=api('/api/copy/deployments',dict(name='QA · NinjaTrader → MT5 '+args.phase,account_id=args.mt5_account,source_type='account',source_id=master['id'],
        symbol_map={'MNQ DEC26':'USTECm'},risk_mode='FIXED_LOT',fixed_lot=.1,max_lot=.1,risk_percent=1,max_order_age_seconds=90,max_positions=5,max_spread_points=1000,deviation_points=200))
    results=json.loads(LOG.read_text());(LOG.parent/('cross_qa_'+args.phase+'_context.json')).write_text(json.dumps(dict(deployment=d['id'],target=args.mt5_account,source=master['id'],connection=args.connection,native_session=source.broker.session)),encoding='utf-8')
    def positions():return [p._asdict() for p in mt.positions_get() if p.magic==d['magic']]
    def orders():return [o._asdict() for o in mt.orders_get() if o.magic==d['magic']]
    try:
        wait(lambda:store.get('runtime',d['id']).get('baseline_master')==[],'Reverse baseline ready')
        api('/api/copy/deployments/'+d['id']+'/resume',{})
        if args.phase=='reverse-market':
            opened=source.open(0);record(results,'reverse_source_market',ticket=opened.order)
            dest=wait(positions,'Reverse market copy');assert len(dest)==1 and dest[0]['volume']==.1
            record(results,'reverse_market_copy',status='PASS',target_ticket=dest[0]['ticket'],lots=dest[0]['volume'])
            origin=source.state()['positions'][0];change=source.modify(origin)
            def changed():
                p=positions();return p and abs((p[0]['sl']-p[0]['price_open'])-(change['sl']-origin['price_open']))<.1 and abs((p[0]['tp']-p[0]['price_open'])-(change['tp']-origin['price_open']))<.1
            wait(changed,'Reverse SL/TP modification');record(results,'reverse_market_protections',status='PASS')
            source.close(source.state()['positions'][0],.5);wait(lambda:(p:=positions()) and abs(p[0]['volume']-.05)<1e-6,'Reverse partial close');record(results,'reverse_partial_close',status='PASS',remaining_position=positions()[0])
            source.close(source.state()['positions'][0]);wait(lambda:not positions(),'Reverse full close');record(results,'reverse_full_close',status='PASS')
        elif args.phase=='reverse-activation':
            opened=source.open(4)
            dest=wait(orders,'Reverse activation pending placement')
            record(results,'reverse_activation_pending',status='PASS',source_ticket=opened.order,target_ticket=dest[0]['ticket'])
            t=source.tick();price=t.ask+.25
            source.send(dict(action=7,order=opened.order,price=price,sl=price-100,tp=price+150,type_time=0))
            wait(lambda:source.state()['positions'],'Reverse source stop execution',seconds=90)
            dest=wait(positions,'Reverse destination stop execution',seconds=90)
            assert len(dest)==1 and abs(dest[0]['volume']-.1)<1e-6
            record(results,'reverse_activation_no_duplicate',status='PASS',target_ticket=dest[0]['ticket'])
            source.close(source.state()['positions'][0]);wait(lambda:not positions(),'Reverse activated full close')
            record(results,'reverse_activation_close',status='PASS')
        else:
            for kind in (2,3,4,5):
                opened=source.open(kind);record(results,'reverse_pending_source',type=kind,source_ticket=opened.order)
                dest=wait(orders,'Reverse pending placement');assert len(dest)==1 and dest[0]['type']==kind and abs(dest[0]['volume_current']-.1)<1e-6
                original=source.state()['orders'][0];before=dest[0];record(results,'reverse_pending_place_'+str(kind),status='PASS',target_ticket=dest[0]['ticket'])
                shift=-10 if kind in (2,5) else 10;change=source.modify(original,True,shift)
                def changed():
                    o=orders();return o and all(abs((o[0][k]-before[k])-(change[key]-original[k]))<=.05 for k,key in [('price_open','price'),('sl','sl'),('tp','tp')])
                wait(changed,'Reverse pending price/SL/TP changes');record(results,'reverse_pending_modify_'+str(kind),status='PASS')
                source.cancel(source.state()['orders'][0]);wait(lambda:not orders(),'Reverse pending cancellation');record(results,'reverse_pending_cancel_'+str(kind),status='PASS')
    except Exception as error:record(results,'failure',status='FAIL',error=str(error));raise
    finally:
        for o in source.state()['orders']:source.cancel(o)
        for p in source.state()['positions']:source.close(p)
        wait(lambda:not source.state()['orders'] and not source.state()['positions'],'Source flat before release')
        source.release();api('/api/copy/deployments/'+d['id']+'/close-stop',{});mt.shutdown()


def record(results,name,**detail):
    results.append(dict(case=name,at=time.time(),**detail));LOG.parent.mkdir(exist_ok=True);LOG.write_text(json.dumps(results,indent=2),encoding='utf-8');print(name,json.dumps(detail),flush=True)


def forward_market(args):
    account=store.get('account',args.mt5_account)
    assert mt.initialize(path=r'C:\Program Files\MetaTrader 5\terminal64.exe')
    source=MT5Source(account);source.guard();assert not mt.positions_get() and not mt.orders_get()
    native=api('/api/ninja/status');connection=next(c for c in native['connections'] if c['id']==args.connection)
    row=next(a for a in connection['snapshot']['accounts'] if a['name']=='Sim101')
    assert connection['connected'] and row['provider']=='Simulator' and row.get('position_quantity',0)==0 and not row.get('working_orders')
    target=api('/api/copy/native-accounts',dict(connection=args.connection,account='Sim101'))
    if not any(m['account_id']==args.mt5_account for m in store.listing('master')):api('/api/copy/masters',dict(name='QA · MT5 demo',account_id=args.mt5_account))
    d=api('/api/copy/deployments',dict(name='QA · MT5 → NinjaTrader',account_id=target['id'],source_type='account',source_id=args.mt5_account,
        symbol_map={'USTECm':'MNQ DEC26'},risk_mode='FIXED_LOT',fixed_lot=2,max_lot=2,risk_percent=1,max_order_age_seconds=90,max_positions=5))
    results=[];LOG.write_text('[]',encoding='utf-8')
    (LOG.parent/'cross_qa_forward_context.json').write_text(json.dumps(dict(deployment=d['id'],target=target['id'],source=args.mt5_account,connection=args.connection)),encoding='utf-8')
    try:
        wait(lambda:pending_ref(d['id']) or store.get('runtime',d['id']).get('copy_legs',{}).get('0',{}).get('baseline_master')==[], 'Native baseline ready')
        api('/api/copy/deployments/'+d['id']+'/resume',{})
        opened=source.open(0);record(results,'source_market_open',ticket=opened.order)
        dest=wait(lambda:snapshot_positions(target['id'],d['magic']),'Forward market copy')
        assert len(dest)==1 and dest[0]['volume']==2
        record(results,'forward_market_copy',status='PASS',source_ticket=opened.order,target_ticket=dest[0]['ticket'],contracts=dest[0]['volume'])
        origin=source.state()['positions'][0];change=source.modify(origin)
        def protections():
            p=snapshot_positions(target['id'],d['magic'])
            return p and abs((p[0]['sl']-p[0]['price_open'])-(change['sl']-origin['price_open']))<=.5 and abs((p[0]['tp']-p[0]['price_open'])-(change['tp']-origin['price_open']))<=.5
        wait(protections,'Forward SL/TP changes');record(results,'forward_market_protections',status='PASS')
        source.close(source.state()['positions'][0],.5)
        wait(lambda:(p:=snapshot_positions(target['id'],d['magic'])) and p[0]['volume']==1,'Forward partial close');record(results,'forward_partial_close',status='PASS')
        source.close(source.state()['positions'][0]);wait(lambda:not snapshot_positions(target['id'],d['magic']),'Forward full close');record(results,'forward_full_close',status='PASS')
    except Exception as error:
        record(results,'failure',status='FAIL',error=str(error));raise
    finally:
        for o in source.state()['orders']:source.cancel(o)
        for p in source.state()['positions']:source.close(p)
        api('/api/copy/deployments/'+d['id']+'/close-stop',{})
        mt.shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--mt5-account',required=True);parser.add_argument('--connection',required=True);parser.add_argument('--phase',choices=['forward-market','forward-pending','forward-activation','reverse-market','reverse-pending','reverse-activation'],default='forward-market')
    args=parser.parse_args()
    if not args.run:raise SystemExit('Pass --run only with explicit authorization for demo terminal tests')
    {'forward-market':forward_market,'forward-pending':forward_pending,'forward-activation':forward_activation,'reverse-market':reverse,'reverse-pending':reverse,'reverse-activation':reverse}[args.phase](args)

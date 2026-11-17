"""Tests only a fake broker. Never initializes or sends to an installed terminal."""
from collections import namedtuple
from types import SimpleNamespace as NS
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend import copy_trading as store
from backend.api import app
from backend.mt5_worker import MT5Worker, floor_volume
from backend.strategy import Strategy, Condition


@pytest.fixture(autouse=True)
def isolated_store(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'copy.sqlite3')


def account():
    return dict(id='account1',login=123,server='Broker-Demo',name='Demo',terminal_path='terminal64.exe')


def deployment():
    value=dict(id='deploy1',account_id='account1',source_type='strategy',source_id='strategy1',
               state='ACTIVE',magic=100000001,strategies=[],symbol_map={},risk_percent=.25,
               fixed_lot=0,max_lot=1.,max_daily_loss_pct=2.,max_drawdown_pct=5.,
               max_positions=5,max_spread_points=50.,deviation_points=10)
    store.put('deployment',value['id'],value)
    return value


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO=0
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING=2
    ORDER_TYPE_BUY=POSITION_TYPE_BUY=0
    ORDER_TYPE_SELL=1
    TRADE_ACTION_DEAL=1
    TRADE_ACTION_SLTP=6
    ORDER_FILLING_FOK=0
    ORDER_FILLING_IOC=1
    ORDER_FILLING_RETURN=2
    ORDER_TIME_GTC=0
    TRADE_RETCODE_DONE=10009
    TRADE_RETCODE_DONE_PARTIAL=10010
    TIMEFRAME_M30=30
    TIMEFRAME_H1=60
    TIMEFRAME_H4=240
    TIMEFRAME_D1=1440

    def __init__(self):
        self.sent=[]
        self.opened=[]
        self.mode=0
        self.tick_age=0
        self.checked=0
        self.fail_send=False
        self.equity=10000.

    def account_info(self):
        return NS(login=123,server='Broker-Demo',trade_mode=self.mode,margin_mode=2,
                  equity=self.equity,balance=10000.,currency='USD',trade_allowed=True)

    def terminal_info(self):
        return NS(connected=True,trade_allowed=True)

    def positions_get(self):
        return self.opened

    def symbol_select(self,*args):
        return True

    def symbol_info(self,symbol):
        return NS(point=.00001,digits=5,volume_min=.01,volume_max=100.,volume_step=.01,
                  trade_stops_level=10,trade_freeze_level=10,filling_mode=3,trade_exemode=2)

    def symbol_info_tick(self,symbol):
        return NS(bid=1.1000,ask=1.1001,time=time.time()-self.tick_age)

    def order_calc_profit(self,kind,symbol,volume,entry,sl):
        return -abs(entry-sl)*100000*volume

    def order_check(self,request):
        self.checked+=1
        return NS(retcode=0)

    def order_send(self,request):
        self.sent.append(request)
        if self.fail_send:
            return None
        result=namedtuple('Result','retcode order volume comment')(10009,44,request.get('volume',0),'OK')
        if request.get('action')==1 and not request.get('position'):
            self.opened.append(NS(ticket=44,symbol=request['symbol'],type=request['type'],volume=request['volume'],
                                  sl=request['sl'],tp=request['tp'],magic=request['magic'],comment=request['comment'],
                                  price_open=request['price'],time=time.time()))
        elif request.get('action')==1 and request.get('position'):
            for p in list(self.opened):
                if p.ticket==request['position']:
                    p.volume=round(p.volume-request['volume'],8)
                    if p.volume<=0:self.opened.remove(p)
        elif request.get('action')==6:
            for p in self.opened:
                if p.ticket==request['position']:p.sl,p.tp=request['sl'],request['tp']
        return result

    def last_error(self):
        return (0,'fake')

    def copy_rates_from_pos(self,symbol,tf,start,count):
        rows=[]
        closed=int(time.time()//(tf*60))*(tf*60)-tf*60
        for i in range(300):
            close=1.08+i*.00003+.0001*np.sin(i)
            rows.append((closed-(299-i)*tf*60,close,close+.0003,close-.0003,close,1000))
        return np.array(rows,dtype=[('time','i8'),('open','f8'),('high','f8'),('low','f8'),('close','f8'),('tick_volume','i8')])


def test_demo_and_identity_guard():
    fake=FakeMT5()
    worker=MT5Worker(fake,account())
    worker.verify()
    fake.mode=2
    with pytest.raises(RuntimeError,match='DEMO'):
        worker.open_position(deployment(),'deploy1:new','EURUSD','BUY',1.09,1.12)
    assert fake.sent==[]
    fake.mode=0
    worker.account['login']=999
    with pytest.raises(RuntimeError,match='login'):
        worker.verify()


def test_volume_risk_and_idempotent_send():
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    result=worker.open_position(d,'deploy1:entry','EURUSD','BUY',1.09,1.12)
    assert result.volume==.02
    assert worker.open_position(d,'deploy1:entry','EURUSD','BUY',1.09,1.12) is None
    assert len(fake.sent)==1 and fake.checked==1
    assert fake.sent[0]['sl']==1.09
    with pytest.raises(ValueError,match='mínimo'):
        floor_volume(.009,fake.symbol_info('EURUSD'))


def test_stale_tick_and_fixed_lot_over_budget_are_rejected():
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    fake.tick_age=100
    with pytest.raises(RuntimeError,match='obsoleta'):
        worker.open_position(d,'deploy1:entry','EURUSD','BUY',1.09,1.12)
    fake.tick_age=0;d['fixed_lot']=1.
    with pytest.raises(RuntimeError,match='excede'):
        worker.open_position(d,'deploy1:entry','EURUSD','BUY',1.09,1.12)
    assert not fake.sent


def test_unknown_result_pauses_and_blocks_retry_after_restart():
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment();fake.fail_send=True
    with pytest.raises(RuntimeError,match='incierto'):
        worker.open_position(d,'deploy1:first','EURUSD','BUY',1.09,1.12)
    assert store.get('deployment','deploy1')['state']=='PAUSED'
    d['state']='ACTIVE';store.put('deployment',d['id'],d)
    with pytest.raises(RuntimeError,match='reconciliación'):
        worker.open_position(d,'deploy1:second','EURUSD','BUY',1.09,1.12)
    assert len(fake.sent)==1


def test_exclusive_worker_lease():
    assert store.lease('a','worker1')
    assert not store.lease('a','worker2')
    assert store.lease('a','worker1')


def test_paused_copy_propagates_master_close_but_never_touches_manual_positions():
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    d.update(source_type='account',source_id='master')
    store.put('deployment',d['id'],d)
    master=dict(ticket=1,symbol='EURUSD',type=0,volume=1.,sl=1.09,tp=1.12,time=time.time())
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,positions=[]))
    state=worker.local_state(d);worker.account_copy(d,state,True)
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,positions=[master]))
    worker.account_copy(d,state,True)
    assert len(fake.opened)==1
    fake.opened.append(NS(ticket=999,symbol='EURUSD',type=0,volume=.01,sl=1.09,tp=1.12,magic=0,comment='manual',price_open=1.1,time=time.time()))
    d['state']='PAUSED';store.put('deployment',d['id'],d)
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,positions=[]))
    worker.account_copy(d,state,False)
    assert [p.ticket for p in fake.opened]==[999]


def test_closed_bar_algorithm_runs_only_once_and_pause_prevents_entries():
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    strategy=Strategy(strategy_id='algorithm1',direction='LONG_ONLY',close_before_weekend=False,
                      buy_conditions=[Condition('RSI',{'period':2},'GREATER_THAN',target_value=0)])
    item=dict(strategy=strategy.to_dict(),weight=1.)
    state=worker.local_state(d)
    worker.algorithm(d,state,item,0,False)
    assert not fake.sent
    worker.algorithm(d,state,item,0,True)
    assert not fake.sent  # Resume waits for a fresh candle, does not replay paused candles.
    state['bars'].clear()
    worker.algorithm(d,state,item,0,True)
    assert len(fake.sent)==1
    worker.algorithm(d,state,item,0,True)
    assert len(fake.sent)==1


def test_master_baseline_new_entry_and_no_reopen_after_manual_close():
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    d.update(source_type='account',source_id='master')
    store.put('deployment',d['id'],d)
    master=dict(ticket=1,symbol='EURUSD',type=0,volume=1.,sl=1.09,tp=1.12,time=time.time())
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,positions=[master]))
    state=worker.local_state(d)
    worker.account_copy(d,state,True)
    assert not fake.sent  # Existing master positions are not imported.
    master2=dict(master,ticket=2)
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,positions=[master,master2]))
    worker.account_copy(d,state,True)
    assert len(fake.sent)==1
    fake.opened=[]  # Manual/broker close on follower.
    worker.account_copy(d,state,True)
    assert len(fake.sent)==1
    store.put('snapshot','master',dict(at=0,verified_demo=True,positions=[]))
    with pytest.raises(RuntimeError,match='Master'):
        worker.account_copy(d,state,True)
    assert len(fake.sent)==1


def test_api_creation_is_paused_and_rejects_unsupported_rules(tmp_path,monkeypatch):
    from backend.portfolio import StrategyRecord
    client=TestClient(app)
    terminal=tmp_path/'terminal64.exe';terminal.write_text('test fixture')
    response=client.post('/api/copy/accounts',json=dict(name='Demo',terminal_path=str(terminal),login=123,server='Broker-Demo'))
    assert response.status_code==200,response.text
    key=response.json()['id']
    strategy=Strategy(strategy_id='test_strategy',max_weekly_loss_pct=0,max_monthly_loss_pct=0,
        buy_conditions=[Condition('RSI',{},'LESS_THAN',target_value=30)])
    monkeypatch.setattr(StrategyRecord,'load',lambda key:NS(data={'strategy':strategy.to_dict()}))
    body=dict(name='Copy',account_id=key,source_type='strategy',source_id='test_strategy')
    response=client.post('/api/copy/deployments',json=body)
    assert response.status_code==200,response.text
    record=response.json();assert record['state']=='PAUSED'
    assert client.post(f'/api/copy/deployments/{record["id"]}/resume').status_code in (404,409)
    strategy.avg_enabled=True
    assert client.post('/api/copy/deployments',json=body).status_code==422
    assert client.get('/api/copy/status').json()['real_trading_enabled'] is False


def test_copy_api_rejects_cross_origin_controls():
    client=TestClient(app)
    response=client.post('/api/copy/accounts/anything/worker',headers={'Origin':'https://untrusted.example'})
    assert response.status_code==403


def test_groups_master_followers_settings_and_membership():
    client=TestClient(app)
    for key in ('master','follower1','follower2'):
        store.put('account',key,dict(account(),id=key,name=key,login=123+len(key)))
    master=client.post('/api/copy/masters',json={'name':'Master test','account_id':'master'}).json()
    assert client.post('/api/copy/masters',json={'name':'Duplicate','account_id':'master'}).status_code==409
    group=client.post('/api/copy/groups',json={'name':'Group test','account_ids':['follower1','follower2'],'risk_mode':'MIRROR'}).json()
    response=client.post(f'/api/copy/masters/{master["id"]}/followers',json={'group_id':group['id']})
    assert response.status_code==200,response.text
    assert [r['status'] for r in response.json()['results']]==['PAUSED','PAUSED']
    records=store.listing('deployment')
    assert all(d['risk_mode']=='MIRROR' and d['group_id']==group['id'] for d in records)
    key=records[0]['id']
    patched=client.patch(f'/api/copy/deployments/{key}/settings',json={'risk_mode':'MULTIPLIER','multiplier':2,'symbol_filter':'BLACKLIST','symbol_whitelist':['XAUUSD']})
    assert patched.status_code==200,patched.text
    assert patched.json()['state']=='PAUSED'
    assert client.patch(f'/api/copy/deployments/{key}/settings',json={'state':'ACTIVE'}).status_code==400
    assert client.delete(f'/api/copy/groups/{group["id"]}').status_code==409
    client.patch(f'/api/copy/groups/{group["id"]}',json={'name':'Group renamed','account_ids':['follower1'],'risk_mode':'PROPORTIONAL'})
    removed=next(d for d in store.listing('deployment') if d['account_id']=='follower2')
    assert removed['group_id'] is None and removed['state']=='PAUSED'
    applied=client.post(f'/api/copy/groups/{group["id"]}/apply').json()
    assert len(applied['updated'])==1
    retained=next(d for d in store.listing('deployment') if d['account_id']=='follower1')
    assert retained['risk_mode']=='PROPORTIONAL'
    assert client.delete(f'/api/copy/masters/{master["id"]}').status_code==409


@pytest.mark.parametrize('mode,source_volume,equity,multiplier,expected',[
    ('FIXED_LOT',.1,10000,1,.01),('MULTIPLIER',.01,10000,2,.02),
    ('MIRROR',.02,10000,1,.02),('PROPORTIONAL',.04,20000,1,.02),('RISK_PERCENT',1.,10000,1,.02)])
def test_copy_sizing_modes(mode,source_volume,equity,multiplier,expected):
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    d.update(risk_mode=mode,multiplier=multiplier,fixed_lot=.01)
    store.put('deployment',d['id'],d)
    result=worker.open_position(d,'deploy1:mode','EURUSD','BUY',1.09,1.12,source_volume=source_volume,source_equity=equity)
    assert result.volume==expected


def test_exposure_and_equity_protection():
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    d['max_total_exposure']=.01
    with pytest.raises(RuntimeError,match='Exposición'):
        worker.open_position(d,'deploy1:exposure','EURUSD','BUY',1.09,1.12)
    assert not fake.sent
    d['equity_protection']=11000
    assert not worker.risk_allowed(d,fake.account_info())


def test_blacklist_and_custom_stops_on_master_copy():
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    d.update(source_type='account',source_id='master',symbol_filter='BLACKLIST',
             symbol_whitelist=['EURUSD'],sl_tp_mode='CUSTOM',custom_sl_pips=20,custom_tp_pips=40)
    store.put('deployment',d['id'],d)
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,positions=[]))
    state=worker.local_state(d);worker.account_copy(d,state,True)
    origin=dict(ticket=7,symbol='EURUSD',type=0,volume=1.,sl=0.,tp=0.,time=time.time())
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,positions=[origin]))
    worker.account_copy(d,state,True)
    assert not fake.sent
    d['symbol_filter']='WHITELIST';store.put('deployment',d['id'],d)
    worker.account_copy(d,state,True)
    assert len(fake.sent)==1
    assert fake.sent[0]['sl']==pytest.approx(1.0981)
    assert fake.sent[0]['tp']==pytest.approx(1.1041)


def test_stop_connector_pauses_entries_without_closing_positions():
    client=TestClient(app)
    store.put('account','account1',account())
    deployment()
    result=client.post('/api/copy/accounts/account1/worker/stop')
    assert result.status_code==200
    assert store.get('worker_control','account1')['stop'] is True
    assert store.get('deployment','deploy1')['state']=='PAUSED'

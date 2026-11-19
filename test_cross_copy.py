"""Cross-platform copy tests; all quotes and fills are simulated in memory."""
import time
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from backend.api import app
from backend import copy_trading as store
from backend.mt5_worker import MT5Worker
from test_copy_trading import FakeMT5,account,deployment,isolated_store

class Futures(FakeMT5):
    platform='NT8'
    def symbol_info(self,symbol):
        return NS(point=.25,digits=8,volume_min=1,volume_max=100,volume_step=1,
                  trade_stops_level=1,trade_freeze_level=0,filling_mode=2,trade_exemode=2)
    def symbol_info_tick(self,symbol):
        return NS(bid=20000,ask=20000.25,time=time.time())
    def order_calc_profit(self,kind,symbol,volume,entry,sl):
        return -abs(entry-sl)*2*volume

def setup(fake=None,**options):
    fake=fake or Futures();worker=MT5Worker(fake,account());d=deployment()
    d.update(source_type='account',source_id='master',cross_platform=True,symbol_map={'NAS100':'MNQ DEC26'},risk_mode='RISK_PERCENT',**options)
    store.put('deployment',d['id'],d)
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,positions=[],source_instance='a'))
    state=worker.local_state(d);worker.account_copy(d,state,True)
    return fake,worker,d,state

def publish(*positions,instance='a'):
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,equity=10000,positions=list(positions),source_instance=instance))

def signal(**changes):
    return dict(dict(ticket=123,symbol='NAS100',type=0,volume=.1,price_open=19950,sl=19940,tp=19970,time=time.time()),**changes)

def test_lots_to_contracts_preserves_cash_risk_and_translates_protection():
    fake,worker,d,state=setup()
    publish(signal());worker.account_copy(d,state,True)
    order=fake.sent[-1]
    assert order['volume']==1
    assert order['sl']==19990.25 and order['tp']==20020.25
    ref=state['positions']['123']
    assert ref['source_ticket']=='123' and ref['target_ticket']==44
    assert TestClient(app).get('/api/copy/deployments/'+d['id']+'/tickets').json()[0]['target_order']==44
    assert ref['target_symbol']=='MNQ DEC26'
    worker.account_copy(d,state,True)
    assert len(fake.sent)==1

def test_contracts_to_lots_uses_destination_specs():
    fake,worker,d,state=setup(FakeMT5())
    d['symbol_map']={'MNQ DEC26':'EURUSD'}
    publish(signal(symbol='MNQ DEC26',price_open=100,sl=99.99,tp=100.02,volume=1))
    worker.account_copy(d,state,True)
    assert fake.sent[-1]['symbol']=='EURUSD'
    assert fake.sent[-1]['volume']==.02


def test_risk_below_one_contract_is_rejected():
    fake,worker,d,state=setup(risk_percent=.1)
    publish(signal())
    with pytest.raises((ValueError,RuntimeError)):
        worker.account_copy(d,state,True)
    assert not fake.sent


def test_cross_partial_and_paused_full_close_preserve_manual_position():
    fake,worker,d,state=setup(fixed_lot=2,max_lot=5,risk_percent=1)
    d['risk_mode']='FIXED_LOT'
    origin=signal(volume=2);publish(origin);worker.account_copy(d,state,True)
    publish(dict(origin,volume=1));worker.account_copy(d,state,False)
    assert fake.opened[0].volume==1
    fake.opened.append(NS(ticket=999,symbol='MNQ DEC26',type=0,volume=1,magic=0,comment='manual'))
    publish();worker.account_copy(d,state,False)
    assert [p.ticket for p in fake.opened]==[999]


def test_restart_of_master_never_infers_a_close():
    fake,worker,d,state=setup();publish(signal());worker.account_copy(d,state,True)
    publish(instance='b')
    with pytest.raises(RuntimeError,match='reiniciada'):worker.account_copy(d,state,True)
    assert len(fake.sent)==1


def test_paused_signal_is_not_imported_when_resuming():
    fake,worker,d,state=setup();publish(signal());worker.account_copy(d,state,False)
    worker.account_copy(d,state,True)
    assert not fake.sent


def test_manual_native_registration_and_copy_validation():
    client=TestClient(app)
    store.put('ninja_snapshot','bridge',dict(at=time.time(),instance='one',version='1.7.0-pending',accounts=[dict(name='Sim101',provider='Simulator',execution_allowed=True)]))
    registered=client.post('/api/copy/native-accounts',json=dict(connection='bridge',account='Sim101'))
    assert registered.status_code==200
    native=registered.json()
    assert native['platform']=='NT8'
    assert client.post('/api/copy/native-accounts',json=dict(connection='bridge',account='Sim101')).json()['id']==native['id']
    store.put('account','master',dict(account(),id='master'))
    body=dict(name='MT5 to NT8',account_id=native['id'],source_type='account',source_id='master',symbol_map={'NAS100':'MNQ DEC26'},risk_mode='MIRROR')
    assert client.post('/api/copy/deployments',json=body).status_code==422
    response=client.post('/api/copy/deployments',json=dict(body,quantity_ratio=10))
    assert response.status_code==200,response.text
    record=response.json()
    assert record['platform']=='NT8' and record['state']=='PAUSED' and record['max_positions']==5
    assert client.patch('/api/copy/deployments/'+record['id']+'/settings',json={'symbol_map':{'NAS100':'NQ DEC26'}}).status_code==409


def test_real_native_account_rejected():
    store.put('ninja_snapshot','bridge',dict(at=time.time(),instance='one',version='1.7.0-pending',accounts=[dict(name='Live',provider='Broker',execution_allowed=True)]))
    assert TestClient(app).post('/api/copy/native-accounts',json=dict(connection='bridge',account='Live')).status_code==409


def test_futures_symbol_with_expiry_is_a_valid_source():
    assert store.validate_symbol_map({'MNQ DEC26':'NAS100'}) == {'MNQ DEC26':'NAS100'}
    with pytest.raises(Exception):store.validate_symbol_map({'NQ|method=mutate':'NAS100'})


def test_native_worker_executes_copy_and_keeps_leg_runtime(monkeypatch):
    from backend import ninja_execution
    brokers=[]
    class Native(Futures):
        def __init__(self,connection,account_name,session,symbol,magic,parent=None):
            super().__init__();self.connection=connection;self.account_name=account_name;self.symbol=symbol;brokers.append(self)
        def invalidate(self):pass
        def rpc(self,method):return {'ok':True}
        def orders_get(self):return []
    monkeypatch.setattr(ninja_execution,'NinjaBroker',Native)
    from backend import ninja_copy_broker
    monkeypatch.setattr(ninja_copy_broker,'NinjaCopyBroker',Native)
    store.put('ninja_snapshot','bridge',dict(at=time.time(),instance='one',accounts=[dict(name='Sim101',provider='Simulator',execution_allowed=True)]))
    d=deployment();d.update(source_type='account',source_id='master',platform='NT8',connection='bridge',
        account_name='Sim101',instance='one',cross_platform=True,risk_mode='RISK_PERCENT',
        symbol_map={'NAS100':'MNQ DEC26'},strategies=[dict(strategy=dict(symbol='NAS100'),weight=1.)])
    store.put('deployment',d['id'],d);publish()
    worker=ninja_execution.NinjaWorker(d);worker.cycle()
    publish(signal());worker.cycle()
    assert brokers[-1].sent[-1]['volume']==1
    runtime=store.get('runtime',d['id'])
    assert runtime['copy_legs']['0']['positions']['123']['target_ticket']==44
    assert 'copy_legs' in runtime and 'baseline_master' in runtime
    publish();worker.cycle()
    assert not brokers[-1].opened

"""Transport and diagnostic tests. No installed terminal or broker is contacted."""
import hashlib
import time
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from backend.api import app
from backend import copy_trading as store
from backend.ea_bridge import EABroker
from backend import mt5_diagnostic as diag
from backend.mt5_worker import MT5Worker
from test_copy_trading import FakeMT5, account, deployment, isolated_store


@pytest.fixture(autouse=True)
def no_real_worker_process(monkeypatch):
    monkeypatch.setattr('backend.ea_bridge.ensure_ea_worker',lambda key:None)


def test_ea_key_hash_authentication_and_delivery_once():
    store.put('account','account1',account())
    client=TestClient(app)
    pairing=client.post('/api/copy/accounts/account1/ea-key')
    assert pairing.status_code==200
    token=pairing.json()['token']
    assert store.get('ea_key','account1')['hash']==hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(store.listing('account'))
    assert client.get('/api/copy/ea/account1/poll').status_code==401
    command=dict(id='cmd',account='account1',method='order_send',args={'action':1},state='QUEUED',created=time.time())
    store.put('ea_command','cmd',command)
    headers={'X-Stratix-Key':token}
    assert client.get('/api/copy/ea/account1/poll',headers=headers).text=='cmd|order_send|action=1'
    assert client.get('/api/copy/ea/account1/poll',headers=headers).text==''
    assert client.post('/api/copy/ea/account1/result/cmd',headers=headers,json={'retcode':10009}).status_code==200
    assert client.post('/api/copy/ea/account1/result/cmd',headers=headers,json={}).status_code==409


def test_ea_expired_command_is_not_executed():
    store.put('ea_key','a',{'hash':hashlib.sha256(b'token').hexdigest()})
    store.put('ea_command','old',dict(id='old',account='a',method='order_send',args={},state='QUEUED',created=0))
    client=TestClient(app)
    assert client.get('/api/copy/ea/a/poll',headers={'X-Stratix-Key':'token'}).text==''
    assert store.get('ea_command','old')['state']=='EXPIRED'


def test_experts_stream_bootstraps_skips_old_logs_and_preserves_rpc_priority():
    store.put('account','account1',account())
    store.put('ea_key','account1',{'hash':hashlib.sha256(b'token').hexdigest()})
    d=deployment();d['name']='Portfolio demo';store.put('deployment',d['id'],d)
    store.log('account1',d['id'],'old history')
    client=TestClient(app);headers={'X-Stratix-Key':'token'}
    path='/api/copy/ea/account1/poll'
    assert client.get(path,headers=headers).text==''  # Backward-compatible old EA.
    result=client.get(path+'?log_events=true&after_event_seq=-1',headers=headers).text
    assert 'Portfolio demo: ACTIVE' in result and 'old history' not in result
    cursor=int(result.split('|seq=')[1].split('|')[0])
    store.log('account1',d['id'],'SEÑAL SELL | RSI\nclosed')
    store.put('ea_command','urgent',dict(id='urgent',account='account1',method='account_info',args={},state='QUEUED',created=time.time()))
    stream=path+f'?log_events=true&after_event_seq={cursor}'
    assert client.get(stream,headers=headers).text=='urgent|account_info'
    message=client.get(stream,headers=headers).text
    assert 'SEÑAL SELL / RSI closed' in message
    next_cursor=int(message.split('|seq=')[1].split('|')[0])
    assert client.get(path+f'?log_events=true&after_event_seq={next_cursor}',headers=headers).text==''
    assert client.get(path+f'?log_events=true&after_event_seq={cursor}',headers={}).status_code==401


def test_ea_account_without_terminal_path_and_saved_diagnostic_is_paused(tmp_path,monkeypatch):
    from backend import portfolio
    monkeypatch.setattr(portfolio,'STRATEGY_DIR',tmp_path/'saved')
    diag.save_test_algorithm()
    client=TestClient(app)
    response=client.post('/api/copy/accounts',json=dict(name='EA demo',login=123,server='Broker-Demo',connection_mode='EA'))
    assert response.status_code==200,response.text
    key=response.json()['id']
    response=client.post('/api/copy/deployments',json=dict(name='Test',account_id=key,source_type='strategy',source_id=diag.PROFILE))
    assert response.status_code==200,response.text
    d=response.json()
    assert d['state']=='PAUSED' and d['source_type']=='diagnostic'
    assert len(client.get(f'/api/copy/diagnostics/{d["id"]}').json()['plan'])==20
    assert client.post(f'/api/copy/accounts/{key}/diagnostic',json={}).status_code in (404,405)
    assert client.post(f'/api/copy/deployments/{d["id"]}/resume').status_code in (404,409)


class DiagnosticBroker(FakeMT5):
    TRADE_ACTION_PENDING=5
    def __init__(self):
        super().__init__()
        self.pending=[]
        self.bid=1.1000
        self.deals=[]
    def symbol_info_tick(self,symbol): return NS(bid=self.bid,ask=self.bid+.0001,time=time.time())
    def orders_get(self): return self.pending
    def history_deals_get(self,position): return self.deals
    def order_send(self,r):
        if r['action'] in (5,7,8):
            self.sent.append(r)
            if r['action']==5:
                self.pending.append(NS(ticket=77,symbol=r['symbol'],type=r['type'],volume=r['volume'],
                    price_open=r['price'],sl=r['sl'],tp=r['tp'],magic=r['magic'],comment=r['comment'],time=time.time()))
            elif r['action']==7:
                o=self.pending[0];o.price_open=r['price'];o.sl=r['sl'];o.tp=r['tp']
            else: self.pending=[]
            from backend.ea_bridge import EAResult
            return EAResult(retcode=10008 if r['action']==5 else 10009,order=77,volume=r.get('volume',0),comment='OK')
        return super().order_send(r)


@pytest.mark.parametrize('index',range(20))
def test_each_diagnostic_case_cleans_only_its_trades(index):
    fake=DiagnosticBroker();worker=MT5Worker(fake,account());d=deployment()
    d.update(source_type='diagnostic',diagnostic_symbol='EURUSD',diagnostic_timeout=15,max_lot=.02)
    store.put('deployment',d['id'],d)
    store.put('diagnostic',d['id'],dict(index=index,phase='OPEN',results=[]))
    case=diag.CASES[index]
    diag.run(worker,d,True)
    assert len(fake.sent)==1
    if case['entry']=='MARKET':
        if case['exit'] in ('SL','TP'):
            fake.opened=[]
            fake.deals=[NS(reason=4 if case['exit']=='SL' else 5)]
        elif case['exit']=='BREAKEVEN':
            fake.bid=1.1005 if case['direction']=='BUY' else 1.0995
        state=store.get('diagnostic',d['id']);state['started']-=10
        store.put('diagnostic',d['id'],state)
    for _ in range(8):
        diag.run(worker,d,True)
        state=store.get('diagnostic',d['id'])
        if state['results']: break
    assert state['results'][0]['outcome']=='PASS',state
    assert not fake.opened and not fake.pending
    assert 'modified' not in state and 'partial_volume' not in state


def test_pending_placed_is_accepted_but_market_placed_remains_ambiguous():
    fake=DiagnosticBroker();worker=MT5Worker(fake,account());d=deployment()
    result=worker.send(d,'deploy1:p',dict(action=5,type=2,symbol='EURUSD',volume=.01,price=1.09,sl=1.08,tp=1.11))
    assert result.retcode==10008
    assert store.get('deployment',d['id'])['state']=='ACTIVE'


def test_diagnostic_pause_no_entry_and_price_timeout_not_pass():
    fake=DiagnosticBroker();worker=MT5Worker(fake,account());d=deployment()
    d.update(diagnostic_symbol='EURUSD',diagnostic_timeout=15,max_lot=.02)
    store.put('deployment',d['id'],d)
    store.put('diagnostic',d['id'],dict(index=4,phase='OPEN',results=[]))
    diag.run(worker,d,False);assert not fake.sent
    diag.run(worker,d,True)
    state=store.get('diagnostic',d['id']);state['started']-=30;store.put('diagnostic',d['id'],state)
    for _ in range(4): diag.run(worker,d,False)
    assert store.get('diagnostic',d['id'])['results'][0]['outcome']=='INCONCLUSIVE'


def test_ea_proxy_rejects_protocol_injection():
    with pytest.raises(ValueError): EABroker(account()).rpc('tick',symbol='EURUSD|action=1')


def test_failed_live_indicator_audit_cannot_be_bypassed_by_resume(monkeypatch):
    from backend import indicator_audit
    calls=[]
    def failure(frame):
        calls.append(True)
        return dict(passed=0,checks=200,failed=200,results=[])
    monkeypatch.setattr(indicator_audit,'audit_frame',failure)
    fake=DiagnosticBroker();worker=MT5Worker(fake,account());d=deployment()
    d.update(audit_indicators=True,diagnostic_symbol='EURUSD')
    store.put('diagnostic',d['id'],dict(index=0,phase='OPEN',results=[]))
    for _ in range(2):
        d['state']='ACTIVE';store.put('deployment',d['id'],d)
        diag.run(worker,d,True)
        assert store.get('deployment',d['id'])['state']=='PAUSED'
    assert len(calls)==2 and not fake.sent


def test_saved_test_algorithm_uses_normal_assignment_flow_and_has_own_log(tmp_path,monkeypatch):
    from backend import portfolio
    monkeypatch.setattr(portfolio,'STRATEGY_DIR',tmp_path/'saved')
    path=diag.save_test_algorithm()
    assert path.is_file()
    client=TestClient(app)
    saved=client.get('/api/strategies/saved').json()
    assert saved[0]['strategy']['name']=='STX · Test integral demo'
    assert len(saved[0]['test_cases'])==20
    store.put('account','account1',account())
    response=client.post('/api/copy/deployments',json=dict(name='Prueba desde Mis algoritmos',
        account_id='account1',source_type='strategy',source_id=diag.PROFILE,
        symbol_map={'EURUSD':'EURUSD.m'}))
    assert response.status_code==200,response.text
    d=response.json()
    assert d['state']=='PAUSED' and d['source_id']==diag.PROFILE
    assert d['diagnostic_symbol']=='EURUSD.m'
    assert d['risk_percent']==.1 and d['max_lot']==.02 and d['max_positions']==1
    assert d['strategies'][0]['strategy']['id']==diag.PROFILE
    store.log('account1',d['id'],'INICIO 1/20')
    store.log('account1','other','No debe mezclarse')
    report=client.get(f'/api/copy/diagnostics/{d["id"]}').json()
    assert [e['message'] for e in report['events']]==['INICIO 1/20']
    assert report['results']==[]

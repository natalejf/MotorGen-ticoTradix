import time
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from backend.api import app
from backend import copy_trading as store
from backend import portfolio
from backend.strategy import Strategy,Condition
from backend import mt5_diagnostic as diagnostic
from backend.ea_bridge import ensure_ea_worker
from test_copy_trading import isolated_store,account,deployment,FakeMT5
from backend.mt5_worker import MT5Worker


@pytest.fixture
def saved(tmp_path,monkeypatch):
    monkeypatch.setattr(portfolio,'STRATEGY_DIR',tmp_path/'saved')
    store.put('account','account1',dict(account(),connection_mode='EA'))
    store.put('snapshot','account1',dict(at=time.time(),verified_demo=True,positions=[]))
    strategy=Strategy(strategy_id='normal',name='Algoritmo normal',risk_per_trade_pct=.7,
        sizing_mode='FIXED_LOT',fixed_lot=.03,max_daily_loss_pct=0,max_account_loss_pct=0,
        max_weekly_loss_pct=0,max_monthly_loss_pct=0,
        buy_conditions=[Condition('RSI',{},'LESS_THAN',target_value=30)])
    portfolio.StrategyRecord(strategy.to_dict()).save()
    diagnostic.save_test_algorithm()
    return strategy


@pytest.mark.parametrize('source_id',['normal',diagnostic.PROFILE])
def test_same_single_step_start_for_normal_and_test_algorithm(saved,source_id):
    client=TestClient(app)
    response=client.post('/api/execution/start',json=dict(source_id=source_id,account_id='account1'))
    assert response.status_code==200,response.text
    session=response.json()
    assert session['state']=='ACTIVE' and session['uses_source_risk']
    assert session['origin_type']=='strategy'
    if source_id=='normal':
        assert session['risk_percent']==.7 and session['fixed_lot']==.03
        assert session['max_daily_loss_pct']==session['max_drawdown_pct']==0
    else:
        assert session['risk_percent']==.1 and session['max_lot']==.02
    sessions=client.get('/api/execution/sessions',params={'source_id':source_id}).json()
    assert len(sessions)==1 and sessions[0]['events'][0]['message'].startswith('INICIO')
    assert ('diagnostic' in sessions[0])==(source_id==diagnostic.PROFILE)
    assert client.post(f'/api/execution/sessions/{session["id"]}/pause').json()['state']=='PAUSED'
    assert client.post(f'/api/execution/sessions/{session["id"]}/resume').json()['state']=='ACTIVE'
    response=client.post('/api/execution/start',json=dict(source_id=source_id,account_id='account1'))
    assert response.status_code==200 and response.json()['id']==session['id']
    assert response.json()['reused_session'] and len(store.listing('deployment'))==1


def test_disconnected_account_cannot_create_active_session(saved):
    store.put('snapshot','account1',dict(at=0,verified_demo=False))
    client=TestClient(app)
    assert client.post('/api/execution/start',json=dict(source_id='normal',account_id='account1')).status_code==409
    assert store.listing('deployment')==[]


def test_execution_rejects_cross_origin_start(saved):
    client=TestClient(app)
    assert client.post('/api/execution/start',json=dict(source_id='normal',account_id='account1'),
        headers={'Origin':'https://untrusted.example'}).status_code==403


def test_portfolio_uses_the_same_start_and_its_saved_risk_budget(saved,monkeypatch):
    record=portfolio.StrategyRecord.load('normal').data
    monkeypatch.setattr(portfolio.Portfolio,'load',lambda key:NS(name='Cartera',risk_budget=.6,strategies=[record],weights=[1.]))
    response=TestClient(app).post('/api/execution/start',json=dict(source_type='portfolio',source_id='portfolio1',account_id='account1'))
    assert response.status_code==200,response.text
    session=response.json()
    assert session['origin_type']=='portfolio' and session['risk_percent']==.6
    assert session['max_daily_loss_pct']==session['max_drawdown_pct']==0


def test_ea_auto_connection_starts_once_and_respects_explicit_stop(saved,monkeypatch):
    calls=[]
    monkeypatch.setattr(store,'start_local_worker',lambda key:calls.append(key))
    ensure_ea_worker('account1');ensure_ea_worker('account1')
    assert calls==['account1']
    store.put('worker_control','account1',{'stop':True})
    store.put('ea_launch','account1',{'at':0})
    ensure_ea_worker('account1')
    assert calls==['account1']


def test_no_added_daily_or_drawdown_manager_when_source_disables_it():
    fake=FakeMT5();d=deployment();d['max_daily_loss_pct']=d['max_drawdown_pct']=0
    worker=MT5Worker(fake,account())
    assert worker.risk_allowed(d,NS(equity=10000))
    assert worker.risk_allowed(d,NS(equity=5000))


def test_legacy_active_diagnostic_is_visible_and_reused_without_reset(saved):
    client=TestClient(app)
    d=deployment()
    d.update(source_type='diagnostic',source_id='diagnostic',execution_profile=diagnostic.PROFILE,
             diagnostic_symbol='EURUSDm',name='Test anterior')
    store.put('deployment',d['id'],d)
    state=dict(index=5,phase='CLEANUP',results=[{'outcome':'PASS'}])
    store.put('diagnostic',d['id'],state)
    sessions=client.get('/api/execution/sessions',params={'source_id':diagnostic.PROFILE}).json()
    assert len(sessions)==1 and sessions[0]['diagnostic']['index']==5
    result=client.post('/api/execution/start',json=dict(source_id=diagnostic.PROFILE,account_id='account1')).json()
    assert result['id']==d['id'] and result['reused_session']
    assert result['diagnostic_symbol']=='EURUSDm'
    assert store.get('diagnostic',d['id'])==state
    assert len(store.listing('deployment'))==1


@pytest.mark.parametrize('state',['PAUSED','CLOSING'])
def test_existing_session_is_not_implicitly_resumed(saved,state):
    d=deployment();d.update(source_id='normal',state=state);store.put('deployment',d['id'],d)
    result=TestClient(app).post('/api/execution/start',json=dict(source_id='normal',account_id='account1'))
    assert result.status_code==200 and result.json()['state']==state
    assert store.get('deployment',d['id'])['state']==state


def test_other_source_is_not_replaced_or_closed(saved):
    d=deployment();d['name']='Otro algoritmo';store.put('deployment',d['id'],d)
    response=TestClient(app).post('/api/execution/start',json=dict(source_id='normal',account_id='account1'))
    assert response.status_code==409 and 'Otro algoritmo' in response.json()['detail']
    assert store.get('deployment',d['id'])==d


def test_account_symbol_mapping_is_saved_and_inherited_by_test_and_normal_sources(saved):
    client=TestClient(app)
    assert client.put('/api/copy/accounts/account1/symbols',json={'symbol_map':{'EURUSD':'EURUSDm'}}).status_code==200
    response=client.post('/api/execution/start',json=dict(source_id=diagnostic.PROFILE,account_id='account1'))
    assert response.status_code==200,response.text
    session=response.json()
    assert session['diagnostic_symbol']=='EURUSDm'
    assert session['symbol_map']=={'EURUSD':'EURUSDm'}
    assert store.get('account','account1')['symbol_map']=={'EURUSD':'EURUSDm'}
    assert client.put('/api/copy/accounts/account1/symbols',json={'symbol_map':{'EURUSD':'bad|command'}}).status_code==422
    assert store.get('deployment',session['id'])['diagnostic_symbol']=='EURUSDm'


def test_clearing_log_preserves_results_actions_state_and_other_sessions(saved):
    client=TestClient(app)
    d=deployment()
    store.put('diagnostic',d['id'],{'index':1,'results':[{'outcome':'PASS'}]})
    store.claim_action('deploy1:sent',{'action':1})
    store.log('account1',d['id'],'old log')
    store.log('account1','other','keep')
    response=client.delete(f'/api/execution/sessions/{d["id"]}/log')
    assert response.status_code==200 and response.json()['deleted']==1
    assert store.get('deployment',d['id'])==d
    assert store.get('diagnostic',d['id'])['index']==1
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM actions').fetchone()[0]==1
        assert db.execute('SELECT message FROM events').fetchone()[0]=='keep'


def test_bars_validates_symbol_before_requesting_history():
    fake=FakeMT5();fake.symbol_select=lambda *args:False
    fake.copy_rates_from_pos=lambda *args:pytest.fail('No debe pedir histórico para un símbolo inexistente')
    with pytest.raises(RuntimeError,match='Símbolo MT5 no disponible: EURUSD'):
        MT5Worker(fake,account()).bars('EURUSD','30m')


def test_reactivation_starts_fresh_log_and_visible_results_without_losing_order_state(saved):
    client=TestClient(app)
    session=client.post('/api/execution/start',json=dict(source_id=diagnostic.PROFILE,account_id='account1')).json()
    key=session['id']
    progress=dict(index=3,phase='WAIT',results=[{'outcome':'PASS'}]*3,opening_ticket=12345)
    store.put('diagnostic',key,progress)
    store.put('runtime',key,{'positions':{'12345':{'tracked':True}}})
    store.put('indicator_audit',key,{'passed':200})
    store.put('last_error',key,{'message':'old error','at':time.time()})
    store.claim_action(key+':sent',{'position':12345})
    store.log('account1',key,'old message')
    client.post(f'/api/execution/sessions/{key}/pause')
    response=client.post(f'/api/execution/sessions/{key}/resume')
    assert response.status_code==200
    view=client.get('/api/execution/sessions',params={'source_id':diagnostic.PROFILE}).json()[0]
    assert view['diagnostic']['results']==[] and view['diagnostic']['index']==0
    assert view['diagnostic']['total_cases']==17
    assert view['indicator_audit'] is None
    assert len(view['events'])==1 and 'ACTIVE' in view['events'][0]['message']
    assert store.get('diagnostic',key)==progress
    assert store.get('runtime',key)['positions']['12345']['tracked']
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM actions WHERE id=?',(key+':sent',)).fetchone()[0]==1
    store.put('diagnostic',key,dict(progress,index=4,results=progress['results']+[{'outcome':'FAIL'}]))
    view=client.get('/api/execution/sessions',params={'source_id':diagnostic.PROFILE}).json()[0]
    assert view['diagnostic']['index']==1 and view['diagnostic']['results']==[{'outcome':'FAIL'}]


def test_new_start_hides_previous_sessions_and_clears_their_log_for_same_source(saved):
    client=TestClient(app)
    first=client.post('/api/execution/start',json=dict(source_id='normal',account_id='account1')).json()
    first['state']='STOPPED';store.put('deployment',first['id'],first)
    store.log('account1',first['id'],'previous attempt')
    second=client.post('/api/execution/start',json=dict(source_id='normal',account_id='account1')).json()
    sessions=client.get('/api/execution/sessions',params={'source_id':'normal'}).json()
    assert [s['id'] for s in sessions]==[second['id']]
    assert len(sessions[0]['events'])==1 and sessions[0]['events'][0]['message'].startswith('INICIO')
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM events WHERE deployment=?',(first['id'],)).fetchone()[0]==0


def test_clicking_start_on_same_active_algorithm_clears_log_without_duplicate_session(saved):
    client=TestClient(app)
    body=dict(source_id='normal',account_id='account1')
    first=client.post('/api/execution/start',json=body).json()
    store.log('account1',first['id'],'old error')
    again=client.post('/api/execution/start',json=body).json()
    assert again['id']==first['id'] and again['reused_session']
    events=client.get('/api/execution/sessions',params={'source_id':'normal'}).json()[0]['events']
    assert len(events)==1 and 'Registro nuevo' in events[0]['message']

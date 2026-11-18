import json
import time
import pytest
from fastapi.testclient import TestClient
from backend.api import app
from backend import portfolio,copy_trading as store,ninja_execution as execution,ninja_rpc
from backend.strategy import Strategy,Condition
from test_copy_trading import isolated_store


def test_clear_results_preserves_durable_library(tmp_path,monkeypatch):
    monkeypatch.setattr(portfolio,'STRATEGY_DIR',tmp_path/'saved')
    monkeypatch.setattr(portfolio,'PORTFOLIO_DIR',tmp_path/'ports')
    strategy=Strategy(strategy_id='persist',buy_conditions=[Condition('RSI',{},'LESS_THAN',target_value=30)])
    record=portfolio.StrategyRecord(strategy.to_dict());path=record.save()
    record.data['note']='second save';record.save()
    portfolio.write_saved_json(tmp_path/'ports'/'one.json',{'name':'kept'})
    response=TestClient(app).post('/api/clear-all-phases')
    assert response.status_code==200
    assert portfolio.StrategyRecord.load('persist').data['note']=='second save'
    assert json.loads(path.with_suffix('.json.bak').read_text())['strategy']['id']=='persist'
    assert (tmp_path/'ports'/'one.json').exists()


def test_native_start_rejects_provider_and_reserves_one_algorithm(tmp_path,monkeypatch):
    monkeypatch.setattr(portfolio,'STRATEGY_DIR',tmp_path/'saved')
    monkeypatch.setattr(execution,'ensure_workers',lambda key:None)
    strategy=Strategy(strategy_id='generated',buy_conditions=[Condition('RSI',{},'LESS_THAN',target_value=30)],
                      max_weekly_loss_pct=0,max_monthly_loss_pct=0,max_consecutive_wins=0,max_consecutive_losses=0)
    portfolio.StrategyRecord(strategy.to_dict()).save()
    snapshot=dict(at=time.time(),version='1.5.4-portfolio',instance='one',accounts=[dict(name='Sim101',provider='Simulator',
                  execution_allowed=True,balance=50000,status='PASS')])
    store.put('ninja_snapshot','bridge',snapshot)
    client=TestClient(app)
    body=dict(connection='bridge',account='Sim101',source_id='generated',symbol_map={strategy.symbol:'NQ DEC26'},contracts=1)
    result=client.post('/api/ninja/execution/start',json=body)
    assert result.status_code==200,result.text
    value=result.json();assert value['platform']=='NT8' and value['fixed_lot']==1 and value['uses_source_risk'] is False
    assert client.post('/api/ninja/execution/start',json=body).json()['id']==value['id']
    snapshot['accounts'][0].update(provider='Provider31',execution_allowed=False)
    store.put('ninja_snapshot','bridge',snapshot)
    assert client.post('/api/ninja/execution/start',json=body).status_code==409


def test_rpc_is_delivered_once_and_results_bound_to_instance():
    record=dict(id='cmd',connection='bridge',instance='one',method='state',args={},expires=time.time()+30,state='QUEUED')
    store.put('ninja_engine_rpc','cmd',record)
    assert ninja_rpc.poll('bridge','one').startswith('cmd|one|')
    assert ninja_rpc.poll('bridge','one')==''
    ninja_rpc.accept_results('bridge','other',[dict(id='cmd',value={'ok':True})])
    assert store.get('ninja_engine_rpc','cmd')['state']=='DELIVERED'
    ninja_rpc.accept_results('bridge','one',[dict(id='cmd',value={'ok':True})])
    assert store.get('ninja_engine_rpc','cmd')['state']=='DONE'


def test_old_engine_addon_is_blocked_before_any_assignment():
    store.put('ninja_snapshot','bridge',dict(at=time.time(),version='1.5.3-portfolio',instance='one',accounts=[]))
    response=TestClient(app).post('/api/ninja/execution/start',json=dict(connection='bridge',account='Sim101',source_id='any',symbol_map={'NASDAQ':'MNQ DEC26'}))
    assert response.status_code==409 and '1.5.4' in response.json()['detail']
    assert not store.listing('deployment')


def test_portfolio_requires_distinct_contracts_and_isolates_legs(tmp_path,monkeypatch):
    monkeypatch.setattr(portfolio,'PORTFOLIO_DIR',tmp_path/'ports')
    monkeypatch.setattr(execution,'ensure_workers',lambda key:None)
    first=Strategy(strategy_id='a',symbol='NASDAQ',buy_conditions=[Condition('RSI',{},'LESS_THAN',target_value=30)],max_weekly_loss_pct=0,max_monthly_loss_pct=0)
    second=Strategy(strategy_id='b',symbol='SP500',buy_conditions=[Condition('EMA',{'period':20},'PRICE_ABOVE')],max_weekly_loss_pct=0,max_monthly_loss_pct=0)
    port=portfolio.Portfolio('Multisymbol',[{'strategy':first.to_dict()},{'strategy':second.to_dict()}],weights=[.4,.6],risk_budget=2,portfolio_id='multi')
    port.save()
    store.put('ninja_snapshot','bridge',dict(at=time.time(),version='1.5.4-portfolio',instance='one',accounts=[dict(name='Sim101',provider='Simulator',execution_allowed=True,balance=50000,status='PASS')]))
    body=dict(connection='bridge',account='Sim101',source_type='portfolio',source_id='multi',symbol_map={'NASDAQ':'MNQ DEC26','SP500':'MNQ DEC26'},contracts=1)
    client=TestClient(app)
    assert client.post('/api/ninja/execution/start',json=body).status_code==422
    body['symbol_map']['SP500']='MES DEC26'
    response=client.post('/api/ninja/execution/start',json=body)
    assert response.status_code==200,response.text
    record=response.json();worker=execution.NinjaWorker(record)
    assert record['source_type']=='portfolio' and record['risk_percent']==2
    assert [b.symbol for b in worker.brokers]==['MNQ DEC26','MES DEC26']
    assert len({b.session for b in worker.brokers})==2
    assert {b.parent for b in worker.brokers}=={record['id']}
    assert [b.magic for b in worker.brokers]==[record['magic'],record['magic']+1]
    assert [item['weight'] for item in record['strategies']]==[.4,.6]


def test_native_diagnostic_rejects_unsplittable_contracts_without_reserving_account(tmp_path,monkeypatch):
    monkeypatch.setattr(portfolio,'STRATEGY_DIR',tmp_path/'saved')
    monkeypatch.setattr(execution,'ensure_workers',lambda key:None)
    strategy=Strategy(strategy_id='native_diag',symbol='NASDAQ',buy_conditions=[Condition('PRICE',{},'GREATER_THAN',target_value=0)],
                      max_weekly_loss_pct=0,max_monthly_loss_pct=0)
    portfolio.StrategyRecord(dict(strategy=strategy.to_dict(),execution_profile='stx_nt8_audit_v1')).save()
    store.put('ninja_snapshot','bridge',dict(at=time.time(),version='1.5.4-portfolio',instance='one',accounts=[dict(name='Sim101',provider='Simulator',execution_allowed=True,balance=50000,status='PASS')]))
    body=dict(connection='bridge',account='Sim101',source_id='native_diag',symbol_map={'NASDAQ':'MNQ DEC26'},contracts=1)
    client=TestClient(app)
    assert client.post('/api/ninja/execution/start',json=body).status_code==422
    assert not store.listing('deployment')
    body['contracts']=2;response=client.post('/api/ninja/execution/start',json=body)
    assert response.status_code==200,response.text
    assert response.json()['source_type']=='diagnostic'
    assert client.post('/api/ninja/execution/start',json=body).json()['id']==response.json()['id']

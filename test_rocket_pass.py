"""API lifecycle and isolation for RocketPass; native trading is never enabled."""
import time
from fastapi.testclient import TestClient
from backend.api import app
from backend import copy_trading as store
from test_copy_trading import isolated_store


def native(client,namespace):
    pairing=client.post(f'/api/{namespace}/connections',json={}).json()
    headers={'X-Stratix-Key':pairing['token']}
    pulse=dict(instance='native1',version='1.9.0-vote40' if namespace=='rocket' else '1.7.0-pending',realtime=True,account_available=True,
        master_enabled=False,position_quantity=0,kind='candle_service_v1',data_ready=True,
        accounts=[dict(name='Eval-123',provider='Broker',connected=True,execution_allowed=False)])
    assert client.post(f'/api/{namespace}/bridge/{pairing["id"]}/pulse',headers=headers,json=pulse).status_code==200
    return pairing,headers,pulse


def test_rocket_and_proppass_connections_credentials_groups_are_isolated():
    c=TestClient(app);rocket,rh,rpulse=native(c,'rocket');prop,ph,ppulse=native(c,'ninja')
    group=c.post('/api/rocket/groups',json=dict(name='Rocket exam',settings=dict(accounts=['Eval-123']))).json()
    assert c.get('/api/rocket/status').json()['groups'][0]['id']==group['id']
    assert c.get('/api/ninja/status').json()['groups']==[]
    assert c.post('/api/rocket/bridge/'+rocket['id']+'/pulse',headers=ph,json=rpulse).status_code==401
    assert c.post('/api/ninja/bridge/'+rocket['id']+'/pulse',headers=rh,json=rpulse).status_code==404
    assert c.get('/api/rocket/download').status_code==200


def test_evaluation_requires_explicit_authorization_then_confirmed_native_scope():
    c=TestClient(app);p,h,s=native(c,'ninja');path='/api/ninja/connections/'+p['id']
    assert c.post(path+'/configure',json=dict(accounts=['Eval-123'])).status_code==409
    result=c.post(path+'/authorize-evaluation',json=dict(accounts=['Eval-123']))
    assert result.status_code==200,result.text
    command=result.json();assert command['settings']['accounts']==['Eval-123']
    # The browser alone cannot make execution available. The native AddOn must
    # confirm the authorization and publish its new per-account capability.
    assert store.get('ninja_snapshot',p['id'])['accounts'][0]['execution_allowed'] is False
    s.update(last_ack=command['id'],ack_status='APPLIED',ack_detail='authorized')
    c.post('/api/ninja/bridge/'+p['id']+'/pulse',headers=h,json=s)
    assert c.post(path+'/configure',json=dict(accounts=['Eval-123'])).status_code==409
    s['accounts'][0]['execution_allowed']=True
    c.post('/api/ninja/bridge/'+p['id']+'/pulse',headers=h,json=s)
    assert c.post(path+'/configure',json=dict(accounts=['Eval-123'])).status_code==200


def test_rocket_contract_budget_rejects_grid_exceeding_total_cap():
    c=TestClient(app)
    result=c.post('/api/rocket/groups',json=dict(name='too much',settings=dict(accounts=['Sim101'],lots=2,limit_count=10,limit_contracts=2,stop_count=10,stop_contracts=2,max_contracts=30)))
    assert result.status_code==422
    result=c.post('/api/rocket/groups',json=dict(name='valid',settings=dict(accounts=['Sim101'],lots=2,limit_count=10,limit_contracts=2,stop_count=10,stop_contracts=2,max_contracts=42)))
    assert result.status_code==200
    assert result.json()['settings']['max_contracts']==42
    assert result.json()['settings']['timeframe_minutes']==5
    assert result.json()['settings']['trend_period']==40


def test_grid_defaults_and_same_size_follow_initial_contracts_and_overrides():
    from backend.rocket_bridge import RocketSettings
    from pydantic import ValidationError
    import pytest
    s=RocketSettings(accounts=['Sim101'],lots=4,max_contracts=40)
    assert (s.limit_count,s.stop_count,s.limit_contracts,s.stop_contracts)==(3,3,4,4)
    s=RocketSettings(accounts=['Sim101'],lots=4,max_contracts=40,grid_same_as_initial=False,limit_contracts=2,stop_contracts=1)
    assert (s.limit_contracts,s.stop_contracts)==(2,1)
    with pytest.raises(ValidationError):
        RocketSettings(accounts=['Sim101'],lots=4,max_contracts=40,account_overrides={'Sim101':{'lots':6}})
    with pytest.raises(ValidationError):
        RocketSettings(accounts=['Sim101'],grid_same_as_initial=False,limit_contracts=4.01)


def test_rocket_rejects_non_m5_or_non_vote40_configuration():
    c=TestClient(app)
    for changes in ({'timeframe_minutes':1},{'trend_period':20}):
        response=c.post('/api/rocket/groups',json=dict(name='wrong signal',settings=dict(accounts=['Sim101'],**changes)))
        assert response.status_code==422


def test_old_rocket_addon_cannot_activate_vote_signal():
    c=TestClient(app);p,h,s=native(c,'rocket')
    s['version']='1.7.0-pending'
    c.post('/api/rocket/bridge/'+p['id']+'/pulse',headers=h,json=s)
    result=c.post('/api/rocket/connections/'+p['id']+'/configure',json={'accounts':['Eval-123']})
    assert result.status_code==409 and '1.9.0-vote40' in result.json()['detail']


def test_rocket_pending_group_does_not_update_proppass_queue():
    c=TestClient(app);p,h,s=native(c,'rocket')
    s['accounts'][0]['execution_allowed']=True
    c.post('/api/rocket/bridge/'+p['id']+'/pulse',headers=h,json=s)
    group=c.post('/api/rocket/groups',json=dict(name='Rocket A',settings=dict(accounts=['Eval-123'],trend_period=40))).json()
    response=c.post('/api/rocket/queues/'+p['id']+'/groups/'+group['id'],json={})
    assert response.status_code==200,response.text
    assert store.listing('rocket_queue') and not store.listing('ninja_queue')
    assert not store.listing('ninja_command')


def test_evaluation_authorization_can_be_revoked_without_selecting_another_account():
    c=TestClient(app);p,h,s=native(c,'ninja')
    response=c.post('/api/ninja/connections/'+p['id']+'/evaluation-accounts',json={'accounts':[]})
    assert response.status_code==200,response.text
    assert response.json()['settings']=={'accounts':[]}


def test_release_clears_confirmed_group_and_prevents_unconfigured_start():
    c=TestClient(app);p,h,s=native(c,'ninja')
    store.put('ninja_config_ack',p['id'],dict(instance='native1',group_id='old',settings={'accounts':['Eval-123']}))
    response=c.post('/api/ninja/connections/'+p['id']+'/release',json={})
    assert response.status_code==200,response.text
    c.post('/api/ninja/bridge/'+p['id']+'/pulse',headers=h,json=s)
    s.update(last_ack=response.json()['id'],ack_status='APPLIED',ack_detail='released')
    c.post('/api/ninja/bridge/'+p['id']+'/pulse',headers=h,json=s)
    assert store.get('ninja_config_ack',p['id'])['group_id'] is None
    assert c.post('/api/ninja/connections/'+p['id']+'/start',json={}).status_code==409

"""Native adapter contract simulated only; does not launch NinjaTrader."""
import hashlib
import time

from fastapi.testclient import TestClient

from backend.api import app
from backend import copy_trading as store
from test_copy_trading import isolated_store


def pair(client):
    p=client.post('/api/ninja/connections',json={}).json()
    return p,{'X-Stratix-Key':p['token']}


def pulse(client,p,headers,**changes):
    value=dict(account='Sim101',instance='native1',realtime=True,account_available=True,
               master_enabled=False,position_quantity=0,kind='candle_service_v1',data_ready=True,
               accounts=[{'name':'Sim101'},{'name':'SimAccount2'}])
    value.update(changes)
    return client.post(f'/api/ninja/bridge/{p["id"]}/pulse',headers=headers,json=value)


def test_pair_auth_sim_scope_and_no_funded_activation():
    client=TestClient(app);p,h=pair(client)
    assert store.get('ninja_connection',p['id'])['hash']==hashlib.sha256(p['token'].encode()).hexdigest()
    assert pulse(client,p,{}).status_code==401
    assert client.post(f'/api/ninja/bridge/{p["id"]}/pulse',headers=h,json={'account':'Funded123'}).status_code==422
    assert pulse(client,p,h).status_code==200
    result=client.get('/api/ninja/status').json()
    assert result['connections'][0]['connected'] and result['copy_execution_enabled'] is False
    assert p['token'] not in str(result)
    assert client.post(f'/api/ninja/connections/{p["id"]}/start',json={}).status_code==409


def test_config_ack_then_start_once_and_pause_preserves_positions():
    client=TestClient(app);p,h=pair(client);pulse(client,p,h)
    endpoint=f'/api/ninja/connections/{p["id"]}'
    command=client.post(endpoint+'/configure',json={'lots':1}).json()
    assert client.post(endpoint+'/start',json={}).status_code==409
    response=pulse(client,p,h)
    assert command['id'] in response.text and '|configure|' in response.text
    assert pulse(client,p,h).text==''  # Delivered commands are never replayed.
    assert store.get('ninja_command',command['id'])['state']=='DELIVERED'
    pulse(client,p,h,last_ack=command['id'],ack_status='APPLIED',ack_detail='configured')
    assert store.get('ninja_command',command['id'])['state']=='APPLIED'
    assert client.post(endpoint+'/start',json={}).status_code==200
    start=pulse(client,p,h).text.split('|')[0]
    pulse(client,p,h,last_ack=start,ack_status='APPLIED')
    body=dict(account='Sim101',instance='native1',realtime=True,account_available=True,master_enabled=True,position_quantity=1)
    client.post(f'/api/ninja/bridge/{p["id"]}/pulse',headers=h,json=body)
    assert client.post(endpoint+'/configure',json={}).status_code==409
    assert client.post(endpoint+'/pause',json={}).status_code==200


def test_expiry_wrong_instance_stale_and_cross_origin():
    client=TestClient(app);p,h=pair(client);pulse(client,p,h)
    endpoint=f'/api/ninja/connections/{p["id"]}'
    c=client.post(endpoint+'/configure',json={}).json();c['expires']=time.time()-1
    store.put('ninja_command',c['id'],c)
    assert pulse(client,p,h).text==''
    assert store.get('ninja_command',c['id'])['state']=='EXPIRED'
    body=dict(account='Sim101',instance='another',realtime=True,account_available=True,master_enabled=False,position_quantity=0)
    assert client.post(f'/api/ninja/bridge/{p["id"]}/pulse',headers=h,json=body).status_code==409
    snapshot=store.get('ninja_snapshot',p['id']);snapshot['at']=0;store.put('ninja_snapshot',p['id'],snapshot)
    assert client.post(endpoint+'/pause',json={}).status_code==409
    assert client.post('/api/ninja/connections',headers={'Origin':'https://evil.invalid'},json={}).status_code==403
    assert client.get('/api/ninja/download',headers={'Origin':'https://evil.invalid'}).status_code==403
    assert client.post(endpoint+'/configure',json={'lots':0}).status_code==422


def test_integrated_source_has_separate_config_and_sim_guards():
    source=(store.ROOT/'ninjatrader'/'StratixChallengeCandleController.cs').read_text(encoding='utf-8')
    assert 'class StratixChallengeCandleController : Strategy' in source
    assert '"StratixChallengeCandleConfig.txt"' in source
    assert 'StratixWebEnabled = false' in source
    assert 'Stratix web solo Sim101' in source
    assert 'Close[0] > Open[0]' in source and 'Close[0] < Open[0]' in source


def test_unimplemented_profit_only_setting_is_rejected():
    client=TestClient(app);p,h=pair(client);pulse(client,p,h)
    result=client.post(f'/api/ninja/connections/{p["id"]}/configure',json={'exit_only_profit':True})
    assert result.status_code==422 and 'no implementa' in result.json()['detail']


def test_groups_apply_ack_and_start_require_matching_group_and_sim_accounts():
    client=TestClient(app);p,h=pair(client);pulse(client,p,h)
    group=client.post('/api/ninja/groups',json={'name':'Dos demos','settings':{'accounts':['Sim101','SimAccount2'],'symbol':'GC DEC26','timeframe_minutes':1}}).json()
    prefix=f'/api/ninja/connections/{p["id"]}/groups/{group["id"]}'
    assert client.post(prefix+'/start').status_code==409
    command=client.post(prefix+'/apply').json()
    wire=pulse(client,p,h).text
    assert 'accounts=Sim101,SimAccount2' in wire and 'symbol=GC DEC26' in wire
    pulse(client,p,h,last_ack=command['id'],ack_status='APPLIED')
    assert client.post(prefix+'/start').status_code==200
    assert client.post('/api/ninja/groups',json={'name':'No','settings':{'accounts':['Funded123']}}).status_code==422
    assert client.put('/api/ninja/groups/'+group['id'],json={'name':'Editado','settings':{'accounts':['Sim101']}}).status_code==200
    assert client.get('/api/ninja/status').json()['groups'][0]['name']=='Editado'


def test_headless_addon_has_no_chart_or_native_panel_dependency():
    source=(store.ROOT/'ninjatrader'/'StratixCandleService.cs').read_text(encoding='utf-8')
    assert 'class StratixCandleService : AddOnBase' in source
    assert 'ChartControl' not in source and 'InitializeDockPanel' not in source
    assert 'Instrument.MarketData.Update+=' in source
    assert 'EvaluateEntrySignals(close>open,close<open)' in source


def test_second_five_accounts_and_emergency_use_applied_not_edited_scope():
    client=TestClient(app);p,h=pair(client)
    accounts=['SimAccount'+str(i) for i in range(6,11)]
    rows=[{'name':name} for name in accounts]
    pulse(client,p,h,accounts=rows)
    settings=dict(accounts=accounts,symbol='NQ DEC26',timeframe_minutes=5,lots=1,
                  target=150,max_loss=2000,tp_usd=150,sl_usd=2000,
                  daily_profit_limit=150,daily_loss_limit=2000)
    group=client.post('/api/ninja/groups',json={'name':'Segundo grupo','settings':settings}).json()
    prefix=f'/api/ninja/connections/{p["id"]}/groups/{group["id"]}'
    response=client.post(prefix+'/apply');assert response.status_code==200
    command=response.json()
    assert 'accounts='+','.join(accounts) in pulse(client,p,h,accounts=rows).text
    pulse(client,p,h,accounts=rows,last_ack=command['id'],ack_status='APPLIED')
    edited=dict(settings,accounts=['Sim101'],symbol='GC DEC26')
    assert client.put('/api/ninja/groups/'+group['id'],json={'name':'Editado','settings':edited}).status_code==200
    close=client.post(prefix+'/close-stop').json()
    assert close['settings']['accounts']==accounts
    assert close['settings']['symbol']=='NQ DEC26'
    assert client.post('/api/ninja/groups',json={'name':'Cuenta ajena','settings':{'accounts':['SimAccount11']}}).status_code==422

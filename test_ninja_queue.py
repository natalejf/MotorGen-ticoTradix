from fastapi.testclient import TestClient
from backend.api import app
from backend import copy_trading as store
from test_copy_trading import isolated_store
from test_ninja_bridge import pair,pulse


def setup_queue():
    client=TestClient(app);p,h=pair(client)
    rows=[dict(name='Sim'+str(i),connected=True,execution_allowed=True,
               status='EN PROCESO',daily_status='EN PROCESO',position_quantity=0,working_orders=[]) for i in range(10)]
    pulse(client,p,h,accounts=rows)
    groups=[]
    for index in range(2):
        groups.append(client.post('/api/ninja/groups',json=dict(name='Grupo '+str(index),settings=dict(accounts=[r['name'] for r in rows[index*5:index*5+5]]))).json())
        assert client.post(f'/api/ninja/queues/{p["id"]}/groups/{groups[-1]["id"]}').status_code==200
    return client,p,h,rows,groups


def start_first(client,p,h,rows):
    wire=pulse(client,p,h,accounts=rows).text
    assert '|configure|' in wire
    assert 'accounts=Sim0,Sim1,Sim2,Sim3,Sim4' in wire
    wire=pulse(client,p,h,accounts=rows,last_ack=wire.split('|')[0],ack_status='APPLIED').text
    assert '|start' in wire
    pulse(client,p,h,accounts=rows,last_ack=wire.split('|')[0],ack_status='APPLIED',master_enabled=True)


def test_one_account_complete_cannot_skip_rest_of_group_or_force_other_group():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    rows[0].update(status='PASS',daily_status='TARGET_REACHED')
    assert pulse(c,p,h,accounts=rows,master_enabled=True).text==''
    q=store.get('ninja_queue',p['id'])
    assert q['index']==0 and q['items'][0]['state']=='ACTIVE'
    assert q['items'][1]['state']=='PENDING'
    prefix=f'/api/ninja/connections/{p["id"]}/groups/{groups[1]["id"]}'
    assert c.post(prefix+'/apply').status_code==409
    assert c.post(prefix+'/reset').status_code==409
    assert c.post(prefix+'/start').status_code==409
    again=c.post(f'/api/ninja/queues/{p["id"]}/groups/{groups[1]["id"]}').json()
    assert len(again['items'])==2 and again['index']==0


def test_every_account_terminal_and_flat_is_required_then_next_group_starts():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    for i,r in enumerate(rows[:5]):r.update(status='PASS' if i%2 else 'BURNED')
    rows[4]['working_orders']=[dict(name='SL',quantity=1)]
    pulse(c,p,h,accounts=rows,master_enabled=True)
    assert store.get('ninja_queue',p['id'])['index']==0
    rows[4]['working_orders']=[];rows[4]['position_quantity']=1
    pulse(c,p,h,accounts=rows,master_enabled=True,position_quantity=1)
    assert store.get('ninja_queue',p['id'])['index']==0
    rows[4]['position_quantity']=0
    assert pulse(c,p,h,accounts=rows).text==''

    assert store.get('ninja_queue',p['id'])['index']==1
    wire=pulse(c,p,h,accounts=rows).text
    assert '|configure|' in wire and 'accounts=Sim5,Sim6,Sim7,Sim8,Sim9' in wire
    wire=pulse(c,p,h,accounts=rows,last_ack=wire.split('|')[0],ack_status='APPLIED').text
    assert '|start' in wire
    pulse(c,p,h,accounts=rows,last_ack=wire.split('|')[0],ack_status='APPLIED',master_enabled=True)
    for r in rows[5:]:r.update(status='PASS')
    pulse(c,p,h,accounts=rows)
    q=store.get('ninja_queue',p['id'])
    assert q['state']=='COMPLETED' and all(item['state']=='COMPLETED' for item in q['items'])
    assert pulse(c,p,h,accounts=rows).text==''



def test_group_waits_for_own_orders_but_excludes_another_algorithms_position():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    for row in rows[:5]:row.update(status='PASS',proppass_position_quantity=0,proppass_working_orders=0)
    rows[0].update(position_quantity=1,working_orders=[dict(name='STXG_TP_other',quantity=1)])
    rows[4]['proppass_position_quantity']=1
    pulse(c,p,h,accounts=rows,master_enabled=True)
    assert store.get('ninja_queue',p['id'])['index']==0
    rows[4].update(proppass_position_quantity=0,proppass_working_orders=1)
    pulse(c,p,h,accounts=rows,master_enabled=True)
    assert store.get('ninja_queue',p['id'])['index']==0
    rows[4]['proppass_working_orders']=0
    pulse(c,p,h,accounts=rows,master_enabled=True)
    assert store.get('ninja_queue',p['id'])['index']==1


def test_pause_does_not_complete_group_and_resume_does_not_reset_results():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    rows[0]['status']='PASS'
    stop=c.post(f'/api/ninja/connections/{p["id"]}/pause',json={}).json()
    pulse(c,p,h,accounts=rows)
    pulse(c,p,h,accounts=rows,last_ack=stop['id'],ack_status='APPLIED')
    assert store.get('ninja_queue',p['id'])['state']=='PAUSED'
    assert pulse(c,p,h,accounts=rows).text==''
    c.post(f'/api/ninja/queues/{p["id"]}/groups/{groups[1]["id"]}')
    assert store.get('ninja_queue',p['id'])['state']=='PAUSED'
    assert pulse(c,p,h,accounts=rows).text==''
    c.post(f'/api/ninja/queues/{p["id"]}/groups/{groups[0]["id"]}')
    wire=pulse(c,p,h,accounts=rows).text
    assert '|configure|' in wire and '|reset|' not in wire
    assert 'accounts=Sim0,Sim1,Sim2,Sim3,Sim4' in wire


def test_disabled_unfinished_account_blocks_group_completion():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    for r in rows[:4]:r.update(status='PASS')
    rows[4].update(enabled=False,status='EN PROCESO')
    pulse(c,p,h,accounts=rows)
    q=store.get('ninja_queue',p['id'])
    assert q['state']=='PAUSED' and q['index']==0 and q['items'][1]['state']=='PENDING'


def test_editing_pending_group_does_not_change_running_group_or_commands():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    before=store.get('ninja_queue',p['id'])
    settings=dict(groups[1]['settings'],lots=7,tp_usd=321,
                  account_overrides={'Sim5':{'enabled':False}})
    response=c.put('/api/ninja/groups/'+groups[1]['id'],json=dict(name='Solo segundo',settings=settings))
    assert response.status_code==200
    after=store.get('ninja_queue',p['id'])
    assert after['items'][0]==before['items'][0]
    assert after['index']==0 and after['state']=='RUNNING'
    assert after['items'][1]['settings']['lots']==7
    assert after['items'][1]['settings']['account_overrides']['Sim5']['enabled'] is False
    assert store.get('ninja_group',groups[0]['id'])==groups[0]
    assert pulse(c,p,h,accounts=rows,master_enabled=True).text==''


def test_reset_pending_group_and_shared_account_edit_have_no_side_effects():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    before=store.get('ninja_queue',p['id'])
    response=c.post(f'/api/ninja/connections/{p["id"]}/groups/{groups[1]["id"]}/reset')
    assert response.status_code==409
    assert store.get('ninja_queue',p['id'])==before
    response=c.put('/api/ninja/groups/'+groups[1]['id'],json=dict(name='No comparte',settings=dict(groups[1]['settings'],accounts=['Sim0'])))
    assert response.status_code==409
    assert store.get('ninja_group',groups[1]['id'])==groups[1]


def test_finished_accounts_are_off_and_cannot_be_reenabled_without_reset():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    rows[0].update(status='PASS',enabled=True)
    pulse(c,p,h,accounts=rows,master_enabled=True)
    current=c.get('/api/ninja/status').json()['connections'][0]
    assert current['snapshot']['accounts'][0]['enabled'] is False
    response=c.post(f'/api/ninja/connections/{p["id"]}/accounts/Sim0/resume')
    assert response.status_code==409


def test_account_toggle_is_retained_only_in_its_group_queue_settings():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    before=store.get('ninja_queue',p['id'])['items'][1]
    command=c.post(f'/api/ninja/connections/{p["id"]}/accounts/Sim0/pause').json()
    pulse(c,p,h,accounts=rows,master_enabled=True)
    pulse(c,p,h,accounts=rows,last_ack=command['id'],ack_status='APPLIED',master_enabled=True)
    q=store.get('ninja_queue',p['id'])
    assert q['items'][0]['settings']['account_overrides']['Sim0']['enabled'] is False
    assert q['items'][1]==before


def test_native_communication_pause_preserves_reason_and_never_resumes_on_recovery():
    c,p,h,rows,groups=setup_queue();start_first(c,p,h,rows)
    pulse(c,p,h,accounts=rows,pause_code='COMMUNICATION_TIMEOUT',
          pause_reason='Sin confirmación del servidor durante 10 segundos. Último error: Timeout')
    q=store.get('ninja_queue',p['id'])
    assert q['state']=='PAUSED' and q['pause_code']=='COMMUNICATION_TIMEOUT'
    assert 'Timeout' in q['detail'] and q['pause_history'][-1]['reason']==q['detail']
    assert pulse(c,p,h,accounts=rows).text==''
    assert store.get('ninja_queue',p['id'])['state']=='PAUSED'

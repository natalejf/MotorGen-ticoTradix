"""Live simulation: closing PropPass must leave another algorithm untouched."""
import json,time,urllib.request
from pathlib import Path
from backend import copy_trading as store
from backend.ninja_rpc import NinjaBroker

def api(path,body=None):
    req=urllib.request.Request('http://127.0.0.1:8000'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)

def main():
    d=json.loads(Path('reports/ninja_scope_test_session.json').read_text())
    b=NinjaBroker(d['connection'],d['account_name'],d['id'],'MNQ DEC26',d['magic'])
    deadline=time.time()+60
    while time.time()<deadline:
        before=b.rpc('state')
        if before['positions']:break
        time.sleep(2)
    else:raise RuntimeError('No se abrió el algoritmo externo; no hay prueba válida de aislamiento')
    cmd=api('/api/ninja/connections/'+d['connection']+'/close-stop',{})
    deadline=time.time()+25
    while time.time()<deadline:
        status=store.get('ninja_command',cmd['id'])
        if status['state'] in ('APPLIED','REJECTED'):break
        time.sleep(.5)
    assert status['state']=='APPLIED',status
    after=b.rpc('state')
    assert [(p['ticket'],p['volume']) for p in before['positions']]==[(p['ticket'],p['volume']) for p in after['positions']]
    assert [(p['name'],p['quantity'],p['stop'],p['limit']) for p in before['protections']]==[(p['name'],p['quantity'],p['stop'],p['limit']) for p in after['protections']]
    assert store.get('deployment',d['id'])['state']=='ACTIVE'
    connections=api('/api/ninja/status')['connections']
    report=dict(result='PASS',before=before,after=after,proppass_command=status,connection_count=len(connections),
                algorithm_remained_active=True,meaning='Native simulation: global PropPass close-stop did not flatten the separately assigned algorithm on SimAccount3.')
    Path('reports/proppass_close_scope_verified.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('PASS: PropPass close-stop preserved the other algorithm, its position and native protections; connections=',len(connections),flush=True)
    api('/api/execution/sessions/'+d['id']+'/close-stop',{})

if __name__=='__main__':main()

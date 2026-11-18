import json,urllib.request
from pathlib import Path
from backend.ninja_rpc import NinjaBroker
r=json.loads(Path('reports/ninja_demo_assignment.json').read_text())
b=NinjaBroker(r['connection'],r['account_name'],r['id'],'MNQ DEC26',r['magic'])
s=b.state();Path('reports/ninja_demo_live_state.json').write_text(json.dumps(s,indent=2),encoding='utf-8');print(json.dumps(s),flush=True)
request=urllib.request.Request('http://127.0.0.1:8000/api/execution/sessions/'+r['id']+'/close-stop',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
with urllib.request.urlopen(request) as response:print('close-stop',json.load(response)['state'],flush=True)

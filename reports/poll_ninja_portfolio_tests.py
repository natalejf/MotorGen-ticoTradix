import json,time,urllib.request
from pathlib import Path
from backend import copy_trading as store
r=json.loads(Path('reports/ninja_portfolio_live_sessions.json').read_text());out={}
for label,dep in r.items():
 with urllib.request.urlopen('http://127.0.0.1:8000/api/execution/sessions?source_id='+dep['source_id']+'&source_type='+dep['origin_type']) as response:sessions=json.load(response)
 out[label]=next(s for s in sessions if s['id']==dep['id'])
d=out['diagnostic'].get('diagnostic',{});print('DIAG',out['diagnostic']['state'],d.get('index'),d.get('phase'),[(x['entry'],x['direction'],x['exit'],x['outcome']) for x in d.get('results',[])],flush=True)
print('PORTFOLIO',out['portfolio']['state'],[e['message'] for e in out['portfolio']['events'][:2]],flush=True)
Path('reports/ninja_portfolio_live_progress.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')

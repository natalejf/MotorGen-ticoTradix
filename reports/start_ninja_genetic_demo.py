import json,urllib.request
from pathlib import Path

def api(path,body=None):
 r=urllib.request.Request('http://127.0.0.1:8000'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(r,timeout=60) as x:return json.load(x)
r=json.loads(Path('reports/ninja_new_genetic_candidates.json').read_text(encoding='utf-8'))
c=next(c for c in r['candidates'] if c['strategy']['id']=='strat_935ab122')
c['strategy']['name']='STX · Demo Ninja · MACD M30'
c['demo_search_config']=r['config'];c['demo_notes']='Selección para prueba de integración: señal presente en NQ; holdout positivo. Mapeo explícito a MNQ; 1 contrato. No certificación de rentabilidad.'
print('saved',api('/api/strategy/save',dict(candidate_data=c,folder='Demo Ninja - Motor genetico')),flush=True)
d=api('/api/ninja/execution/start',dict(connection='38f7b4403b0c42dbbfef643ea6dea5ad',account='Sim101',source_id=c['strategy']['id'],source_type='strategy',symbol_map={'NASDAQ':'MNQ DEC26'},contracts=1))
Path('reports/ninja_demo_assignment.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
print('assignment',d['id'],d['state'],d['account_name'],flush=True)

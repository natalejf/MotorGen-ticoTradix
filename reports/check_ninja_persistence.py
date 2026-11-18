import json,time,urllib.request
from pathlib import Path
base='http://127.0.0.1:8000'
def get(path):
 with urllib.request.urlopen(base+path,timeout=10) as response:return json.load(response)
saved=get('/api/strategies/saved');assert any(c['strategy']['id']=='strat_935ab122' for c in saved)
nt=get('/api/ninja/status');c=next(c for c in nt['connections'] if c['id']=='38f7b4403b0c42dbbfef643ea6dea5ad');assert c['connected']
row=next(a for a in c['snapshot']['accounts'] if a['name']=='Sim101');assert row['symbol_map']=={'NASDAQ':'MNQ DEC26'}
assert row['position_quantity']==0 and not row['working_orders']
report=json.loads(Path('reports/ninja_genetic_live_verified.json').read_text(encoding='utf-8'));report.update(persistence_after_server_restart=True,saved_count=len(saved),post_restart_account=row,version=c['snapshot']['version'],native_instance=c['snapshot']['instance'],verification_time=time.time())
Path('reports/ninja_genetic_live_verified.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(saved_after_restart=len(saved),native_connected=c['connected'],version=c['snapshot']['version'],flat=True,mapping=row['symbol_map'],balance=row['balance'])))

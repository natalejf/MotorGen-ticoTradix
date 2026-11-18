import json,urllib.request
from pathlib import Path
base='http://127.0.0.1:8000'
def start(body):
 req=urllib.request.Request(base+'/api/ninja/execution/start',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
connection='38f7b4403b0c42dbbfef643ea6dea5ad'
p=start(dict(connection=connection,account='Sim101',source_type='portfolio',source_id='port_stx_demo_ninja_3_symbols',symbol_map={'NASDAQ':'MNQ DEC26','US30':'MYM DEC26','XAUUSD':'MGC DEC26'},contracts=1))
d=start(dict(connection=connection,account='SimAccount2',source_type='strategy',source_id='stx_nt8_audit_v1',symbol_map={'NASDAQ':'MNQ DEC26'},contracts=2))
Path('reports/ninja_portfolio_live_sessions.json').write_text(json.dumps(dict(portfolio=p,diagnostic=d),indent=2),encoding='utf-8')
print('PORTFOLIO',p['id'],p['state']);print('DIAGNOSTIC',d['id'],d['state'])

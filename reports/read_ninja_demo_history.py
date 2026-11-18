import json,uuid
from pathlib import Path
from backend import copy_trading as s
from backend.ninja_rpc import NinjaBroker
snap=s.listing('ninja_snapshot')[0];conn=s.listing('ninja_connection');key=next(c['id'] for c in conn if c['id']=='38f7b4403b0c42dbbfef643ea6dea5ad')
b=NinjaBroker(key,'Sim101',uuid.uuid4().hex,'NQ DEC26',100099999)
print('claim',b.rpc('claim'),flush=True)
try:
    print('state',b.state(),flush=True)
    bars=b.copy_rates_from_pos('NQ DEC26',30,1,1000)
    Path('reports/ninja_native_m30.json').write_text(json.dumps(bars),encoding='utf-8')
    print('bars',len(bars),'last',bars[-1],flush=True)
finally:print('release',b.rpc('release'),flush=True)

import json
from pathlib import Path
import pandas as pd
from backend.strategy import Strategy
from backend.backtester import Backtester
from backend.copy_trading import compatibility
report=json.loads(Path('reports/ninja_new_genetic_candidates.json').read_text(encoding='utf-8'))
bars=pd.DataFrame(json.loads(Path('reports/ninja_native_m30.json').read_text()));bars.index=pd.to_datetime(bars.pop('time'),unit='s');bars=bars.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','tick_volume':'Volume'})
ranked=sorted(report['candidates'],key=lambda c:c['metrics'].get('tn_score',0),reverse=True)
for candidate in ranked:
 s=Strategy.from_dict(candidate['strategy']);b,a=Backtester().generate_signal_arrays(bars,s)
 print(s.id,candidate['metrics']['tn_score'],bool(b[-1]),bool(a[-1]),compatibility(s),[(c.indicator,c.operator,c.params) for c in s.buy_conditions],flush=True)

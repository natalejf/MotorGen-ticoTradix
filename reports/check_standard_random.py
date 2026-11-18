"""Small local-data check; never deploys strategies or changes account assignments."""
import random,json,time
from pathlib import Path
from backend.data_manager import data_manager
from backend.genetic_engine import GeneticEngine,ALL_28_INDICATORS,ALL_EXIT_MODES
from backend.backtester import backtester
families={}
for key,meta in ALL_28_INDICATORS.items():families.setdefault(meta['family'],[]).append(key)
rng=random.Random(83);engine=GeneticEngine();frame=data_manager.load_data('EURUSD','1h');report=[]
for entry,exit_mode in [('MARKET','ATR_CLASSIC'),('LIMIT','PIPS_FIXED'),('STOP','TIME_EXIT')]:
 assert exit_mode in ALL_EXIT_MODES
 chosen=[rng.choice(keys) for keys in families.values()];row=dict(indicators=chosen,entry=entry,exit=exit_mode,strategies=[]);start=time.perf_counter()
 for _ in range(2):
  strategy=engine.create_random_strategy('EURUSD','1h',chosen,[entry],[exit_mode],rng=rng)
  result=backtester.run_backtest(strategy,frame)
  row['strategies'].append(dict(trades=result.metrics['total_trades'],score=result.metrics.get('tn_score'),actual_exit=strategy.exit_mode))
 row['seconds']=round(time.perf_counter()-start,3);report.append(row);print(entry,exit_mode,row['seconds'],flush=True)
Path('reports/standard_random_live_sample.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

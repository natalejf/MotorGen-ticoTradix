import cProfile,pstats,io,json,random,time
from pathlib import Path
from backend.genetic_engine import GeneticEngine,ALL_28_INDICATORS
from backend.backtester import Backtester
from backend.data_manager import data_manager
from backend.indicators import indicator_engine
frame=data_manager.load_data('EURUSD','1h').tail(4000).copy()
mixes={'compact':['EMA','RSI','ATR'],'broad':list(ALL_28_INDICATORS),'structural':['ICHIMOKU','PSAR','HMA','ADX','RCI']}
output=[]
profiler=cProfile.Profile();profiler.enable()
for name,inds in mixes.items():
 engine=GeneticEngine();bt=Backtester();indicator_engine.clear_cache();rng=random.Random(410)
 population=[engine.create_random_strategy('EURUSD','1h',inds,['MARKET'],['ATR_CLASSIC'],rng=rng,min_indicators=1,max_indicators=3, risk_rules={'close_before_weekend':False}) for _ in range(12)]
 start=time.perf_counter();trades=[]
 for strategy in population:
  result=bt.run_backtest(strategy,frame);trades.append(result.metrics.get('total_trades',0))
 elapsed=time.perf_counter()-start;output.append(dict(mix=name,bars=len(frame),candidates=12,seconds=elapsed,per_second=12/elapsed,with_trades=sum(t>0 for t in trades)))
profiler.disable();buffer=io.StringIO();pstats.Stats(profiler,stream=buffer).sort_stats('cumtime').print_stats(20)
Path('reports/search_optimized.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
Path('reports/search_optimized_profile.txt').write_text(buffer.getvalue(),encoding='utf-8')
print(json.dumps(output,indent=2));print(buffer.getvalue())

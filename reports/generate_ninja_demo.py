import json,time,urllib.request
from pathlib import Path

def api(path,body=None):
    req=urllib.request.Request('http://127.0.0.1:8000'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
config=dict(symbol='NASDAQ',timeframe='30m',search_mode='genetic',objective='tn_score',enabled_indicators=['EMA','SMA','RSI','MACD','ATR'],enabled_operators=['GREATER_THAN','LESS_THAN','PRICE_ABOVE','PRICE_BELOW'],enabled_entry_types=['MARKET'],enabled_exit_modes=['ATR_CLASSIC'],min_indicators_per_strategy=1,max_indicators_per_strategy=2,infinite_mode=False,population_size=40,generations=5,parallel_workers=0,holdout_pct=20,initial_deposit=50000,sizing_mode='FIXED_RISK',risk_per_trade_pct=1,averaging_config={'enabled':False},max_consecutive_wins=0,max_consecutive_losses=0,max_daily_trades=4,max_open_trades=1,close_before_weekend=True,prop_firm_filter=False,validate_during_exploration=False,modeling_mode='ohlc',spread_pips=1,slippage_pips=.2,min_win_rate=40,min_trades=30,min_profit_factor=1.2,min_sharpe=.8,min_dsr=0,max_drawdown=20,min_net_profit_usd=0,max_candidates=30)
print(api('/api/start-exploration',config),flush=True)
for _ in range(120):
    time.sleep(2);status=api('/api/status')
    if not status['is_running']:break
else:api('/api/stop-exploration',{});raise RuntimeError('Tiempo de búsqueda agotado')
result=api('/api/candidates')
Path('reports/ninja_new_genetic_candidates.json').write_text(json.dumps(dict(config=config,status=status,candidates=result),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(tested=status['tested_count'],accepted=status['accepted_count'],candidates=len(result),best=[{'id':c['strategy']['id'],'score':c['metrics'].get('tn_score'),'pf':c['metrics'].get('profit_factor'),'trades':c['metrics'].get('total_trades')} for c in result[:3]])),flush=True)

"""Live API exploration checks on an isolated local server. Never accesses MT5."""
import json
import time
import urllib.request
from pathlib import Path

BASE='http://127.0.0.1:8013'


def request(path,body=None):
    value=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request(BASE+path,data=value,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)


catalog=request('/api/config-defaults')['all_indicators']
all_indicators=list(catalog) if isinstance(catalog,dict) else [x['id'] for x in catalog]
cases=[
    ('compact',['EMA','RSI','ATR'],['MARKET'],['ATR_CLASSIC'],2,None,False),
    ('momentum',['RSI','MACD','STOCHASTIC'],['MARKET'],['PIPS_FIXED','TIME_EXIT'],2,None,False),
    ('structural',['HMA','RCI','PSAR','ADX'],['LIMIT','STOP'],['TRAILING_ATR','BREAKEVEN'],2,None,False),
    ('broad_stress',all_indicators,['MARKET','LIMIT','STOP'],['ATR_CLASSIC','PIPS_FIXED','PCT_EXIT','TRAILING_ATR','BREAKEVEN','STRUCTURE_SWING','TIME_EXIT','PARTIAL_TP','ATR_SMOOTHED'],4,None,False),
    ('all_operators',['EMA','RSI','MACD','HIGHEST'],['MARKET'],['ATR_CLASSIC'],2,['GREATER_THAN','LESS_THAN','EQUAL_TO','CROSS_ABOVE','CROSS_BELOW','CROSS_BOTH','PRICE_ABOVE','PRICE_BELOW','BULLISH','BEARISH'],False),
    ('equality_only',['RSI','MACD'],['MARKET'],['ATR_CLASSIC'],2,['EQUAL_TO'],False),
    ('validators_on',['EMA','RSI','ATR'],['MARKET'],['ATR_CLASSIC'],2,None,True),
    ('pipeline_control',['EMA','RSI','ATR'],['MARKET'],['ATR_CLASSIC'],2,None,False),
    ('validator_control',['EMA','RSI'],['MARKET'],['ATR_CLASSIC'],1,None,True),
]
results=[]
for name,indicators,entries,exits,max_rules,operators,validators in cases:
    config=dict(symbol='EURUSD',timeframe='1h',enabled_indicators=indicators,enabled_entry_types=entries,
        enabled_exit_modes=exits,min_indicators_per_strategy=1,max_indicators_per_strategy=max_rules,
        enabled_operators=operators,search_mode='genetic',infinite_mode=False,generations=2,population_size=12,
        validate_during_exploration=validators,wf_top_n=1,mv_top_n=1,mv_universes=10,
        modeling_mode='ohlc',parallel_workers=0,prop_firm_filter=False)
    if name.endswith('_control'):
        # Explicit plumbing check only: these are NOT the product's classification defaults.
        config.update(min_win_rate=0,min_trades=1,max_drawdown=100,min_net_profit_usd=-1e9,min_sharpe=-100,min_profit_factor=0,min_dsr=0)
    if name=='validator_control':config.update(population_size=4,generations=1)
    expected=config['population_size']*config['generations']
    started=time.monotonic();request('/api/start-exploration',config)
    first=None;samples=[]
    while True:
        status=request('/api/status');elapsed=time.monotonic()-started
        if status['tested_count'] and first is None:first=elapsed
        samples.append(dict(seconds=round(elapsed,3),created=status['tested_count'],approved=status['accepted_count'],progress=status['progress_pct']))
        if not status['is_running']:break
        if elapsed>150:
            request('/api/stop-exploration',{})
            raise RuntimeError(f'{name}: presupuesto de prueba excedido')
        time.sleep(.25)
    row=dict(name=name,config=config,seconds=round(elapsed,3),first_candidate_seconds=round(first,3) if first else None,
        no_trades=status.get('no_trade_count'),rejection_counts=status.get('rejection_counts'),
        created=status['tested_count'],approved=status['accepted_count'],discarded=status['discarded_count'],
        errors=[x for x in status['log_messages'] if 'Error en la exploración' in x],samples=samples)
    results.append(row)
    Path('reports/live_search_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in row.items() if k not in ('samples','config')},ensure_ascii=False),flush=True)
    assert row['created']==expected and not row['errors'],row

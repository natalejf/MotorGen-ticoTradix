"""Bounded genetic search and ordinary save APIs for a demo deployment trial."""
import json
import time
import urllib.request
from pathlib import Path

from backend import copy_trading as store
from backend.strategy import Strategy

BASE='http://127.0.0.1:8000'
OUT=Path(__file__).with_name('demo_genetic_portfolio.json')


def api(path,body=None):
    req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)


def main():
    account=store.listing('account')[0]
    if any(d['state']!='STOPPED' for d in store.listing('deployment') if d['account_id']==account['id']):
        raise RuntimeError('Hay otra asignación; no se sustituye sin revisar sus operaciones')
    report=dict(account_id=account['id'],started=time.time(),batches=[],purpose='Prueba realista DEMO; no certificación de inversión')
    def save():OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    groups=[('Tendencia',['EMA','SMA','ADX']),('Momentum',['RSI','MACD','STOCHASTIC']),
            ('Estructura',['HIGHEST','LOWEST','ATR','CCI'])]
    for number,(label,indicators) in enumerate(groups,1):
        config=dict(symbol='EURUSD',timeframe='30m',search_mode='genetic',objective='tn_score',
            enabled_indicators=indicators,enabled_operators=['GREATER_THAN','LESS_THAN','CROSS_ABOVE',
                'CROSS_BELOW','PRICE_ABOVE','PRICE_BELOW'],enabled_entry_types=['MARKET'],
            enabled_exit_modes=['ATR_CLASSIC','TRAILING_ATR','BREAKEVEN'],
            min_indicators_per_strategy=1,max_indicators_per_strategy=2,infinite_mode=False,
            population_size=40,generations=4,parallel_workers=0,holdout_pct=20,
            initial_deposit=4989.44,sizing_mode='FIXED_RISK',risk_per_trade_pct=.1,
            averaging_config={'enabled':False},max_consecutive_wins=0,max_consecutive_losses=0,
            max_daily_trades=4,max_open_trades=1,close_before_weekend=True,
            prop_firm_filter=False,validate_during_exploration=False,modeling_mode='ohlc',
            spread_pips=1,slippage_pips=.2,min_win_rate=45,min_trades=20,
            min_profit_factor=1.15,min_sharpe=.5,min_dsr=0,max_drawdown=15,
            min_net_profit_usd=0,max_candidates=30)
        print('SEARCH',number,label,flush=True);api('/api/start-exploration',config)
        deadline=time.time()+240
        while True:
            status=api('/api/status')
            if not status['is_running']:break
            if time.time()>deadline:
                api('/api/stop-exploration',{});raise RuntimeError('Presupuesto de búsqueda agotado')
            time.sleep(2)
        candidates=api('/api/candidates')
        compatible=[c for c in candidates if not store.compatibility(Strategy.from_dict(c['strategy']))]
        compatible.sort(key=lambda c:c['metrics'].get('tn_score',0),reverse=True)
        chosen=compatible[:2]
        if len(chosen)<2:raise RuntimeError(f'{label}: solo {len(chosen)} candidatos compatibles aprobados')
        folder=f'Demo realista · Lote {number} {label}'
        for i,c in enumerate(chosen,1):
            c['strategy']['name']=f'STX Demo L{number}.{i} {label} · EURUSD M30'
            c['demo_search_config']=config
            api('/api/strategy/save',dict(candidate_data=c,folder=folder))
        row=dict(folder=folder,config=config,tested=status['tested_count'],accepted=status['accepted_count'],
            saved=[dict(id=c['strategy']['id'],name=c['strategy']['name'],metrics=c['metrics'],strategy=c['strategy']) for c in chosen])
        report['batches'].append(row);save()
        print('SAVED',folder,[(c['metrics']['tn_score'],c['metrics'].get('holdout')) for c in chosen],flush=True)
    ids=[batch['saved'][0]['id'] for batch in report['batches']]
    result=api('/api/portfolio/create',dict(name='STX · Demo realista · 3 lotes',strategy_ids=ids,
        weights=[1,1,1],risk_budget=.3,folder='Pruebas demo'))
    report['portfolio']=result['portfolio'];report['created']=time.time();save()
    print('PORTFOLIO',result['portfolio']['id'],flush=True)


if __name__=='__main__':main()

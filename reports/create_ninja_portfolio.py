"""Bounded genetic searches, durable saves and ordinary portfolio API creation."""
import json,time,urllib.request
from pathlib import Path
import pandas as pd
from backend.strategy import Strategy
from backend.backtester import Backtester
from backend import copy_trading as store

def api(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:8000'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=90) as response:return json.load(response)

def main():
    original=json.loads(Path('reports/ninja_new_genetic_candidates.json').read_text(encoding='utf-8'))
    report={'searches':[],'saved':[]}
    for symbol,contract,indicators,entry,exit in [
        ('NASDAQ','MNQ DEC26',['MACD','EMA'],'MARKET','ATR_CLASSIC'),
        ('US30','MYM DEC26',['EMA','SMA','ADX'],'LIMIT','TRAILING_ATR'),
        ('XAUUSD','MGC DEC26',['RSI','CCI','ATR'],'STOP','BREAKEVEN')]:
        if symbol=='NASDAQ':candidates=original['candidates'];config=original['config']
        else:
            config=dict(original['config'],symbol=symbol,enabled_indicators=indicators,enabled_entry_types=[entry],enabled_exit_modes=[exit],population_size=50,generations=5)
            api('/api/start-exploration',config)
            deadline=time.time()+240
            while api('/api/status')['is_running']:
                if time.time()>deadline:api('/api/stop-exploration',{});raise RuntimeError('Búsqueda agotó su tiempo')
                time.sleep(2)
            candidates=api('/api/candidates')
        candidates=[c for c in candidates if not store.compatibility(Strategy.from_dict(c['strategy']))]
        if not candidates:raise RuntimeError(symbol+': no hubo candidatos aprobados; no se bajan los filtros')
        native_path=Path('reports/ninja_symbols_audit.json')
        native=json.loads(native_path.read_text()).get(contract) if native_path.exists() else None
        frame=None
        if native:
            frame=pd.DataFrame(native['bars']);frame.index=pd.to_datetime(frame.pop('time'),unit='s');frame=frame.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','tick_volume':'Volume'})
        def rank(c):
            signal=False
            if frame is not None:
                buy,sell=Backtester().generate_signal_arrays(frame,Strategy.from_dict(c['strategy']))
                signal=bool(buy[-1])!=bool(sell[-1])
            return (c['metrics'].get('holdout',{}).get('net_profit',0)>0,signal,c['metrics'].get('tn_score',0))
        chosen=max(candidates,key=rank)
        chosen=json.loads(json.dumps(chosen));chosen['strategy']['name']=f'STX Portfolio · {symbol} · {chosen["strategy"]["entry_order_type"]} · {chosen["strategy"]["exit_mode"]}'
        chosen['demo_search_config']=config
        chosen['demo_notes']='Prueba de integración en microfuturo con mapeo explícito. Métricas del histórico del símbolo fuente, no certificación del contrato micro.'
        api('/api/strategy/save',dict(candidate_data=chosen,folder='Demo Ninja - Portfolio multisymbol'))
        report['searches'].append(dict(symbol=symbol,contract=contract,approved=len(candidates),config=config,candidates=candidates))
        report['saved'].append(dict(id=chosen['strategy']['id'],contract=contract,strategy=chosen['strategy'],metrics=chosen['metrics'],rank=rank(chosen)))
        Path('reports/ninja_portfolio_created.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print('SAVED',symbol,chosen['strategy']['id'],chosen['metrics']['tn_score'],'rank',rank(chosen),flush=True)
    result=api('/api/portfolio/create',dict(name='STX · Demo Ninja · 3 símbolos',strategy_ids=[c['id'] for c in report['saved']],weights=[1,1,1],risk_budget=3,folder='Demo Ninja'))
    report['portfolio']=result['portfolio']
    Path('reports/ninja_portfolio_created.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('PORTFOLIO',result['portfolio']['id'],flush=True)

if __name__=='__main__':main()

"""Regression coverage for publication boundaries, snapshots and risk analytics."""
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.api import app, ExplorationConfigRequest
from backend.genetic_engine import genetic_engine, MACRO_INDICATORS
from backend.macro_manager import MacroManager, FRED_CATALOG
from backend.portfolio import Portfolio
from backend.workspace_features import RiskRequest, portfolio_risk


def test_publication_alignment_intraday_and_no_future_fill(tmp_path):
    manager = MacroManager(str(tmp_path))
    data = pd.Series([100., 120.], index=pd.to_datetime(['2024-01-01', '2024-02-01']), name='CPIAUCSL')
    bars = pd.to_datetime(['2024-01-01 00:00', '2024-02-14 08:29', '2024-02-14 08:30', '2024-02-14 09:00', '2024-03-12 08:30'])
    actual = manager.align_to_index(data, bars, published_at=pd.to_datetime(['2024-02-14 08:30','2024-03-12 08:30']))
    assert actual.iloc[:2].isna().all()
    assert actual.iloc[2:].tolist() == [100.,100.,120.]
    naive = data.reindex(bars, method='ffill')
    assert naive.iloc[1] == 120.  # The naive alignment leaks February's observation.
    delayed = manager.align_to_index(data, pd.to_datetime(['2024-01-02 00:00','2024-01-03 00:00','2024-01-03 12:00']), lag_days=2)
    assert np.isnan(delayed.iloc[0])
    assert delayed.iloc[1:].tolist() == [100., 100.]


def test_catalog_and_defaults():
    assert len(FRED_CATALOG) == 29
    assert len({x['category'] for x in FRED_CATALOG.values()}) == 14
    assert set(MACRO_INDICATORS) == {f'MACRO_{s}' for s in FRED_CATALOG}
    cfg = ExplorationConfigRequest()
    assert (cfg.min_sharpe, cfg.max_drawdown, cfg.min_win_rate, cfg.min_dsr) == (1.2,15.,50.,.3)


def test_empty_portfolio_does_not_fabricate_equity():
    result = Portfolio('Empty', []).get_detailed_equity_data()
    assert result['combined_curve'] == []
    assert result['data_status'] == 'unavailable'


def test_sessions_editor_and_paths(tmp_path, monkeypatch):
    import backend.workspace_features as features
    monkeypatch.setattr(features, 'ROOT', tmp_path)
    client = TestClient(app)
    assert not genetic_engine.is_running
    original = genetic_engine.get_candidates()
    config = getattr(genetic_engine, 'last_config', {})
    try:
        result = client.post('/api/sessions', json={'name':'Test', 'config':{'symbol':'EURUSD'},'ui_state':{'fields':[]}})
        assert result.status_code == 200, result.text
        key = result.json()['id']
        assert client.get('/api/sessions').json()[0]['id'] == key
        assert client.patch(f'/api/sessions/{key}', json={'name':'Renamed'}).json()['name'] == 'Renamed'
        assert client.post(f'/api/sessions/{key}/open').status_code == 200
        for text in ['first', 'second']:
            assert client.post('/api/editor/strategy_1/versions',json={'source':text,'language':'python'}).status_code == 200
        history=client.get('/api/editor/strategy_1/versions').json()
        assert [x['source'] for x in history] == ['first','second']
        assert client.get('/api/editor/bad.id/versions').status_code == 400
        assert client.delete(f'/api/sessions/{key}').status_code == 200
        assert client.get(f'/api/sessions/{key}').status_code == 404
    finally:
        genetic_engine.candidates_passed=original
        genetic_engine.last_config=config


def test_portfolio_risk_is_reproducible_and_handles_constant_component():
    days=pd.date_range('2024-01-01',periods=30)
    returns=np.array([.01,-.02,.005,.01,-.005]*6)
    def component(key, rs):
        return {'strategy':{'id':key,'name':key},'equity_curve':[{'time':str(t),'equity':float(e)} for t,e in zip(days,10000*np.cumprod(1+rs))]}
    portfolio=Portfolio('Test',[component('a',returns),component('b',returns),component('c',np.zeros(30))])
    risk=portfolio_risk(portfolio,RiskRequest(simulations=100))
    assert abs(risk['correlation'][0][1]-1)<1e-10
    assert risk['correlation'][0][2] is None
    assert risk['terminal_equity'] == portfolio_risk(portfolio,RiskRequest(simulations=100))['terminal_equity']
    assert risk['terminal_equity']['p5'] <= risk['terminal_equity']['p50'] <= risk['terminal_equity']['p95']


def test_macro_exploration_and_averaging_smoke(monkeypatch):
    from backend.data_manager import data_manager
    from backend.macro_manager import macro_manager
    from backend.genetic_engine import GeneticEngine
    from backend.strategy import Strategy, Condition
    from backend.backtester import backtester
    index=pd.date_range('2024-01-01',periods=240,freq='h')
    prices=1.1 + np.arange(240)*.00005 + .001*np.sin(np.arange(240)/3)
    bars=pd.DataFrame({'Open':prices,'Close':prices+.00002,'High':prices+.0003,'Low':prices-.0003,'Volume':1000},index=index)
    monkeypatch.setattr(data_manager,'load_data',lambda *args,**kwargs:bars.copy())
    monkeypatch.setattr(macro_manager,'load_series',lambda sid:pd.Series([20.],index=pd.to_datetime(['2023-12-01']),name=sid))
    engine=GeneticEngine()
    engine.start_exploration({'search_mode':'random','num_combinations':4,'population_size':4,
                             'infinite_mode':False,'enabled_indicators':[],
                             'use_macro':True,'macro_series':['VIXCLS'],
                             'validate_during_exploration':False})
    engine._thread.join(timeout=15)
    assert not engine.is_running
    assert engine.tested_count == 4, engine.log_messages
    assert not any('Error en la exploración' in line for line in engine.log_messages)
    strategy=Strategy(direction='LONG_ONLY',buy_conditions=[Condition('RSI',{'period':2},'GREATER_THAN','value',target_value=0)],
                      exit_mode='TIME_EXIT',max_bars=20,sl_atr=100,tp_atr=100,
                      avg_enabled=True,avg_mode='both',avg_max_levels=2,
                      avg_spacing_unit='percent',avg_spacing_value=.001,
                      max_daily_loss_pct=0,max_weekly_loss_pct=0,max_monthly_loss_pct=0,max_account_loss_pct=0)
    restored=Strategy.from_dict(strategy.to_dict())
    assert restored.avg_enabled and restored.avg_mode=='both'
    result=backtester.run_backtest(restored,bars)
    assert any(t.get('averaged_levels',0)>0 for t in result.trades)

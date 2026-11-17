import random
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from backend.api import app
from backend.exploration_policy import normalize_config,ACCOUNT_LIMITS
from backend.genetic_engine import GeneticEngine
from backend.mt5_worker import MT5Worker,MarketDataUnavailable
from backend import mt5_diagnostic as diagnostic,copy_trading as store
from test_copy_trading import isolated_store,account,deployment,FakeMT5


def test_propfirm_off_cannot_randomize_account_limits_back_on():
    config=normalize_config(dict(enabled_indicators=['RSI'],prop_firm_filter=False,max_daily_loss_pct=3,max_account_gain_pct=10))
    assert all(config[field]==0 for field in ACCOUNT_LIMITS)
    for seed in range(5):
        s=GeneticEngine().create_random_strategy('EURUSD','1h',['RSI'],['MARKET'],['ATR_CLASSIC'],rng=random.Random(seed))
        assert all(getattr(s,field)==0 for field in ACCOUNT_LIMITS)
        assert not any('Pérdida máxima' in line for line in s.to_human_description()['risk_rules'])


def test_propfirm_single_source_for_loss_and_target():
    config=normalize_config(dict(prop_firm_filter=True,prop_firm_daily_loss_pct=4,prop_firm_total_dd_pct=8,prop_firm_target_pct=9,max_daily_loss_pct=99))
    assert (config['max_daily_loss_pct'],config['max_account_loss_pct'],config['max_account_gain_pct'])==(4,8,9)
    assert config['max_weekly_loss_pct']==config['max_monthly_gain_pct']==0
    s=GeneticEngine().create_random_strategy('EURUSD','1h',['RSI'],['MARKET'],['ATR_CLASSIC'],prop_firm_filter=True,risk_rules=config)
    assert s.max_daily_loss_pct==4 and s.max_account_loss_pct==8 and s.max_account_gain_pct==9


def test_explicit_averaging_off_and_zero_streak_caps_survive_generation(monkeypatch):
    from backend.indicator_audit import sample_frame
    from backend import genetic_engine as module
    engine=GeneticEngine();observed=[]
    original=engine.create_random_strategy
    def capture(*args,**kwargs):
        observed.append(dict(kwargs['risk_rules']))
        result=original(*args,**kwargs)
        assert not result.avg_enabled
        assert result.max_consecutive_wins==result.max_consecutive_losses==0
        return result
    monkeypatch.setattr(engine,'create_random_strategy',capture)
    monkeypatch.setattr(module.data_manager,'load_data',lambda *args,**kwargs:sample_frame())
    engine._run_exploration_worker(dict(symbol='EURUSD',timeframe='1h',infinite_mode=False,
        search_mode='genetic',population_size=4,generations=1,enabled_indicators=['RSI'],
        enabled_entry_types=['MARKET'],enabled_exit_modes=['ATR_CLASSIC'],
        averaging_config={'enabled':False},max_consecutive_wins=0,max_consecutive_losses=0,
        validate_during_exploration=False),None)
    assert len(observed)==4
    assert all(r['max_consecutive_wins']==r['max_consecutive_losses']==0 for r in observed)


def test_fred_not_available_in_new_exploration():
    assert 'use_macro' not in normalize_config({'use_macro':True,'macro_series':['VIXCLS']})
    with pytest.raises(ValueError,match='FRED'):
        GeneticEngine().start_exploration({'enabled_indicators':['MACRO_VIXCLS']})
    client=TestClient(app)
    assert client.get('/api/macro-series').status_code==404
    assert client.post('/api/start-exploration',json={'enabled_indicators':['MACRO_VIXCLS']}).status_code==422


def test_stale_quote_waits_without_failing_or_restarting_an_open_case(monkeypatch):
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    d['source_type']='diagnostic';store.put('deployment',d['id'],d)
    state=dict(index=2,phase='WAIT',opening_ticket=44,audit_complete=True,results=[])
    store.put('diagnostic',d['id'],state)
    def unavailable(*args): raise MarketDataUnavailable('Cotización obsoleta: EURUSDm')
    monkeypatch.setattr(diagnostic,'run',unavailable)
    worker.cycle()
    assert store.get('diagnostic',d['id'])==state
    assert not fake.sent


def test_account_profit_target_pauses_at_threshold_only():
    worker=MT5Worker(FakeMT5(),account());d=deployment()
    d.update(max_daily_loss_pct=0,max_drawdown_pct=0,max_account_gain_pct=8,initial_equity=10000)
    assert worker.risk_allowed(d,NS(equity=10799))
    assert not worker.risk_allowed(d,NS(equity=10800))


@pytest.mark.parametrize('enabled',[False,True])
def test_api_uses_same_propfirm_switch_for_filter_and_account_limits(monkeypatch,enabled):
    from backend.api import genetic_engine
    captured=[]
    monkeypatch.setattr(genetic_engine,'start_exploration',lambda config:captured.append(config))
    response=TestClient(app).post('/api/start-exploration',json=dict(prop_firm_filter=enabled,
        prop_firm_daily_loss_pct=3,prop_firm_total_dd_pct=7,prop_firm_target_pct=9,max_daily_loss_pct=99))
    assert response.status_code==200,response.text
    config=captured[0]
    assert config['max_daily_loss_pct']==(3 if enabled else 0)
    assert config['max_account_loss_pct']==(7 if enabled else 0)
    assert config['max_account_gain_pct']==(9 if enabled else 0)


def test_stale_quote_before_sending_can_retry_entry_without_claiming_an_order(monkeypatch):
    fake=FakeMT5();worker=MT5Worker(fake,account());d=deployment()
    d['source_type']='diagnostic';store.put('deployment',d['id'],d)
    store.put('diagnostic',d['id'],dict(index=0,phase='WAIT',audit_complete=True,results=[]))
    def unavailable(*args): raise MarketDataUnavailable('Cotización obsoleta')
    monkeypatch.setattr(diagnostic,'run',unavailable)
    worker.cycle()
    assert store.get('diagnostic',d['id'])['phase']=='OPEN'
    with store.connect() as db: assert db.execute('SELECT COUNT(*) FROM actions').fetchone()[0]==0

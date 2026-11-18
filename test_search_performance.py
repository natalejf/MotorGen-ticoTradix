import random
import threading
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backend.indicators import IndicatorEngine
from backend.genetic_engine import GeneticEngine
from backend.indicator_audit import sample_frame


def test_full_ranking_replacement_does_not_deadlock_status_or_stop():
    from backend.strategy import Strategy,Condition
    engine=GeneticEngine();errors=[]
    result=SimpleNamespace(equity_curve=[],trades=[])
    def replace():
        try:
            for i in range(2):
                strategy=Strategy(buy_conditions=[Condition('RSI',{},'LESS_THAN',target_value=30+i)])
                metrics=dict(total_trades=30,total_return_usd=100+i,max_drawdown_pct=2,win_rate_pct=60,tn_score=70+i,sharpe_ratio=1)
                engine._ingest_result(strategy,result,metrics,True,'tn_score',1,1,i,2)
        except Exception as error:errors.append(error)
    thread=threading.Thread(target=replace,daemon=True);thread.start();thread.join(3)
    assert not thread.is_alive(),'Replacing a full ranking deadlocked inside logging'
    assert not errors
    assert engine.get_status()['candidates_count']==1
    assert engine.get_candidates()[0]['metrics']['tn_score']==71
    engine.stop_exploration()


@pytest.mark.parametrize('period',[2,9,21,80])
def test_vector_wma_matches_original_rolling_calculation(period):
    values=pd.Series(np.random.default_rng(17).normal(size=300))
    values.iloc[60]=np.nan;values.iloc[170]=np.inf
    weights=np.arange(1,period+1)
    expected=values.rolling(period).apply(lambda x:np.dot(x,weights)/weights.sum(),raw=True)
    pd.testing.assert_series_equal(IndicatorEngine().wma(values,period),expected,rtol=1e-12,atol=1e-12)


@pytest.mark.parametrize('period',[2,9,21,80])
def test_vector_rci_matches_original_including_ties_and_missing_values(period):
    values=pd.Series(np.random.default_rng(21).integers(0,7,size=300).astype(float))
    values.iloc[100]=np.nan;values.iloc[200]=np.inf
    def original(chunk):
        order=np.argsort(-chunk);ranks=np.empty_like(order);ranks[order]=np.arange(1,len(chunk)+1)
        return (1-6*np.sum((ranks-np.arange(1,len(chunk)+1))**2)/(len(chunk)*(len(chunk)**2-1)))*100
    expected=values.rolling(period).apply(original,raw=True).fillna(0.)
    pd.testing.assert_series_equal(IndicatorEngine().rci(values,period),expected,rtol=1e-12,atol=1e-12)


def test_first_candidate_is_published_before_batch_finishes(monkeypatch):
    from backend.data_manager import data_manager
    monkeypatch.setattr(data_manager,'load_data',lambda *a,**k:sample_frame())
    engine=GeneticEngine();original=engine._evaluate_batch
    second=threading.Event();release=threading.Event();sizes=[]
    def batch(population,*args,**kwargs):
        sizes.append(len(population))
        if len(sizes)==2:
            second.set();assert release.wait(8)
        return original(population,*args,**kwargs)
    monkeypatch.setattr(engine,'_evaluate_batch',batch)
    engine.start_exploration(dict(search_mode='random',infinite_mode=False,num_combinations=4,population_size=4,
        enabled_indicators=['RSI'],enabled_entry_types=['MARKET'],enabled_exit_modes=['ATR_CLASSIC'],
        validate_during_exploration=False))
    try:
        assert second.wait(8)
        assert engine.get_status()['tested_count']==1
        assert sizes==[1,1]
    finally:
        release.set();engine._thread.join(10)
    assert not engine.is_running and engine.tested_count==4


def test_only_explicit_equality_selection_still_works_and_is_not_forced_elsewhere():
    engine=GeneticEngine();engine.enabled_operators=['EQUAL_TO']
    assert engine.create_random_condition(['RSI'],True,random.Random(1)).operator=='EQUAL_TO'
    engine.enabled_operators=['EQUAL_TO','GREATER_THAN','LESS_THAN','CROSS_ABOVE']
    choices=[engine.create_random_condition(['RSI'],True,random.Random(seed)).operator for seed in range(300)]
    assert 0<choices.count('EQUAL_TO')<30

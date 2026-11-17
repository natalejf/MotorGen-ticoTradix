import random
import numpy as np
import pandas as pd
import pytest

from backend.indicator_audit import audit_frame,sample_frame
from backend.indicators import indicator_engine
from backend.backtester import Backtester
from backend.genetic_engine import GeneticEngine
from backend.strategy import Condition
from backend.operators import validate_selection


def test_all_32_indicators_and_200_compatible_rule_pairs_are_causal():
    report=audit_frame(sample_frame())
    assert report['indicators']==32
    assert report['checks']==200
    assert report['failed']==0,[r for r in report['results'] if r['status']=='FAIL']


def test_unknown_rules_reject_and_missing_macro_never_triggers():
    b=Backtester();frame=sample_frame()
    for c in (Condition('inventado',{},'GREATER_THAN'),Condition('RSI',{},'inventado')):
        with pytest.raises(ValueError): b.evaluate_condition(frame,c,True)
    for op in ('LESS_THAN','GREATER_THAN','EQUAL_TO','CROSS_BOTH'):
        assert not b.evaluate_condition(frame,Condition('MACRO_MISSING',{},op,target_value=50),True).any()


def test_target_dema_uses_dema_and_swept_parameters_are_effective():
    b=Backtester();frame=sample_frame()
    condition=Condition('PRICE',{},'GREATER_THAN','indicator',target_indicator='DEMA',target_params={'period':19})
    expected=(frame.Close>indicator_engine.dema(frame.Close,19)).values
    np.testing.assert_array_equal(b.evaluate_condition(frame,condition,True),expected)
    kama=Condition('KAMA',{'period':10,'fast':5,'slow':40},'GREATER_THAN')
    np.testing.assert_allclose(b._evaluate_condition_raw(frame,kama,True,True),indicator_engine.kama(frame.Close,10,5,40))
    ichi=Condition('ICHIMOKU',{'tenkan_p':7,'kijun_p':20,'span_b_p':40,'sub':'kijun'},'GREATER_THAN')
    np.testing.assert_allclose(b._evaluate_condition_raw(frame,ichi,True,True),frame.Close-indicator_engine.ichimoku(frame,7,20,40)['kijun'])


def test_cache_distinguishes_high_volume_macro_and_timestamps():
    frame=sample_frame();base=indicator_engine.df_fingerprint(frame)
    for column in ('High','Volume'):
        altered=frame.copy();altered.loc[altered.index[11],column]+=100
        assert indicator_engine.df_fingerprint(altered)!=base
    shifted=frame.copy();shifted.index+=pd.Timedelta('1h')
    assert indicator_engine.df_fingerprint(shifted)!=base
    macro=frame.assign(MACRO_X=1.)
    assert indicator_engine.df_fingerprint(macro)!=indicator_engine.df_fingerprint(macro.assign(MACRO_X=2.))


def test_selected_operators_are_respected_by_generation_and_mutation():
    engine=GeneticEngine();engine.enabled_operators=['EQUAL_TO']
    for seed in range(15):
        c=engine.create_random_condition(['RSI','SMA','MACD'],True,random.Random(seed))
        assert c.operator=='EQUAL_TO'
    engine.enabled_operators=['PRICE_ABOVE']
    assert engine.create_random_condition(['SMA'],True,random.Random(1)).operator=='PRICE_ABOVE'
    with pytest.raises(ValueError):validate_selection(['RSI'],['BULLISH'])
    with pytest.raises(ValueError):validate_selection(['RSI'],[])
    with pytest.raises(ValueError):validate_selection(['RSI'],['UNKNOWN'])


def test_pivots_do_not_backfill_the_first_bar_from_the_future():
    frame=sample_frame()
    pivots=indicator_engine.pivot_points(frame)
    assert np.isnan(pivots['pp'].iloc[0])
    assert pivots['pp'].iloc[1]==pytest.approx((frame.High.iloc[0]+frame.Low.iloc[0]+frame.Close.iloc[0])/3)


def test_indicator_warmup_never_uses_future_atr_or_ichimoku_values():
    frame=sample_frame()
    assert indicator_engine.atr(frame,14).iloc[:13].isna().all()
    ichimoku=indicator_engine.ichimoku(frame)
    assert ichimoku['kijun'].iloc[:25].isna().all()
    assert ichimoku['span_b'].iloc[:77].isna().all()


def test_combined_rules_use_and_and_respect_direction():
    from backend.strategy import Strategy
    frame=sample_frame();b=Backtester()
    a=Condition('RSI',{'period':14},'GREATER_THAN',target_value=40)
    c=Condition('SMA',{'period':20},'PRICE_ABOVE')
    strategy=Strategy(direction='LONG_ONLY',buy_conditions=[a,c],sell_conditions=[a],
        close_before_weekend=False,no_new_trades_friday=False,no_monday_open=False,avoid_rollover=False)
    buys,sells=b.generate_signal_arrays(frame,strategy)
    np.testing.assert_array_equal(buys,b.evaluate_condition(frame,a,True)&b.evaluate_condition(frame,c,True))
    assert not sells.any()

"""Deterministic functional audit. A PASS says nothing about expected returns."""
import random
import numpy as np
import pandas as pd

from backend.backtester import Backtester
from backend.genetic_engine import GeneticEngine, ALL_28_INDICATORS
from backend.operators import compatible, OPERATORS


def sample_frame():
    rng=np.random.default_rng(8241)
    close=1.1+np.cumsum(rng.normal(0,.0005,360))
    return pd.DataFrame(dict(Open=close-.0001,High=close+.0007,Low=close-.0006,Close=close,
        Volume=rng.integers(100,5000,len(close))),index=pd.date_range('2025-01-01',periods=len(close),freq='h'))


def audit_frame(frame):
    engine=GeneticEngine();backtester=Backtester();results=[]
    cutoff=len(frame)-20
    if cutoff<100: raise ValueError('Se requieren al menos 120 velas')
    prefix=frame.iloc[:cutoff].copy()
    for name in ALL_28_INDICATORS:
        for operator in sorted(compatible(name)):
            engine.enabled_operators=[operator]
            try:
                condition=engine.create_random_condition([name],True,random.Random(52))
                full=backtester.evaluate_condition(frame,condition,True)
                before=backtester.evaluate_condition(prefix,condition,True)
                series=backtester._evaluate_condition_raw(frame,condition,True,return_indicator=True)
                short=backtester._evaluate_condition_raw(frame.iloc[:30].copy(),condition,True,return_indicator=True)
                # Trend flags return bool directly; shape still must match the input.
                valid=(len(full)==len(frame) and full.dtype==np.bool_ and np.array_equal(full[:cutoff],before)
                    and np.allclose(np.asarray(series)[:30],np.asarray(short),equal_nan=True))
                finite=np.isfinite(np.asarray(series)[-min(100,len(frame)):]).all()
                results.append(dict(indicator=name,operator=operator,status='PASS' if valid and finite else 'FAIL',
                    signals=int(full.sum()),constant=bool(full.all() or not full.any()),condition=condition.to_dict()))
            except Exception as error:
                results.append(dict(indicator=name,operator=operator,status='FAIL',error=str(error)))
    return dict(indicators=len(ALL_28_INDICATORS),checks=len(results),passed=sum(r['status']=='PASS' for r in results),
        failed=sum(r['status']=='FAIL' for r in results),results=results,
        meaning='Valida cálculo, evaluación y estabilidad al añadir velas futuras; no rentabilidad ni equivalencia numérica con MT5/TradingNote.')


def install_routes(app):
    @app.get('/api/rule-operators')
    def catalog():
        return dict(operators=OPERATORS,compatibility={i:sorted(compatible(i)) for i in ALL_28_INDICATORS})

    @app.post('/api/indicator-audit')
    def synthetic_audit():
        return dict(dataset='synthetic',**audit_frame(sample_frame()))

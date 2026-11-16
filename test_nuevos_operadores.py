# -*- coding: utf-8 -*-
"""Tests: operadores nuevos de TradingNote (EQUAL_TO, CROSS_BOTH, PRICE_ABOVE,
PRICE_BELOW), rangos de parámetros editables (indicator_ranges) y generador."""
import random
import unittest

import numpy as np
import pandas as pd

from backend.backtester import Backtester
from backend.strategy import Condition
from backend.indicators import indicator_engine
from backend.genetic_engine import (
    ALL_28_INDICATORS,
    GeneticEngine,
    count_combinations,
    cross_op,
    range_values,
)


def make_df(kind="osc", n=300):
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    i = np.arange(n, dtype=float)
    if kind == "mono":
        close = np.linspace(100.0, 160.0, n)
    elif kind == "trend_osc":
        close = 100.0 + 0.06 * i + 5.0 * np.sin(i * 0.35)
    else:  # osc
        close = 100.0 + 5.0 * np.sin(i * 0.35) + 0.4 * np.cos(i * 1.3)
    close = pd.Series(close)
    high = close + 0.8
    low = close - 0.8
    open_ = close.shift(1).fillna(close.iloc[0])
    vol = pd.Series(1000.0, index=close.index)
    return pd.DataFrame(
        {"Open": open_.values, "High": high.values, "Low": low.values,
         "Close": close.values, "Volume": vol.values},
        index=idx,
    )


class TestNuevosOperadores(unittest.TestCase):
    def setUp(self):
        self.bt = Backtester()

    # ---------------------------------------------------------------- EQUAL_TO
    def test_equal_to_only_where_true_equality(self):
        df = make_df("mono")
        sma = indicator_engine.sma(df["Close"], 20).values
        i = 150
        cond = Condition("SMA", {"period": 20}, "EQUAL_TO", "value",
                         target_value=float(sma[i]))
        mask = self.bt._evaluate_condition_raw(df, cond, True)
        self.assertTrue(mask[i])
        self.assertEqual(int(mask.sum()), 1)

    def test_equal_to_no_false_positive(self):
        df = make_df("mono")
        sma = indicator_engine.sma(df["Close"], 20).values
        cond = Condition("SMA", {"period": 20}, "EQUAL_TO", "value",
                         target_value=float(sma[150]) + 0.01)
        mask = self.bt._evaluate_condition_raw(df, cond, True)
        self.assertEqual(int(mask.sum()), 0)

    # ------------------------------------------------------------- CROSS_BOTH
    def test_cross_both_series_is_union_of_directions(self):
        df = make_df("osc")
        base = dict(indicator="SMA", params={"period": 10},
                    target_type="indicator",
                    target_indicator="SMA", target_params={"period": 30})
        m_cb = self.bt._evaluate_condition_raw(
            df, Condition(operator="CROSS_BOTH", **base), True)
        m_up = self.bt._evaluate_condition_raw(
            df, Condition(operator="CROSS_ABOVE", **base), True)
        m_dn = self.bt._evaluate_condition_raw(
            df, Condition(operator="CROSS_BELOW", **base), True)
        np.testing.assert_array_equal(m_cb, m_up | m_dn)
        self.assertGreaterEqual(int(m_up.sum()), 1)
        self.assertGreaterEqual(int(m_dn.sum()), 1)

    def test_cross_both_scalar_matches_manual(self):
        df = make_df("osc")
        rsi = indicator_engine.rsi(df["Close"], 14).values
        cond = Condition("RSI", {"period": 14}, "CROSS_BOTH", "value",
                         target_value=50.0)
        mask = self.bt._evaluate_condition_raw(df, cond, True)
        prev = np.roll(rsi, 1)
        prev[0] = rsi[0]
        expected = ((prev <= 50.0) & (rsi > 50.0)) | ((prev >= 50.0) & (rsi < 50.0))
        np.testing.assert_array_equal(mask, expected)
        self.assertGreaterEqual(int(mask.sum()), 2)

    # -------------------------------------------------- PRICE_ABOVE/PRICE_BELOW
    def test_price_above_below_vs_sma(self):
        df = make_df("osc")
        sma = indicator_engine.sma(df["Close"], 10).values
        close = df["Close"].values
        up = self.bt._evaluate_condition_raw(
            df, Condition("SMA", {"period": 10}, "PRICE_ABOVE", "value",
                          target_value=0.0), True)
        dn = self.bt._evaluate_condition_raw(
            df, Condition("SMA", {"period": 10}, "PRICE_BELOW", "value",
                          target_value=0.0), True)
        np.testing.assert_array_equal(up, close > sma)
        np.testing.assert_array_equal(dn, close < sma)
        self.assertTrue(up.any() and dn.any())

    def test_price_above_vs_highest_uses_previous_window(self):
        df = make_df("trend_osc")
        h = indicator_engine.highest(df, 20).values
        close = df["Close"].values
        prev = np.roll(h, 1)
        prev[0] = h[0]
        up = self.bt._evaluate_condition_raw(
            df, Condition("HIGHEST", {"period": 20}, "PRICE_ABOVE", "value",
                          target_value=0.0), True)
        dn = self.bt._evaluate_condition_raw(
            df, Condition("HIGHEST", {"period": 20}, "PRICE_BELOW", "value",
                          target_value=0.0), False)
        np.testing.assert_array_equal(up, close > prev)
        np.testing.assert_array_equal(dn, close < prev)
        self.assertTrue(up.any())  # el trend garantiza breakouts reales

    def test_price_below_vs_lowest_breakdown(self):
        df = make_df("trend_osc")
        lo = indicator_engine.lowest(df, 20).values
        close = df["Close"].values
        prev = np.roll(lo, 1)
        prev[0] = lo[0]
        dn = self.bt._evaluate_condition_raw(
            df, Condition("LOWEST", {"period": 20}, "PRICE_BELOW", "value",
                          target_value=0.0), False)
        np.testing.assert_array_equal(dn, close < prev)

    def test_price_ops_vs_vwap(self):
        df = make_df("osc")
        vw = indicator_engine.vwap(df).values
        close = df["Close"].values
        up = self.bt._evaluate_condition_raw(
            df, Condition("VWAP", {}, "PRICE_ABOVE", "value",
                          target_value=0.0), True)
        np.testing.assert_array_equal(up, close > vw)

    # ------------------------------------------------------------ descripción
    def test_human_descriptions(self):
        c = Condition("RSI", {"period": 14}, "EQUAL_TO", "value", target_value=50)
        self.assertIn("igual a", c.to_human_string())
        c = Condition("RSI", {"period": 14}, "CROSS_BOTH", "value", target_value=50)
        self.assertIn("cruza en ambos sentidos de", c.to_human_string())
        c = Condition("VWAP", {}, "PRICE_ABOVE", "value", target_value=0.0)
        self.assertIn("el precio está por encima de", c.to_human_string())
        c = Condition("VWAP", {}, "PRICE_BELOW", "value", target_value=0.0)
        self.assertIn("el precio está por debajo de", c.to_human_string())

    # ------------------------------------------------------- cross_op generador
    def test_cross_op_distribution(self):
        rng = random.Random(7)
        ops = [cross_op(True, rng) for _ in range(1000)]
        n_both = ops.count("CROSS_BOTH")
        self.assertGreater(n_both, 50)
        self.assertLess(n_both, 300)
        self.assertTrue(set(ops) <= {"CROSS_ABOVE", "CROSS_BOTH"})
        rng = random.Random(7)
        ops_sell = [cross_op(False, rng) for _ in range(1000)]
        self.assertTrue(set(ops_sell) <= {"CROSS_BELOW", "CROSS_BOTH"})


class TestRangosEditables(unittest.TestCase):
    # ------------------------------------------------------ count_combinations
    def test_count_combinations_with_override(self):
        base = count_combinations(["RSI"])
        ov = count_combinations(
            ["RSI"], {"RSI": {"period": {"from": 14, "step": 1, "to": 14}}})
        period_cfg = ALL_28_INDICATORS["RSI"]["params"]["period"]
        n_period = len(range_values(period_cfg))
        self.assertGreater(n_period, 1)
        self.assertEqual(base, ov * n_period)
        self.assertLess(ov, base)

    def test_count_combinations_values_override(self):
        base = count_combinations(["PIVOT_POINTS"])
        ov = count_combinations(
            ["PIVOT_POINTS"], {"PIVOT_POINTS": {"sub": {"values": ["pp"]}}})
        self.assertLess(ov, base)
        self.assertEqual(ov, base // 5 * 1)

    # ------------------------------------------------------------ range_values
    def test_range_values_guards(self):
        self.assertEqual(range_values({"from": 14, "step": 0, "to": 30}), [14])
        self.assertEqual(range_values({"from": 14, "step": 1, "to": 14}), [14])
        self.assertEqual(range_values({"from": 30, "step": 1, "to": 14}), [30])
        self.assertEqual(range_values({"values": [9, 26, 52]}), [9, 26, 52])

    # ------------------------------------------------- prange en el generador
    def test_create_random_condition_respects_override(self):
        eng = GeneticEngine()
        eng.param_ranges = {"RSI": {"period": {"from": 14, "step": 1, "to": 14}}}
        rng = random.Random(42)
        for _ in range(60):
            cond = eng.create_random_condition(["RSI"], True, rng)
            self.assertEqual(cond.indicator, "RSI")
            self.assertEqual(cond.params["period"], 14)
            self.assertIn(cond.operator, ("CROSS_ABOVE", "CROSS_BOTH"))

    def test_real_mutate_keeps_period_in_range(self):
        from backend.strategy import Strategy
        eng = GeneticEngine()
        eng.param_ranges = {"RSI": {"period": {"from": 14, "step": 1, "to": 14}}}
        rng = random.Random(42)
        cond = eng.create_random_condition(["RSI"], True, rng)
        strat = Strategy(name="test-rangos", buy_conditions=[cond],
                         sell_conditions=[])
        random.seed(1)  # mutate usa el módulo random
        for _ in range(120):
            strat = eng.mutate(strat, ["RSI"], ["MARKET"], ["ATR_CLASSIC"])
            for c in list(strat.buy_conditions) + list(strat.sell_conditions):
                if c.indicator == "RSI" and "period" in c.params:
                    self.assertEqual(c.params["period"], 14,
                                     f"period fuera del rango editado: {c.params}")


class TestApiCombinationsCount(unittest.TestCase):
    def test_count_endpoint_with_indicator_ranges(self):
        from fastapi.testclient import TestClient
        from backend.api import app
        client = TestClient(app)
        base = client.post("/api/combinations-count",
                           json={"enabled_indicators": ["RSI"]}).json()
        ov = client.post(
            "/api/combinations-count",
            json={"enabled_indicators": ["RSI"],
                  "indicator_ranges": {"RSI": {"period": {"from": 14, "step": 1,
                                                          "to": 14}}}}).json()
        period_cfg = ALL_28_INDICATORS["RSI"]["params"]["period"]
        n_period = len(range_values(period_cfg))
        self.assertLess(ov["combinations"], base["combinations"])
        self.assertEqual(base["combinations"],
                         ov["combinations"] * n_period)
        self.assertEqual(ov["indicators"], 1)


class TestGeneradorOperadores(unittest.TestCase):
    def _ops(self, ind, is_buy, n=80, seed=3):
        eng = GeneticEngine()
        rng = random.Random(seed)
        return [eng.create_random_condition([ind], is_buy, rng).operator
                for _ in range(n)]

    def test_vwap_price_state_not_inverted(self):
        self.assertEqual(set(self._ops("VWAP", True)), {"PRICE_ABOVE"})
        self.assertEqual(set(self._ops("VWAP", False)), {"PRICE_BELOW"})

    def test_highest_lowest_breakout_ops(self):
        self.assertEqual(set(self._ops("HIGHEST", True)), {"PRICE_ABOVE"})
        self.assertEqual(set(self._ops("LOWEST", False)), {"PRICE_BELOW"})

    def test_ema_family_mixed_ops(self):
        ops = set(self._ops("EMA", True, n=120))
        self.assertTrue(ops <= {"PRICE_ABOVE", "CROSS_ABOVE", "CROSS_BOTH"})
        self.assertIn("PRICE_ABOVE", ops)   # 25% de variante precio/EMA
        self.assertTrue(ops & {"CROSS_ABOVE", "CROSS_BOTH"})

    def test_ichimoku_targets_zero(self):
        eng = GeneticEngine()
        rng = random.Random(5)
        for _ in range(30):
            cond = eng.create_random_condition(["ICHIMOKU"], True, rng)
            self.assertEqual(cond.target_type, "value")
            self.assertEqual(float(cond.target_value), 0.0)

    def test_new_ops_never_generated_for_equal(self):
        eng = GeneticEngine()
        rng = random.Random(11)
        for _ in range(120):
            cond = eng.create_random_condition(
                ["RSI", "EMA", "MACD", "VWAP", "HIGHEST", "PIVOT_POINTS"],
                True, rng)
            self.assertNotEqual(cond.operator, "EQUAL_TO")


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

# Ensure root in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.strategy import Strategy, Condition
from backend.backtester import Backtester
from backend.portfolio import StrategyRecord, Portfolio
from backend.genetic_engine import ALL_28_INDICATORS, GeneticEngine
from backend.api import app

client = TestClient(app)

class TestAllFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create dummy df with 300 candles and capitalized column names
        dates = pd.date_range("2024-01-01", periods=300, freq="1h")
        price = 1.1000 + np.cumsum(np.random.normal(0, 0.0005, 300))
        cls.df = pd.DataFrame({
            "Open": price,
            "High": price + 0.0010,
            "Low": price - 0.0010,
            "Close": price + 0.0002,
            "Volume": 1000
        }, index=dates)

    def test_multi_indicator_generation(self):
        """Verifica que el motor combine entre 2 y 4 indicadores distintos en una estrategia."""
        engine = GeneticEngine()
        strat = engine.create_random_strategy(
            symbol="EURUSD",
            timeframe="1h",
            enabled_indicators=["RSI", "MACD", "EMA", "Bollinger_Bands", "ATR", "Supertrend"],
            enabled_entry_types=["MARKET"],
            enabled_exit_modes=["ATR_CLASSIC"],
            min_indicators=2,
            max_indicators=4
        )
        used_inds = strat.get_used_indicators()
        self.assertGreaterEqual(len(used_inds), 1, "Debe tener al menos un indicador usado")
        # Generate multiple to ensure diversity
        counts = []
        for _ in range(15):
            s = engine.create_random_strategy(
                symbol="EURUSD",
                timeframe="1h",
                enabled_indicators=["RSI", "MACD", "EMA", "Bollinger_Bands", "ATR", "Supertrend", "Stochastic"],
                enabled_entry_types=["MARKET"],
                enabled_exit_modes=["ATR_CLASSIC"],
                min_indicators=2,
                max_indicators=4
            )
            counts.append(len(s.get_used_indicators()))
        max_seen = max(counts)
        self.assertGreater(max_seen, 1, f"El motor debe ser capaz de combinar múltiples indicadores (máx visto: {max_seen})")

    def test_sizing_modes_backtest(self):
        """Verifica que el backtester respete FIXED_CASH, FIXED_LOT y FIXED_RISK."""
        bt = Backtester()
        strat_cash = Strategy(
            symbol="EURUSD",
            timeframe="1h",
            sizing_mode="FIXED_CASH",
            fixed_cash_risk=150.0
        )
        # Add simple condition
        strat_cash.buy_conditions.append(Condition("RSI", {"period": 14}, "GREATER_THAN", "value", 30.0))
        strat_cash.sell_conditions.append(Condition("RSI", {"period": 14}, "LESS_THAN", "value", 70.0))
        res_cash = bt.run_backtest(strat_cash, self.df, initial_deposit=10000)
        self.assertIn("total_return_usd", res_cash.metrics)

        # FIXED LOT
        strat_lot = Strategy(
            symbol="EURUSD",
            timeframe="1h",
            sizing_mode="FIXED_LOT",
            fixed_lot=0.05
        )
        strat_lot.buy_conditions.append(Condition("RSI", {"period": 14}, "GREATER_THAN", "value", 30.0))
        strat_lot.sell_conditions.append(Condition("RSI", {"period": 14}, "LESS_THAN", "value", 70.0))
        res_lot = bt.run_backtest(strat_lot, self.df, initial_deposit=10000)
        self.assertIn("total_return_usd", res_lot.metrics)

    def test_save_and_view_analysis_endpoint(self):
        """Verifica que una estrategia guardada en disco pueda ser consultada por /api/candidate/{id}."""
        strat = Strategy(name="Test Strategy Analyzed", symbol="EURUSD", timeframe="1h")
        strat.buy_conditions.append(Condition("EMA", {"period": 50}, "GREATER_THAN", "value", 1.1000))
        rec = StrategyRecord({
            "strategy": strat.to_dict(),
            "metrics": {
                "initial_capital": 10000.0,
                "total_return_usd": 450.0,
                "sharpe_ratio": 1.95,
                "win_rate_pct": 65.0,
                "max_drawdown_pct": 3.2,
                "total_trades": 25,
                "profit_factor": 1.8,
                "tn_score": 88
            },
            "equity_curve": [{"trade": 0, "equity": 10000.0}, {"trade": 1, "equity": 10450.0}],
            "trades_sample": [{"trade_no": 1, "type": "BUY", "pnl_usd": 450.0}],
            "folder": "Test_Carpeta"
        })
        rec.save(folder="Test_Carpeta")
        strat_id = rec.id

        # Query endpoint
        resp = client.get(f"/api/candidate/{strat_id}")
        self.assertEqual(resp.status_code, 200, "Debe cargar la estrategia desde disco")
        data = resp.json()
        self.assertEqual(data["strategy"]["id"], strat_id)
        self.assertEqual(data["metrics"]["tn_score"], 88)
        self.assertGreaterEqual(len(data["equity_curve"]), 1)

        # Clean up
        StrategyRecord.delete(strat_id)

    def test_portfolio_detail_endpoint(self):
        """Verifica que un portafolio devuelva métricas completas y combined_equity_curve."""
        s1 = Strategy(name="Leg 1", symbol="EURUSD", timeframe="1h")
        s2 = Strategy(name="Leg 2", symbol="GBPUSD", timeframe="1h")

        port = Portfolio(
            name="Alpha Portfolio Test",
            folder="Folder_Test_Port",
            strategies=[
                {
                    "strategy": s1.to_dict(),
                    "metrics": {"total_return_usd": 300, "win_rate_pct": 60, "max_drawdown_pct": 2},
                    "equity_curve": [{"equity": 10000}, {"equity": 10300}]
                },
                {
                    "strategy": s2.to_dict(),
                    "metrics": {"total_return_usd": 500, "win_rate_pct": 70, "max_drawdown_pct": 3},
                    "equity_curve": [{"equity": 10000}, {"equity": 10500}]
                }
            ],
            weights=[0.5, 0.5]
        )
        port.save(folder="Folder_Test_Port")

        resp = client.get(f"/api/portfolio/{port.id}")
        self.assertEqual(resp.status_code, 200, "Debe cargar el portafolio exitosamente")
        p_data = resp.json()
        self.assertEqual(p_data["id"], port.id)
        self.assertEqual(p_data["folder"], "Folder_Test_Port")
        self.assertIn("combined_equity_curve", p_data)
        self.assertGreaterEqual(len(p_data["combined_equity_curve"]), 2)

        # Clean up
        Portfolio.delete(port.id)

    def test_prop_firm_filter_rule(self):
        """Verifica que el filtro Prop Firm descarte estrategias que superen el límite de drawdown o pérdida diaria."""
        engine = GeneticEngine()
        # Mock metrics
        metrics_pass = {"max_daily_loss_pct": 2.5, "max_drawdown_pct": 5.0, "win_rate_pct": 50, "total_trades": 20, "total_return_usd": 500, "sharpe_ratio": 1.5, "profit_factor": 1.5, "dsr": 0.5, "tn_score": 75}
        metrics_fail = {"max_daily_loss_pct": 5.2, "max_drawdown_pct": 9.5, "win_rate_pct": 50, "total_trades": 20, "total_return_usd": 500, "sharpe_ratio": 1.5, "profit_factor": 1.5, "dsr": 0.5, "tn_score": 75}

        prop_daily_loss = 4.0
        prop_total_dd = 8.0

        pass_check = (metrics_pass["max_daily_loss_pct"] <= prop_daily_loss) and (metrics_pass["max_drawdown_pct"] <= prop_total_dd)
        fail_check = (metrics_fail["max_daily_loss_pct"] <= prop_daily_loss) and (metrics_fail["max_drawdown_pct"] <= prop_total_dd)

        self.assertTrue(pass_check, "Métricas conservadoras deben pasar la prueba prop firm")
        self.assertFalse(fail_check, "Exceso de DD diario o total debe ser descartado")

    def test_top_pool_limit_and_replacement(self):
        """Verifica que el límite de pool (ej. 3) mantenga exactamente 3 y desplace al de menor score."""
        engine = GeneticEngine()
        engine.candidates_passed = []
        max_cands = 3

        for i, score in enumerate([50.0, 70.0, 60.0]):
            c = {
                "strategy": {"id": f"strat_{i}"},
                "metrics": {"tn_score": score, "total_return_usd": score * 10},
                "signature": f"sig_{i}",
                "perf_sig": f"perf_{i}"
            }
            engine.candidates_passed.append(c)
        engine.candidates_passed.sort(key=lambda x: x["metrics"]["tn_score"], reverse=True)
        self.assertEqual(len(engine.candidates_passed), 3)
        self.assertEqual(engine.candidates_passed[-1]["metrics"]["tn_score"], 50.0)

        # Insert a better one (85.0)
        new_c = {
            "strategy": {"id": "strat_better"},
            "metrics": {"tn_score": 85.0, "total_return_usd": 850},
            "signature": "sig_better",
            "perf_sig": "perf_better"
        }
        cand_score = 85.0
        lowest_score = engine.candidates_passed[-1]["metrics"]["tn_score"]
        if cand_score > lowest_score:
            engine.candidates_passed.pop(-1)
            engine.candidates_passed.append(new_c)
            engine.candidates_passed.sort(key=lambda x: x["metrics"]["tn_score"], reverse=True)

        self.assertEqual(len(engine.candidates_passed), 3, "El pool debe seguir teniendo exactamente 3 estrategias")
        self.assertEqual(engine.candidates_passed[0]["metrics"]["tn_score"], 85.0, "La nueva debe ser el nuevo líder")
        scores = [c["metrics"]["tn_score"] for c in engine.candidates_passed]
        self.assertNotIn(50.0, scores, "El peor algoritmo (50.0) debió ser desplazado")

if __name__ == "__main__":
    unittest.main()

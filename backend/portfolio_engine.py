"""
Portfolio Engine for TradingNote Replica
Automated multi-pair, multi-strategy portfolio generator and genetic optimizer.
Combines saved strategies across different assets/timeframes, optimizes weights,
calculates combined equity curves, diversification indices, and ranks top portfolios in real time.
"""

import time
import math
import random
import threading
from typing import Dict, List, Any, Optional, Set
import numpy as np

from backend.portfolio import StrategyRecord, Portfolio

class PortfolioEngine:
    def __init__(self):
        self.is_running: bool = False
        self.worker_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        # Engine Telemetry
        self.tested_count: int = 0
        self.accepted_count: int = 0
        self.discarded_count: int = 0
        self.generation_step: int = 0
        self.best_portfolio: Optional[Dict[str, Any]] = None
        self.start_time: float = 0.0

        # Live Results Pool
        self.top_portfolios: List[Dict[str, Any]] = []
        self.seen_signatures: Set[frozenset] = set()

        # Configuration
        self.config: Dict[str, Any] = {}

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            elapsed = time.time() - self.start_time if (self.is_running and self.start_time > 0) else 0.0
            return {
                "is_running": self.is_running,
                "tested_count": self.tested_count,
                "accepted_count": self.accepted_count,
                "discarded_count": self.discarded_count,
                "generation_step": self.generation_step,
                "elapsed_seconds": round(elapsed, 1),
                "top_count": len(self.top_portfolios),
                "best_portfolio": self.best_portfolio
            }

    def get_top_portfolios(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.top_portfolios)

    def start_exploration(self, config: Dict[str, Any]):
        if self.is_running:
            self.stop_exploration()
            time.sleep(0.3)

        self.config = config
        self.is_running = True
        self.tested_count = 0
        self.accepted_count = 0
        self.discarded_count = 0
        self.generation_step = 0
        self.top_portfolios = []
        self.seen_signatures = set()
        self.best_portfolio = None
        self.start_time = time.time()

        self.worker_thread = threading.Thread(target=self._run_worker, daemon=True)
        self.worker_thread.start()

    def stop_exploration(self):
        self.is_running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)

    def _calculate_weights(self, strats: List[Dict[str, Any]], mode: str) -> List[float]:
        n = len(strats)
        if n == 0:
            return []
        if mode == "EQUAL" or n == 1:
            return [round(1.0 / n, 4)] * n
        elif mode == "SHARPE":
            sharpes = [max(0.1, float(s.get("metrics", {}).get("sharpe_ratio", 1.0))) for s in strats]
            total_s = sum(sharpes)
            return [round(s / total_s, 4) for s in sharpes]
        elif mode == "PROFIT":
            profits = [max(10.0, float(s.get("metrics", {}).get("total_return_usd", 100.0))) for s in strats]
            total_p = sum(profits)
            return [round(p / total_p, 4) for p in profits]
        else:
            return [round(1.0 / n, 4)] * n

    def _evaluate_candidate(self, strats: List[Dict[str, Any]], weight_mode: str, initial_deposit: float = 10000.0) -> Dict[str, Any]:
        weights = self._calculate_weights(strats, weight_mode)
        n = len(strats)

        # Assets & Timeframes
        symbols_set = set()
        tf_set = set()
        total_pnl = 0.0
        weighted_wr = 0.0
        total_trades = 0

        # Equity curves interpolation
        max_trades = 0
        strat_curves = []

        for idx, it in enumerate(strats):
            s = it.get("strategy", it)
            m = it.get("metrics", {})
            w = weights[idx] if idx < len(weights) else (1.0 / n)

            pnl = float(m.get("total_return_usd", 0.0))
            wr = float(m.get("win_rate_pct", 50.0))
            tr = int(m.get("total_trades", 10))

            total_pnl += pnl * w
            weighted_wr += wr * w
            total_trades += tr

            sym = s.get("symbol", "N/A")
            tf = s.get("timeframe", "1h")
            symbols_set.add(sym)
            tf_set.add(tf)

            curve = it.get("equity_curve", [])
            strat_curves.append((w, curve))
            if curve:
                max_trades = max(max_trades, len(curve))

        # Generate combined curve
        combined_curve = []
        steps = max(20, min(100, max_trades))
        for step_idx in range(steps):
            ratio = step_idx / max(1, steps - 1)
            step_balance = 0.0
            for w, curve in strat_curves:
                if curve:
                    c_idx = min(len(curve) - 1, int(ratio * (len(curve) - 1)))
                    eq = curve[c_idx].get("equity", initial_deposit)
                    step_balance += (eq - initial_deposit) * w
                else:
                    # Synthetic linear growth based on PnL
                    step_balance += (total_pnl * ratio) * w
            combined_curve.append({
                "step": step_idx,
                "equity": round(initial_deposit + step_balance, 2)
            })

        # Calculate Combined Drawdown
        peak = initial_deposit
        max_dd_usd = 0.0
        max_dd_pct = 0.0
        for pt in combined_curve:
            eq = pt["equity"]
            if eq > peak:
                peak = eq
            dd_usd = peak - eq
            dd_pct = (dd_usd / peak) * 100.0 if peak > 0 else 0.0
            if dd_usd > max_dd_usd:
                max_dd_usd = dd_usd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        # Multi-Pair Diversification Score
        num_symbols = len(symbols_set)
        num_timeframes = len(tf_set)
        asset_div = min(1.0, num_symbols / 3.0)
        tf_div = min(1.0, num_timeframes / 2.0)
        strat_div = min(1.0, n / 5.0)
        diversification_score = round((asset_div * 0.45 + tf_div * 0.25 + strat_div * 0.30) * 100, 1)

        # Estimated DD reduction from multi-asset desynchronization
        estimated_dd_red = min(55.0, round(12.0 * num_symbols + 6.0 * strat_div, 1))

        # Combined Sharpe calculation
        returns_arr = np.diff([pt["equity"] for pt in combined_curve]) if len(combined_curve) > 1 else np.array([0.0])
        std = np.std(returns_arr) if len(returns_arr) > 0 else 1.0
        combined_sharpe = round((np.mean(returns_arr) / std) * math.sqrt(252), 2) if std > 1e-6 else 1.0
        if math.isnan(combined_sharpe) or math.isinf(combined_sharpe):
            combined_sharpe = 1.0

        # Holistic TradingNote Portfolio Score (0-100)
        pnl_component = min(35.0, (total_pnl / 3000.0) * 35.0)
        div_component = min(35.0, (diversification_score / 100.0) * 35.0)
        dd_component = max(0.0, 30.0 - (max_dd_pct * 1.5))
        tn_portfolio_score = round(max(10.0, min(100.0, pnl_component + div_component + dd_component)), 1)

        # Sparkline (25 points)
        sparkline = [pt["equity"] for pt in combined_curve[::max(1, len(combined_curve) // 25)]]

        metrics = {
            "combined_net_profit_usd": round(total_pnl, 2),
            "weighted_win_rate_pct": round(weighted_wr, 1),
            "combined_sharpe": combined_sharpe,
            "combined_max_drawdown_pct": round(max_dd_pct, 1),
            "combined_max_drawdown_usd": round(max_dd_usd, 2),
            "diversification_score": diversification_score,
            "estimated_dd_reduction_pct": estimated_dd_red,
            "total_trades": total_trades,
            "strategies_count": n,
            "symbols": sorted(list(symbols_set)),
            "timeframes": sorted(list(tf_set)),
            "tn_score": tn_portfolio_score
        }

        # Human-friendly portfolio name
        symbols_title = " + ".join(sorted(list(symbols_set))) if symbols_set else "Multi-Par"
        port_name = f"Portafolio {symbols_title} ({n} Algoritmos)"

        return {
            "id": f"port_cand_{int(time.time()*1000)}_{random.randint(100, 999)}",
            "name": port_name,
            "weights": weights,
            "metrics": metrics,
            "equity_curve": combined_curve,
            "sparkline": sparkline,
            "strategies": strats,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def _run_worker(self):
        """Background exploration worker testing combinations of saved strategies."""
        # 1. Load source strategies
        raw_items = StrategyRecord.list_all()
        if not raw_items:
            self.is_running = False
            return

        # Filter by requested source if specified
        source_pairs = self.config.get("source_pairs", ["ALL"])
        source_folders = self.config.get("source_folders", ["ALL"])

        pool = raw_items
        if source_pairs and "ALL" not in source_pairs:
            pool = [it for it in pool if (it.get("strategy", it)).get("symbol") in source_pairs]
        if source_folders and "ALL" not in source_folders:
            pool = [it for it in pool if (it.get("folder") in source_folders or it.get("batch_name") in source_folders)]

        if len(pool) < 2:
            # Fall back to all available
            pool = raw_items

        min_strat = max(2, int(self.config.get("min_strategies", 2)))
        max_strat = max(min_strat, min(12, int(self.config.get("max_strategies", 5))))
        weight_mode = self.config.get("weight_mode", "EQUAL")
        objective = self.config.get("objective", "diversification")  # "diversification", "sharpe", "net_profit", "tn_score"
        max_top = max(10, min(500, int(self.config.get("max_portfolios", 50))))
        min_div = float(self.config.get("min_diversification", 25.0))
        min_sharpe = float(self.config.get("min_sharpe", 0.8))

        # Group pool by symbol to favor multi-pair diversity
        by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        for it in pool:
            sym = (it.get("strategy", it)).get("symbol", "N/A")
            by_symbol.setdefault(sym, []).append(it)

        all_symbols = list(by_symbol.keys())

        while self.is_running:
            self.generation_step += 1
            batch_count = 15

            for _ in range(batch_count):
                if not self.is_running:
                    break

                target_size = random.randint(min_strat, min(max_strat, len(pool)))
                candidate_strats: List[Dict[str, Any]] = []

                # Favor picking 1 strategy per distinct symbol first (True Multi-Pair)
                if len(all_symbols) >= 2 and random.random() < 0.75:
                    chosen_symbols = random.sample(all_symbols, min(len(all_symbols), target_size))
                    for sym in chosen_symbols:
                        candidate_strats.append(random.choice(by_symbol[sym]))
                    # If still need more to fill target_size
                    while len(candidate_strats) < target_size:
                        extra = random.choice(pool)
                        if extra not in candidate_strats:
                            candidate_strats.append(extra)
                else:
                    # Random sampling from whole pool
                    candidate_strats = random.sample(pool, target_size)

                # Signature for deduplication: set of strategy IDs
                strat_ids = frozenset((s.get("strategy", s)).get("id") for s in candidate_strats)
                if strat_ids in self.seen_signatures:
                    self.discarded_count += 1
                    continue

                self.seen_signatures.add(strat_ids)
                self.tested_count += 1

                # Evaluate portfolio
                cand = self._evaluate_candidate(candidate_strats, weight_mode=weight_mode)
                m = cand["metrics"]

                # Admission Filters
                passes = (
                    m["diversification_score"] >= min_div and
                    m["combined_sharpe"] >= min_sharpe
                )

                if passes:
                    cand_score = m.get(objective, m.get("tn_score", 0.0))

                    with self.lock:
                        if len(self.top_portfolios) < max_top:
                            self.accepted_count += 1
                            self.top_portfolios.append(cand)
                            self.top_portfolios.sort(
                                key=lambda x: x["metrics"].get(objective, x["metrics"].get("tn_score", 0.0)),
                                reverse=True
                            )
                        else:
                            # Top Pool replacement
                            lowest = self.top_portfolios[-1]
                            lowest_score = lowest["metrics"].get(objective, lowest["metrics"].get("tn_score", 0.0))
                            if cand_score > lowest_score:
                                self.top_portfolios.pop(-1)
                                self.top_portfolios.append(cand)
                                self.top_portfolios.sort(
                                    key=lambda x: x["metrics"].get(objective, x["metrics"].get("tn_score", 0.0)),
                                    reverse=True
                                )
                            else:
                                self.discarded_count += 1

                        if self.best_portfolio is None or cand_score > self.best_portfolio["metrics"].get(objective, self.best_portfolio["metrics"].get("tn_score", 0.0)):
                            self.best_portfolio = cand
                else:
                    self.discarded_count += 1

            # Micro sleep between batches to yield CPU
            time.sleep(0.08)

        self.is_running = False

    def save_portfolio_candidate(self, candidate_id: str, folder: str = "Portafolios_Principales") -> Dict[str, Any]:
        """Saves a top candidate portfolio permanently to disk."""
        with self.lock:
            target = next((p for p in self.top_portfolios if p["id"] == candidate_id), None)
            if not target:
                raise FileNotFoundError(f"Portfolio candidate {candidate_id} not found in live pool")

            port = Portfolio(
                name=target["name"],
                strategies=target["strategies"],
                weights=target["weights"],
                folder=folder
            )
            port.save(folder=folder)
            return port.to_dict()

    def save_all_top(self, folder: str = "Lote_Portafolios_Top") -> List[Dict[str, Any]]:
        """Saves all currently approved top portfolios to disk in a labeled batch/folder."""
        saved = []
        with self.lock:
            for p in self.top_portfolios:
                port = Portfolio(
                    name=p["name"],
                    strategies=p["strategies"],
                    weights=p["weights"],
                    folder=folder
                )
                port.save(folder=folder)
                saved.append(port.to_dict())
        return saved

# Singleton instance
portfolio_engine = PortfolioEngine()

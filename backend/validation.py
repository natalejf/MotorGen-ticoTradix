"""
Validation and Anti-Overfitting Suite for TradingNote Genetic Engine Replica
Implements:
1. Deflated Sharpe Ratio (DSR) based on Bailey & López de Prado (2014)
2. Walk-Forward Analysis (WFA) with concatenated Out-of-Sample (OOS) equity curve
3. Multiverse Simulation (Stationary Block Bootstrap synthetic market universes)
4. Prop Firm Challenge Pass Rate Evaluator
"""

import math
import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Any, Optional, Tuple
from backend.strategy import Strategy
from backend.backtester import backtester, BacktestResult

class ValidationSuite:
    def __init__(self):
        pass

    # =========================================================================
    # 1. DEFLATED SHARPE RATIO (DSR)
    # =========================================================================
    def calculate_dsr(
        self,
        observed_sharpe: float,
        num_trials: int,
        sharpe_variance: float,
        returns: np.ndarray,
        benchmark_sharpe: float = 0.0
    ) -> float:
        """
        Calculates the Deflated Sharpe Ratio (DSR) discounting selection bias under multiple testing.
        Reference: Bailey, D. H., & López de Prado, M. (2014).
        The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality.
        """
        if num_trials <= 1:
            num_trials = 2
        if sharpe_variance <= 1e-6:
            sharpe_variance = 0.25 # Reasonable baseline variance of candidate Sharpes

        n = len(returns)
        if n < 10 or observed_sharpe <= 0:
            return 0.0

        # Calculate Skewness and Kurtosis of returns
        skew = float(stats.skew(returns))
        kurt = float(stats.kurtosis(returns, fisher=False)) # Pearson kurtosis (normal=3)
        if math.isnan(skew):
            skew = 0.0
        if math.isnan(kurt) or kurt < 1.0:
            kurt = 3.0

        # Expected maximum Sharpe under null hypothesis of zero skill (Euler-Mascheroni constant ~ 0.5772)
        euler_mascheroni = 0.5772156649
        sqrt_2_ln_n = np.sqrt(2.0 * np.log(num_trials))
        expected_max_sharpe = float(
            (sqrt_2_ln_n + (euler_mascheroni / sqrt_2_ln_n)) * np.sqrt(sharpe_variance)
        )

        # Standard error of the observed Sharpe ratio under non-normality
        # Var[SR] = (1 - skew*SR + ((kurt - 1)/4)*SR^2) / (n - 1)
        sr_var = (1.0 - (skew * observed_sharpe) + (((kurt - 1.0) / 4.0) * (observed_sharpe ** 2))) / max(n - 1, 1)
        sr_se = np.sqrt(max(sr_var, 1e-6))

        # Z score and CDF
        z = (observed_sharpe - expected_max_sharpe) / sr_se
        dsr_prob = float(stats.norm.cdf(z))
        return round(min(max(dsr_prob, 0.0), 1.0), 3)

    # =========================================================================
    # 2. WALK-FORWARD ANALYSIS (WFA) — validación y reoptimización
    # =========================================================================
    def run_walk_forward(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        n_windows: int = 5,
        test_ratio: float = 0.3,
        mode: str = "validation",  # "validation" | "reoptimization"
        reopt_depth: str = "standard",  # "fast" (5 gen/20 pop) | "standard" (10/30) | "deep" (20/50)
        top_params: Optional[Dict[str, Any]] = None,
        min_wfe: float = 0.5,        # TN default threshold
        min_pass_rate: float = 60.0, # TN default threshold (%)
        min_sharpe_oos: float = 0.5  # TN default threshold
    ) -> Dict[str, Any]:
        """
        Walk-Forward temporal validation.
        mode="validation": same params on every OOS window.
        mode="reoptimization": light genetic recalibration on each train window
          before evaluating OOS (depth: fast/standard/deep).
        """
        n = len(df)
        window_size = int(n / (1.0 + (n_windows - 1) * test_ratio))
        test_size = int(window_size * test_ratio)
        train_size = window_size - test_size

        windows_results = []
        chained_oos_equity = []
        chained_trades = []
        running_oos_balance = 10000.0

        total_is_return = 0.0
        total_oos_return = 0.0
        total_is_sharpe = 0.0
        total_oos_sharpe = 0.0
        param_stability_samples: List[Dict[str, Any]] = []

        step = int((n - window_size) / max(n_windows - 1, 1)) if n_windows > 1 else 0

        # Reoptimization budget
        depth_map = {
            "fast": (5, 20),
            "standard": (10, 30),
            "deep": (20, 50),
        }
        ro_gens, ro_pop = depth_map.get(reopt_depth, depth_map["standard"])

        for w in range(n_windows):
            start_idx = w * step
            train_end_idx = start_idx + train_size
            test_end_idx = min(train_end_idx + test_size, n)

            train_df = df.iloc[start_idx:train_end_idx]
            test_df = df.iloc[train_end_idx:test_end_idx]

            if len(train_df) < 50 or len(test_df) < 20:
                continue

            # Choose strategy for this window
            window_strat = strategy
            if mode == "reoptimization":
                window_strat = self._reoptimize_on_train(strategy, train_df, ro_gens, ro_pop)
                param_stability_samples.append({
                    "window": w + 1,
                    "sl_atr": getattr(window_strat, "sl_atr", None),
                    "tp_atr": getattr(window_strat, "tp_atr", None),
                    "exit_mode": getattr(window_strat, "exit_mode", None),
                    "risk_per_trade_pct": getattr(window_strat, "risk_per_trade_pct", None),
                    "session_filter": getattr(window_strat, "session_filter", None),
                })

            is_res = backtester.run_backtest(window_strat, train_df, initial_deposit=10000.0)
            oos_res = backtester.run_backtest(window_strat, test_df, initial_deposit=running_oos_balance)

            running_oos_balance = oos_res.metrics["final_balance"]
            for eq in oos_res.equity_curve:
                chained_oos_equity.append({
                    "time": eq["time"],
                    "equity": eq["equity"],
                    "window": w + 1
                })
            chained_trades.extend(oos_res.trades)

            is_ret = is_res.metrics["total_return_pct"]
            oos_ret = oos_res.metrics["total_return_pct"]
            is_sh = max(is_res.metrics["sharpe_ratio"], 0.01)
            oos_sh = oos_res.metrics["sharpe_ratio"]

            total_is_return += is_ret
            total_oos_return += oos_ret
            total_is_sharpe += is_sh
            total_oos_sharpe += oos_sh

            # Pass criteria per window (configurable TN defaults: WFE>=0.5, sharpe OOS>=0.5)
            wfe_win = (oos_ret / max(is_ret, 0.1)) if is_ret > 0 else 0.0
            window_passed = (wfe_win >= min_wfe) and (oos_sh >= min_sharpe_oos) and (oos_ret > 0)

            windows_results.append({
                "window": w + 1,
                "is_period": f"{train_df.index[0].date()} to {train_df.index[-1].date()}",
                "oos_period": f"{test_df.index[0].date()} to {test_df.index[-1].date()}",
                "is_return_pct": is_ret,
                "oos_return_pct": oos_ret,
                "is_sharpe": round(is_sh, 2),
                "oos_sharpe": round(oos_sh, 2),
                "is_trades": is_res.metrics["total_trades"],
                "oos_trades": oos_res.metrics["total_trades"],
                "window_wfe": round(wfe_win, 3),
                "passed": bool(window_passed)
            })

        num_valid = len(windows_results)
        if num_valid > 0:
            avg_is_ret = total_is_return / num_valid
            avg_oos_ret = total_oos_return / num_valid
            wfe_return = (avg_oos_ret / max(avg_is_ret, 0.1)) if avg_is_ret > 0 else 0.0
            avg_is_sh = total_is_sharpe / num_valid
            avg_oos_sh = total_oos_sharpe / num_valid
            wfe_sharpe = (avg_oos_sh / avg_is_sh) if avg_is_sh > 0 else 0.0
            overall_wfe = round(min(max(float((wfe_return + wfe_sharpe) / 2.0), 0.0), 1.5), 2)
            pass_rate = round(100.0 * sum(1 for w in windows_results if w.get("passed")) / num_valid, 1)
            sharpe_oos_mean = round(avg_oos_sh, 2)

            # Degradation slope: linear fit of OOS return across windows
            oos_vals = [w["oos_return_pct"] for w in windows_results]
            if num_valid >= 3:
                x = np.arange(num_valid, dtype=float)
                degradation_slope = float(np.polyfit(x, np.array(oos_vals, dtype=float), 1)[0])
            else:
                degradation_slope = 0.0
        else:
            overall_wfe = 0.0
            pass_rate = 0.0
            sharpe_oos_mean = 0.0
            degradation_slope = 0.0

        # Parameter stability (reoptimization mode): lower std = more stable
        param_stability = None
        if mode == "reoptimization" and len(param_stability_samples) >= 2:
            sl_vals = [s["sl_atr"] for s in param_stability_samples if s.get("sl_atr") is not None]
            tp_vals = [s["tp_atr"] for s in param_stability_samples if s.get("tp_atr") is not None]
            if sl_vals and tp_vals:
                param_stability = {
                    "sl_std": round(float(np.std(sl_vals)), 3),
                    "tp_std": round(float(np.std(tp_vals)), 3),
                    "score": round(max(0.0, 100.0 - (float(np.std(sl_vals)) + float(np.std(tp_vals))) * 20.0), 1)
                }

        # TN approval: configurable thresholds (defaults WFE >= 0.5, pass >= 60%, sharpe OOS >= 0.5)
        is_passed = (overall_wfe >= min_wfe and pass_rate >= min_pass_rate and sharpe_oos_mean >= min_sharpe_oos)
        if not is_passed:
            # Legacy softer threshold as fallback signal (10% / 10 pts below the configured minimums)
            is_passed = (overall_wfe >= min_wfe * 0.9 and pass_rate >= max(min_pass_rate - 10.0, 0.0))

        return {
            "passed": is_passed,
            "mode": mode,
            "overall_wfe": overall_wfe,
            "pass_rate_pct": pass_rate,
            "sharpe_oos_mean": sharpe_oos_mean,
            "degradation_slope": round(degradation_slope, 4),
            "param_stability": param_stability,
            "windows": windows_results,
            "chained_oos_equity": chained_oos_equity[::max(1, len(chained_oos_equity)//100)],
            "total_oos_trades": len(chained_trades)
        }

    def _reoptimize_on_train(self, strategy: Strategy, train_df: pd.DataFrame, generations: int, pop_size: int) -> Strategy:
        """Light genetic recalibration of key numeric params on the train window."""
        import copy as _copy
        import random as _random

        best = _copy.deepcopy(strategy)
        best_res = backtester.run_backtest(best, train_df, initial_deposit=10000.0)
        best_fit = best_res.metrics.get("calmar_ratio", 0.0) + 0.5 * best_res.metrics.get("sharpe_ratio", 0.0)

        population = []
        for _ in range(pop_size):
            m = _copy.deepcopy(strategy)
            m.sl_atr = round(_random.uniform(0.5, 3.0), 2)
            m.tp_atr = round(_random.uniform(1.0, 6.0), 2)
            m.trail_atr = round(_random.uniform(0.5, 2.5), 2)
            m.be_atr = round(_random.uniform(0.5, 2.0), 2)
            m.risk_per_trade_pct = round(_random.uniform(0.5, 2.0), 2)
            population.append(m)

        for _ in range(generations):
            scored = []
            for ind in population:
                res = backtester.run_backtest(ind, train_df, initial_deposit=10000.0)
                if res.metrics["total_trades"] < 3:
                    fit = -999
                else:
                    fit = res.metrics.get("calmar_ratio", 0.0) + 0.5 * res.metrics.get("sharpe_ratio", 0.0)
                scored.append((fit, ind))
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored and scored[0][0] > best_fit:
                best_fit = scored[0][0]
                best = _copy.deepcopy(scored[0][1])
            # breed next pop
            elite = [s[1] for s in scored[: max(2, pop_size // 4)]]
            next_pop = [_copy.deepcopy(e) for e in elite]
            while len(next_pop) < pop_size:
                a = _copy.deepcopy(_random.choice(elite))
                b = _random.choice(elite)
                if _random.random() < 0.5:
                    a.sl_atr = b.sl_atr
                if _random.random() < 0.5:
                    a.tp_atr = b.tp_atr
                if _random.random() < 0.3:
                    a.sl_atr = round(max(0.5, a.sl_atr + _random.uniform(-0.3, 0.3)), 2)
                    a.tp_atr = round(max(1.0, a.tp_atr + _random.uniform(-0.5, 0.5)), 2)
                next_pop.append(a)
            population = next_pop

        return best

    # =========================================================================
    # 3. MULTIVERSE SIMULATION (Score 0-100 + regimes + engine presets)
    # =========================================================================
    def run_multiverse(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        n_universes: int = 100,
        engine_preset: str = "balanced",  # "balanced" | "conservative" | "aggressive"
        n_regimes: int = 3,               # 1..4: bull / bear / crisis (+ mixed)
        block_size: Optional[int] = None  # override; default depends on preset
    ) -> Dict[str, Any]:
        """
        Synthetic alternative markets via block bootstrap.
        Classifies each universe into a market regime, runs the strategy,
        and produces a TN-style Robustness Score 0-100:
          Score >= 75 robust | 50-74 moderate | < 50 fragile.
        """
        n = len(df)
        if n < 100:
            return {
                "passed": False, "score": 0.0, "verdict": "FRAGIL",
                "profitable_pct": 0.0, "total_universes": 0, "regimes": {}, "universes": []
            }

        # Engine presets: block size & regime classification sensitivity
        preset_cfg = {
            "conservative": {"block": 48, "min_profitable": 70.0, "score_bonus": -5.0},
            "balanced":     {"block": 24, "min_profitable": 65.0, "score_bonus": 0.0},
            "aggressive":   {"block": 12, "min_profitable": 60.0, "score_bonus": 5.0},
        }
        pcfg = preset_cfg.get(engine_preset, preset_cfg["balanced"])
        bs = int(block_size or pcfg["block"])
        min_profitable = pcfg["min_profitable"]

        n_regimes = max(1, min(4, int(n_regimes)))

        log_ret = np.diff(np.log(df["Close"].values))
        num_blocks = int(np.ceil(len(log_ret) / bs))

        base_open = df["Open"].values[0]
        high_ratio = (df["High"] / df["Close"]).values
        low_ratio = (df["Low"] / df["Close"]).values
        open_ratio = (df["Open"] / df["Close"]).values

        results_pnl = []
        results_drawdown = []
        results_sharpe = []
        regime_buckets: Dict[str, List[float]] = {
            "alcista": [], "bajista": [], "crisis": [], "mixto": []
        }

        regime_names = ["alcista", "bajista", "crisis", "mixto"][:n_regimes]

        for u in range(n_universes):
            sampled_block_starts = np.random.randint(0, len(log_ret) - bs + 1, size=num_blocks)
            synth_returns = np.concatenate([
                log_ret[s: s + bs] for s in sampled_block_starts
            ])[: len(log_ret)]

            synth_close = np.exp(np.cumsum(np.insert(synth_returns, 0, 0.0))) * base_open

            perm = np.random.permutation(n)
            synth_high = synth_close * high_ratio[perm]
            synth_low = synth_close * low_ratio[perm]
            synth_open = synth_close * open_ratio[perm]
            synth_high = np.maximum(synth_high, np.maximum(synth_open, synth_close))
            synth_low = np.minimum(synth_low, np.minimum(synth_open, synth_close))

            synth_df = pd.DataFrame({
                "Open": synth_open,
                "High": synth_high,
                "Low": synth_low,
                "Close": synth_close,
                "Volume": df["Volume"].values
            }, index=df.index)

            # Classify regime from synthetic path
            total_ret = (synth_close[-1] / synth_close[0]) - 1.0
            vol = float(np.std(synth_returns)) * np.sqrt(252)
            if vol > 0.45 or total_ret < -0.15:
                regime = "crisis"
            elif total_ret > 0.08:
                regime = "alcista"
            elif total_ret < -0.05:
                regime = "bajista"
            else:
                regime = "mixto"

            # Only keep regimes within the requested set (cycle if fewer)
            if regime not in regime_names:
                regime = regime_names[u % len(regime_names)]

            res = backtester.run_backtest(strategy, synth_df, initial_deposit=10000.0)
            pnl = res.metrics["total_return_pct"]
            results_pnl.append(pnl)
            results_drawdown.append(res.metrics["max_drawdown_pct"])
            results_sharpe.append(res.metrics["sharpe_ratio"])
            regime_buckets[regime].append(pnl)

        pnl_arr = np.array(results_pnl)
        dd_arr = np.array(results_drawdown)
        sh_arr = np.array(results_sharpe)

        profitable_count = int(np.sum(pnl_arr > 0))
        profitable_pct = round((profitable_count / n_universes) * 100.0, 1)

        # Regime breakdown
        regimes_out = {}
        for rname, vals in regime_buckets.items():
            if not vals:
                continue
            arr = np.array(vals)
            regimes_out[rname] = {
                "count": len(vals),
                "profitable_pct": round(float(np.mean(arr > 0) * 100.0), 1),
                "median_return_pct": round(float(np.median(arr)), 2)
            }

        # TN Robustness Score 0-100:
        #  base = profitable_pct
        #  + regime consistency bonus (spread of regime profitable rates)
        #  + median Sharpe bonus
        #  - drawdown penalty (p95)
        #  + preset bonus
        median_ret = round(float(np.median(pnl_arr)), 2)
        p5_dd = round(float(np.percentile(dd_arr, 5)), 2)
        p50_dd = round(float(np.percentile(dd_arr, 50)), 2)
        p95_dd = round(float(np.percentile(dd_arr, 95)), 2)
        median_sharpe = round(float(np.median(sh_arr)), 2)

        regime_rates = [v["profitable_pct"] for v in regimes_out.values()]
        if len(regime_rates) >= 2:
            regime_consistency = 100.0 - float(np.std(regime_rates))  # higher = more consistent
        else:
            regime_consistency = 50.0

        score = (
            0.55 * profitable_pct +
            0.20 * regime_consistency +
            0.15 * min(max((median_sharpe / 2.0) * 100.0, 0.0), 100.0) +
            0.10 * max(0.0, 100.0 - p95_dd * 4.0) +
            pcfg["score_bonus"]
        )
        score = round(max(0.0, min(100.0, score)), 1)

        if score >= 75.0:
            verdict, verdict_badge = "ROBUSTO", "✅ Robusto"
        elif score >= 50.0:
            verdict, verdict_badge = "MODERADO", "⚠️ Moderado"
        else:
            verdict, verdict_badge = "FRAGIL", "❌ Frágil"

        hist_counts, bin_edges = np.histogram(pnl_arr, bins=12)
        histogram = [
            {"range": f"{round(bin_edges[i], 1)}% to {round(bin_edges[i+1], 1)}%", "count": int(hist_counts[i])}
            for i in range(len(hist_counts))
        ]

        passed = (profitable_pct >= min_profitable) and (score >= 60.0)

        return {
            "passed": passed,
            "score": score,
            "verdict": verdict,
            "verdict_badge": verdict_badge,
            "engine_preset": engine_preset,
            "total_universes": n_universes,
            "profitable_pct": profitable_pct,
            "regimes": regimes_out,
            "median_return_pct": median_ret,
            "median_sharpe": median_sharpe,
            "drawdown_p5": p5_dd,
            "drawdown_median": p50_dd,
            "drawdown_p95": p95_dd,
            "histogram": histogram
        }

    # =========================================================================
    # 4. PROP FIRM CHALLENGE PASS RATE
    # =========================================================================
    def evaluate_prop_firm(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        challenge_capital: float = 10000.0,
        profit_target_pct: float = 8.0,
        max_daily_loss_pct: float = 4.0,
        max_total_loss_pct: float = 8.0,
        min_trading_days: int = 5,
        simulations_count: int = 30
    ) -> Dict[str, Any]:
        """
        Simulates multiple random challenge starting dates across the historical dataset
        and calculates the pass rate for passing prop firm rules (FTMO, Topstep, etc.).
        """
        n = len(df)
        # Window ~35 calendar days scaled to the dataframe timeframe
        median_sec = 0.0
        if n >= 3:
            try:
                median_sec = float(np.median(
                    np.diff(df.index.values).astype("timedelta64[s]").astype(np.int64)
                ))
            except Exception:
                median_sec = 0.0
        bars_per_day = (86400.0 / median_sec) if median_sec > 0 else 24.0
        window_bars = max(50, int(round(bars_per_day * 35)))
        window_bars = min(window_bars, max(50, n - 50))
        max_start = n - window_bars
        if max_start <= 50:
            return {
                "pass_rate_pct": 0.0, "total_simulations": 0, "passed_count": 0,
                "failed_total_dd": 0, "failed_daily_dd": 0,
                "failed_target_not_reached": 0, "failed_min_days": 0,
                "min_trading_days": min_trading_days, "window_bars": int(window_bars),
                "target_pct": profit_target_pct, "max_dd_pct": max_total_loss_pct
            }

        start_indices = np.linspace(0, max_start, num=simulations_count, dtype=int)
        passed_count = 0
        failed_daily_dd = 0
        failed_total_dd = 0
        failed_target_not_reached = 0
        failed_min_days = 0

        for s_idx in start_indices:
            sub_df = df.iloc[s_idx : s_idx + window_bars] # ~35 calendar days of bars
            res = backtester.run_backtest(strategy, sub_df, initial_deposit=challenge_capital)

            pnl_pct = res.metrics["total_return_pct"]
            max_dd_pct = res.metrics["max_drawdown_pct"]
            max_dl_pct = res.metrics.get("max_daily_loss_pct", 0.0)
            trading_days = len({str(tr.get("entry_time", ""))[:10] for tr in res.trades})

            # Check conditions
            if max_dd_pct > max_total_loss_pct:
                failed_total_dd += 1
            elif max_dl_pct > max_daily_loss_pct:
                failed_daily_dd += 1
            elif pnl_pct < profit_target_pct:
                failed_target_not_reached += 1
            elif trading_days < min_trading_days:
                failed_min_days += 1
            else:
                passed_count += 1

        pass_rate = round((passed_count / simulations_count) * 100.0, 1)

        return {
            "pass_rate_pct": pass_rate,
            "total_simulations": simulations_count,
            "passed_count": passed_count,
            "failed_total_dd": failed_total_dd,
            "failed_daily_dd": failed_daily_dd,
            "failed_target_not_reached": failed_target_not_reached,
            "failed_min_days": failed_min_days,
            "min_trading_days": min_trading_days,
            "window_bars": int(window_bars),
            "target_pct": profit_target_pct,
            "max_dd_pct": max_total_loss_pct
        }

    # =========================================================================
    # 5. MONTE CARLO STRESS TEST (TRADINGNOTE CANON)
    # =========================================================================
    def run_monte_carlo(
        self,
        trades: List[Dict[str, Any]],
        initial_deposit: float = 10000.0,
        n_simulations: int = 1000,
        skip_rate: float = 0.05
    ) -> Dict[str, Any]:
        """
        Monte Carlo Simulation (TradingNote canon):
        - Shuffles trades sequence (tests sequence/streak vulnerability).
        - Skips skip_rate of trades (simulates missed signals/slippage).
        - Returns P95 Drawdown, % Profitable Runs, Ruin Probability (DD > 20%),
          and Return Percentiles (P5, P50, P95).
        """
        if not trades or len(trades) < 4:
            return {
                "passed": False,
                "n_simulations": n_simulations,
                "profitable_pct": 50.0,
                "drawdown_p95_pct": 10.0,
                "drawdown_median_pct": 5.0,
                "ruin_probability_pct": 0.0,
                "return_p5_usd": 0.0,
                "return_median_usd": 0.0,
                "return_p95_usd": 0.0
            }

        pnls = np.array([float(t.get("pnl_usd", 0.0)) for t in trades], dtype=float)
        n_trades = max(3, int(len(pnls) * (1.0 - skip_rate)))

        sim_max_dds = []
        sim_final_pnls = []

        for _ in range(n_simulations):
            idx = np.random.choice(len(pnls), size=n_trades, replace=True)
            sampled = pnls[idx]
            curve = np.insert(np.cumsum(sampled), 0, 0.0) + initial_deposit
            peak = np.maximum.accumulate(curve)
            dd_pct = ((peak - curve) / np.maximum(peak, 1.0)) * 100.0
            sim_max_dds.append(float(np.max(dd_pct)))
            sim_final_pnls.append(float(curve[-1] - initial_deposit))

        p95_dd = round(float(np.percentile(sim_max_dds, 95)), 2)
        p50_dd = round(float(np.percentile(sim_max_dds, 50)), 2)
        profitable_pct = round(float(np.mean(np.array(sim_final_pnls) > 0) * 100.0), 1)
        ruin_prob = round(float(np.mean(np.array(sim_max_dds) > 20.0) * 100.0), 1)

        p5_ret = round(float(np.percentile(sim_final_pnls, 5)), 2)
        p50_ret = round(float(np.percentile(sim_final_pnls, 50)), 2)
        p95_ret = round(float(np.percentile(sim_final_pnls, 95)), 2)

        # Passed if at least 80% profitable and P95 DD under 15% and ruin prob <= 3%
        passed = (profitable_pct >= 80.0) and (p95_dd <= 15.0) and (ruin_prob <= 3.0)

        return {
            "passed": passed,
            "n_simulations": n_simulations,
            "profitable_pct": profitable_pct,
            "drawdown_p95_pct": p95_dd,
            "drawdown_median_pct": p50_dd,
            "ruin_probability_pct": ruin_prob,
            "return_p5_usd": p5_ret,
            "return_median_usd": p50_ret,
            "return_p95_usd": p95_ret
        }

    # =========================================================================
    # 6. FULL RETEST SUITE (RUTA TRADINGNOTE)
    # =========================================================================
    def run_full_retest(
        self,
        strategy_data: Dict[str, Any],
        df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Runs the canonical 4-layer TradingNote robustness retest:
        1. Walk-Forward OOS (temporal validation)
        2. Monte Carlo (1000 trade-shuffling iterations)
        3. Multiverso (alternative synthetic markets)
        Calculates holistic Robustness Score (0-100) and Portfolio Approval.
        """
        st_dict = strategy_data.get("strategy", strategy_data)
        strat = Strategy.from_dict(st_dict) if isinstance(st_dict, dict) else st_dict
        
        if df is None:
            from backend.data_manager import data_manager
            df = data_manager.load_data(strat.symbol, strat.timeframe)

        # 1. Backtest if trades_sample not already provided
        trades = strategy_data.get("trades_sample", [])
        if not trades:
            res = backtester.run_backtest(strat, df, initial_deposit=10000.0)
            trades = res.trades  # already list[dict]

        # 2. Walk-Forward OOS (configurable via strategy_data)
        wf_mode = strategy_data.get("wf_mode", "validation")
        wf_depth = strategy_data.get("wf_reopt_depth", "standard")
        wf_res = self.run_walk_forward(
            strat, df,
            n_windows=int(strategy_data.get("wf_windows", 4)),
            test_ratio=float(strategy_data.get("wf_test_ratio", 0.25)),
            mode=wf_mode,
            reopt_depth=wf_depth
        )

        # 3. Monte Carlo
        mc_res = self.run_monte_carlo(trades, initial_deposit=10000.0, n_simulations=1000)

        # 4. Multiverse with score/regimes
        mv_res = self.run_multiverse(
            strat, df,
            n_universes=int(strategy_data.get("mv_universes", 60)),
            engine_preset=strategy_data.get("mv_preset", "balanced"),
            n_regimes=int(strategy_data.get("mv_regimes", 3))
        )

        # 5. Composite Robustness Score (0 to 100) — WF + MC + MV (score-based)
        wfe = wf_res.get("overall_wfe", 0.0)
        wf_score = min(35.0, (wfe / 0.7) * 35.0)

        mc_prof = mc_res.get("profitable_pct", 50.0)
        p95_dd = mc_res.get("drawdown_p95_pct", 10.0)
        mc_score = max(0.0, min(35.0, (mc_prof / 100.0) * 35.0 - (p95_dd * 0.4)))

        mv_score_val = mv_res.get("score", None)
        if mv_score_val is None:
            mv_score_val = mv_res.get("profitable_pct", 50.0)
        mv_score = min(30.0, (mv_score_val / 100.0) * 30.0)

        robustness_score = round(max(0.0, min(100.0, wf_score + mc_score + mv_score)), 1)

        wf_pass_rate = wf_res.get("pass_rate_pct", 0.0)
        if robustness_score >= 65.0 and wfe >= 0.50 and p95_dd <= 15.0 and wf_pass_rate >= 60.0:
            verdict = "ROBUSTO"
            verdict_badge = "✅ Robusto (Aprobado)"
            approved_for_portfolio = True
        elif robustness_score >= 48.0:
            verdict = "MODERADO"
            verdict_badge = "⚠️ Moderado"
            approved_for_portfolio = False
        else:
            verdict = "FRAGIL"
            verdict_badge = "❌ Frágil (Sobreajustado)"
            approved_for_portfolio = False

        return {
            "strategy_id": strat.id,
            "strategy_name": strat.name,
            "symbol": strat.symbol,
            "timeframe": strat.timeframe,
            "robustness_score": robustness_score,
            "verdict": verdict,
            "verdict_badge": verdict_badge,
            "approved_for_portfolio": approved_for_portfolio,
            "walk_forward": wf_res,
            "monte_carlo": mc_res,
            "multiverse": mv_res,
            "tested_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }

# Global singleton
validation_suite = ValidationSuite()

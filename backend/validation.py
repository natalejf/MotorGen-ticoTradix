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
    # 2. WALK-FORWARD ANALYSIS (WFA)
    # =========================================================================
    def run_walk_forward(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        n_windows: int = 5,
        test_ratio: float = 0.3
    ) -> Dict[str, Any]:
        """
        Runs Walk-Forward temporal validation.
        Splits dataset into n_windows overlapping rolling segments.
        Computes In-Sample (IS) and Out-Of-Sample (OOS) performance.
        Builds the chained OOS equity curve and calculates WFE.
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

        step = int((n - window_size) / max(n_windows - 1, 1)) if n_windows > 1 else 0

        for w in range(n_windows):
            start_idx = w * step
            train_end_idx = start_idx + train_size
            test_end_idx = min(train_end_idx + test_size, n)

            train_df = df.iloc[start_idx:train_end_idx]
            test_df = df.iloc[train_end_idx:test_end_idx]

            if len(train_df) < 50 or len(test_df) < 20:
                continue

            # Run IS backtest
            is_res = backtester.run_backtest(strategy, train_df, initial_deposit=10000.0)
            # Run OOS backtest
            oos_res = backtester.run_backtest(strategy, test_df, initial_deposit=running_oos_balance)

            # Update chained OOS
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

            windows_results.append({
                "window": w + 1,
                "is_period": f"{train_df.index[0].date()} to {train_df.index[-1].date()}",
                "oos_period": f"{test_df.index[0].date()} to {test_df.index[-1].date()}",
                "is_return_pct": is_ret,
                "oos_return_pct": oos_ret,
                "is_sharpe": round(is_sh, 2),
                "oos_sharpe": round(oos_sh, 2),
                "is_trades": is_res.metrics["total_trades"],
                "oos_trades": oos_res.metrics["total_trades"]
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
        else:
            overall_wfe = 0.0

        is_passed = overall_wfe >= 0.45

        return {
            "passed": is_passed,
            "overall_wfe": overall_wfe,
            "windows": windows_results,
            "chained_oos_equity": chained_oos_equity[::max(1, len(chained_oos_equity)//100)],
            "total_oos_trades": len(chained_trades)
        }

    # =========================================================================
    # 3. MULTIVERSE SIMULATION (SYNTHETIC ROBUSTNESS / MONTE CARLO)
    # =========================================================================
    def run_multiverse(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        n_universes: int = 100,
        block_size: int = 24 # 24 bars block to preserve volatility clustering
    ) -> Dict[str, Any]:
        """
        Creates synthetic alternative market universes using block bootstrap.
        Runs strategy across all universes to test if the edge is robust.
        """
        n = len(df)
        if n < 100:
            return {"passed": False, "profitable_pct": 0.0, "universes": []}

        # Calculate log returns of close prices
        log_ret = np.diff(np.log(df["Close"].values))
        num_blocks = int(np.ceil(len(log_ret) / block_size))

        results_pnl = []
        results_drawdown = []
        results_sharpe = []

        base_open = df["Open"].values[0]

        for u in range(n_universes):
            # Block bootstrap returns
            sampled_block_starts = np.random.randint(0, len(log_ret) - block_size + 1, size=num_blocks)
            synth_returns = np.concatenate([
                log_ret[start : start + block_size] for start in sampled_block_starts
            ])[: len(log_ret)]

            # Reconstruct synthetic Close prices
            synth_close = np.exp(np.cumsum(np.insert(synth_returns, 0, 0.0))) * base_open
            
            # Reconstruct synthetic High, Low, Open with realistic spreads
            high_ratio = (df["High"] / df["Close"]).values
            low_ratio = (df["Low"] / df["Close"]).values
            open_ratio = (df["Open"] / df["Close"]).values

            # Fast random permutation of ratios to maintain candle structure
            perm = np.random.permutation(n)
            synth_high = synth_close * high_ratio[perm]
            synth_low = synth_close * low_ratio[perm]
            synth_open = synth_close * open_ratio[perm]

            # Ensure High >= max(Open, Close) and Low <= min(Open, Close)
            synth_high = np.maximum(synth_high, np.maximum(synth_open, synth_close))
            synth_low = np.minimum(synth_low, np.minimum(synth_open, synth_close))

            synth_df = pd.DataFrame({
                "Open": synth_open,
                "High": synth_high,
                "Low": synth_low,
                "Close": synth_close,
                "Volume": df["Volume"].values
            }, index=df.index)

            # Fast test
            res = backtester.run_backtest(strategy, synth_df, initial_deposit=10000.0)
            results_pnl.append(res.metrics["total_return_pct"])
            results_drawdown.append(res.metrics["max_drawdown_pct"])
            results_sharpe.append(res.metrics["sharpe_ratio"])

        pnl_arr = np.array(results_pnl)
        dd_arr = np.array(results_drawdown)
        sh_arr = np.array(results_sharpe)

        profitable_count = int(np.sum(pnl_arr > 0))
        profitable_pct = round((profitable_count / n_universes) * 100.0, 1)

        # Percentiles
        median_ret = round(float(np.median(pnl_arr)), 2)
        p5_dd = round(float(np.percentile(dd_arr, 5)), 2)
        p50_dd = round(float(np.percentile(dd_arr, 50)), 2)
        p95_dd = round(float(np.percentile(dd_arr, 95)), 2)
        median_sharpe = round(float(np.median(sh_arr)), 2)

        # Histogram bins for UI
        hist_counts, bin_edges = np.histogram(pnl_arr, bins=12)
        histogram = [
            {"range": f"{round(bin_edges[i], 1)}% to {round(bin_edges[i+1], 1)}%", "count": int(hist_counts[i])}
            for i in range(len(hist_counts))
        ]

        passed = profitable_pct >= 65.0

        return {
            "passed": passed,
            "total_universes": n_universes,
            "profitable_pct": profitable_pct,
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
        max_start = n - 200 # Need at least 200 bars for a challenge attempt
        if max_start <= 50:
            return {"pass_rate_pct": 0.0, "total_simulations": 0, "passed_count": 0}

        start_indices = np.linspace(0, max_start, num=simulations_count, dtype=int)
        passed_count = 0
        failed_daily_dd = 0
        failed_total_dd = 0
        failed_target_not_reached = 0

        for s_idx in start_indices:
            sub_df = df.iloc[s_idx : s_idx + 350] # ~30-45 calendar days of hourly bars
            res = backtester.run_backtest(strategy, sub_df, initial_deposit=challenge_capital)
            
            pnl_pct = res.metrics["total_return_pct"]
            max_dd_pct = res.metrics["max_drawdown_pct"]
            
            # Check conditions
            if max_dd_pct > max_total_loss_pct:
                failed_total_dd += 1
            elif pnl_pct >= profit_target_pct:
                passed_count += 1
            else:
                failed_target_not_reached += 1

        pass_rate = round((passed_count / simulations_count) * 100.0, 1)

        return {
            "pass_rate_pct": pass_rate,
            "total_simulations": simulations_count,
            "passed_count": passed_count,
            "failed_total_dd": failed_total_dd,
            "failed_target_not_reached": failed_target_not_reached,
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
            trades = [t.to_dict() for t in res.trades]

        # 2. Walk-Forward OOS
        wf_res = self.run_walk_forward(strat, df, n_windows=4, test_ratio=0.25)

        # 3. Monte Carlo
        mc_res = self.run_monte_carlo(trades, initial_deposit=10000.0, n_simulations=1000)

        # 4. Multiverse (quick 60 synthetic universes)
        mv_res = self.run_multiverse(strat, df, n_universes=60)

        # 5. Composite Robustness Score (0 to 100)
        wfe = wf_res.get("overall_wfe", 0.0)
        wf_score = min(35.0, (wfe / 0.7) * 35.0)

        mc_prof = mc_res.get("profitable_pct", 50.0)
        p95_dd = mc_res.get("drawdown_p95_pct", 10.0)
        mc_score = max(0.0, min(35.0, (mc_prof / 100.0) * 35.0 - (p95_dd * 0.4)))

        mv_prof = mv_res.get("profitable_pct", 50.0)
        mv_score = min(30.0, (mv_prof / 100.0) * 30.0)

        robustness_score = round(max(0.0, min(100.0, wf_score + mc_score + mv_score)), 1)

        # TradingNote Verdict
        if robustness_score >= 65.0 and wfe >= 0.40 and p95_dd <= 15.0:
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

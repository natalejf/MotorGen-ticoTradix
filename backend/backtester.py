"""
High-Speed Vectorized & Event-Driven Backtester for TradingNote Genetic Engine Replica
Simulates strategy trades with realistic broker execution:
- Spread, slippage, commission, swap
- ATR/Trailing/Breakeven/Time exits
- Prop firm daily & total drawdown risk limits
- Comprehensive statistical metrics & TN Score
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
from backend.indicators import indicator_engine
from backend.strategy import Strategy, Condition
from backend.data_manager import SUPPORTED_SYMBOLS

class BacktestResult:
    def __init__(
        self,
        strategy_id: str,
        metrics: Dict[str, Any],
        equity_curve: List[Dict[str, Any]],
        trades: List[Dict[str, Any]],
        drawdown_curve: List[Dict[str, Any]]
    ):
        self.strategy_id = strategy_id
        self.metrics = metrics
        self.equity_curve = equity_curve
        self.trades = trades
        self.drawdown_curve = drawdown_curve

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "metrics": self.metrics,
            "equity_curve": self.equity_curve,
            "trades": self.trades,
            "drawdown_curve": self.drawdown_curve
        }


class Backtester:
    def __init__(self, default_initial_deposit: float = 10000.0):
        self.default_initial_deposit = default_initial_deposit

    def evaluate_condition(self, df: pd.DataFrame, cond: Condition, is_buy: bool) -> np.ndarray:
        """Evaluates a single Condition into a boolean NumPy array."""
        ind_name = cond.indicator.upper()
        p = cond.params
        c_series = df["Close"]

        # 1. Resolve Primary Indicator
        if ind_name == "EMA":
            s1 = indicator_engine.ema(c_series, p.get("period", 50))
        elif ind_name == "SMA":
            s1 = indicator_engine.sma(c_series, p.get("period", 50))
        elif ind_name == "DEMA":
            s1 = indicator_engine.dema(c_series, p.get("period", 21))
        elif ind_name == "TEMA":
            s1 = indicator_engine.tema(c_series, p.get("period", 21))
        elif ind_name == "HMA":
            s1 = indicator_engine.hma(c_series, p.get("period", 9))
        elif ind_name == "WMA":
            s1 = indicator_engine.wma(c_series, p.get("period", 20))
        elif ind_name == "KAMA":
            s1 = indicator_engine.kama(c_series, p.get("period", 10))
        elif ind_name == "RSI":
            s1 = indicator_engine.rsi(c_series, p.get("period", 14))
        elif ind_name == "MACD":
            m, s, h = indicator_engine.macd(c_series, p.get("fast", 12), p.get("slow", 26), p.get("signal", 9))
            sub = p.get("sub", "hist")
            s1 = h if sub == "hist" else (m if sub == "macd" else s)
        elif ind_name == "STOCHASTIC":
            k, d = indicator_engine.stochastic(df, p.get("k_period", 14), p.get("d_period", 3))
            s1 = k if p.get("sub", "k") == "k" else d
        elif ind_name == "SUPERTREND":
            trend, line = indicator_engine.supertrend(df, p.get("period", 10), p.get("multiplier", 3.0))
            if cond.operator in ["BULLISH", "BEARISH"]:
                return (trend == 1).values if cond.operator == "BULLISH" else (trend == -1).values
            s1 = c_series - line
        elif ind_name == "BOLLINGER":
            upper, mid, lower, pb = indicator_engine.bollinger_bands(c_series, p.get("period", 20), p.get("std_dev", 2.0))
            sub = p.get("sub", "pct_b")
            s1 = pb if sub == "pct_b" else (upper if sub == "upper" else (lower if sub == "lower" else mid))
        elif ind_name == "KELTNER":
            upper, mid, lower = indicator_engine.keltner_channel(df, p.get("period", 20), p.get("multiplier", 1.5))
            s1 = c_series - mid
        elif ind_name == "DONCHIAN":
            upper, mid, lower = indicator_engine.donchian_channel(df, p.get("period", 20))
            s1 = c_series - mid
        elif ind_name == "STDDEV":
            s1 = indicator_engine.std_dev(c_series, p.get("period", 20))
        elif ind_name == "CCI":
            s1 = indicator_engine.cci(df, p.get("period", 20))
        elif ind_name == "ROC":
            s1 = indicator_engine.roc(c_series, p.get("period", 12))
        elif ind_name == "WILLIAMS_R":
            s1 = indicator_engine.williams_r(df, p.get("period", 14))
        elif ind_name == "RCI":
            s1 = indicator_engine.rci(c_series, p.get("period", 9))
        elif ind_name == "ADX":
            adx, pdi, mdi = indicator_engine.adx(df, p.get("period", 14))
            sub = p.get("sub", "adx")
            s1 = adx if sub == "adx" else (pdi if sub == "pdi" else mdi)
        elif ind_name == "PSAR":
            val, direction = indicator_engine.psar(df, p.get("step", 0.02), p.get("max_step", 0.2))
            if cond.operator in ["BULLISH", "BEARISH"]:
                return (direction == 1).values if cond.operator == "BULLISH" else (direction == -1).values
            s1 = c_series - val
        elif ind_name == "AROON":
            up, down, osc = indicator_engine.aroon(df, p.get("period", 14))
            s1 = osc
        elif ind_name == "ICHIMOKU":
            ichi = indicator_engine.ichimoku(df)
            s1 = c_series - ichi["kijun"]
        elif ind_name == "VOLUME_SMA":
            s1 = indicator_engine.volume_sma(df, p.get("period", 20))
        elif ind_name == "OBV":
            s1 = indicator_engine.obv(df)
        elif ind_name == "CMF":
            s1 = indicator_engine.cmf(df, p.get("period", 20))
        elif ind_name == "MFI":
            s1 = indicator_engine.mfi(df, p.get("period", 14))
        elif ind_name == "ATR":
            s1 = indicator_engine.atr(df, p.get("period", 14))
        elif ind_name == "PRICE":
            s1 = c_series
        else:
            s1 = c_series

        # 2. Resolve Target / Secondary
        if cond.target_type == "value":
            s2 = cond.target_value
            is_scalar = True
        else:
            # Secondary indicator
            t_name = (cond.target_indicator or "EMA").upper()
            tp = cond.target_params
            if t_name == "EMA":
                s2 = indicator_engine.ema(c_series, tp.get("period", 200))
            elif t_name == "SMA":
                s2 = indicator_engine.sma(c_series, tp.get("period", 200))
            elif t_name == "PRICE":
                s2 = c_series
            else:
                s2 = indicator_engine.ema(c_series, 200)
            is_scalar = False

        v1 = s1.values if isinstance(s1, pd.Series) else s1
        v2 = s2.values if isinstance(s2, pd.Series) else s2

        op = cond.operator.upper()
        if op == "GREATER_THAN":
            return v1 > v2
        elif op == "LESS_THAN":
            return v1 < v2
        elif op == "CROSS_ABOVE":
            if is_scalar:
                prev_v1 = np.roll(v1, 1)
                prev_v1[0] = v1[0]
                return (prev_v1 <= v2) & (v1 > v2)
            else:
                prev_v1 = np.roll(v1, 1)
                prev_v2 = np.roll(v2, 1)
                prev_v1[0], prev_v2[0] = v1[0], v2[0]
                return (prev_v1 <= prev_v2) & (v1 > v2)
        elif op == "CROSS_BELOW":
            if is_scalar:
                prev_v1 = np.roll(v1, 1)
                prev_v1[0] = v1[0]
                return (prev_v1 >= v2) & (v1 < v2)
            else:
                prev_v1 = np.roll(v1, 1)
                prev_v2 = np.roll(v2, 1)
                prev_v1[0], prev_v2[0] = v1[0], v2[0]
                return (prev_v1 >= prev_v2) & (v1 < v2)
        elif op == "BULLISH":
            return v1 > 0
        elif op == "BEARISH":
            return v1 < 0
        else:
            return np.ones(len(df), dtype=bool)

    def generate_signal_arrays(self, df: pd.DataFrame, strategy: Strategy) -> Tuple[np.ndarray, np.ndarray]:
        """Generates raw boolean buy and sell signal arrays for the strategy."""
        n = len(df)
        buy_signals = np.ones(n, dtype=bool) if strategy.buy_conditions else np.zeros(n, dtype=bool)
        for cond in strategy.buy_conditions:
            res = self.evaluate_condition(df, cond, is_buy=True)
            buy_signals = buy_signals & res

        sell_signals = np.ones(n, dtype=bool) if strategy.sell_conditions else np.zeros(n, dtype=bool)
        for cond in strategy.sell_conditions:
            res = self.evaluate_condition(df, cond, is_buy=False)
            sell_signals = sell_signals & res

        # Direction filter
        if strategy.direction == "LONG_ONLY":
            sell_signals[:] = False
        elif strategy.direction == "SHORT_ONLY":
            buy_signals[:] = False

        # Session Filter
        if strategy.session_filter != "ALL":
            hours = df.index.hour.values
            if strategy.session_filter == "LONDON":
                mask = (hours >= 7) & (hours < 16)
            elif strategy.session_filter == "NEW_YORK":
                mask = (hours >= 12) & (hours < 21)
            elif strategy.session_filter == "TOKYO":
                mask = (hours >= 0) & (hours < 9)
            elif strategy.session_filter == "OVERLAP_LDN_NY":
                mask = (hours >= 12) & (hours < 16)
            else:
                mask = np.ones(n, dtype=bool)
            buy_signals = buy_signals & mask
            sell_signals = sell_signals & mask

        return buy_signals, sell_signals

    def run_backtest(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        initial_deposit: Optional[float] = None,
        custom_spread_pips: Optional[float] = None,
        custom_slippage_pips: float = 0.5,
        commission_per_lot: float = 5.0 # USD per standard lot roundturn
    ) -> BacktestResult:
        """
        Executes fast, tick-level simulated backtest bar-by-bar.
        """
        capital = initial_deposit or self.default_initial_deposit
        sym_meta = SUPPORTED_SYMBOLS.get(strategy.symbol, {
            "pip_size": 0.0001, "point_value": 100000.0, "default_spread": 0.00015, "digits": 5
        })
        pip_size = sym_meta["pip_size"]
        point_val = sym_meta["point_value"]
        spread = (custom_spread_pips * pip_size) if custom_spread_pips is not None else sym_meta["default_spread"]
        slippage = custom_slippage_pips * pip_size

        atr_series = indicator_engine.atr(df, 14).values
        opens = df["Open"].values
        highs = df["High"].values
        lows = df["Low"].values
        closes = df["Close"].values
        times = df.index
        n = len(df)

        buy_signals, sell_signals = self.generate_signal_arrays(df, strategy)

        # Simulation state
        balance = capital
        equity = capital
        peak_equity = capital
        max_drawdown_usd = 0.0
        max_drawdown_pct = 0.0

        equity_curve = [{"time": str(times[0]), "equity": round(capital, 2), "balance": round(capital, 2)}]
        drawdown_curve = [{"time": str(times[0]), "drawdown_pct": 0.0}]
        trades = []

        current_trade = None # None or dict
        consecutive_wins = 0
        consecutive_losses = 0
        max_consec_wins = 0
        max_consec_losses = 0

        # Daily loss tracker
        current_day = times[0].date()
        day_start_balance = balance
        day_loss_locked = False
        day_trades_count = 0

        for i in range(1, n):
            t = times[i]
            t_date = t.date()

            # Check new day
            if t_date != current_day:
                current_day = t_date
                day_start_balance = balance
                day_loss_locked = False
                day_trades_count = 0

            cur_atr = max(atr_series[i], pip_size * 5.0)

            # ----------------------------------------------------
            # 1. Manage existing open trade
            # ----------------------------------------------------
            if current_trade is not None:
                tr = current_trade
                tr["bars_held"] += 1
                direction = tr["direction"]
                entry_p = tr["entry_price"]
                sl = tr["sl_price"]
                tp = tr["tp_price"]
                size_lots = tr["size_lots"]

                closed = False
                exit_price = 0.0
                exit_reason = ""

                # Weekend exit rule
                if strategy.close_before_weekend and t.weekday() == 4 and t.hour >= 20:
                    closed = True
                    exit_price = opens[i]
                    exit_reason = "Weekend Close"

                # Check SL / TP within current bar
                if not closed:
                    if direction == "BUY":
                        # Check Stop Loss
                        if lows[i] <= sl:
                            closed = True
                            exit_price = sl - slippage
                            exit_reason = "Stop Loss"
                        # Check Take Profit
                        elif highs[i] >= tp:
                            closed = True
                            exit_price = tp
                            exit_reason = "Take Profit"
                        # Check Trailing Stop logic
                        elif strategy.exit_mode == "TRAILING_ATR":
                            highest_since = max(tr["mfe_price"], highs[i])
                            tr["mfe_price"] = highest_since
                            new_sl = highest_since - (strategy.trail_atr * cur_atr)
                            if new_sl > sl:
                                tr["sl_price"] = new_sl
                        # Check Breakeven logic
                        elif strategy.exit_mode == "BREAKEVEN":
                            if not tr["be_activated"] and (highs[i] - entry_p) >= (strategy.be_atr * cur_atr):
                                tr["sl_price"] = entry_p + (spread / 2.0)
                                tr["be_activated"] = True
                        # Check Time exit
                        elif strategy.exit_mode == "TIME_EXIT" and tr["bars_held"] >= strategy.max_bars:
                            closed = True
                            exit_price = closes[i]
                            exit_reason = "Time Exit"

                    else: # SELL
                        # Check Stop Loss
                        if highs[i] >= sl:
                            closed = True
                            exit_price = sl + slippage
                            exit_reason = "Stop Loss"
                        # Check Take Profit
                        elif lows[i] <= tp:
                            closed = True
                            exit_price = tp
                            exit_reason = "Take Profit"
                        # Trailing Stop logic
                        elif strategy.exit_mode == "TRAILING_ATR":
                            lowest_since = min(tr["mfe_price"], lows[i])
                            tr["mfe_price"] = lowest_since
                            new_sl = lowest_since + (strategy.trail_atr * cur_atr)
                            if new_sl < sl:
                                tr["sl_price"] = new_sl
                        # Breakeven logic
                        elif strategy.exit_mode == "BREAKEVEN":
                            if not tr["be_activated"] and (entry_p - lows[i]) >= (strategy.be_atr * cur_atr):
                                tr["sl_price"] = entry_p - (spread / 2.0)
                                tr["be_activated"] = True
                        # Time exit
                        elif strategy.exit_mode == "TIME_EXIT" and tr["bars_held"] >= strategy.max_bars:
                            closed = True
                            exit_price = closes[i]
                            exit_reason = "Time Exit"

                # If trade closed this bar
                if closed:
                    if direction == "BUY":
                        diff_points = (exit_price - entry_p)
                    else:
                        diff_points = (entry_p - exit_price)

                    pnl_raw = diff_points * point_val * size_lots
                    comm = commission_per_lot * size_lots
                    net_pnl = pnl_raw - comm
                    pips = round(diff_points / pip_size, 1)

                    balance += net_pnl
                    equity = balance

                    # Consecutive win/loss tracking
                    if net_pnl > 0:
                        consecutive_wins += 1
                        consecutive_losses = 0
                        max_consec_wins = max(max_consec_wins, consecutive_wins)
                    else:
                        consecutive_losses += 1
                        consecutive_wins = 0
                        max_consec_losses = max(max_consec_losses, consecutive_losses)

                    trades.append({
                        "trade_num": int(len(trades) + 1),
                        "symbol": str(strategy.symbol),
                        "direction": str(direction),
                        "entry_time": str(tr["entry_time"]),
                        "entry_price": float(round(entry_p, sym_meta["digits"])),
                        "exit_time": str(t),
                        "exit_price": float(round(exit_price, sym_meta["digits"])),
                        "size_lots": float(round(size_lots, 2)),
                        "pnl_usd": float(round(net_pnl, 2)),
                        "pips": float(pips),
                        "bars_held": int(tr["bars_held"]),
                        "exit_reason": str(exit_reason),
                        "balance_after": float(round(balance, 2))
                    })

                    current_trade = None

                    # Check daily loss limit
                    day_loss_pct = ((day_start_balance - balance) / day_start_balance) * 100.0 if day_start_balance > 0 else 0
                    if day_loss_pct >= strategy.max_daily_loss_pct:
                        day_loss_locked = True

            # ----------------------------------------------------
            # 2. Check for new trade entry if flat
            # ----------------------------------------------------
            if current_trade is None and not day_loss_locked and day_trades_count < strategy.max_daily_trades:
                # Check total account loss limit
                total_loss_pct = ((capital - balance) / capital) * 100.0
                if total_loss_pct < strategy.max_account_loss_pct:
                    sig_buy = buy_signals[i - 1] # Signal generated on close of previous bar
                    sig_sell = sell_signals[i - 1]

                    if sig_buy or sig_sell:
                        trade_dir = "BUY" if sig_buy else "SELL"
                        base_open = opens[i]
                        sl_dist = strategy.sl_atr * cur_atr
                        tp_dist = strategy.tp_atr * cur_atr
                        entry_type = getattr(strategy, "entry_order_type", "MARKET")
                        
                        filled = False
                        entry_price = base_open

                        if entry_type == "LIMIT":
                            # Pullback limit order
                            offset = 0.2 * cur_atr
                            if trade_dir == "BUY":
                                limit_p = base_open - offset
                                if lows[i] <= limit_p:
                                    entry_price = limit_p + (spread / 2.0)
                                    filled = True
                            else:
                                limit_p = base_open + offset
                                if highs[i] >= limit_p:
                                    entry_price = limit_p - (spread / 2.0)
                                    filled = True
                        elif entry_type == "STOP":
                            # Breakout stop order
                            offset = 0.2 * cur_atr
                            if trade_dir == "BUY":
                                stop_p = base_open + offset
                                if highs[i] >= stop_p:
                                    entry_price = stop_p + (spread / 2.0) + slippage
                                    filled = True
                            else:
                                stop_p = base_open - offset
                                if lows[i] <= stop_p:
                                    entry_price = stop_p - (spread / 2.0) - slippage
                                    filled = True
                        else:
                            # Standard Market Order
                            entry_price = base_open + (spread / 2.0 if trade_dir == "BUY" else -spread / 2.0)
                            filled = True

                        if filled:
                            if trade_dir == "BUY":
                                sl_p = entry_price - sl_dist
                                tp_p = entry_price + tp_dist
                            else:
                                sl_p = entry_price + sl_dist
                                tp_p = entry_price - tp_dist

                            # Sizing
                            if strategy.sizing_mode == "FIXED_LOT":
                                lot_size = strategy.fixed_lot
                            else:
                                # Risk % per trade
                                risk_usd = balance * (strategy.risk_per_trade_pct / 100.0)
                                # Martingale adjustment
                                if strategy.sizing_mode == "MARTINGALE" and consecutive_losses > 0:
                                    risk_usd *= (strategy.martingale_mult ** min(consecutive_losses, 3))
                                elif strategy.sizing_mode == "ANTI_MARTINGALE" and consecutive_wins > 0:
                                    risk_usd *= (1.2 ** min(consecutive_wins, 3))
                                
                                price_risk = max(sl_dist, pip_size * 5)
                                lot_size = risk_usd / (price_risk * point_val)
                                lot_size = max(0.01, min(round(lot_size, 2), 50.0))

                            current_trade = {
                                "direction": trade_dir,
                                "entry_time": t,
                                "entry_price": entry_price,
                                "sl_price": sl_p,
                                "tp_price": tp_p,
                                "size_lots": lot_size,
                                "bars_held": 0,
                                "mfe_price": entry_price,
                                "be_activated": False
                            }
                            day_trades_count += 1

            # ----------------------------------------------------
            # 3. Track Drawdown and Equity
            # ----------------------------------------------------
            # Floating PnL
            unrealized_pnl = 0.0
            if current_trade is not None:
                cur_close = closes[i]
                if current_trade["direction"] == "BUY":
                    unrealized_pnl = (cur_close - current_trade["entry_price"]) * point_val * current_trade["size_lots"]
                else:
                    unrealized_pnl = (current_trade["entry_price"] - cur_close) * point_val * current_trade["size_lots"]

            current_equity = balance + unrealized_pnl
            peak_equity = max(peak_equity, current_equity)
            dd_usd = peak_equity - current_equity
            dd_pct = (dd_usd / peak_equity) * 100.0 if peak_equity > 0 else 0.0

            max_drawdown_usd = max(max_drawdown_usd, dd_usd)
            max_drawdown_pct = max(max_drawdown_pct, dd_pct)

            # Sample equity curve (e.g. every bar or every few bars to save payload)
            if i % max(1, int(n / 250)) == 0 or i == n - 1:
                equity_curve.append({
                    "time": str(t),
                    "equity": round(current_equity, 2),
                    "balance": round(balance, 2)
                })
                drawdown_curve.append({
                    "time": str(t),
                    "drawdown_pct": round(-dd_pct, 2)
                })

        # --------------------------------------------------------
        # 4. Compute Comprehensive Performance Metrics
        # --------------------------------------------------------
        total_trades = len(trades)
        if total_trades > 0:
            pnls = np.array([tr["pnl_usd"] for tr in trades])
            wins = pnls[pnls > 0]
            losses = pnls[pnls < 0]
            
            win_rate = (len(wins) / total_trades) * 100.0
            gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
            gross_loss = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.001
            profit_factor = gross_profit / gross_loss
            expectancy = float(np.mean(pnls))
            
            # Annualized Return & Sharpe
            days_span = max((times[-1] - times[0]).days, 1)
            years = days_span / 365.25
            total_return_usd = balance - capital
            total_return_pct = (total_return_usd / capital) * 100.0
            cagr = ((balance / capital) ** (1.0 / max(years, 0.1)) - 1.0) * 100.0 if balance > 0 else -100.0

            # Daily / trade returns Sharpe
            daily_returns = pd.Series([e["equity"] for e in equity_curve]).pct_change().dropna()
            if len(daily_returns) > 5 and daily_returns.std() > 0:
                sharpe = float((daily_returns.mean() / daily_returns.std()) * np.sqrt(252 * (n / max(years*252, 1) if n > 0 else 252)))
                # Sortino (downside risk only)
                neg_returns = daily_returns[daily_returns < 0]
                downside_std = neg_returns.std() if len(neg_returns) > 2 else daily_returns.std()
                sortino = float((daily_returns.mean() / max(downside_std, 1e-6)) * np.sqrt(252))
            else:
                sharpe = 0.0
                sortino = 0.0

            calmar = (cagr / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0
            recovery_factor = (total_return_usd / max_drawdown_usd) if max_drawdown_usd > 0 else 0.0

            # TradingNote TN Score formula (0 to 100)
            # Ponderation: Sharpe (30%), Calmar (25%), Profit Factor (20%), Win Rate (15%), Trade sufficiency (10%)
            sharpe_component = min(max(sharpe / 3.0, 0.0), 1.0) * 30.0
            calmar_component = min(max(calmar / 3.0, 0.0), 1.0) * 25.0
            pf_component = min(max((profit_factor - 1.0) / 1.5, 0.0), 1.0) * 20.0
            wr_component = min(max((win_rate - 35.0) / 35.0, 0.0), 1.0) * 15.0
            trade_count_penalty = min(total_trades / 30.0, 1.0) # Penalize if under 30 trades
            
            raw_score = (sharpe_component + calmar_component + pf_component + wr_component + (trade_count_penalty * 10.0))
            if max_drawdown_pct > 25.0: # Severe DD penalty
                raw_score *= max(0.0, 1.0 - (max_drawdown_pct - 25.0) / 25.0)
            tn_score = round(min(max(raw_score, 0.0), 100.0), 1)

        else:
            total_return_usd = 0.0
            total_return_pct = 0.0
            cagr = 0.0
            sharpe = 0.0
            sortino = 0.0
            calmar = 0.0
            win_rate = 0.0
            profit_factor = 0.0
            expectancy = 0.0
            recovery_factor = 0.0
            tn_score = 0.0

        metrics = {
            "initial_capital": float(capital),
            "final_balance": float(round(balance, 2)),
            "total_return_usd": float(round(total_return_usd, 2)),
            "total_return_pct": float(round(total_return_pct, 2)),
            "cagr_pct": float(round(cagr, 2)),
            "sharpe_ratio": float(round(sharpe, 2)),
            "sortino_ratio": float(round(sortino, 2)),
            "calmar_ratio": float(round(calmar, 2)),
            "max_drawdown_usd": float(round(max_drawdown_usd, 2)),
            "max_drawdown_pct": float(round(max_drawdown_pct, 2)),
            "total_trades": int(total_trades),
            "win_rate_pct": float(round(win_rate, 1)),
            "profit_factor": float(round(profit_factor, 2)),
            "expectancy_usd": float(round(expectancy, 2)),
            "recovery_factor": float(round(recovery_factor, 2)),
            "max_consecutive_wins": int(max_consec_wins),
            "max_consecutive_losses": int(max_consec_losses),
            "tn_score": float(tn_score)
        }

        # Store in strategy
        strategy.metrics = metrics

        return BacktestResult(
            strategy_id=strategy.id,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            drawdown_curve=drawdown_curve
        )

# Global singleton
backtester = Backtester()

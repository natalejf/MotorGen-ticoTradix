"""
High-Speed Vectorized & Event-Driven Backtester for TradingNote Genetic Engine Replica
Simulates strategy trades with realistic broker execution:
- Spread, slippage, commission, swap
- 9 exit modes: ATR, Pips, %, Trailing, Breakeven, Swing, Time, Partial TP, ATR smoothed
- Full risk rules: daily/weekly/monthly loss & gain caps, consecutive limits, R:R min
- Session & time filters: Sydney/Tokyo/London/NY overlaps, Friday/Monday/rollover rules
- Modeling modes: open_prices (fast pre-filter) and ohlc (default)
- Content-fingerprint signal caching for rapid genetic exploration
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
        # Signal array cache: (df_fp, cond_fingerprint) -> bool ndarray
        self._sig_cache: Dict[Tuple, np.ndarray] = {}
        self._sig_max = 16384

    # ------------------------------------------------------------------
    # CONDITION EVALUATION (with signal caching)
    # ------------------------------------------------------------------
    def _cond_key(self, df: pd.DataFrame, cond: Condition) -> Tuple:
        return (
            indicator_engine.df_fingerprint(df),
            cond.indicator,
            tuple(sorted((cond.params or {}).items(), key=lambda x: str(x[0]))),
            cond.operator,
            cond.target_type,
            round(float(cond.target_value), 8) if cond.target_type == "value" else None,
            cond.target_indicator,
            tuple(sorted((cond.target_params or {}).items(), key=lambda x: str(x[0]))),
        )

    def evaluate_condition(self, df: pd.DataFrame, cond: Condition, is_buy: bool) -> np.ndarray:
        """Evaluates a single Condition into a boolean NumPy array (cached)."""
        key = self._cond_key(df, cond)
        hit = self._sig_cache.get(key)
        if hit is not None:
            return hit
        arr = self._evaluate_condition_raw(df, cond, is_buy)
        if len(self._sig_cache) >= self._sig_max:
            for k in list(self._sig_cache.keys())[: max(1, self._sig_max // 4)]:
                del self._sig_cache[k]
        self._sig_cache[key] = arr
        return arr

    def clear_signal_cache(self):
        self._sig_cache.clear()

    def _evaluate_condition_raw(self, df: pd.DataFrame, cond: Condition, is_buy: bool, return_indicator=False) -> np.ndarray:
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
            s1 = indicator_engine.kama(c_series, p.get("period", 10),p.get("fast",2),p.get("slow",30))
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
            ichi = indicator_engine.ichimoku(df,p.get("tenkan_p",9),p.get("kijun_p",26),p.get("span_b_p",52))
            sub = p.get("sub", "kijun")
            s1 = c_series - ichi.get(sub, ichi["kijun"])
        elif ind_name == "HIGHEST":
            s1 = indicator_engine.highest(df, p.get("period", 20))
        elif ind_name == "LOWEST":
            s1 = indicator_engine.lowest(df, p.get("period", 20))
        elif ind_name == "PIVOT_POINTS":
            piv = indicator_engine.pivot_points(df)
            sub = p.get("sub", "pp")
            s1 = piv.get(sub, piv["pp"])
        elif ind_name == "VWAP":
            s1 = indicator_engine.vwap(df)
        elif ind_name.startswith("MACRO_"):
            # FRED macro context column aligned anti-lookahead (MACRO_{ID})
            col = f"MACRO_{ind_name[6:]}"
            if col in df.columns:
                s1 = df[col]
            else:
                # Missing macro is unavailable information, never a synthetic zero.
                s1 = pd.Series(np.nan, index=df.index)
        elif ind_name == "VOLUME_SMA":
            s1 = indicator_engine.volume_sma(df, p.get("period", 20))
        elif ind_name == "OBV":
            s1 = indicator_engine.obv(df, p.get("signal", 20))
        elif ind_name == "CMF":
            s1 = indicator_engine.cmf(df, p.get("period", 20))
        elif ind_name == "MFI":
            s1 = indicator_engine.mfi(df, p.get("period", 14))
        elif ind_name == "ATR":
            s1 = indicator_engine.atr(df, p.get("period", 14))
        elif ind_name == "PRICE":
            s1 = c_series
        else:
            raise ValueError(f'Indicador no admitido: {ind_name}')

        if return_indicator:
            return s1

        # 2. Resolve Target / Secondary
        if cond.target_type == "value":
            s2 = cond.target_value
            is_scalar = True
        else:
            t_name = (cond.target_indicator or "EMA").upper()
            tp = cond.target_params
            if t_name == "EMA":
                s2 = indicator_engine.ema(c_series, tp.get("period", 200))
            elif t_name == "SMA":
                s2 = indicator_engine.sma(c_series, tp.get("period", 200))
            elif t_name == "PRICE":
                s2 = c_series
            elif t_name == "VWAP":
                s2 = indicator_engine.vwap(df)
            else:
                target=Condition(t_name,tp,"GREATER_THAN")
                s2=self._evaluate_condition_raw(df,target,is_buy,return_indicator=True)
            is_scalar = False

        v1 = s1.values if isinstance(s1, pd.Series) else np.asarray(s1)
        v2 = s2.values if isinstance(s2, pd.Series) else s2

        op = cond.operator.upper()
        if op == "GREATER_THAN":
            return v1 > v2
        elif op == "LESS_THAN":
            return v1 < v2
        elif op == "EQUAL_TO":
            return np.isclose(v1, v2, rtol=1e-5, atol=1e-8)
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
        elif op == "CROSS_BOTH":
            # Cruza en cualquier sentido durante la barra (TN: "cruza ambos")
            if is_scalar:
                prev_v1 = np.roll(v1, 1)
                prev_v1[0] = v1[0]
                return ((prev_v1 <= v2) & (v1 > v2)) | ((prev_v1 >= v2) & (v1 < v2))
            else:
                prev_v1 = np.roll(v1, 1)
                prev_v2 = np.roll(v2, 1)
                prev_v1[0], prev_v2[0] = v1[0], v2[0]
                return ((prev_v1 <= prev_v2) & (v1 > v2)) | ((prev_v1 >= prev_v2) & (v1 < v2))
        elif op in ("PRICE_ABOVE", "PRICE_BELOW"):
            # TN 'price_above'/'price_below': el PRECIO respecto al indicador.
            # Para HIGHEST/LOWEST se compara contra la ventana ANTERIOR (breakout:
            # close > máximo de las N velas previas, sin incluir la barra actual).
            close_arr = c_series.values
            ref = v1
            if ind_name in ("HIGHEST", "LOWEST"):
                ref = np.roll(v1, 1)
                ref[0] = v1[0]
            return close_arr > ref if op == "PRICE_ABOVE" else close_arr < ref
        elif op == "BULLISH":
            return v1 > 0
        elif op == "BEARISH":
            return v1 < 0
        else:
            raise ValueError(f'Operador no admitido: {op}')

    # ------------------------------------------------------------------
    # SIGNAL ARRAYS (sessions, direction, time rules)
    # ------------------------------------------------------------------
    def generate_signal_arrays(self, df: pd.DataFrame, strategy: Strategy) -> Tuple[np.ndarray, np.ndarray]:
        n = len(df)
        buy_signals = np.ones(n, dtype=bool) if strategy.buy_conditions else np.zeros(n, dtype=bool)
        for cond in strategy.buy_conditions:
            buy_signals = buy_signals & self.evaluate_condition(df, cond, is_buy=True)

        sell_signals = np.ones(n, dtype=bool) if strategy.sell_conditions else np.zeros(n, dtype=bool)
        for cond in strategy.sell_conditions:
            sell_signals = sell_signals & self.evaluate_condition(df, cond, is_buy=False)

        if strategy.direction == "LONG_ONLY":
            sell_signals[:] = False
        elif strategy.direction == "SHORT_ONLY":
            buy_signals[:] = False

        # Session filter
        if strategy.session_filter != "ALL":
            hours = df.index.hour.values
            if strategy.session_filter == "SYDNEY":
                mask = (hours >= 21) | (hours < 6)
            elif strategy.session_filter == "TOKYO":
                mask = (hours >= 0) & (hours < 9)
            elif strategy.session_filter == "OVERLAP_TOKYO_LDN":
                mask = (hours >= 7) & (hours < 9)
            elif strategy.session_filter == "LONDON":
                mask = (hours >= 7) & (hours < 16)
            elif strategy.session_filter == "NEW_YORK":
                mask = (hours >= 12) & (hours < 21)
            elif strategy.session_filter == "OVERLAP_LDN_NY":
                mask = (hours >= 12) & (hours < 16)
            else:
                mask = np.ones(n, dtype=bool)
            buy_signals = buy_signals & mask
            sell_signals = sell_signals & mask

        # Time rules applied to ENTRIES
        weekdays = df.index.weekday.values  # 0=Mon .. 4=Fri
        hours = df.index.hour.values
        minutes = df.index.minute.values

        if getattr(strategy, "no_new_trades_friday", False):
            fri = weekdays == 4
            buy_signals = buy_signals & ~fri
            sell_signals = sell_signals & ~fri

        if getattr(strategy, "no_monday_open", False):
            # No entries until 01:00 UTC Monday
            mon_early = (weekdays == 0) & (hours < 1)
            buy_signals = buy_signals & ~mon_early
            sell_signals = sell_signals & ~mon_early

        if getattr(strategy, "avoid_rollover", False):
            # 20:55 - 21:10 UTC daily
            rollover = (hours == 20) & (minutes >= 55) | (hours == 21) & (minutes <= 10)
            buy_signals = buy_signals & ~rollover
            sell_signals = sell_signals & ~rollover

        return buy_signals, sell_signals

    # ------------------------------------------------------------------
    # MAIN BACKTEST
    # ------------------------------------------------------------------
    def run_backtest(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        initial_deposit: Optional[float] = None,
        custom_spread_pips: Optional[float] = None,
        custom_slippage_pips: float = 0.5,
        commission_per_lot: float = 5.0,
        swap_long_per_lot: float = 0.0,
        swap_short_per_lot: float = 0.0,
        modeling_mode: str = "ohlc",  # "ohlc" | "open_prices" | "ohlc_m1" | "tick"
        htf_df: Optional[pd.DataFrame] = None  # F: df del TF superior (confirmación MTF)
    ) -> BacktestResult:
        """
        Executes simulated backtest bar-by-bar.
        modeling_mode:
          - ohlc: detect SL/TP touch inside bar via High/Low (default)
          - open_prices: evaluate exits only at bar open (fast pre-filter)
          - ohlc_m1: intra-bar sequential path (O->L->H->C bullish, O->H->L->C bearish)
            with 4 sub-steps per leg; resolves same-bar SL/TP touch order deterministically
          - tick: same intra-bar path with 10 sub-steps per leg (finest resolution)
        Entries keep bar-level fills (open/limit/stop) in all modes.
        """
        capital = initial_deposit or self.default_initial_deposit
        sym_meta = SUPPORTED_SYMBOLS.get(strategy.symbol, {
            "pip_size": 0.0001, "point_value": 100000.0, "default_spread": 0.00015, "digits": 5
        })
        pip_size = sym_meta["pip_size"]
        point_val = sym_meta["point_value"]
        spread = (custom_spread_pips * pip_size) if custom_spread_pips is not None else sym_meta["default_spread"]
        slippage = custom_slippage_pips * pip_size
        fast_mode = (modeling_mode == "open_prices")
        precise_mode = modeling_mode in ("ohlc_m1", "tick")
        n_sub = (4 if modeling_mode == "ohlc_m1" else 10) if precise_mode else 0

        def _intra_path(o, h, l, c):
            anchors = (o, l, h, c) if c >= o else (o, h, l, c)
            pts = []
            for leg_a, leg_b in zip(anchors[:-1], anchors[1:]):
                for s_idx in range(n_sub):
                    pts.append(leg_a + (leg_b - leg_a) * (s_idx / n_sub))
            pts.append(anchors[-1])
            return pts

        exit_mode = getattr(strategy, "exit_mode", "ATR_CLASSIC")
        use_smoothed = (exit_mode == "ATR_SMOOTHED")
        atr_series = (
            indicator_engine.atr_smoothed(df, 14, 50).values if use_smoothed
            else indicator_engine.atr(df, 14).values
        )
        opens = df["Open"].values
        highs = df["High"].values
        lows = df["Low"].values
        closes = df["Close"].values
        times = list(df.index)  # Box timestamps once, rather than on every simulation bar.
        n = len(df)

        # Precompute structural swing levels (rolling min/max of lows/highs)
        swing_lo = None
        swing_hi = None
        if exit_mode == "STRUCTURE_SWING":
            wb = max(2, int(getattr(strategy, "swing_bars", 15)))
            swing_lo = pd.Series(lows).rolling(wb, min_periods=1).min().values
            swing_hi = pd.Series(highs).rolling(wb, min_periods=1).max().values

        buy_signals, sell_signals = self.generate_signal_arrays(df, strategy)

        # F: Multi-timeframe combinado — la entrada en el TF bajo exige confirmación
        # de la MISMA estrategia en el TF superior, usando solo barras HTF ya CERRADAS
        # (anti-lookahead: se resta la duración de la vela HTF antes de alinear).
        mtf_tf = getattr(strategy, "mtf_timeframe", None)
        if mtf_tf and htf_df is not None and len(htf_df) >= 2:
            h_buy, h_sell = self.generate_signal_arrays(htf_df, strategy)
            h_idx = htf_df.index
            h_dur = h_idx.to_series().diff().median()
            if pd.isna(h_dur) or h_dur <= pd.Timedelta(0):
                h_dur = pd.Timedelta(minutes=1)
            pos = h_idx.searchsorted(df.index - h_dur, side="right") - 1
            valid = pos >= 0
            pos_c = np.clip(pos, 0, None)
            h_buy_al = np.where(valid, h_buy[pos_c], False)
            h_sell_al = np.where(valid, h_sell[pos_c], False)
            buy_signals = buy_signals & h_buy_al
            sell_signals = sell_signals & h_sell_al

        # Simulation state
        balance = capital
        peak_equity = capital
        max_drawdown_usd = 0.0
        max_drawdown_pct = 0.0

        equity_curve = [{"time": str(times[0]), "equity": round(capital, 2), "balance": round(capital, 2)}]
        drawdown_curve = [{"time": str(times[0]), "drawdown_pct": 0.0}]
        trades = []

        current_trade = None
        consecutive_wins = 0
        consecutive_losses = 0
        max_consec_wins = 0
        max_consec_losses = 0

        # Period trackers
        current_day = times[0].date()
        day_start_balance = balance
        day_loss_locked = False
        day_gain_locked = False
        day_trades_count = 0

        # ISO week / month trackers
        iso_year, iso_week, _ = times[0].isocalendar()
        week_start_balance = balance
        week_loss_locked = False
        week_gain_locked = False

        month_key = (times[0].year, times[0].month)
        month_start_balance = balance
        month_loss_locked = False
        month_gain_locked = False

        account_gain_locked = False
        consec_loss_locked = False
        consec_win_locked = False

        max_open = max(1, int(getattr(strategy, "max_open_trades", 1)))
        # NOTE: engine manages a single dominant position (max_open=1 semantics for parallel safety).
        # When max_open > 1 the entry gate is more permissive but still one tracked slot per cycle.

        def _manage_bar_exit(chk_hi, chk_lo, ext_hi, ext_lo):
            nonlocal closed, exit_price, exit_reason, sl, balance, size_lots, partial_closed
            base_mode = exit_mode in ("ATR_CLASSIC", "PIPS_FIXED", "PCT_EXIT", "ATR_SMOOTHED")
            trail_mod = exit_mode == "TRAILING_ATR" or (base_mode and getattr(strategy, "modifier_trailing", False))
            be_mod = exit_mode == "BREAKEVEN" or (base_mode and getattr(strategy, "modifier_breakeven", False))
            if direction == "BUY":
                # Update trailing / breakeven / structure BEFORE touch checks so same-bar move applies
                if trail_mod:
                    highest_since = max(tr["mfe_price"], ext_hi)
                    tr["mfe_price"] = highest_since
                    new_sl = highest_since - (strategy.trail_atr * cur_atr)
                    if new_sl > sl:
                        tr["sl_price"] = new_sl
                        sl = new_sl
                if be_mod:
                    if not tr["be_activated"] and (ext_hi - entry_p) >= (strategy.be_atr * cur_atr):
                        tr["sl_price"] = entry_p + (spread / 2.0)
                        tr["be_activated"] = True
                        sl = tr["sl_price"]
                if exit_mode == "STRUCTURE_SWING" and swing_lo is not None:
                    new_sl = swing_lo[i]
                    # Only move SL in favor of the trade
                    if new_sl > sl and new_sl < entry_p:
                        tr["sl_price"] = new_sl
                        sl = new_sl
                elif exit_mode == "TIME_EXIT" and tr["bars_held"] >= strategy.max_bars:
                    closed = True
                    exit_price = closes[i]
                    exit_reason = "Time Exit"

                if not closed:
                    if chk_lo <= sl:
                        closed = True
                        exit_price = sl - slippage
                        exit_reason = "Stop Loss"
                    elif chk_hi >= tp:
                        # Partial TP handling
                        if exit_mode == "PARTIAL_TP" and not tr.get("partial_done", False) and tr.get("tp1_hit", False) is not True:
                            if ext_hi >= tr.get("tp1_price", tp) and ext_hi < tp:
                                # Hit TP1 first
                                tr["tp1_hit"] = True
                                closed = False
                            elif ext_hi >= tp:
                                closed = True
                                exit_price = tp
                                exit_reason = "Take Profit"
                        elif exit_mode == "PARTIAL_TP" and tr.get("partial_done", False):
                            if ext_hi >= tp:
                                closed = True
                                exit_price = tp
                                exit_reason = "Take Profit"
                        else:
                            closed = True
                            exit_price = tp
                            exit_reason = "Take Profit"

                    # PARTIAL_TP: realize partial when TP1 touched
                    if exit_mode == "PARTIAL_TP" and not tr.get("partial_done", False):
                        tp1 = tr.get("tp1_price")
                        if tp1 is not None and ext_hi >= tp1:
                            partial_pct = strategy.partial_pct / 100.0
                            partial_size = round(size_lots * partial_pct, 2)
                            if partial_size >= 0.01:
                                add_pnl = (tp1 - entry_p) * point_val * partial_size - commission_per_lot * partial_size
                                balance += add_pnl
                                tr["size_lots"] = round(size_lots - partial_size, 2)
                                size_lots = tr["size_lots"]
                                tr["partial_done"] = True
                                partial_closed = True
                                trades.append({
                                    "trade_num": int(len(trades) + 1),
                                    "symbol": str(strategy.symbol),
                                    "direction": str(direction),
                                    "entry_time": str(tr["entry_time"]),
                                    "entry_price": float(round(entry_p, sym_meta["digits"])),
                                    "exit_time": str(t),
                                    "exit_price": float(round(tp1, sym_meta["digits"])),
                                    "size_lots": float(partial_size),
                                    "pnl_usd": float(round(add_pnl, 2)),
                                    "pips": float(round((tp1 - entry_p) / pip_size, 1)),
                                    "bars_held": int(tr["bars_held"]),
                                    "exit_reason": "Partial TP1",
                                    "balance_after": float(round(balance, 2))
                                })
                                # Move SL to breakeven after partial
                                tr["sl_price"] = entry_p + (spread / 2.0)
                                sl = tr["sl_price"]

            else:  # SELL
                if trail_mod:
                    lowest_since = min(tr["mfe_price"], ext_lo)
                    tr["mfe_price"] = lowest_since
                    new_sl = lowest_since + (strategy.trail_atr * cur_atr)
                    if new_sl < sl:
                        tr["sl_price"] = new_sl
                        sl = new_sl
                if be_mod:
                    if not tr["be_activated"] and (entry_p - ext_lo) >= (strategy.be_atr * cur_atr):
                        tr["sl_price"] = entry_p - (spread / 2.0)
                        tr["be_activated"] = True
                        sl = tr["sl_price"]
                if exit_mode == "STRUCTURE_SWING" and swing_hi is not None:
                    new_sl = swing_hi[i]
                    if new_sl < sl and new_sl > entry_p:
                        tr["sl_price"] = new_sl
                        sl = new_sl
                elif exit_mode == "TIME_EXIT" and tr["bars_held"] >= strategy.max_bars:
                    closed = True
                    exit_price = closes[i]
                    exit_reason = "Time Exit"

                if not closed:
                    if chk_hi >= sl:
                        closed = True
                        exit_price = sl + slippage
                        exit_reason = "Stop Loss"
                    elif chk_lo <= tp:
                        if exit_mode == "PARTIAL_TP" and not tr.get("partial_done", False):
                            tp1 = tr.get("tp1_price")
                            if tp1 is not None and ext_lo <= tp1 and ext_lo > tp:
                                tr["tp1_hit"] = True
                            elif ext_lo <= tp:
                                closed = True
                                exit_price = tp
                                exit_reason = "Take Profit"
                        else:
                            closed = True
                            exit_price = tp
                            exit_reason = "Take Profit"

                    if exit_mode == "PARTIAL_TP" and not tr.get("partial_done", False):
                        tp1 = tr.get("tp1_price")
                        if tp1 is not None and ext_lo <= tp1:
                            partial_pct = strategy.partial_pct / 100.0
                            partial_size = round(size_lots * partial_pct, 2)
                            if partial_size >= 0.01:
                                add_pnl = (entry_p - tp1) * point_val * partial_size - commission_per_lot * partial_size
                                balance += add_pnl
                                tr["size_lots"] = round(size_lots - partial_size, 2)
                                size_lots = tr["size_lots"]
                                tr["partial_done"] = True
                                partial_closed = True
                                trades.append({
                                    "trade_num": int(len(trades) + 1),
                                    "symbol": str(strategy.symbol),
                                    "direction": str(direction),
                                    "entry_time": str(tr["entry_time"]),
                                    "entry_price": float(round(entry_p, sym_meta["digits"])),
                                    "exit_time": str(t),
                                    "exit_price": float(round(tp1, sym_meta["digits"])),
                                    "size_lots": float(partial_size),
                                    "pnl_usd": float(round(add_pnl, 2)),
                                    "pips": float(round((entry_p - tp1) / pip_size, 1)),
                                    "bars_held": int(tr["bars_held"]),
                                    "exit_reason": "Partial TP1",
                                    "balance_after": float(round(balance, 2))
                                })
                                tr["sl_price"] = entry_p - (spread / 2.0)
                                sl = tr["sl_price"]

        for i in range(1, n):
            t = times[i]
            t_date = t.date()

            # --- period rollovers ---
            if t_date != current_day:
                current_day = t_date
                day_start_balance = balance
                day_loss_locked = False
                day_gain_locked = False
                day_trades_count = 0
                consec_loss_locked = False
                consec_win_locked = False

            y, w, _ = t.isocalendar()
            if (y, w) != (iso_year, iso_week):
                iso_year, iso_week = y, w
                week_start_balance = balance
                week_loss_locked = False
                week_gain_locked = False

            m_key = (t.year, t.month)
            if m_key != month_key:
                month_key = m_key
                month_start_balance = balance
                month_loss_locked = False
                month_gain_locked = False

            cur_atr = max(atr_series[i], pip_size * 5.0)

            # ----------------------------------------------------
            # 1. Manage existing open trade
            # ----------------------------------------------------
            if current_trade is not None:
                tr = current_trade
                tr["bars_held"] += 1
                direction = tr["direction"]
                entry_p = tr["entry_price"]
                size_lots = tr["size_lots"]

                # Overnight swap accrual (one calendar day crossed)
                if tr.get("last_swap_day") != t_date:
                    if swap_long_per_lot or swap_short_per_lot:
                        sw = (swap_long_per_lot if direction == "BUY" else swap_short_per_lot) * size_lots
                        balance += sw
                    tr["last_swap_day"] = t_date

                # Dynamic exit prices
                sl = tr["sl_price"]
                tp = tr["tp_price"]

                closed = False
                partial_closed = False
                exit_price = 0.0
                exit_reason = ""

                # Weekend exit rule
                if strategy.close_before_weekend and t.weekday() == 4 and t.hour >= 20:
                    closed = True
                    exit_price = opens[i] if fast_mode else closes[i]
                    exit_reason = "Weekend Close"

                # NY close rule: block/exit from 20:00 UTC
                if not closed and getattr(strategy, "close_before_ny_close", False) and t.hour >= 20:
                    closed = True
                    exit_price = opens[i] if fast_mode else closes[i]
                    exit_reason = "NY Close"

                if not closed:
                    if precise_mode:
                        ext_hi = opens[i]
                        ext_lo = opens[i]
                        for sub_p in _intra_path(opens[i], highs[i], lows[i], closes[i]):
                            if sub_p > ext_hi:
                                ext_hi = sub_p
                            if sub_p < ext_lo:
                                ext_lo = sub_p
                            _manage_bar_exit(sub_p, sub_p, ext_hi, ext_lo)
                            if closed:
                                break
                    else:
                        # In fast mode only open/close prices matter
                        _manage_bar_exit(
                            opens[i] if fast_mode else highs[i],
                            opens[i] if fast_mode else lows[i],
                            highs[i],
                            lows[i],
                        )

                # Close full position
                if closed:
                    # If partially closed already, size_lots reflects remainder
                    size_lots = tr.get("size_lots", size_lots)
                    if direction == "BUY":
                        diff_points = (exit_price - entry_p)
                    else:
                        diff_points = (entry_p - exit_price)

                    pnl_raw = diff_points * point_val * size_lots
                    comm = commission_per_lot * size_lots
                    net_pnl = pnl_raw - comm
                    pips = round(diff_points / pip_size, 1)

                    balance += net_pnl

                    if net_pnl > 0:
                        consecutive_wins += 1
                        consecutive_losses = 0
                        max_consec_wins = max(max_consec_wins, consecutive_wins)
                    else:
                        consecutive_losses += 1
                        consecutive_wins = 0
                        max_consec_losses = max(max_consec_losses, consecutive_losses)

                    trade_rec = {
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
                    }
                    if tr.get("avg_levels", 0) > 0:
                        trade_rec["averaged_levels"] = tr["avg_levels"]
                    trades.append(trade_rec)

                    current_trade = None

                # ----------------------------------------------------
                # G: Averaging (DCA/piramidado) — añadir unidades a posición abierta
                # ----------------------------------------------------
                if current_trade is not None and getattr(strategy, "avg_enabled", False):
                    tr_a = current_trade
                    if tr_a.get("avg_levels", 0) < int(getattr(strategy, "avg_max_levels", 0)):
                        a_unit = getattr(strategy, "avg_spacing_unit", "atr")
                        a_val = float(getattr(strategy, "avg_spacing_value", 1.0) or 1.0)
                        if a_unit == "atr":
                            spacing = a_val * cur_atr
                        elif a_unit == "percent":
                            spacing = abs(tr_a["entry_price"]) * (a_val / 100.0)
                        else:
                            spacing = a_val * pip_size
                        a_mode = getattr(strategy, "avg_mode", "dca")
                        do_add = False
                        if tr_a["direction"] == "BUY":
                            if a_mode in ("dca", "both") and closes[i] <= tr_a["last_avg_price"] - spacing:
                                do_add = True
                            if a_mode in ("pyramiding", "both") and closes[i] >= tr_a["last_avg_price"] + spacing:
                                do_add = True
                        else:
                            if a_mode in ("dca", "both") and closes[i] >= tr_a["last_avg_price"] + spacing:
                                do_add = True
                            if a_mode in ("pyramiding", "both") and closes[i] <= tr_a["last_avg_price"] - spacing:
                                do_add = True
                        if do_add:
                            mult = float(getattr(strategy, "avg_size_multiplier", 1.0) or 1.0)
                            add_size = round(tr_a["initial_size_lots"] * mult, 2)
                            if add_size >= 0.01:
                                old_size = tr_a["size_lots"]
                                new_size = round(old_size + add_size, 2)
                                new_entry = (tr_a["entry_price"] * old_size + closes[i] * add_size) / new_size
                                tr_a["entry_price"] = new_entry
                                tr_a["size_lots"] = new_size
                                tr_a["avg_levels"] += 1
                                tr_a["last_avg_price"] = closes[i]
                                if getattr(strategy, "avg_recompute_stop", False):
                                    d_sl = abs(tr_a["initial_entry_price"] - tr_a["initial_sl_price"])
                                    if tr_a["direction"] == "BUY":
                                        tr_a["sl_price"] = new_entry - d_sl
                                    else:
                                        tr_a["sl_price"] = new_entry + d_sl

                    # --- risk limit updates after close ---
                    # Limits <= 0 are treated as disabled (free)
                    day_loss_pct = ((day_start_balance - balance) / day_start_balance) * 100.0 if day_start_balance > 0 else 0
                    mdl = getattr(strategy, "max_daily_loss_pct", 0.0)
                    if mdl > 0 and day_loss_pct >= mdl:
                        day_loss_locked = True
                    day_gain_pct = ((balance - day_start_balance) / day_start_balance) * 100.0 if day_start_balance > 0 else 0
                    mdg = getattr(strategy, "max_daily_gain_pct", 0.0)
                    if mdg > 0 and day_gain_pct >= mdg:
                        day_gain_locked = True

                    week_loss_pct = ((week_start_balance - balance) / week_start_balance) * 100.0 if week_start_balance > 0 else 0
                    mwl = getattr(strategy, "max_weekly_loss_pct", 0.0)
                    if mwl > 0 and week_loss_pct >= mwl:
                        week_loss_locked = True
                    mwg = getattr(strategy, "max_weekly_gain_pct", 0.0)
                    week_gain_pct = ((balance - week_start_balance) / week_start_balance) * 100.0 if week_start_balance > 0 else 0
                    if mwg > 0 and week_gain_pct >= mwg:
                        week_gain_locked = True

                    month_loss_pct = ((month_start_balance - balance) / month_start_balance) * 100.0 if month_start_balance > 0 else 0
                    mml = getattr(strategy, "max_monthly_loss_pct", 0.0)
                    if mml > 0 and month_loss_pct >= mml:
                        month_loss_locked = True
                    mmg = getattr(strategy, "max_monthly_gain_pct", 0.0)
                    month_gain_pct = ((balance - month_start_balance) / month_start_balance) * 100.0 if month_start_balance > 0 else 0
                    if mmg > 0 and month_gain_pct >= mmg:
                        month_gain_locked = True

                    mag = getattr(strategy, "max_account_gain_pct", 0.0)
                    if mag > 0 and ((balance - capital) / capital) * 100.0 >= mag:
                        account_gain_locked = True

                    mcw = getattr(strategy, "max_consecutive_wins", 0)
                    if mcw > 0 and consecutive_wins >= mcw:
                        consec_win_locked = True
                    mcl = getattr(strategy, "max_consecutive_losses", 0)
                    if mcl > 0 and consecutive_losses >= mcl:
                        consec_loss_locked = True

            # ----------------------------------------------------
            # 2. Check for new trade entry if flat
            # ----------------------------------------------------
            entry_blocked = (
                day_loss_locked or day_gain_locked or
                week_loss_locked or week_gain_locked or
                month_loss_locked or month_gain_locked or
                account_gain_locked or consec_loss_locked or consec_win_locked or
                day_trades_count >= strategy.max_daily_trades
            )

            if current_trade is None and not entry_blocked:
                total_loss_pct = ((capital - balance) / capital) * 100.0
                max_acct_loss = getattr(strategy, "max_account_loss_pct", 0.0)
                if max_acct_loss <= 0 or total_loss_pct < max_acct_loss:
                    sig_buy = buy_signals[i - 1]
                    sig_sell = sell_signals[i - 1]

                    if sig_buy or sig_sell:
                        trade_dir = "BUY" if sig_buy else "SELL"
                        base_open = opens[i]

                        # --- distance by exit mode ---
                        if exit_mode == "PIPS_FIXED":
                            sl_dist = strategy.sl_pips * pip_size
                            tp_dist = strategy.tp_pips * pip_size
                        elif exit_mode == "PCT_EXIT":
                            sl_dist = base_open * (strategy.sl_pct / 100.0)
                            tp_dist = base_open * (strategy.tp_pct / 100.0)
                        elif exit_mode == "ATR_SMOOTHED":
                            sl_dist = strategy.sl_smooth_mult * cur_atr
                            tp_dist = strategy.tp_smooth_mult * cur_atr
                        else:
                            sl_dist = strategy.sl_atr * cur_atr
                            tp_dist = strategy.tp_atr * cur_atr

                        # Fixed R:R override
                        frr = getattr(strategy, "fixed_rr", 0.0)
                        if frr and frr > 0:
                            tp_dist = sl_dist * frr

                        # Minimum reward:risk filter
                        rr_min = getattr(strategy, "reward_risk_ratio", 0.0)
                        if rr_min and rr_min > 0:
                            if (tp_dist / max(sl_dist, 1e-12)) < rr_min:
                                # Skip this signal: insufficient R:R
                                tp_dist = sl_dist * rr_min  # force compliant TP instead of dropping
                                if (tp_dist / max(sl_dist, 1e-12)) < rr_min * 0.999:
                                    pass

                        entry_type = getattr(strategy, "entry_order_type", "MARKET")
                        filled = False
                        entry_price = base_open

                        if fast_mode:
                            # open_prices: fill at open only
                            entry_price = base_open + (spread / 2.0 if trade_dir == "BUY" else -spread / 2.0)
                            filled = True
                        elif entry_type == "LIMIT":
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
                            entry_price = base_open + (spread / 2.0 if trade_dir == "BUY" else -spread / 2.0)
                            filled = True

                        if filled and entry_price > 0:
                            if trade_dir == "BUY":
                                sl_p = entry_price - sl_dist
                                tp_p = entry_price + tp_dist
                            else:
                                sl_p = entry_price + sl_dist
                                tp_p = entry_price - tp_dist

                            # Sizing with risk multiplier
                            risk_mult = getattr(strategy, "risk_multiplier", 1.0) or 1.0
                            if strategy.sizing_mode == "FIXED_LOT":
                                lot_size = strategy.fixed_lot
                            elif strategy.sizing_mode == "FIXED_CASH":
                                cash_risk = getattr(strategy, "fixed_cash_risk", 100.0) * risk_mult
                                price_risk = max(sl_dist, pip_size * 5)
                                lot_size = cash_risk / (price_risk * point_val)
                                lot_size = max(0.01, min(round(lot_size, 2), 50.0))
                            else:
                                risk_usd = balance * (strategy.risk_per_trade_pct / 100.0) * risk_mult
                                if strategy.sizing_mode == "MARTINGALE" and consecutive_losses > 0:
                                    risk_usd *= (strategy.martingale_mult ** min(consecutive_losses, 3))
                                elif strategy.sizing_mode == "ANTI_MARTINGALE" and consecutive_wins > 0:
                                    risk_usd *= (1.2 ** min(consecutive_wins, 3))
                                price_risk = max(sl_dist, pip_size * 5)
                                lot_size = risk_usd / (price_risk * point_val)
                                lot_size = max(0.01, min(round(lot_size, 2), 50.0))

                            # PARTIAL_TP: precompute TP1
                            tp1_price = None
                            if exit_mode == "PARTIAL_TP":
                                if trade_dir == "BUY":
                                    tp1_price = entry_price + (strategy.partial_tp1_atr * cur_atr)
                                    # ensure tp2 (=tp_p) > tp1
                                    if tp_p <= tp1_price:
                                        tp_p = tp1_price + (strategy.partial_tp2_atr - strategy.partial_tp1_atr) * cur_atr
                                else:
                                    tp1_price = entry_price - (strategy.partial_tp1_atr * cur_atr)
                                    if tp_p >= tp1_price:
                                        tp_p = tp1_price - (strategy.partial_tp2_atr - strategy.partial_tp1_atr) * cur_atr

                            current_trade = {
                                "direction": trade_dir,
                                "entry_time": t,
                                "entry_price": entry_price,
                                "sl_price": sl_p,
                                "tp_price": tp_p,
                                "tp1_price": tp1_price,
                                "partial_done": False,
                                "tp1_hit": False,
                                "size_lots": lot_size,
                                "initial_size_lots": lot_size,
                                "initial_entry_price": entry_price,
                                "initial_sl_price": sl_p,
                                "avg_levels": 0,
                                "last_avg_price": entry_price,
                                "bars_held": 0,
                                "mfe_price": entry_price,
                                "be_activated": False,
                                "last_swap_day": t_date
                            }
                            day_trades_count += 1

            # ----------------------------------------------------
            # 3. Track Drawdown and Equity
            # ----------------------------------------------------
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

            days_span = max((times[-1] - times[0]).days, 1)
            years = days_span / 365.25
            total_return_usd = balance - capital
            total_return_pct = (total_return_usd / capital) * 100.0
            cagr = ((balance / capital) ** (1.0 / max(years, 0.1)) - 1.0) * 100.0 if balance > 0 else -100.0

            daily_returns = pd.Series([e["equity"] for e in equity_curve]).pct_change().dropna()
            if len(daily_returns) > 5 and daily_returns.std() > 0:
                sharpe = float((daily_returns.mean() / daily_returns.std()) * np.sqrt(252 * (n / max(years * 252, 1) if n > 0 else 252)))
                neg_returns = daily_returns[daily_returns < 0]
                downside_std = neg_returns.std() if len(neg_returns) > 2 else daily_returns.std()
                sortino = float((daily_returns.mean() / max(downside_std, 1e-6)) * np.sqrt(252))
            else:
                sharpe = 0.0
                sortino = 0.0

            calmar = (cagr / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0
            recovery_factor = (total_return_usd / max_drawdown_usd) if max_drawdown_usd > 0 else 0.0

            sharpe_component = min(max(sharpe / 3.0, 0.0), 1.0) * 30.0
            calmar_component = min(max(calmar / 3.0, 0.0), 1.0) * 25.0
            pf_component = min(max((profit_factor - 1.0) / 1.5, 0.0), 1.0) * 20.0
            wr_component = min(max((win_rate - 35.0) / 35.0, 0.0), 1.0) * 15.0
            trade_count_penalty = min(total_trades / 30.0, 1.0)

            raw_score = (sharpe_component + calmar_component + pf_component + wr_component + (trade_count_penalty * 10.0))
            if max_drawdown_pct > 25.0:
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

        # Daily loss metric for prop-firm filters
        max_daily_loss_seen = 0.0
        # Recompute approximate daily loss from trades grouped by exit date
        if trades:
            by_day: Dict[Any, float] = {}
            for tr in trades:
                d = str(tr["exit_time"])[:10]
                by_day[d] = by_day.get(d, 0.0) + tr["pnl_usd"]
            worst_day = min(by_day.values()) if by_day else 0.0
            max_daily_loss_seen = abs(min(0.0, worst_day)) / capital * 100.0 if capital > 0 else 0.0

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
            "max_daily_loss_pct": float(round(max_daily_loss_seen, 2)),
            "tn_score": float(tn_score)
        }

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

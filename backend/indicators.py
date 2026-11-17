"""
Indicator Library for TradingNote Genetic Engine Replica
Vectorized implementations of 32 indicators across 7 families.
Includes content-fingerprint caching for rapid genetic exploration.
"""

import numpy as np
import hashlib
import pandas as pd
from typing import Dict, Tuple, Any, Callable


class IndicatorEngine:
    def __init__(self, max_cache: int = 8192):
        self._cache: Dict[Tuple, Any] = {}
        self.max_cache = max_cache
        self.hits = 0
        self.misses = 0

    @staticmethod
    def df_fingerprint(df: pd.DataFrame) -> Tuple:
        n = len(df)
        if n == 0:
            return (0, 0.0, 0.0, 0.0)
        digest=hashlib.blake2b(pd.util.hash_pandas_object(df,index=True).values.tobytes(),digest_size=16).hexdigest()
        return (n,tuple(df.columns),digest)

    def get_cache_key(self, df: pd.DataFrame, name: str, params: tuple) -> Tuple:
        return (self.df_fingerprint(df), name, params)

    def cached(self, df: pd.DataFrame, name: str, params: tuple, compute_fn: Callable[[], Any]) -> Any:
        key = self.get_cache_key(df, name, params)
        hit = self._cache.get(key)
        if hit is not None:
            self.hits += 1
            return hit
        self.misses += 1
        val = compute_fn()
        if len(self._cache) >= self.max_cache:
            for k in list(self._cache.keys())[: max(1, self.max_cache // 4)]:
                del self._cache[k]
        self._cache[key] = val
        return val

    def clear_cache(self):
        self._cache.clear()
        self.hits = 0
        self.misses = 0

    # ==========================================
    # 1. TREND FAMILY
    # ==========================================

    def ema(self, series: pd.Series, period: int = 50) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    def sma(self, series: pd.Series, period: int = 50) -> pd.Series:
        return series.rolling(window=period, min_periods=1).mean()

    def wma(self, series: pd.Series, period: int = 20) -> pd.Series:
        if period<1: raise ValueError('El período debe ser positivo')
        values=series.to_numpy(dtype=float)
        result=np.full(len(values),np.nan)
        if len(values)>=period:
            weights=np.arange(1,period+1,dtype=float)
            values=np.where(np.isfinite(values),values,np.nan)
            result[period-1:]=np.convolve(values,weights[::-1],mode='valid')/weights.sum()
        return pd.Series(result,index=series.index)

    def dema(self, series: pd.Series, period: int = 21) -> pd.Series:
        e1 = self.ema(series, period)
        e2 = self.ema(e1, period)
        return 2 * e1 - e2

    def tema(self, series: pd.Series, period: int = 21) -> pd.Series:
        e1 = self.ema(series, period)
        e2 = self.ema(e1, period)
        e3 = self.ema(e2, period)
        return 3 * e1 - 3 * e2 + e3

    def hma(self, series: pd.Series, period: int = 9) -> pd.Series:
        half_length = max(1, int(period / 2))
        sqrt_length = max(1, int(np.sqrt(period)))
        wma_half = self.wma(series, half_length)
        wma_full = self.wma(series, period)
        diff = 2 * wma_half - wma_full
        return self.wma(diff, sqrt_length)

    def kama(self, series: pd.Series, period: int = 10, fast: int = 2, slow: int = 30) -> pd.Series:
        def _compute():
            change = (series - series.shift(period)).abs()
            volatility = (series - series.shift(1)).abs().rolling(period).sum()
            er = change / volatility.replace(0, np.nan)
            er = er.fillna(0)
            fast_sc = 2.0 / (fast + 1)
            slow_sc = 2.0 / (slow + 1)
            sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
            kama_vals = np.zeros(len(series))
            kama_vals[:] = series.iloc[0]
            c_vals = series.values
            sc_vals = sc.values
            for i in range(1, len(series)):
                kama_vals[i] = kama_vals[i - 1] + sc_vals[i] * (c_vals[i] - kama_vals[i - 1])
            return pd.Series(kama_vals, index=series.index)
        return _compute()

    def supertrend(self, df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
        """Returns (trend_direction: +1/-1, supertrend_line)"""
        def _compute():
            atr_val = self.atr(df, period)
            hl2 = (df["High"] + df["Low"]) / 2.0
            upperband = hl2 + (multiplier * atr_val)
            lowerband = hl2 - (multiplier * atr_val)

            close = df["Close"].values
            upper = upperband.values.copy()
            lower = lowerband.values.copy()
            n = len(df)

            trend = np.ones(n)
            st_line = np.zeros(n)

            for i in range(1, n):
                if close[i - 1] > lower[i - 1]:
                    lower[i] = max(lower[i], lower[i - 1])
                if close[i - 1] < upper[i - 1]:
                    upper[i] = min(upper[i], upper[i - 1])

                if close[i] > upper[i - 1]:
                    trend[i] = 1
                elif close[i] < lower[i - 1]:
                    trend[i] = -1
                else:
                    trend[i] = trend[i - 1]

                st_line[i] = lower[i] if trend[i] == 1 else upper[i]

            return pd.Series(trend, index=df.index), pd.Series(st_line, index=df.index)
        return self.cached(df, "supertrend", (period, float(multiplier)), _compute)

    # ==========================================
    # 2. MOMENTUM FAMILY
    # ==========================================

    def rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi_val = 100 - (100 / (1 + rs))
        return rsi_val.fillna(50.0)

    def stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        def _compute():
            low_min = df["Low"].rolling(window=k_period).min()
            high_max = df["High"].rolling(window=k_period).max()
            k = 100.0 * ((df["Close"] - low_min) / (high_max - low_min).replace(0, np.nan))
            d = k.rolling(window=d_period).mean()
            return k.fillna(50.0), d.fillna(50.0)
        return self.cached(df, "stochastic", (k_period, d_period), _compute)

    def macd(self, series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        fast_ema = self.ema(series, fast)
        slow_ema = self.ema(series, slow)
        macd_line = fast_ema - slow_ema
        signal_line = self.ema(macd_line, signal)
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    def cci(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        def _compute():
            tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
            sma_tp = tp.rolling(period).mean()
            mean_dev = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
            cci_val = (tp - sma_tp) / (0.015 * mean_dev.replace(0, np.nan))
            return cci_val.fillna(0.0)
        return self.cached(df, "cci", (period,), _compute)

    def roc(self, series: pd.Series, period: int = 12) -> pd.Series:
        return ((series - series.shift(period)) / series.shift(period).replace(0, np.nan)) * 100.0

    def williams_r(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_max = df["High"].rolling(period).max()
        low_min = df["Low"].rolling(period).min()
        wr = -100.0 * ((high_max - df["Close"]) / (high_max - low_min).replace(0, np.nan))
        return wr.fillna(-50.0)

    # ==========================================
    # 3. VOLATILITY FAMILY
    # ==========================================

    def atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        def _compute():
            high = df["High"]
            low = df["Low"]
            close = df["Close"].shift(1)
            tr1 = high - low
            tr2 = (high - close).abs()
            tr3 = (low - close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        return self.cached(df, "atr", (period,), _compute)

    def atr_smoothed(self, df: pd.DataFrame, period: int = 14, smooth: int = 50) -> pd.Series:
        """ATR suavizado: media del ATR(14) de las últimas `smooth` velas."""
        base = self.atr(df, period)
        return base.rolling(smooth, min_periods=1).mean()

    def bollinger_bands(self, series: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        mid = series.rolling(period).mean()
        sigma = series.rolling(period).std()
        upper = mid + (std_dev * sigma)
        lower = mid - (std_dev * sigma)
        pct_b = (series - lower) / (upper - lower).replace(0, np.nan)
        return upper, mid, lower, pct_b.fillna(0.5)

    def keltner_channel(self, df: pd.DataFrame, period: int = 20, mult: float = 1.5) -> Tuple[pd.Series, pd.Series, pd.Series]:
        mid = self.ema(df["Close"], period)
        atr_val = self.atr(df, period)
        upper = mid + (mult * atr_val)
        lower = mid - (mult * atr_val)
        return upper, mid, lower

    def donchian_channel(self, df: pd.DataFrame, period: int = 20) -> Tuple[pd.Series, pd.Series, pd.Series]:
        upper = df["High"].rolling(period).max()
        lower = df["Low"].rolling(period).min()
        mid = (upper + lower) / 2.0
        return upper, mid, lower

    def std_dev(self, series: pd.Series, period: int = 20) -> pd.Series:
        return series.rolling(period).std().fillna(0.0)

    # ==========================================
    # 4. VOLUME FAMILY
    # ==========================================

    def volume_sma(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        vol = df["Volume"].replace(0, 1.0)
        return vol.rolling(period).mean().fillna(1.0)

    def obv(self, df: pd.DataFrame, signal: int = 20) -> pd.Series:
        def _compute():
            change = df["Close"].diff()
            direction = np.where(change > 0, 1, np.where(change < 0, -1, 0))
            obv_val = (direction * df["Volume"]).cumsum()
            s = pd.Series(obv_val, index=df.index)
            if signal and signal > 1:
                return s  # raw OBV; signal line available via obv_signal
            return s
        return self.cached(df, "obv", (signal,), _compute)

    def obv_signal(self, df: pd.DataFrame, signal: int = 20) -> pd.Series:
        return self.obv(df, signal).rolling(signal, min_periods=1).mean()

    def cmf(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        mfv = (((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (df["High"] - df["Low"]).replace(0, np.nan)) * df["Volume"]
        cmf_val = mfv.rolling(period).sum() / df["Volume"].rolling(period).sum().replace(0, np.nan)
        return cmf_val.fillna(0.0)

    def mfi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
        rmf = tp * df["Volume"]
        diff = tp.diff()
        pos_mf = np.where(diff > 0, rmf, 0.0)
        neg_mf = np.where(diff < 0, rmf, 0.0)
        pos_sum = pd.Series(pos_mf, index=df.index).rolling(period).sum()
        neg_sum = pd.Series(neg_mf, index=df.index).rolling(period).sum()
        mfi_val = 100 - (100 / (1 + pos_sum / neg_sum.replace(0, np.nan)))
        return mfi_val.fillna(50.0)

    # ==========================================
    # 5. PRICE FAMILY (breakout helpers)
    # ==========================================

    def highest(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        return df["High"].rolling(period, min_periods=1).max()

    def lowest(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        return df["Low"].rolling(period, min_periods=1).min()

    def pivot_points(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """Classic pivot points from previous bar OHLC (no lookahead)."""
        prev_o = df["Open"].shift(1)
        prev_h = df["High"].shift(1)
        prev_l = df["Low"].shift(1)
        prev_c = df["Close"].shift(1)
        pp = (prev_h + prev_l + prev_c) / 3.0
        r1 = 2 * pp - prev_l
        s1 = 2 * pp - prev_h
        r2 = pp + (prev_h - prev_l)
        s2 = pp - (prev_h - prev_l)
        r3 = prev_h + 2 * (pp - prev_l)
        s3 = prev_l - 2 * (prev_h - pp)
        return {
            "pp": pp, "r1": r1, "s1": s1,
            "r2": r2, "s2": s2, "r3": r3, "s3": s3
        }

    def vwap(self, df: pd.DataFrame) -> pd.Series:
        """VWAP real ponderado por volumen (typical price * volume acumulado)."""
        tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
        cum_vol = df["Volume"].replace(0, np.nan).fillna(1.0).cumsum()
        cum_pv = (tp * df["Volume"].replace(0, np.nan).fillna(1.0)).cumsum()
        return cum_pv / cum_vol

    # ==========================================
    # 6. CYCLE & ADVANCED STRUCTURAL
    # ==========================================

    def rci(self, series: pd.Series, period: int = 9) -> pd.Series:
        if period<1: raise ValueError('El período debe ser positivo')
        values=series.to_numpy(dtype=float)
        result=np.zeros(len(values))
        if period>1 and len(values)>=period:
            windows=np.lib.stride_tricks.sliding_window_view(values,period)
            # Bound temporary ranking arrays even for large imported periods.
            chunk_size=max(1,250000//period)
            time_ranks=np.arange(1,period+1)
            for start in range(0,len(windows),chunk_size):
                chunk=windows[start:start+chunk_size]
                order=np.argsort(-chunk,axis=1)
                ranks=np.empty_like(order)
                np.put_along_axis(ranks,order,np.broadcast_to(time_ranks,order.shape),axis=1)
                distance=np.sum((ranks-time_ranks)**2,axis=1)
                scores=(1.-6.*distance/(period*(period**2-1)))*100.
                scores[~np.isfinite(chunk).all(axis=1)]=0.
                result[period-1+start:period-1+start+len(chunk)]=scores
        return pd.Series(result,index=series.index)

    def adx(self, df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
        def _compute():
            high = df["High"]
            low = df["Low"]
            up_move = high.diff()
            down_move = -low.diff()
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
            tr = self.atr(df, period)
            plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / tr.replace(0, np.nan))
            minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / tr.replace(0, np.nan))
            dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
            adx_val = dx.ewm(alpha=1.0 / period, adjust=False).mean()
            return adx_val.fillna(20.0), plus_di.fillna(20.0), minus_di.fillna(20.0)
        return self.cached(df, "adx", (period,), _compute)

    def ichimoku(self, df: pd.DataFrame, tenkan_p: int = 9, kijun_p: int = 26, span_b_p: int = 52) -> Dict[str, pd.Series]:
        def _compute():
            tenkan = (df["High"].rolling(tenkan_p).max() + df["Low"].rolling(tenkan_p).min()) / 2.0
            kijun = (df["High"].rolling(kijun_p).max() + df["Low"].rolling(kijun_p).min()) / 2.0
            span_a = ((tenkan + kijun) / 2.0).shift(kijun_p)
            span_b = ((df["High"].rolling(span_b_p).max() + df["Low"].rolling(span_b_p).min()) / 2.0).shift(kijun_p)
            return {
                "tenkan": tenkan,
                "kijun": kijun,
                "span_a": span_a,
                "span_b": span_b
            }
        return self.cached(df, "ichimoku", (tenkan_p, kijun_p, span_b_p), _compute)

    def aroon(self, df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
        def _compute():
            high_period = df["High"].rolling(period + 1)
            low_period = df["Low"].rolling(period + 1)
            aroon_up = high_period.apply(lambda x: float(np.argmax(x)) / period * 100.0, raw=True)
            aroon_down = low_period.apply(lambda x: float(np.argmin(x)) / period * 100.0, raw=True)
            aroon_osc = aroon_up - aroon_down
            return aroon_up.fillna(50.0), aroon_down.fillna(50.0), aroon_osc.fillna(0.0)
        return self.cached(df, "aroon", (period,), _compute)

    def psar(self, df: pd.DataFrame, af_step: float = 0.02, af_max: float = 0.2) -> Tuple[pd.Series, pd.Series]:
        def _compute():
            high = df["High"].values
            low = df["Low"].values
            close = df["Close"].values
            n = len(df)

            psar = np.zeros(n)
            direction = np.zeros(n)

            bull = close[1] > close[0] if n > 1 else True
            direction[0] = 1 if bull else -1
            af = af_step
            ep = high[0] if bull else low[0]
            psar[0] = low[0] if bull else high[0]

            for i in range(1, n):
                prev_psar = psar[i - 1]
                if bull:
                    current_psar = prev_psar + af * (ep - prev_psar)
                    current_psar = min(current_psar, low[i - 1], low[max(0, i - 2)])
                    if low[i] < current_psar:
                        bull = False
                        current_psar = ep
                        ep = low[i]
                        af = af_step
                    else:
                        if high[i] > ep:
                            ep = high[i]
                            af = min(af + af_step, af_max)
                else:
                    current_psar = prev_psar + af * (ep - prev_psar)
                    current_psar = max(current_psar, high[i - 1], high[max(0, i - 2)])
                    if high[i] > current_psar:
                        bull = True
                        current_psar = ep
                        ep = high[i]
                        af = af_step
                    else:
                        if low[i] < ep:
                            ep = low[i]
                            af = min(af + af_step, af_max)
                psar[i] = current_psar
                direction[i] = 1 if bull else -1

            return pd.Series(psar, index=df.index), pd.Series(direction, index=df.index)
        return self.cached(df, "psar", (float(af_step), float(af_max)), _compute)


# Global singleton
indicator_engine = IndicatorEngine()

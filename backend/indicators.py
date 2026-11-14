"""
Indicator Library for TradingNote Genetic Engine Replica
Vectorized, ultra-fast implementations of all 28 indicators across 7 families.
Includes caching mechanism for rapid genetic exploration.
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Any

class IndicatorEngine:
    def __init__(self):
        # Cache keyed by: (df_id, indicator_name, param_tuple)
        self._cache: Dict[Tuple, Any] = {}

    def get_cache_key(self, df: pd.DataFrame, name: str, params: tuple) -> Tuple:
        return (id(df), len(df), name, params)

    # ==========================================
    # 1. TREND FAMILY
    # ==========================================

    def ema(self, series: pd.Series, period: int = 50) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    def sma(self, series: pd.Series, period: int = 50) -> pd.Series:
        return series.rolling(window=period, min_periods=1).mean()

    def wma(self, series: pd.Series, period: int = 20) -> pd.Series:
        weights = np.arange(1, period + 1)
        return series.rolling(period).apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)

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
        half_length = int(period / 2)
        sqrt_length = int(np.sqrt(period))
        wma_half = self.wma(series, half_length)
        wma_full = self.wma(series, period)
        diff = 2 * wma_half - wma_full
        return self.wma(diff, sqrt_length)

    def kama(self, series: pd.Series, period: int = 10, fast: int = 2, slow: int = 30) -> pd.Series:
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

    def supertrend(self, df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
        """Returns (trend_direction: +1/-1, supertrend_line)"""
        atr_val = self.atr(df, period)
        hl2 = (df["High"] + df["Low"]) / 2.0
        upperband = hl2 + (multiplier * atr_val)
        lowerband = hl2 - (multiplier * atr_val)
        
        close = df["Close"].values
        upper = upperband.values
        lower = lowerband.values
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
        low_min = df["Low"].rolling(window=k_period).min()
        high_max = df["High"].rolling(window=k_period).max()
        k = 100.0 * ((df["Close"] - low_min) / (high_max - low_min).replace(0, np.nan))
        d = k.rolling(window=d_period).mean()
        return k.fillna(50.0), d.fillna(50.0)

    def macd(self, series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        fast_ema = self.ema(series, fast)
        slow_ema = self.ema(series, slow)
        macd_line = fast_ema - slow_ema
        signal_line = self.ema(macd_line, signal)
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    def cci(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
        sma_tp = tp.rolling(period).mean()
        mean_dev = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
        cci_val = (tp - sma_tp) / (0.015 * mean_dev.replace(0, np.nan))
        return cci_val.fillna(0.0)

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
        high = df["High"]
        low = df["Low"]
        close = df["Close"].shift(1)
        tr1 = high - low
        tr2 = (high - close).abs()
        tr3 = (low - close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().bfill()

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

    def obv(self, df: pd.DataFrame) -> pd.Series:
        change = df["Close"].diff()
        direction = np.where(change > 0, 1, np.where(change < 0, -1, 0))
        obv_val = (direction * df["Volume"]).cumsum()
        return pd.Series(obv_val, index=df.index)

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
    # 5. CYCLE & ADVANCED STRUCTURAL
    # ==========================================

    def rci(self, series: pd.Series, period: int = 9) -> pd.Series:
        """
        Rank Correlation Index (Spearman Rank Correlation).
        Key TradingNote indicator: -100 to +100.
        """
        def _calc_spearman(chunk):
            n = len(chunk)
            d = 0.0
            order = np.argsort(-chunk)  # rank 1 is highest price
            price_ranks = np.empty_like(order)
            price_ranks[order] = np.arange(1, n + 1)
            time_ranks = np.arange(1, n + 1)
            d = np.sum((price_ranks - time_ranks) ** 2)
            rci = (1.0 - (6.0 * d) / (n * (n**2 - 1))) * 100.0
            return rci

        return series.rolling(period).apply(_calc_spearman, raw=True).fillna(0.0)

    def adx(self, df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Returns (ADX, Plus_DI, Minus_DI)"""
        high = df["High"]
        low = df["Low"]
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        tr = self.atr(df, period)
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(alpha=1.0/period, adjust=False).mean() / tr.replace(0, np.nan))
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(alpha=1.0/period, adjust=False).mean() / tr.replace(0, np.nan))
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
        adx_val = dx.ewm(alpha=1.0/period, adjust=False).mean()
        return adx_val.fillna(20.0), plus_di.fillna(20.0), minus_di.fillna(20.0)

    def ichimoku(self, df: pd.DataFrame, tenkan_p: int = 9, kijun_p: int = 26, span_b_p: int = 52) -> Dict[str, pd.Series]:
        tenkan = (df["High"].rolling(tenkan_p).max() + df["Low"].rolling(tenkan_p).min()) / 2.0
        kijun = (df["High"].rolling(kijun_p).max() + df["Low"].rolling(kijun_p).min()) / 2.0
        span_a = ((tenkan + kijun) / 2.0).shift(kijun_p)
        span_b = ((df["High"].rolling(span_b_p).max() + df["Low"].rolling(span_b_p).min()) / 2.0).shift(kijun_p)
        return {
            "tenkan": tenkan.bfill(),
            "kijun": kijun.bfill(),
            "span_a": span_a.bfill(),
            "span_b": span_b.bfill()
        }

    def aroon(self, df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Aroon Up, Aroon Down, and Aroon Oscillator."""
        high_period = df["High"].rolling(period + 1)
        low_period = df["Low"].rolling(period + 1)
        aroon_up = high_period.apply(lambda x: float(np.argmax(x)) / period * 100.0, raw=True)
        aroon_down = low_period.apply(lambda x: float(np.argmin(x)) / period * 100.0, raw=True)
        aroon_osc = aroon_up - aroon_down
        return aroon_up.fillna(50.0), aroon_down.fillna(50.0), aroon_osc.fillna(0.0)

    def psar(self, df: pd.DataFrame, af_step: float = 0.02, af_max: float = 0.2) -> Tuple[pd.Series, pd.Series]:
        """Returns (psar_value, psar_direction: +1 for long, -1 for short)"""
        high = df["High"].values
        low = df["Low"].values
        close = df["Close"].values
        n = len(df)
        
        psar = np.zeros(n)
        direction = np.zeros(n)
        
        # initialize
        bull = close[1] > close[0]
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

# Global singleton
indicator_engine = IndicatorEngine()

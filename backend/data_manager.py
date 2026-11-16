"""
Data Manager for TradingNote Genetic Engine Replica
Handles historical market data download, caching, resampling (1h -> 4h),
and automated daily updates.
"""

import os
import datetime
import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, List, Optional, Tuple

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

SUPPORTED_SYMBOLS = {
    "XAUUSD": {"ticker": "GC=F", "name": "Gold / US Dollar", "category": "Commodities", "pip_size": 0.1, "point_value": 100.0, "default_spread": 0.25, "digits": 2},
    "NASDAQ": {"ticker": "NQ=F", "name": "Nasdaq 100 E-mini", "category": "Indices", "pip_size": 1.0, "point_value": 20.0, "default_spread": 1.0, "digits": 2},
    "EURUSD": {"ticker": "EURUSD=X", "name": "Euro / US Dollar", "category": "Forex", "pip_size": 0.0001, "point_value": 100000.0, "default_spread": 0.00015, "digits": 5},
    "USDJPY": {"ticker": "JPY=X", "name": "US Dollar / Japanese Yen", "category": "Forex", "pip_size": 0.01, "point_value": 1000.0, "default_spread": 0.015, "digits": 3},
    "AUDUSD": {"ticker": "AUDUSD=X", "name": "Australian Dollar / USD", "category": "Forex", "pip_size": 0.0001, "point_value": 100000.0, "default_spread": 0.00018, "digits": 5},
    "GBPUSD": {"ticker": "GBPUSD=X", "name": "British Pound / USD", "category": "Forex", "pip_size": 0.0001, "point_value": 100000.0, "default_spread": 0.00020, "digits": 5},
    "US30": {"ticker": "YM=F", "name": "Dow Jones 30 E-mini", "category": "Indices", "pip_size": 1.0, "point_value": 5.0, "default_spread": 2.0, "digits": 1},
    "BTCUSD": {"ticker": "BTC-USD", "name": "Bitcoin / US Dollar", "category": "Crypto", "pip_size": 1.0, "point_value": 1.0, "default_spread": 10.0, "digits": 2},
    # --- TN universe expansion (21 adicionales → 29 activos) ---
    "USDCHF": {"ticker": "USDCHF=X", "name": "US Dollar / Swiss Franc", "category": "Forex", "pip_size": 0.0001, "point_value": 100000.0, "default_spread": 0.00020, "digits": 5},
    "USDCAD": {"ticker": "USDCAD=X", "name": "US Dollar / Canadian Dollar", "category": "Forex", "pip_size": 0.0001, "point_value": 100000.0, "default_spread": 0.00020, "digits": 5},
    "NZDUSD": {"ticker": "NZDUSD=X", "name": "New Zealand Dollar / USD", "category": "Forex", "pip_size": 0.0001, "point_value": 100000.0, "default_spread": 0.00022, "digits": 5},
    "EURJPY": {"ticker": "EURJPY=X", "name": "Euro / Japanese Yen", "category": "Forex", "pip_size": 0.01, "point_value": 1000.0, "default_spread": 0.020, "digits": 3},
    "GBPJPY": {"ticker": "GBPJPY=X", "name": "British Pound / Japanese Yen", "category": "Forex", "pip_size": 0.01, "point_value": 1000.0, "default_spread": 0.030, "digits": 3},
    "AUDJPY": {"ticker": "AUDJPY=X", "name": "Australian Dollar / Japanese Yen", "category": "Forex", "pip_size": 0.01, "point_value": 1000.0, "default_spread": 0.025, "digits": 3},
    "EURGBP": {"ticker": "EURGBP=X", "name": "Euro / British Pound", "category": "Forex", "pip_size": 0.0001, "point_value": 100000.0, "default_spread": 0.00020, "digits": 5},
    "XAGUSD": {"ticker": "SI=F", "name": "Silver / US Dollar", "category": "Commodities", "pip_size": 0.01, "point_value": 5000.0, "default_spread": 0.02, "digits": 3},
    "XPTUSD": {"ticker": "PL=F", "name": "Platinum / US Dollar", "category": "Commodities", "pip_size": 0.01, "point_value": 50.0, "default_spread": 0.30, "digits": 2},
    "USOIL": {"ticker": "CL=F", "name": "WTI Crude Oil", "category": "Commodities", "pip_size": 0.01, "point_value": 1000.0, "default_spread": 0.03, "digits": 2},
    "NGAS": {"ticker": "NG=F", "name": "Natural Gas", "category": "Commodities", "pip_size": 0.001, "point_value": 10000.0, "default_spread": 0.005, "digits": 3},
    "USTEC": {"ticker": "^NDX", "name": "Nasdaq 100 Cash", "category": "Indices", "pip_size": 1.0, "point_value": 20.0, "default_spread": 2.0, "digits": 1},
    "SPXUSD": {"ticker": "^GSPC", "name": "S&P 500 Cash", "category": "Indices", "pip_size": 1.0, "point_value": 50.0, "default_spread": 1.0, "digits": 1},
    "GER40": {"ticker": "^GDAXI", "name": "DAX 40 Cash", "category": "Indices", "pip_size": 1.0, "point_value": 25.0, "default_spread": 1.5, "digits": 1},
    "UK100": {"ticker": "^FTSE", "name": "FTSE 100 Cash", "category": "Indices", "pip_size": 1.0, "point_value": 10.0, "default_spread": 1.5, "digits": 1},
    "JPN225": {"ticker": "^N225", "name": "Nikkei 225 Cash", "category": "Indices", "pip_size": 1.0, "point_value": 5.0, "default_spread": 2.0, "digits": 1},
    "AUS200": {"ticker": "^AXJO", "name": "ASX 200 Cash", "category": "Indices", "pip_size": 1.0, "point_value": 25.0, "default_spread": 1.5, "digits": 1},
    "ETHUSD": {"ticker": "ETH-USD", "name": "Ethereum / US Dollar", "category": "Crypto", "pip_size": 0.1, "point_value": 1.0, "default_spread": 0.5, "digits": 2},
    "XRPUSD": {"ticker": "XRP-USD", "name": "Ripple / US Dollar", "category": "Crypto", "pip_size": 0.0001, "point_value": 1.0, "default_spread": 0.0002, "digits": 4},
    "SOLUSD": {"ticker": "SOL-USD", "name": "Solana / US Dollar", "category": "Crypto", "pip_size": 0.01, "point_value": 1.0, "default_spread": 0.05, "digits": 2},
    "LTCUSD": {"ticker": "LTC-USD", "name": "Litecoin / US Dollar", "category": "Crypto", "pip_size": 0.01, "point_value": 1.0, "default_spread": 0.05, "digits": 2},
}

# Timeframes served by this data layer (M30 = intraday 60d from yfinance)
SUPPORTED_TIMEFRAMES = ["1h", "30m", "4h", "1d"]

class DataManager:
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.memory_cache: Dict[str, pd.DataFrame] = {}

    def get_file_path(self, symbol: str, timeframe: str) -> str:
        return os.path.join(self.data_dir, f"{symbol.upper()}_{timeframe.lower()}.parquet")

    def resample_ohlcv(self, df_1h: pd.DataFrame, rule: str = "4h") -> pd.DataFrame:
        """Resample 1h OHLCV data into 4h or other timeframes cleanly."""
        resampled = df_1h.resample(rule).agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        }).dropna()
        return resampled

    def download_symbol_history(self, symbol: str) -> Dict[str, int]:
        """Download full available history for a symbol and cache 1h, 4h, and 1d."""
        meta = SUPPORTED_SYMBOLS.get(symbol)
        if not meta:
            raise ValueError(f"Symbol {symbol} not in supported symbols")
        
        ticker = meta["ticker"]
        results = {}

        # 1. Download 1h data (up to 730 days)
        df_1h = yf.download(ticker, period="730d", interval="1h", progress=False)
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = [col[0] for col in df_1h.columns]
        df_1h = df_1h[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df_1h.index = pd.to_datetime(df_1h.index)
        
        p1h = self.get_file_path(symbol, "1h")
        df_1h.to_parquet(p1h)
        results["1h"] = len(df_1h)

        # 1b. M30 intraday (yfinance limita intervalos <1h a 60 días)
        try:
            df_30m = yf.download(ticker, period="60d", interval="30m", progress=False)
            if isinstance(df_30m.columns, pd.MultiIndex):
                df_30m.columns = [col[0] for col in df_30m.columns]
            df_30m = df_30m[["Open", "High", "Low", "Close", "Volume"]].dropna()
            df_30m.index = pd.to_datetime(df_30m.index)
            df_30m.to_parquet(self.get_file_path(symbol, "30m"))
            results["30m"] = len(df_30m)
        except Exception:
            results["30m"] = 0

        # 2. Resample to 4h
        df_4h = self.resample_ohlcv(df_1h, "4h")
        p4h = self.get_file_path(symbol, "4h")
        df_4h.to_parquet(p4h)
        results["4h"] = len(df_4h)

        # 3. Download 5y 1d data
        df_1d = yf.download(ticker, period="5y", interval="1d", progress=False)
        if isinstance(df_1d.columns, pd.MultiIndex):
            df_1d.columns = [col[0] for col in df_1d.columns]
        df_1d = df_1d[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df_1d.index = pd.to_datetime(df_1d.index)
        
        p1d = self.get_file_path(symbol, "1d")
        df_1d.to_parquet(p1d)
        results["1d"] = len(df_1d)

        # Invalidate memory cache for this symbol
        keys_to_del = [k for k in self.memory_cache if k.startswith(f"{symbol}_")]
        for k in keys_to_del:
            del self.memory_cache[k]

        return results

    def auto_update_symbol(self, symbol: str) -> Dict[str, int]:
        """
        Auto-updates cached data by appending newly closed bars.
        Reads existing parquet, fetches delta, appends, and re-saves.
        """
        meta = SUPPORTED_SYMBOLS.get(symbol)
        if not meta:
            raise ValueError(f"Symbol {symbol} not in supported symbols")
        
        p1h = self.get_file_path(symbol, "1h")
        if not os.path.exists(p1h):
            return self.download_symbol_history(symbol)

        # Load existing 1h
        existing_1h = pd.read_parquet(p1h)
        last_dt = existing_1h.index[-1]
        
        # Download recent data (last 30 days) to get fresh bars
        ticker = meta["ticker"]
        new_df = yf.download(ticker, period="30d", interval="1h", progress=False)
        if isinstance(new_df.columns, pd.MultiIndex):
            new_df.columns = [col[0] for col in new_df.columns]
        new_df = new_df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        new_df.index = pd.to_datetime(new_df.index)

        # Combine and drop duplicates
        combined_1h = pd.concat([existing_1h, new_df])
        combined_1h = combined_1h[~combined_1h.index.duplicated(keep="last")].sort_index()
        combined_1h.to_parquet(p1h)

        # Recompute 4h
        combined_4h = self.resample_ohlcv(combined_1h, "4h")
        combined_4h.to_parquet(self.get_file_path(symbol, "4h"))

        # Refresh 30m (rolling 60d window — cheap full refresh)
        results_30m = 0
        try:
            df_30m = yf.download(ticker, period="60d", interval="30m", progress=False)
            if isinstance(df_30m.columns, pd.MultiIndex):
                df_30m.columns = [col[0] for col in df_30m.columns]
            df_30m = df_30m[["Open", "High", "Low", "Close", "Volume"]].dropna()
            df_30m.index = pd.to_datetime(df_30m.index)
            df_30m.to_parquet(self.get_file_path(symbol, "30m"))
            results_30m = len(df_30m)
        except Exception:
            p30 = self.get_file_path(symbol, "30m")
            if os.path.exists(p30):
                results_30m = len(pd.read_parquet(p30))

        # Update 1d
        p1d = self.get_file_path(symbol, "1d")
        if os.path.exists(p1d):
            existing_1d = pd.read_parquet(p1d)
            new_1d = yf.download(ticker, period="60d", interval="1d", progress=False)
            if isinstance(new_1d.columns, pd.MultiIndex):
                new_1d.columns = [col[0] for col in new_1d.columns]
            new_1d = new_1d[["Open", "High", "Low", "Close", "Volume"]].dropna()
            new_1d.index = pd.to_datetime(new_1d.index)
            combined_1d = pd.concat([existing_1d, new_1d])
            combined_1d = combined_1d[~combined_1d.index.duplicated(keep="last")].sort_index()
            combined_1d.to_parquet(p1d)
        else:
            combined_1d = pd.DataFrame()

        # Invalidate memory cache
        keys_to_del = [k for k in self.memory_cache if k.startswith(f"{symbol}_")]
        for k in keys_to_del:
            del self.memory_cache[k]

        return {
            "1h": len(combined_1h),
            "30m": results_30m,
            "4h": len(combined_4h),
            "1d": len(combined_1d) if not combined_1d.empty else 0
        }

    def update_all_symbols(self) -> Dict[str, Dict[str, int]]:
        """Updates all supported symbols."""
        results = {}
        for sym in SUPPORTED_SYMBOLS:
            try:
                results[sym] = self.auto_update_symbol(sym)
            except Exception as e:
                results[sym] = {"error": str(e)}
        return results

    def load_data(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Load historical OHLCV data for backtesting and exploration.
        Cached in memory for extreme speed.
        """
        cache_key = f"{symbol}_{timeframe}_{start_date}_{end_date}"
        if cache_key in self.memory_cache:
            return self.memory_cache[cache_key]

        fpath = self.get_file_path(symbol, timeframe)
        if not os.path.exists(fpath):
            # Try to download if missing
            self.download_symbol_history(symbol)

        if not os.path.exists(fpath):
            raise FileNotFoundError(f"Data not found for {symbol} ({timeframe})")

        df = pd.read_parquet(fpath)

        # Date filtering (end_date inclusive: whole day)
        if start_date or end_date:
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            if start_date:
                df = df[df.index >= pd.to_datetime(start_date, utc=True)]
            if end_date:
                df = df[df.index < pd.to_datetime(end_date, utc=True) + pd.Timedelta(days=1)]

        self.memory_cache[cache_key] = df
        return df

    def get_symbols_summary(self) -> List[Dict]:
        """Returns list of symbols with their metadata and available date ranges."""
        summary = []
        for sym, meta in SUPPORTED_SYMBOLS.items():
            sym_info = {
                "symbol": sym,
                "name": meta["name"],
                "category": meta["category"],
                "pip_size": meta["pip_size"],
                "point_value": meta["point_value"],
                "default_spread": meta["default_spread"],
                "digits": meta["digits"],
                "timeframes": {}
            }
            for tf in SUPPORTED_TIMEFRAMES:
                p = self.get_file_path(sym, tf)
                if os.path.exists(p):
                    try:
                        df = pd.read_parquet(p)
                        sym_info["timeframes"][tf] = {
                            "bars": len(df),
                            "start": str(df.index[0]),
                            "end": str(df.index[-1])
                        }
                    except Exception:
                        pass
            summary.append(sym_info)
        return summary

# Singleton instance
data_manager = DataManager()

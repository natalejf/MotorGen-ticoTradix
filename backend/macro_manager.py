"""
Macro economic data from FRED (Federal Reserve Economic Data).

- Public CSV endpoint (no API key): https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES
- Cached to data/macro/{SERIES}.parquet
- Publication alignment uses conservative calendar delays or explicit release
  timestamps; bars before the first release stay NaN. CSV data may be revised.
- A failed download without cache raises an explicit error, never invented data.
"""

import os
from typing import Dict, List, Optional

import pandas as pd

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
MACRO_DIR = os.path.join(DATA_DIR, "macro")

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"

# 11 TN categories condensed into available FRED series
FRED_CATALOG: Dict[str, Dict[str, str]] = {
    # Volatilidad y riesgo
    "VIXCLS": {"name": "VIX (volatilidad S&P 500)", "category": "Volatilidad y riesgo", "freq": "Diaria"},
    # Tasas de interés US
    "DGS10": {"name": "Treasury 10Y (%)", "category": "Tasas de interés US", "freq": "Diaria"},
    "DGS2": {"name": "Treasury 2Y (%)", "category": "Tasas de interés US", "freq": "Diaria"},
    "FEDFUNDS": {"name": "Fed Funds Rate (%)", "category": "Tasas de interés US", "freq": "Mensual"},
    # Dólar y FX
    "DTWEXBGS": {"name": "DXY (índice dólar amplio)", "category": "Dólar y FX", "freq": "Diaria"},
    # Inflación
    "CPIAUCSL": {"name": "CPI (inflación EE.UU.)", "category": "Inflación", "freq": "Mensual"},
    "PCEPI": {"name": "PCE (deflador)", "category": "Inflación", "freq": "Mensual"},
    # Mercado laboral
    "UNRATE": {"name": "Desempleo (%)", "category": "Mercado laboral", "freq": "Mensual"},
    # Actividad económica
    "GDP": {"name": "PIB EE.UU.", "category": "Actividad económica", "freq": "Trimestral"},
    # Monetaria y liquidez
    "M2SL": {"name": "M2 (masa monetaria)", "category": "Monetaria y liquidez", "freq": "Mensual"},
    # Commodities
    "DCOILWTICO": {"name": "Petróleo WTI", "category": "Commodities", "freq": "Diaria"},
    "GOLDAMGBD228NLBM": {"name": "Oro (London fixing)", "category": "Commodities", "freq": "Diaria"},
    # Sentimiento
    "UMCSENT": {"name": "Michigan Consumer Sentiment", "category": "Sentimiento", "freq": "Mensual"},
    # Derivados calculados (se computan a partir de DGS10 - DGS2)
    "YIELD_CURVE_10Y2Y": {"name": "Curva 10Y-2Y (spread)", "category": "Derivados calculados", "freq": "Diaria", "derived": "DGS10-DGS2"},
}

# Default threshold scan ranges per series for the genetic engine (from/step/to)
MACRO_RANGES: Dict[str, Dict[str, float]] = {
    "VIXCLS": {"from": 12.0, "step": 3.0, "to": 40.0},
    "DGS10": {"from": 0.5, "step": 0.5, "to": 5.5},
    "DGS2": {"from": 0.25, "step": 0.25, "to": 5.0},
    "FEDFUNDS": {"from": 0.0, "step": 0.25, "to": 6.0},
    "DTWEXBGS": {"from": 90.0, "step": 5.0, "to": 130.0},
    "CPIAUCSL": {"from": 1.0, "step": 1.0, "to": 9.0},
    "PCEPI": {"from": 1.0, "step": 1.0, "to": 6.0},
    "UNRATE": {"from": 3.0, "step": 0.5, "to": 10.0},
    "GDP": {"from": -2.0, "step": 1.0, "to": 8.0},
    "M2SL": {"from": -2.0, "step": 2.0, "to": 25.0},
    "DCOILWTICO": {"from": 30.0, "step": 15.0, "to": 120.0},
    "GOLDAMGBD228NLBM": {"from": 1200.0, "step": 400.0, "to": 2800.0},
    "UMCSENT": {"from": 50.0, "step": 10.0, "to": 110.0},
    "YIELD_CURVE_10Y2Y": {"from": -1.0, "step": 0.5, "to": 3.0},
}

# Additional FRED series. Thresholds are in the raw units returned by FRED.
for _sid, _name, _category, _freq, _lo, _step, _hi in [
    ('ECBDFR', 'ECB deposit facility (%)', 'Tasas internacionales', 'Diaria', -1, .5, 5),
    ('IRSTCI01JPM156N', 'Japan short-term rate (%)', 'Tasas internacionales', 'Mensual', -1, .25, 2),
    ('IR3TIB01GBM156N', 'UK interbank 3M (%)', 'Tasas internacionales', 'Mensual', 0, .5, 8),
    ('DEXJPUS', 'USD/JPY', 'Dólar y FX', 'Diaria', 80, 10, 180),
    ('PPIACO', 'Producer price index', 'Inflación', 'Mensual', 100, 25, 350),
    ('PAYEMS', 'Nóminas no agrícolas (miles)', 'Mercado laboral', 'Mensual', 100000, 10000, 180000),
    ('RSAFS', 'Ventas minoristas (millones USD)', 'Actividad económica', 'Mensual', 200000, 50000, 900000),
    ('BOGMBASE', 'Base monetaria (miles de millones USD)', 'Monetaria y liquidez', 'Mensual', 500, 500, 6500),
    ('TEDRATE', 'TED spread (%)', 'Monetaria y liquidez', 'Diaria', 0, .25, 3),
    ('HOUST', 'Housing starts (miles)', 'Vivienda', 'Mensual', 500, 250, 2500),
    ('MORTGAGE30US', 'Hipoteca 30 años (%)', 'Vivienda', 'Semanal', 2, 1, 10),
    ('BAMLH0A0HYM2', 'High yield spread (%)', 'Crédito', 'Diaria', 2, 1, 12),
    ('BAA10Y', 'BAA / Treasury spread (%)', 'Crédito', 'Diaria', 1, .5, 6),
    ('GFDEGDQ188S', 'Deuda federal / PIB (%)', 'Fiscal', 'Trimestral', 40, 10, 140),
    ('FYFSGDA188S', 'Balance fiscal / PIB (%)', 'Fiscal', 'Anual', -20, 2, 4),
]:
    FRED_CATALOG[_sid] = dict(name=_name, category=_category, freq=_freq)
    MACRO_RANGES[_sid] = {'from': float(_lo), 'step': float(_step), 'to': float(_hi)}

# Conservative calendar delays from observation-period start, not bar shifts.
# Explicit published_at indices may be supplied for exact release calendars.
PUBLICATION_LAGS = {'Diaria': 2, 'Semanal': 8, 'Mensual': 65, 'Trimestral': 125, 'Anual': 400}
for _sid, _meta in FRED_CATALOG.items():
    _meta['publication_lag_days'] = PUBLICATION_LAGS[_meta['freq']]
MACRO_RANGES.update({
    'CPIAUCSL': {'from': 150., 'step': 25., 'to': 400.},
    'PCEPI': {'from': 70., 'step': 10., 'to': 150.},
    'GDP': {'from': 10000., 'step': 2500., 'to': 35000.},
    'M2SL': {'from': 5000., 'step': 2500., 'to': 25000.},
})
CATALOG_LIST: List[str] = list(FRED_CATALOG.keys())


class MacroManager:
    def __init__(self, macro_dir: str = MACRO_DIR):
        self.macro_dir = macro_dir
        os.makedirs(self.macro_dir, exist_ok=True)
        self.memory_cache: Dict[str, pd.Series] = {}

    def _file_path(self, series_id: str) -> str:
        return os.path.join(self.macro_dir, f"{series_id.upper()}.parquet")

    def get_catalog(self) -> List[Dict]:
        out = []
        for sid, meta in FRED_CATALOG.items():
            out.append({
                "series_id": sid,
                "name": meta["name"],
                "category": meta["category"],
                "freq": meta["freq"],
                "publication_lag_days": meta['publication_lag_days'],
                "range": MACRO_RANGES.get(sid, {}),
                "cached": os.path.exists(self._file_path(sid)),
            })
        # group by category for UI
        return out

    def _fetch_csv(self, series_id: str) -> pd.Series:
        """Download FRED public CSV (no API key). Raises on failure."""
        import urllib.request
        url = FRED_CSV_URL.format(series_id=series_id)
        req = urllib.request.Request(url, headers={"User-Agent": "TradingNoteGenetic/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8")
        from io import StringIO
        df = pd.read_csv(StringIO(raw))
        # FRED CSV: first col DATE, second col value (sometimes named series_id)
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["date", "value"])
        # FRED uses "." for missing -> already coerced to NaN then dropped
        series = df.set_index("date")["value"].sort_index()
        series.name = series_id
        return series

    def load_series(self, series_id: str, allow_fetch: bool = True) -> pd.Series:
        """Load a series: memory cache -> parquet -> fetch -> explicit failure."""
        sid = series_id.upper()
        if sid not in FRED_CATALOG:
            raise ValueError(f'Unknown FRED series: {sid}')
        if sid in self.memory_cache:
            return self.memory_cache[sid]

        fpath = self._file_path(sid)
        series: Optional[pd.Series] = None

        if os.path.exists(fpath):
            try:
                loaded = pd.read_parquet(fpath)
                if isinstance(loaded, pd.DataFrame):
                    series = loaded.iloc[:, 0]
                else:
                    series = loaded
                series = pd.Series(series)
            except Exception:
                series = None

        if series is None and allow_fetch and sid in FRED_CATALOG:
            derived = FRED_CATALOG[sid].get("derived")
            if derived:
                # derived like "DGS10-DGS2"
                a, b = derived.split("-")
                sa = self.load_series(a, allow_fetch=True)
                sb = self.load_series(b, allow_fetch=True)
                series = (sa - sb).rename(sid)
            else:
                try:
                    series = self._fetch_csv(sid)
                except Exception:
                    series = None

        if series is None or series.empty:
            raise RuntimeError(f'FRED {sid}: descarga y caché no disponibles')

        series = series.dropna().sort_index()
        # NOTE: pd.Series has no to_parquet in this pandas version -> wrap in DataFrame
        try:
            series.to_frame(name=sid).to_parquet(fpath)
        except Exception:
            pass
        self.memory_cache[sid] = series
        return series

    def align_to_index(self, series, index, lag_days=None, published_at=None):
        """As-of release alignment. Never backfill before the first publication.

        published_at is an optional sequence of actual release timestamps matching
        observations. Otherwise the catalog's conservative calendar lag is used.
        Historical revisions require vintage data; these delays do not undo them.
        """
        sid = str(series.name or '').upper()
        delay = FRED_CATALOG.get(sid, {}).get('publication_lag_days', 2) if lag_days is None else lag_days
        def naive(values):
            ix = pd.DatetimeIndex(values)
            return ix.tz_convert('UTC').tz_localize(None) if ix.tz is not None else ix
        releases = naive(published_at) if published_at is not None else naive(series.index) + pd.Timedelta(days=delay)
        available = pd.Series(series.to_numpy(dtype=float), index=releases).dropna()
        available = available.groupby(level=0).last().sort_index()
        target = naive(index)
        values = available.reindex(target, method='ffill').to_numpy()
        return pd.Series(values, index=index, name=series.name)

    def attach_macro(self, df: pd.DataFrame, series_ids: List[str]) -> pd.DataFrame:
        """
        Return a copy of df with MACRO_{ID} columns aligned anti-lookahead.
        Safe to call multiple times (existing columns are kept).
        """
        if not series_ids:
            return df
        out = df
        new_cols = {}
        for sid in series_ids:
            col = f"MACRO_{sid.upper()}"
            if col in df.columns:
                continue
            try:
                ser = self.load_series(sid)
                new_cols[col] = self.align_to_index(ser, df.index)
            except Exception as exc:
                raise RuntimeError(f'No se pudo incorporar {sid}: {exc}') from exc
        if not new_cols:
            return out
        out = df.copy()
        for col, vals in new_cols.items():
            out[col] = vals.values
        return out

    def update_all(self, series_ids: Optional[List[str]] = None) -> Dict[str, str]:
        """Force re-download of series (bypass cache)."""
        ids = series_ids or CATALOG_LIST
        results = {}
        for sid in ids:
            try:
                if sid.upper() in FRED_CATALOG and not FRED_CATALOG[sid.upper()].get("derived"):
                    fpath = self._file_path(sid)
                    if os.path.exists(fpath):
                        os.remove(fpath)
                    self.memory_cache.pop(sid.upper(), None)
                    s = self.load_series(sid, allow_fetch=True)
                    results[sid] = f"ok ({len(s)} pts)"
                else:
                    results[sid] = "derived/cached"
            except Exception as e:
                results[sid] = f"error: {e}"
        return results


macro_manager = MacroManager()

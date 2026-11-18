"""
Complete Genetic Engine & Strategy Factory Replica for TradingNote
Implements:
- Population generation & smart seeding with all 32 indicators
- Random search mode (pure sweep) AND genetic evolution mode
- Parameter range sweep (From / Step / To) with combination counter
- Continuous / Infinite exploration mode (runs until user stops)
- Parallel backtest evaluation (ProcessPool with shared data)
- Dedicated Classification filters (Win Rate, Trades, Max DD, Net Profit, Sharpe, PF, DSR)
- Order Entry Types (Market, Limit, Stop) & 9 Exit Types
- Dynamic counters: Creadas, Descartadas, Aceptadas
- 3D Genealogy tree generation for Neural Explorer
- Thread-safe background execution with real-time callbacks
"""

import math
import copy
import random
import threading
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Callable, Tuple
from backend.strategy import Strategy, Condition
from backend.operators import compatible
from backend.exploration_policy import ACCOUNT_LIMITS, normalize_config
from backend.backtester import backtester, BacktestResult
from backend.validation import validation_suite
from backend.data_manager import data_manager

# ---------------------------------------------------------------------------
# INDICATOR UNIVERSE (32) with From/Step/To ranges per parameter
# ---------------------------------------------------------------------------
ALL_28_INDICATORS: Dict[str, Dict[str, Any]] = {
    # 1. Tendencia (8)
    "EMA": {"name": "Media Móvil Exponencial", "family": "Tendencia",
            "params": {"period": {"from": 10, "step": 10, "to": 200}}, "default_param": "period"},
    "SMA": {"name": "Media Móvil Simple", "family": "Tendencia",
            "params": {"period": {"from": 20, "step": 20, "to": 200}}, "default_param": "period"},
    "DEMA": {"name": "Doble Media Exponencial", "family": "Tendencia",
             "params": {"period": {"from": 9, "step": 5, "to": 100}}, "default_param": "period"},
    "TEMA": {"name": "Triple Media Exponencial", "family": "Tendencia",
             "params": {"period": {"from": 9, "step": 5, "to": 100}}, "default_param": "period"},
    "HMA": {"name": "Hull Moving Average", "family": "Tendencia",
            "params": {"period": {"from": 9, "step": 3, "to": 50}}, "default_param": "period"},
    "WMA": {"name": "Media Ponderada Lineal", "family": "Tendencia",
            "params": {"period": {"from": 10, "step": 5, "to": 100}}, "default_param": "period"},
    "KAMA": {"name": "Kaufman Adaptive MA", "family": "Tendencia",
             "params": {"period": {"from": 10, "step": 5, "to": 50},
                        "fast": {"from": 2, "step": 1, "to": 5},
                        "slow": {"from": 20, "step": 5, "to": 40}}, "default_param": "period"},
    "SUPERTREND": {"name": "SuperTrend ATR Channel", "family": "Tendencia",
                   "params": {"period": {"from": 7, "step": 7, "to": 21},
                              "multiplier": {"from": 1.5, "step": 0.5, "to": 4.0}}, "default_param": "period"},

    # 2. Momentum (6)
    "RSI": {"name": "Relative Strength Index", "family": "Momentum",
            "params": {"period": {"from": 7, "step": 7, "to": 28},
                       "threshold_low": {"from": 20, "step": 5, "to": 40},
                       "threshold_high": {"from": 60, "step": 5, "to": 80}}, "default_param": "period"},
    "STOCHASTIC": {"name": "Estocástico (%K & %D)", "family": "Momentum",
                   "params": {"k_period": {"from": 9, "step": 3, "to": 21},
                              "d_period": {"from": 2, "step": 1, "to": 5},
                              "threshold_low": {"from": 15, "step": 5, "to": 30},
                              "threshold_high": {"from": 70, "step": 5, "to": 85}}, "default_param": "k_period"},
    "MACD": {"name": "MACD (Histograma & Señal)", "family": "Momentum",
             "params": {"fast": {"from": 8, "step": 2, "to": 16},
                        "slow": {"from": 20, "step": 2, "to": 32},
                        "signal": {"from": 5, "step": 2, "to": 13}}, "default_param": "fast"},
    "CCI": {"name": "Commodity Channel Index", "family": "Momentum",
            "params": {"period": {"from": 14, "step": 6, "to": 40},
                       "threshold": {"from": 75, "step": 25, "to": 200}}, "default_param": "period"},
    "ROC": {"name": "Rate of Change", "family": "Momentum",
            "params": {"period": {"from": 8, "step": 4, "to": 24}}, "default_param": "period"},
    "WILLIAMS_R": {"name": "Williams %R", "family": "Momentum",
                   "params": {"period": {"from": 10, "step": 4, "to": 28},
                              "threshold_low": {"from": -85, "step": 5, "to": -60},
                              "threshold_high": {"from": -40, "step": 5, "to": -15}}, "default_param": "period"},

    # 3. Volatilidad (5)
    "BOLLINGER": {"name": "Bandas de Bollinger (%B)", "family": "Volatilidad",
                  "params": {"period": {"from": 10, "step": 10, "to": 50},
                             "std_dev": {"from": 1.5, "step": 0.5, "to": 3.0}}, "default_param": "period"},
    "ATR": {"name": "Average True Range", "family": "Volatilidad",
            "params": {"period": {"from": 10, "step": 2, "to": 24}}, "default_param": "period"},
    "KELTNER": {"name": "Canales de Keltner", "family": "Volatilidad",
                "params": {"period": {"from": 10, "step": 5, "to": 40},
                           "multiplier": {"from": 1.0, "step": 0.5, "to": 3.0}}, "default_param": "period"},
    "DONCHIAN": {"name": "Canales de Donchian", "family": "Volatilidad",
                 "params": {"period": {"from": 10, "step": 5, "to": 50}}, "default_param": "period"},
    "STDDEV": {"name": "Desviación Estándar", "family": "Volatilidad",
               "params": {"period": {"from": 10, "step": 5, "to": 50}}, "default_param": "period"},

    # 4. Volumen (4)
    "VOLUME_SMA": {"name": "SMA de Volumen", "family": "Volumen",
                   "params": {"period": {"from": 10, "step": 5, "to": 50}}, "default_param": "period"},
    "OBV": {"name": "On-Balance Volume", "family": "Volumen",
            "params": {"signal": {"from": 10, "step": 5, "to": 40}}, "default_param": "signal"},
    "CMF": {"name": "Chaikin Money Flow", "family": "Volumen",
            "params": {"period": {"from": 10, "step": 5, "to": 40}}, "default_param": "period"},
    "MFI": {"name": "Money Flow Index", "family": "Volumen",
            "params": {"period": {"from": 10, "step": 4, "to": 28},
                       "threshold_low": {"from": 20, "step": 5, "to": 40},
                       "threshold_high": {"from": 60, "step": 5, "to": 80}}, "default_param": "period"},

    # 5. Precio / Breakout (4) — added for TN parity
    "HIGHEST": {"name": "Máximo N períodos", "family": "Precio",
                "params": {"period": {"from": 10, "step": 5, "to": 50}}, "default_param": "period"},
    "LOWEST": {"name": "Mínimo N períodos", "family": "Precio",
               "params": {"period": {"from": 10, "step": 5, "to": 50}}, "default_param": "period"},
    "PIVOT_POINTS": {"name": "Pivot Points Clásicos", "family": "Precio",
                     "params": {"sub": {"values": ["pp", "r1", "s1", "r2", "s2"]}}, "default_param": "sub"},
    "VWAP": {"name": "VWAP (ponderado por volumen)", "family": "Precio",
             "params": {}, "default_param": None},

    # 6. Ciclo & Estructurales (5)
    "RCI": {"name": "Rank Correlation Index (RCI)", "family": "Ciclo",
            "params": {"period": {"from": 7, "step": 2, "to": 21}}, "default_param": "period"},
    "ADX": {"name": "Average Directional Index", "family": "Ciclo",
            "params": {"period": {"from": 10, "step": 5, "to": 25},
                       "threshold": {"from": 15, "step": 5, "to": 35}}, "default_param": "period"},
    "PSAR": {"name": "Parabolic SAR", "family": "Ciclo",
             "params": {"step": {"from": 0.01, "step": 0.01, "to": 0.04},
                        "max_step": {"from": 0.1, "step": 0.05, "to": 0.3}}, "default_param": "step"},
    "ICHIMOKU": {"name": "Ichimoku Kinko Hyo", "family": "Ciclo",
                 "params": {"tenkan_p": {"from": 7, "step": 1, "to": 12},
                            "kijun_p": {"from": 20, "step": 2, "to": 34},
                            "span_b_p": {"from": 40, "step": 4, "to": 60}}, "default_param": "tenkan_p"},
    "AROON": {"name": "Aroon Oscillator", "family": "Ciclo",
              "params": {"period": {"from": 10, "step": 4, "to": 25}}, "default_param": "period"},
}

# Backwards-compatible aliases used by older code/tests
ALL_INDICATORS = ALL_28_INDICATORS

# ---------------------------------------------------------------------------
# Legacy name retained for imports; FRED is no longer an exploration universe.
MACRO_INDICATORS: Dict[str, Dict[str, Any]] = {}


def is_macro_indicator(name: str) -> bool:
    return str(name).upper().startswith("MACRO_")


def combined_indicator_meta(name: str) -> Dict[str, Any]:
    u = str(name).upper()
    return ALL_28_INDICATORS.get(u) or MACRO_INDICATORS.get(u) or {}

ALL_ENTRY_TYPES = ["MARKET", "LIMIT", "STOP"]
ALL_EXIT_MODES = [
    "ATR_CLASSIC", "PIPS_FIXED", "PCT_EXIT", "TRAILING_ATR", "BREAKEVEN",
    "STRUCTURE_SWING", "TIME_EXIT", "PARTIAL_TP", "ATR_SMOOTHED"
]
SESSION_FILTERS = ["ALL", "SYDNEY", "TOKYO", "OVERLAP_TOKYO_LDN", "LONDON", "NEW_YORK", "OVERLAP_LDN_NY"]
SIZING_MODES = ["FIXED_RISK", "FIXED_LOT", "MARTINGALE", "ANTI_MARTINGALE"]
OPTIMIZATION_OBJECTIVES = [
    "tn_score", "sharpe", "sortino", "calmar", "pnl", "drawdown",
    "profit_factor", "expectancy", "win_rate", "recovery_factor", "pass_rate"
]
# F: minutos por vela — orden de TFs para el modo multi-timeframe combinado
TF_MINUTES = {"30m": 30, "1h": 60, "4h": 240, "1d": 1440}


# ---------------------------------------------------------------------------
# RANGE SWEEP HELPERS
# ---------------------------------------------------------------------------
def range_values(cfg: Dict[str, Any]) -> List[Any]:
    """Expand a From/Step/To (or values list) config into discrete points."""
    if not cfg:
        return [None]
    if "values" in cfg:
        return list(cfg["values"])
    start = float(cfg.get("from", 0))
    try:
        step = float(cfg.get("step", 1))
    except (TypeError, ValueError):
        step = 1.0
    end = float(cfg.get("to", start))
    if step <= 0:
        # Paso inválido (0 o negativo): un solo punto para no barre erroneamente
        return [start]
    vals = []
    v = start
    # guard against float drift
    while v <= end + 1e-9:
        vals.append(int(v) if abs(v - round(v)) < 1e-9 and step >= 1 else round(v, 4))
        v += step
        if len(vals) > 500:
            break
    return vals or [start]


def sample_from_range(cfg: Dict[str, Any], rng: random.Random) -> Any:
    vals = range_values(cfg)
    return rng.choice(vals)


def cross_op(is_buy: bool, rng: random.Random) -> str:
    """Crossover operator with a chance of CROSS_BOTH (TN 'cruza ambos')."""
    if rng.random() < 0.15:
        return "CROSS_BOTH"
    return "CROSS_ABOVE" if is_buy else "CROSS_BELOW"


# Exit/risk params sweepable from the UI (TN: barrido de salidas/riesgo)
EXIT_SWEEP_PARAMS = [
    "sl_atr", "tp_atr", "sl_pips", "tp_pips", "sl_pct", "tp_pct",
    "sl_smooth_mult", "tp_smooth_mult", "trail_atr", "be_atr",
    "swing_bars", "max_bars", "partial_tp1_atr", "partial_tp2_atr", "partial_pct",
]


def count_combinations(enabled_indicators: List[str], param_ranges: Optional[Dict[str, Any]] = None,
                       exit_ranges: Optional[Dict[str, Any]] = None) -> int:
    """Product of all possible parameter values across enabled indicators (TN combination counter).

    param_ranges: optional per-indicator override {IND: {param: {from, step, to} | {values: [...]}}}
    applied on top of the built-in metadata (user-edited ranges from the UI).
    exit_ranges: optional exit/risk sweep {param: {from, step, to} | {values: [...]}}.
    """
    total = 1
    for name in enabled_indicators:
        meta = combined_indicator_meta(name)
        if not meta:
            continue
        overrides = (param_ranges or {}).get(str(name).upper()) or {}
        for _pname, pcfg in (meta.get("params") or {}).items():
            ov = overrides.get(_pname)
            if ov and ("from" in ov or "values" in ov):
                pcfg = ov
            n = len(range_values(pcfg))
            total *= max(1, n)
            if total > 10**12:
                return total
    for _ep, ecfg in (exit_ranges or {}).items():
        if _ep in EXIT_SWEEP_PARAMS and isinstance(ecfg, dict) and ("from" in ecfg or "values" in ecfg):
            total *= max(1, len(range_values(ecfg)))
            if total > 10**12:
                return total
    return total


# ---------------------------------------------------------------------------
# PARALLEL BACKTEST WORKER (module-level for pickling) — MULTI-SYMBOL
# ---------------------------------------------------------------------------
_WORKER_DFS: Dict[str, pd.DataFrame] = {}
_WORKER_KWARGS: Dict[str, Any] = {}


def _init_worker(dfs_pickle_b64: str, kwargs: Dict[str, Any]):
    """Initializer for process pool workers (Windows spawn-safe).
    Receives a pickled Dict[key, DataFrame] where key = f"{symbol}_{timeframe}".
    """
    global _WORKER_DFS, _WORKER_KWARGS
    import base64, pickle
    _WORKER_DFS = pickle.loads(base64.b64decode(dfs_pickle_b64))
    _WORKER_KWARGS = kwargs


def _worker_df_for(strat: Strategy) -> pd.DataFrame:
    key = f"{strat.symbol}_{strat.timeframe}"
    if key in _WORKER_DFS:
        return _WORKER_DFS[key]
    # fallback: first available frame (should not happen if parent built pairs right)
    if _WORKER_DFS:
        return next(iter(_WORKER_DFS.values()))
    raise RuntimeError("Worker has no dataframes loaded")


def _worker_eval(payload: Tuple[Dict[str, Any], float]) -> Dict[str, Any]:
    """Evaluate a single strategy dict in a worker process; returns serializable result."""
    strat_dict, deposit = payload
    strat = Strategy.from_dict(strat_dict)
    df = _worker_df_for(strat)
    htf_df = None
    if getattr(strat, "mtf_timeframe", None):
        htf_df = _WORKER_DFS.get(f"{strat.symbol}_{strat.mtf_timeframe}")
    res = backtester.run_backtest(strat, df, initial_deposit=deposit,
                                  htf_df=htf_df, **_WORKER_KWARGS)
    return {
        "strategy_id": strat.id,
        "metrics": res.metrics,
        "equity_curve": res.equity_curve,
        "trades": res.trades,
        "drawdown_curve": res.drawdown_curve,
    }


class GeneticEngine:
    def __init__(self):
        self.is_running = False
        self.should_stop = False
        self._thread: Optional[threading.Thread] = None

        # Live Counters
        self.tested_count: int = 0
        self.discarded_count: int = 0
        self.accepted_count: int = 0

        self.progress_pct: float = 0.0
        self.current_generation: int = 0
        self.is_infinite_mode: bool = True
        self.population_size: int = 30
        self.search_mode: str = "genetic"
        self.total_combinations: int = 0
        # User-edited per-parameter sweep ranges {IND: {param: {from, step, to}}}
        self.param_ranges: Dict[str, Any] = {}
        self.enabled_operators = None
        self.rejection_counts = {}
        self.no_trade_count = 0
        # Exploration date range (start_date, end_date) — inclusive, None = full
        self.date_range: Tuple[Optional[str], Optional[str]] = (None, None)
        # Additional validators (WF/MV) config applied during exploration
        self.validator_cfg: Dict[str, Any] = {}

        self.candidates_passed: List[Dict[str, Any]] = []
        self.best_candidate: Optional[Dict[str, Any]] = None
        self.log_messages: List[str] = []

        # 3D Neural Explorer Tree (Nodes and Axons)
        self.neural_nodes: List[Dict[str, Any]] = []
        self.neural_edges: List[Dict[str, Any]] = []

        # Deduplication sets
        self.seen_signatures: set = set()
        self.seen_perf_signatures: set = set()

        self.lock = threading.Lock()

    def reset_state(self):
        with self.lock:
            self.tested_count = 0
            self.discarded_count = 0
            self.accepted_count = 0
            self.rejection_counts = {}
            self.no_trade_count = 0
            self.progress_pct = 0.0
            self.current_generation = 0
            self.candidates_passed = []
            self.best_candidate = None
            self.log_messages = []
            self.neural_nodes = []
            self.neural_edges = []
            self.seen_signatures = set()
            self.seen_perf_signatures = set()
            self.total_combinations = 0

    def log(self, msg: str):
        with self.lock:
            self.log_messages.append(msg)
            if len(self.log_messages) > 100:
                self.log_messages.pop(0)

    # =========================================================================
    # INDIVIDUAL GENERATION & MUTATION OPERATORS
    # =========================================================================

    def create_random_condition(self, enabled_indicators: List[str], is_buy: bool, rng: Optional[random.Random] = None) -> Condition:
        rng=rng or random
        cond=self._create_base_condition(enabled_indicators,is_buy,rng)
        if self.enabled_operators is not None:
            pool=sorted(set(self.enabled_operators)&compatible(cond.indicator))
            if not pool: raise ValueError(f'Sin operador compatible para {cond.indicator}')
            weights=[(.1 if candidate=='EQUAL_TO' else (3. if candidate==cond.operator else 1.)) for candidate in pool]
            op=rng.choices(pool,weights=weights,k=1)[0]
            if cond.operator in ('PRICE_ABOVE','PRICE_BELOW') and op not in ('PRICE_ABOVE','PRICE_BELOW'):
                cond.target_type='indicator';cond.target_indicator='PRICE';cond.target_params={}
            cond.operator=op
        return cond

    def _create_base_condition(self, enabled_indicators: List[str], is_buy: bool, rng: Optional[random.Random] = None) -> Condition:
        rng = rng or random
        if not enabled_indicators:
            enabled_indicators = ["EMA", "RSI", "SUPERTREND", "MACD"]

        ind = rng.choice(enabled_indicators)
        ind_u = ind.upper()

        if ind_u.startswith('MACRO_'):
            raise ValueError('Los indicadores FRED fueron retirados del motor')

        meta = ALL_28_INDICATORS.get(ind_u, {})
        pcfg = meta.get("params") or {}
        override_cfg = (self.param_ranges or {}).get(ind_u) or {}

        def prange(key, default):
            ov = override_cfg.get(key)
            if ov and ("from" in ov or "values" in ov):
                try:
                    return sample_from_range(ov, rng)
                except Exception:
                    pass
            if key in pcfg and pcfg[key]:
                return sample_from_range(pcfg[key], rng)
            return default

        if ind_u == "RSI":
            p = {"period": int(prange("period", 14))}
            thr_low = float(prange("threshold_low", 30))
            thr_high = float(prange("threshold_high", 70))
            op = cross_op(is_buy, rng)
            val = thr_low if is_buy else thr_high
            return Condition("RSI", p, op, "value", target_value=val)

        if ind_u == "SUPERTREND":
            p = {"period": int(prange("period", 10)), "multiplier": float(prange("multiplier", 3.0))}
            op = "BULLISH" if is_buy else "BEARISH"
            return Condition("SUPERTREND", p, op, "value", target_value=0.0)

        if ind_u == "PSAR":
            p = {"step": float(prange("step", 0.02)), "max_step": float(prange("max_step", 0.2))}
            op = "BULLISH" if is_buy else "BEARISH"
            return Condition("PSAR", p, op, "value", target_value=0.0)

        if ind_u == "MACD":
            p = {"fast": int(prange("fast", 12)), "slow": int(prange("slow", 26)),
                 "signal": int(prange("signal", 9)), "sub": "hist"}
            op = cross_op(is_buy, rng)
            return Condition("MACD", p, op, "value", target_value=0.0)

        if ind_u == "STOCHASTIC":
            p = {"k_period": int(prange("k_period", 14)), "d_period": int(prange("d_period", 3)), "sub": "k"}
            op = cross_op(is_buy, rng)
            val = float(prange("threshold_low", 20)) if is_buy else float(prange("threshold_high", 80))
            return Condition("STOCHASTIC", p, op, "value", target_value=val)

        if ind_u == "BOLLINGER":
            p = {"period": int(prange("period", 20)), "std_dev": float(prange("std_dev", 2.0)), "sub": "pct_b"}
            op = "LESS_THAN" if is_buy else "GREATER_THAN"
            val = 0.15 if is_buy else 0.85
            return Condition("BOLLINGER", p, op, "value", target_value=val)

        if ind_u == "RCI":
            p = {"period": int(prange("period", 14))}
            op = cross_op(is_buy, rng)
            val = -60.0 if is_buy else 60.0
            return Condition("RCI", p, op, "value", target_value=val)

        if ind_u == "ADX":
            p = {"period": int(prange("period", 14)), "sub": "adx"}
            return Condition("ADX", p, "GREATER_THAN", "value", target_value=float(prange("threshold", 25)))

        if ind_u == "AROON":
            p = {"period": int(prange("period", 14))}
            op = "GREATER_THAN" if is_buy else "LESS_THAN"
            return Condition("AROON", p, op, "value", target_value=0.0)

        if ind_u == "CCI":
            p = {"period": int(prange("period", 20))}
            thr = float(prange("threshold", 100))
            op = cross_op(is_buy, rng)
            val = -thr if is_buy else thr
            return Condition("CCI", p, op, "value", target_value=val)

        if ind_u == "ROC":
            p = {"period": int(prange("period", 12))}
            op = cross_op(is_buy, rng)
            return Condition("ROC", p, op, "value", target_value=0.0)

        if ind_u == "WILLIAMS_R":
            p = {"period": int(prange("period", 14))}
            op = cross_op(is_buy, rng)
            val = float(prange("threshold_low", -80)) if is_buy else float(prange("threshold_high", -20))
            return Condition("WILLIAMS_R", p, op, "value", target_value=val)

        if ind_u in ["EMA", "SMA", "DEMA", "TEMA", "HMA", "WMA", "KAMA"]:
            fast_p = int(prange("period", 20))
            slow_p = int(prange("period", 200))
            if slow_p <= fast_p:
                slow_p = fast_p + 50
            if rng.random() < 0.25:
                # TN 'price_above'/'price_below': estado del precio respecto a la media
                return Condition(ind_u, {"period": fast_p},
                                 "PRICE_ABOVE" if is_buy else "PRICE_BELOW",
                                 "value", target_value=0.0)
            op = cross_op(is_buy, rng)
            return Condition(ind_u, {"period": fast_p}, op, "indicator",
                             target_indicator=ind_u, target_params={"period": slow_p})

        if ind_u in ["KELTNER", "DONCHIAN"]:
            p = {"period": int(prange("period", 20))}
            if "multiplier" in pcfg:
                p["multiplier"] = float(prange("multiplier", 1.5))
            op = cross_op(is_buy, rng)
            return Condition(ind_u, p, op, "value", target_value=0.0)

        if ind_u in ["MFI", "CMF", "OBV", "VOLUME_SMA"]:
            p = {"period": int(prange("period", 14))} if "period" in pcfg else {"signal": int(prange("signal", 20))}
            op = "GREATER_THAN" if is_buy else "LESS_THAN"
            val = 50.0 if ind_u == "MFI" else 0.0
            if ind_u == "MFI":
                val = float(prange("threshold_low", 30)) if is_buy else float(prange("threshold_high", 70))
            return Condition(ind_u, p, op, "value", target_value=val)

        if ind_u == "HIGHEST":
            p = {"period": int(prange("period", 20))}
            # Breakout: close por encima del máximo de la ventana ANTERIOR (largo)
            # o por debajo de ella (debilidad) — TN 'price_above'/'price_below'
            op = "PRICE_ABOVE" if is_buy else "PRICE_BELOW"
            return Condition(ind_u, p, op, "value", target_value=0.0)

        if ind_u == "LOWEST":
            p = {"period": int(prange("period", 20))}
            # Breakdown: close por debajo del mínimo de la ventana ANTERIOR (corto)
            # o por encima de ella (soporte se mantiene) — TN 'price_above'/'price_below'
            op = "PRICE_BELOW" if not is_buy else "PRICE_ABOVE"
            return Condition(ind_u, p, op, "value", target_value=0.0)

        if ind_u == "PIVOT_POINTS":
            sub = sample_from_range(pcfg.get("sub", {"values": ["pp"]}), rng) or "pp"
            p = {"sub": sub}
            if rng.random() < 0.35:
                # Breakout del pivote
                op = "PRICE_ABOVE" if is_buy else "PRICE_BELOW"
                return Condition(ind_u, p, op, "value", target_value=0.0)
            # Reversión: precio bajo el pivote (soporte) / sobre el pivote (resistencia)
            op = "GREATER_THAN" if is_buy else "LESS_THAN"
            return Condition(ind_u, p, op, "indicator",
                             target_indicator="PRICE", target_params={})

        if ind_u == "VWAP":
            p = {}
            # Estado: precio sobre/bajo el VWAP (TN 'price_above'/'price_below')
            op = "PRICE_ABOVE" if is_buy else "PRICE_BELOW"
            return Condition(ind_u, p, op, "value", target_value=0.0)

        if ind_u == "ICHIMOKU":
            p = {"tenkan_p": int(prange("tenkan_p", 9)),
                 "kijun_p": int(prange("kijun_p", 26)),
                 "span_b_p": int(prange("span_b_p", 52)),
                 "sub": "kijun"}
            # s1 = close - kijun; cruzar 0 equivale a que el precio cruce el kijun
            op = cross_op(is_buy, rng)
            return Condition(ind_u, p, op, "value", target_value=0.0)

        if ind_u == "ATR":
            p = {"period": int(prange("period", 14))}
            return Condition(ind_u, p, "GREATER_THAN", "value", target_value=0.0)

        # Fallback
        p = {"period": 14}
        return Condition("RSI", p, "GREATER_THAN" if is_buy else "LESS_THAN", "value", target_value=50.0)

    def create_random_strategy(
        self,
        symbol: str,
        timeframe: str,
        enabled_indicators: List[str],
        enabled_entry_types: List[str],
        enabled_exit_modes: List[str],
        generation: int = 0,
        min_indicators: int = 1,
        max_indicators: int = 2,
        sizing_mode: Optional[str] = None,
        risk_per_trade_pct: Optional[float] = None,
        fixed_lot: Optional[float] = None,
        fixed_cash_risk: Optional[float] = None,
        martingale_mult: Optional[float] = None,
        direction: str = "BOTH",
        prop_firm_filter: bool = False,
        rng: Optional[random.Random] = None,
        risk_rules: Optional[Dict[str, Any]] = None
    ) -> Strategy:
        rng = rng or random
        risk_rules = risk_rules or {}

        avail_inds = list(enabled_indicators) if enabled_indicators else ["EMA", "RSI", "MACD", "ATR"]
        num_conds = rng.randint(min_indicators, max(min_indicators, min(4, max_indicators)))

        if len(avail_inds) >= num_conds:
            chosen_buy = rng.sample(avail_inds, num_conds)
            chosen_sell = rng.sample(avail_inds, num_conds)
        else:
            chosen_buy = [rng.choice(avail_inds) for _ in range(num_conds)]
            chosen_sell = [rng.choice(avail_inds) for _ in range(num_conds)]

        buy_conds = [self.create_random_condition([ind], is_buy=True, rng=rng) for ind in chosen_buy]
        sell_conds = [self.create_random_condition([ind], is_buy=False, rng=rng) for ind in chosen_sell]

        entry_type = rng.choice(enabled_entry_types) if enabled_entry_types else "MARKET"
        exit_mode = rng.choice(enabled_exit_modes) if enabled_exit_modes else "ATR_CLASSIC"

        # Exit params by mode (ranges from TN docs) — defaults always defined
        sl_atr, tp_atr = 1.5, 3.0
        sl_pips, tp_pips = 20.0, 40.0
        sl_pct, tp_pct = 0.5, 1.0
        sl_smooth, tp_smooth = 1.5, 3.0
        if exit_mode == "PIPS_FIXED":
            sl_pips = rng.choice([10, 15, 20, 30, 40, 50])
            tp_pips = rng.choice([20, 30, 40, 60, 80, 100])
        elif exit_mode == "PCT_EXIT":
            sl_pct = rng.choice([0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0])
            tp_pct = rng.choice([0.5, 1.0, 1.5, 2.0, 3.0, 4.0])
        elif exit_mode == "ATR_SMOOTHED":
            sl_smooth = rng.choice([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
            tp_smooth = rng.choice([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        else:
            sl_atr = rng.choice([1.0, 1.5, 2.0, 2.5, 3.0])
            tp_atr = rng.choice([1.5, 2.0, 3.0, 4.0, 5.0, 6.0])

        trail_atr = rng.choice([0.5, 1.0, 1.5, 2.0, 2.5])
        be_atr = rng.choice([0.5, 1.0, 1.2, 1.5, 2.0])
        swing_bars = rng.choice([10, 15, 20, 30, 40, 50])
        max_bars = rng.choice([5, 12, 24, 36, 48])
        partial_tp1 = rng.choice([0.5, 1.0, 1.5, 2.0])
        partial_tp2 = rng.choice([2.0, 3.0, 4.0, 6.0])
        partial_pct = rng.choice([30.0, 40.0, 50.0, 60.0, 70.0])

        # User-edited exit/risk sweep ranges override (TN: barrido de salidas)
        er = getattr(self, "exit_ranges", None) or {}
        if er:
            def _ov(key: str, default: Any) -> Any:
                cfg = er.get(key)
                if cfg and ("from" in cfg or "values" in cfg):
                    try:
                        return sample_from_range(cfg, rng)
                    except Exception:
                        return default
                return default
            sl_atr = _ov("sl_atr", sl_atr)
            tp_atr = _ov("tp_atr", tp_atr)
            sl_pips = _ov("sl_pips", sl_pips)
            tp_pips = _ov("tp_pips", tp_pips)
            sl_pct = _ov("sl_pct", sl_pct)
            tp_pct = _ov("tp_pct", tp_pct)
            sl_smooth = _ov("sl_smooth_mult", sl_smooth)
            tp_smooth = _ov("tp_smooth_mult", tp_smooth)
            trail_atr = _ov("trail_atr", trail_atr)
            be_atr = _ov("be_atr", be_atr)
            swing_bars = int(_ov("swing_bars", swing_bars))
            max_bars = int(_ov("max_bars", max_bars))
            partial_tp1 = _ov("partial_tp1_atr", partial_tp1)
            partial_tp2 = _ov("partial_tp2_atr", partial_tp2)
            partial_pct = _ov("partial_pct", partial_pct)

        # Exit modifiers explored on base modes (TN: modificadores BE/trailing)
        _base_modes = ("ATR_CLASSIC", "PIPS_FIXED", "PCT_EXIT", "ATR_SMOOTHED")
        mod_be = exit_mode in _base_modes and rng.random() < 0.35
        mod_tr = exit_mode in _base_modes and rng.random() < 0.35

        # G: Averaging (DCA/piramidado)
        avg_cfg = getattr(self, "avg_cfg", None) or {}
        avg_enabled = False
        avg_mode = "dca"
        avg_max_levels = 2
        avg_spacing_unit = "atr"
        avg_spacing_value = 1.0
        avg_size_multiplier = 1.0
        avg_recompute_stop = False
        if avg_cfg.get("enabled", False):
            _prob = 0.45
            if avg_cfg.get("allowDual", False):
                avg_mode_pool = ["dca", "pyramiding", "both"]
            elif avg_cfg.get("mode"):
                avg_mode_pool = [str(avg_cfg["mode"])]
            else:
                avg_mode_pool = ["dca", "pyramiding", "both"]
        elif "enabled" in avg_cfg:
            _prob = 0.0
            avg_mode_pool = ["dca", "pyramiding", "both"]
        else:
            _prob = 0.15
            avg_mode_pool = ["dca", "pyramiding", "both"]
        if rng.random() < _prob:
            avg_enabled = True
            avg_mode = rng.choice(avg_mode_pool)
            avg_max_levels = int(avg_cfg.get("maxLevels", rng.randint(1, 4)))
            avg_spacing_unit = str(avg_cfg.get("spacingUnit", rng.choice(["atr", "pips", "percent"])))
            if "spacingValue" in avg_cfg:
                avg_spacing_value = float(avg_cfg["spacingValue"])
            elif avg_spacing_unit == "atr":
                avg_spacing_value = rng.choice([0.5, 1.0, 1.5, 2.0, 2.5])
            elif avg_spacing_unit == "pips":
                avg_spacing_value = float(rng.choice([10, 20, 30, 40, 50]))
            else:
                avg_spacing_value = rng.choice([0.2, 0.5, 1.0, 1.5, 2.0])
            avg_size_multiplier = float(avg_cfg.get("sizeMultiplier", rng.choice([0.5, 0.75, 1.0, 1.5])))
            avg_recompute_stop = bool(avg_cfg.get("recomputeStopFromAvg", rng.random() < 0.5))

        session = rng.choice(SESSION_FILTERS)
        sizing = sizing_mode if sizing_mode else rng.choice(SIZING_MODES)
        risk_pct = risk_per_trade_pct if risk_per_trade_pct is not None else rng.choice([0.5, 1.0, 1.5, 2.0, 3.0])
        f_lot = fixed_lot if fixed_lot is not None else 0.1
        f_cash = fixed_cash_risk if fixed_cash_risk is not None else 100.0
        m_mult = martingale_mult if martingale_mult is not None else 1.5

        # Risk rules (from config with random variation when allowed)
        if not prop_firm_filter:
            risk_rules=dict(risk_rules,**{field:0. for field in ACCOUNT_LIMITS})
        max_daily_loss = risk_rules.get("max_daily_loss_pct", rng.choice([1.0, 2.0, 2.5, 3.0, 4.0, 5.0]))
        max_weekly_loss = risk_rules.get("max_weekly_loss_pct", rng.choice([2.0, 4.0, 6.0, 8.0, 10.0]))
        max_monthly_loss = risk_rules.get("max_monthly_loss_pct", rng.choice([5.0, 10.0, 15.0, 20.0]))
        max_account_loss = risk_rules.get("max_account_loss_pct", rng.choice([5.0, 6.0, 8.0, 10.0, 12.0]))
        max_daily_gain = risk_rules.get("max_daily_gain_pct", rng.choice([0.0, 0.0, 1.0, 2.0, 3.0, 5.0]))
        max_weekly_gain = risk_rules.get("max_weekly_gain_pct", rng.choice([0.0, 0.0, 2.0, 5.0, 10.0]))
        max_monthly_gain = risk_rules.get("max_monthly_gain_pct", rng.choice([0.0, 0.0, 5.0, 10.0, 20.0]))
        max_account_gain = risk_rules.get("max_account_gain_pct", rng.choice([0.0, 0.0, 10.0, 20.0, 50.0]))
        max_consec_wins = risk_rules.get("max_consecutive_wins", rng.choice([0, 0, 0, 3, 5, 10]))
        max_consec_losses = risk_rules.get("max_consecutive_losses", rng.choice([0, 0, 3, 5, 7, 10]))
        max_daily_trades = risk_rules.get("max_daily_trades", rng.choice([1, 2, 3, 4, 5, 10, 20]))
        max_open_trades = risk_rules.get("max_open_trades", rng.choice([1, 1, 1, 2, 3, 5]))
        reward_risk = risk_rules.get("reward_risk_ratio", rng.choice([0.0, 0.0, 1.0, 1.5, 2.0, 3.0]))
        fixed_rr = risk_rules.get("fixed_rr", rng.choice([0.0, 0.0, 0.0, 1.5, 2.0, 3.0]))
        risk_multiplier = risk_rules.get("risk_multiplier", rng.choice([0.5, 0.75, 1.0, 1.25, 1.5]))

        # Time rules
        no_fri = risk_rules.get("no_new_trades_friday", rng.random() < 0.25)
        no_mon = risk_rules.get("no_monday_open", rng.random() < 0.25)
        no_roll = risk_rules.get("avoid_rollover", rng.random() < 0.3)
        close_ny = risk_rules.get("close_before_ny_close", rng.random() < 0.2)
        close_wknd = risk_rules.get("close_before_weekend", True)

        strat = Strategy(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            prop_firm_filter=prop_firm_filter,
            entry_order_type=entry_type,
            buy_conditions=buy_conds,
            sell_conditions=sell_conds,
            session_filter=session,
            close_before_weekend=close_wknd,
            close_before_ny_close=close_ny,
            no_new_trades_friday=no_fri,
            no_monday_open=no_mon,
            avoid_rollover=no_roll,
            exit_mode=exit_mode,
            sl_atr=sl_atr,
            tp_atr=tp_atr,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            sl_pct=sl_pct,
            tp_pct=tp_pct,
            sl_smooth_mult=sl_smooth,
            tp_smooth_mult=tp_smooth,
            trail_atr=trail_atr,
            be_atr=be_atr,
            swing_bars=swing_bars,
            max_bars=max_bars,
            partial_tp1_atr=partial_tp1,
            partial_tp2_atr=partial_tp2,
            partial_pct=partial_pct,
            modifier_breakeven=mod_be,
            modifier_trailing=mod_tr,
            sizing_mode=sizing,
            risk_per_trade_pct=risk_pct,
            fixed_lot=f_lot,
            fixed_cash_risk=f_cash,
            risk_multiplier=risk_multiplier,
            fixed_rr=fixed_rr,
            max_daily_loss_pct=max_daily_loss,
            max_weekly_loss_pct=max_weekly_loss,
            max_monthly_loss_pct=max_monthly_loss,
            max_account_loss_pct=max_account_loss,
            max_daily_gain_pct=max_daily_gain,
            max_weekly_gain_pct=max_weekly_gain,
            max_monthly_gain_pct=max_monthly_gain,
            max_account_gain_pct=max_account_gain,
            max_consecutive_wins=max_consec_wins,
            max_consecutive_losses=max_consec_losses,
            max_daily_trades=max_daily_trades,
            max_open_trades=max_open_trades,
            reward_risk_ratio=reward_risk,
            martingale_mult=m_mult,
            avg_enabled=avg_enabled,
            avg_mode=avg_mode,
            avg_max_levels=avg_max_levels,
            avg_spacing_unit=avg_spacing_unit,
            avg_spacing_value=avg_spacing_value,
            avg_size_multiplier=avg_size_multiplier,
            avg_recompute_stop=avg_recompute_stop,
            generation=generation
        )
        return strat

    def crossover(self, parent_a: Strategy, parent_b: Strategy, generation: int) -> Strategy:
        child = copy.deepcopy(parent_a)
        child.id = f"strat_g{generation}_{random.randint(1000, 9999)}"
        child.generation = generation
        child.parent_ids = [parent_a.id, parent_b.id]

        if parent_a.buy_conditions and parent_b.buy_conditions and random.random() < 0.6:
            half_a = parent_a.buy_conditions[:max(1, len(parent_a.buy_conditions)//2)]
            half_b = parent_b.buy_conditions[:max(1, len(parent_b.buy_conditions)//2)]
            child.buy_conditions = copy.deepcopy(half_a + half_b)[:4]
        elif random.random() < 0.5:
            child.buy_conditions = copy.deepcopy(parent_b.buy_conditions)

        if parent_a.sell_conditions and parent_b.sell_conditions and random.random() < 0.6:
            half_a = parent_a.sell_conditions[:max(1, len(parent_a.sell_conditions)//2)]
            half_b = parent_b.sell_conditions[:max(1, len(parent_b.sell_conditions)//2)]
            child.sell_conditions = copy.deepcopy(half_a + half_b)[:4]
        elif random.random() < 0.5:
            child.sell_conditions = copy.deepcopy(parent_b.sell_conditions)

        if random.random() < 0.5:
            child.entry_order_type = parent_b.entry_order_type
        if random.random() < 0.5:
            child.exit_mode = parent_b.exit_mode
            child.sl_atr = parent_b.sl_atr
            child.tp_atr = parent_b.tp_atr
            child.sl_pips = parent_b.sl_pips
            child.tp_pips = parent_b.tp_pips
            child.sl_pct = parent_b.sl_pct
            child.tp_pct = parent_b.tp_pct
            child.sl_smooth_mult = parent_b.sl_smooth_mult
            child.tp_smooth_mult = parent_b.tp_smooth_mult
            child.trail_atr = parent_b.trail_atr
            child.be_atr = parent_b.be_atr
            child.modifier_breakeven = parent_b.modifier_breakeven
            child.modifier_trailing = parent_b.modifier_trailing
        if random.random() < 0.4:
            child.session_filter = parent_b.session_filter
        if random.random() < 0.3:
            child.reward_risk_ratio = parent_b.reward_risk_ratio
            child.fixed_rr = parent_b.fixed_rr
        # G: Averaging
        if random.random() < 0.4:
            child.avg_enabled = parent_b.avg_enabled
            child.avg_mode = parent_b.avg_mode
            child.avg_max_levels = parent_b.avg_max_levels
            child.avg_spacing_unit = parent_b.avg_spacing_unit
            child.avg_spacing_value = parent_b.avg_spacing_value
            child.avg_size_multiplier = parent_b.avg_size_multiplier
            child.avg_recompute_stop = parent_b.avg_recompute_stop

        return child

    def mutate(
        self,
        strategy: Strategy,
        enabled_indicators: List[str],
        enabled_entry_types: List[str],
        enabled_exit_modes: List[str]
    ) -> Strategy:
        mutant = copy.deepcopy(strategy)
        mutation_type = random.choice([
            "param_drift", "exit_tweak", "entry_type_tweak", "condition_swap",
            "session_tweak", "risk_tweak", "threshold_tweak", "time_rule_tweak"
        ])

        if mutation_type == "param_drift":
            all_conds = mutant.buy_conditions + mutant.sell_conditions
            if all_conds:
                target_cond = random.choice(all_conds)
                if "period" in target_cond.params:
                    cur = target_cond.params["period"]
                    drift = random.choice([-5, -2, 2, 5])
                    new_val = int(cur + drift)
                    # Respect user-edited sweep range for this parameter if any
                    ov = (self.param_ranges or {}).get(target_cond.indicator.upper(), {}).get("period")
                    if ov and "from" in ov and "to" in ov:
                        try:
                            new_val = max(int(float(ov["from"])), min(int(float(ov["to"])), new_val))
                        except (TypeError, ValueError):
                            pass
                    target_cond.params["period"] = max(5, new_val)
                if target_cond.target_type == "value":
                    target_cond.target_value = round(target_cond.target_value * random.choice([0.9, 1.1]), 2)

        elif mutation_type == "threshold_tweak":
            all_conds = mutant.buy_conditions + mutant.sell_conditions
            if all_conds:
                tc = random.choice(all_conds)
                if tc.target_type == "value" and tc.target_value not in (0.0,):
                    tc.target_value = round(tc.target_value + random.choice([-5, -2.5, 2.5, 5]), 2)

        elif mutation_type == "exit_tweak":
            if mutant.exit_mode == "ATR_CLASSIC":
                mutant.sl_atr = round(max(0.5, mutant.sl_atr + random.choice([-0.25, 0.25])), 2)
                mutant.tp_atr = round(max(1.0, mutant.tp_atr + random.choice([-0.5, 0.5])), 2)
            elif mutant.exit_mode == "PIPS_FIXED":
                mutant.sl_pips = round(max(5.0, mutant.sl_pips + random.choice([-5, 5])), 1)
                mutant.tp_pips = round(max(10.0, mutant.tp_pips + random.choice([-10, 10])), 1)
            elif mutant.exit_mode == "PCT_EXIT":
                mutant.sl_pct = round(max(0.1, mutant.sl_pct + random.choice([-0.1, 0.1])), 3)
                mutant.tp_pct = round(max(0.2, mutant.tp_pct + random.choice([-0.2, 0.2])), 3)
            elif mutant.exit_mode == "ATR_SMOOTHED":
                mutant.sl_smooth_mult = round(max(0.5, mutant.sl_smooth_mult + random.choice([-0.25, 0.25])), 2)
                mutant.tp_smooth_mult = round(max(1.0, mutant.tp_smooth_mult + random.choice([-0.5, 0.5])), 2)
            else:
                mutant.trail_atr = round(max(0.5, mutant.trail_atr + random.choice([-0.25, 0.25])), 2)
                mutant.be_atr = round(max(0.5, mutant.be_atr + random.choice([-0.2, 0.2])), 2)
            if enabled_exit_modes and random.random() < 0.3:
                mutant.exit_mode = random.choice(enabled_exit_modes)
            _bm = ("ATR_CLASSIC", "PIPS_FIXED", "PCT_EXIT", "ATR_SMOOTHED")
            if mutant.exit_mode not in _bm:
                mutant.modifier_breakeven = False
                mutant.modifier_trailing = False
            else:
                if random.random() < 0.3:
                    mutant.modifier_breakeven = not mutant.modifier_breakeven
                if random.random() < 0.3:
                    mutant.modifier_trailing = not mutant.modifier_trailing

        elif mutation_type == "entry_type_tweak" and enabled_entry_types:
            mutant.entry_order_type = random.choice(enabled_entry_types)

        elif mutation_type == "condition_swap":
            if mutant.buy_conditions and random.random() < 0.5:
                idx = random.randrange(len(mutant.buy_conditions))
                mutant.buy_conditions[idx] = self.create_random_condition(enabled_indicators, is_buy=True)
            elif mutant.sell_conditions:
                idx = random.randrange(len(mutant.sell_conditions))
                mutant.sell_conditions[idx] = self.create_random_condition(enabled_indicators, is_buy=False)

        elif mutation_type == "session_tweak":
            mutant.session_filter = random.choice(SESSION_FILTERS)

        elif mutation_type == "risk_tweak":
            mutant.risk_per_trade_pct = round(max(0.5, min(3.0, mutant.risk_per_trade_pct + random.choice([-0.25, 0.25]))), 2)
            if random.random() < 0.4:
                mutant.reward_risk_ratio = round(max(0.0, mutant.reward_risk_ratio + random.choice([-0.5, 0.5])), 2)
            if random.random() < 0.3:
                mutant.risk_multiplier = round(max(0.5, min(2.0, mutant.risk_multiplier + random.choice([-0.25, 0.25]))), 2)

        elif mutation_type == "time_rule_tweak":
            if random.random() < 0.33:
                mutant.no_new_trades_friday = not mutant.no_new_trades_friday
            elif random.random() < 0.5:
                mutant.no_monday_open = not mutant.no_monday_open
            else:
                mutant.avoid_rollover = not mutant.avoid_rollover

        return mutant

    # =========================================================================
    # FITNESS & CLASSIFICATION EVALUATION
    # =========================================================================

    def calculate_fitness(self, metrics: Dict[str, Any], objective: str = "tn_score") -> float:
        if metrics["total_trades"] < 5:
            return -9999.0

        if objective == "tn_score":
            return float(metrics["tn_score"])
        elif objective == "sharpe":
            return float(metrics["sharpe_ratio"])
        elif objective == "sortino":
            return float(metrics["sortino_ratio"])
        elif objective == "calmar":
            return float(metrics["calmar_ratio"])
        elif objective == "pnl":
            return float(metrics["total_return_usd"])
        elif objective == "drawdown":
            return -float(metrics["max_drawdown_pct"])
        elif objective == "profit_factor":
            return float(metrics["profit_factor"])
        elif objective == "expectancy":
            return float(metrics["expectancy_usd"])
        elif objective == "win_rate":
            return float(metrics["win_rate_pct"])
        elif objective == "recovery_factor":
            return float(metrics["recovery_factor"])
        elif objective == "pass_rate":
            # Higher is better; uses tn_score as proxy when pass_rate not yet computed
            return float(metrics.get("pass_rate_pct", metrics["tn_score"]))
        else:
            return float(metrics["tn_score"])

    # =========================================================================
    # BATCH EVALUATION (serial or parallel)
    # =========================================================================

    def _evaluate_batch(
        self,
        population: List[Strategy],
        dfs: Any,  # Dict[str, pd.DataFrame] or single pd.DataFrame
        initial_deposit: float,
        bt_kwargs: Dict[str, Any],
        parallel_workers: int = 0
    ) -> List[BacktestResult]:
        # Normalize to dict keyed by f"{symbol}_{timeframe}"
        if isinstance(dfs, pd.DataFrame):
            if population:
                key = f"{population[0].symbol}_{population[0].timeframe}"
            else:
                key = "single"
            dfs_map: Dict[str, pd.DataFrame] = {key: dfs}
        else:
            dfs_map = dict(dfs)

        # Bind provenance in the parent too (parallel workers serialize strategies).
        for strategy in population:
            frame = dfs_map.get(f'{strategy.symbol}_{strategy.timeframe}')
            if frame is not None and frame.attrs.get('data_source'):
                strategy.data_source = frame.attrs['data_source']

        if parallel_workers and parallel_workers > 1 and len(population) > 4:
            try:
                import base64, pickle
                from concurrent.futures import ProcessPoolExecutor
                payload_b64 = base64.b64encode(
                    pickle.dumps(dfs_map, protocol=pickle.HIGHEST_PROTOCOL)
                ).decode()
                payloads = [(s.to_dict(), initial_deposit) for s in population]
                with ProcessPoolExecutor(
                    max_workers=parallel_workers,
                    initializer=_init_worker,
                    initargs=(payload_b64, bt_kwargs)
                ) as ex:
                    chunk = max(1, len(population) // (parallel_workers * 2))
                    raw = list(ex.map(_worker_eval, payloads, chunksize=chunk))
                results = []
                for r in raw:
                    results.append(BacktestResult(
                        strategy_id=r["strategy_id"],
                        metrics=r["metrics"],
                        equity_curve=r["equity_curve"],
                        trades=r["trades"],
                        drawdown_curve=r["drawdown_curve"]
                    ))
                return results
            except Exception as e:
                self.log(f"⚠ Paralelo no disponible ({type(e).__name__}: {e}); usando serial.")

        results = []
        fallback_df = next(iter(dfs_map.values())) if dfs_map else None
        for s in population:
            key = f"{s.symbol}_{s.timeframe}"
            df = dfs_map.get(key)
            if df is None:
                df = fallback_df
            htf_df = None
            if getattr(s, "mtf_timeframe", None):
                htf_df = dfs_map.get(f"{s.symbol}_{s.mtf_timeframe}")
            results.append(
                backtester.run_backtest(s, df, initial_deposit=initial_deposit,
                                        htf_df=htf_df, **bt_kwargs)
            )
        return results

    # =========================================================================
    # CORE EXPLORATION RUNNER
    # =========================================================================

    def start_exploration(
        self,
        config: Dict[str, Any],
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        resume_candidates: Optional[List[Dict[str, Any]]] = None,
    ):
        if self.is_running:
            raise RuntimeError("Ya hay una exploración en curso.")

        config=normalize_config(config)
        self.reset_state()
        self.last_config = copy.deepcopy(config)
        if resume_candidates:
            self.candidates_passed = copy.deepcopy(resume_candidates)
            self.best_candidate = self.candidates_passed[0]
        self.is_running = True
        self.should_stop = False

        self._thread = threading.Thread(
            target=self._run_exploration_worker,
            args=(config, on_progress),
            daemon=True
        )
        self._thread.start()

    def stop_exploration(self):
        self.should_stop = True
        self.log("⏹ Detención solicitada por el usuario. Finalizando ronda actual...")

    def _ingest_result(
        self,
        individual: Strategy,
        res: BacktestResult,
        m: Dict[str, Any],
        passes_classification: bool,
        objective: str,
        max_candidates: Optional[int],
        gen: int,
        ind_idx: int,
        pop_size: int,
        df: Optional[pd.DataFrame] = None
    ):
        """Shared acceptance logic for random and genetic modes."""
        if passes_classification:
            sig = individual.get_signature()
            perf_sig = (
                individual.symbol,
                individual.timeframe,
                individual.entry_order_type,
                m["total_trades"],
                round(m["total_return_usd"], 1),
                round(m["max_drawdown_pct"], 1),
                round(m["win_rate_pct"], 1)
            )
            is_duplicate = (sig in self.seen_signatures) or (perf_sig in self.seen_perf_signatures)
            if is_duplicate:
                self.discarded_count += 1
                return
            self.seen_signatures.add(sig)
            self.seen_perf_signatures.add(perf_sig)

            candidate_entry = {
                "strategy": individual.to_dict(),
                "metrics": m,
                "equity_curve": res.equity_curve,
                "sparkline": [e["equity"] for e in res.equity_curve[::max(1, len(res.equity_curve)//25)]],
                "trades_sample": res.trades[:15],
                "rules_desc": individual.to_human_description(),
                "indicators_used": individual.get_used_indicators(),
                "signature": sig,
                "perf_sig": perf_sig,
                "passed_filters": True
            }
            cand_score = m.get(objective, m.get("tn_score", 0.0))
            replacement_message=None
            with self.lock:
                if max_candidates is None or len(self.candidates_passed) < max_candidates:
                    self.accepted_count += 1
                    self.candidates_passed.append(candidate_entry)
                    self.candidates_passed.sort(
                        key=lambda x: x["metrics"].get(objective, x["metrics"].get("tn_score", 0.0)),
                        reverse=True
                    )
                else:
                    lowest_cand = self.candidates_passed[-1]
                    lowest_score = lowest_cand["metrics"].get(objective, lowest_cand["metrics"].get("tn_score", 0.0))
                    if cand_score > lowest_score:
                        evicted = self.candidates_passed.pop(-1)
                        if evicted.get("signature") in self.seen_signatures:
                            self.seen_signatures.remove(evicted["signature"])
                        if evicted.get("perf_sig") in self.seen_perf_signatures:
                            self.seen_perf_signatures.remove(evicted["perf_sig"])
                        self.candidates_passed.append(candidate_entry)
                        self.candidates_passed.sort(
                            key=lambda x: x["metrics"].get(objective, x["metrics"].get("tn_score", 0.0)),
                            reverse=True
                        )
                        replacement_message=f"⚡ Top {max_candidates} actualizado: Algo {individual.id[-4:].upper()} ({cand_score:.1f}) desplazó a uno menor ({lowest_score:.1f})"
                    else:
                        self.discarded_count += 1
                        return

            if replacement_message:self.log(replacement_message)
            # --- Additional validators (WF/MV) on top-N accepted candidates ---
            vc = self.validator_cfg or {}
            if passes_classification and df is not None and vc.get("validate_during_exploration"):
                with self.lock:
                    pos = next(
                        (i for i, c in enumerate(self.candidates_passed) if c is candidate_entry),
                        None
                    )
                if pos is not None:
                    validation_data: Dict[str, Any] = {}
                    try:
                        if pos < int(vc.get("wf_top_n", 10)):
                            validation_data["walk_forward"] = validation_suite.run_walk_forward(
                                individual, df,
                                n_windows=int(vc.get("wf_windows", 4)),
                                test_ratio=float(vc.get("wf_test_ratio", 0.25)),
                                mode=str(vc.get("wf_mode", "validation")),
                                reopt_depth=str(vc.get("wf_reopt_depth", "standard")),
                                min_wfe=float(vc.get("wf_min_wfe", 0.5)),
                                min_pass_rate=float(vc.get("wf_min_pass_rate", 60.0)),
                                min_sharpe_oos=float(vc.get("wf_min_oos_sharpe", 0.5)),
                            )
                        if pos < int(vc.get("mv_top_n", 5)):
                            validation_data["multiverse"] = validation_suite.run_multiverse(
                                individual, df,
                                n_universes=int(vc.get("mv_universes", 25)),
                                engine_preset=str(vc.get("mv_preset", "balanced")),
                                n_regimes=int(vc.get("mv_regimes", 3)),
                            )
                        if validation_data:
                            candidate_entry["validation"] = validation_data
                            wf_p = validation_data.get("walk_forward", {}).get("passed")
                            mv_p = validation_data.get("multiverse", {}).get("passed")
                            wf_lbl = "✓" if wf_p else ("—" if wf_p is None else "✗")
                            mv_lbl = "✓" if mv_p else ("—" if mv_p is None else "✗")
                            self.log(f"🔍 Validadores Algo {individual.id[-4:].upper()}: "
                                     f"Walk-Forward {wf_lbl} | Multiverso {mv_lbl}")
                    except Exception as ve:
                        self.log(f"⚠ Validadores adicionales fallaron "
                                 f"(Algo {individual.id[-4:].upper()}): {ve}")

            if self.best_candidate is None or cand_score > self.best_candidate["metrics"].get(objective, self.best_candidate["metrics"].get("tn_score", 0.0)):
                self.best_candidate = candidate_entry
                self.log(f"★ NUEVO LÍDER: Algo {individual.id[-4:].upper()} | TN Score: {m['tn_score']} | Net Profit: +${m['total_return_usd']:,.2f} | WR: {m['win_rate_pct']}% | Trades: {m['total_trades']}")
        else:
            self.discarded_count += 1

        # Neural node
        angle = (ind_idx / max(pop_size, 1)) * 2 * math.pi
        radius = 20.0 + ((gen % 20) * 6.0)
        z_coord = (m["tn_score"] - 50.0) * 1.5
        node_data = {
            "id": individual.id,
            "name": individual.name,
            "generation": gen,
            "tn_score": m["tn_score"],
            "sharpe": m["sharpe_ratio"],
            "drawdown": m["max_drawdown_pct"],
            "passed": passes_classification,
            "x": round(radius * math.cos(angle), 1),
            "y": round(radius * math.sin(angle), 1),
            "z": round(z_coord, 1),
            "parents": individual.parent_ids
        }
        self.neural_nodes.append(node_data)
        for p_id in individual.parent_ids:
            self.neural_edges.append({"source": p_id, "target": individual.id})

    def _classify(
        self,
        m: Dict[str, Any],
        cfg: Dict[str, Any],
        all_tested_sharpes: List[float],
        pnl_arr: np.ndarray
    ) -> Tuple[bool, float]:
        """Apply classification filters; returns (passes, dsr)."""
        min_win_rate = float(cfg.get("min_win_rate", 40.0))
        min_trades = int(cfg.get("min_trades", 30))
        max_drawdown = float(cfg.get("max_drawdown", 20.0))
        min_net_profit_usd = float(cfg.get("min_net_profit_usd", 0.0))
        min_sharpe = float(cfg.get("min_sharpe", 0.8))
        min_profit_factor = float(cfg.get("min_profit_factor", 1.2))
        min_dsr = float(cfg.get("min_dsr", 0.3))

        sharpe_var = float(np.var(all_tested_sharpes)) if len(all_tested_sharpes) > 2 else 0.25
        dsr_val = validation_suite.calculate_dsr(
            observed_sharpe=m["sharpe_ratio"],
            num_trials=max(len(all_tested_sharpes), 2),
            sharpe_variance=sharpe_var,
            returns=pnl_arr
        )
        m["dsr"] = dsr_val

        prop_firm_filter = bool(cfg.get("prop_firm_filter", False))
        passes_prop_firm = True
        if prop_firm_filter:
            prop_daily_loss = float(cfg.get("prop_firm_daily_loss_pct", 4.0))
            prop_total_dd = float(cfg.get("prop_firm_total_dd_pct", 8.0))
            max_dl = m.get("max_daily_loss_pct", 0.0)
            max_dd = m.get("max_drawdown_pct", 0.0)
            passes_prop_firm = (max_dl <= prop_daily_loss) and (max_dd <= prop_total_dd)

        checks={
            'Win rate':m['win_rate_pct']>=min_win_rate,
            'Operaciones':m['total_trades']>=min_trades,
            'Drawdown':m['max_drawdown_pct']<=max_drawdown,
            'Beneficio':m['total_return_usd']>=min_net_profit_usd,
            'Sharpe':m['sharpe_ratio']>=min_sharpe,
            'Profit factor':m['profit_factor']>=min_profit_factor,
            'DSR':m['dsr']>=min_dsr,
            'Prop Firm':passes_prop_firm,
        }
        m['filter_failures']=[name for name,passed in checks.items() if not passed]
        passes=all(checks.values())
        return passes, dsr_val

    def _run_exploration_worker(
        self,
        config: Dict[str, Any],
        on_progress: Optional[Callable[[Dict[str, Any]], None]]
    ):
        try:
            symbol = config.get("symbol", "EURUSD")
            timeframe = config.get("timeframe", "1h")
            # --- Multi-symbol / multi-timeframe pairs ---
            symbols_list = config.get("symbols") or [symbol]
            timeframes_list = config.get("timeframes") or [timeframe]
            if isinstance(symbols_list, str):
                symbols_list = [symbols_list]
            if isinstance(timeframes_list, str):
                timeframes_list = [timeframes_list]
            # de-dup preserving order
            symbols_list = list(dict.fromkeys([str(s) for s in symbols_list if s]))
            timeframes_list = list(dict.fromkeys([str(t) for t in timeframes_list if t]))
            if not symbols_list:
                symbols_list = [symbol]
            if not timeframes_list:
                timeframes_list = [timeframe]
            pairs = [(s, tf) for s in symbols_list for tf in timeframes_list]

            # F: modo multi-timeframe — "separate" (un algo por TF) | "combined"
            # (entrada en el TF bajo + confirmación de la misma estrategia en el TF superior)
            mtf_mode = str(config.get("mtf_mode", "separate") or "separate").lower()
            if mtf_mode not in ("separate", "combined"):
                mtf_mode = "separate"
            if mtf_mode == "combined" and len(timeframes_list) < 2:
                mtf_mode = "separate"
                self.log("⚠ Multi-timeframe combinado requiere 2+ timeframes marcados; usando modo separado.")

            initial_deposit = float(config.get("initial_deposit", 10000.0))
            objective = config.get("objective", "tn_score")
            search_mode = (config.get("search_mode", "genetic") or "genetic").lower()
            self.search_mode = search_mode

            # Exploration date range (inclusive; None = full history)
            start_date = config.get("start_date") or None
            end_date = config.get("end_date") or None
            self.date_range = (start_date, end_date)

            enabled_indicators = config.get("enabled_indicators", list(ALL_28_INDICATORS.keys()))
            self.enabled_operators=config.get('enabled_operators')
            enabled_entry_types = config.get("enabled_entry_types", ALL_ENTRY_TYPES)
            enabled_exit_modes = config.get("enabled_exit_modes", ALL_EXIT_MODES)

            # --- User-edited parameter sweep ranges (Desde/Paso/Hasta por parámetro) ---
            raw_ranges = config.get("indicator_ranges") or {}
            self.param_ranges = {}
            if isinstance(raw_ranges, dict):
                for _ind, _params in raw_ranges.items():
                    if isinstance(_params, dict):
                        self.param_ranges[str(_ind).upper()] = _params

            # --- G: averaging config (TN averagingConfig) ---
            self.avg_cfg = config.get("averaging_config") or config.get("averaging") or {}

            # --- User-edited exit/risk sweep ranges (TN: slAtr/tpAtr/trailAtr ...) ---
            raw_exit = config.get("exit_ranges") or {}
            self.exit_ranges = {}
            if isinstance(raw_exit, dict):
                for _ep, _ecfg in raw_exit.items():
                    if isinstance(_ecfg, dict) and ("from" in _ecfg or "values" in _ecfg):
                        self.exit_ranges[str(_ep)] = _ecfg

            # --- Additional validators during exploration (WF/MV over top-N) ---
            self.validator_cfg = {
                "validate_during_exploration": bool(config.get("validate_during_exploration", True)),
                "wf_top_n": max(1, min(50, int(config.get("wf_top_n", 10) or 10))),
                "mv_top_n": max(1, min(10, int(config.get("mv_top_n", 5) or 5))),
                "wf_mode": str(config.get("wf_mode", "validation") or "validation"),
                "wf_reopt_depth": str(config.get("wf_reopt_depth", "standard") or "standard"),
                "wf_windows": max(2, min(12, int(config.get("wf_windows", 4) or 4))),
                "wf_test_ratio": float(config.get("wf_test_ratio", 0.25) or 0.25),
                "wf_min_wfe": float(config.get("wf_min_wfe", 0.5)),
                "wf_min_pass_rate": float(config.get("wf_min_pass_rate", 60.0)),
                "wf_min_oos_sharpe": float(config.get("wf_min_oos_sharpe", 0.5)),
                "mv_universes": max(10, min(500, int(config.get("mv_universes", 25) or 25))),
                "mv_preset": str(config.get("mv_preset", "balanced") or "balanced"),
                "mv_regimes": max(1, min(4, int(config.get("mv_regimes", 3) or 3))),
            }

            # --- Prop challenge simulation during exploration (TN: simulador de reto) ---
            challenge_cfg: Dict[str, Any] = {
                "enabled": bool(config.get("prop_firm_filter", False)),
                "capital": float(config.get("challenge_capital", 10000.0) or 10000.0),
                "target_pct": float(config.get("prop_firm_target_pct", 8.0) or 8.0),
                "daily_loss_pct": float(config.get("prop_firm_daily_loss_pct", 4.0) or 4.0),
                "total_dd_pct": float(config.get("prop_firm_total_dd_pct", 8.0) or 8.0),
                "min_trading_days": int(config.get("challenge_min_trading_days", 5) or 5),
                "simulations": max(3, min(60, int(config.get("challenge_simulations", 10) or 10))),
                "min_pass_rate": float(config.get("challenge_min_pass_rate", 0.0) or 0.0),
            }

            infinite_mode = config.get("infinite_mode", True)
            generations_limit = int(config.get("generations", 0)) if not infinite_mode else 999999
            pop_size = int(config.get("population_size", 30))
            self.population_size = pop_size

            # Combination counter (TN style)
            self.total_combinations = count_combinations(enabled_indicators, self.param_ranges, self.exit_ranges)
            self.log(f"Combinaciones posibles (rango activo): {self.total_combinations:,}")

            # Random mode: fixed budget of combinations
            num_combinations = int(config.get("num_combinations", 10000))
            if not infinite_mode and generations_limit > 0 and search_mode == "genetic":
                pass  # genetic budget as before

            # Backtest modeling
            modeling_mode = config.get("modeling_mode", "ohlc")
            # Costs
            bt_kwargs: Dict[str, Any] = {"modeling_mode": modeling_mode}
            if config.get("spread_pips") is not None:
                bt_kwargs["custom_spread_pips"] = float(config["spread_pips"])
            if config.get("slippage_pips") is not None:
                bt_kwargs["custom_slippage_pips"] = float(config["slippage_pips"])
            if config.get("commission_per_lot") is not None:
                bt_kwargs["commission_per_lot"] = float(config["commission_per_lot"])
            if config.get("swap_long") is not None:
                bt_kwargs["swap_long_per_lot"] = float(config["swap_long"])
            if config.get("swap_short") is not None:
                bt_kwargs["swap_short_per_lot"] = float(config["swap_short"])

            parallel_workers = int(config.get("parallel_workers", 0) or 0)

            # Classification config
            cls_cfg = config

            # Multi-indicator parameters
            min_inds = max(1, int(config.get("min_indicators_per_strategy", 1)))
            max_inds = max(min_inds, min(4, int(config.get("max_indicators_per_strategy", 2))))

            cfg_sizing = config.get("sizing_mode", "FIXED_RISK")
            cfg_risk_pct = float(config.get("risk_per_trade_pct", 1.0))
            cfg_fixed_lot = float(config.get("fixed_lot", 0.01))
            cfg_fixed_cash = float(config.get("fixed_cash_risk", 100.0))
            cfg_martingale_mult = float(config.get("martingale_mult", 1.5))

            prop_firm_filter = bool(config.get("prop_firm_filter", False))

            direction = config.get("direction", "BOTH")
            if direction not in ("BOTH", "LONG_ONLY", "SHORT_ONLY"):
                direction = "BOTH"

            risk_rules: Dict[str, Any] = {}
            # Loss caps: 0/None = free to vary during generation
            for k in (
                "max_daily_loss_pct", "max_weekly_loss_pct", "max_monthly_loss_pct",
                "max_account_loss_pct",
                "max_consecutive_wins", "max_consecutive_losses",
                "max_daily_trades", "max_open_trades",
                "reward_risk_ratio", "fixed_rr", "risk_multiplier",
            ):
                if k in config and config[k] is not None and (float(config[k]) > 0 or k in ACCOUNT_LIMITS
                        or k in ('max_consecutive_wins','max_consecutive_losses')):
                    risk_rules[k] = config[k]
            # Gain caps & consec wins: 0 = free (engine may still pick 0 sometimes)
            for k in (
                "max_daily_gain_pct", "max_weekly_gain_pct",
                "max_monthly_gain_pct", "max_account_gain_pct",
            ):
                if k in config and config[k] is not None and (float(config[k]) > 0 or k in ACCOUNT_LIMITS):
                    risk_rules[k] = config[k]
            # Booleans: always pass explicit user choice
            for k in (
                "no_new_trades_friday", "no_monday_open", "avoid_rollover",
                "close_before_ny_close", "close_before_weekend",
            ):
                if k in config:
                    risk_rules[k] = config[k]

            mode_label = "ALEATORIA" if search_mode == "random" else "GENÉTICA"
            pair_label = ", ".join(f"{s}/{tf}" for s, tf in pairs[:6])
            if len(pairs) > 6:
                pair_label += f" … (+{len(pairs) - 6})"
            self.log(f"Iniciando Fábrica de Algoritmos en modo {mode_label} "
                     f"{'INFINITO CONTINUO' if infinite_mode else 'PROGRAMADO'} sobre {pair_label}...")
            self.log(f"Indicadores activos: {len(enabled_indicators)} | "
                     f"Combinando: {min_inds} a {max_inds} indicadores | Modelado: {modeling_mode}"
                     + (" | Multi-TF COMBINADO (entrada TF bajo + confirmación TF superior)"
                        if mtf_mode == "combined" else ""))
            if parallel_workers > 1:
                self.log(f"Paralelismo: {parallel_workers} workers")

            # --- Load all pair dataframes; attach macro columns if enabled ---
            dfs_map: Dict[str, pd.DataFrame] = {}
            for (psym, ptf) in pairs:
                key = f"{psym}_{ptf}"
                try:
                    d = data_manager.load_data(psym, ptf, start_date=start_date, end_date=end_date)
                except Exception as de:
                    self.log(f"⚠ Sin datos para {key}: {de}")
                    continue
                dfs_map[key] = d

            if not dfs_map:
                raise RuntimeError("No se pudieron cargar datos para ningún par símbolo/timeframe.")

            # --- K: Examen sorpresa (holdout): reservar el último tramo, invisible a la generación ---
            holdout_pct = max(0.0, min(50.0, float(config.get("holdout_pct", 0.0) or 0.0)))
            holdout_map: Dict[str, pd.DataFrame] = {}
            if holdout_pct > 0:
                for _hk, _hd in list(dfs_map.items()):
                    if len(_hd) < 40:
                        continue
                    _split = int(len(_hd) * (1.0 - holdout_pct / 100.0))
                    _split = max(20, min(len(_hd) - 10, _split))
                    holdout_map[_hk] = _hd.iloc[_split:]
                    dfs_map[_hk] = _hd.iloc[:_split]
                if holdout_map:
                    _h0 = next(iter(holdout_map.values()))
                    self.log(f"Examen sorpresa (holdout {holdout_pct:.0f}%): último tramo reservado "
                             f"({len(_h0)} velas desde {_h0.index[0].date()}) — no visible para la generación.")
                else:
                    self.log(f"⚠ Holdout {holdout_pct:.0f}%: datos insuficientes; se genera con el rango completo.")

            first_df = next(iter(dfs_map.values()))
            self.log(f"Datos históricos listos: {len(dfs_map)} pares | "
                     f"ej. {len(first_df)} velas ({first_df.index[0].date()} a {first_df.index[-1].date()}).")

            all_tested_sharpes: List[float] = []

            def make_one(gen: int) -> Strategy:
                if len(pairs) > 1:
                    sym, tf = random.choice(pairs)
                else:
                    sym, tf = pairs[0] if pairs else (symbol, timeframe)
                strat = self.create_random_strategy(
                    sym, tf, enabled_indicators, enabled_entry_types, enabled_exit_modes,
                    generation=gen,
                    min_indicators=min_inds,
                    max_indicators=max_inds,
                    sizing_mode=cfg_sizing,
                    risk_per_trade_pct=cfg_risk_pct,
                    fixed_lot=cfg_fixed_lot,
                    fixed_cash_risk=cfg_fixed_cash,
                    martingale_mult=cfg_martingale_mult,
                    direction=direction,
                    prop_firm_filter=prop_firm_filter,
                    risk_rules=risk_rules
                )
                # F: en modo combinado, confirmar en el siguiente TF superior seleccionado
                if mtf_mode == "combined":
                    _base_min = TF_MINUTES.get(strat.timeframe, 0)
                    _higher = [tf2 for tf2 in timeframes_list if TF_MINUTES.get(tf2, 0) > _base_min]
                    if _higher:
                        strat.mtf_timeframe = min(_higher, key=lambda t: TF_MINUTES[t])
                return strat

            def handle_results(population: List[Strategy], results: List[BacktestResult], gen: int, offset=0, total=None):
                pop_size_local = total or len(population)
                evaluated: List[Strategy] = []
                for local_idx, (individual, res) in enumerate(zip(population, results)):
                    ind_idx=offset+local_idx
                    if self.should_stop:
                        break
                    m = res.metrics
                    all_tested_sharpes.append(m["sharpe_ratio"])
                    pnl_arr = np.array([t["pnl_usd"] for t in res.trades]) if res.trades else np.array([])
                    passes, _dsr = self._classify(m, cls_cfg, all_tested_sharpes, pnl_arr)
                    if m['total_trades']==0:self.no_trade_count+=1
                    for reason in m.get('filter_failures',[]):
                        self.rejection_counts[reason]=self.rejection_counts.get(reason,0)+1
                    if challenge_cfg["enabled"] and (objective == "pass_rate" or passes):
                        try:
                            pf = validation_suite.evaluate_prop_firm(
                                individual,
                                dfs_map.get(f"{individual.symbol}_{individual.timeframe}"),
                                challenge_capital=challenge_cfg["capital"],
                                profit_target_pct=challenge_cfg["target_pct"],
                                max_daily_loss_pct=challenge_cfg["daily_loss_pct"],
                                max_total_loss_pct=challenge_cfg["total_dd_pct"],
                                min_trading_days=challenge_cfg["min_trading_days"],
                                simulations_count=challenge_cfg["simulations"],
                            )
                            if pf.get("total_simulations", 0) > 0:
                                m["pass_rate_pct"] = pf["pass_rate_pct"]
                                m["pass_rate"] = pf["pass_rate_pct"]
                                m["challenge"] = pf
                                if (challenge_cfg["min_pass_rate"] > 0
                                        and pf["pass_rate_pct"] < challenge_cfg["min_pass_rate"]):
                                    passes = False
                        except Exception as ce:
                            self.log(f"⚠ Simulación de reto falló: {ce}")
                    # --- K: examen sorpresa — las aprobadas se evalúan SOLO en el tramo reservado ---
                    if passes and holdout_map:
                        _hdf = holdout_map.get(f"{individual.symbol}_{individual.timeframe}")
                        if _hdf is not None and len(_hdf) >= 10:
                            try:
                                _htf_hold = None
                                if getattr(individual, "mtf_timeframe", None):
                                    _htf_hold = holdout_map.get(
                                        f"{individual.symbol}_{individual.mtf_timeframe}")
                                _hres = backtester.run_backtest(
                                    individual, _hdf, htf_df=_htf_hold,
                                    initial_deposit=initial_deposit, **bt_kwargs)
                                _hm = _hres.metrics
                                m["holdout"] = {
                                    "net_profit": round(float(_hm.get("total_return_usd", 0.0) or 0.0), 2),
                                    "sharpe_ratio": round(float(_hm.get("sharpe_ratio", 0.0) or 0.0), 3),
                                    "win_rate_pct": round(float(_hm.get("win_rate_pct", 0.0) or 0.0), 1),
                                    "trades": int(_hm.get("total_trades", len(_hres.trades)) or 0),
                                    "max_drawdown_pct": round(float(_hm.get("max_drawdown_pct", 0.0) or 0.0), 2),
                                    "bars": int(len(_hdf)),
                                }
                            except Exception as he:
                                self.log(f"⚠ Examen sorpresa falló ({individual.symbol}/{individual.timeframe}): {he}")
                    individual.fitness = self.calculate_fitness(m, objective=objective)
                    self.tested_count += 1
                    if search_mode == 'genetic':
                        fraction = (ind_idx + 1) / max(pop_size_local, 1)
                        self.progress_pct = round(100.0 * (fraction if infinite_mode else
                            (gen - 1 + fraction) / max(generations_limit, 1)), 1)
                    self._ingest_result(
                        individual, res, m, passes, objective,
                        max_candidates, gen, ind_idx, pop_size_local,
                        df=dfs_map.get(f"{individual.symbol}_{individual.timeframe}")
                    )
                    evaluated.append(individual)
                return evaluated

            def evaluate_population(population,gen):
                if parallel_workers>1:
                    results=self._evaluate_batch(population,dfs_map,initial_deposit,bt_kwargs,parallel_workers)
                    return handle_results(population,results,gen)
                evaluated=[]
                for index,individual in enumerate(population):
                    if self.should_stop:break
                    results=self._evaluate_batch([individual],dfs_map,initial_deposit,bt_kwargs,0)
                    evaluated.extend(handle_results([individual],results,gen,offset=index,total=len(population)))
                    if search_mode=='random':
                        self.progress_pct=round(100*self.tested_count/max(num_combinations,1),1)
                return evaluated

            max_candidates = config.get("max_candidates", None)
            if max_candidates is not None:
                max_candidates = int(max_candidates) if int(max_candidates) > 0 else None

            # =================================================================
            # RANDOM MODE: pure sweep of N combinations (no evolution)
            # =================================================================
            if search_mode == "random":
                done = 0
                batch_idx = 0
                while not self.should_stop and done < num_combinations:
                    batch_n = min(pop_size, num_combinations - done)
                    population = [make_one(0) for _ in range(batch_n)]
                    evaluated=evaluate_population(population,gen=0)
                    done += len(evaluated)
                    batch_idx += 1
                    self.progress_pct = round(100.0 * done / max(num_combinations, 1), 1)
                    if batch_idx % 5 == 0 or done >= num_combinations:
                        self.log(f"--- Random {done}/{num_combinations} ({self.progress_pct}%) | "
                                 f"Aceptadas: {self.accepted_count} | Descartadas: {self.discarded_count}")

                self.log(f"⏹ Exploración aleatoria finalizada. Total creadas: {self.tested_count} | "
                         f"Descartadas: {self.discarded_count} | Aprobadas: {self.accepted_count}.")
                return

            # =================================================================
            # GENETIC MODE
            # =================================================================
            population: List[Strategy] = [make_one(0) for _ in range(pop_size)]
            gen = 0
            evaluated_population: List[Strategy] = []

            while not self.should_stop and (infinite_mode or gen < generations_limit):
                gen += 1
                self.current_generation = gen
                self.log(f"--- Generación {gen} ({'Modo Infinito' if infinite_mode else f'{gen}/{generations_limit}'}) ---")

                evaluated_population = evaluate_population(population,gen)

                if self.should_stop:
                    break

                evaluated_population.sort(key=lambda x: x.fitness, reverse=True)

                next_gen: List[Strategy] = []
                elite_count = max(2, int(pop_size * 0.10))
                for e in evaluated_population[:elite_count]:
                    elite_copy = copy.deepcopy(e)
                    elite_copy.generation = gen + 1
                    next_gen.append(elite_copy)

                while len(next_gen) < pop_size:
                    t1 = random.sample(evaluated_population, min(3, len(evaluated_population)))
                    parent_a = max(t1, key=lambda x: x.fitness)
                    t2 = random.sample(evaluated_population, min(3, len(evaluated_population)))
                    parent_b = max(t2, key=lambda x: x.fitness)

                    child = self.crossover(parent_a, parent_b, generation=gen + 1)
                    if random.random() < 0.35:
                        child = self.mutate(child, enabled_indicators, enabled_entry_types, enabled_exit_modes)

                    next_gen.append(child)

                population = next_gen
                if not infinite_mode:
                    self.progress_pct = round(100.0 * gen / max(generations_limit, 1), 1)

            self.log(f"⏹ Exploración finalizada. Total creadas: {self.tested_count} | "
                     f"Descartadas: {self.discarded_count} | Aprobadas: {self.accepted_count}.")

        except Exception as e:
            self.log(f"Error en la exploración: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_running = False

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            if self.candidates_passed:
                avg_win_rate = float(np.mean([c["metrics"]["win_rate_pct"] for c in self.candidates_passed]))
                avg_sharpe = float(np.mean([c["metrics"]["sharpe_ratio"] for c in self.candidates_passed]))
                best_sharpe = float(max(c["metrics"]["sharpe_ratio"] for c in self.candidates_passed))
            else:
                avg_win_rate = 0.0
                avg_sharpe = 0.0
                best_sharpe = 0.0

            return {
                "is_running": self.is_running,
                "search_mode": self.search_mode,
                "current_generation": self.current_generation,
                "progress_pct": self.progress_pct,
                "total_combinations": self.total_combinations,
                "tested_count": self.tested_count,
                "no_trade_count": self.no_trade_count,
                "rejection_counts": dict(self.rejection_counts),
                "discarded_count": self.discarded_count,
                "accepted_count": self.accepted_count,
                "candidates_count": len(self.candidates_passed),
                "best_sharpe": round(best_sharpe, 2),
                "avg_sharpe": round(avg_sharpe, 2),
                "avg_win_rate": round(avg_win_rate, 1),
                "best_candidate": self.best_candidate,
                "log_messages": self.log_messages[-10:],
                "neural_nodes_count": len(self.neural_nodes)
            }

    def get_candidates(self) -> List[Dict[str, Any]]:
        with self.lock:
            return copy.deepcopy(self.candidates_passed)

    def clear_candidates(self):
        with self.lock:
            self.candidates_passed.clear()
            self.tested_count = 0
            self.discarded_count = 0
            self.best_candidate = None

    def get_neural_tree(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "nodes": self.neural_nodes[-200:],
                "edges": self.neural_edges[-250:]
            }


# Global singleton
genetic_engine = GeneticEngine()

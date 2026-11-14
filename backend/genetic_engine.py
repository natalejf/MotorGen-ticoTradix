"""
Complete Genetic Engine & Strategy Factory Replica for TradingNote
Implements:
- Population generation & smart seeding with all 28 indicators
- Continuous / Infinite exploration mode (runs until user stops)
- Dedicated Classification filters (Win Rate, Trades, Max DD, Net Profit, Sharpe, PF, DSR)
- Order Entry Types (Market, Limit, Stop) & Exit Types (ATR, Trailing, BE, Swing, Time, Partial)
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
from typing import Dict, List, Any, Optional, Callable
from backend.strategy import Strategy, Condition
from backend.backtester import backtester, BacktestResult
from backend.validation import validation_suite
from backend.data_manager import data_manager

# All 28 Technical Indicators with Pre-configured Generic Quantitative Defaults
ALL_28_INDICATORS = {
    # 1. Tendencia (8)
    "EMA": {"name": "Media Móvil Exponencial", "family": "Tendencia", "from": 10, "step": 10, "to": 200, "default_param": "period"},
    "SMA": {"name": "Media Móvil Simple", "family": "Tendencia", "from": 20, "step": 20, "to": 200, "default_param": "period"},
    "DEMA": {"name": "Doble Media Exponencial", "family": "Tendencia", "from": 9, "step": 5, "to": 100, "default_param": "period"},
    "TEMA": {"name": "Triple Media Exponencial", "family": "Tendencia", "from": 9, "step": 5, "to": 100, "default_param": "period"},
    "HMA": {"name": "Hull Moving Average", "family": "Tendencia", "from": 9, "step": 3, "to": 50, "default_param": "period"},
    "WMA": {"name": "Media Ponderada Ponderal", "family": "Tendencia", "from": 10, "step": 5, "to": 100, "default_param": "period"},
    "KAMA": {"name": "Kaufman Adaptive MA", "family": "Tendencia", "from": 10, "step": 5, "to": 50, "default_param": "period"},
    "SUPERTREND": {"name": "SuperTrend ATR Channel", "family": "Tendencia", "from": 7, "step": 7, "to": 21, "default_param": "period"},
    
    # 2. Momentum (6)
    "RSI": {"name": "Relative Strength Index", "family": "Momentum", "from": 7, "step": 7, "to": 28, "default_param": "period"},
    "STOCHASTIC": {"name": "Estocástico (%K & %D)", "family": "Momentum", "from": 9, "step": 3, "to": 21, "default_param": "k_period"},
    "MACD": {"name": "MACD (Histograma & Señal)", "family": "Momentum", "from": 8, "step": 2, "to": 16, "default_param": "fast"},
    "CCI": {"name": "Commodity Channel Index", "family": "Momentum", "from": 14, "step": 6, "to": 40, "default_param": "period"},
    "ROC": {"name": "Rate of Change", "family": "Momentum", "from": 8, "step": 4, "to": 24, "default_param": "period"},
    "WILLIAMS_R": {"name": "Williams %R", "family": "Momentum", "from": 10, "step": 4, "to": 28, "default_param": "period"},
    
    # 3. Volatilidad (5)
    "BOLLINGER": {"name": "Bandas de Bollinger (%B)", "family": "Volatilidad", "from": 10, "step": 10, "to": 50, "default_param": "period"},
    "ATR": {"name": "Average True Range", "family": "Volatilidad", "from": 10, "step": 2, "to": 24, "default_param": "period"},
    "KELTNER": {"name": "Canales de Keltner", "family": "Volatilidad", "from": 10, "step": 5, "to": 40, "default_param": "period"},
    "DONCHIAN": {"name": "Canales de Donchian", "family": "Volatilidad", "from": 10, "step": 5, "to": 50, "default_param": "period"},
    "STDDEV": {"name": "Desviación Estándar", "family": "Volatilidad", "from": 10, "step": 5, "to": 50, "default_param": "period"},
    
    # 4. Volumen (4)
    "VOLUME_SMA": {"name": "SMA de Volumen", "family": "Volumen", "from": 10, "step": 5, "to": 50, "default_param": "period"},
    "OBV": {"name": "On-Balance Volume", "family": "Volumen", "from": 1, "step": 1, "to": 1, "default_param": "period"},
    "CMF": {"name": "Chaikin Money Flow", "family": "Volumen", "from": 10, "step": 5, "to": 40, "default_param": "period"},
    "MFI": {"name": "Money Flow Index", "family": "Volumen", "from": 10, "step": 4, "to": 28, "default_param": "period"},
    
    # 5. Ciclo & Estructurales (5)
    "RCI": {"name": "Rank Correlation Index (RCI)", "family": "Ciclo", "from": 7, "step": 2, "to": 21, "default_param": "period"},
    "ADX": {"name": "Average Directional Index", "family": "Ciclo", "from": 10, "step": 5, "to": 25, "default_param": "period"},
    "PSAR": {"name": "Parabolic SAR", "family": "Ciclo", "from": 0.01, "step": 0.01, "to": 0.04, "default_param": "step"},
    "ICHIMOKU": {"name": "Ichimoku Kinko Hyo (Kijun/Tenkan)", "family": "Ciclo", "from": 9, "step": 1, "to": 26, "default_param": "tenkan_p"},
    "AROON": {"name": "Aroon Oscillator", "family": "Ciclo", "from": 10, "step": 4, "to": 25, "default_param": "period"}
}

ALL_ENTRY_TYPES = ["MARKET", "LIMIT", "STOP"]
ALL_EXIT_MODES = ["ATR_CLASSIC", "TRAILING_ATR", "BREAKEVEN", "STRUCTURE_SWING", "TIME_EXIT", "PARTIAL_TP"]
SESSION_FILTERS = ["ALL", "LONDON", "NEW_YORK", "TOKYO", "OVERLAP_LDN_NY"]
SIZING_MODES = ["FIXED_RISK", "FIXED_LOT", "MARTINGALE", "ANTI_MARTINGALE"]

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
        
        self.candidates_passed: List[Dict[str, Any]] = []
        self.best_candidate: Optional[Dict[str, Any]] = None
        self.log_messages: List[str] = []

        # 3D Neural Explorer Tree (Nodes and Axons)
        self.neural_nodes: List[Dict[str, Any]] = []
        self.neural_edges: List[Dict[str, Any]] = []

        self.lock = threading.Lock()

    def reset_state(self):
        with self.lock:
            self.tested_count = 0
            self.discarded_count = 0
            self.accepted_count = 0
            self.progress_pct = 0.0
            self.current_generation = 0
            self.candidates_passed = []
            self.best_candidate = None
            self.log_messages = []
            self.neural_nodes = []
            self.neural_edges = []

    def log(self, msg: str):
        with self.lock:
            self.log_messages.append(msg)
            if len(self.log_messages) > 100:
                self.log_messages.pop(0)

    # =========================================================================
    # INDIVIDUAL GENERATION & MUTATION OPERATORS
    # =========================================================================

    def create_random_condition(self, enabled_indicators: List[str], is_buy: bool) -> Condition:
        if not enabled_indicators:
            enabled_indicators = ["EMA", "RSI", "SUPERTREND", "MACD"]
        
        ind = random.choice(enabled_indicators)
        ind_u = ind.upper()

        if ind_u == "RSI":
            p = {"period": random.choice([7, 9, 14, 21, 28])}
            op = "CROSS_ABOVE" if is_buy else "CROSS_BELOW"
            val = random.choice([25.0, 30.0, 35.0, 40.0]) if is_buy else random.choice([60.0, 65.0, 70.0, 75.0])
            return Condition("RSI", p, op, "value", target_value=val)

        elif ind_u == "SUPERTREND":
            p = {"period": random.choice([10, 14]), "multiplier": random.choice([2.0, 3.0, 3.5])}
            op = "BULLISH" if is_buy else "BEARISH"
            return Condition("SUPERTREND", p, op, "value", target_value=0.0)

        elif ind_u == "PSAR":
            p = {"step": 0.02, "max_step": 0.2}
            op = "BULLISH" if is_buy else "BEARISH"
            return Condition("PSAR", p, op, "value", target_value=0.0)

        elif ind_u == "MACD":
            p = {"fast": 12, "slow": 26, "signal": 9, "sub": "hist"}
            op = "CROSS_ABOVE" if is_buy else "CROSS_BELOW"
            return Condition("MACD", p, op, "value", target_value=0.0)

        elif ind_u == "STOCHASTIC":
            p = {"k_period": 14, "d_period": 3, "sub": "k"}
            op = "CROSS_ABOVE" if is_buy else "CROSS_BELOW"
            val = 20.0 if is_buy else 80.0
            return Condition("STOCHASTIC", p, op, "value", target_value=val)

        elif ind_u == "BOLLINGER":
            p = {"period": 20, "std_dev": 2.0, "sub": "pct_b"}
            op = "LESS_THAN" if is_buy else "GREATER_THAN"
            val = 0.15 if is_buy else 0.85
            return Condition("BOLLINGER", p, op, "value", target_value=val)

        elif ind_u == "RCI":
            p = {"period": random.choice([9, 14, 21])}
            op = "CROSS_ABOVE" if is_buy else "CROSS_BELOW"
            val = -60.0 if is_buy else 60.0
            return Condition("RCI", p, op, "value", target_value=val)

        elif ind_u == "ADX":
            p = {"period": 14, "sub": "adx"}
            return Condition("ADX", p, "GREATER_THAN", "value", target_value=random.choice([20.0, 25.0]))

        elif ind_u == "AROON":
            p = {"period": 14}
            op = "GREATER_THAN" if is_buy else "LESS_THAN"
            return Condition("AROON", p, op, "value", target_value=0.0)

        elif ind_u == "CCI":
            p = {"period": 20}
            op = "CROSS_ABOVE" if is_buy else "CROSS_BELOW"
            val = -100.0 if is_buy else 100.0
            return Condition("CCI", p, op, "value", target_value=val)

        elif ind_u == "ROC":
            p = {"period": 12}
            op = "CROSS_ABOVE" if is_buy else "CROSS_BELOW"
            return Condition("ROC", p, op, "value", target_value=0.0)

        elif ind_u == "WILLIAMS_R":
            p = {"period": 14}
            op = "CROSS_ABOVE" if is_buy else "CROSS_BELOW"
            val = -80.0 if is_buy else -20.0
            return Condition("WILLIAMS_R", p, op, "value", target_value=val)

        elif ind_u in ["EMA", "SMA", "DEMA", "TEMA", "HMA", "WMA", "KAMA"]:
            fast_p = random.choice([9, 14, 20, 25])
            slow_p = random.choice([50, 100, 200])
            op = "CROSS_ABOVE" if is_buy else "CROSS_BELOW"
            return Condition(ind_u, {"period": fast_p}, op, "indicator", target_indicator=ind_u, target_params={"period": slow_p})

        elif ind_u in ["KELTNER", "DONCHIAN"]:
            p = {"period": 20}
            op = "CROSS_ABOVE" if is_buy else "CROSS_BELOW"
            return Condition(ind_u, p, op, "value", target_value=0.0)

        elif ind_u in ["MFI", "CMF", "OBV", "VOLUME_SMA"]:
            p = {"period": 14}
            op = "GREATER_THAN" if is_buy else "LESS_THAN"
            val = 50.0 if ind_u == "MFI" else 0.0
            return Condition(ind_u, p, op, "value", target_value=val)

        else:
            p = {"period": 14}
            return Condition("RSI", p, "GREATER_THAN" if is_buy else "LESS_THAN", "value", target_value=50.0)

    def create_random_strategy(
        self,
        symbol: str,
        timeframe: str,
        enabled_indicators: List[str],
        enabled_entry_types: List[str],
        enabled_exit_modes: List[str],
        generation: int = 0
    ) -> Strategy:
        num_conds = random.choice([1, 2, 2, 3])
        buy_conds = [self.create_random_condition(enabled_indicators, is_buy=True) for _ in range(num_conds)]
        sell_conds = [self.create_random_condition(enabled_indicators, is_buy=False) for _ in range(num_conds)]

        entry_type = random.choice(enabled_entry_types) if enabled_entry_types else "MARKET"
        exit_mode = random.choice(enabled_exit_modes) if enabled_exit_modes else "ATR_CLASSIC"

        sl_atr = random.choice([1.0, 1.5, 2.0, 2.5, 3.0])
        tp_atr = random.choice([1.5, 2.0, 3.0, 4.0, 5.0, 6.0])
        trail_atr = random.choice([1.0, 1.5, 2.0])
        be_atr = random.choice([1.0, 1.2, 1.5])
        swing_bars = random.choice([10, 15, 20])
        max_bars = random.choice([12, 24, 36, 48])

        session = random.choice(SESSION_FILTERS)
        sizing = random.choice(SIZING_MODES)
        risk_pct = random.choice([0.5, 1.0, 1.5, 2.0])
        max_daily_loss = random.choice([2.5, 3.0, 4.0])

        strat = Strategy(
            symbol=symbol,
            timeframe=timeframe,
            direction="BOTH",
            entry_order_type=entry_type,
            buy_conditions=buy_conds,
            sell_conditions=sell_conds,
            session_filter=session,
            exit_mode=exit_mode,
            sl_atr=sl_atr,
            tp_atr=tp_atr,
            trail_atr=trail_atr,
            be_atr=be_atr,
            swing_bars=swing_bars,
            max_bars=max_bars,
            sizing_mode=sizing,
            risk_per_trade_pct=risk_pct,
            max_daily_loss_pct=max_daily_loss,
            generation=generation
        )
        return strat

    def crossover(self, parent_a: Strategy, parent_b: Strategy, generation: int) -> Strategy:
        child = copy.deepcopy(parent_a)
        child.id = f"strat_g{generation}_{random.randint(1000, 9999)}"
        child.generation = generation
        child.parent_ids = [parent_a.id, parent_b.id]

        if random.random() < 0.5:
            child.sell_conditions = copy.deepcopy(parent_b.sell_conditions)
        if random.random() < 0.5:
            child.entry_order_type = parent_b.entry_order_type
        if random.random() < 0.5:
            child.exit_mode = parent_b.exit_mode
            child.sl_atr = parent_b.sl_atr
            child.tp_atr = parent_b.tp_atr
            child.trail_atr = parent_b.trail_atr
            child.be_atr = parent_b.be_atr

        return child

    def mutate(
        self,
        strategy: Strategy,
        enabled_indicators: List[str],
        enabled_entry_types: List[str],
        enabled_exit_modes: List[str]
    ) -> Strategy:
        mutant = copy.deepcopy(strategy)
        mutation_type = random.choice(["param_drift", "exit_tweak", "entry_type_tweak", "condition_swap", "session_tweak", "risk_tweak"])

        if mutation_type == "param_drift":
            all_conds = mutant.buy_conditions + mutant.sell_conditions
            if all_conds:
                target_cond = random.choice(all_conds)
                if "period" in target_cond.params:
                    cur = target_cond.params["period"]
                    drift = random.choice([-5, -2, 2, 5])
                    target_cond.params["period"] = max(5, cur + drift)
                if target_cond.target_type == "value":
                    target_cond.target_value = round(target_cond.target_value * random.choice([0.9, 1.1]), 2)

        elif mutation_type == "exit_tweak":
            mutant.sl_atr = round(max(0.5, mutant.sl_atr + random.choice([-0.25, 0.25])), 2)
            mutant.tp_atr = round(max(1.0, mutant.tp_atr + random.choice([-0.5, 0.5])), 2)
            if enabled_exit_modes and random.random() < 0.3:
                mutant.exit_mode = random.choice(enabled_exit_modes)

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
        else:
            return float(metrics["tn_score"])

    # =========================================================================
    # CORE EXPLORATION RUNNER (INFINITE GENERATION SUPPORT)
    # =========================================================================

    def start_exploration(
        self,
        config: Dict[str, Any],
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        if self.is_running:
            raise RuntimeError("Ya hay una exploración en curso.")

        self.reset_state()
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

    def _run_exploration_worker(
        self,
        config: Dict[str, Any],
        on_progress: Optional[Callable[[Dict[str, Any]], None]]
    ):
        try:
            symbol = config.get("symbol", "EURUSD")
            timeframe = config.get("timeframe", "1h")
            initial_deposit = float(config.get("initial_deposit", 10000.0))
            objective = config.get("objective", "tn_score")

            # Selection sets from user
            enabled_indicators = config.get("enabled_indicators", list(ALL_28_INDICATORS.keys()))
            enabled_entry_types = config.get("enabled_entry_types", ALL_ENTRY_TYPES)
            enabled_exit_modes = config.get("enabled_exit_modes", ALL_EXIT_MODES)

            # Infinite mode (True by default or if generations <= 0)
            infinite_mode = config.get("infinite_mode", True)
            generations_limit = int(config.get("generations", 0)) if not infinite_mode else 999999
            pop_size = int(config.get("population_size", 30))
            self.population_size = pop_size

            # Classification & Admission Criteria (Pestaña Clasificación)
            min_win_rate = float(config.get("min_win_rate", 35.0))
            min_trades = int(config.get("min_trades", 8))
            max_drawdown = float(config.get("max_drawdown", 20.0))
            min_net_profit_usd = float(config.get("min_net_profit_usd", 0.0))
            min_sharpe = float(config.get("min_sharpe", 0.8))
            min_profit_factor = float(config.get("min_profit_factor", 1.1))
            min_dsr = float(config.get("min_dsr", 0.2))

            self.log(f"Iniciando Fábrica de Algoritmos en modo {'INFINITO CONTINUO' if infinite_mode else 'PROGRAMADO'} sobre {symbol} ({timeframe})...")
            self.log(f"Indicadores activos: {len(enabled_indicators)}/28 · Entradas: {len(enabled_entry_types)} · Salidas: {len(enabled_exit_modes)}")

            df = data_manager.load_data(symbol, timeframe)
            self.log(f"Datos históricos listos: {len(df)} velas ({df.index[0].date()} a {df.index[-1].date()}).")

            # Initial population
            population: List[Strategy] = [
                self.create_random_strategy(
                    symbol, timeframe, enabled_indicators, enabled_entry_types, enabled_exit_modes, generation=0
                )
                for _ in range(pop_size)
            ]

            gen = 0
            all_tested_sharpes = []

            while not self.should_stop and (infinite_mode or gen < generations_limit):
                gen += 1
                self.current_generation = gen
                self.log(f"--- Generación {gen} ({'Modo Infinito' if infinite_mode else f'{gen}/{generations_limit}'}) ---")

                evaluated_population: List[Strategy] = []

                for ind_idx, individual in enumerate(population):
                    if self.should_stop:
                        break

                    res = backtester.run_backtest(individual, df, initial_deposit=initial_deposit)
                    m = res.metrics
                    all_tested_sharpes.append(m["sharpe_ratio"])

                    # Calculate DSR
                    sharpe_var = float(np.var(all_tested_sharpes)) if len(all_tested_sharpes) > 2 else 0.25
                    pnl_arr = np.array([t["pnl_usd"] for t in res.trades]) if res.trades else np.array([])
                    dsr_val = validation_suite.calculate_dsr(
                        observed_sharpe=m["sharpe_ratio"],
                        num_trials=len(all_tested_sharpes),
                        sharpe_variance=sharpe_var,
                        returns=pnl_arr
                    )
                    m["dsr"] = dsr_val

                    # Calculate Fitness
                    individual.fitness = self.calculate_fitness(m, objective=objective)

                    self.tested_count += 1

                    # Check Classification Criteria
                    passes_classification = (
                        m["win_rate_pct"] >= min_win_rate and
                        m["total_trades"] >= min_trades and
                        m["max_drawdown_pct"] <= max_drawdown and
                        m["total_return_usd"] >= min_net_profit_usd and
                        m["sharpe_ratio"] >= min_sharpe and
                        m["profit_factor"] >= min_profit_factor and
                        m["dsr"] >= min_dsr
                    )

                    # 3D Node data for Neural Explorer
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

                    if passes_classification:
                        self.accepted_count += 1
                        candidate_entry = {
                            "strategy": individual.to_dict(),
                            "metrics": m,
                            "equity_curve": res.equity_curve,
                            "sparkline": [e["equity"] for e in res.equity_curve[::max(1, len(res.equity_curve)//25)]],
                            "trades_sample": res.trades[:15],
                            "rules_desc": individual.to_human_description(),
                            "indicators_used": individual.get_used_indicators(),
                            "passed_filters": True
                        }
                        
                        # Add or update
                        existing_ids = [c["strategy"]["id"] for c in self.candidates_passed]
                        if individual.id not in existing_ids:
                            self.candidates_passed.append(candidate_entry)
                            self.candidates_passed.sort(key=lambda x: x["metrics"]["tn_score"], reverse=True)

                        if self.best_candidate is None or m["tn_score"] > self.best_candidate["metrics"]["tn_score"]:
                            self.best_candidate = candidate_entry
                            self.log(f"★ APROBADO: Algo {individual.id[-4:]} | TN Score: {m['tn_score']} | Net Profit: +${m['total_return_usd']:,.2f} | Win Rate: {m['win_rate_pct']}% | Trades: {m['total_trades']}")

                    else:
                        self.discarded_count += 1

                    evaluated_population.append(individual)

                # Sort by fitness
                evaluated_population.sort(key=lambda x: x.fitness, reverse=True)

                # Selection, Crossover & Mutation for next generation
                if not self.should_stop:
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

            self.log(f"⏹ Exploración finalizada. Total creadas: {self.tested_count} | Descartadas: {self.discarded_count} | Aprobadas: {self.accepted_count}.")

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
                best_sharpe = float(max([c["metrics"]["sharpe_ratio"] for c in self.candidates_passed]))
            else:
                avg_win_rate = 0.0
                avg_sharpe = 0.0
                best_sharpe = 0.0

            return {
                "is_running": self.is_running,
                "current_generation": self.current_generation,
                "tested_count": self.tested_count,
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

    def get_neural_tree(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "nodes": self.neural_nodes[-200:],
                "edges": self.neural_edges[-250:]
            }

# Global singleton
genetic_engine = GeneticEngine()

"""
Strategy and Chromosome Representation for TradingNote Genetic Engine
Defines strategy genome, entry conditions, exit modes, risk management,
and human-readable rules generator.
"""

import uuid
import copy
import random
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from backend.indicators import indicator_engine

class Condition:
    def __init__(
        self,
        indicator: str,
        params: Dict[str, Any],
        operator: str,
        target_type: str = "value", # "value" or "indicator"
        target_value: float = 0.0,
        target_indicator: Optional[str] = None,
        target_params: Optional[Dict[str, Any]] = None
    ):
        self.indicator = indicator
        self.params = params
        self.operator = operator  # "CROSS_ABOVE", "CROSS_BELOW", "CROSS_BOTH", "GREATER_THAN", "LESS_THAN", "EQUAL_TO", "PRICE_ABOVE", "PRICE_BELOW", "BULLISH", "BEARISH"
        self.target_type = target_type
        self.target_value = target_value
        self.target_indicator = target_indicator
        self.target_params = target_params or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "indicator": self.indicator,
            "params": self.params,
            "operator": self.operator,
            "target_type": self.target_type,
            "target_value": self.target_value,
            "target_indicator": self.target_indicator,
            "target_params": self.target_params
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        return cls(
            indicator=data["indicator"],
            params=data.get("params", {}),
            operator=data["operator"],
            target_type=data.get("target_type", "value"),
            target_value=data.get("target_value", 0.0),
            target_indicator=data.get("target_indicator"),
            target_params=data.get("target_params", {})
        )

    def to_human_string(self, lang: str = "es") -> str:
        if isinstance(self.params, dict):
            p_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
        else:
            p_str = str(self.params)
        ind_str = f"{self.indicator}({p_str})"
        
        op_map = {
            "CROSS_ABOVE": "cruza por encima de",
            "CROSS_BELOW": "cruza por debajo de",
            "CROSS_BOTH": "cruza en ambos sentidos de",
            "GREATER_THAN": "> (mayor que)",
            "LESS_THAN": "< (menor que)",
            "EQUAL_TO": "= (igual a)",
            "BULLISH": "está en tendencia alcista",
            "BEARISH": "está en tendencia bajista"
        }
        op_str = op_map.get(self.operator, self.operator)

        if self.operator in ["BULLISH", "BEARISH"]:
            return f"{ind_str} {op_str}"

        if self.operator in ("PRICE_ABOVE", "PRICE_BELOW"):
            side = "por encima de" if self.operator == "PRICE_ABOVE" else "por debajo de"
            return f"el precio está {side} {ind_str}"

        if self.target_type == "value":
            return f"{ind_str} {op_str} {self.target_value}"
        else:
            tp_str = ", ".join(f"{k}={v}" for k, v in self.target_params.items())
            return f"{ind_str} {op_str} {self.target_indicator}({tp_str})"


class Strategy:
    def __init__(
        self,
        strategy_id: Optional[str] = None,
        name: Optional[str] = None,
        symbol: str = "EURUSD",
        timeframe: str = "1h",
        # F: TF superior de confirmación en modo multi-timeframe combinado (None = off)
        mtf_timeframe: Optional[str] = None,
        direction: str = "BOTH", # "BOTH", "LONG_ONLY", "SHORT_ONLY"
        prop_firm_filter: bool = False, # True si el motor corrió con filtro Prop Firm activo
        entry_order_type: str = "MARKET", # "MARKET", "LIMIT", "STOP"
        buy_conditions: Optional[List[Condition]] = None,
        sell_conditions: Optional[List[Condition]] = None,
        session_filter: str = "ALL", # ALL, SYDNEY, TOKYO, OVERLAP_TOKYO_LDN, LONDON, NEW_YORK, OVERLAP_LDN_NY
        close_before_weekend: bool = True,
        close_before_ny_close: bool = False,
        no_new_trades_friday: bool = False,
        no_monday_open: bool = False,
        avoid_rollover: bool = False,
        # Exit modes: ATR_CLASSIC, PIPS_FIXED, PCT_EXIT, TRAILING_ATR, BREAKEVEN,
        # STRUCTURE_SWING, TIME_EXIT, PARTIAL_TP, ATR_SMOOTHED
        exit_mode: str = "ATR_CLASSIC",
        sl_atr: float = 1.5,
        tp_atr: float = 3.0,
        sl_pips: float = 20.0,
        tp_pips: float = 40.0,
        sl_pct: float = 0.5,
        tp_pct: float = 1.0,
        sl_smooth_mult: float = 1.5,
        tp_smooth_mult: float = 3.0,
        trail_atr: float = 1.5,
        be_atr: float = 1.2,
        swing_bars: int = 15,
        max_bars: int = 24,
        partial_tp1_atr: float = 1.5,
        partial_tp2_atr: float = 4.0,
        partial_pct: float = 50.0,
        # Exit modifiers combinable con modos base (ATR_CLASSIC/PIPS/PCT/SMOOTH)
        modifier_breakeven: bool = False,
        modifier_trailing: bool = False,
        # Risk management & sizing
        sizing_mode: str = "FIXED_RISK", # FIXED_RISK, FIXED_LOT, FIXED_CASH, MARTINGALE, ANTI_MARTINGALE, DCA
        risk_per_trade_pct: float = 1.0,
        fixed_lot: float = 0.1,
        fixed_cash_risk: float = 100.0,
        risk_multiplier: float = 1.0,
        fixed_rr: float = 0.0,  # 0 = disabled; else force TP = SL * fixed_rr
        max_daily_loss_pct: float = 3.0,
        max_weekly_loss_pct: float = 6.0,
        max_monthly_loss_pct: float = 12.0,
        max_account_loss_pct: float = 8.0,
        max_daily_gain_pct: float = 0.0,   # 0 = disabled
        max_weekly_gain_pct: float = 0.0,
        max_monthly_gain_pct: float = 0.0,
        max_account_gain_pct: float = 0.0,
        max_consecutive_wins: int = 0,     # 0 = disabled
        max_consecutive_losses: int = 0,   # 0 = disabled
        max_daily_trades: int = 4,
        max_open_trades: int = 1,
        reward_risk_ratio: float = 0.0,    # 0 = disabled; min TP/SL required
        martingale_mult: float = 1.5,
        # G: Averaging / piramidado (añadir unidades a posición abierta)
        avg_enabled: bool = False,
        avg_mode: str = "dca",            # dca | pyramiding | both
        avg_max_levels: int = 2,
        avg_spacing_unit: str = "atr",    # atr | pips | percent
        avg_spacing_value: float = 1.0,
        avg_size_multiplier: float = 1.0,
        avg_recompute_stop: bool = False,
        parent_ids: Optional[List[str]] = None,
        generation: int = 0
    ):
        self.id = strategy_id or f"strat_{uuid.uuid4().hex[:8]}"
        self.name = name or f"Algo {self.id[-4:].upper()} ({symbol} {timeframe})"
        self.symbol = symbol
        self.timeframe = timeframe
        self.mtf_timeframe = mtf_timeframe
        self.direction = direction
        self.prop_firm_filter = bool(prop_firm_filter)
        self.entry_order_type = entry_order_type
        self.buy_conditions = buy_conditions or []
        self.sell_conditions = sell_conditions or []
        self.session_filter = session_filter
        self.close_before_weekend = close_before_weekend
        self.close_before_ny_close = close_before_ny_close
        self.no_new_trades_friday = no_new_trades_friday
        self.no_monday_open = no_monday_open
        self.avoid_rollover = avoid_rollover

        self.exit_mode = exit_mode
        self.sl_atr = round(sl_atr, 2)
        self.tp_atr = round(tp_atr, 2)
        self.sl_pips = round(sl_pips, 1)
        self.tp_pips = round(tp_pips, 1)
        self.sl_pct = round(sl_pct, 3)
        self.tp_pct = round(tp_pct, 3)
        self.sl_smooth_mult = round(sl_smooth_mult, 2)
        self.tp_smooth_mult = round(tp_smooth_mult, 2)
        self.trail_atr = round(trail_atr, 2)
        self.be_atr = round(be_atr, 2)
        self.swing_bars = int(swing_bars)
        self.max_bars = int(max_bars)
        self.partial_tp1_atr = round(partial_tp1_atr, 2)
        self.partial_tp2_atr = round(partial_tp2_atr, 2)
        self.partial_pct = round(partial_pct, 1)
        self.modifier_breakeven = bool(modifier_breakeven)
        self.modifier_trailing = bool(modifier_trailing)

        self.sizing_mode = sizing_mode
        self.risk_per_trade_pct = round(risk_per_trade_pct, 2)
        self.fixed_lot = round(fixed_lot, 2)
        self.fixed_cash_risk = round(fixed_cash_risk, 2)
        self.risk_multiplier = round(risk_multiplier, 2)
        self.fixed_rr = round(fixed_rr, 2)
        self.max_daily_loss_pct = round(max_daily_loss_pct, 2)
        self.max_weekly_loss_pct = round(max_weekly_loss_pct, 2)
        self.max_monthly_loss_pct = round(max_monthly_loss_pct, 2)
        self.max_account_loss_pct = round(max_account_loss_pct, 2)
        self.max_daily_gain_pct = round(max_daily_gain_pct, 2)
        self.max_weekly_gain_pct = round(max_weekly_gain_pct, 2)
        self.max_monthly_gain_pct = round(max_monthly_gain_pct, 2)
        self.max_account_gain_pct = round(max_account_gain_pct, 2)
        self.max_consecutive_wins = int(max_consecutive_wins)
        self.max_consecutive_losses = int(max_consecutive_losses)
        self.max_daily_trades = int(max_daily_trades)
        self.max_open_trades = int(max_open_trades)
        self.reward_risk_ratio = round(reward_risk_ratio, 2)
        self.martingale_mult = round(martingale_mult, 2)

        # G: Averaging
        self.avg_enabled = bool(avg_enabled)
        self.avg_mode = avg_mode if avg_mode in ("dca", "pyramiding", "both") else "dca"
        self.avg_max_levels = max(1, min(8, int(avg_max_levels)))
        self.avg_spacing_unit = avg_spacing_unit if avg_spacing_unit in ("atr", "pips", "percent") else "atr"
        self.avg_spacing_value = float(avg_spacing_value)
        self.avg_size_multiplier = float(avg_size_multiplier)
        self.avg_recompute_stop = bool(avg_recompute_stop)

        self.parent_ids = parent_ids or []
        self.generation = generation
        self.metrics: Dict[str, Any] = {}
        self.fitness: float = -9999.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "mtf_timeframe": self.mtf_timeframe,
            "direction": self.direction,
            "prop_firm_filter": self.prop_firm_filter,
            "entry_order_type": self.entry_order_type,
            "buy_conditions": [c.to_dict() for c in self.buy_conditions],
            "sell_conditions": [c.to_dict() for c in self.sell_conditions],
            "session_filter": self.session_filter,
            "close_before_weekend": self.close_before_weekend,
            "close_before_ny_close": self.close_before_ny_close,
            "no_new_trades_friday": self.no_new_trades_friday,
            "no_monday_open": self.no_monday_open,
            "avoid_rollover": self.avoid_rollover,
            "exit_mode": self.exit_mode,
            "sl_atr": self.sl_atr,
            "tp_atr": self.tp_atr,
            "sl_pips": self.sl_pips,
            "tp_pips": self.tp_pips,
            "sl_pct": self.sl_pct,
            "tp_pct": self.tp_pct,
            "sl_smooth_mult": self.sl_smooth_mult,
            "tp_smooth_mult": self.tp_smooth_mult,
            "trail_atr": self.trail_atr,
            "be_atr": self.be_atr,
            "swing_bars": self.swing_bars,
            "max_bars": self.max_bars,
            "partial_tp1_atr": self.partial_tp1_atr,
            "partial_tp2_atr": self.partial_tp2_atr,
            "partial_pct": self.partial_pct,
            "modifier_breakeven": self.modifier_breakeven,
            "modifier_trailing": self.modifier_trailing,
            "avg_enabled": self.avg_enabled,
            "avg_mode": self.avg_mode,
            "avg_max_levels": self.avg_max_levels,
            "avg_spacing_unit": self.avg_spacing_unit,
            "avg_spacing_value": self.avg_spacing_value,
            "avg_size_multiplier": self.avg_size_multiplier,
            "avg_recompute_stop": self.avg_recompute_stop,
            "sizing_mode": self.sizing_mode,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "fixed_lot": self.fixed_lot,
            "fixed_cash_risk": self.fixed_cash_risk,
            "risk_multiplier": self.risk_multiplier,
            "fixed_rr": self.fixed_rr,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_weekly_loss_pct": self.max_weekly_loss_pct,
            "max_monthly_loss_pct": self.max_monthly_loss_pct,
            "max_account_loss_pct": self.max_account_loss_pct,
            "max_daily_gain_pct": self.max_daily_gain_pct,
            "max_weekly_gain_pct": self.max_weekly_gain_pct,
            "max_monthly_gain_pct": self.max_monthly_gain_pct,
            "max_account_gain_pct": self.max_account_gain_pct,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_daily_trades": self.max_daily_trades,
            "max_open_trades": self.max_open_trades,
            "reward_risk_ratio": self.reward_risk_ratio,
            "martingale_mult": self.martingale_mult,
            "parent_ids": self.parent_ids,
            "generation": self.generation,
            "metrics": self.metrics,
            "fitness": self.fitness
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Strategy":
        s = cls(
            strategy_id=d.get("id"),
            name=d.get("name"),
            symbol=d.get("symbol", "EURUSD"),
            timeframe=d.get("timeframe", "1h"),
            mtf_timeframe=d.get("mtf_timeframe"),
            direction=d.get("direction", "BOTH"),
            prop_firm_filter=d.get("prop_firm_filter", False),
            entry_order_type=d.get("entry_order_type", "MARKET"),
            buy_conditions=[Condition.from_dict(c) for c in d.get("buy_conditions", [])],
            sell_conditions=[Condition.from_dict(c) for c in d.get("sell_conditions", [])],
            session_filter=d.get("session_filter", "ALL"),
            close_before_weekend=d.get("close_before_weekend", True),
            close_before_ny_close=d.get("close_before_ny_close", False),
            no_new_trades_friday=d.get("no_new_trades_friday", False),
            no_monday_open=d.get("no_monday_open", False),
            avoid_rollover=d.get("avoid_rollover", False),
            exit_mode=d.get("exit_mode", "ATR_CLASSIC"),
            sl_atr=d.get("sl_atr", 1.5),
            tp_atr=d.get("tp_atr", 3.0),
            sl_pips=d.get("sl_pips", 20.0),
            tp_pips=d.get("tp_pips", 40.0),
            sl_pct=d.get("sl_pct", 0.5),
            tp_pct=d.get("tp_pct", 1.0),
            sl_smooth_mult=d.get("sl_smooth_mult", 1.5),
            tp_smooth_mult=d.get("tp_smooth_mult", 3.0),
            trail_atr=d.get("trail_atr", 1.5),
            be_atr=d.get("be_atr", 1.2),
            swing_bars=d.get("swing_bars", 15),
            max_bars=d.get("max_bars", 24),
            partial_tp1_atr=d.get("partial_tp1_atr", 1.5),
            partial_tp2_atr=d.get("partial_tp2_atr", 4.0),
            partial_pct=d.get("partial_pct", 50.0),
            modifier_breakeven=d.get("modifier_breakeven", False),
            modifier_trailing=d.get("modifier_trailing", False),
            avg_enabled=d.get("avg_enabled", False),
            avg_mode=d.get("avg_mode", "dca"),
            avg_max_levels=d.get("avg_max_levels", 2),
            avg_spacing_unit=d.get("avg_spacing_unit", "atr"),
            avg_spacing_value=d.get("avg_spacing_value", 1.0),
            avg_size_multiplier=d.get("avg_size_multiplier", 1.0),
            avg_recompute_stop=d.get("avg_recompute_stop", False),
            sizing_mode=d.get("sizing_mode", "FIXED_RISK"),
            risk_per_trade_pct=d.get("risk_per_trade_pct", 1.0),
            fixed_lot=d.get("fixed_lot", 0.1),
            fixed_cash_risk=d.get("fixed_cash_risk", 100.0),
            risk_multiplier=d.get("risk_multiplier", 1.0),
            fixed_rr=d.get("fixed_rr", 0.0),
            max_daily_loss_pct=d.get("max_daily_loss_pct", 3.0),
            max_weekly_loss_pct=d.get("max_weekly_loss_pct", 6.0),
            max_monthly_loss_pct=d.get("max_monthly_loss_pct", 12.0),
            max_account_loss_pct=d.get("max_account_loss_pct", 8.0),
            max_daily_gain_pct=d.get("max_daily_gain_pct", 0.0),
            max_weekly_gain_pct=d.get("max_weekly_gain_pct", 0.0),
            max_monthly_gain_pct=d.get("max_monthly_gain_pct", 0.0),
            max_account_gain_pct=d.get("max_account_gain_pct", 0.0),
            max_consecutive_wins=d.get("max_consecutive_wins", 0),
            max_consecutive_losses=d.get("max_consecutive_losses", 0),
            max_daily_trades=d.get("max_daily_trades", 4),
            max_open_trades=d.get("max_open_trades", 1),
            reward_risk_ratio=d.get("reward_risk_ratio", 0.0),
            martingale_mult=d.get("martingale_mult", 1.5),
            parent_ids=d.get("parent_ids", []),
            generation=d.get("generation", 0)
        )
        s.metrics = d.get("metrics", {})
        s.fitness = d.get("fitness", -9999.0)
        return s

    def get_used_indicators(self) -> List[str]:
        """Returns unique list of indicator names used in this strategy."""
        inds = set()
        for c in self.buy_conditions + self.sell_conditions:
            inds.add(c.indicator)
            if c.target_type == "indicator" and c.target_indicator:
                inds.add(c.target_indicator)
        inds.add("ATR") # Used by default for sizing & exits
        return sorted(list(inds))

    def get_signature(self) -> str:
        """Returns a deterministic signature string representing the exact logic of the strategy."""
        buy_strs = sorted([c.to_human_string() for c in self.buy_conditions])
        sell_strs = sorted([c.to_human_string() for c in self.sell_conditions])
        return (
            f"{self.symbol}|{self.timeframe}|{self.direction}|{self.entry_order_type}|"
            f"BUY:{';'.join(buy_strs)}|SELL:{';'.join(sell_strs)}|"
            f"{self.exit_mode}|sl:{self.sl_atr}|tp:{self.tp_atr}|pips:{self.sl_pips}/{self.tp_pips}|"
            f"pct:{self.sl_pct}/{self.tp_pct}|smooth:{self.sl_smooth_mult}/{self.tp_smooth_mult}|"
            f"trail:{self.trail_atr}|be:{self.be_atr}|swing:{self.swing_bars}|maxb:{self.max_bars}|"
            f"partial:{self.partial_tp1_atr}/{self.partial_tp2_atr}/{self.partial_pct}|"
            f"sess:{self.session_filter}|rr:{self.reward_risk_ratio}|frr:{self.fixed_rr}"
        )

    def to_human_description(self) -> Dict[str, Any]:
        """Generates detailed human-readable explanation of strategy rules in Spanish."""
        buy_rules = [c.to_human_string("es") for c in self.buy_conditions]
        sell_rules = [c.to_human_string("es") for c in self.sell_conditions]

        # Dirección: ocultar reglas del lado que nunca opera
        if self.direction == "LONG_ONLY":
            sell_rules = []
        elif self.direction == "SHORT_ONLY":
            buy_rules = []

        exit_desc_map = {
            "ATR_CLASSIC": f"Stop Loss a {self.sl_atr}×ATR(14) y Take Profit a {self.tp_atr}×ATR(14).",
            "PIPS_FIXED": f"Stop Loss a {self.sl_pips} pips fijos y Take Profit a {self.tp_pips} pips fijos.",
            "PCT_EXIT": f"Stop Loss a {self.sl_pct}% del precio y Take Profit a {self.tp_pct}% del precio.",
            "TRAILING_ATR": f"Trailing Stop dinámico a {self.trail_atr}×ATR(14) siguiendo el precio en ganancias.",
            "BREAKEVEN": f"Mueve Stop Loss a precio de entrada al alcanzar {self.be_atr}×ATR(14) de beneficio.",
            "STRUCTURE_SWING": f"Stop Loss en el mínimo/máximo estructural de las últimas {self.swing_bars} velas.",
            "TIME_EXIT": f"Cierre forzado tras {self.max_bars} velas si no tocó SL ni TP.",
            "PARTIAL_TP": f"Cierre parcial del {self.partial_pct}% en TP1={self.partial_tp1_atr}×ATR y remanente a TP2={self.partial_tp2_atr}×ATR.",
            "ATR_SMOOTHED": f"Stop Loss a {self.sl_smooth_mult}×ATR suavizado(14,50) y Take Profit a {self.tp_smooth_mult}×ATR suavizado."
        }
        exit_desc = exit_desc_map.get(self.exit_mode, f"Modo de salida: {self.exit_mode}")

        session_map = {
            "ALL": "Operativa continua 24 horas (sin restricción horaria)",
            "SYDNEY": "Sesión Sídney (21:00 a 06:00 UTC)",
            "TOKYO": "Sesión Tokio / Asia (00:00 a 09:00 UTC)",
            "OVERLAP_TOKYO_LDN": "Solapamiento Tokio-Londres (07:00 a 09:00 UTC)",
            "LONDON": "Sesión Londres (07:00 a 16:00 UTC)",
            "NEW_YORK": "Sesión Nueva York (12:00 a 21:00 UTC)",
            "OVERLAP_LDN_NY": "Solapamiento Londres y NY (12:00 a 16:00 UTC - Mayor liquidez)"
        }
        session_desc = session_map.get(self.session_filter, self.session_filter)

        pf_tag = " (Filtro Prop Firm)" if self.prop_firm_filter else ""

        return {
            "direction": self.direction,
            "buy_rules": buy_rules if buy_rules else ([] if self.direction == "SHORT_ONLY" else ["Sin reglas de compra"]),
            "sell_rules": sell_rules if sell_rules else ([] if self.direction == "LONG_ONLY" else ["Sin reglas de venta"]),
            "exit_rules": exit_desc,
            "session": session_desc,
            "risk_rules": [r for r in [
                f"Riesgo por operación: {self.risk_per_trade_pct}% del balance (Modelo: {self.sizing_mode})",
                (f"Pérdida máxima diaria permitida: {self.max_daily_loss_pct}%{pf_tag}" if self.max_daily_loss_pct>0 else None),
                (f"Pérdida máxima semanal permitida: {self.max_weekly_loss_pct}%" if self.max_weekly_loss_pct>0 else None),
                (f"Pérdida máxima mensual permitida: {self.max_monthly_loss_pct}%" if self.max_monthly_loss_pct>0 else None),
                (f"Drawdown máximo total permitido: {self.max_account_loss_pct}%{pf_tag}" if self.max_account_loss_pct>0 else None),
                f"Máximo de operaciones diarias: {self.max_daily_trades}",
                f"Máx. operaciones abiertas: {self.max_open_trades}",
                (f"Relación riesgo/recompensa mínima: 1:{self.reward_risk_ratio}" if self.reward_risk_ratio > 0 else "Sin mínimo R:R forzado"),
                "Cerrar antes del fin de semana: Sí" if self.close_before_weekend else "Mantener en fin de semana: Sí",
                "No abrir operaciones el viernes: Sí" if self.no_new_trades_friday else None,
                "No operar el lunes hasta 01:00 UTC: Sí" if self.no_monday_open else None,
                "Evitar rollover 20:55-21:10 UTC: Sí" if self.avoid_rollover else None,
            ] if r]
        }

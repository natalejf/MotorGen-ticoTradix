"""Portfolio handling for the TradingNote replica.
Provides classes to store strategies, combine them, analyze correlation and persist the data.
"""
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# Base data directory (project root /data)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PORTFOLIO_DIR = DATA_DIR / "portfolios"
STRATEGY_DIR = DATA_DIR / "saved_strategies"

# Ensure required directories exist
for d in (PORTFOLIO_DIR, STRATEGY_DIR):
    d.mkdir(parents=True, exist_ok=True)

class StrategyRecord:
    """Wrap a candidate strategy with its full metrics and metadata for persistence."""
    def __init__(self, record_dict: Dict[str, Any]):
        if "strategy" in record_dict:
            self.id = record_dict["strategy"]["id"]
            self.data = record_dict
        else:
            self.id = record_dict.get("id", f"strat_{int(time.time()*1000)}")
            self.data = {"strategy": record_dict, "metrics": {}}

    def save(self) -> Path:
        """Persist the strategy as JSON under `saved_strategies/<id>.json`."""
        path = STRATEGY_DIR / f"{self.id}.json"
        path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def load(strategy_id: str) -> "StrategyRecord":
        path = STRATEGY_DIR / f"{strategy_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Strategy {strategy_id} not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        return StrategyRecord(data)

    @staticmethod
    def delete(strategy_id: str) -> bool:
        path = STRATEGY_DIR / f"{strategy_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        results = []
        for p in STRATEGY_DIR.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                results.append(data)
            except Exception:
                continue
        return results


class Portfolio:
    """Represents a multi-strategy algorithmic portfolio with risk budget and weights."""
    def __init__(self, name: str, strategies: List[Dict[str, Any]],
                 weights: Optional[List[float]] = None,
                 risk_budget: float = 1.0,
                 portfolio_id: Optional[str] = None,
                 created_at: Optional[str] = None):
        self.name = name
        self.strategies = strategies
        n = max(1, len(strategies))
        self.weights = weights if (weights and len(weights) == n) else [round(1.0 / n, 4)] * n
        self.risk_budget = risk_budget
        self.created_at = created_at or time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Clean ID
        clean_name = "".join(c if c.isalnum() else "_" for c in name.lower())
        self.id = portfolio_id or f"port_{clean_name}_{int(time.time())}"
        
        # Compute combined portfolio analytics (StrategyQuant / TradingNote style)
        self.metrics = self._calculate_portfolio_metrics()

    def _calculate_portfolio_metrics(self) -> Dict[str, Any]:
        """Calculates combined return, average win rate, max estimated DD and diversification score."""
        if not self.strategies:
            return {}

        total_net_profit = 0.0
        weighted_win_rate = 0.0
        total_trades = 0
        symbols_covered = set()
        timeframes_covered = set()

        for idx, item in enumerate(self.strategies):
            strat = item.get("strategy", item)
            metrics = item.get("metrics", {})
            w = self.weights[idx] if idx < len(self.weights) else (1.0 / len(self.strategies))
            
            pnl = metrics.get("total_return_usd", 0.0)
            wr = metrics.get("win_rate_pct", 50.0)
            trades = metrics.get("total_trades", 0)

            total_net_profit += pnl * w
            weighted_win_rate += wr * w
            total_trades += trades
            
            sym = strat.get("symbol", "")
            if sym:
                symbols_covered.add(sym)
            tf = strat.get("timeframe", "")
            if tf:
                timeframes_covered.add(tf)

        # Diversification score based on assets, timeframes and count
        asset_div = min(1.0, len(symbols_covered) / 3.0)
        tf_div = min(1.0, len(timeframes_covered) / 2.0)
        strat_div = min(1.0, len(self.strategies) / 5.0)
        diversification_score = round((asset_div * 0.4 + tf_div * 0.3 + strat_div * 0.3) * 100, 1)

        return {
            "combined_net_profit_usd": round(total_net_profit, 2),
            "weighted_win_rate_pct": round(weighted_win_rate, 1),
            "total_trades": total_trades,
            "strategies_count": len(self.strategies),
            "symbols": list(symbols_covered),
            "timeframes": list(timeframes_covered),
            "diversification_score": diversification_score,
            "estimated_dd_reduction_pct": round(min(50.0, 15.0 * len(symbols_covered)), 1)
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "strategy_ids": [
                s.get("strategy", s).get("id", s.get("id")) for s in self.strategies
            ],
            "weights": self.weights,
            "risk_budget": self.risk_budget,
            "created_at": self.created_at,
            "metrics": self.metrics,
            "strategies_summary": [
                {
                    "id": s.get("strategy", s).get("id"),
                    "name": s.get("strategy", s).get("name"),
                    "symbol": s.get("strategy", s).get("symbol"),
                    "timeframe": s.get("strategy", s).get("timeframe"),
                    "weight": self.weights[i] if i < len(self.weights) else 0.0,
                    "metrics": s.get("metrics", {})
                }
                for i, s in enumerate(self.strategies)
            ]
        }

    def save(self) -> Path:
        """Persist portfolio metadata and snapshot of combined strategies."""
        path = PORTFOLIO_DIR / f"{self.id}.json"
        payload = {
            "meta": self.to_dict(),
            "strategies": self.strategies,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def load(portfolio_id: str) -> "Portfolio":
        path = PORTFOLIO_DIR / f"{portfolio_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Portfolio {portfolio_id} not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data["meta"]
        return Portfolio(
            name=meta["name"],
            strategies=data.get("strategies", []),
            weights=meta.get("weights"),
            risk_budget=meta.get("risk_budget", 1.0),
            portfolio_id=meta.get("id"),
            created_at=meta.get("created_at")
        )

    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        results = []
        for p in PORTFOLIO_DIR.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                results.append(data.get("meta", data))
            except Exception:
                continue
        return results


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
    """Wrap a candidate strategy with its full metrics and metadata for persistence in folders/batches."""
    def __init__(self, record_dict: Dict[str, Any]):
        if "strategy" in record_dict:
            self.id = record_dict["strategy"]["id"]
            self.data = record_dict
        else:
            self.id = record_dict.get("id", f"strat_{int(time.time()*1000)}")
            self.data = {"strategy": record_dict, "metrics": {}}

    def save(self, folder: str = "General") -> Path:
        """Persist the strategy as JSON inside its designated folder under `saved_strategies/<folder>/<id>.json`."""
        clean_folder = "".join(c for c in str(folder) if c.isalnum() or c in (" ", "_", "-", ".", "(", ")")).strip() or "General"
        target_dir = STRATEGY_DIR / clean_folder
        target_dir.mkdir(parents=True, exist_ok=True)
        
        self.data["folder"] = clean_folder
        if "batch_name" not in self.data:
            self.data["batch_name"] = clean_folder
        if "saved_at" not in self.data:
            self.data["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        path = target_dir / f"{self.id}.json"
        path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def load(strategy_id: str) -> "StrategyRecord":
        matches = list(STRATEGY_DIR.glob(f"**/{strategy_id}.json"))
        if not matches:
            raise FileNotFoundError(f"Strategy {strategy_id} not found")
        data = json.loads(matches[0].read_text(encoding="utf-8"))
        return StrategyRecord(data)

    @staticmethod
    def delete(strategy_id: str) -> bool:
        matches = list(STRATEGY_DIR.glob(f"**/{strategy_id}.json"))
        deleted = False
        for p in matches:
            try:
                p.unlink()
                deleted = True
            except Exception:
                pass
        return deleted

    @staticmethod
    def delete_folder(folder_name: str) -> bool:
        clean_folder = folder_name.strip()
        target_dir = STRATEGY_DIR / clean_folder
        if target_dir.exists() and target_dir.is_dir():
            import shutil
            shutil.rmtree(target_dir)
            return True
        return False

    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        results = []
        for p in STRATEGY_DIR.glob("**/*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                rel = p.relative_to(STRATEGY_DIR)
                data["folder"] = rel.parts[0] if len(rel.parts) > 1 else data.get("folder", "General")
                results.append(data)
            except Exception:
                continue
        return results

    @staticmethod
    def list_folders() -> List[Dict[str, Any]]:
        folders_dict: Dict[str, Dict[str, Any]] = {}
        for p in STRATEGY_DIR.glob("**/*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                rel = p.relative_to(STRATEGY_DIR)
                fname = rel.parts[0] if len(rel.parts) > 1 else data.get("folder", "General")
                
                if fname not in folders_dict:
                    folders_dict[fname] = {
                        "name": fname,
                        "count": 0,
                        "symbols": set(),
                        "timeframes": set(),
                        "indicators": set(),
                        "total_net_profit": 0.0,
                        "avg_win_rate": 0.0,
                        "avg_sharpe": 0.0,
                        "created_at": data.get("saved_at", time.strftime("%Y-%m-%d %H:%M")),
                        "strategies": []
                    }
                
                f = folders_dict[fname]
                f["count"] += 1
                f["strategies"].append(data)
                
                s = data.get("strategy", data)
                m = data.get("metrics", {})
                
                if s.get("symbol"):
                    f["symbols"].add(s["symbol"])
                if s.get("timeframe"):
                    f["timeframes"].add(s["timeframe"])
                for ind in data.get("indicators_used", s.get("indicators_used", [])):
                    f["indicators"].add(ind)
                for cond in s.get("buy_conditions", []) + s.get("sell_conditions", []):
                    if isinstance(cond, dict) and cond.get("indicator"):
                        f["indicators"].add(cond["indicator"])
                    
                f["total_net_profit"] += m.get("total_return_usd", 0.0)
                f["avg_win_rate"] += m.get("win_rate_pct", 0.0)
                f["avg_sharpe"] += m.get("sharpe_ratio", 0.0)
            except Exception:
                continue

        results = []
        for fname, f in folders_dict.items():
            cnt = max(1, f["count"])
            results.append({
                "folder": fname,
                "name": fname,
                "count": f["count"],
                "symbols": sorted(list(f["symbols"])),
                "timeframes": sorted(list(f["timeframes"])),
                "indicators": sorted(list(f["indicators"])),
                "total_profit": round(f["total_net_profit"], 2),
                "total_net_profit": round(f["total_net_profit"], 2),
                "avg_win_rate": round(f["avg_win_rate"] / cnt, 1),
                "avg_sharpe": round(f["avg_sharpe"] / cnt, 2),
                "created_at": f["created_at"],
                "strategies": f["strategies"]
            })
        return sorted(results, key=lambda x: x["created_at"], reverse=True)


class Portfolio:
    """Represents a multi-strategy algorithmic portfolio with risk budget and weights."""
    def __init__(self, name: str, strategies: List[Dict[str, Any]],
                 weights: Optional[List[float]] = None,
                 risk_budget: float = 1.0,
                 portfolio_id: Optional[str] = None,
                 created_at: Optional[str] = None,
                 folder: str = "General"):
        self.name = name
        self.strategies = strategies
        n = max(1, len(strategies))
        self.weights = weights if (weights and len(weights) == n) else [round(1.0 / n, 4)] * n
        self.risk_budget = risk_budget
        self.created_at = created_at or time.strftime("%Y-%m-%d %H:%M:%S")
        self.folder = "".join(c for c in str(folder) if c.isalnum() or c in (" ", "_", "-", ".", "(", ")")).strip() or "General"
        
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
        diversification_score = round((asset_div * 0.45 + tf_div * 0.25 + strat_div * 0.30) * 100, 1)

        # StrategyQuant correlation scale (0.00 to 1.00)
        sq_correlation_index = round(max(0.05, min(0.95, 1.0 - (diversification_score / 100.0))), 2)
        if sq_correlation_index <= 0.25:
            sq_rating = "Excelente"
        elif sq_correlation_index <= 0.45:
            sq_rating = "Muy Buena"
        elif sq_correlation_index <= 0.65:
            sq_rating = "Moderada"
        else:
            sq_rating = "Alta / Débil"

        # Calculate standalone worst-case DD in USD (weighted sum without decorrelation benefit)
        standalone_dd_usd = 0.0
        for i, s in enumerate(self.strategies):
            m_ind = s.get("metrics", {})
            w_ind = self.weights[i] if i < len(self.weights) else (1.0 / max(1, len(self.strategies)))
            dd_u = m_ind.get("max_drawdown_usd")
            if dd_u is None or float(dd_u) <= 0:
                dd_pct = float(m_ind.get("max_drawdown_pct", 3.0))
                dd_u = 10000.0 * (dd_pct / 100.0)
            standalone_dd_usd += float(dd_u) * w_ind

        avg_ind_dd = round((standalone_dd_usd / 10000.0) * 100.0, 2)
        est_dd_red = min(55.0, round(15.0 * len(symbols_covered) + 6.0 * strat_div, 1))
        comb_dd_pct = round(max(0.5, avg_ind_dd * (1.0 - (est_dd_red / 100.0))), 2)
        comb_dd_usd = round(10000.0 * (comb_dd_pct / 100.0), 2)
        ret_to_dd = round(total_net_profit / max(1.0, comb_dd_usd), 2)

        return {
            "combined_net_profit_usd": round(total_net_profit, 2),
            "weighted_win_rate_pct": round(weighted_win_rate, 1),
            "total_trades": total_trades,
            "strategies_count": len(self.strategies),
            "symbols": list(symbols_covered),
            "timeframes": list(timeframes_covered),
            "diversification_score": diversification_score,
            "estimated_dd_reduction_pct": est_dd_red,
            "avg_individual_dd_pct": avg_ind_dd,
            "combined_max_drawdown_pct": comb_dd_pct,
            "combined_max_drawdown_usd": comb_dd_usd,
            "ret_to_dd_ratio": ret_to_dd,
            "sq_correlation_index": sq_correlation_index,
            "sq_rating": sq_rating
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "folder": self.folder,
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

    def get_detailed_equity_data(self, initial_capital: float = 10000.0) -> Dict[str, Any]:
        """Synthesize both combined curve and individual strategy curves for visual comparison."""
        curves = []
        strat_meta = []
        for i, s in enumerate(self.strategies):
            w = self.weights[i] if i < len(self.weights) else (1.0 / max(1, len(self.strategies)))
            st_data = s.get("strategy", s)
            name = st_data.get("name", st_data.get("id", f"Estrategia {i+1}"))
            sym = st_data.get("symbol", "N/A")
            tf = st_data.get("timeframe", "1h")
            eq = s.get("equity_curve")
            if not eq:
                try:
                    from backend.strategy import Strategy
                    from backend.data_manager import data_manager
                    from backend.backtester import backtester
                    st_obj = Strategy.from_dict(st_data)
                    df = data_manager.load_data(st_obj.symbol, st_obj.timeframe)
                    res = backtester.run_backtest(st_obj, df, initial_capital=initial_capital)
                    eq = res.equity_curve
                except Exception:
                    eq = []
            curves.append((w, eq or []))
            strat_meta.append({"name": name, "symbol": sym, "timeframe": tf, "weight": w})

        valid_curves = [c for c in curves if c[1]]
        if not valid_curves:
            pnl = self.metrics.get("combined_net_profit_usd", 0.0)
            combined = [
                {"timestamp": "Inicio", "equity": initial_capital, "drawdown_pct": 0.0},
                {"timestamp": "Actual", "equity": round(initial_capital + pnl, 2), "drawdown_pct": 0.5}
            ]
            ind_curves = [{"name": sm["name"], "symbol": sm["symbol"], "timeframe": sm["timeframe"], "weight": sm["weight"], "data": [initial_capital, round(initial_capital + pnl * sm["weight"], 2)]} for sm in strat_meta]
            return {"combined_curve": combined, "individual_curves": ind_curves}

        base_curve = max(valid_curves, key=lambda x: len(x[1]))[1]
        n_points = min(len(base_curve), 80)
        step = max(1, len(base_curve) // n_points)
        sampled_base = base_curve[::step]

        combined = []
        ind_curves = [{"name": sm["name"], "symbol": sm["symbol"], "timeframe": sm["timeframe"], "weight": sm["weight"], "data": []} for sm in strat_meta]
        peak = initial_capital

        for idx_pt, pt in enumerate(sampled_base):
            total_eq = 0.0
            ratio = idx_pt / max(1, len(sampled_base) - 1)

            for i, (w, c) in enumerate(curves):
                if c:
                    c_idx = min(len(c) - 1, int(ratio * (len(c) - 1)))
                    strat_eq = c[c_idx].get("equity", initial_capital)
                    diff = strat_eq - initial_capital
                else:
                    diff = 0.0

                total_eq += diff * w
                ind_curves[i]["data"].append(round(initial_capital + diff, 2))

            curr_equity = round(initial_capital + total_eq, 2)
            if curr_equity > peak:
                peak = curr_equity
            dd_pct = round(((peak - curr_equity) / peak) * 100.0, 2) if peak > 0 else 0.0

            combined.append({
                "timestamp": pt.get("timestamp", str(idx_pt)),
                "equity": curr_equity,
                "drawdown_pct": dd_pct
            })

        return {"combined_curve": combined, "individual_curves": ind_curves}

    def get_combined_equity_curve(self, initial_capital: float = 10000.0) -> List[Dict[str, Any]]:
        return self.get_detailed_equity_data(initial_capital)["combined_curve"]

    def save(self, folder: Optional[str] = None) -> Path:
        """Persist portfolio metadata and snapshot of combined strategies inside folder."""
        f_name = folder or self.folder or "General"
        clean_folder = "".join(c for c in str(f_name) if c.isalnum() or c in (" ", "_", "-", ".", "(", ")")).strip() or "General"
        target_dir = PORTFOLIO_DIR / clean_folder
        target_dir.mkdir(parents=True, exist_ok=True)
        
        self.folder = clean_folder
        path = target_dir / f"{self.id}.json"
        
        d = self.to_dict()
        d["folder"] = clean_folder
        payload = {
            "meta": d,
            "strategies": self.strategies,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def load(portfolio_id: str) -> "Portfolio":
        matches = list(PORTFOLIO_DIR.glob(f"**/{portfolio_id}.json"))
        if not matches:
            raise FileNotFoundError(f"Portfolio {portfolio_id} not found")
        data = json.loads(matches[0].read_text(encoding="utf-8"))
        meta = data["meta"]
        rel = matches[0].relative_to(PORTFOLIO_DIR)
        folder = rel.parts[0] if len(rel.parts) > 1 else meta.get("folder", "General")
        return Portfolio(
            name=meta["name"],
            strategies=data.get("strategies", []),
            weights=meta.get("weights"),
            risk_budget=meta.get("risk_budget", 1.0),
            portfolio_id=meta.get("id"),
            created_at=meta.get("created_at"),
            folder=folder
        )

    @staticmethod
    def delete(portfolio_id: str) -> bool:
        matches = list(PORTFOLIO_DIR.glob(f"**/{portfolio_id}.json"))
        deleted = False
        for p in matches:
            try:
                p.unlink()
                deleted = True
            except Exception:
                pass
        return deleted

    @staticmethod
    def delete_folder(folder_name: str) -> bool:
        clean_folder = folder_name.strip()
        target_dir = PORTFOLIO_DIR / clean_folder
        if target_dir.exists() and target_dir.is_dir():
            import shutil
            shutil.rmtree(target_dir)
            return True
        return False

    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        results = []
        for p in PORTFOLIO_DIR.glob("**/*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                meta = data.get("meta", data)
                rel = p.relative_to(PORTFOLIO_DIR)
                meta["folder"] = rel.parts[0] if len(rel.parts) > 1 else meta.get("folder", "General")
                results.append(meta)
            except Exception:
                continue
        return results

    @staticmethod
    def list_folders() -> List[Dict[str, Any]]:
        folders_dict: Dict[str, Dict[str, Any]] = {}
        for p in PORTFOLIO_DIR.glob("**/*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                meta = data.get("meta", data)
                rel = p.relative_to(PORTFOLIO_DIR)
                fname = rel.parts[0] if len(rel.parts) > 1 else meta.get("folder", "General")
                
                if fname not in folders_dict:
                    folders_dict[fname] = {
                        "name": fname,
                        "count": 0,
                        "created_at": meta.get("created_at", time.strftime("%Y-%m-%d")),
                        "portfolios": []
                    }
                f = folders_dict[fname]
                f["count"] += 1
                f["portfolios"].append(meta)
            except Exception:
                continue

        results = []
        for fname, f in folders_dict.items():
            syms = set()
            tot_strat = 0
            tot_pnl = 0.0
            for p in f["portfolios"]:
                m = p.get("metrics", {})
                for s in m.get("symbols", []):
                    syms.add(s)
                tot_strat += m.get("strategies_count", len(p.get("strategies_summary", [])))
                tot_pnl += m.get("combined_net_profit_usd", 0.0)

            results.append({
                "folder": fname,
                "name": fname,
                "count": f["count"],
                "symbols": sorted(list(syms)),
                "total_strategies": tot_strat,
                "total_profit": round(tot_pnl, 2),
                "created_at": f["created_at"],
                "portfolios": f["portfolios"]
            })
        return sorted(results, key=lambda x: x["created_at"], reverse=True)


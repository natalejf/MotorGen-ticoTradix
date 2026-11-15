"""
FastAPI Server for TradingNote Genetic Engine Replica
Provides REST API endpoints and background task management.
"""

import os
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, JSONResponse
from pathlib import Path
from pydantic import BaseModel

from backend.data_manager import data_manager, SUPPORTED_SYMBOLS
from backend.strategy import Strategy
from backend.backtester import backtester
from backend.genetic_engine import genetic_engine, ALL_28_INDICATORS, ALL_ENTRY_TYPES, ALL_EXIT_MODES, SESSION_FILTERS, SIZING_MODES
from backend.validation import validation_suite
from backend.code_generator import code_generator

app = FastAPI(
    title="TradingNote Genetic Engine API",
    description="Replica del motor genético y creador de algoritmos de TradingNote",
    version="1.0.0"
)

# Enable CORS for local dev and frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class ExplorationConfigRequest(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "1h"
    search_mode: str = "genetic"
    initial_deposit: float = 10000.0
    objective: str = "tn_score"
    infinite_mode: bool = True
    generations: int = 0
    population_size: int = 30
    enabled_indicators: List[str] = list(ALL_28_INDICATORS.keys())
    enabled_entry_types: List[str] = ALL_ENTRY_TYPES
    enabled_exit_modes: List[str] = ALL_EXIT_MODES
    min_win_rate: float = 35.0
    min_trades: int = 8
    max_drawdown: float = 20.0
    min_net_profit_usd: float = 0.0
    min_sharpe: float = 0.8
    min_profit_factor: float = 1.1
    min_dsr: float = 0.2
    max_candidates: int = 1000

    # Risk management & Position sizing
    sizing_mode: str = "FIXED_RISK"  # "FIXED_RISK", "FIXED_LOT", "FIXED_CASH", "MARTINGALE", "ANTI_MARTINGALE"
    risk_per_trade_pct: float = 1.0
    fixed_lot: float = 0.01
    fixed_cash_risk: float = 100.0
    martingale_mult: float = 1.5

    # Multi-indicator synergy
    min_indicators_per_strategy: int = 1
    max_indicators_per_strategy: int = 3

    # Prop Firm Challenge Filter
    prop_firm_filter: bool = False
    prop_firm_daily_loss_pct: float = 4.0
    prop_firm_total_dd_pct: float = 8.0
    prop_firm_target_pct: float = 8.0

class UpdateDataRequest(BaseModel):
    symbol: Optional[str] = None

# =============================================================================
# DATA ENDPOINTS
# =============================================================================

@app.get("/api/symbols")
def get_symbols():
    """Returns available symbols and cached bar counts."""
    return data_manager.get_symbols_summary()

@app.post("/api/update-data")
def update_data(req: UpdateDataRequest):
    """Triggers update of historical data."""
    if req.symbol:
        res = data_manager.auto_update_symbol(req.symbol)
        return {"status": "success", "symbol": req.symbol, "result": res}
    else:
        res = data_manager.update_all_symbols()
        return {"status": "success", "results": res}

# =============================================================================
# GENETIC ENGINE ENDPOINTS
# =============================================================================

# ---------------------------------------------------------------------
# PORTFOLIO ENDPOINTS
# ---------------------------------------------------------------------
from backend.portfolio import StrategyRecord, Portfolio
from backend.portfolio_engine import portfolio_engine
from pydantic import conint, confloat
from typing import List

class PortfolioEngineConfigRequest(BaseModel):
    source_pairs: Optional[List[str]] = None
    source_folders: Optional[List[str]] = None
    min_strategies: int = 2
    max_strategies: int = 5
    weight_mode: str = "EQUAL"  # "EQUAL", "SHARPE", "PROFIT"
    objective: str = "diversification_score"  # "diversification_score", "combined_sharpe", "combined_net_profit_usd", "tn_score"
    min_diversification: float = 25.0
    min_sharpe: float = 0.8
    max_portfolios: int = 50
    folder: str = "Portafolios_Principales"

class SavePortfolioCandidateRequest(BaseModel):
    candidate_id: str
    folder: Optional[str] = "Portafolios_Principales"

class SaveAllTopPortfoliosRequest(BaseModel):
    folder: Optional[str] = "Lote_Portafolios_Top"

class SaveStrategyRequest(BaseModel):
    strategy_id: Optional[str] = None
    candidate_data: Optional[Dict[str, Any]] = None
    batch_name: Optional[str] = None
    folder: Optional[str] = None

class BatchSaveStrategiesRequest(BaseModel):
    strategy_ids: Optional[List[str]] = None
    save_all_candidates: bool = False
    batch_name: Optional[str] = None
    folder: Optional[str] = None

class CreatePortfolioRequest(BaseModel):
    name: str
    strategy_ids: List[str]
    weights: Optional[List[float]] = None
    max_strategies: int = 10
    risk_budget: float = 1.0
    folder: Optional[str] = None

@app.post("/api/strategy/save")
def save_strategy(req: SaveStrategyRequest):
    """Saves a strategy with its metrics to disk inside a labeled folder/batch."""
    import time
    cand = None
    if req.candidate_data:
        cand = req.candidate_data
    elif req.strategy_id:
        cand = next((c for c in genetic_engine.get_candidates() if c["strategy"]["id"] == req.strategy_id), None)
    
    if not cand:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada.")
    
    sym = cand.get("strategy", {}).get("symbol", "N/A")
    tf = cand.get("strategy", {}).get("timeframe", "1h")
    folder_name = req.folder or req.batch_name or f"Lote {sym} {tf}"
    cand["batch_name"] = folder_name
    cand["folder"] = folder_name
    cand["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    rec = StrategyRecord(cand)
    rec.save(folder=folder_name)
    return {"status": "saved", "strategy_id": rec.id, "folder": folder_name}

@app.post("/api/strategy/batch-save")
def batch_save_strategies(req: BatchSaveStrategiesRequest):
    """Saves multiple strategies at once inside a designated folder/batch."""
    import time
    saved_ids = []
    candidates = genetic_engine.get_candidates()
    
    if req.save_all_candidates:
        targets = candidates
    elif req.strategy_ids:
        targets = [c for c in candidates if c["strategy"]["id"] in req.strategy_ids]
    else:
        targets = candidates

    if not targets:
        return {"status": "saved_batch", "count": 0, "saved_ids": [], "folder": "General"}

    first_cand = targets[0]
    sym = first_cand.get("strategy", {}).get("symbol", "N/A")
    tf = first_cand.get("strategy", {}).get("timeframe", "1h")
    folder_name = req.folder or req.batch_name or f"Lote {sym} {tf} ({time.strftime('%d-%m %H-%M')})"

    for cand in targets:
        cand["batch_name"] = folder_name
        cand["folder"] = folder_name
        cand["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        rec = StrategyRecord(cand)
        rec.save(folder=folder_name)
        saved_ids.append(rec.id)

    return {"status": "saved_batch", "count": len(saved_ids), "saved_ids": saved_ids, "folder": folder_name}

@app.delete("/api/strategy/{strategy_id}")
def delete_strategy(strategy_id: str):
    """Deletes a saved strategy file."""
    deleted = StrategyRecord.delete(strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada.")
    return {"status": "deleted", "strategy_id": strategy_id}

@app.get("/api/strategy-folders")
def list_strategy_folders():
    """Lists organized strategy folders with aggregate metrics."""
    return StrategyRecord.list_folders()

@app.delete("/api/strategy-folder/{folder_name}")
def delete_strategy_folder(folder_name: str):
    """Deletes an entire strategy folder and all strategies within it."""
    deleted = StrategyRecord.delete_folder(folder_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada.")
    return {"status": "deleted_folder", "folder": folder_name}

@app.post("/api/portfolio/create")
def create_portfolio(req: CreatePortfolioRequest):
    """Stops engine if running and combines selected strategies into a portfolio inside folder."""
    if genetic_engine.is_running:
        genetic_engine.stop_exploration()

    candidates_pool = {c["strategy"]["id"]: c for c in genetic_engine.get_candidates()}
    selected = []
    
    ids_to_process = req.strategy_ids[: req.max_strategies]
    for sid in ids_to_process:
        try:
            rec = StrategyRecord.load(sid)
            selected.append(rec.data)
        except FileNotFoundError:
            if sid in candidates_pool:
                cand = candidates_pool[sid]
                rec = StrategyRecord(cand)
                rec.save(folder="General")
                selected.append(cand)
            else:
                continue

    if not selected:
        raise HTTPException(status_code=400, detail="No se encontraron estrategias válidas para combinar.")

    weights = None
    if req.weights and len(req.weights) == len(selected):
        total = sum(req.weights)
        if total > 0:
            weights = [round(w / total, 4) for w in req.weights]

    folder_name = req.folder or "Portafolios Multi-Activo"
    port = Portfolio(name=req.name or f"Portafolio {len(selected)} Estrategias", 
                     strategies=selected, 
                     weights=weights, 
                     risk_budget=req.risk_budget,
                     folder=folder_name)
    port.save(folder=folder_name)
    return {"status": "created", "portfolio": port.to_dict()}

@app.get("/api/strategies/saved")
def list_saved_strategies():
    return StrategyRecord.list_all()

@app.get("/api/portfolios")
def list_portfolios():
    return Portfolio.list_all()

@app.get("/api/portfolio-folders")
def list_portfolio_folders():
    return Portfolio.list_folders()

@app.delete("/api/portfolio-folder/{folder_name}")
def delete_portfolio_folder(folder_name: str):
    deleted = Portfolio.delete_folder(folder_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Carpeta de portafolios no encontrada.")
    return {"status": "deleted_portfolio_folder", "folder": folder_name}



@app.get("/api/portfolio/{portfolio_id}")
def get_portfolio_detail(portfolio_id: str):
    """Returns full analytics, constituent strategies and combined equity curve for a portfolio."""
    try:
        port = Portfolio.load(portfolio_id)
        detailed_eq = port.get_detailed_equity_data()
        data = port.to_dict()
        data["combined_equity_curve"] = detailed_eq["combined_curve"]
        data["individual_curves"] = detailed_eq["individual_curves"]
        data["strategies"] = port.strategies
        return data
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Portafolio no encontrado: {str(e)}")

@app.delete("/api/portfolio/{portfolio_id}")
def delete_portfolio(portfolio_id: str):
    deleted = Portfolio.delete(portfolio_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Portafolio no encontrado.")
    return {"status": "deleted", "portfolio_id": portfolio_id}

# =============================================================================
# PORTFOLIO ENGINE (MULTI-PAIR EXPLORATION & OPTIMIZATION)
# =============================================================================

@app.post("/api/portfolio-engine/start")
def start_portfolio_engine(req: PortfolioEngineConfigRequest):
    portfolio_engine.start_exploration(req.dict())
    return {"status": "started", "config": req.dict()}

@app.post("/api/portfolio-engine/stop")
def stop_portfolio_engine():
    portfolio_engine.stop_exploration()
    return {"status": "stopping"}

@app.get("/api/portfolio-engine/status")
def get_portfolio_engine_status():
    return portfolio_engine.get_status()

@app.get("/api/portfolio-engine/top")
def get_portfolio_engine_top():
    return portfolio_engine.get_top_portfolios()

@app.post("/api/portfolio-engine/save-candidate")
def save_portfolio_engine_candidate(req: SavePortfolioCandidateRequest):
    try:
        saved = portfolio_engine.save_portfolio_candidate(req.candidate_id, folder=req.folder or "Portafolios_Principales")
        return {"status": "saved", "portfolio": saved}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/portfolio-engine/save-all")
def save_all_top_portfolios(req: SaveAllTopPortfoliosRequest):
    try:
        saved_list = portfolio_engine.save_all_top(folder=req.folder or "Lote_Portafolios_Top")
        return {"status": "saved_batch", "count": len(saved_list), "folder": req.folder}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/start-exploration")
def start_exploration(req: ExplorationConfigRequest):
    if genetic_engine.is_running:
        genetic_engine.stop_exploration()
        import time
        time.sleep(0.5)
    
    genetic_engine.start_exploration(req.dict())
    return {"status": "started", "config": req.dict()}

@app.post("/api/stop-exploration")
def stop_exploration():
    genetic_engine.stop_exploration()
    return {"status": "stopping"}

@app.get("/api/status")
def get_engine_status():
    return genetic_engine.get_status()

@app.get("/api/candidates")
def get_candidates(
    symbol: Optional[str] = None,
    wf_only: bool = False,
    multiverse_only: bool = False
):
    candidates = genetic_engine.get_candidates()
    
    # Filter by symbol
    if symbol and symbol != "ALL":
        candidates = [c for c in candidates if c["strategy"]["symbol"] == symbol]

    # Filter by WF or Multiverse if requested
    if wf_only:
        candidates = [c for c in candidates if c.get("validation", {}).get("walk_forward", {}).get("passed", False)]
    if multiverse_only:
        candidates = [c for c in candidates if c.get("validation", {}).get("multiverse", {}).get("passed", False)]

    return candidates

@app.get("/api/candidate/{candidate_id}")
def get_candidate_detail(candidate_id: str):
    # 1. Search in live engine memory
    candidates = genetic_engine.get_candidates()
    for c in candidates:
        if c["strategy"]["id"] == candidate_id:
            return c

    # 2. Search in saved strategies on disk
    try:
        rec = StrategyRecord.load(candidate_id)
        st_data = rec.data.get("strategy", rec.data)
        strat = Strategy.from_dict(st_data)

        equity_curve = rec.data.get("equity_curve")
        trades = rec.data.get("trades_sample", rec.data.get("trades", []))
        metrics = rec.data.get("metrics", {})

        if not equity_curve or not trades:
            try:
                df = data_manager.load_data(strat.symbol, strat.timeframe)
                init_cap = float(metrics.get("initial_capital", 10000.0))
                res = backtester.run_backtest(strat, df, initial_deposit=init_cap)
                equity_curve = res.equity_curve
                trades = res.trades[:50]
                if not metrics or "sharpe_ratio" not in metrics:
                    metrics = res.metrics
            except Exception as be_err:
                print(f"Error backtesting saved strategy: {be_err}")

        sparkline = rec.data.get("sparkline")
        if not sparkline and equity_curve:
            sparkline = [e["equity"] for e in equity_curve[::max(1, len(equity_curve)//25)]]

        return {
            "strategy": strat.to_dict(),
            "metrics": metrics,
            "equity_curve": equity_curve or [],
            "sparkline": sparkline or [],
            "trades_sample": trades or [],
            "rules_desc": strat.to_human_description(),
            "indicators_used": strat.get_used_indicators(),
            "validation": rec.data.get("validation", {}),
            "batch_name": rec.data.get("batch_name", ""),
            "folder": rec.data.get("folder", "General"),
            "saved_at": rec.data.get("saved_at", "")
        }
    except Exception as e:
        import traceback
        traceback.print_exc()

    raise HTTPException(status_code=404, detail="Estrategia no encontrada.")

@app.post("/api/candidate/{candidate_id}/validate")
def validate_candidate(candidate_id: str):
    """Runs full Walk-Forward and Multiverse Monte Carlo simulations on the candidate."""
    candidates = genetic_engine.get_candidates()
    target_c = next((c for c in candidates if c["strategy"]["id"] == candidate_id), None)
    is_from_disk = False
    rec = None

    if not target_c:
        try:
            rec = StrategyRecord.load(candidate_id)
            target_c = rec.data
            is_from_disk = True
        except Exception:
            pass

    if not target_c:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada.")

    strat = Strategy.from_dict(target_c.get("strategy", target_c))
    df = data_manager.load_data(strat.symbol, strat.timeframe)

    # 1. Run Walk-Forward
    wf_res = validation_suite.run_walk_forward(strat, df, n_windows=4, test_ratio=0.25)

    # 2. Run Multiverse (80 synthetic universes)
    mv_res = validation_suite.run_multiverse(strat, df, n_universes=80)

    # 3. Prop firm challenge evaluation
    pf_res = validation_suite.evaluate_prop_firm(strat, df)

    validation_data = {
        "walk_forward": wf_res,
        "multiverse": mv_res,
        "prop_firm": pf_res
    }

    if is_from_disk and rec:
        rec.data["validation"] = validation_data
        rec.save(folder=rec.data.get("folder", "General"))
    else:
        # Cache validation result on live candidate
        with genetic_engine.lock:
            for c in genetic_engine.candidates_passed:
                if c["strategy"]["id"] == candidate_id:
                    c["validation"] = validation_data
                    break

    return validation_data

@app.get("/api/candidate/{candidate_id}/export/{export_format}")
def export_candidate(candidate_id: str, export_format: str):
    candidates = genetic_engine.get_candidates()
    target_c = next((c for c in candidates if c["strategy"]["id"] == candidate_id), None)
    if not target_c:
        try:
            rec = StrategyRecord.load(candidate_id)
            target_c = rec.data
        except Exception:
            pass

    if not target_c:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada.")

    strat = Strategy.from_dict(target_c.get("strategy", target_c))

    if export_format == "mq5":
        content = code_generator.to_mql5(strat)
        return PlainTextResponse(content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={strat.id}.mq5"})
    elif export_format == "python":
        content = code_generator.to_python(strat)
        return PlainTextResponse(content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename={strat.id}.py"})
    elif export_format == "json":
        content = code_generator.to_json(strat)
        return PlainTextResponse(content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename={strat.id}.json"})
    else:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa mq5, python o json.")



@app.get("/api/neural-tree")
def get_neural_tree():
    """Returns 3D Neural Explorer genealogy nodes and connections."""
    return genetic_engine.get_neural_tree()

@app.get("/api/config-defaults")
def get_config_defaults():
    """Returns metadata, all 28 indicators, entry and exit modes and default parameters."""
    return {
        "symbols": list(SUPPORTED_SYMBOLS.keys()),
        "timeframes": ["1h", "4h", "1d"],
        "all_indicators": ALL_28_INDICATORS,
        "entry_types": ALL_ENTRY_TYPES,
        "exit_modes": ALL_EXIT_MODES,
        "session_filters": SESSION_FILTERS,
        "sizing_modes": SIZING_MODES,
        "optimization_objectives": [
            {"id": "tn_score", "name": "Score balanceado (default TN Score)"},
            {"id": "sharpe", "name": "Mayor Sharpe Ratio"},
            {"id": "sortino", "name": "Mayor Sortino"},
            {"id": "calmar", "name": "Mayor Calmar"},
            {"id": "pnl", "name": "Mayor PnL absoluto"},
            {"id": "drawdown", "name": "Menor Drawdown"},
            {"id": "profit_factor", "name": "Mayor Profit Factor"},
            {"id": "expectancy", "name": "Mayor Expectancy"},
            {"id": "win_rate", "name": "Mayor Win Rate"},
            {"id": "recovery_factor", "name": "Mayor Recovery Factor"}
        ]
    }

# Mount static frontend files if folder exists
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api:app", host="0.0.0.0", port=8000, reload=True)

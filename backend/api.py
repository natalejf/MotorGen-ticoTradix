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
from pydantic import conint, confloat
from typing import List

class SaveStrategyRequest(BaseModel):
    strategy_id: Optional[str] = None
    candidate_data: Optional[Dict[str, Any]] = None
    batch_name: Optional[str] = None

class BatchSaveStrategiesRequest(BaseModel):
    strategy_ids: Optional[List[str]] = None
    save_all_candidates: bool = False
    batch_name: Optional[str] = None

class CreatePortfolioRequest(BaseModel):
    name: str
    strategy_ids: List[str]
    weights: Optional[List[float]] = None
    max_strategies: int = 10
    risk_budget: float = 1.0

@app.post("/api/strategy/save")
def save_strategy(req: SaveStrategyRequest):
    """Saves a strategy with its metrics to disk."""
    import time
    cand = None
    if req.candidate_data:
        cand = req.candidate_data
    elif req.strategy_id:
        cand = next((c for c in genetic_engine.get_candidates() if c["strategy"]["id"] == req.strategy_id), None)
    
    if not cand:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada.")
    
    # Enrich with batch/timestamp info if not present
    sym = cand.get("strategy", {}).get("symbol", "N/A")
    tf = cand.get("strategy", {}).get("timeframe", "1h")
    cand["batch_name"] = req.batch_name or cand.get("batch_name") or f"Lote {sym} {tf}"
    cand["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    rec = StrategyRecord(cand)
    rec.save()
    return {"status": "saved", "strategy_id": rec.id}

@app.post("/api/strategy/batch-save")
def batch_save_strategies(req: BatchSaveStrategiesRequest):
    """Saves multiple strategies at once in batch with batch label."""
    import time
    saved_ids = []
    candidates = genetic_engine.get_candidates()
    
    if req.save_all_candidates:
        targets = candidates
    elif req.strategy_ids:
        targets = [c for c in candidates if c["strategy"]["id"] in req.strategy_ids]
    else:
        targets = candidates

    for cand in targets:
        sym = cand.get("strategy", {}).get("symbol", "N/A")
        tf = cand.get("strategy", {}).get("timeframe", "1h")
        batch_label = req.batch_name or f"Lote {sym} {tf} ({time.strftime('%d/%m %H:%M')})"
        cand["batch_name"] = batch_label
        cand["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        rec = StrategyRecord(cand)
        rec.save()
        saved_ids.append(rec.id)

    return {"status": "saved_batch", "count": len(saved_ids), "saved_ids": saved_ids, "batch_name": req.batch_name}

@app.delete("/api/strategy/{strategy_id}")
def delete_strategy(strategy_id: str):
    """Deletes a saved strategy file."""
    deleted = StrategyRecord.delete(strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Estrategia no encontrada.")
    return {"status": "deleted", "strategy_id": strategy_id}

@app.post("/api/portfolio/create")
def create_portfolio(req: CreatePortfolioRequest):
    """Stops engine if running and combines selected strategies into a portfolio."""
    # 1. Stop engine first as requested
    if genetic_engine.is_running:
        genetic_engine.stop_exploration()

    # 2. Load strategies (check both saved and active candidate pool)
    candidates_pool = {c["strategy"]["id"]: c for c in genetic_engine.get_candidates()}
    selected = []
    
    ids_to_process = req.strategy_ids[: req.max_strategies]
    for sid in ids_to_process:
        try:
            rec = StrategyRecord.load(sid)
            selected.append(rec.data)
        except FileNotFoundError:
            # Check if it's currently in active candidates and auto-persist it
            if sid in candidates_pool:
                cand = candidates_pool[sid]
                rec = StrategyRecord(cand)
                rec.save()
                selected.append(cand)
            else:
                continue

    if not selected:
        raise HTTPException(status_code=400, detail="No se encontraron estrategias válidas para combinar.")

    # 3. Normalise weights if provided
    weights = None
    if req.weights and len(req.weights) == len(selected):
        total = sum(req.weights)
        if total > 0:
            weights = [round(w / total, 4) for w in req.weights]

    port = Portfolio(name=req.name or f"Portafolio {len(selected)} Estrategias", 
                     strategies=selected, 
                     weights=weights, 
                     risk_budget=req.risk_budget)
    port.save()
    return {"status": "created", "portfolio": port.to_dict()}

@app.get("/api/strategies/saved")
def list_saved_strategies():
    return StrategyRecord.list_all()

@app.get("/api/portfolios")
def list_portfolios():
    return Portfolio.list_all()

@app.get("/api/portfolio/{portfolio_id}")
def get_portfolio(portfolio_id: str):
    try:
        port = Portfolio.load(portfolio_id)
        return port.to_dict()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Portafolio no encontrado.")

@app.delete("/api/portfolio/{portfolio_id}")
def delete_portfolio(portfolio_id: str):
    path = Path(__file__).resolve().parents[1] / "data" / "portfolios" / f"{portfolio_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Portafolio no encontrado.")
    path.unlink()
    return {"status": "deleted", "portfolio_id": portfolio_id}

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
    candidates = genetic_engine.get_candidates()
    for c in candidates:
        if c["strategy"]["id"] == candidate_id:
            return c
    raise HTTPException(status_code=404, detail="Candidato no encontrado.")

@app.post("/api/candidate/{candidate_id}/validate")
def validate_candidate(candidate_id: str):
    """Runs full Walk-Forward and Multiverse Monte Carlo simulations on the candidate."""
    candidates = genetic_engine.get_candidates()
    target_c = None
    for c in candidates:
        if c["strategy"]["id"] == candidate_id:
            target_c = c
            break

    if not target_c:
        raise HTTPException(status_code=404, detail="Candidato no encontrado.")

    strat = Strategy.from_dict(target_c["strategy"])
    df = data_manager.load_data(strat.symbol, strat.timeframe)

    # 1. Run Walk-Forward
    wf_res = validation_suite.run_walk_forward(strat, df, n_windows=4, test_ratio=0.25)

    # 2. Run Multiverse (100 synthetic universes)
    mv_res = validation_suite.run_multiverse(strat, df, n_universes=80)

    # 3. Prop firm challenge evaluation
    pf_res = validation_suite.evaluate_prop_firm(strat, df)

    validation_data = {
        "walk_forward": wf_res,
        "multiverse": mv_res,
        "prop_firm": pf_res
    }

    # Cache validation result on candidate
    with genetic_engine.lock:
        for c in genetic_engine.candidates_passed:
            if c["strategy"]["id"] == candidate_id:
                c["validation"] = validation_data
                break

    return validation_data

@app.get("/api/candidate/{candidate_id}/export/{export_format}")
def export_candidate(candidate_id: str, export_format: str):
    candidates = genetic_engine.get_candidates()
    target_c = None
    for c in candidates:
        if c["strategy"]["id"] == candidate_id:
            target_c = c
            break

    if not target_c:
        raise HTTPException(status_code=404, detail="Candidato no encontrado.")

    strat = Strategy.from_dict(target_c["strategy"])

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

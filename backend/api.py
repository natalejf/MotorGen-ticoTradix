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

"""
FastAPI Server for TradingNote Genetic Engine Replica
Provides REST API endpoints and background task management.
"""

import os
import json
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse
from pathlib import Path
from pydantic import BaseModel, Field

from backend.data_manager import data_manager, SUPPORTED_SYMBOLS
from backend.historical_data import historical_archive
from backend.strategy import Strategy
from backend.backtester import backtester
from backend.genetic_engine import genetic_engine, ALL_28_INDICATORS, ALL_ENTRY_TYPES, ALL_EXIT_MODES, SESSION_FILTERS, SIZING_MODES
from backend.validation import validation_suite
from backend.code_generator import code_generator

app = FastAPI(
    title="Stratix API",
    description="Motor de algoritmos, portafolios y copy trading MT5 demo",
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
    # Multi-symbol / multi-timeframe (fallback to symbol/timeframe if omitted)
    symbols: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    # Exploration date range (inclusive; None = full history)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    # K: % final de datos reservado como "examen sorpresa" (holdout), 0 = off
    holdout_pct: float = 0.0
    # F: modo multi-timeframe — "separate" (un algo por TF) | "combined" (TF bajo + confirmación TF alto)
    mtf_mode: str = "separate"
    # G: Averaging config (TN averagingConfig)
    averaging_config: Optional[Dict[str, Any]] = None
    search_mode: str = "genetic"  # "genetic" | "random"
    initial_deposit: float = 10000.0
    objective: str = "tn_score"
    infinite_mode: bool = True
    generations: int = 0
    population_size: int = 30
    num_combinations: int = 10000  # budget for random mode
    enabled_indicators: List[str] = list(ALL_28_INDICATORS.keys())
    enabled_operators: Optional[List[str]] = None
    enabled_entry_types: List[str] = ALL_ENTRY_TYPES
    enabled_exit_modes: List[str] = ALL_EXIT_MODES
    # User-edited per-parameter sweep ranges {IND: {param: {from, step, to}}}
    indicator_ranges: Optional[Dict[str, Any]] = None
    # User-edited exit/risk sweep ranges {param: {from, step, to}}
    exit_ranges: Optional[Dict[str, Any]] = None
    min_win_rate: float = 40.0
    min_trades: int = 30
    max_drawdown: float = 20.0
    min_net_profit_usd: float = 0.0
    min_sharpe: float = 0.8
    min_profit_factor: float = 1.2
    min_dsr: float = 0.3
    max_candidates: Optional[int] = None

    # Backtest modeling & costs
    modeling_mode: str = "ohlc"  # "ohlc" | "open_prices" | "ohlc_m1" | "tick"
    spread_pips: Optional[float] = None
    slippage_pips: Optional[float] = None
    commission_per_lot: Optional[float] = None
    swap_long: Optional[float] = None
    swap_short: Optional[float] = None
    parallel_workers: int = 0  # 0 = serial

    # Risk management & Position sizing
    sizing_mode: str = "FIXED_RISK"  # "FIXED_RISK", "FIXED_LOT", "FIXED_CASH", "MARTINGALE", "ANTI_MARTINGALE"
    risk_per_trade_pct: float = 1.0
    fixed_lot: float = 0.01
    fixed_cash_risk: float = 100.0
    martingale_mult: float = 1.5
    risk_multiplier: float = 1.0
    fixed_rr: float = 0.0
    reward_risk_ratio: float = 0.0

    # Full risk rules (0 / defaults = free to vary in generation)
    max_daily_loss_pct: float = 0.0
    max_weekly_loss_pct: float = 0.0
    max_monthly_loss_pct: float = 0.0
    max_account_loss_pct: float = 0.0
    max_daily_gain_pct: float = 0.0
    max_weekly_gain_pct: float = 0.0
    max_monthly_gain_pct: float = 0.0
    max_account_gain_pct: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    max_daily_trades: int = 4
    max_open_trades: int = 1

    # Time rules
    no_new_trades_friday: bool = False
    no_monday_open: bool = False
    avoid_rollover: bool = False
    close_before_ny_close: bool = False
    close_before_weekend: bool = True

    # Multi-indicator synergy
    min_indicators_per_strategy: int = 1
    max_indicators_per_strategy: int = 2

    # Prop Firm Challenge Filter
    prop_firm_filter: bool = False
    prop_firm_daily_loss_pct: float = Field(default=4.0,gt=0,le=100)
    prop_firm_total_dd_pct: float = Field(default=8.0,gt=0,le=100)
    prop_firm_target_pct: float = Field(default=8.0,gt=0,le=100)

    # Challenge simulation during exploration (runs when prop_firm_filter on or objective=pass_rate)
    challenge_capital: float = 10000.0
    challenge_min_trading_days: int = 5
    challenge_simulations: int = 10
    challenge_min_pass_rate: float = 0.0  # 0 = never rejects on pass rate

    # Direction filter (BOTH, LONG_ONLY, SHORT_ONLY)
    direction: str = "BOTH"

    # Additional validators during exploration (TN: "ejecutar validadores adicionales")
    validate_during_exploration: bool = True
    wf_top_n: int = 10            # 1..50: WF sobre los N mejores aceptados
    mv_top_n: int = 5             # 1..10: Multiverso sobre los N mejores aceptados
    wf_mode: str = "validation"   # "validation" | "reoptimization"
    wf_reopt_depth: str = "standard"
    wf_windows: int = 4
    wf_test_ratio: float = 0.25
    wf_min_wfe: float = 0.5
    wf_min_pass_rate: float = 60.0
    wf_min_oos_sharpe: float = 0.5
    mv_universes: int = 25        # ligero para exploración (80 en retest manual)
    mv_preset: str = "balanced"
    mv_regimes: int = 3

class UpdateDataRequest(BaseModel):
    symbol: Optional[str] = None

# =============================================================================
# DATA ENDPOINTS
# =============================================================================

@app.get("/api/symbols")
def get_symbols():
    """Returns available symbols and cached bar counts."""
    return data_manager.get_symbols_summary()

@app.get('/api/history/status')
def history_status():
    status = historical_archive.status()
    # A CLI import can run independently of the web process and survives restarts.
    progress = historical_archive.root / 'progress.json'
    if status['status'] == 'idle' and progress.exists():
        status = json.loads(progress.read_text(encoding='utf-8'))
        import time
        if status.get('status') == 'running' and time.time() - progress.stat().st_mtime > 1800:
            status['status'] = 'interrupted'
    return status

@app.post('/api/history/update')
def history_update(req: UpdateDataRequest):
    status = history_status()
    if status['status'] == 'running':
        return {'started': False, 'status': status}
    try:
        started = historical_archive.start([req.symbol] if req.symbol else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'started': started, 'status': historical_archive.status()}

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
from backend.portfolio import StrategyRecord, Portfolio, STRATEGY_DIR, PORTFOLIO_DIR
from backend.portfolio_engine import portfolio_engine
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

class BatchRetestRequest(BaseModel):
    folder: Optional[str] = "ALL"
    strategy_ids: Optional[List[str]] = None

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

# ============================================================================
# RETEST & ROBUSTNESS PIPELINE (RUTA TRADINGNOTE)
# ============================================================================
RETEST_CACHE_FILE = Path("data/retest_results.json")

@app.post("/api/retest/batch")
def run_batch_retest(req: BatchRetestRequest):
    """
    Runs the canonical 4-layer TradingNote robustness retest on saved strategies:
    - Walk-Forward Out-Of-Sample (WFE, pass rate)
    - Monte Carlo (1000 shuffle & skip simulations, P95 drawdown)
    - Multiverso (synthetic market bootstrap)
    """
    raw_strats = StrategyRecord.list_all()
    if req.strategy_ids:
        targets = [s for s in raw_strats if s.get("strategy", s).get("id") in req.strategy_ids]
    elif req.folder and req.folder != "ALL":
        targets = [s for s in raw_strats if s.get("folder") == req.folder]
    else:
        targets = raw_strats



    results = []
    for s_data in targets:
        try:
            r = validation_suite.run_full_retest(s_data)
            results.append(r)
            # Save into strategy file as well
            try:
                strat_id = r["strategy_id"]
                rec = StrategyRecord.load(strat_id)
                rec.data["retest"] = r
                rec.save(folder=rec.data.get("folder", "General"))
            except Exception:
                pass
        except Exception:
            continue

    # Save cache file
    try:
        RETEST_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        RETEST_CACHE_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "status": "success",
        "tested_count": len(results),
        "approved_count": len([r for r in results if r.get("approved_for_portfolio")]),
        "results": results
    }

@app.get("/api/retest/results")
def get_retest_results():
    """Returns the latest retest results from disk cache or strategy records."""
    if RETEST_CACHE_FILE.exists():
        try:
            return json.loads(RETEST_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    res = []
    for s in StrategyRecord.list_all():
        if "retest" in s:
            res.append(s["retest"])
    return res

@app.post("/api/retest/send-to-portfolio")
def send_retested_to_portfolio(req: Dict[str, Any]):
    """Receives approved strategy IDs and confirms them ready for the portfolio builder."""
    ids = req.get("strategy_ids", [])
    raw_strats = StrategyRecord.list_all()
    selected = [s for s in raw_strats if s.get("strategy", s).get("id") in ids]
    return {
        "status": "ready_for_portfolio",
        "count": len(selected),
        "strategy_ids": [s.get("strategy", s).get("id") for s in selected]
    }

@app.post("/api/retest/clear")
def clear_retest_results():
    """Clears all cached retest results."""
    if RETEST_CACHE_FILE.exists():
        try:
            RETEST_CACHE_FILE.unlink()
        except Exception:
            pass
    # Also remove retest field from strategy files if present
    for s in StrategyRecord.list_all():
        try:
            sid = s.get("strategy", s).get("id")
            rec = StrategyRecord.load(sid)
            if "retest" in rec.data:
                del rec.data["retest"]
                rec.save(folder=rec.data.get("folder", "General"))
        except Exception:
            pass
    return {"status": "cleared"}

@app.post("/api/engine/clear-results")
def clear_engine_candidates():
    """Clears all current approved candidates in the genetic engine."""
    genetic_engine.clear_candidates()
    return {"status": "cleared"}

@app.post("/api/portfolio-engine/clear")
def clear_portfolio_engine_results():
    """Clears the live top portfolios exploration results."""
    portfolio_engine.clear_top_portfolios()
    return {"status": "cleared"}

@app.post("/api/strategies/clear-all")
def clear_all_strategies(req: Optional[Dict[str, Any]] = None):
    """Deletes all saved strategies or a specific folder."""
    import shutil
    folder = (req or {}).get("folder", "ALL")
    if folder and folder != "ALL":
        StrategyRecord.delete_folder(folder)
    else:
        for p in STRATEGY_DIR.glob("**/*.json"):
            try:
                p.unlink()
            except Exception:
                pass
        for d in STRATEGY_DIR.iterdir():
            if d.is_dir():
                try:
                    shutil.rmtree(d)
                except Exception:
                    pass
    return {"status": "cleared", "folder": folder}

@app.post("/api/clear-all-phases")
def clear_all_phases():
    """Clear transient exploration results; saved libraries survive cleanup/restarts."""
    genetic_engine.clear_candidates()
    if RETEST_CACHE_FILE.exists():
        RETEST_CACHE_FILE.unlink()
    portfolio_engine.clear_top_portfolios()
    return {"status":"cleared","phases":["engine","retest","portfolio_engine"],"saved_libraries_preserved":True}

@app.post("/api/portfolios/clear-all")
def clear_all_portfolios(req: Optional[Dict[str, Any]] = None):
    """Deletes all saved portfolios or a specific folder."""
    import shutil
    folder = (req or {}).get("folder", "ALL")
    if folder and folder != "ALL":
        Portfolio.delete_folder(folder)
    else:
        for p in PORTFOLIO_DIR.glob("**/*.json"):
            try:
                p.unlink()
            except Exception:
                pass
        for d in PORTFOLIO_DIR.iterdir():
            if d.is_dir():
                try:
                    shutil.rmtree(d)
                except Exception:
                    pass
    return {"status": "cleared", "folder": folder}

@app.post("/api/start-exploration")
def start_exploration(req: ExplorationConfigRequest):
    from backend.operators import validate_selection
    from backend.exploration_policy import normalize_config
    try:
        config=normalize_config(req.model_dump())
        validate_selection(req.enabled_indicators,req.enabled_operators)
    except ValueError as error:
        raise HTTPException(422,str(error))
    if req.start_date and req.end_date and req.start_date > req.end_date:
        raise HTTPException(status_code=400,
                            detail="start_date debe ser anterior a end_date")
    if genetic_engine.is_running:
        genetic_engine.stop_exploration()
        import time
        time.sleep(0.5)
    
    genetic_engine.start_exploration(config)
    return {"status": "started", "config": config}

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
                df = data_manager.load_data(strat.symbol, strat.timeframe, source=strat.data_source)
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
    except Exception:
        import traceback
        traceback.print_exc()

    raise HTTPException(status_code=404, detail="Estrategia no encontrada.")

class ValidateCandidateRequest(BaseModel):
    wf_mode: str = "validation"       # "validation" | "reoptimization"
    wf_reopt_depth: str = "standard"  # "fast" | "standard" | "deep"
    wf_windows: int = 4
    wf_test_ratio: float = 0.25
    wf_min_wfe: float = 0.5
    wf_min_pass_rate: float = 60.0
    wf_min_oos_sharpe: float = 0.5
    mv_universes: int = 80
    mv_preset: str = "balanced"       # "balanced" | "conservative" | "aggressive"
    mv_regimes: int = 3

@app.post("/api/candidate/{candidate_id}/validate")
def validate_candidate(candidate_id: str, req: Optional[ValidateCandidateRequest] = None):
    """Runs full Walk-Forward (validation/reoptimization), Multiverse (score+regimes) and Prop Firm sims."""
    options = req or ValidateCandidateRequest()
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
    df = data_manager.load_data(strat.symbol, strat.timeframe, source=strat.data_source)

    # 1. Walk-Forward (con modo reoptimización y umbrales configurables)
    wf_res = validation_suite.run_walk_forward(
        strat, df,
        n_windows=options.wf_windows,
        test_ratio=options.wf_test_ratio,
        mode=options.wf_mode,
        reopt_depth=options.wf_reopt_depth,
        min_wfe=options.wf_min_wfe,
        min_pass_rate=options.wf_min_pass_rate,
        min_sharpe_oos=options.wf_min_oos_sharpe
    )

    # 2. Multiverse con Score 0-100, presets y regímenes
    mv_res = validation_suite.run_multiverse(
        strat, df,
        n_universes=options.mv_universes,
        engine_preset=options.mv_preset,
        n_regimes=options.mv_regimes
    )

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
        with genetic_engine.lock:
            for c in genetic_engine.candidates_passed:
                if c["strategy"]["id"] == candidate_id:
                    c["validation"] = validation_data
                    break

    return validation_data

@app.get("/api/candidate/{candidate_id}/export/{export_format}")
def export_candidate(candidate_id: str, export_format: str):
    if export_format in ('mq5','python'):
        raise HTTPException(501,'Exportación ejecutable no implementada. Usa Copy Master para asignar estrategias compatibles a MT5 demo.')
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
    """Returns metadata, all 32 indicators, entry and exit modes and default parameters."""
    from backend.genetic_engine import OPTIMIZATION_OBJECTIVES
    return {
        "symbols": list(SUPPORTED_SYMBOLS.keys()),
        "timeframes": ["1h", "30m", "4h", "1d"],
        "all_indicators": ALL_28_INDICATORS,
        "entry_types": ALL_ENTRY_TYPES,
        "exit_modes": ALL_EXIT_MODES,
        "session_filters": SESSION_FILTERS,
        "sizing_modes": SIZING_MODES,
        "modeling_modes": ["ohlc", "open_prices", "ohlc_m1", "tick"],
        "search_modes": ["genetic", "random"],
        "wf_modes": ["validation", "reoptimization"],
        "wf_depths": ["fast", "standard", "deep"],
        "mv_presets": ["balanced", "conservative", "aggressive"],
        "macro_available": False,
        "classification_defaults": {"min_trades": 30,"min_profit_factor": 1.2,"min_sharpe": 0.8, "max_drawdown": 20.0, "min_win_rate": 40.0, "min_dsr": 0.3},
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
            {"id": "recovery_factor", "name": "Mayor Recovery Factor"},
            {"id": "pass_rate", "name": "Mayor pass rate de fondeo"}
        ],
        "objective_ids": OPTIMIZATION_OBJECTIVES
    }

class CombinationCountRequest(BaseModel):
    enabled_indicators: List[str] = list(ALL_28_INDICATORS.keys())
    indicator_ranges: Optional[Dict[str, Any]] = None
    exit_ranges: Optional[Dict[str, Any]] = None

@app.post("/api/combinations-count")
def combinations_count(req: CombinationCountRequest):
    """TN-style counter: product of all parameter range points for enabled indicators."""
    from backend.genetic_engine import count_combinations
    total = count_combinations(req.enabled_indicators, req.indicator_ranges, req.exit_ranges)
    return {"combinations": total, "indicators": len(req.enabled_indicators)}

from backend.workspace_features import install_routes
install_routes(app, genetic_engine, ExplorationConfigRequest)
from backend.copy_trading import install_copy_routes
install_copy_routes(app)
from backend.cross_copy import install_routes as install_cross_copy_routes
install_cross_copy_routes(app)
from backend.ea_bridge import install_routes as install_ea_routes
install_ea_routes(app)
from backend.mt5_diagnostic import install_routes as install_diagnostic_routes
install_diagnostic_routes(app)
from backend.indicator_audit import install_routes as install_audit_routes
install_audit_routes(app)
from backend.ninja_bridge import install_routes as install_ninja_routes
from backend.ninja_execution import install_routes as install_ninja_execution
install_ninja_execution(app)
install_ninja_routes(app)
from backend.rocket_bridge import install_routes as install_rocket_routes
install_rocket_routes(app)

from fastapi.responses import FileResponse
USER_PROFILE_FILE = Path("data/user_profile.json")

def get_default_profile():
    return {
        "name": "Julián F.",
        "email": "julian.admin@stratix.io",
        "avatar_url": "https://api.dicebear.com/7.x/bottts/svg?seed=stratix-master",
        "role": "Super Administrador & Fundador",
        "is_admin": True,
        "plan": "Stratix ADMIN (Lifetime Unlimited)",
        "plan_name": "STRATIX ADMIN / MASTER VIP (Ilimitado)",
        "plan_tier": "ADMIN",
        "billing_period": "lifetime",
        "price_usd": 0,
        "discount_code": "ADMIN_FOUNDER",
        "status": "active_lifetime",
        "renewal_date": "De por vida (Acceso Total Ilimitado)",
        "member_since": "Noviembre 2024",
        "license_key": "STX-ADMIN-MASTER-UNLIMITED",
        "max_accounts": 999,
        "linked_services": {
            "ninjatrader": True,
            "mt5": True,
            "cloud_sync": True,
            "unlimited_accounts": True,
            "master_override": True
        }
    }

def load_user_profile():
    if USER_PROFILE_FILE.exists():
        try:
            return json.loads(USER_PROFILE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    profile = get_default_profile()
    USER_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_FILE.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return profile

def save_user_profile(profile_data):
    USER_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_FILE.write_text(json.dumps(profile_data, indent=2, ensure_ascii=False), encoding="utf-8")

@app.get("/api/user/profile")
def get_profile():
    return load_user_profile()

@app.put("/api/user/profile")
def update_profile(data: dict):
    profile = load_user_profile()
    profile.update(data)
    save_user_profile(profile)
    return {"ok": True, "profile": profile}

@app.post("/api/user/regenerate-license")
def regen_license():
    profile = load_user_profile()
    import secrets
    part1 = secrets.token_hex(2).upper()
    part2 = secrets.token_hex(2).upper()
    tier = profile.get('plan_tier', 'ADMIN')
    if profile.get('is_admin') or tier == 'ADMIN':
        profile["license_key"] = f"STX-ADMIN-MASTER-{part1}-{part2}"
    else:
        profile["license_key"] = f"STX-{tier}-{part1}-{part2}-LIVE"
    save_user_profile(profile)
    return {"ok": True, "license_key": profile["license_key"]}

# Frontend routing: /landing (Marketing SaaS), /app (Platform), / (Landing with direct access)
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

@app.get("/landing", response_class=FileResponse)
def serve_landing_page():
    return FileResponse(os.path.join(frontend_dir, "landing.html"))

@app.get("/app", response_class=FileResponse)
def serve_app_platform():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/", response_class=FileResponse)
def serve_root_page():
    landing = os.path.join(frontend_dir, "landing.html")
    if os.path.exists(landing):
        return FileResponse(landing)
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# Mount static frontend files if folder exists
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api:app", host="0.0.0.0", port=8000, reload=True)

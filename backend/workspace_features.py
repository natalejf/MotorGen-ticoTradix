"""Persistent exploration snapshots, editor history and empirical portfolio risk.

No submitted editor source is executed. JSON writes are atomic within one process.
"""
import copy
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1] / 'data'
STORE_LOCK = threading.RLock()


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise HTTPException(400, 'Identificador inválido')
    return value


def read_record(kind, key):
    path = ROOT / kind / (identifier(key) + '.json')
    if not path.exists():
        raise HTTPException(404, 'Registro no encontrado')
    return json.loads(path.read_text(encoding='utf-8'))


def write_record(kind, key, value):
    path = ROOT / kind / (identifier(key) + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with STORE_LOCK:
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temporary.replace(path)
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


class SessionRequest(BaseModel):
    name: str = Field(default='Exploración', min_length=1, max_length=150)
    config: dict = Field(default_factory=dict)
    ui_state: dict = Field(default_factory=dict)


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class EditorRequest(BaseModel):
    source: str = Field(max_length=500000)
    language: str = Field(default='json', pattern='^(json|python|javascript|plaintext)$')
    note: str = Field(default='', max_length=500)


class RiskRequest(BaseModel):
    simulations: int = Field(default=1000, ge=100, le=10000)
    initial_capital: float = Field(default=10000, gt=0, le=1e10)
    ruin_drawdown_pct: float = Field(default=30, gt=0, le=100)
    block_size: int = Field(default=5, ge=1, le=60)
    seed: int = 42


def portfolio_risk(portfolio, options):
    """Daily marked-to-market returns, synchronous block bootstrap of components.

    Calendar alignment preserves simultaneous losses/correlation; empty/constant
    components are reported rather than assigned invented correlations.
    """
    from backend.strategy import Strategy
    from backend.data_manager import data_manager
    from backend.backtester import backtester
    series, labels = [], []
    for item in portfolio.strategies:
        st = item.get('strategy', item)
        curve = item.get('equity_curve')
        if not curve:
            strategy = Strategy.from_dict(st)
            bars = data_manager.load_data(strategy.symbol, strategy.timeframe)
            macro_ids = [name[6:] for name in strategy.get_used_indicators() if name.startswith('MACRO_')]
            if macro_ids:
                from backend.macro_manager import macro_manager
                bars = macro_manager.attach_macro(bars, macro_ids)
            htf = data_manager.load_data(strategy.symbol, strategy.mtf_timeframe) if strategy.mtf_timeframe else None
            result = backtester.run_backtest(strategy, bars, htf_df=htf,
                                            initial_deposit=options.initial_capital)
            curve = result.equity_curve
        frame = pd.DataFrame(curve)
        if frame.empty or 'equity' not in frame:
            raise HTTPException(422, f"Sin equity para {st.get('id')}")
        dates = pd.to_datetime(frame.get('time', frame.get('timestamp')), utc=True, errors='coerce')
        equity = pd.Series(pd.to_numeric(frame['equity'], errors='coerce').to_numpy(), index=dates).dropna()
        equity = equity[~equity.index.isna()].groupby(level=0).last().sort_index().resample('D').last().ffill()
        returns = equity.pct_change(fill_method=None).dropna()
        series.append(returns)
        labels.append(st.get('name', st.get('id', 'Estrategia')))
    if not series:
        raise HTTPException(422, 'Portafolio vacío')
    # Compare only the common observed calendar; missing trading days earn zero.
    start, end = max(s.index.min() for s in series), min(s.index.max() for s in series)
    if pd.isna(start) or pd.isna(end) or start >= end:
        raise HTTPException(422, 'Sin fechas comunes suficientes entre componentes')
    frame = pd.concat(series, axis=1).loc[start:end].fillna(0.)
    if len(frame) < 3:
        raise HTTPException(422, 'Se necesitan al menos tres días comunes')
    corr = frame.corr().to_numpy()
    matrix = [[float(x) if np.isfinite(x) else None for x in row] for row in corr]
    weights = np.asarray(portfolio.weights, dtype=float)
    if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() <= 0:
        raise HTTPException(422, 'Pesos inválidos')
    weights /= weights.sum()
    returns = frame.to_numpy() @ weights
    rng = np.random.default_rng(options.seed)
    horizon = len(returns)
    # Chunk simulations to bound memory even for long historical series.
    terminals, drawdowns, paths = [], [], []
    points = np.unique(np.linspace(0, horizon, min(121, horizon + 1), dtype=int))
    for offset in range(0, options.simulations, 100):
        count = min(100, options.simulations - offset)
        starts = rng.integers(0, horizon, size=(count, int(np.ceil(horizon / options.block_size))))
        indices = (starts[:, :, None] + np.arange(options.block_size)) % horizon
        sampled = returns[indices.reshape(count, -1)[:, :horizon]]
        equity = options.initial_capital * np.cumprod(np.maximum(0., 1. + sampled), axis=1)
        equity = np.column_stack([np.full(count, options.initial_capital), equity])
        peak = np.maximum.accumulate(equity, axis=1)
        dd = np.max((peak - equity) / np.maximum(peak, 1e-12), axis=1) * 100
        terminals.extend(equity[:, -1].tolist())
        drawdowns.extend(dd.tolist())
        paths.extend(equity[:, points].tolist())
    return dict(labels=labels, correlation=matrix, observations=horizon,
                start=str(start), end=str(end), simulations=options.simulations,
                method='synchronous_daily_block_bootstrap', block_size=options.block_size,
                terminal_equity=dict(zip(['p5', 'p50', 'p95'], np.percentile(terminals, [5, 50, 95]).tolist())),
                max_drawdown_pct=dict(zip(['p5', 'p50', 'p95'], np.percentile(drawdowns, [5, 50, 95]).tolist())),
                ruin_probability_pct=float(np.mean(np.asarray(drawdowns) >= options.ruin_drawdown_pct) * 100),
                ruin_drawdown_pct=options.ruin_drawdown_pct,
                path_steps=points.tolist(), equity_percentiles=np.percentile(paths, [5, 50, 95], axis=0).tolist())


def install_routes(app, engine, config_model):
    from backend.portfolio import Portfolio, StrategyRecord

    @app.get('/api/sessions')
    def sessions():
        records = []
        for path in (ROOT / 'sessions').glob('*.json'):
            value = json.loads(path.read_text(encoding='utf-8'))
            records.append({k: value[k] for k in ('id', 'name', 'updated_at', 'candidate_count')})
        return sorted(records, key=lambda r: r['updated_at'], reverse=True)

    @app.post('/api/sessions')
    def save_session(req: SessionRequest):
        config = req.config or getattr(engine, 'last_config', {})
        config = config_model(**config).model_dump()
        with engine.lock:
            candidates = copy.deepcopy(engine.candidates_passed)
            status = {k: getattr(engine, k) for k in ('tested_count', 'discarded_count', 'accepted_count',
                                                      'current_generation', 'progress_pct', 'total_combinations')}
        key = uuid.uuid4().hex
        return write_record('sessions', key, dict(id=key, name=req.name, config=config,
                            candidates=candidates, state=status, ui_state=req.ui_state,
                            updated_at=now(), candidate_count=len(candidates)))

    @app.get('/api/sessions/{key}')
    def session_detail(key: str):
        return read_record('sessions', key)

    @app.patch('/api/sessions/{key}')
    def rename_session(key: str, req: RenameRequest):
        with STORE_LOCK:
            record = read_record('sessions', key)
            record.update(name=req.name, updated_at=now())
            return write_record('sessions', key, record)

    @app.delete('/api/sessions/{key}')
    def delete_session(key: str):
        read_record('sessions', key)
        (ROOT / 'sessions' / (identifier(key) + '.json')).unlink()
        return {'status': 'deleted'}

    @app.post('/api/sessions/{key}/open')
    def open_session(key: str):
        if engine.is_running:
            raise HTTPException(409, 'Detén la exploración antes de abrir una sesión')
        record = read_record('sessions', key)
        engine.reset_state()
        with engine.lock:
            engine.candidates_passed = copy.deepcopy(record['candidates'])
            for k, v in record['state'].items():
                setattr(engine, k, v)
            engine.best_candidate = engine.candidates_passed[0] if engine.candidates_passed else None
            engine.last_config = record['config']
        return record

    @app.post('/api/sessions/{key}/resume')
    def resume_session(key: str):
        if engine.is_running:
            raise HTTPException(409, 'Hay una exploración activa')
        record = read_record('sessions', key)
        config = config_model(**record['config']).model_dump()
        engine.start_exploration(config, resume_candidates=record['candidates'])
        return {'status': 'started', 'config': config, 'resume_mode': 'new_population_preserve_candidates'}

    @app.get('/api/editor/{key}/versions')
    def versions(key: str):
        identifier(key)
        path = ROOT / 'editor' / (key + '.json')
        return read_record('editor', key)['versions'] if path.exists() else []

    @app.post('/api/editor/{key}/versions')
    def save_version(key: str, req: EditorRequest):
        identifier(key)
        with STORE_LOCK:
            path = ROOT / 'editor' / (key + '.json')
            record = read_record('editor', key) if path.exists() else {'id': key, 'versions': []}
            version = dict(version=len(record['versions']) + 1, created_at=now(), **req.model_dump())
            record['versions'].append(version)
            write_record('editor', key, record)
        return version

    @app.patch('/api/rename/{kind}/{key}')
    def rename(kind: str, key: str, req: RenameRequest):
        identifier(key)
        if kind == 'portfolio':
            try:
                portfolio = Portfolio.load(key)
            except FileNotFoundError:
                raise HTTPException(404, 'Portafolio no encontrado')
            portfolio.name = req.name
            portfolio.save()
        elif kind == 'strategy':
            found = False
            with engine.lock:
                for candidate in engine.candidates_passed:
                    if candidate['strategy']['id'] == key:
                        candidate['strategy']['name'] = req.name
                        found = True
            try:
                record = StrategyRecord.load(key)
                record.data['strategy']['name'] = req.name
                record.save(record.data.get('folder', 'General'))
                found = True
            except FileNotFoundError:
                pass
            if not found:
                raise HTTPException(404, 'Estrategia no encontrada')
        else:
            raise HTTPException(400, 'Tipo inválido')
        return {'name': req.name}

    @app.post('/api/portfolio/{key}/risk')
    def risk(key: str, req: RiskRequest):
        identifier(key)
        try:
            portfolio = Portfolio.load(key)
        except FileNotFoundError:
            raise HTTPException(404, 'Portafolio no encontrado')
        return portfolio_risk(portfolio, req)

"""Stratix local copy control plane. Workers alone communicate with MT5.

No broker credentials are stored. Demo accounts only in this first connector.
"""
import json
import math
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'data' / 'copy_trading.sqlite3'


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, account TEXT, deployment TEXT, message TEXT);
        CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, state TEXT, body TEXT, updated REAL);
        CREATE TABLE IF NOT EXISTS leases(account TEXT PRIMARY KEY, owner TEXT, expires REAL);
    ''')
    try:
        with db:
            yield db
    finally:
        db.close()


def put(kind, key, body):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)', (kind, key, json.dumps(body, allow_nan=False)))
    return body


def get(kind, key):
    with connect() as db:
        row = db.execute('SELECT body FROM records WHERE kind=? AND id=?', (kind, key)).fetchone()
    if row is None:
        raise KeyError(key)
    return json.loads(row['body'])


def listing(kind):
    with connect() as db:
        rows = db.execute('SELECT body FROM records WHERE kind=? ORDER BY rowid DESC', (kind,)).fetchall()
    return [json.loads(r['body']) for r in rows]


def log(account, deployment, message):
    with connect() as db:
        db.execute('INSERT INTO events(created,account,deployment,message) VALUES(?,?,?,?)',
                   (time.time(), account, deployment, str(message)[:2000]))
        db.execute('DELETE FROM events WHERE seq < (SELECT COALESCE(MAX(seq),0)-10000 FROM events)')


def lease(account, owner, seconds=30):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT owner,expires FROM leases WHERE account=?', (account,)).fetchone()
        if row and row['owner'] != owner and row['expires'] > time.time():
            return False
        db.execute('INSERT OR REPLACE INTO leases VALUES(?,?,?)', (account, owner, time.time()+seconds))
    return True


def claim_action(key, request):
    """Never resend an action after an ambiguous result or process interruption."""
    with connect() as db:
        cursor = db.execute('INSERT OR IGNORE INTO actions VALUES(?,?,?,?)',
                            (key, 'SENDING', json.dumps(request), time.time()))
        return cursor.rowcount == 1


def finish_action(key, state, result):
    with connect() as db:
        db.execute('UPDATE actions SET state=?,body=?,updated=? WHERE id=?',
                   (state, json.dumps(result, default=str), time.time(), key))


class AccountRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    terminal_path: str = Field(min_length=1, max_length=500)
    login: int = Field(gt=0)
    server: str = Field(min_length=1, max_length=150)


class DeploymentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    account_id: str
    source_type: str = Field(pattern='^(strategy|portfolio|account)$')
    source_id: str
    symbol_map: dict[str, str] = Field(default_factory=dict)
    risk_percent: float = Field(default=.25, gt=0, le=5)
    fixed_lot: float = Field(default=0, ge=0, le=100)
    max_lot: float = Field(default=1, gt=0, le=100)
    max_daily_loss_pct: float = Field(default=2, gt=0, le=20)
    max_drawdown_pct: float = Field(default=5, gt=0, le=50)
    max_positions: int = Field(default=5, ge=1, le=50)
    max_spread_points: float = Field(default=50, gt=0, le=10000)
    deviation_points: int = Field(default=10, ge=0, le=1000)
    risk_mode: str = Field(default='RISK_PERCENT',pattern='^(RISK_PERCENT|FIXED_LOT|MULTIPLIER|PROPORTIONAL|MIRROR)$')
    multiplier: float = Field(default=1,gt=0,le=100)
    direction_filter: str = Field(default='BOTH',pattern='^(BOTH|BUY|SELL)$')
    symbol_whitelist: list[str] = Field(default_factory=list)
    group_id: str | None = None
    symbol_filter: str = Field(default='WHITELIST',pattern='^(ALL|WHITELIST|BLACKLIST)$')
    sl_tp_mode: str = Field(default='PROVIDER',pattern='^(PROVIDER|CUSTOM)$')
    custom_sl_pips: float = Field(default=20,gt=0,le=100000)
    custom_tp_pips: float = Field(default=40,gt=0,le=100000)
    max_daily_gain_pct: float = Field(default=0,ge=0,le=100)
    max_exposure_per_symbol: float = Field(default=0,ge=0,le=10000)
    max_total_exposure: float = Field(default=0,ge=0,le=10000)
    equity_protection: float = Field(default=0,ge=0)
    max_order_age_seconds: int = Field(default=30,ge=1,le=300)


class GroupRequest(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    description: str = Field(default='',max_length=500)
    account_ids: list[str] = Field(default_factory=list)
    risk_mode: str = Field(default='FIXED_LOT',pattern='^(RISK_PERCENT|FIXED_LOT|MULTIPLIER|PROPORTIONAL|MIRROR)$')
    fixed_lot: float = Field(default=.01,gt=0,le=100)
    multiplier: float = Field(default=1,gt=0,le=100)
    risk_percent: float = Field(default=.25,gt=0,le=5)
    max_daily_loss_pct: float = Field(default=2,gt=0,le=20)
    max_drawdown_pct: float = Field(default=5,gt=0,le=50)


class MasterRequest(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    account_id: str


class FollowerRequest(BaseModel):
    account_id: str | None = None
    group_id: str | None = None
    settings: dict = Field(default_factory=dict)


def compatibility(strategy):
    """Reject unsupported live semantics rather than silently dropping rules."""
    reasons = []
    if strategy.timeframe not in ('30m', '1h', '4h', '1d'):
        reasons.append('Temporalidad no admitida')
    if strategy.entry_order_type != 'MARKET':
        reasons.append('El conector inicial admite entradas MARKET; LIMIT/STOP requieren implementación específica')
    if strategy.avg_enabled:
        reasons.append('Averaging/DCA todavía no habilitado en el conector MT5')
    if strategy.sizing_mode in ('MARTINGALE', 'ANTI_MARTINGALE', 'DCA'):
        reasons.append('Sizing dinámico por racha/DCA todavía no habilitado en MT5')
    if strategy.mtf_timeframe and strategy.mtf_timeframe not in ('30m','1h','4h','1d'):
        reasons.append('Temporalidad HTF no admitida')
    if strategy.max_consecutive_wins or strategy.max_consecutive_losses or any(
        getattr(strategy,key,0) for key in ('max_daily_gain_pct','max_weekly_gain_pct','max_monthly_gain_pct','max_account_gain_pct')):
        reasons.append('Topes de ganancia/racha de la estrategia aún no admitidos por el conector')
    if not strategy.buy_conditions and not strategy.sell_conditions:
        reasons.append('La estrategia no tiene condiciones')
    return reasons


def install_copy_routes(app):
    from backend.strategy import Strategy
    from backend.portfolio import Portfolio, StrategyRecord

    @app.middleware('http')
    async def copy_same_origin(request, call_next):
        if request.url.path.startswith('/api/copy/'):
            origin=request.headers.get('origin')
            if origin:
                parsed=urlsplit(origin)
                if parsed.netloc != request.headers.get('host') or parsed.scheme != request.url.scheme:
                    return JSONResponse({'detail':'Copy Trading solo acepta solicitudes desde la propia aplicación'},status_code=403)
        return await call_next(request)

    def required(kind, key):
        try:
            return get(kind, key)
        except KeyError:
            raise HTTPException(404, 'Registro no encontrado')

    @app.get('/api/copy/status')
    def status():
        accounts = listing('account')
        for account in accounts:
            try:
                snapshot = get('snapshot', account['id'])
                account['snapshot'] = snapshot
                account['connected'] = time.time()-snapshot.get('at', 0) < 15
            except KeyError:
                account['connected'] = False
        with connect() as db:
            events = [dict(row) for row in db.execute('SELECT * FROM events ORDER BY seq DESC LIMIT 100')]
        return dict(accounts=accounts, deployments=listing('deployment'), events=events,
                    masters=listing('master'),groups=listing('group'),
                    connector='MT5 local / demo', real_trading_enabled=False)

    @app.post('/api/copy/accounts')
    def account(req: AccountRequest):
        path = Path(req.terminal_path).resolve()
        if not path.is_file() or path.name.lower() != 'terminal64.exe':
            raise HTTPException(400, 'Indica la ruta existente de terminal64.exe')
        for existing in listing('account'):
            if existing['login'] == req.login and existing['server'] == req.server:
                raise HTTPException(409, 'Esa cuenta ya está registrada')
            if Path(existing['terminal_path']).resolve() == path:
                raise HTTPException(409, 'Cada cuenta simultánea necesita una instalación de terminal independiente')
        key = uuid.uuid4().hex
        return put('account', key, dict(id=key, **req.model_dump()))

    @app.patch('/api/copy/accounts/{key}')
    def edit_account(key:str,req:AccountRequest):
        required('account',key)
        if any(d['account_id']==key and d['state']!='STOPPED' for d in listing('deployment')):
            raise HTTPException(409,'Detén las asignaciones antes de editar el terminal')
        path=Path(req.terminal_path).resolve()
        if not path.is_file() or path.name.lower()!='terminal64.exe':
            raise HTTPException(400,'Ruta terminal64.exe inválida')
        for other in listing('account'):
            if other['id']!=key and (Path(other['terminal_path']).resolve()==path or (other['login']==req.login and other['server']==req.server)):
                raise HTTPException(409,'Terminal o cuenta ya registrada')
        with connect() as db:
            row=db.execute('SELECT expires FROM leases WHERE account=?',(key,)).fetchone()
        if row and row['expires']>time.time():
            raise HTTPException(409,'Cierra primero el conector de esta cuenta')
        return put('account',key,dict(id=key,**req.model_dump()))

    @app.post('/api/copy/accounts/{key}/worker')
    def worker(key: str):
        required('account', key)
        with connect() as db:
            active = db.execute('SELECT expires FROM leases WHERE account=?', (key,)).fetchone()
        if active and active['expires'] > time.time():
            raise HTTPException(409, 'El conector ya está activo')
        args = [sys.executable, '-m', 'backend.mt5_worker', '--account', key]
        put('worker_control',key,{'stop':False})
        log_dir = ROOT / 'data' / 'copy_logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / f'{key}.log').open('ab') as output:
            process = subprocess.Popen(args, cwd=str(ROOT), stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        log(key, '', f'Conector solicitado (PID {process.pid}); pendiente de heartbeat MT5 verificado')
        return {'status': 'starting', 'pid': process.pid}

    @app.post('/api/copy/accounts/{key}/worker/stop')
    def stop_worker(key:str):
        required('account',key)
        for record in listing('deployment'):
            if record['account_id']==key and record['state']=='ACTIVE':
                record['state']='PAUSED'
                put('deployment',record['id'],record)
        put('worker_control',key,{'stop':True})
        log(key,'','Detención del conector solicitada; entradas pausadas. SL/TP quedan en el bróker.')
        return {'status':'stopping'}

    @app.post('/api/copy/deployments')
    def deployment(req: DeploymentRequest):
        required('account', req.account_id)
        if req.risk_mode=='FIXED_LOT' and req.fixed_lot<=0:
            raise HTTPException(400,'Lote fijo debe ser mayor que cero')
        if req.source_type!='account' and req.risk_mode not in ('FIXED_LOT','RISK_PERCENT'):
            raise HTTPException(400,'Ese modo de tamaño requiere una cuenta master')
        if req.group_id:
            group=required('group',req.group_id)
            if req.account_id not in group['account_ids']:
                raise HTTPException(400,'La cuenta destino no pertenece al grupo')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',req.source_id):
            raise HTTPException(400,'Identificador origen inválido')
        strategies, weights = [], []
        try:
            if req.source_type == 'strategy':
                strategies = [StrategyRecord.load(req.source_id).data]
                weights = [1.]
            elif req.source_type == 'portfolio':
                portfolio = Portfolio.load(req.source_id)
                strategies, weights = portfolio.strategies, portfolio.weights
            else:
                required('account', req.source_id)
                if req.account_id == req.source_id:
                    raise HTTPException(400, 'Una cuenta no puede copiarse a sí misma')
                # Avoid copying a follower into another chain or cycle.
                for other in listing('deployment'):
                    if other['state']!='STOPPED' and other['source_type']=='account' and (other['account_id'] == req.source_id or other['source_id'] == req.account_id):
                        raise HTTPException(400, 'No se admiten cadenas o ciclos de copia')
        except FileNotFoundError:
            raise HTTPException(404, 'Guarda primero la estrategia o el portafolio')
        if req.source_type != 'account' and not strategies:
            raise HTTPException(400, 'Sin estrategias')
        if any(not math.isfinite(float(w)) or w < 0 for w in weights) or (weights and sum(weights) <= 0):
            raise HTTPException(400, 'Pesos inválidos')
        snapshots = []
        for item, weight in zip(strategies, weights):
            strategy = Strategy.from_dict(item.get('strategy', item))
            errors = compatibility(strategy)
            if errors:
                raise HTTPException(422, f'{strategy.name}: ' + '; '.join(errors))
            snapshots.append(dict(strategy=strategy.to_dict(), weight=float(weight)/sum(weights)))
        # One risk owner per account; multiple algorithms belong in one portfolio.
        if any(d['account_id'] == req.account_id and d['state'] != 'STOPPED' for d in listing('deployment')):
            raise HTTPException(409, 'La cuenta ya tiene una asignación. Combina los algoritmos en un portafolio o detén la anterior.')
        key = uuid.uuid4().hex
        record = dict(id=key, **req.model_dump(), state='PAUSED', strategies=snapshots,
                      magic=100000000 + int(key[:7], 16), created_at=time.time())
        return put('deployment', key, record)

    @app.post('/api/copy/deployments/{key}/{action}')
    def control(key: str, action: str):
        record = required('deployment', key)
        if action not in ('resume', 'pause', 'close-stop'):
            raise HTTPException(400, 'Acción inválida')
        if action == 'resume':
            if record['state'] == 'STOPPED':
                raise HTTPException(409, 'Crea una nueva asignación para reiniciar una detenida')
            snapshot = required('snapshot', record['account_id'])
            if time.time()-snapshot.get('at', 0) > 15 or not snapshot.get('verified_demo'):
                raise HTTPException(409, 'Conecta primero la cuenta demo MT5 correcta')
        record['state'] = {'resume':'ACTIVE', 'pause':'PAUSED', 'close-stop':'CLOSING'}[action]
        put('deployment', key, record)
        log(record['account_id'], key, f'Estado solicitado: {record["state"]}')
        return record

    @app.patch('/api/copy/deployments/{key}/settings')
    def settings(key:str,req:dict):
        record=required('deployment',key)
        editable={'risk_mode','risk_percent','fixed_lot','max_lot','multiplier','max_daily_loss_pct',
                  'max_drawdown_pct','max_positions','max_spread_points','deviation_points',
                  'direction_filter','symbol_whitelist','symbol_map','symbol_filter','sl_tp_mode',
                  'custom_sl_pips','custom_tp_pips','max_daily_gain_pct','max_exposure_per_symbol',
                  'max_total_exposure','equity_protection','max_order_age_seconds'}
        if set(req)-editable:
            raise HTTPException(400,'Campos no editables en la configuración')
        try:
            validated=DeploymentRequest(**dict(record,**req)).model_dump()
        except ValueError as error:
            raise HTTPException(422,str(error))
        if validated['risk_mode']=='FIXED_LOT' and validated['fixed_lot']<=0:
            raise HTTPException(400,'Lote fijo debe ser mayor que cero')
        if record['source_type']!='account' and validated['risk_mode'] not in ('FIXED_LOT','RISK_PERCENT'):
            raise HTTPException(400,'Ese modo de tamaño requiere una master')
        for field in editable:
            record[field]=validated[field]
        put('deployment',key,record)
        log(record['account_id'],key,'Tamaño, filtros y límites actualizados desde Stratix')
        return record

    @app.get('/api/copy/groups')
    def groups():
        return listing('group')

    def group_record(req,key):
        for account_id in req.account_ids:
            required('account',account_id)
        record=dict(id=key,**req.model_dump())
        record['account_ids']=list(dict.fromkeys(record['account_ids']))
        return record

    @app.post('/api/copy/groups')
    def create_group(req:GroupRequest):
        key=uuid.uuid4().hex
        return put('group',key,group_record(req,key))

    @app.patch('/api/copy/groups/{key}')
    def update_group(key:str,req:GroupRequest):
        required('group',key)
        record=group_record(req,key)
        for deployment_record in listing('deployment'):
            if deployment_record.get('group_id')==key and deployment_record['account_id'] not in req.account_ids:
                deployment_record['group_id']=None
                if deployment_record['state']!='STOPPED':
                    deployment_record['state']='PAUSED'
                put('deployment',deployment_record['id'],deployment_record)
                log(deployment_record['account_id'],deployment_record['id'],'Cuenta retirada del grupo: copia pausada y conservada como individual')
        return put('group',key,record)

    @app.post('/api/copy/groups/{key}/apply')
    def apply_group(key:str):
        group=required('group',key)
        members=[d for d in listing('deployment') if d.get('group_id')==key and d['state']!='STOPPED']
        if group['risk_mode'] not in ('FIXED_LOT','RISK_PERCENT') and any(d['source_type']!='account' for d in members):
            raise HTTPException(422,'El modo de tamaño del grupo no es compatible con sus asignaciones de algoritmos')
        updated=[]
        for record in members:
            if record.get('group_id')==key and record['state']!='STOPPED':
                for field in ('risk_mode','fixed_lot','multiplier','risk_percent','max_daily_loss_pct','max_drawdown_pct'):
                    record[field]=group[field]
                put('deployment',record['id'],record)
                log(record['account_id'],record['id'],'Configuración de grupo aplicada')
                updated.append(record['id'])
        return {'updated':updated}

    @app.post('/api/copy/groups/{key}/{action}')
    def group_control(key:str,action:str):
        required('group',key)
        if action not in ('pause','resume','close-stop'):
            raise HTTPException(400,'Acción inválida')
        result=[]
        for record in listing('deployment'):
            if record.get('group_id')==key and record['state']!='STOPPED':
                try:
                    control(record['id'],action)
                    result.append({'id':record['id'],'status':'updated'})
                except HTTPException as error:
                    result.append({'id':record['id'],'error':error.detail})
        return {'results':result}

    @app.delete('/api/copy/groups/{key}')
    def delete_group(key:str):
        required('group',key)
        if any(d.get('group_id')==key and d['state']!='STOPPED' for d in listing('deployment')):
            raise HTTPException(409,'Detén las copias del grupo antes de eliminarlo')
        with connect() as db:
            db.execute('DELETE FROM records WHERE kind=? AND id=?',('group',key))
        return {'status':'deleted'}

    @app.post('/api/copy/masters')
    def create_master(req:MasterRequest):
        required('account',req.account_id)
        if any(m['account_id']==req.account_id for m in listing('master')):
            raise HTTPException(409,'La cuenta ya está registrada como master')
        key=uuid.uuid4().hex
        return put('master',key,dict(id=key,**req.model_dump()))

    @app.delete('/api/copy/masters/{key}')
    def delete_master(key:str):
        master=required('master',key)
        if any(d['source_type']=='account' and d['source_id']==master['account_id'] and d['state']!='STOPPED' for d in listing('deployment')):
            raise HTTPException(409,'Detén sus seguidoras antes de retirar la master')
        with connect() as db:
            db.execute('DELETE FROM records WHERE kind=? AND id=?',('master',key))
        return {'status':'deleted'}

    @app.post('/api/copy/masters/{key}/followers')
    def add_followers(key:str,req:FollowerRequest):
        master=required('master',key)
        if bool(req.account_id)==bool(req.group_id):
            raise HTTPException(400,'Elige una cuenta O un grupo')
        settings=dict(req.settings)
        if req.group_id:
            group=required('group',req.group_id)
            targets=group['account_ids']
            if not targets:
                raise HTTPException(400,'Añade cuentas al grupo antes de crear sus copias')
            for field in ('risk_mode','fixed_lot','multiplier','risk_percent','max_daily_loss_pct','max_drawdown_pct'):
                settings[field]=group[field]
        else:
            targets=[req.account_id]
        results=[]
        for target in dict.fromkeys(targets):
            try:
                body=dict(settings,name=f'{master["name"]} → {required("account",target)["name"]}',
                          account_id=target,source_type='account',source_id=master['account_id'],group_id=req.group_id)
                record=deployment(DeploymentRequest(**body))
                results.append({'account_id':target,'id':record['id'],'status':'PAUSED'})
            except HTTPException as error:
                results.append({'account_id':target,'error':error.detail})
            except ValueError as error:
                results.append({'account_id':target,'error':str(error)})
        return {'results':results}

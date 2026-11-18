"""NT8 single-strategy executor using the same signal/exit engine as MT5."""
import hashlib
import math
import threading
import time
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field
from backend import copy_trading as store
from backend.mt5_worker import MT5Worker
from backend.ninja_rpc import NinjaBroker
from backend.portfolio import StrategyRecord,Portfolio
from backend.strategy import Strategy

workers={}
worker_lock=threading.Lock()
assignment_lock=threading.Lock()


class StartRequest(BaseModel):
    connection: str
    account: str
    source_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    source_type: str=Field(default='strategy',pattern='^(strategy|portfolio)$')
    symbol_map: dict[str,str]
    contracts: int=Field(default=1,ge=1,le=100)


class NinjaWorker(MT5Worker):
    def __init__(self,record):
        super().__init__(NinjaBroker(record['connection'],record['account_name'],record['id'],
                         next(iter(record['symbol_map'].values())),record['magic']),dict(id=record['account_id']))
        self.session=record['id'];self.claimed=False;self.error_at=0
        self.brokers=[]
        for index,item in enumerate(record['strategies']):
            symbol=record['symbol_map'][item['strategy']['symbol']]
            child=record['id'] if len(record['strategies'])==1 else uuid.uuid5(uuid.UUID(record['id']),str(index)).hex
            self.brokers.append(NinjaBroker(record['connection'],record['account_name'],child,symbol,record['magic']+index,parent=record['id']))

    def verify(self):
        snapshot=store.get('ninja_snapshot',self.mt5.connection)
        if time.time()-snapshot.get('at',0)>10:raise RuntimeError('NinjaTrader desconectado')
        record=store.get('deployment',self.session)
        if snapshot['instance']!=record['instance']:
            if record['state']=='ACTIVE':
                record['state']='PAUSED';store.put('deployment',record['id'],record)
            raise RuntimeError('NinjaTrader reiniciado: reanuda explícitamente esta asignación')
        row=next((a for a in snapshot['accounts'] if a['name']==self.mt5.account_name),{})
        if not row.get('execution_allowed') or row.get('provider') not in ('Simulator','Playback'):
            raise RuntimeError('La cuenta local simulada no está disponible')
        info=self.mt5.account_info()
        if not info.trade_allowed and record['state']!='CLOSING':
            record['state']='PAUSED';store.put('deployment',record['id'],record)
            raise RuntimeError('Cuenta sin permiso de ejecución; asignación pausada')
        return info,self.mt5.terminal_info()

    def cycle(self):
        record=store.get('deployment',self.session)
        if not store.lease(self.account['id'],self.owner,120):return
        if not self.claimed:
            for broker in self.brokers:broker.rpc('claim')
            self.claimed=True
            store.log(self.account['id'],self.session,f'NT8 CONECTADO · {len(self.brokers)} instrumento(s) reservado(s); evaluador compartido del motor')
        all_positions=[]
        for broker in self.brokers:
            broker.invalidate();all_positions.extend(vars(p) for p in broker.positions_get())
        self.mt5=self.brokers[0];info,_=self.verify()
        store.put('snapshot',self.account['id'],dict(at=time.time(),verified_demo=True,platform='NT8',
                  balance=info.balance,equity=info.equity,positions=all_positions))
        if record['state']=='CLOSING':
            from backend.mt5_diagnostic import cancel_pending
            flat=True
            for index,broker in enumerate(self.brokers):
                self.mt5=broker;sub=dict(record,magic=record['magic']+index)
                for order in broker.orders_get():cancel_pending(self,sub,order)
                for position in self.positions():self.close_position(sub,position,reason='stop')
                broker.invalidate()
                if self.positions() or broker.orders_get():flat=False
            if flat:
                for broker in self.brokers:broker.rpc('release')
                record['state']='STOPPED';store.put('deployment',record['id'],record)
                store.log(self.account['id'],self.session,'DETENIDO · cuenta sin posiciones ni órdenes del algoritmo')
            return
        runtime=self.local_state(record)
        if record.get('execution_profile')=='stx_nt8_audit_v1':
            from backend.mt5_diagnostic import run
            run(self,record,record['state']=='ACTIVE' and self.risk_allowed(record,info))
            if store.get('deployment',self.session)['state']=='STOPPED':
                self.mt5.rpc('release')
            return
        for index,(item,broker) in enumerate(zip(record['strategies'],self.brokers)):
            self.mt5=broker
            sub=dict(record,risk_percent=record['risk_percent']*item['weight'])
            # Weights allocate cash risk, never fractions of futures contracts.
            try:self.algorithm(sub,runtime,dict(item,weight=1),index,store.get('deployment',self.session)['state']=='ACTIVE' and self.risk_allowed(record,info))
            except Exception as error:
                if len(self.brokers)==1:raise
                if time.time()-runtime.setdefault('leg_errors',{}).get(str(index),0)>60:
                    store.log(self.account['id'],self.session,f'{broker.symbol} · {error}')
                    runtime['leg_errors'][str(index)]=time.time()
        store.put('runtime',record['id'],runtime)

    def run(self):
        while store.get('deployment',self.session)['state']!='STOPPED':
            try:self.cycle()
            except Exception as error:
                if time.time()-self.error_at>60:
                    store.log(self.account['id'],self.session,str(error));self.error_at=time.time()
            time.sleep(1)


def ensure_workers(connection):
    with worker_lock:
        for record in store.listing('deployment'):
            if record.get('platform')!='NT8' or record.get('connection')!=connection or record['state']=='STOPPED':continue
            thread=workers.get(record['id'])
            if not thread or not thread.is_alive():
                worker=NinjaWorker(record)
                thread=threading.Thread(target=worker.run,daemon=True,name='NT8-'+record['id'][:8])
                workers[record['id']]=thread;thread.start()


def install_routes(app):
    @app.post('/api/ninja/execution/start')
    def start(req:StartRequest):
        with assignment_lock:
            try:snapshot=store.get('ninja_snapshot',req.connection)
            except KeyError:raise HTTPException(409,'Conecta NinjaTrader primero')
            if time.time()-snapshot.get('at',0)>10 or snapshot.get('version')!='1.5.4-portfolio':
                raise HTTPException(409,'Conecta el AddOn 1.5.4-portfolio actualizado y compilado en NinjaTrader')
            row=next((a for a in snapshot['accounts'] if a['name']==req.account),{})
            if not row.get('execution_allowed') or row.get('provider') not in ('Simulator','Playback'):
                raise HTTPException(409,'Primera versión: cuentas locales Simulator/Playback')
            account_id='nt_'+hashlib.sha256((req.connection+':'+req.account).encode()).hexdigest()[:24]
            for occupied in store.listing('deployment'):
                if occupied['account_id']==account_id and occupied['state']!='STOPPED':
                    if store.same_execution_source(occupied,req.source_type,req.source_id):return occupied
                    raise HTTPException(409,'Detén la asignación anterior de esta cuenta')
            if row.get('enabled') and row.get('status')=='EN PROCESO':
                raise HTTPException(409,'La cuenta está reservada a PropPass')
            if row.get('position_quantity') or row.get('working_orders'):
                raise HTTPException(409,'La cuenta debe estar flat y sin órdenes')
            try:
                if req.source_type=='portfolio':
                    portfolio=Portfolio.load(req.source_id)
                    items=portfolio.strategies;weights=portfolio.weights;name=portfolio.name;risk=portfolio.risk_budget
                else:
                    saved=StrategyRecord.load(req.source_id).data
                    items=[saved];weights=[1];name=saved['strategy']['name'];risk=saved['strategy']['risk_per_trade_pct']
            except FileNotFoundError:raise HTTPException(404,'Algoritmo guardado no encontrado')
            if not 1<=len(items)<=10 or len(weights)!=len(items) or any(not math.isfinite(w) or w<=0 for w in weights):raise HTTPException(422,'Portafolio: 1 a 10 algoritmos y pesos positivos')
            if not math.isfinite(risk) or not 0<risk<=5:raise HTTPException(422,'Riesgo total por entradas del portafolio: mayor que 0 y hasta 5%')
            weights=[w/sum(weights) for w in weights]
            strategies=[Strategy.from_dict(item['strategy']) for item in items]
            reasons=[]
            for strategy in strategies:
                reasons.extend(store.compatibility(strategy))
                if any(i.startswith('MACRO_') for i in strategy.get_used_indicators()):reasons.append('Indicadores macro no habilitados en NT8')
                if strategy.exit_mode=='PARTIAL_TP' and (int(req.contracts*strategy.partial_pct/100)<1 or int(req.contracts*strategy.partial_pct/100)>=req.contracts):reasons.append('El cierre parcial requiere contratos enteros para ambas partes')
            if reasons:raise HTTPException(422,'; '.join(reasons).replace('MT5','NT8'))
            mapping=store.validate_symbol_map(req.symbol_map)
            if set(mapping)!={s.symbol for s in strategies}:raise HTTPException(422,'Mapea todos los símbolos a contratos exactos de NinjaTrader')
            if len({mapping[s.symbol] for s in strategies})!=len(strategies):raise HTTPException(422,'NT8 netting: cada algoritmo del portafolio debe usar un contrato distinto')
            strategy=strategies[0]
            key=uuid.uuid4().hex
            config=store.DeploymentRequest(name=name,account_id=account_id,source_type=req.source_type,source_id=req.source_id,
                symbol_map=mapping,fixed_lot=req.contracts,max_lot=req.contracts,risk_mode='FIXED_LOT',
                risk_percent=risk,max_positions=1,
                max_daily_loss_pct=strategy.max_daily_loss_pct if len(items)==1 else 0,max_drawdown_pct=strategy.max_account_loss_pct if len(items)==1 else 0,
                max_daily_gain_pct=strategy.max_daily_gain_pct if len(items)==1 else 0,max_account_gain_pct=strategy.max_account_gain_pct if len(items)==1 else 0)
            record=dict(config.model_dump(),id=key,platform='NT8',connection=req.connection,instance=snapshot['instance'],
                account_name=req.account,ui_account_id='nt:'+req.connection+':'+req.account,contracts=req.contracts,
                state='ACTIVE',origin_type=req.source_type,uses_source_risk=False,initial_equity=row['balance']+row.get('unrealized',0),
                strategies=[dict(strategy=s.to_dict(),weight=w) for s,w in zip(strategies,weights)],magic=100000000+int(key[:7],16),created_at=time.time())
            if req.source_type=='strategy' and saved.get('execution_profile')=='stx_nt8_audit_v1' and req.contracts<2:
                raise HTTPException(422,'El diagnóstico necesita 2 contratos para probar el cierre parcial')
            store.put('deployment',key,record);store.reset_execution_view(record)
            if req.source_type=='strategy' and saved.get('execution_profile')=='stx_nt8_audit_v1':
                record.update(source_type='diagnostic',execution_profile='stx_nt8_audit_v1',
                    diagnostic_symbol=mapping[strategy.symbol],diagnostic_timeout=45,audit_indicators=True)
                store.put('deployment',key,record)
                store.put('diagnostic',key,dict(index=0,phase='OPEN',results=[]))
            store.put('ninja_symbol_map',req.connection+':'+req.account,dict(connection=req.connection,account=req.account,symbol_map=mapping))
            store.log(account_id,key,f'INICIO · {name} · NT8 {req.account} · {req.contracts} contrato(s) por instrumento · riesgo máximo total {record["risk_percent"]}%')
            ensure_workers(req.connection)
            return record

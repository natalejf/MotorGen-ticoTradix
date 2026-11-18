"""Account registration and read-only native master observation for cross copy."""
import hashlib
import threading
import time
import uuid
from fastapi import HTTPException
from pydantic import BaseModel, Field
from backend import copy_trading as store

observers = {}
observer_lock = threading.Lock()
COPY_VERSION = '1.6.0-copy'


class NativeAccount(BaseModel):
    connection: str
    account: str = Field(min_length=1,max_length=100)


def configure_copy(record, target, source):
    cross = target.get('platform','MT5') != source.get('platform','MT5')
    if cross and not record['symbol_map']:
        raise HTTPException(422,'Mapea explícitamente el símbolo master al instrumento destino')
    if cross and record['risk_mode'] in ('MIRROR','MULTIPLIER','PROPORTIONAL') and record.get('quantity_ratio') is None:
        raise HTTPException(422,'Indica cuántas unidades destino corresponden a una unidad master; no existe una conversión universal lote/contrato')
    record['cross_platform'] = cross
    if target.get('platform') == 'NT8':
        if record['risk_mode']=='FIXED_LOT' and record['fixed_lot']!=int(record['fixed_lot']):
            raise HTTPException(422,'El tamaño fijo NinjaTrader debe ser un número entero de contratos')
        if record.get('sl_tp_mode')=='CUSTOM':
            raise HTTPException(422,'Para futuros usa distancias SL/TP de la master; pips propios solo están disponibles en MT5')
        if not record['symbol_map'] or len(set(record['symbol_map'].values())) != len(record['symbol_map']):
            raise HTTPException(422,'NinjaTrader requiere un contrato destino distinto por símbolo master (netting)')
        snapshot = store.get('ninja_snapshot',target['connection'])
        if snapshot.get('version') != COPY_VERSION:
            raise HTTPException(409,'Actualiza el AddOn a '+COPY_VERSION)
        record.update(platform='NT8',connection=target['connection'],account_name=target['account_name'],
                      instance=snapshot['instance'],ui_account_id=target['id'])
        record['max_positions']=1
        record['strategies']=[dict(strategy=dict(symbol=symbol),weight=1) for symbol in record['symbol_map']]


def observe(account):
    from backend.ninja_rpc import NinjaBroker
    session = uuid.uuid5(uuid.NAMESPACE_OID,'observe:'+account['id']).hex
    broker = NinjaBroker(account['connection'],account['account_name'],session,'',0)
    while True:
        try:
            if store.get('worker_control',account['id']).get('stop'):return
        except KeyError:pass
        try:
            native = store.get('ninja_snapshot',account['connection'])
            if native.get('version') != COPY_VERSION:raise RuntimeError('Actualiza AddOn a '+COPY_VERSION)
            value = broker.rpc('observe')
            store.put('snapshot',account['id'],dict(value,at=time.time(),verified_demo=True,
                      platform='NT8',currency='USD',source_instance=native['instance']))
        except Exception as error:
            store.log(account['id'],'','Observador master NT8: '+str(error))
        time.sleep(1)


def ensure_observers(connection):
    with observer_lock:
        masters={m['account_id'] for m in store.listing('master')}
        for account in store.listing('account'):
            if account.get('platform')!='NT8' or account.get('connection')!=connection or account['id'] not in masters:continue
            try:
                if store.get('worker_control',account['id']).get('stop'):continue
            except KeyError:pass
            thread=observers.get(account['id'])
            if not thread or not thread.is_alive():
                thread=threading.Thread(target=observe,args=(account,),daemon=True,name='CopyObserver-'+account['id'])
                observers[account['id']]=thread;thread.start()


def install_routes(app):
    @app.get('/api/copy/deployments/{key}/tickets')
    def tickets(key:str):
        try:record=store.get('deployment',key)
        except KeyError:raise HTTPException(404,'Copia inexistente')
        if record['source_type']!='account':raise HTTPException(400,'Esta asignación no es una copia de cuenta')
        try:runtime=store.get('runtime',key)
        except KeyError:runtime={}
        legs=list(runtime.get('copy_legs',{}).values()) or [runtime]
        return [dict(ref,source_ticket=ticket) for leg in legs for ticket,ref in leg.get('positions',{}).items()]

    @app.post('/api/copy/native-accounts')
    def register(req:NativeAccount):
        try:snapshot=store.get('ninja_snapshot',req.connection)
        except KeyError:raise HTTPException(409,'Conecta NinjaTrader primero')
        row=next((a for a in snapshot.get('accounts',[]) if a['name']==req.account),{})
        if time.time()-snapshot.get('at',0)>10 or not row.get('execution_allowed') or row.get('provider') not in ('Simulator','Playback'):
            raise HTTPException(409,'Cuenta Simulator/Playback conectada requerida')
        key='nt_'+hashlib.sha256((req.connection+':'+req.account).encode()).hexdigest()[:24]
        try:return store.get('account',key)
        except KeyError:pass
        return store.put('account',key,dict(id=key,name='NT8 · '+req.account,platform='NT8',connection=req.connection,
                         account_name=req.account,connection_mode='NT8',server='NinjaTrader',login=0,symbol_map={}))

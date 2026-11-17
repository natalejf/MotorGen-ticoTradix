"""PropPass bridge: ten explicit simulated accounts; one applied group per service."""
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime
from typing import Literal

from fastapi import Header,HTTPException,Request
from fastapi.responses import FileResponse,PlainTextResponse,JSONResponse
from pydantic import BaseModel,Field

from backend import copy_trading as store


SimAccount=Literal['Sim101','SimAccount2','SimAccount3','SimAccount4','SimAccount5','SimAccount6','SimAccount7','SimAccount8','SimAccount9','SimAccount10']


class AccountOverrides(BaseModel):
    lots:int|None=Field(default=None,ge=1,le=100)
    tp_usd:float|None=Field(default=None,gt=0,le=100000)
    sl_usd:float|None=Field(default=None,gt=0,le=100000)
    daily_profit_limit:float|None=Field(default=None,ge=0,le=100000)
    daily_loss_limit:float|None=Field(default=None,ge=0,le=100000)
    enabled:bool|None=None


class Settings(BaseModel):
    accounts:list[Literal['Sim101','SimAccount2','SimAccount3','SimAccount4','SimAccount5','SimAccount6','SimAccount7','SimAccount8','SimAccount9','SimAccount10']]=Field(default_factory=lambda:['Sim101'],min_length=1,max_length=5)
    symbol:str=Field(default='GC DEC26',pattern=r'^[A-Za-z0-9._ -]{1,40}$')
    timeframe_minutes:int=Field(default=1,ge=1,le=60)
    account_overrides:dict[SimAccount,AccountOverrides]=Field(default_factory=dict)
    lots:int=Field(default=1,ge=1,le=100)
    tp_usd:float=Field(default=100,gt=0,le=100000)
    sl_usd:float=Field(default=100,gt=0,le=100000)
    target:float=Field(default=500,gt=0,le=100000)
    max_loss:float=Field(default=500,gt=0,le=100000)
    daily_profit_limit:float=Field(default=200,ge=0,le=100000)
    daily_loss_limit:float=Field(default=200,ge=0,le=100000)
    start_balance:float=Field(default=50000,gt=0,le=10000000)
    exit_only_profit:bool=False
    time_filter:bool=False
    start_time:str=Field(default='09:30',pattern=r'^\d{2}:\d{2}$')
    end_time:str=Field(default='16:00',pattern=r'^\d{2}:\d{2}$')


class Group(BaseModel):
    name:str=Field(min_length=1,max_length=80)
    settings:Settings=Field(default_factory=Settings)


def required(key):
    try:return store.get('ninja_connection',key)
    except KeyError:raise HTTPException(404,'Conexión NinjaTrader inexistente')


def install_routes(app):
    @app.middleware('http')
    async def local_controls(request,call_next):
        if request.url.path.startswith('/api/ninja/'):
            origin=request.headers.get('origin')
            if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Control NinjaTrader solo desde esta aplicación'},status_code=403)
        return await call_next(request)

    @app.get('/api/ninja/status')
    def status():
        result=[]
        for connection in store.listing('ninja_connection'):
            try:snapshot=store.get('ninja_snapshot',connection['id'])
            except KeyError:snapshot={}
            try:applied=store.get('ninja_config_ack',connection['id'])
            except KeyError:applied={}
            with store.connect() as db:
                rows=db.execute("SELECT body FROM records WHERE kind='ninja_command' AND json_extract(body,'$.connection')=? ORDER BY rowid DESC LIMIT 20",(connection['id'],)).fetchall()
            result.append(dict(id=connection['id'],name=connection['name'],account='Sim101',
                connected=time.time()-snapshot.get('at',0)<10,snapshot=snapshot,active_group_id=applied.get('group_id'),applied_settings=applied.get('settings'),
                commands=[json.loads(r['body']) for r in rows]))
        return dict(platform='NinjaTrader 8',mode='SIM_ACCOUNTS_ONLY',copy_execution_enabled=False,
                    connections=result,groups=store.listing('ninja_group'))

    @app.post('/api/ninja/groups')
    def create_group(group:Group):
        key=uuid.uuid4().hex
        return store.put('ninja_group',key,dict(id=key,**group.model_dump()))

    @app.put('/api/ninja/groups/{key}')
    def update_group(key:str,group:Group):
        try:store.get('ninja_group',key)
        except KeyError:raise HTTPException(404,'Grupo inexistente')
        return store.put('ninja_group',key,dict(id=key,**group.model_dump()))

    @app.delete('/api/ninja/groups/{key}')
    def delete_group(key:str):
        for connection in store.listing('ninja_connection'):
            try:
                snapshot=store.get('ninja_snapshot',connection['id']);applied=store.get('ninja_config_ack',connection['id'])
            except KeyError:continue
            if applied.get('group_id')==key and (snapshot.get('master_enabled') or snapshot.get('position_quantity')):
                raise HTTPException(409,'Pausa y espera a estar flat antes de retirar el grupo aplicado')
        with store.connect() as db:db.execute("DELETE FROM records WHERE kind='ninja_group' AND id=?",(key,))
        return {'deleted':True}

    @app.post('/api/ninja/connections')
    async def create():
        key=uuid.uuid4().hex;token=secrets.token_urlsafe(32)
        store.put('ninja_connection',key,dict(id=key,name='Servicio Candle · simulación',
                  hash=hashlib.sha256(token.encode()).hexdigest(),created=time.time()))
        return dict(id=key,token=token,url='http://127.0.0.1:8000',account='Sim101')

    @app.get('/api/ninja/download')
    def download():
        return FileResponse(store.ROOT/'ninjatrader'/'StratixCandleService.cs',filename='StratixCandleService.cs')

    def enqueue(key,action,settings=None,group_id=None,account_name=None):
        required(key)
        if action not in ('configure','start','pause','reset','close-stop','account_pause','account_resume'):raise HTTPException(400,'Acción no admitida')
        try:snapshot=store.get('ninja_snapshot',key)
        except KeyError:snapshot={}
        if time.time()-snapshot.get('at',0)>10 or not snapshot.get('realtime') or not snapshot.get('account_available'):
            raise HTTPException(409,'Conecta el AddOn de NinjaTrader con sus cuentas simuladas')
        if action!='pause' and snapshot.get('kind')!='candle_service_v1':
            raise HTTPException(409,'Retira el controlador del gráfico y carga el AddOn sin interfaz')
        if action in ('configure','start','reset') and snapshot.get('position_quantity',0):
            raise HTTPException(409,'Configura/activa con Sim101 sin posiciones en este instrumento')
        if action in ('configure','reset') and snapshot.get('master_enabled'):
            raise HTTPException(409,'Pausa entradas y espera confirmación antes de configurar')
        with store.connect() as db:
            pending=db.execute("SELECT 1 FROM records WHERE kind='ninja_command' AND json_extract(body,'$.connection')=? AND json_extract(body,'$.state') IN ('QUEUED','DELIVERED') AND json_extract(body,'$.expires')>?",(key,time.time())).fetchone()
        if pending:raise HTTPException(409,'Espera la confirmación del comando anterior')
        if action=='start':
            try:applied=store.get('ninja_config_ack',key)
            except KeyError:applied={}
            if applied.get('instance')!=snapshot.get('instance'):
                raise HTTPException(409,'Aplica y confirma primero la configuración de esta instancia')
            if group_id and applied.get('group_id')!=group_id:raise HTTPException(409,'El grupo seleccionado todavía no está aplicado')
            if not snapshot.get('data_ready'):raise HTTPException(409,'Esperando ticks recientes del instrumento')
        params=(settings or Settings()).model_dump() if action in ('configure','reset','close-stop') else {}
        if action in ('account_pause','account_resume'):
            try:applied=store.get('ninja_config_ack',key)
            except KeyError:applied={}
            if applied.get('instance')!=snapshot.get('instance') or account_name not in applied.get('settings',{}).get('accounts',[]):
                raise HTTPException(409,'La cuenta no pertenece al grupo aplicado en esta instancia')
            params={'account':account_name}
        if 'accounts' in params:
            available={a['name'] for a in snapshot.get('accounts',[]) if isinstance(a,dict) and isinstance(a.get('name'),str)}
            if set(params['accounts'])-available:raise HTTPException(409,'Una cuenta del grupo no está disponible en NinjaTrader')
            params['accounts']=list(dict.fromkeys(params['accounts']))
        if params.get('exit_only_profit'):
            raise HTTPException(422,'ExitOnlyInProfit está declarado en el archivo pero no implementa una regla de salida; no se habilita desde la web')
        for field in ('start_time','end_time'):
            if field in params:
                try:datetime.strptime(params[field],'%H:%M')
                except ValueError:raise HTTPException(422,'Horario no válido')
        value=dict(id=uuid.uuid4().hex,connection=key,instance=snapshot['instance'],action=action,
                   settings=params,group_id=group_id,state='QUEUED',created=time.time(),expires=time.time()+20)
        return store.put('ninja_command',value['id'],value)

    @app.post('/api/ninja/connections/{key}/{action}')
    def command(key:str,action:str,settings:Settings|None=None):return enqueue(key,action,settings)

    @app.post('/api/ninja/connections/{key}/accounts/{account_name}/{action}')
    def account_control(key:str,account_name:SimAccount,action:Literal['pause','resume']):
        return enqueue(key,'account_'+action,account_name=account_name)

    @app.post('/api/ninja/connections/{key}/groups/{group_id}/{action}')
    def group_control(key:str,group_id:str,action:str):
        try:group=store.get('ninja_group',group_id)
        except KeyError:raise HTTPException(404,'Grupo inexistente')
        if action=='apply':return enqueue(key,'configure',Settings(**group['settings']),group_id)
        if action=='reset':return enqueue(key,'reset',Settings(**group['settings']),group_id)
        if action=='close-stop':
            try:applied=store.get('ninja_config_ack',key)
            except KeyError:raise HTTPException(409,'No hay grupo aplicado')
            if applied.get('group_id')!=group_id:raise HTTPException(409,'El grupo no está aplicado')
            return enqueue(key,'close-stop',Settings(**applied['settings']),group_id)
        if action=='start':return enqueue(key,'start',group_id=group_id)
        raise HTTPException(400,'Acción de grupo no admitida')

    @app.post('/api/ninja/bridge/{key}/pulse',response_class=PlainTextResponse)
    async def pulse(key:str,request:Request,x_stratix_key:str=Header(default='')):
        connection=required(key)
        if not hmac.compare_digest(connection['hash'],hashlib.sha256(x_stratix_key.encode()).hexdigest()):
            raise HTTPException(401,'Clave de conector inválida')
        body=await request.body()
        if len(body)>16000:raise HTTPException(413,'Pulso demasiado grande')
        try:value=json.loads(body)
        except (ValueError,UnicodeError):raise HTTPException(422,'Pulso JSON inválido')
        if not isinstance(value,dict) or value.get('account')!='Sim101':raise HTTPException(422,'Primera versión limitada a Sim101')
        try:json.dumps(value,allow_nan=False)
        except ValueError:raise HTTPException(422,'Valores no finitos en pulso')
        instance=value.get('instance','')
        if not isinstance(instance,str) or not 1<=len(instance)<=64:raise HTTPException(422,'Instancia inválida')
        for flag in ('realtime','account_available','master_enabled'):
            if type(value.get(flag)) is not bool:raise HTTPException(422,'Estado de conector inválido')
        if type(value.get('position_quantity')) is not int or value['position_quantity']<0:raise HTTPException(422,'Posición inválida')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute("SELECT body FROM records WHERE kind='ninja_snapshot' AND id=?",(key,)).fetchone()
            previous=json.loads(old['body']) if old else {}
            if previous.get('instance')!=instance and time.time()-previous.get('at',0)<10:
                raise HTTPException(409,'Esta conexión ya pertenece a otra instancia nativa activa')
            db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)',('ninja_snapshot',key,json.dumps(dict(value,at=time.time()),allow_nan=False)))
        ack=value.get('last_ack')
        if isinstance(ack,str) and ack:
            try:cmd=store.get('ninja_command',ack)
            except KeyError:cmd={}
            if cmd.get('connection')==key and cmd.get('instance')==instance and cmd.get('state')=='DELIVERED':
                cmd.update(state='APPLIED' if value.get('ack_status')=='APPLIED' else 'REJECTED',
                           detail=str(value.get('ack_detail',''))[:500],acked=time.time())
                store.put('ninja_command',ack,cmd)
                if cmd['state']=='APPLIED' and cmd['action'] in ('configure','reset'):
                    store.put('ninja_config_ack',key,dict(instance=instance,settings=cmd['settings'],group_id=cmd.get('group_id')))
                if cmd['state']=='APPLIED' and cmd['action'] in ('account_pause','account_resume'):
                    try:
                        applied=store.get('ninja_config_ack',key);group=store.get('ninja_group',applied['group_id'])
                        name=cmd['settings']['account'];enabled=cmd['action']=='account_resume'
                        group['settings'].setdefault('account_overrides',{}).setdefault(name,{})['enabled']=enabled
                        applied['settings'].setdefault('account_overrides',{}).setdefault(name,{})['enabled']=enabled
                        store.put('ninja_group',group['id'],group);store.put('ninja_config_ack',key,applied)
                    except (KeyError,TypeError):pass
        with store.connect() as db:
            rows=db.execute("SELECT id,body FROM records WHERE kind='ninja_command' AND json_extract(body,'$.connection')=? AND json_extract(body,'$.state')='QUEUED' ORDER BY rowid LIMIT 10",(key,)).fetchall()
            for row in rows:
                cmd=json.loads(row['body'])
                if cmd['expires']<time.time() or cmd['instance']!=instance:
                    cmd['state']='EXPIRED';db.execute("UPDATE records SET body=? WHERE kind='ninja_command' AND id=?",(json.dumps(cmd),cmd['id']));continue
                cmd['state']='DELIVERED'
                changed=db.execute("UPDATE records SET body=? WHERE kind='ninja_command' AND id=? AND body=?",(json.dumps(cmd),cmd['id'],row['body'])).rowcount
                if not changed:continue
                def wire(v):return ','.join(v) if isinstance(v,list) else '1' if v is True else '0' if v is False else str(v)
                fields=[k+'='+wire(v) for k,v in cmd['settings'].items() if k!='account_overrides']
                fields += [f'{field}:{account}='+wire(v) for account,overrides in cmd['settings'].get('account_overrides',{}).items()
                           for field,v in overrides.items() if v is not None]
                return '|'.join([cmd['id'],instance,str(int(cmd['expires'])),cmd['action']]+fields)
        return ''

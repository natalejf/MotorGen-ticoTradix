"""Discover connected NT8 accounts; current execution tests require local simulators."""
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime
from typing import Literal,Annotated

from fastapi import Header,HTTPException,Request
from fastapi.responses import FileResponse,PlainTextResponse,JSONResponse
from pydantic import BaseModel,Field,StringConstraints

from backend import copy_trading as store


AccountName=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=100,pattern=r'^[^|,=:\r\n]+$')]


class AccountOverrides(BaseModel):
    lots:int|None=Field(default=None,ge=1,le=100)
    tp_usd:float|None=Field(default=None,gt=0,le=100000)
    sl_usd:float|None=Field(default=None,gt=0,le=100000)
    daily_profit_limit:float|None=Field(default=None,ge=0,le=100000)
    daily_loss_limit:float|None=Field(default=None,ge=0,le=100000)
    enabled:bool|None=None


class Settings(BaseModel):
    accounts:list[AccountName]=Field(default_factory=list,min_length=1,max_length=200)
    symbol:str=Field(default='GC DEC26',pattern=r'^[A-Za-z0-9._ -]{1,40}$')
    timeframe_minutes:int=Field(default=1,ge=1,le=60)
    account_overrides:dict[AccountName,AccountOverrides]=Field(default_factory=dict)
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
    settings:Settings


class EvaluationAuthorization(BaseModel):
    accounts:list[AccountName]=Field(default_factory=list,max_length=200)


def required(key):
    try:return store.get('ninja_connection',key)
    except KeyError:raise HTTPException(404,'Conexión NinjaTrader inexistente')


def visible_accounts(snapshot):
    # NT8 Account.All also contains internal backtest/playback placeholders.
    # Newer telemetry can explicitly report connectivity; legacy live pulses
    # cannot establish that the playback placeholder is connected.
    rows=[]
    for account in snapshot.get('accounts',[]):
        if not isinstance(account,dict) or not account.get('name'):continue
        if account['name'].casefold()=='backtest':continue
        if account.get('provider')=='Playback' and account.get('native_connection_status')!='Connected':continue
        if account.get('connected') is False:continue
        if account.get('status') in ('PASS','BURNED') or account.get('daily_status') in ('TARGET_REACHED','LOSS_LIMIT_REACHED'):
            account=dict(account,enabled=False)
        rows.append(account)
    return rows


def install_routes(app,namespace='ninja',settings_model=Settings,group_model=Group):
    from backend.namespaced_store import NamespacedStore
    store=globals()['store'] if namespace=='ninja' else NamespacedStore(namespace)
    Settings=settings_model;Group=group_model;prefix='/api/'+namespace
    def required(key):
        try:return store.get('ninja_connection',key)
        except KeyError:raise HTTPException(404,'Conexión inexistente')
    @app.middleware('http')
    async def local_controls(request,call_next):
        if request.url.path.startswith(prefix+'/'):
            origin=request.headers.get('origin')
            if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Control NinjaTrader solo desde esta aplicación'},status_code=403)
        return await call_next(request)

    @app.get(prefix+'/status')
    def status():
        result=[]
        for connection in store.listing('ninja_connection'):
            try:snapshot=store.get('ninja_snapshot',connection['id'])
            except KeyError:snapshot={}
            snapshot=dict(snapshot,accounts=visible_accounts(snapshot))
            maps={m['account']:m['symbol_map'] for m in store.listing('ninja_symbol_map') if m['connection']==connection['id']}
            snapshot['accounts']=[dict(a,symbol_map=maps.get(a['name'],{})) for a in snapshot['accounts']]
            queue_state=queue.get(connection['id'])
            try:applied=store.get('ninja_config_ack',connection['id'])
            except KeyError:applied={}
            with store.connect() as db:
                rows=db.execute("SELECT body FROM records WHERE kind='ninja_command' AND json_extract(body,'$.connection')=? ORDER BY rowid DESC LIMIT 20",(connection['id'],)).fetchall()
            result.append(dict(id=connection['id'],name=connection['name'],account=None,
                connected=time.time()-snapshot.get('at',0)<10,snapshot=snapshot,active_group_id=applied.get('group_id'),applied_settings=applied.get('settings'),
                queue=queue_state,commands=[json.loads(r['body']) for r in rows]))
        return dict(platform='NinjaTrader 8',mode='EXPLICIT_EVALUATION_ALLOWLIST',copy_execution_enabled=False,
                    connections=result,groups=store.listing('ninja_group'))

    @app.post(prefix+'/groups')
    def create_group(group:Group):
        key=uuid.uuid4().hex
        return store.put('ninja_group',key,dict(id=key,**group.model_dump()))

    @app.put(prefix+'/groups/{key}')
    def update_group(key:str,group:Group):
        try:store.get('ninja_group',key)
        except KeyError:raise HTTPException(404,'Grupo inexistente')
        res=queue.update_template(dict(id=key,**group.model_dump()))
        # Si el conector está pausado con este grupo aplicado, reenviar configure con los nuevos parámetros
        for conn in store.listing('ninja_connection'):
            if conn.get('id'):
                try: snap=store.get('ninja_snapshot',conn['id'])
                except KeyError: snap={}
                try: applied=store.get('ninja_config_ack',conn['id'])
                except KeyError: applied={}
                if applied.get('group_id')==key and not snap.get('master_enabled'):
                    queue.enqueue(conn['id'],'configure',group.settings,group_id=key,from_queue=True)
        return res

    @app.delete(prefix+'/groups/{key}')
    def delete_group(key:str):
        # 1. Limpiar de cualquier cola de ejecución para no bloquear la eliminación
        with store.connect() as db:
            queue_rows = db.execute("SELECT id, body FROM records WHERE kind='ninja_queue'").fetchall()
        for q_row in queue_rows:
            q_id = q_row['id']
            try:
                pending = json.loads(q_row['body'])
            except Exception:
                continue
            items = pending.get('items', [])
            if any(i.get('group_id') == key for i in items):
                new_items = [i for i in items if i.get('group_id') != key]
                pending['items'] = new_items
                if not new_items:
                    pending['state'] = 'STOPPED'
                    pending['index'] = 0
                else:
                    pending['index'] = min(pending.get('index', 0), max(0, len(new_items) - 1))
                store.put('ninja_queue', q_id, pending)

        # 2. Verificar conexiones activas: solo bloquear si hay posición de mercado abierta en vivo
        for connection in store.listing('ninja_connection'):
            c_id = connection.get('id')
            if not c_id:
                continue
            try:
                snapshot = store.get('ninja_snapshot', c_id)
            except KeyError:
                snapshot = {}
            try:
                applied = store.get('ninja_config_ack', c_id)
            except KeyError:
                applied = {}
            if applied.get('group_id') == key:
                is_live = bool(snapshot.get('master_enabled') and snapshot.get('position_quantity', 0) != 0)
                if is_live:
                    raise HTTPException(409, 'Pausa el servicio y cierra las posiciones abiertas antes de eliminar el grupo activo.')
                applied['group_id'] = None
                store.put('ninja_config_ack', c_id, applied)

        with store.connect() as db:
            db.execute("DELETE FROM records WHERE kind='ninja_group' AND id=?", (key,))
        return {'deleted': True}

    @app.post(prefix+'/connections')
    async def create(new_device:bool=False):
        if store.listing('ninja_connection') and not new_device:
            raise HTTPException(409,'Ya hay un vínculo guardado. Abre NinjaTrader para reutilizarlo; crea otro vínculo solo para otro equipo.')
        key=uuid.uuid4().hex;token=secrets.token_urlsafe(32)
        store.put('ninja_connection',key,dict(id=key,name=('PropPass' if namespace=='ninja' else 'RocketPass')+' · NinjaTrader',
                  hash=hashlib.sha256(token.encode()).hexdigest(),token=token,created=time.time()))
        return dict(id=key,token=token,url='http://127.0.0.1:8000',account='Sim101')

    @app.post(prefix+'/auto-link')
    async def auto_link():
        import os, shutil
        from pathlib import Path
        localapp = os.environ.get('LOCALAPPDATA')
        if not localapp:
            raise HTTPException(400, 'No se encontró la variable LOCALAPPDATA')
        folder_name = 'RocketPass' if namespace == 'rocket' else 'NinjaTrader'
        key_filename = 'RocketBridge.key' if namespace == 'rocket' else 'CandleBridge.key'
        target_dir = Path(localapp) / 'Stratix' / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        key_path = target_dir / key_filename

        conns = store.listing('ninja_connection')
        if conns:
            conn = conns[0]
            token = conn.get('token') or secrets.token_urlsafe(32)
            conn['token'] = token
            conn['hash'] = hashlib.sha256(token.encode()).hexdigest()
            store.put('ninja_connection', conn['id'], conn)
            cid = conn['id']
        else:
            cid = uuid.uuid4().hex
            token = secrets.token_urlsafe(32)
            conn = dict(id=cid, name=('PropPass' if namespace=='ninja' else 'RocketPass')+' · NinjaTrader',
                        hash=hashlib.sha256(token.encode()).hexdigest(), token=token, created=time.time())
            store.put('ninja_connection', cid, conn)

        key_path.write_text(f"{cid}\n{token}\n", encoding='utf-8')

        addon_name = 'RocketPassService.cs' if namespace == 'rocket' else 'StratixCandleService.cs'
        source_addon = store.ROOT / 'ninjatrader' / addon_name
        addon_dest_installed = None
        user_home = Path(os.path.expanduser('~'))
        candidate_dirs = [
            user_home / 'OneDrive' / 'Documentos' / 'NinjaTrader 8' / 'bin' / 'Custom' / 'AddOns',
            user_home / 'Documentos' / 'NinjaTrader 8' / 'bin' / 'Custom' / 'AddOns',
            user_home / 'Documents' / 'NinjaTrader 8' / 'bin' / 'Custom' / 'AddOns'
        ]
        for cdir in candidate_dirs:
            if cdir.exists() and source_addon.exists():
                dest = cdir / addon_name
                shutil.copy2(source_addon, dest)
                addon_dest_installed = str(dest)
                break

        return dict(ok=True, id=cid, key_file=str(key_path), addon_installed=addon_dest_installed,
                    message='Vinculación automática completada exitosamente en este equipo.')

    @app.get(prefix+'/download')
    def download():
        filename='StratixCandleService.cs' if namespace=='ninja' else 'RocketPassService.cs'
        return FileResponse(store.ROOT/'ninjatrader'/filename,filename=filename)

    def enqueue(key,action,settings=None,group_id=None,account_name=None,from_queue=False):
        required(key)
        q=queue.get(key)
        if not from_queue and q and q['state']=='RUNNING' and action in ('configure','reset','start'):
            raise HTTPException(409,'Hay una cola activa: no se puede saltar ni reiniciar el grupo actual')
        if not from_queue and action in ('pause','close-stop','release'):queue.pause(key)
        if action not in ('configure','start','pause','reset','close-stop','account_pause','account_resume','authorize-evaluation','release'):raise HTTPException(400,'Acción no admitida')
        try:snapshot=store.get('ninja_snapshot',key)
        except KeyError:snapshot={}
        snapshot=dict(snapshot,accounts=visible_accounts(snapshot))
        if namespace=='rocket' and action in ('configure','reset','start') and snapshot.get('version')!='1.9.0-vote40':
            raise HTTPException(409,'Actualiza RocketPass a 1.9.0-vote40 para usar cierre M5 frente a conteo de 40 velas')
        if action in ('authorize-evaluation','release') and snapshot.get('version') not in ('1.7.0-pending','1.8.0-ema20','1.9.0-vote40'):
            raise HTTPException(409,'Actualiza el AddOn a 1.7.0-pending para autorizar o liberar cuentas')
        if time.time()-snapshot.get('at',0)>10 or not snapshot.get('realtime') or not snapshot.get('account_available'):
            raise HTTPException(409,'Conecta el AddOn de NinjaTrader y sus cuentas')
        if action!='pause' and snapshot.get('kind')!='candle_service_v1':
            raise HTTPException(409,'Retira el controlador del gráfico y carga el AddOn sin interfaz')
        if action in ('configure','reset') and snapshot.get('position_quantity',0):
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
            if not applied.get('settings',{}).get('accounts'):
                raise HTTPException(409,'Aplica un grupo antes de activar entradas')
            selected=set(applied['settings']['accounts'])
            if any(a.get('position_quantity',0) and (a['name'] not in selected or a.get('proppass_position_quantity')!=a['position_quantity']) for a in snapshot.get('accounts',[])):
                raise HTTPException(409,'No se reanuda una posición que no pertenece al grupo aplicado')
            if namespace=='rocket' and (applied['settings'].get('timeframe_minutes')!=5 or applied['settings'].get('trend_period')!=40):
                raise HTTPException(409,'Reaplica el grupo con M5 y conteo de 40 velas antes de reanudar')
            if group_id and applied.get('group_id')!=group_id:raise HTTPException(409,'El grupo seleccionado todavía no está aplicado')
            if not snapshot.get('data_ready'):raise HTTPException(409,'Esperando ticks recientes del instrumento')
        params=(settings or Settings()).model_dump() if action in ('configure','reset','close-stop','authorize-evaluation') else {}
        if action=='close-stop':
            if snapshot.get('version') not in ('1.5.3-portfolio','1.5.4-portfolio','1.6.0-copy','1.7.0-pending','1.8.0-ema20','1.9.0-vote40'):
                raise HTTPException(409,'Compila el AddOn actualizado: esta versión anterior no garantiza el cierre exclusivo de PropPass')
            try:applied=store.get('ninja_config_ack',key)
            except KeyError:raise HTTPException(409,'No hay grupo PropPass aplicado para cerrar')
            params=Settings(**applied['settings']).model_dump()
            group_id=applied.get('group_id')
        if action in ('account_pause','account_resume'):
            try:applied=store.get('ninja_config_ack',key)
            except KeyError:applied={}
            if applied.get('instance')!=snapshot.get('instance') or account_name not in applied.get('settings',{}).get('accounts',[]):
                raise HTTPException(409,'La cuenta no pertenece al grupo aplicado en esta instancia')
            row=next((a for a in snapshot.get('accounts',[]) if a.get('name')==account_name),{})
            if action=='account_resume' and (row.get('status') in ('PASS','BURNED') or row.get('daily_status') in ('TARGET_REACHED','LOSS_LIMIT_REACHED')):
                raise HTTPException(409,'Cuenta finalizada por target o stop; reinicia explícitamente su seguimiento')
            params={'account':account_name}
        if 'accounts' in params:
            if not params['accounts'] and action!='authorize-evaluation':params['accounts']=[a['name'] for a in snapshot.get('accounts',[]) if a.get('execution_allowed',True)][:1]
            if not params['accounts'] and action!='authorize-evaluation':raise HTTPException(409,'No hay cuentas disponibles para aplicar la configuración')
            available={a['name'] for a in snapshot.get('accounts',[]) if isinstance(a,dict) and isinstance(a.get('name'),str) and a.get('connected',True)}
            if set(params['accounts'])-available:raise HTTPException(409,'Una cuenta del grupo no está disponible en NinjaTrader')
            params['accounts']=list(dict.fromkeys(params['accounts']))
            rows={a['name']:a for a in snapshot.get('accounts',[]) if isinstance(a,dict) and 'name' in a}
            if action!='authorize-evaluation' and any(rows[n].get('execution_allowed') is False for n in params['accounts']):raise HTTPException(409,'Cuenta detectada, pero esta fase de pruebas solo ejecuta en simuladores locales')
        if params.get('exit_only_profit'):
            raise HTTPException(422,'ExitOnlyInProfit está declarado en el archivo pero no implementa una regla de salida; no se habilita desde la web')
        for field in ('start_time','end_time'):
            if field in params:
                try:datetime.strptime(params[field],'%H:%M')
                except ValueError:raise HTTPException(422,'Horario no válido')
        value=dict(id=uuid.uuid4().hex,connection=key,instance=snapshot['instance'],action=action,
                   settings=params,group_id=group_id,state='QUEUED',created=time.time(),expires=time.time()+20)
        return store.put('ninja_command',value['id'],value)

    from backend.ninja_queue import NinjaQueue
    queue=NinjaQueue(store,enqueue,Settings)
    queue.install(app,prefix)

    @app.post(prefix+'/connections/{key}/evaluation-accounts')
    def authorize_evaluation(key:str,req:EvaluationAuthorization):return enqueue(key,'authorize-evaluation',req)

    @app.post(prefix+'/connections/{key}/{action}')
    def command(key:str,action:str,settings:Settings|None=None):return enqueue(key,action,settings)

    @app.post(prefix+'/connections/{key}/accounts/{account_name}/{action}')
    def account_control(key:str,account_name:AccountName,action:Literal['pause','resume']):
        return enqueue(key,'account_'+action,account_name=account_name)

    @app.post(prefix+'/connections/{key}/groups/{group_id}/{action}')
    def group_control(key:str,group_id:str,action:str):
        try:group=store.get('ninja_group',group_id)
        except KeyError:raise HTTPException(404,'Grupo inexistente')
        q=queue.get(key)
        if action=='reset' and q and q['state'] not in ('COMPLETED','STOPPED') and q['items'][q['index']]['group_id']!=group_id:
            raise HTTPException(409,'No se reinicia otro grupo mientras el grupo actual está en curso')
        if action=='apply':return enqueue(key,'configure',Settings(**group['settings']),group_id)
        if action=='reset':return enqueue(key,'reset',Settings(**group['settings']),group_id)
        if action=='close-stop':
            try:applied=store.get('ninja_config_ack',key)
            except KeyError:raise HTTPException(409,'No hay grupo aplicado')
            if applied.get('group_id')!=group_id:raise HTTPException(409,'El grupo no está aplicado')
            return enqueue(key,'close-stop',Settings(**applied['settings']),group_id)
        if action=='start':return enqueue(key,'start',group_id=group_id)
        raise HTTPException(400,'Acción de grupo no admitida')

    @app.post(prefix+'/groups/{group_id}/reset-state')
    def reset_group_state(group_id:str):
        try:group=store.get('ninja_group',group_id)
        except KeyError:raise HTTPException(404,'Grupo inexistente')
        group_accounts=set(group.get('settings',{}).get('accounts',[]))
        for connection in store.listing('ninja_connection'):
            key=connection['id']
            q=queue.get(key)
            if q:
                changed=False
                for item in q.get('items',[]):
                    if item.get('group_id')==group_id:
                        item['state']='PENDING'
                        item.pop('completed_at',None)
                        changed=True
                if q.get('state')=='COMPLETED' and any(i.get('group_id')==group_id for i in q.get('items',[])):
                    q['state']='STOPPED'
                    q['phase']='READY'
                    q['detail']='Estado reiniciado; cola lista para nueva activación'
                    changed=True
                if changed:queue.save(key,q)
            try:
                snapshot=store.get('ninja_snapshot',key)
                if snapshot and 'accounts' in snapshot:
                    for a in snapshot['accounts']:
                        if a.get('name') in group_accounts:
                            a['status']='EN PROCESO'
                            a['daily_status']='EN PROCESO'
                            a['daily_pnl']=0.0
                            a['unrealized']=0.0
                            a['wins']=0
                            a['losses']=0
                            a['closed_trades']=0
                            a['enabled']=True
                            a['direction']='Flat'
                    store.put('ninja_snapshot',key,snapshot)
            except KeyError:pass
            try:enqueue(key,'reset',Settings(**group['settings']),group_id,from_queue=True)
            except Exception:pass
        settings=copy.deepcopy(group.get('settings',{}))
        for acc in group_accounts:
            if 'account_overrides' in settings and acc in settings['account_overrides']:
                settings['account_overrides'][acc]['enabled']=True
        group['settings']=settings
        group['pnl']=0.0
        store.put('ninja_group',group_id,group)
        return {'ok':True,'message':'Estado del grupo y cuentas reiniciado a neutral'}

    @app.post(prefix+'/bridge/{key}/pulse',response_class=PlainTextResponse)
    async def pulse(key:str,request:Request,x_stratix_key:str=Header(default='')):
        connection=required(key)
        if not hmac.compare_digest(connection['hash'],hashlib.sha256(x_stratix_key.encode()).hexdigest()):
            raise HTTPException(401,'Clave de conector inválida')
        body=await request.body()
        if len(body)>512000:raise HTTPException(413,'Pulso demasiado grande')
        try:value=json.loads(body)
        except (ValueError,UnicodeError):raise HTTPException(422,'Pulso JSON inválido')
        if not isinstance(value,dict) or value.get('kind') not in (None,'candle_service_v1'):raise HTTPException(422,'Servicio NinjaTrader inválido')
        if value.get('kind')=='candle_service_v1' and not isinstance(value.get('accounts'),list):raise HTTPException(422,'Cuentas inválidas')
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
        from backend import ninja_rpc
        if namespace=='ninja':
            ninja_rpc.accept_results(key,instance,value.get('engine_results',[]))
            from backend.ninja_execution import ensure_workers
            ensure_workers(key)
            from backend.cross_copy import ensure_observers
            ensure_observers(key)
        if isinstance(ack,str) and ack:
            try:cmd=store.get('ninja_command',ack)
            except KeyError:cmd={}
            if cmd.get('connection')==key and cmd.get('instance')==instance and cmd.get('state')=='DELIVERED':
                cmd.update(state='APPLIED' if value.get('ack_status')=='APPLIED' else 'REJECTED',
                           detail=str(value.get('ack_detail',''))[:500],acked=time.time())
                store.put('ninja_command',ack,cmd)
                if cmd['state']=='APPLIED' and cmd['action'] in ('configure','reset'):
                    store.put('ninja_config_ack',key,dict(instance=instance,settings=cmd['settings'],group_id=cmd.get('group_id')))
                if cmd['state']=='APPLIED' and cmd['action']=='release':
                    store.put('ninja_config_ack',key,dict(instance=instance,settings={'accounts':[]},group_id=None))
                    released=queue.get(key)
                    if released:
                        released.update(state='STOPPED',phase='RELEASED',detail='Cuentas liberadas; aplica un grupo para iniciar una nueva cola')
                        queue.save(key,released)
                if cmd['state']=='APPLIED' and cmd['action'] in ('account_pause','account_resume'):
                    try:
                        applied=store.get('ninja_config_ack',key);group=store.get('ninja_group',applied['group_id'])
                        name=cmd['settings']['account'];enabled=cmd['action']=='account_resume'
                        group['settings'].setdefault('account_overrides',{}).setdefault(name,{})['enabled']=enabled
                        applied['settings'].setdefault('account_overrides',{}).setdefault(name,{})['enabled']=enabled
                        store.put('ninja_group',group['id'],group);store.put('ninja_config_ack',key,applied)
                        queue.set_account_enabled(key,group['id'],name,enabled)
                    except (KeyError,TypeError):pass
        queue.step(key,value)
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
        return ninja_rpc.poll(key,instance) if namespace=='ninja' else ''

"""Persistent group queue. A group advances only after every account finishes flat."""
import copy
import threading
import time
from contextlib import ExitStack

from fastapi import HTTPException


class NinjaQueue:
    def __init__(self,store,enqueue,settings_model):
        self.store=store;self.enqueue=enqueue;self.settings_model=settings_model
        self.locks={}

    def get(self,key):
        try:return self.store.get('ninja_queue',key)
        except KeyError:return None

    def save(self,key,q):
        q['connection']=key
        q['updated_at']=time.time()
        return self.store.put('ninja_queue',key,q)

    def update_template(self,group):
        """Update group in store and in any pending or paused queues."""
        with self.store.connect() as db:
            keys=[r['id'] for r in db.execute("SELECT id FROM records WHERE kind='ninja_queue' ORDER BY id")]
        changes=[]
        with ExitStack() as stack:
            for key in keys:stack.enter_context(self.locks.setdefault(key,threading.Lock()))
            for key in keys:
                q=self.get(key)
                if not q or q['state'] in ('COMPLETED','STOPPED'):continue
                item=next((i for i in q['items'] if i['group_id']==group['id']),None)
                if not item:continue
                if item.get('state')=='COMPLETED':continue
                other={name for i in q['items'] if i is not item and i.get('state')!='COMPLETED' for name in i['settings']['accounts']}
                if other.intersection(group['settings']['accounts']):
                    raise HTTPException(409,'Estas cuentas pertenecen a otro grupo activo de la cola')
                item.update(name=group['name'],settings=copy.deepcopy(group['settings']))
                if q['state']=='PAUSED' or q['phase'] in ('ACTIVE','CONFIGURED','READY','APPLYING'):
                    q['phase']='READY'
                changes.append((key,q))
            result=self.store.put('ninja_group',group['id'],copy.deepcopy(group))
            for key,q in changes:self.save(key,q)
        return result

    def set_account_enabled(self,key,group_id,name,enabled):
        with self.locks.setdefault(key,threading.Lock()):
            q=self.get(key)
            if not q or q['state'] in ('COMPLETED','STOPPED'):return
            item=next((i for i in q['items'] if i['group_id']==group_id),None)
            if item and name in item['settings']['accounts']:
                item['settings'].setdefault('account_overrides',{}).setdefault(name,{})['enabled']=enabled
                self.save(key,q)

    def pause(self,key,reason='Pausa solicitada desde la web; no se cambia de grupo',code='MANUAL'):
        q=self.get(key)
        if q and q['state'] not in ('COMPLETED','STOPPED'):
            q['state']='PAUSED';q['detail']=reason
            q['pause_code']=code;q['paused_at']=time.time()
            history=q.setdefault('pause_history',[])
            history.append(dict(at=q['paused_at'],code=code,reason=reason))
            q['pause_history']=history[-20:]
            self.save(key,q)

    def add(self,key,group_id):
        try:
            self.store.get('ninja_connection',key)
            group=self.store.get('ninja_group',group_id)
            snapshot=self.store.get('ninja_snapshot',key)
        except KeyError:raise HTTPException(404,'Conexión o grupo inexistente')
        if time.time()-snapshot.get('at',0)>10:raise HTTPException(409,'Conecta NinjaTrader')
        q=self.get(key)
        if not q or q['state'] in ('COMPLETED','STOPPED'):
            q=dict(state='RUNNING',phase='READY',index=0,items=[],created_at=time.time(),instance=snapshot['instance'])
            # Adding a group never interrupts an existing running group.
            if snapshot.get('master_enabled'):
                try:applied=self.store.get('ninja_config_ack',key);current=self.store.get('ninja_group',applied['group_id'])
                except KeyError:raise HTTPException(409,'Pausa la asignación manual antes de crear la cola')
                q['items'].append(dict(group_id=current['id'],name=current['name'],settings=copy.deepcopy(applied['settings']),state='ACTIVE'))
                q['phase']='ACTIVE'
        existing=next((item for item in q['items'] if item['group_id']==group_id),None)
        if existing and existing['state']=='COMPLETED':raise HTTPException(409,'Grupo completado; reinicia su seguimiento explícitamente para repetirlo')
        if not existing:
            occupied={name for item in q['items'] if item.get('state') not in ('COMPLETED','STOPPED') for name in item['settings']['accounts']}
            if occupied.intersection(group['settings']['accounts']):raise HTTPException(409,'Una cuenta ya pertenece a otro grupo activo de esta cola')
            q['items'].append(dict(group_id=group_id,name=group['name'],settings=copy.deepcopy(group['settings']),state='PENDING'))
        if q['state']=='PAUSED' and q['items'][q['index']]['group_id']==group_id:
            try:applied=self.store.get('ninja_config_ack',key)
            except KeyError:applied={}
            same=(applied.get('instance')==snapshot['instance'] and applied.get('group_id')==group_id
                  and applied.get('settings')==q['items'][q['index']]['settings'])
            q.update(state='RUNNING',phase='CONFIGURED' if same else 'READY',instance=snapshot['instance'])
        q['detail']='Grupos en orden de activación; el actual se completa antes de avanzar'
        return self.save(key,q)

    def step(self,key,snapshot):
        lock=self.locks.setdefault(key,threading.Lock())
        if not lock.acquire(False):return
        try:self._step(key,snapshot)
        finally:lock.release()

    def _step(self,key,snapshot):
        q=self.get(key)
        if not q or q['state']!='RUNNING':return
        if q['instance']!=snapshot['instance']:
            self.pause(key,'La instancia de NinjaTrader cambió; reanudación explícita requerida','INSTANCE_CHANGED');return
        item=q['items'][q['index']]
        rows={a['name']:a for a in snapshot.get('accounts',[]) if isinstance(a,dict) and 'name' in a}
        accounts=[rows.get(name) for name in item['settings']['accounts']]
        available=all(a is not None and a.get('connected',True) for a in accounts)
        flat=available and all(not a.get('proppass_position_quantity',a.get('position_quantity'))
                               and not a.get('proppass_working_orders',a.get('working_orders')) for a in accounts)
        complete=flat and all(a.get('status') in ('PASS','BURNED') or a.get('daily_status') in ('TARGET_REACHED','LOSS_LIMIT_REACHED') for a in accounts)
        try:
            if q['phase'] in ('CONFIGURING','STARTING'):
                cmd=self.store.get('ninja_command',q['command_id'])
                if cmd['state'] in ('QUEUED','DELIVERED'):
                    if cmd['expires']<time.time():raise HTTPException(409,'Comando de cola vencido; no se reenvía')
                    return
                if cmd['state']!='APPLIED':raise HTTPException(409,cmd.get('detail','Comando de cola rechazado'))
                if q['phase']=='CONFIGURING':
                    # Restored PASS/SL accounts retain their results; never reset them.
                    q['phase']='CONFIGURED'
                else:
                    q['phase']='ACTIVE';item['state']='ACTIVE'
                self.save(key,q)
            if q['phase'] in ('ACTIVE','CONFIGURED') and complete:
                item.update(state='COMPLETED',completed_at=time.time())
                q['index']+=1
                if q['index']==len(q['items']):
                    q.update(state='COMPLETED',phase='DONE',detail='Todos los grupos completados')
                else:q.update(phase='READY',detail='Grupo completo y flat; preparando el siguiente')
                self.save(key,q);return
            if q['phase']=='READY':
                if not flat or snapshot.get('master_enabled'):
                    q['detail']='Esperando cuentas flat y entradas pausadas, sin saltar de grupo';self.save(key,q);return
                cmd=self.enqueue(key,'configure',self.settings_model(**item['settings']),item['group_id'],from_queue=True)
                item['state']='APPLYING';q.update(phase='CONFIGURING',command_id=cmd['id'])
                self.save(key,q);return
            if q['phase']=='CONFIGURED':
                if not snapshot.get('data_ready'):return
                cmd=self.enqueue(key,'start',group_id=item['group_id'],from_queue=True)
                q.update(phase='STARTING',command_id=cmd['id']);self.save(key,q);return
            if q['phase']=='ACTIVE' and not snapshot.get('master_enabled'):
                self.pause(key,snapshot.get('pause_reason') or 'El conector pausó las entradas sin informar causa; revisa su registro y versión',snapshot.get('pause_code') or 'NATIVE_PAUSE_UNSPECIFIED')
        except HTTPException as error:
            q.update(state='PAUSED',detail=str(error.detail));self.save(key,q)

    def install(self,app,prefix='/api/ninja'):
        @app.post(prefix+'/queues/{key}/groups/{group_id}')
        def activate(key:str,group_id:str):return self.add(key,group_id)

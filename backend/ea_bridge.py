"""Authenticated local EA transport. No broker credentials, no terminal auto-login."""
import hashlib
import hmac
import json
import secrets
import time
import uuid
from types import SimpleNamespace

from fastapi import Header, HTTPException, Request
from fastapi.responses import PlainTextResponse, FileResponse

from backend import copy_trading as store


class BridgeReadUnavailable(RuntimeError):
    """Only a read timed out; no market mutation is retried by this exception."""
    pass


def authorize(key, token):
    try:
        saved = store.get('ea_key', key)['hash']
    except KeyError:
        raise HTTPException(401, 'EA no vinculado')
    if not token or not hmac.compare_digest(saved, hashlib.sha256(token.encode()).hexdigest()):
        raise HTTPException(401, 'Clave EA inválida')


def ensure_ea_worker(key):
    account=store.get('account',key)
    if account.get('connection_mode')!='EA': return
    try:
        if store.get('worker_control',key).get('stop'): return
    except KeyError: pass
    now=time.time()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        active=db.execute('SELECT expires FROM leases WHERE account=?',(key,)).fetchone()
        if active and active['expires']>now: return
        launch=db.execute('SELECT body FROM records WHERE kind=? AND id=?',('ea_launch',key)).fetchone()
        if launch and now-json.loads(launch['body'])['at']<30: return
        db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)',('ea_launch',key,json.dumps({'at':now})))
    store.start_local_worker(key)


def install_routes(app):
    @app.get('/api/copy/ea/download')
    def download():
        return FileResponse(store.ROOT/'mt5'/'Stratix_Connector.mq5', filename='Stratix_Connector.mq5')

    @app.get('/api/copy/ea/download-ex5')
    def download_binary():
        return FileResponse(store.ROOT/'mt5'/'Stratix_Connector.ex5', filename='Stratix_Connector.ex5')

    @app.post('/api/copy/accounts/{key}/ea-key')
    def pairing(key: str):
        account = store.get('account', key)
        if any(d['account_id']==key and d['state']=='ACTIVE' for d in store.listing('deployment')):
            raise HTTPException(409, 'Pausa las asignaciones antes de vincular el EA')
        with store.connect() as db:
            lease = db.execute('SELECT expires FROM leases WHERE account=?', (key,)).fetchone()
        if lease and lease['expires']>time.time():
            raise HTTPException(409, 'Detén primero el conector actual')
        token = secrets.token_urlsafe(32)
        store.put('ea_key',key,{'hash':hashlib.sha256(token.encode()).hexdigest()})
        account['connection_mode']='EA'
        store.put('account',key,account)
        store.put('worker_control',key,{'stop':False})
        return dict(account_id=key,token=token,url='http://127.0.0.1:8000',download='/api/copy/ea/download')

    @app.get('/api/copy/ea/{key}/poll', response_class=PlainTextResponse)
    def poll(key: str, x_stratix_key: str = Header(default=''), log_events: bool=False, after_event_seq: int=-1):
        authorize(key,x_stratix_key)
        ensure_ea_worker(key)
        with store.connect() as db:
            rows=db.execute("SELECT r.body FROM ea_queue q JOIN records r ON r.kind='ea_command' AND r.id=q.id WHERE q.account=? AND q.state='QUEUED' ORDER BY q.created LIMIT 16",(key,)).fetchall()
        commands=[json.loads(row['body']) for row in rows]
        for command in commands:
            if time.time()-command['created']>12:
                command['state']='EXPIRED'
                store.put('ea_command',command['id'],command)
                continue
            # Delivered commands are never delivered again, including order_send.
            original=json.dumps(command,allow_nan=False)
            command['state']='DELIVERED'
            with store.connect() as db:
                changed=db.execute('UPDATE records SET body=? WHERE kind=? AND id=? AND body=?',
                    (json.dumps(command,allow_nan=False),'ea_command',command['id'],original)).rowcount
            if not changed:
                continue
            fields = [command['id'],command['method']]
            fields += [f'{k}={v}' for k,v in command['args'].items()]
            return '|'.join(fields)
        if log_events:
            def notice(seq,message):
                clean=str(message).replace('|','/').replace('\r',' ').replace('\n',' ')[:1400]
                return f'event_{seq}|log|seq={seq}|message={clean}'
            with store.connect() as db:
                if after_event_seq<0:
                    seq=db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE account=?',(key,)).fetchone()[0]
                else:
                    event=db.execute('SELECT seq,message FROM events WHERE account=? AND seq>? ORDER BY seq LIMIT 1',
                                     (key,after_event_seq)).fetchone()
                    if event:return notice(event['seq'],event['message'])
            if after_event_seq<0:
                sessions=[f'{d["name"]}: {d["state"]}' for d in store.listing('deployment')
                          if d['account_id']==key and d['state']!='STOPPED']
                return notice(seq,'Estado de asignaciones: '+('; '.join(sessions) or 'ningun algoritmo asignado'))
        return ''

    @app.post('/api/copy/ea/{key}/result/{command_id}')
    async def result(key: str, command_id: str, request: Request, x_stratix_key: str = Header(default='')):
        authorize(key,x_stratix_key)
        try:
            command=store.get('ea_command',command_id)
        except KeyError:
            raise HTTPException(404,'Comando inexistente')
        if command['account']!=key or command['state']!='DELIVERED':
            raise HTTPException(409,'Comando no vigente')
        body=await request.body()
        if len(body)>2_000_000:
            raise HTTPException(413,'Respuesta demasiado grande')
        command.update(state='DONE',result=json.loads(body))
        store.put('ea_command',command_id,command)
        return {'ok':True}


class EABroker:
    """MT5Worker adapter; calls are answered by the EA timer, never replayed."""
    ACCOUNT_TRADE_MODE_DEMO=0
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING=2
    POSITION_TYPE_BUY=ORDER_TYPE_BUY=0
    ORDER_TYPE_SELL=1
    TRADE_ACTION_DEAL=1
    TRADE_ACTION_PENDING=5
    TRADE_ACTION_SLTP=6
    TRADE_ACTION_REMOVE=8
    ORDER_FILLING_FOK=0
    ORDER_FILLING_IOC=1
    ORDER_FILLING_RETURN=2
    ORDER_TIME_GTC=0
    TRADE_RETCODE_DONE=10009
    TRADE_RETCODE_DONE_PARTIAL=10010
    TRADE_RETCODE_PLACED=10008
    TIMEFRAME_M30=30
    TIMEFRAME_H1=16385
    TIMEFRAME_H4=16388
    TIMEFRAME_D1=16408

    def __init__(self, account):
        self.account=account
        self.read_timeout=15.
        self.read_retries=1

    def rpc(self, method, **args):
        if any('|' in str(v) or '\n' in str(v) or '\r' in str(v) for v in args.values()):
            raise ValueError('Argumento EA inválido')
        attempts=1 if method=='order_send' else self.read_retries+1
        for attempt in range(attempts):
            try:return self._request(method,args)
            except BridgeReadUnavailable:
                if attempt+1==attempts:raise

    def _request(self,method,args):
        key=uuid.uuid4().hex
        store.put('ea_command',key,dict(id=key,account=self.account['id'],method=method,
                  args=args,state='QUEUED',created=time.time()))
        deadline=time.monotonic()+self.read_timeout
        while time.monotonic()<deadline:
            command=store.get('ea_command',key)
            if command['state']=='DONE':
                value=command['result']
                if method!='order_send':
                    with store.connect() as db:db.execute("DELETE FROM records WHERE kind='ea_command' AND id=?",(key,))
                if isinstance(value,dict) and 'error' in value:
                    raise RuntimeError(f'EA: {value["error"]}')
                return value
            time.sleep(.05)
        if method!='order_send':
            # Remove even a delivered read: a late response cannot mutate the broker.
            with store.connect() as db:db.execute("DELETE FROM records WHERE kind='ea_command' AND id=?",(key,))
            raise BridgeReadUnavailable(f'EA sin respuesta de lectura para {method}')
        raise RuntimeError(f'EA sin respuesta para {method}; no se reenvía el comando {key}')

    def account_info(self): return SimpleNamespace(**self.rpc('account_info'))
    def terminal_info(self): return SimpleNamespace(**self.rpc('terminal_info'))
    def positions_get(self): return [SimpleNamespace(**p) for p in self.rpc('positions_get')]
    def orders_get(self): return [SimpleNamespace(**p) for p in self.rpc('orders_get')]
    def history_deals_get(self,position):
        return [SimpleNamespace(**p) for p in self.rpc('history',position=position)]
    def symbol_select(self,symbol,selected): return self.rpc('symbol_select',symbol=symbol)
    def symbol_info(self,symbol): return SimpleNamespace(**self.rpc('symbol_info',symbol=symbol))
    def symbol_info_tick(self,symbol): return SimpleNamespace(**self.rpc('tick',symbol=symbol))
    def order_calc_profit(self,kind,symbol,volume,entry,sl):
        return self.rpc('profit',type=kind,symbol=symbol,volume=volume,price=entry,sl=sl)
    def order_check(self,request): return SimpleNamespace(**self.rpc('order_check',**request))
    def order_send(self,request):
        value=self.rpc('order_send',**request)
        return EAResult(**value)
    def copy_rates_from_pos(self,symbol,tf,start,count):
        return self.rpc('bars',symbol=symbol,timeframe=tf,start=start,count=count)
    def last_error(self): return 'Consultar registro Experts del EA'
    def initialize(self,*args,**kwargs): return True
    def shutdown(self): pass


class EAResult(SimpleNamespace):
    def _asdict(self): return vars(self)

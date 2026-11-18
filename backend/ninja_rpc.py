"""Authenticated NT8 RPC. Delivered mutations are never replayed."""
import time
import uuid
from types import SimpleNamespace
from backend import copy_trading as store
from backend.ea_bridge import EABroker,EAResult,BridgeReadUnavailable


def accept_results(key,instance,results):
    for item in results:
        if not isinstance(item,dict):continue
        try:command=store.get('ninja_engine_rpc',item.get('id',''))
        except KeyError:continue
        if command['connection']==key and command['instance']==instance and command['state']=='DELIVERED':
            command.update(state='DONE',result=item.get('value'));store.put('ninja_engine_rpc',command['id'],command)


def poll(key,instance):
    with store.connect() as db:
        rows=db.execute("SELECT id,body FROM records WHERE kind='ninja_engine_rpc' AND json_extract(body,'$.connection')=? AND json_extract(body,'$.state')='QUEUED' ORDER BY rowid LIMIT 20",(key,)).fetchall()
        import json
        for row in rows:
            c=json.loads(row['body'])
            if c['instance']!=instance or c['expires']<time.time():
                c['state']='EXPIRED';db.execute("UPDATE records SET body=? WHERE kind='ninja_engine_rpc' AND id=?",(json.dumps(c),c['id']));continue
            c['state']='DELIVERED';db.execute("UPDATE records SET body=? WHERE kind='ninja_engine_rpc' AND id=?",(json.dumps(c),c['id']))
            return '|'.join([c['id'],instance,str(int(c['expires'])),'engine','method='+c['method']]+[k+'='+str(v) for k,v in c['args'].items()])
    return ''


class NinjaBroker(EABroker):
    platform='NT8'
    def __init__(self,connection,account_name,session,symbol,magic,parent=None):
        self.connection=connection;self.account_name=account_name;self.session=session;self.symbol=symbol;self.magic=magic
        self.parent=parent or session
        self.cached=None;self.cache_at=0;self.history_cache={}

    def rpc(self,method,**args):
        for name,expected in dict(session=self.session,parent=self.parent,account=self.account_name,symbol=self.symbol,magic=self.magic).items():
            if name in args and args[name]!=expected:raise ValueError('La identidad de la sesión NT8 no puede cambiar')
        if any(any(char in str(v) for char in '|\r\n') for v in args.values()):raise ValueError('Argumento NT8 inválido')
        snapshot=store.get('ninja_snapshot',self.connection)
        if time.time()-snapshot.get('at',0)>10:raise BridgeReadUnavailable('NinjaTrader desconectado')
        key=uuid.uuid4().hex
        command=dict(id=key,connection=self.connection,instance=snapshot['instance'],method=method,
                     args={**dict(session=self.session,parent=self.parent,account=self.account_name,symbol=self.symbol,magic=self.magic),**args},
                     state='QUEUED',expires=time.time()+25,created=time.time())
        store.put('ninja_engine_rpc',key,command)
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            c=store.get('ninja_engine_rpc',key)
            if c['state']=='DONE':
                value=c['result']
                with store.connect() as db:db.execute("DELETE FROM records WHERE kind='ninja_engine_rpc' AND id=?",(key,))
                if isinstance(value,dict) and value.get('error'):raise RuntimeError('NT8: '+value['error'])
                return value
            if c['state']=='EXPIRED':raise BridgeReadUnavailable('RPC NT8 vencido sin entregar')
            time.sleep(.1)
        if method in ('state','bars','observe'):raise BridgeReadUnavailable('Lectura NT8 sin respuesta')
        raise RuntimeError('Resultado NT8 incierto; no se reenvía '+key)

    def state(self):
        if self.cached is None or time.monotonic()-self.cache_at>1:
            self.cached=self.rpc('state');self.cache_at=time.monotonic()
        return self.cached

    def invalidate(self):self.cached=None
    def account_info(self):
        s=self.state();return SimpleNamespace(balance=s['balance'],equity=s['equity'],currency='USD',trade_allowed=s['execution_allowed'],name=self.account_name)
    def terminal_info(self):return SimpleNamespace(connected=True,trade_allowed=True)
    def positions_get(self):return [SimpleNamespace(**p) for p in self.state()['positions']]
    def orders_get(self):return [SimpleNamespace(**p) for p in self.state()['orders']]
    def symbol_select(self,symbol,selected):return symbol==self.symbol
    def symbol_info(self,symbol):
        s=self.state();point=s['tick_size'];return SimpleNamespace(point=point,digits=8,volume_step=1,volume_min=1,volume_max=100,
            trade_stops_level=1,trade_freeze_level=0,expiration_mode=4,filling_mode=2,trade_exemode=2,point_value=s['point_value'])
    def symbol_info_tick(self,symbol):
        s=self.state();return SimpleNamespace(bid=s['bid'],ask=s['ask'],time=s['tick_time'])
    def order_calc_profit(self,kind,symbol,volume,entry,sl):return (sl-entry)*(1 if kind==0 else -1)*self.state()['point_value']*volume
    def order_check(self,request):
        qty=request.get('volume',1)
        if qty!=int(qty) or qty<1:return SimpleNamespace(retcode=1,comment='Contratos enteros requeridos')
        return SimpleNamespace(retcode=0)
    def order_send(self,request):
        value=self.rpc('mutate',**request);self.invalidate();return EAResult(**value)
    def history_deals_get(self,position):
        state=self.state();exit=state.get('last_exit')
        if not exit or state.get('position_ticket')!=position:return []
        reason=4 if exit['name'].startswith('STXG_SL_') else 5 if exit['name'].startswith('STXG_TP_') else 0
        return [SimpleNamespace(reason=reason,price=exit['price'],volume=exit['quantity'],stop_price=exit.get('stop_price'))]
    def copy_rates_from_pos(self,symbol,tf,start,count):
        minutes={30:30,16385:60,16388:240,16408:1440}[tf]
        old=self.history_cache.get(minutes)
        if old and time.monotonic()-old[0]<15:return old[1]
        value=self.rpc('bars',minutes=minutes,count=min(count,1000));self.history_cache[minutes]=(time.monotonic(),value);return value

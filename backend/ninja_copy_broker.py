"""One native ownership lease per copied order; shared parent owns the account."""
import uuid
import time
from backend import copy_trading as store
from backend.ninja_rpc import NinjaBroker


class NinjaCopyBroker(NinjaBroker):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.leg_cache={};self.combined=None;self.combined_at=0

    def legs(self):
        records=[r for r in store.listing('ninja_copy_leg') if r['parent']==self.parent and r['symbol']==self.symbol and r.get('state')!='RELEASED']
        for r in records:
            if r['id'] not in self.leg_cache:self.leg_cache[r['id']]=NinjaBroker(self.connection,self.account_name,r['id'],self.symbol,self.magic,parent=self.parent)
        return [self.leg_cache[r['id']] for r in records]

    def invalidate(self):
        super().invalidate();self.combined=None

    def rpc(self,method,**args):
        if method=='claim':args['copy_mode']=1
        if method=='release':
            for leg in self.legs():
                leg.rpc('release')
                record=store.get('ninja_copy_leg',leg.session);record['state']='RELEASED';store.put('ninja_copy_leg',leg.session,record)
        return super().rpc(method,**args)

    def state(self):
        if self.combined is not None and time.monotonic()-self.combined_at<1:return self.combined
        state=dict(super().state());positions=list(state['positions']);orders=list(state['orders'])
        for leg in self.legs():
            value=leg.state();positions.extend(value['positions']);orders.extend(value['orders'])
            if not value.get('execution_allowed',False):state.update(execution_allowed=False,fault=value.get('fault','Fallo en una copia'))
            record=store.get('ninja_copy_leg',leg.session)
            if (record.get('confirmed_at') and time.time()-record['confirmed_at']>5
                    and not value['positions'] and not value['orders'] and not value.get('fault')):
                leg.rpc('release');record['state']='RELEASED';store.put('ninja_copy_leg',leg.session,record)
        state.update(positions=positions,orders=orders)
        self.combined=state;self.combined_at=time.monotonic();return state

    def order_send(self,request):
        opening=request['action'] in (1,5) and not request.get('position')
        if opening:
            child=uuid.uuid5(uuid.UUID(self.parent),request['comment']).hex
            leg=NinjaBroker(self.connection,self.account_name,child,self.symbol,self.magic,parent=self.parent)
            self.leg_cache[child]=leg
            store.put('ninja_copy_leg',child,dict(id=child,parent=self.parent,symbol=self.symbol))
            leg.rpc('claim',copy_mode=1)
        else:
            ticket=request.get('position') or request.get('order')
            leg=None
            for candidate in self.legs():
                value=candidate.state()
                if any(p['ticket']==ticket for p in value['positions']+value['orders']):leg=candidate;break
            if leg is None:raise RuntimeError('No se encuentra la orden/posición propia NT8; no se envía a otra sesión')
        result=leg.order_send(request)
        if opening:
            record=store.get('ninja_copy_leg',leg.session);record['confirmed_at']=time.time();store.put('ninja_copy_leg',leg.session,record)
        self.invalidate();return result

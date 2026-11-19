"""Pending-order reconciliation. A fill never produces a second market entry."""
import hashlib
import json
import time
import uuid
from backend import copy_trading as store


def persist(d,runtime):
    if d.get('copy_source_symbol'):
        try:parent=store.get('runtime',d['id'])
        except KeyError:parent={}
        record=store.get('deployment',d['id'])
        index=next(i for i,item in enumerate(record['strategies']) if item['strategy']['symbol']==d['copy_source_symbol'])
        parent.setdefault('copy_legs',{})[str(index)]=runtime
        store.put('runtime',d['id'],parent)
    else:store.put('runtime',d['id'],runtime)


def synchronize_pending(worker,d,runtime,source,may_open):
    refs=runtime.setdefault('pending_copies',{})
    if 'orders' not in source:
        if refs:raise RuntimeError('Actualiza el conector master: faltan órdenes pendientes en la instantánea')
        return set()
    source_orders={str(o['ticket']):o for o in source['orders'] if o.get('type') in (2,3,4,5)
                   and (not d.get('copy_source_symbol') or o['symbol']==d['copy_source_symbol'])}
    baseline=runtime.setdefault('baseline_pending',list(source_orders))
    if not may_open:runtime['baseline_pending']=baseline=list(set(baseline).union(source_orders))
    positions=source['positions'];managed=set()
    local_orders=list(worker.mt5.orders_get() or [])
    local_positions=worker.positions()
    for key,ref in list(refs.items()):
        origin=source_orders.get(key)
        filled=next((p for p in positions if str(p.get('source_order',p.get('identifier',p['ticket'])))==key
                     or key in [str(x) for x in p.get('source_orders',[])]
                     or str(p['ticket'])==ref.get('source_position_ticket')),None)
        if filled:
            ref['source_position_ticket']=str(filled['ticket']);managed.add(str(filled['ticket']))
        local_order=next((o for o in local_orders if o.magic==d['magic'] and o.comment==ref['comment']),None)
        local=next((p for p in local_positions if p.magic==d['magic'] and p.comment==ref['comment']),None)
        if ref.get('terminal'):continue
        if origin is None and filled is None:
            if local_order:worker.send(d,f'{d["id"]}:pending-cancel:{key}:{local_order.ticket}',dict(action=8,order=int(local_order.ticket),symbol=local_order.symbol))
            if local:worker.close_position(d,local,reason='master-pending-cancelled')
            if not local_order and not local:ref['terminal']=True
            continue
        if local and filled:
            ref.update(target_ticket=local.ticket,target_identifier=getattr(local,'identifier',local.ticket),target_entry=local.price_open)
            runtime['positions'].setdefault(str(filled['ticket']),dict(ref,source_entry=filled['price_open'],initial_master_volume=filled['volume']))
            ref['linked']=True
            continue
        current=origin or filled
        if origin and local_order and not local and origin['volume']!=ref['initial_master_volume']:
            result=worker.send(d,f'{d["id"]}:pending-resize-cancel:{key}:{ref.get("generation",0)}',dict(action=8,order=int(local_order.ticket),symbol=local_order.symbol))
            if result and result.retcode==worker.mt5.TRADE_RETCODE_DONE:
                runtime.setdefault('pending_generations',{})[key]=ref.get('generation',0)+1
                del refs[key];source_orders[key]=dict(origin,time=time.time());persist(d,runtime)
            continue
        if local:
            # The destination filled first. Keep protection and follow cancellation;
            # never submit another entry while the source is still pending.
            if current.get('sl',0)>0 and current.get('tp',0)>0:
                sl,tp=project(ref,current['sl']),project(ref,current['tp'])
                worker.modify(d,local,sl,tp)
        elif local_order:
            price=project(ref,current['price_open']);sl=project(ref,current['sl']);tp=project(ref,current['tp'])
            info,_=worker.tick(local_order.symbol,d)
            if d.get('sl_tp_mode')=='CUSTOM':
                sign=1 if local_order.type in (2,4) else -1
                pip=info.point*(10 if info.digits in (3,5) else 1)
                sl=price-sign*d['custom_sl_pips']*pip;tp=price+sign*d['custom_tp_pips']*pip
            if getattr(worker.mt5,'platform','MT5')=='NT8':
                price,sl,tp=[round(x/info.point)*info.point for x in (price,sl,tp)]
            values=[round(x,info.digits) for x in (price,sl,tp)]
            expiry=int(current.get('expiration',0))
            if expiry!=getattr(local_order,'expiration',0) or any(abs(a-b)>=info.point*.5 for a,b in zip(values,(local_order.price_open,local_order.sl,local_order.tp))):
                desired=hashlib.sha256(json.dumps(values+[expiry,int(current.get('type_time',0))]).encode()).hexdigest()[:16]
                if desired!=ref.get('last_modify'):
                    ref.update(last_modify=desired,modify_revision=ref.get('modify_revision',0)+1);persist(d,runtime)
                worker.send(d,f'{d["id"]}:pending-modify:{key}:{ref["modify_revision"]}',dict(action=7,order=int(local_order.ticket),symbol=local_order.symbol,
                    price=values[0],sl=values[1],tp=values[2],type_time=int(current.get('type_time',0)),expiration=int(current.get('expiration',0))))
        else:
            if time.time()-ref.get('created_at',0)>10:ref['terminal']=True  # Respect manual/broker cancellation.
    if may_open:
        for key,origin in source_orders.items():
            if key in refs or key in baseline:continue
            if time.time()-origin.get('time',0)>d.get('max_order_age_seconds',30):continue
            allowed=d.get('symbol_whitelist',[]);mode=d.get('symbol_filter','WHITELIST')
            if allowed and ((mode=='WHITELIST' and origin['symbol'] not in allowed) or (mode=='BLACKLIST' and origin['symbol'] in allowed)):continue
            direction='BUY' if origin['type'] in (2,4) else 'SELL'
            if d.get('direction_filter','BOTH') not in ('BOTH',direction):continue
            custom=d.get('sl_tp_mode')=='CUSTOM'
            if not custom and (origin.get('sl',0)<=0 or origin.get('tp',0)<=0):continue
            symbol=d['symbol_map'].get(origin['symbol'],origin['symbol'])
            if d.get('cross_platform') and origin['symbol'] not in d['symbol_map']:continue
            anchor_source=anchor_target=0.
            translated=bool(d.get('cross_platform') or d.get('price_scale',1)!=1)
            if translated:
                quote=source.get('quotes',{}).get(origin['symbol'])
                if not quote or quote.get('bid',0)<=0 or quote.get('ask',0)<quote['bid']:raise RuntimeError('La master no publica cotización para convertir pendientes')
                _,tick=worker.tick(symbol,d,opening=True)
                anchor_source=(quote['bid']+quote['ask'])/2;anchor_target=(tick.bid+tick.ask)/2
            ref=dict(source_ticket=key,source_symbol=origin['symbol'],target_symbol=symbol,translated=translated,
                     anchor_source=anchor_source,anchor_target=anchor_target,price_scale=d.get('price_scale',1),
                     initial_master_volume=origin['volume'],source_entry=origin['price_open'])
            price,sl,tp=[project(ref,origin[k]) for k in ('price_open','sl','tp')]
            info,_=worker.tick(symbol,d)
            if custom:
                sign=1 if direction=='BUY' else -1
                pip=info.point*(10 if info.digits in (3,5) else 1)
                sl=price-sign*d['custom_sl_pips']*pip;tp=price+sign*d['custom_tp_pips']*pip
            if getattr(worker.mt5,'platform','MT5')=='NT8':price,sl,tp=[round(x/info.point)*info.point for x in (price,sl,tp)]
            generation=runtime.get('pending_generations',{}).get(key,0)
            action_key=f'{d["id"]}:pending-entry:{key}:{generation}'
            ref['generation']=generation
            ref.update(comment='STX'+uuid.uuid5(uuid.NAMESPACE_OID,action_key).hex[:20],created_at=time.time())
            refs[key]=ref;persist(d,runtime)
            result=worker.open_position(d,action_key,symbol,direction,sl,tp,source_volume=origin['volume'],source_equity=source.get('equity'),
                entry_order_type='LIMIT' if origin['type'] in (2,3) else 'STOP',entry_price=price,expiration=int(origin.get('expiration',0)))
            if result:
                ref.update(comment='STX'+uuid.uuid5(uuid.NAMESPACE_OID,action_key).hex[:20],target_order=result.order,
                           target_native_order_id=getattr(result,'native_order_id',None),target_entry=price,initial_local_volume=result.volume)
                refs[key]=ref
    return managed


def project(ref,price):
    if not ref.get('translated'):return price
    return ref['anchor_target']+(price-ref['anchor_source'])*ref['price_scale']

"""Shared rule engine with NT8 metadata/integer contracts; no native orders."""
import time
import numpy as np
import pytest
from backend import copy_trading as store
from backend.ninja_rpc import NinjaBroker
from backend.ninja_execution import NinjaWorker
from backend.strategy import Strategy,Condition
from test_copy_trading import isolated_store

MODES=['ATR_CLASSIC','PIPS_FIXED','PCT_EXIT','TRAILING_ATR','BREAKEVEN','STRUCTURE_SWING','TIME_EXIT','PARTIAL_TP','ATR_SMOOTHED']


class ControlledNative(NinjaBroker):
    def __init__(self):
        super().__init__('bridge','Sim101','a'*32,'MNQ DEC26',100000001)
        self.bid=27000.;self.opened=[];self.pending=[];self.sent=[];self.ticket=100
    def rpc(self,method,**args):
        if method=='state':return dict(balance=50000,equity=50000,execution_allowed=True,tick_size=.25,point_value=2,
            bid=self.bid,ask=self.bid+.25,tick_time=time.time(),positions=self.opened,orders=self.pending)
        if method=='bars':
            seconds=args['minutes']*60;end=int(time.time()//seconds)*seconds
            return [dict(time=end-(500-i)*seconds,open=26750+i*.5-.2,high=26750+i*.5+1,
                         low=26750+i*.5-1,close=26750+i*.5,tick_volume=100+i) for i in range(500)]
        if method=='mutate':
            self.sent.append(dict(args));action=args['action'];qty=args.get('volume',0)
            if action==5:
                self.ticket+=1;self.pending.append(dict(ticket=self.ticket,magic=args['magic'],symbol=args['symbol'],comment=args['comment'],
                    price_open=args['price'],sl=args['sl'],tp=args['tp']))
            elif action==8:self.pending=[o for o in self.pending if o['ticket']!=args['order']]
            elif action==6:
                for p in self.opened:
                    if p['ticket']==args['position']:p.update(sl=args['sl'],tp=args['tp'])
            elif args.get('position'):
                for p in self.opened:
                    if p['ticket']==args['position']:p['volume']-=qty
                self.opened=[p for p in self.opened if p['volume']>0]
            else:
                self.ticket+=1
                self.opened.append(dict(ticket=self.ticket,magic=args['magic'],symbol=args['symbol'],comment=args['comment'],
                    price_open=args['price'],type=args['type'],volume=qty,sl=args['sl'],tp=args['tp'],time=time.time()))
            return dict(retcode=10008 if action==5 else 10009,order=self.ticket,volume=qty,comment='controlled NT model')
        return {'ok':True}


def setup_case(direction,entry,mode):
    strategy=Strategy(strategy_id='controlled',symbol='NASDAQ',timeframe='30m',
        buy_conditions=[Condition('PRICE',{},'GREATER_THAN',target_value=0)] if direction=='BUY' else [],
        sell_conditions=[Condition('PRICE',{},'GREATER_THAN',target_value=0)] if direction=='SELL' else [],
        direction='LONG_ONLY' if direction=='BUY' else 'SHORT_ONLY',close_before_weekend=False,
        entry_order_type=entry,exit_mode=mode,sl_atr=3,tp_atr=6,partial_pct=50,max_bars=1,be_atr=.5,trail_atr=.5,partial_tp1_atr=.5)
    record=store.DeploymentRequest(name='controlled',account_id='native',source_type='strategy',source_id='controlled',
        symbol_map={'NASDAQ':'MNQ DEC26'},risk_percent=2,fixed_lot=2,max_lot=2,risk_mode='FIXED_LOT').model_dump()
    record.update(id='a'*32,connection='bridge',account_name='Sim101',instance='one',state='ACTIVE',magic=100000001,
                  strategies=[dict(strategy=strategy.to_dict(),weight=1)],uses_source_risk=False)
    store.put('deployment',record['id'],record)
    store.put('ninja_snapshot','bridge',dict(at=time.time(),instance='one',accounts=[dict(name='Sim101',provider='Simulator',execution_allowed=True)]))
    worker=NinjaWorker(record);worker.mt5=ControlledNative()
    return worker,record,worker.local_state(record),record['strategies'][0]


@pytest.mark.parametrize('direction',['BUY','SELL'])
@pytest.mark.parametrize('entry',['MARKET','LIMIT','STOP'])
@pytest.mark.parametrize('mode',MODES)
def test_all_entry_exit_pairs_use_native_contracts_and_preserve_protection(direction,entry,mode):
    worker,record,state,item=setup_case(direction,entry,mode)
    worker.algorithm(record,state,item,0,True)
    assert len(worker.mt5.sent)==1
    request=worker.mt5.sent[0]
    assert request['volume']==2 and request['symbol']=='MNQ DEC26'
    assert request['action']==(1 if entry=='MARKET' else 5)
    sign=1 if direction=='BUY' else -1
    assert (request['price']-request['sl'])*sign>0
    assert (request['tp']-request['price'])*sign>0
    assert np.isfinite([request['sl'],request['tp']]).all()
    worker.algorithm(record,state,item,0,True)
    assert sum(r['action'] in (1,5) and not r.get('position') for r in worker.mt5.sent)==1


@pytest.mark.parametrize('direction',['BUY','SELL'])
@pytest.mark.parametrize('mode',['TRAILING_ATR','BREAKEVEN','PARTIAL_TP','TIME_EXIT'])
def test_native_integer_contract_management_on_controlled_prices(direction,mode):
    worker,record,state,item=setup_case(direction,'MARKET',mode)
    worker.algorithm(record,state,item,0,True)
    original=worker.mt5.opened[0].copy()
    if mode=='TIME_EXIT':worker.mt5.opened[0]['time']-=1800
    else:worker.mt5.bid+=3 if direction=='BUY' else -3
    worker.mt5.invalidate()
    worker.algorithm(record,state,item,0,False)
    if mode=='TIME_EXIT':assert not worker.mt5.opened
    elif mode=='PARTIAL_TP':
        assert worker.mt5.opened[0]['volume']==1
        worker.mt5.invalidate();worker.algorithm(record,state,item,0,False)
        assert worker.mt5.opened[0]['volume']==1
    elif mode=='BREAKEVEN':assert worker.mt5.opened[0]['sl']==original['price_open']
    elif direction=='BUY':assert worker.mt5.opened[0]['sl']>original['sl']
    else:assert worker.mt5.opened[0]['sl']<original['sl']


@pytest.mark.parametrize('first_leg_unavailable',[False,True])
def test_portfolio_runs_distinct_symbols_and_close_stop_cleans_every_leg(first_leg_unavailable):
    worker,record,state,item=setup_case('BUY','MARKET','ATR_CLASSIC')
    other=dict(item,strategy=dict(item['strategy'],id='other',symbol='US30',buy_conditions=[],
               sell_conditions=item['strategy']['buy_conditions'],direction='SHORT_ONLY'))
    record.update(source_type='portfolio',symbol_map={'NASDAQ':'MNQ DEC26','US30':'MYM DEC26'},
                  strategies=[dict(item,weight=.5),dict(other,weight=.5)])
    store.put('deployment',record['id'],record)
    one=ControlledNative();two=ControlledNative();two.symbol='MYM DEC26';two.magic=record['magic']+1;two.ticket=200
    if first_leg_unavailable:
        def unavailable(*args):raise RuntimeError('Historical data unavailable')
        one.copy_rates_from_pos=unavailable
    worker.brokers=[one,two]
    worker.cycle()
    assert len(one.opened)==(0 if first_leg_unavailable else 1)
    assert len(two.opened)==1 and two.opened[0]['type']==1 and two.opened[0]['symbol']=='MYM DEC26'
    worker.cycle()
    assert len(two.opened)==1
    record['state']='CLOSING';store.put('deployment',record['id'],record)
    worker.cycle()
    assert not one.opened and not two.opened
    assert store.get('deployment',record['id'])['state']=='STOPPED'

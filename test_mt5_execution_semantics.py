"""Controlled price paths; never contacts MT5. Covers live-worker decisions."""
import time
from datetime import datetime,timezone

import pytest

from backend import copy_trading as store
from backend.ea_bridge import EABroker,BridgeReadUnavailable
from backend.mt5_worker import MT5Worker
from backend.strategy import Strategy,Condition
from test_copy_trading import account,deployment,isolated_store
from test_ea_diagnostic import DiagnosticBroker


class Broker(DiagnosticBroker):
    def symbol_info(self,symbol):
        value=super().symbol_info(symbol);value.expiration_mode=15
        return value


def strategy(**kwargs):
    return Strategy(buy_conditions=[Condition('PRICE',{},'GREATER_THAN',target_value=0)],
        sell_conditions=[],direction='LONG_ONLY',timeframe='30m',close_before_weekend=False,
        sizing_mode=kwargs.pop('sizing_mode','FIXED_LOT'),fixed_lot=.02,risk_per_trade_pct=.5,
        sl_atr=3,tp_atr=6,**kwargs)


@pytest.mark.parametrize('mode,cash,mult,expected',[
    ('FIXED_RISK',0,1,.09),('FIXED_RISK',0,2,.18),
    ('FIXED_CASH',2.3,1,.02),('FIXED_CASH',2.3,2,.04)])
def test_sizing_multiplier_changes_cash_budget(mode,cash,mult,expected):
    broker=Broker();worker=MT5Worker(broker,account());d=deployment()
    d.update(strategy_sizing_mode=mode,strategy_risk_multiplier=mult,strategy_cash_risk=cash,risk_percent=.1)
    result=worker.open_position(d,'deploy1:sizing','EURUSD','BUY',1.099,1.103)
    assert result.volume==expected


@pytest.mark.parametrize('direction,entry,kind',[
    ('BUY','LIMIT',2),('SELL','LIMIT',3),('BUY','STOP',4),('SELL','STOP',5)])
def test_normal_algorithm_pending_orders_expire_and_do_not_duplicate(direction,entry,kind):
    broker=Broker();worker=MT5Worker(broker,account());d=deployment();d['uses_source_risk']=True
    s=strategy(entry_order_type=entry)
    if direction=='SELL':s.buy_conditions,s.sell_conditions=[],s.buy_conditions;s.direction='SHORT_ONLY'
    state=worker.local_state(d);item={'strategy':s.to_dict(),'weight':1}
    worker.algorithm(d,state,item,0,True)
    assert broker.sent[0]['type']==kind
    assert broker.sent[0]['type_time']==2 and broker.sent[0]['expiration']>time.time()
    worker.algorithm(d,state,item,0,True)
    assert len(broker.sent)==1
    state['bars'][f'{d["id"]}:algo:0']='old-bar'
    worker.algorithm(d,state,item,0,True)
    assert not broker.pending and broker.sent[-1]['action']==8


def test_daily_entry_cap_applies_after_closed_position_on_new_bar():
    broker=Broker();worker=MT5Worker(broker,account());d=deployment();s=strategy(max_daily_trades=1)
    state=worker.local_state(d);item={'strategy':s.to_dict(),'weight':1}
    worker.algorithm(d,state,item,0,True)
    assert len(broker.opened)==1
    broker.opened=[];state['bars']={}
    worker.algorithm(d,state,item,0,True)
    assert len(broker.sent)==1
    day=datetime.now(timezone.utc).date().isoformat()
    assert state['entry_counts'][f'{d["id"]}:algo:0:{day}']==1


def test_time_exit_waits_for_closed_bars_and_closes_when_bar_arrives():
    broker=Broker();worker=MT5Worker(broker,account());d=deployment();s=strategy(exit_mode='TIME_EXIT',max_bars=1)
    state=worker.local_state(d);item={'strategy':s.to_dict(),'weight':1}
    worker.algorithm(d,state,item,0,True)
    worker.algorithm(d,state,item,0,False)
    assert broker.opened
    broker.opened[0].time-=1800
    worker.algorithm(d,state,item,0,False)
    assert not broker.opened


def test_bridge_retries_read_but_never_order_send(monkeypatch):
    broker=EABroker(account());calls=[]
    def request(method,args):
        calls.append(method)
        if method=='order_send':raise RuntimeError('unknown mutation')
        if calls.count(method)==1:raise BridgeReadUnavailable('temporary read')
        return {'equity':100}
    monkeypatch.setattr(broker,'_request',request)
    assert broker.rpc('account_info')=={'equity':100}
    with pytest.raises(RuntimeError,match='unknown mutation'):broker.rpc('order_send')
    assert calls==['account_info','account_info','order_send']


def test_preflight_timeout_does_not_claim_uncertain_mutation(monkeypatch):
    broker=Broker();worker=MT5Worker(broker,account());d=deployment()
    def unavailable(request):raise BridgeReadUnavailable('read-only check unavailable')
    monkeypatch.setattr(broker,'order_check',unavailable)
    with pytest.raises(BridgeReadUnavailable):worker.open_position(d,'deploy1:read','EURUSD','BUY',1.09,1.12)
    with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM actions').fetchone()[0]==0
    assert store.get('deployment',d['id'])['state']=='ACTIVE' and not broker.sent


@pytest.mark.parametrize('direction',['BUY','SELL'])
@pytest.mark.parametrize('mode',['TRAILING_ATR','BREAKEVEN','PARTIAL_TP','TIME_EXIT'])
def test_management_on_controlled_price_paths(direction,mode):
    broker=Broker();worker=MT5Worker(broker,account());d=deployment()
    d['uses_source_risk']=True
    s=strategy(exit_mode=mode,max_bars=1,partial_tp1_atr=.5,be_atr=.5,trail_atr=.5)
    if direction=='SELL':s.buy_conditions,s.sell_conditions=[],s.buy_conditions;s.direction='SHORT_ONLY'
    state=worker.local_state(d);item={'strategy':s.to_dict(),'weight':1}
    worker.algorithm(d,state,item,0,True)
    position=broker.opened[0];original_sl=position.sl;entry=position.price_open
    if mode=='TIME_EXIT':position.time-=1800
    else:broker.bid+=.003 if direction=='BUY' else -.003
    worker.algorithm(d,state,item,0,False)
    if mode=='TIME_EXIT':assert not broker.opened
    elif mode=='PARTIAL_TP':
        assert broker.opened[0].volume==.01
        worker.algorithm(d,state,item,0,False)
        assert broker.opened[0].volume==.01  # partial exit remains one-shot
    elif mode=='BREAKEVEN':assert broker.opened[0].sl==pytest.approx(entry)
    else:assert broker.opened[0].sl>original_sl if direction=='BUY' else broker.opened[0].sl<original_sl


def test_opposite_signal_closes_managed_trade():
    broker=Broker();worker=MT5Worker(broker,account());d=deployment();s=strategy()
    state=worker.local_state(d);worker.algorithm(d,state,{'strategy':s.to_dict(),'weight':1},0,True)
    s.buy_conditions,s.sell_conditions=[],s.buy_conditions;s.direction='SHORT_ONLY'
    worker.algorithm(d,state,{'strategy':s.to_dict(),'weight':1},0,False)
    assert not broker.opened and len(broker.sent)==2


def test_hedging_same_symbol_repeated_algorithm_and_opposite_leg_stay_independent():
    from backend.ea_bridge import EAResult
    class UniqueTickets(Broker):
        def order_send(self,request):
            result=super().order_send(request)
            if request.get('action')==1 and not request.get('position'):
                self.opened[-1].ticket=100+len(self.sent)
                return EAResult(retcode=result.retcode,order=self.opened[-1].ticket,volume=result.volume,comment=result.comment)
            return result
    broker=UniqueTickets();worker=MT5Worker(broker,account());d=deployment()
    long=strategy();short=strategy();short.buy_conditions,short.sell_conditions=[],short.buy_conditions;short.direction='SHORT_ONLY'
    state=worker.local_state(d)
    for index,s in enumerate((long,long,short)):
        worker.algorithm(d,state,dict(strategy=s.to_dict(),weight=1),index,True)
    assert len(broker.opened)==3
    assert {p.symbol for p in broker.opened}=={'EURUSD'}
    assert [p.type for p in broker.opened]==[0,0,1]
    assert [p.magic for p in broker.opened]==[d['magic']+i for i in range(3)]
    kept={broker.opened[0].ticket,broker.opened[2].ticket}
    worker.close_position(dict(d,magic=d['magic']+1),broker.opened[1],reason='one-leg')
    assert {p.ticket for p in broker.opened}==kept


def test_unsupported_limits_and_dynamic_sizing_are_explicitly_blocked():
    s=strategy(max_weekly_loss_pct=1)
    assert any('semanales' in reason for reason in store.compatibility(s))
    s.max_weekly_loss_pct=s.max_monthly_loss_pct=0
    assert store.compatibility(s)==[]
    s.sizing_mode='DCA'
    assert any('DCA' in reason for reason in store.compatibility(s))


def test_partial_exit_rejects_unsplittable_minimum_lot_before_opening():
    broker=Broker();worker=MT5Worker(broker,account());d=deployment()
    d.update(fixed_lot=.01,partial_exit_pct=50)
    with pytest.raises(RuntimeError,match='cierre parcial configurado'):
        worker.open_position(d,'deploy1:partial-min','EURUSD','BUY',1.099,1.103)
    assert not broker.sent

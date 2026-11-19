"""Pending lifecycle against an in-memory broker; no terminal initialization."""
import time
from collections import namedtuple
from types import SimpleNamespace as NS
import pytest
from backend import copy_trading as store
from backend.mt5_worker import MT5Worker
from test_copy_trading import FakeMT5,account,deployment,isolated_store

Result=namedtuple('Result','retcode order volume comment')


class PendingBroker(FakeMT5):
    def __init__(self):super().__init__();self.pending=[];self.next_ticket=1000
    def orders_get(self):return self.pending
    def symbol_info(self,symbol):
        info=super().symbol_info(symbol);info.expiration_mode=4;return info
    def order_send(self,r):
        if r['action'] in (5,7,8):
            self.sent.append(dict(r))
            if r['action']==5:
                self.next_ticket+=1
                self.pending.append(NS(ticket=self.next_ticket,symbol=r['symbol'],type=r['type'],volume=r['volume'],
                    price_open=r['price'],sl=r['sl'],tp=r['tp'],magic=r['magic'],comment=r['comment'],time=time.time()))
                return Result(10008,self.next_ticket,0,'accepted')
            o=next(o for o in self.pending if o.ticket==r['order'])
            if r['action']==7:o.price_open=r['price'];o.sl=r['sl'];o.tp=r['tp']
            else:self.pending.remove(o)
            return Result(10009,o.ticket,o.volume,'done')
        return super().order_send(r)
    def fill(self):
        o=self.pending.pop(0)
        self.opened.append(NS(**dict(vars(o),ticket=o.ticket+10000,type=0 if o.type in (2,4) else 1)))


def snapshot(orders=(),positions=()):
    store.put('snapshot','master',dict(at=time.time(),verified_demo=True,equity=10000,orders=list(orders),positions=list(positions),quotes={'EURUSD':dict(bid=1.1,ask=1.1001)}))


def prepare(**changes):
    b=PendingBroker();w=MT5Worker(b,account());d=deployment()
    d.update(source_type='account',source_id='master',risk_mode='RISK_PERCENT',symbol_filter='ALL',**changes)
    store.put('deployment',d['id'],d);r=w.local_state(d);snapshot();w.account_copy(d,r,True)
    return b,w,d,r


def order(**changes):
    return dict(dict(ticket=123,symbol='EURUSD',type=2,volume=.1,price_open=1.095,sl=1.09,tp=1.12,time=time.time()),**changes)


@pytest.mark.parametrize('kind,price,sl,tp',[(2,1.09,1.08,1.12),(3,1.11,1.12,1.09),(4,1.11,1.10,1.13),(5,1.09,1.10,1.07)])
def test_all_four_pending_types_are_copied_once(kind,price,sl,tp):
    b,w,d,r=prepare();snapshot([order(type=kind,price_open=price,sl=sl,tp=tp)])
    w.account_copy(d,r,True);w.account_copy(d,r,True)
    assert len(b.pending)==1 and b.pending[0].type==kind
    assert r['pending_copies']['123']['initial_local_volume']>0


def test_pending_changes_can_return_to_previous_price_repeatedly():
    b,w,d,r=prepare();o=order();snapshot([o]);w.account_copy(d,r,True)
    for price in [1.094,1.093,1.094,1.093]:
        snapshot([dict(o,price_open=price,sl=price-.005,tp=price+.01)]);w.account_copy(d,r,False)
        assert b.pending[0].price_open==price
    assert len([r for r in b.sent if r['action']==7])==4


def test_fill_changes_ticket_without_duplicating_entry_and_master_close_closes_copy():
    b,w,d,r=prepare();o=order();snapshot([o]);w.account_copy(d,r,True);b.fill()
    p=dict(o,ticket=900,source_order=123,type=0)
    snapshot([], [p]);w.account_copy(d,r,True)
    assert len([x for x in b.sent if x['action']==5])==1
    assert len(b.opened)==1 and r['positions']['900']['target_ticket']==11001
    snapshot();w.account_copy(d,r,False)
    assert not b.pending and not b.opened


def test_master_cancel_removes_owned_pending_only():
    b,w,d,r=prepare();snapshot([order()]);w.account_copy(d,r,True)
    b.pending.append(NS(**dict(vars(b.pending[0]),ticket=999,magic=0,comment='manual')))
    snapshot();w.account_copy(d,r,False)
    assert [o.ticket for o in b.pending]==[999]


def test_destination_fills_first_then_master_cancels_closes_it():
    b,w,d,r=prepare();snapshot([order()]);w.account_copy(d,r,True);b.fill()
    w.account_copy(d,r,False)
    snapshot();w.account_copy(d,r,False)
    assert not b.opened


def test_resize_waits_for_cancel_then_creates_one_replacement():
    b,w,d,r=prepare()
    d.update(risk_mode='MULTIPLIER',multiplier=.1);store.put('deployment',d['id'],d)
    o=order(volume=.1);snapshot([o]);w.account_copy(d,r,True)
    snapshot([dict(o,volume=.2)]);w.account_copy(d,r,True)
    assert len(b.pending)==1 and b.pending[0].volume==.02


def test_native_pending_without_bracket_can_use_explicit_destination_protection():
    b,w,d,r=prepare(sl_tp_mode='CUSTOM',custom_sl_pips=20,custom_tp_pips=40)
    snapshot([order(sl=0,tp=0)]);w.account_copy(d,r,True)
    assert b.pending and b.pending[0].sl>0 and b.pending[0].tp>b.pending[0].price_open


def test_protection_can_move_to_previously_used_values():
    b,w,d,r=prepare();snapshot([order()]);w.account_copy(d,r,True);b.fill();p=b.opened[0]
    for sl in [1.091,1.092,1.091,1.092]:w.modify(d,p,sl,1.12);assert p.sl==sl

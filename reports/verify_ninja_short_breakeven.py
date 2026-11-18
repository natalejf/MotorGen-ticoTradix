"""One bounded native simulation retest, using received prices without altering them."""
import json,time,uuid
from pathlib import Path
from backend.ninja_rpc import NinjaBroker

def main():
    sid=uuid.uuid4().hex
    b=NinjaBroker('38f7b4403b0c42dbbfef643ea6dea5ad','SimAccount2',sid,'MNQ DEC26',140000001)
    report=dict(session=sid,purpose='Native SHORT breakeven retest',status='INCONCLUSIVE')
    claimed=False
    try:
        b.rpc('claim');claimed=True
        state=b.rpc('state')
        assert state['execution_allowed'] and not state['positions'] and not state['orders']
        assert time.time()-state['tick_time']<30
        bid,ask=state['bid'],state['ask']
        risk=(ask+20-bid)*state['point_value']
        assert risk<=state['equity']*.002
        report['entry_result']=b.order_send(dict(action=1,type=1,volume=1,price=bid,sl=ask+20,tp=bid-100,comment='STX_BE_SHORT_TEST'))._asdict()
        deadline=time.time()+45
        while time.time()<deadline:
            state=b.rpc('state')
            if not state['positions']:break
            p=state['positions'][0]
            if state['ask']<p['price_open']-state['tick_size']*2:
                report['before_modify']=state
                report['modify_result']=b.order_send(dict(action=6,position=p['ticket'],sl=p['price_open'],tp=p['tp']))._asdict()
                observed=b.rpc('state');report['after_modify']=observed
                price=p['price_open']
                working=any(o['name'].startswith('STXG_SL_') and o['stop']==price and o['state'] in ('Working','Accepted') for o in observed['protections'])
                executed=bool(observed.get('last_exit') and observed['last_exit']['name'].startswith('STXG_SL_') and observed['last_exit'].get('stop_price')==price)
                if working or executed:report['status']='PASS'
                break
            time.sleep(2)
    finally:
        if claimed:
            state=b.rpc('state')
            for p in state['positions']:
                report['cleanup_result']=b.order_send(dict(action=1,type=0,position=p['ticket'],volume=p['volume'],comment='STX_BE_TEST_CLEANUP'))._asdict()
            deadline=time.time()+15
            while time.time()<deadline:
                final=b.rpc('state')
                if not final['positions'] and not final['orders'] and not any(o['state'] in ('Working','Accepted','Submitted','CancelPending') for o in final['protections']):break
                time.sleep(1)
            assert not final['positions'] and not final['orders']
            b.rpc('release');report['flat_after_test']=True
        Path('reports/ninja_short_breakeven_live.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print(report['status'],'SHORT breakeven native retest; flat:',report.get('flat_after_test'),flush=True)

if __name__=='__main__':main()

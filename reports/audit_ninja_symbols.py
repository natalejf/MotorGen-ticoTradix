"""Read-only native data audit; temporarily reserves a flat local sim account."""
import json,time,uuid
from pathlib import Path
import pandas as pd
from backend.ninja_rpc import NinjaBroker
from backend.indicator_audit import audit_frame

def main():
    parent=uuid.uuid4().hex
    brokers=[NinjaBroker('38f7b4403b0c42dbbfef643ea6dea5ad','Sim101',uuid.uuid5(uuid.UUID(parent),str(i)).hex,symbol,130000000+i,parent)
             for i,symbol in enumerate(('MNQ DEC26','MYM DEC26','MGC DEC26'))]
    claimed=[];report={}
    try:
        for broker in brokers:broker.rpc('claim');claimed.append(broker)
        for broker in brokers:
            print('HISTORY',broker.symbol,flush=True)
            bars=broker.copy_rates_from_pos(broker.symbol,30,1,1000)
            frame=pd.DataFrame(bars);frame.index=pd.to_datetime(frame.pop('time'),unit='s')
            frame=frame.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','tick_volume':'Volume'})
            audit=audit_frame(frame);state=broker.state()
            report[broker.symbol]=dict(bars=bars,state=state,audit=audit)
            print(broker.symbol,len(bars),'quotes',state['bid'],state['ask'],'AUDIT',audit['passed'],audit['failed'],flush=True)
            Path('reports/ninja_symbols_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    finally:
        for broker in reversed(claimed):print('RELEASE',broker.symbol,broker.rpc('release'),flush=True)

if __name__=='__main__':main()

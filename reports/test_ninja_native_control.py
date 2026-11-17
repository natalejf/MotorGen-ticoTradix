"""Native Sim101 integration check. No order API: uses original candle rules."""
import json
import time
from pathlib import Path
from reports.create_demo_genetic_portfolio import api

OUT=Path(__file__).with_name('ninja_native_test.json')


def main():
    report=json.loads(OUT.read_text(encoding='utf-8'));key=report['connection']
    def save():OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    def state():return next(c for c in api('/api/ninja/status')['connections'] if c['id']==key)
    def command(action,params=None):
        sent=api(f'/api/ninja/connections/{key}/{action}',params or {})
        deadline=time.time()+25
        while time.time()<deadline:
            current=state();cmd=next((c for c in current['commands'] if c['id']==sent['id']),{})
            if cmd.get('state')=='APPLIED':return cmd
            if cmd.get('state') in ('REJECTED','EXPIRED'):raise RuntimeError(str(cmd))
            time.sleep(1)
        raise RuntimeError('Comando sin ACK nativo; no se reenvía')
    before=state()
    if not before['connected'] or before['snapshot']['account']!='Sim101' or before['snapshot']['position_quantity']:
        raise RuntimeError('Requiere Sim101 conectado y sin posición en el instrumento')
    report['before']=before
    report['configure']=command('configure',dict(lots=1,tp_usd=100,sl_usd=100,target=500,
        max_loss=500,daily_profit_limit=200,daily_loss_limit=200,start_balance=50020))
    report['configured']=state();save();print('CONFIGURE APPLIED',report['configured']['snapshot']['lots'],flush=True)
    report['start']=command('start');save();print('START APPLIED; esperando cierre de vela original',flush=True)
    deadline=time.time()+360;seen=False
    try:
        while time.time()<deadline:
            current=state();snapshot=current['snapshot']
            if not current['connected']:raise RuntimeError('Se perdió conexión nativa')
            if snapshot.get('position_quantity'):
                report['position_observed']=snapshot;save();seen=True
                print('POSITION',json.dumps(snapshot,ensure_ascii=True),flush=True);break
            time.sleep(1)
    finally:
        report['pause']=command('pause');report['after_pause']=state();save()
        print('PAUSE APPLIED; gestión nativa conserva TP/SL',flush=True)
    if seen:
        deadline=time.time()+180
        while time.time()<deadline:
            snapshot=state()['snapshot']
            if not snapshot.get('position_quantity'):
                report['flat_confirmed']=snapshot;break
            time.sleep(2)
    report['finished']=time.time();report['result']='ENTRY_CONFIRMED' if seen else 'NO_POSITION_OBSERVED_WITHIN_WINDOW'
    report['final']=state();save()
    print('RESULT',report['result'],'quantity',report['final']['snapshot']['position_quantity'],flush=True)


if __name__=='__main__':main()

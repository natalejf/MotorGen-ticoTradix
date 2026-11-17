"""Bounded native demo trial; entries only from original closed-candle signal."""
import json,time,requests
from pathlib import Path
OUT=Path(__file__).with_name('proppass_requested_groups.json')
r=json.loads(OUT.read_text(encoding='utf-8'));base='http://127.0.0.1:8000/api/ninja/'
def save():OUT.write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
def api(path,body=None):
 z=requests.get(base+path,timeout=8) if body is None else requests.post(base+path,json=body,timeout=8)
 z.raise_for_status();return z.json()
key=api('status')['connections'][0]['id']
def state():return next(c for c in api('status')['connections'] if c['id']==key)
def cmd(path):
 sent=api('connections/'+key+'/'+path,{})
 for _ in range(27):
  time.sleep(1);c=state();ack=next((v for v in c['commands'] if v['id']==sent['id']),{})
  if ack.get('state')=='APPLIED':return ack
  if ack.get('state') in ('REJECTED','EXPIRED'):raise RuntimeError(ack.get('detail',ack['state']))
 raise RuntimeError('Sin ACK nativo; no se reenvia')
def flat():return state()['snapshot']['position_quantity']==0 and not any(a.get('working_orders') for a in state()['snapshot']['accounts'])
try:
 for index,g in enumerate(r['groups']):
  trial={'group_id':g['id'],'start_at':time.time(),'accounts':g['settings']['accounts']};r.setdefault('trials',[]).append(trial);save()
  if index:
   trial['reset']=cmd('groups/'+g['id']+'/reset');save()
  trial['configured']=state()['snapshot'];trial['start_ack']=cmd('groups/'+g['id']+'/start');save();print('START group',index+1,flush=True)
  deadline=time.time()+650;entry=False;last='';target=False
  while time.time()<deadline:
   c=state();s=c['snapshot']
   if not c['connected']:raise RuntimeError('Conector desconectado')
   current=[(a['name'],a['position_quantity'],a['status'],a.get('daily_pnl'),len(a.get('working_orders',[]))) for a in s['accounts'] if a['name'] in trial['accounts']]
   signature=str([(a[0],a[1],a[2],a[4]) for a in current])
   if signature!=last:print('STATE group',index+1,current,flush=True);last=signature
   if s['position_quantity'] and not entry:
    entry=True;trial['entry_snapshot']=s;trial['entry_at']=time.time();save();deadline=min(deadline,time.time()+210)
   completed=[a for a in s['accounts'] if a['name'] in trial['accounts'] and (a['status'] in ('PASS','BURNED') or a.get('daily_status') in ('TARGET_REACHED','LOSS_LIMIT_REACHED'))]
   if completed and not s['position_quantity']:
    target=True;trial['limit_transition_snapshot']=s;trial['limit_at']=time.time();save();break
   time.sleep(2)
  trial['pause_ack']=cmd('pause');save()
  if not flat():trial['close_stop_ack']=cmd('groups/'+g['id']+'/close-stop');save()
  deadline=time.time()+25
  while time.time()<deadline and not flat():time.sleep(1)
  trial['final']=state();trial['ended_at']=time.time();trial['result']='LIMIT_TRANSITION_CONFIRMED' if target else 'ENTRY_CONFIRMED_LIMIT_NOT_REACHED' if entry else 'NO_SIGNAL_ENTRY_WITHIN_WINDOW';save()
  print('RESULT group',index+1,trial['result'],'flat',flat(),flush=True)
  if not flat():raise RuntimeError('No se confirmo flat; no se cambia grupo')
except Exception as e:
 r['error']=str(e);save();print('ERROR',str(e),flush=True)
 try:r['safety_pause']=cmd('pause');save()
 except Exception:pass
 raise
finally:
 r['finished_at']=time.time();save()

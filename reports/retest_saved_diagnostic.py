"""Repeat the saved demo test through its ordinary, user-visible start API."""
import json
import time
import urllib.request
from pathlib import Path

from backend import copy_trading as store
from backend.mt5_diagnostic import PROFILE


def main():
    account=store.listing('account')[0]
    deadline=time.time()+60
    while time.time()<deadline:
        snapshot=store.get('snapshot',account['id'])
        if snapshot.get('verified_demo') and time.time()-snapshot['at']<15:break
        time.sleep(2)
    body=json.dumps(dict(source_id=PROFILE,account_id=account['id'])).encode()
    request=urllib.request.Request('http://127.0.0.1:8000/api/execution/start',data=body,
        headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=30) as response:session=json.load(response)
    key=session['id'];print('SESSION',key,flush=True)
    out=Path(__file__).with_name('mt5_saved_diagnostic_retest.json')
    deadline=time.time()+1500;last=-1
    while time.time()<deadline:
        state=store.get('diagnostic',key);deployment=store.get('deployment',key)
        report=dict(deployment=key,status=deployment['state'],**state)
        out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        if state['index']!=last:
            print('PROGRESS',state['index'],state['results'][-1] if state['results'] else '',flush=True);last=state['index']
        if deployment['state'] in ('STOPPED','PAUSED'):return
        time.sleep(3)
    raise RuntimeError('El diagnóstico continúa; inspeccionar la sesión y no iniciar otro encima')


if __name__=='__main__':main()

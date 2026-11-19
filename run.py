"""Start Stratix from any working directory; reuse an existing local instance."""
from pathlib import Path
import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent
URL="http://127.0.0.1:8000"

def server_state():
    try:
        with urllib.request.urlopen(URL+"/openapi.json",timeout=2) as response:
            info=json.load(response).get("info",{})
        if "Stratix" in info.get("title",""):
            return "stratix"
    except Exception:
        pass
    with socket.socket() as probe:
        probe.settimeout(.5)
        return "occupied" if probe.connect_ex(("127.0.0.1",8000))==0 else "free"

def open_when_ready():
    for _ in range(60):
        if server_state()=="stratix":
            webbrowser.open(URL)
            return
        time.sleep(.5)

def main(argv=None):
    parser=argparse.ArgumentParser(description="Iniciar Stratix")
    parser.add_argument("--check",action="store_true",help="Comprobar entorno sin iniciar ni abrir ventanas")
    parser.add_argument("--no-browser",action="store_true")
    args=parser.parse_args(argv)
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(errors="replace")
    print("STRATIX - http://127.0.0.1:8000",flush=True)
    state=server_state()
    if state=="stratix":
        print("Stratix ya esta iniciado. Se reutiliza el servidor existente.",flush=True)
        if not args.check and not args.no_browser:webbrowser.open(URL)
        return 0
    if state=="occupied":
        print("ERROR: otro programa ocupa el puerto 8000. No se ha detenido ese programa.",flush=True)
        return 1
    try:
        import uvicorn
        from backend.api import app
    except ImportError as exc:
        import traceback
        log=ROOT/"reports"/"startup_error.log"
        log.parent.mkdir(exist_ok=True)
        log.write_text(traceback.format_exc(),encoding="utf-8")
        print(f"ERROR: Falta modulo o dependencia ({exc}).",flush=True)
        print("Ejecuta: pip install -r requirements.txt",flush=True)
        print("Detalle: "+str(log),flush=True)
        return 1
    except Exception:
        import traceback
        log=ROOT/"reports"/"startup_error.log"
        log.parent.mkdir(exist_ok=True)
        log.write_text(traceback.format_exc(),encoding="utf-8")
        print("ERROR preparando el servidor. Detalle: "+str(log),flush=True)
        return 1
    if args.check:
        print("Entorno y aplicacion OK. Puerto disponible.",flush=True)
        return 0
    if not args.no_browser:threading.Thread(target=open_when_ready,daemon=True).start()
    try:
        uvicorn.run(app,host="127.0.0.1",port=8000,reload=False)
    except (OSError,SystemExit) as error:
        print("ERROR al iniciar el servidor: "+str(error),flush=True)
        return 1
    return 0

if __name__=="__main__":raise SystemExit(main())

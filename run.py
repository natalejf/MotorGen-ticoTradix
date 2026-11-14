"""
Main Launcher for TradingNote Genetic Engine Replica
Starts backend server and opens browser dashboard.
"""

import os
import sys
import webbrowser
import subprocess
import time

def main():
    print("=" * 65)
    print("   TRADINGNOTE · MOTOR GENÉTICO & CREADOR DE ALGORITMOS (REPLICA)   ")
    print("=" * 65)
    print("Iniciando servidor local en http://127.0.0.1:8000 ...")

    # Launch browser after 1.5s
    def open_dash():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8000")

    import threading
    threading.Thread(target=open_dash, daemon=True).start()

    # Run uvicorn
    import uvicorn
    uvicorn.run("backend.api:app", host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    main()

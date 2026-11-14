"""
Automated Daily Historical Data Updater for TradingNote Genetic Engine
Schedules daily fetch of newly closed candles across all 8 major trading pairs:
- XAUUSD (Gold)
- NASDAQ (NQ=F)
- EURUSD
- USDJPY
- AUDUSD
- GBPUSD
- US30 (Dow Jones)
- BTCUSD

Runs once every 4 hours or at market close daily.
Can be executed as a standalone background service or triggered via API.
"""

import time
import schedule
import datetime
from backend.data_manager import data_manager

def job_update_data():
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] Iniciando sincronización automática de datos de mercado...")
    try:
        results = data_manager.update_all_symbols()
        for sym, res in results.items():
            print(f"  ✓ {sym}: 1h={res.get('1h', 'N/A')} barras, 4h={res.get('4h', 'N/A')} barras, 1d={res.get('1d', 'N/A')} barras")
        print(f"[{now_str}] Sincronización completada con éxito.")
    except Exception as e:
        print(f"[{now_str}] Error durante la sincronización: {e}")

def run_scheduler():
    print("=" * 60)
    print("TradingNote Auto-Updater Service Activo")
    print("Monitoreando XAUUSD, NASDAQ, EURUSD, USDJPY, AUDUSD, GBPUSD, US30, BTCUSD")
    print("=" * 60)

    # Initial sync on launch
    job_update_data()

    # Schedule daily at 22:30 UTC (after NY close) and every 6 hours
    schedule.every().day.at("22:30").do(job_update_data)
    schedule.every(6).hours.do(job_update_data)

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    run_scheduler()

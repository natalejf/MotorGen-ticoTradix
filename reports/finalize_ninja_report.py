"""Build the local verification report from preserved native evidence."""
import json,time,uuid
from pathlib import Path
from backend import copy_trading as store

ROOT=Path(__file__).resolve().parent
def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))

def main():
    sid='be32fd9f457b4192a089d6af070aab98'
    diagnostic=store.get('diagnostic',sid);deployment=store.get('deployment',sid)
    snapshot=store.get('ninja_snapshot',deployment['connection'])
    audits=read('ninja_symbols_audit.json');supplement=read('ninja_short_breakeven_live.json')
    isolation=read('proppass_close_scope_verified.json')
    accounts=[a for a in snapshot['accounts'] if a['name'] in ('Sim101','SimAccount2','SimAccount3')]
    assert deployment['state']=='STOPPED' and diagnostic['index']==20
    assert all(not a['position_quantity'] and not a['working_orders'] for a in accounts)
    assert supplement['status']=='PASS' and supplement['flat_after_test']
    assert isolation['result']=='PASS' and isolation['native_protections_unchanged_verified']
    assert len(store.listing('ninja_connection'))==1
    results=diagnostic['results'];passed=sum(r['outcome']=='PASS' for r in results)
    inconclusive=[r for r in results if r['outcome']=='INCONCLUSIVE']
    assert passed==19 and len(inconclusive)==1 and inconclusive[0]['exit']=='BREAKEVEN' and inconclusive[0]['direction']=='SELL'
    target_ids={sid,'825c557fcf1148eab9cfc50dd3d849b0',supplement['session']}
    for parent in ('567901110ce54ac8bca88ce2ba93d6c0','3ad9dd11b1f44bbeb398f34f5d694c61'):
        target_ids.update(uuid.uuid5(uuid.UUID(parent),str(i)).hex for i in range(3))
    events=[]
    logs=Path('C:/Users/yo/OneDrive/Documentos/NinjaTrader 8/log')
    for path in logs.glob('log.202611*.txt'):
        if '.es.' in path.name:continue
        for line in path.read_text(encoding='utf-8-sig',errors='replace').splitlines():
            if any(s in line for s in target_ids):events.append(dict(file=path.name,event=line))
    report=dict(native_version=snapshot['version'],at=time.time(),diagnostic=diagnostic,
        diagnostic_tally=dict(passed=passed,failed=sum(r['outcome']=='FAIL' for r in results),inconclusive=len(inconclusive)),
        supplementary_short_breakeven=supplement,proppass_isolation=isolation,
        indicator_audits={symbol:dict(indicators=v['audit']['indicators'],checks=v['audit']['checks'],passed=v['audit']['passed'],failed=v['audit']['failed']) for symbol,v in audits.items()},
        accounts_after_tests=accounts,connection_count=1,controlled_rule_pairs=54,
        native_order_events=events,reconciliations=['ninja_ack_reconciliation.json','ninja_pending_reconciliation.json'],
        limits=['Local simulated accounts only','One algorithm per distinct NT8 contract in a portfolio','Controlled rule matrix is not 54 separate native trading scenarios','MTF and exhaustive parameter combinations not certified','DCA, martingale and unsupported limits remain blocked'])
    (ROOT/'ninja_portfolio_final_verified.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    rows='\n'.join(f"| {i+1} | {r['entry']} | {r['direction']} | {r['exit']} | {r['outcome']} |" for i,r in enumerate(results))
    text=f'''# Pruebas NinjaTrader y aislamiento de PropPass

Fecha: 18/11/2026. AddOn cargado: {snapshot['version']}. Todas las operaciones fueron en cuentas locales simuladas.

## Resultado

- Portafolio guardado: **STX · Demo Ninja · 3 símbolos**, en portafolios, carpeta Demo Ninja.
- Mapeo: NASDAQ → MNQ DEC26; US30 → MYM DEC26; XAUUSD → MGC DEC26.
- Un contrato por instrumento, presupuesto total de riesgo 3% distribuido por pesos. El mínimo de contratos nunca se redondea hacia arriba para exceder ese presupuesto.
- Se evaluaron los tres algoritmos sobre velas recibidas de NT8. Oro generó una venta por ATR y RSI: su Sell Stop se activó y tuvo SL/TP nativos con OCO. Nasdaq no tuvo señal; Dow respetó su sesión de Londres. No se cambiaron sus condiciones para forzar entradas.
- Auditoría: 32 indicadores y 200 pares compatibles de indicador/operador por instrumento; **600/600 comprobaciones**, sobre 1000 velas cerradas de cada instrumento.
- Matriz controlada del evaluador: 54 combinaciones de entrada/dirección/salida, más gestión de posiciones y cierre de todas las patas. No equivale a 54 escenarios ejecutados en el mercado.
- Diagnóstico nativo: **19 aprobados, 0 fallidos y 1 inconcluso** en la tanda. El inconcluso fue breakeven de venta por falta de movimiento favorable. La prueba nativa adicional de breakeven de venta **pasó**, conservando ambos resultados por separado.
- Sim101, SimAccount2 y SimAccount3 quedaron sin posiciones ni órdenes pendientes. Portafolio y diagnóstico quedaron detenidos al terminar; siguen guardados para volver a asignarlos.

## PropPass

Queda **un vínculo de NinjaTrader**. Se archivó otro que nunca recibió cuentas ni tuvo asignaciones; el vínculo activo y su clave se conservaron. Un vínculo identifica una instalación y persiste al cerrar: no hay que crearlo de nuevo. «Vincular otro equipo» se usa solamente para otra instalación.

«Cerrar PropPass» está limitado a sus operaciones identificadas en el instrumento y las cuentas del grupo aplicado. El servidor no acepta ampliar ese alcance enviando otras cuentas. El AddOn excluye las cuentas reservadas por algoritmos del motor y las exposiciones sin propiedad de PropPass; si detecta una mezcla externa, bloquea su gestión automática.

Se ejecutó el cierre de PropPass con otro algoritmo abierto en SimAccount3: **su posición, estado activo y protecciones quedaron intactos**. Después se cerró ese algoritmo desde su propio control. El botón de la sesión de un algoritmo o portafolio cierra solamente esa sesión.

## Casos nativos

| Caso | Entrada | Dirección | Salida | Resultado de la tanda |
|---|---|---|---|---|
{rows}

El caso de breakeven BUY se confirmó contra el registro nativo: el stop fue aceptado al precio de entrada y ejecutado antes del siguiente pulso. Se corrigió esa carrera del acuse, sin repetir la orden. El primer intento de modificar una pendiente coincidió con su activación: se archivó, se confirmó el rechazo anterior al cambio y se repitió con una nueva intención después de verificar la cuenta flat. Los cuatro casos finales de pendientes pasaron.

Los casos TIME del diagnóstico prueban un cierre programado. La salida del motor tras X velas se probó con recorridos controlados. Breakeven significa mover el SL a la entrada: el fill puede tener deslizamiento o comisiones.

## Uso y límites

En Mis portafolios, abre **STX · Demo Ninja · 3 símbolos**, pulsa ejecutar, selecciona la cuenta NinjaTrader, revisa las tres equivalencias y los contratos, y sigue su registro. En Mis algoritmos también está **STX · Test integral NinjaTrader**; requiere dos contratos para probar parciales. Sus entradas son deliberadas y no representan señales de inversión.

En NT8 se permite un algoritmo por contrato distinto dentro del portafolio. No está habilitada la mezcla de algoritmos sobre el mismo contrato neto. En MT5 hedging se comprobó en broker controlado la convivencia de instancias repetidas y direcciones opuestas sobre el mismo símbolo.

Estas pruebas validan funciones concretas, no rentabilidad ni todas las combinaciones de parámetros. MTF nativo, calendarios y cargas prolongadas requieren ampliar la matriz. DCA, martingala y otros límites no implementados siguen rechazándose al asignar.

Evidencia detallada: `ninja_portfolio_final_verified.json`, `proppass_close_scope_verified.json`, `ninja_short_breakeven_live.json` y archivos de reconciliación en esta carpeta.
'''
    (ROOT/'INFORME_NINJA_PORTFOLIO_Y_PROPPASS.md').write_text(text,encoding='utf-8')
    print('Report ready: native cases 19 PASS + 1 INCONCLUSIVE; supplementary SHORT BE PASS; isolation PASS; accounts flat.')

if __name__=='__main__':main()

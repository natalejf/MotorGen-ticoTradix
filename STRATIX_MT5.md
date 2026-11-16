# Stratix · Copy Trading MT5 (primera versión demo)

## Qué se implementó

La navegación se organiza ahora en **Cuentas**, **Copy Master** y **Grupos**,
con el diseño monocromático de Stratix. Cuentas incluye tarjetas, filtros por
estado/servidor, búsqueda, vista lista/grid, detalle de posiciones y controles
de inicio/detención del conector. Copy Master tiene pestañas de masters,
algoritmos/portafolios y registro. Las masters permiten añadir una cuenta o
un grupo completo. Grupos permite alta, edición de miembros, plantilla de riesgo,
aplicación explícita de ajustes, pausa/reactivación colectiva y eliminación.

Modos de tamaño de seguidoras: lote fijo, multiplicador, proporcional por equity,
espejo y riesgo porcentual. Siempre dentro del riesgo máximo configurado.
Se pueden editar tamaño, lote máximo, exposición por símbolo/total, equity mínima,
ganancia diaria máxima, spread, dirección, listas blancas/negras, mapeos y SL/TP
propios. Guardar una copia nunca la activa. Retirar una cuenta de un grupo pausa
su copia y la conserva como individual. Las acciones colectivas reportan errores
por cuenta en lugar de ocultar resultados parciales.

La referencia funcional fue revisada en la cuenta del usuario (formularios y
pantallas permitidas), la documentación pública y la transcripción del tutorial
oficial https://www.youtube.com/watch?v=C92Gm6loaTA. El plan FREE impidió crear el
grupo de referencia en TradingNote: no se guardó el grupo ni se cambió el plan.
No se copiaron cuentas, credenciales ni saldos privados a Stratix.

Panel lateral **Copy Trading** para asignar un algoritmo guardado, un portafolio
guardado o una cuenta master a una cuenta MT5 demo. No hay pantalla de órdenes
manuales, exportaciones de algoritmos ni un robot diferente por estrategia.
La conexión utiliza el paquete oficial `MetaTrader5` desde un proceso Python
aislado por cuenta, conectado al terminal local. PC o VPS Windows y terminales
deben permanecer encendidos. No se guarda la contraseña del bróker.

Esta versión rechaza cuentas reales y cuentas netting. Requiere **DEMO HEDGING**.
Tener código y pruebas aprobadas no equivale a certificación con un bróker real.
No se conectó ninguna cuenta ni se enviaron órdenes durante el desarrollo.

## Prueba del 17 de noviembre de 2026

1. Reiniciar Stratix con `python run.py` y recargar el navegador (Ctrl+F5).
2. Abrir MT5 e iniciar sesión en una cuenta **demo hedging**. Verificar por tu
   cuenta que el terminal permite trading algorítmico y acceso de Python.
3. En **Cuentas → Nueva Cuenta** registrar nombre, login, servidor exacto y ruta a
   `terminal64.exe`. Login y servidor deben coincidir con el terminal abierto.
4. Pulsar «Conectar MT5». Esperar el heartbeat **Conectada** y
   verificar que balance/equity/moneda coincidan con MT5. Consultar el registro
   ante cualquier error; «solicitado» no significa «conectado».
5. En **Copy Master → Algoritmos y portafolios**, elegir un algoritmo/portafolio.
   Para copiar una cuenta: **Registrar Master → Añadir seguidora**, o crear un
   grupo en **Grupos** y seleccionarlo como seguidor. Elegir cuenta destino,
   mapeos y límites. Guardar crea una asignación **PAUSED**, sin operaciones.
6. Verificar los símbolos y especificaciones de tu bróker. Ejemplo de mapeo:
   `{"EURUSD":"EURUSD.m","NASDAQ":"USTEC"}`. Solo nombres equivalentes del
   mismo instrumento; no hay conversión económica entre futuros y CFD.
7. Pulsar «Activar en demo». Para algoritmos, las entradas se evalúan al cierre
   de velas M30/H1/H4/D1, usando histórico del terminal (no Yahoo). Activar o
   reanudar espera una vela nueva; no reproduce todas las señales pasadas.
8. Verificar apertura, SL/TP, modificación y cierre en **MT5**, además del registro
   de Stratix. Los resultados del bróker mandan, no un contador del panel.
9. Probar pausa, reconexión, cierre manual de una posición STX, y «Cerrar STX y
   detener». Las posiciones manuales no deben ser alteradas.

Para copiar una cuenta master se necesitan **dos instalaciones MT5 independientes**,
con sus dos cuentas demo iniciadas, registradas y con conector activo. Una misma
instalación no puede mantener dos cuentas distintas conectadas simultáneamente.
No se importan posiciones que ya existían al observar la master por primera vez;
solo aperturas nuevas de menos de 30 segundos. Master desconectada no se interpreta
como «cerró todo». Pausar una copia mantiene cierres y modificaciones existentes.

## Compatibilidad y límites explícitos

- Entradas MARKET; se rechazan LIMIT/STOP y averaging/DCA, martingala/anti-martingala
  y topes de ganancia/racha no implementados. No se eliminan silenciosamente reglas.
- Señales: evaluador del backtester, filtros de dirección/sesión y confirmación
  HTF con barras cerradas. Mínimo 200 barras MT5, hasta 1000 por evaluación.
- Salidas: SL/TP ATR, pips, porcentaje y ATR suavizado; trailing/breakeven,
  estructura, tiempo y parcial sujetos a mínimos y pasos del bróker. La salida
  temporal mide tiempo de reloj, no número de velas efectivamente negociadas.
- Sizing: el configurado en la **asignación** reemplaza el sizing del backtest.
  Presupuesto por entrada = equity × riesgo% × peso normalizado de la estrategia.
  Lote fijo también está sujeto a ese presupuesto y al lote máximo. Se redondea
  hacia abajo; si no alcanza el mínimo del bróker, se rechaza la entrada.
- Topes efectivos del conector: pérdida diaria y drawdown de **equity de cuenta**,
  máximo de posiciones totales, spread y riesgo por entrada. Incluyen el efecto
  de operaciones ajenas/depósitos en equity; no son un libro contable segregado
  por algoritmo ni una garantía de pérdida máxima ante gaps/slippage.
- Los límites de pérdidas semanales/mensuales y operaciones diarias del backtest
  no se transfieren automáticamente: esta primera versión usa los límites de la
  asignación. Revisarlos antes de la prueba y no asumir paridad total con backtest.
- Una asignación no detenida por cuenta. Para operar varios algoritmos usar un
  portafolio. Se rechazan cadenas/ciclos de copia entre cuentas.
- Un proceso por cuenta, lease en SQLite y acciones persistidas antes de enviar.
  Tras resultado incierto o interrupción con orden en envío, se bloquean nuevas
  mutaciones para esa asignación. **No hay reintento ciego ni promesa de exactly-once**:
  revisar posiciones/historial en MT5 y resolver el incidente antes de continuar.
  La reconciliación automática completa de órdenes inciertas queda pendiente.
- Pausa bloquea nuevas entradas. SL/TP ya enviados permanecen en el bróker.
  Trailing, parciales, copy y salidas de horario requieren el conector encendido.
  «Cerrar STX y detener» solo cierra posiciones con los magic asignados por Stratix.

## Persistencia y diagnóstico

`data/copy_trading.sqlite3`: cuentas, asignaciones, snapshots, riesgo, eventos,
acciones y leases. `data/copy_logs/{account_id}.log`: errores del proceso.
Ambos son locales, excluidos de Git. Las asignaciones conservan una copia de la
estrategia al crearlas: editar la estrategia original no cambia una copia activa.

Conector manual alternativo, desde la carpeta del proyecto:

```powershell
python -m backend.mt5_worker --account ID_DE_CUENTA_STRATIX
```

No ejecutar dos workers para una cuenta. «Iniciar conector» lo lanza sin ventana.
No se inicia ningún conector por el simple hecho de abrir Stratix ni por correr tests.

Pruebas: `python -X utf8 -m pytest test_copy_trading.py test_complete_suite.py test_nuevos_operadores.py test_workspace_features.py -q`.
Los tests de ejecución usan un bróker simulado y una SQLite temporal.

Fuentes técnicas oficiales:
- https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5ordercheck_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py

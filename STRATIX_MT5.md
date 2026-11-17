# Stratix · Ejecución MT5 demo

## Cambios del motor

La mezcla aleatoria ahora es compacta: 3–5 indicadores compatibles, una entrada,
1–2 salidas y como máximo 2 condiciones por algoritmo inicialmente. Se pueden
ampliar manualmente. El motor serial publica cada candidato al terminar su backtest,
sin esperar al lote completo. El panel muestra motivos de descarte y candidatos
sin operaciones; el contador de combinaciones es espacio teórico, no tareas en cola.
Mediciones y exploraciones reales del motor: `reports/search_performance.md`.

FRED se retiró de la interfaz, el catálogo de exploración y sus endpoints públicos.
Las búsquedas nuevas usan indicadores técnicos. Las utilidades antiguas permanecen
solo para compatibilidad con datos y pruebas históricos, sin añadir series a la búsqueda.

En Riesgo y Horarios hay un único **Activar Modo Prop Firm**, apagado por defecto.
Apagado: todos los límites porcentuales de pérdida/ganancia de cuenta se fijan en 0
(desactivados); el motor no los vuelve a introducir aleatoriamente. Encendido:
pérdida diaria, drawdown total y objetivo de ganancia se usan tanto en las reglas
del algoritmo como en el filtro/simulación del reto. Se eliminó la tarjeta duplicada
de Límites de Cuenta. El riesgo por operación y los SL/TP siguen siendo independientes.

Una cotización con más de 30 segundos se rechaza. El diagnóstico espera una nueva
sin marcar un fallo inmediato ni reenviar una orden ya enviada. El fallo histórico
por precio obsoleto se conserva en los resultados de aquella ejecución; debe repetirse
para validar la corrección. Los SL/TP/breakeven que no se activan por precio siguen
siendo INCONCLUSOS, no APROBADOS. No se reescriben resultados históricos.

## Conectar una cuenta (una sola vez)

1. Cuentas → Nueva Cuenta: nombre, login y servidor exactos de una **DEMO HEDGING**.
   Selecciona **EA Stratix** como conexión. No guardamos contraseñas del bróker.
2. Pulsa Vincular EA. Descarga `Stratix_Connector.ex5`; el MQ5 también está disponible.
3. En MT5: Archivo → Abrir carpeta de datos → MQL5 → Experts. Copia el EX5,
   actualiza el Navegador y arrástralo a un gráfico.
4. En Herramientas → Opciones → Asesores Expertos permite WebRequest para
   `http://127.0.0.1:8000`. Activa trading algorítmico global y del EA.
5. Completa los parámetros que muestra Stratix: AccountID, ConnectionKey,
   ExpectedLogin, ExpectedServer y StratixURL. Solo un EA por cuenta.

**La conexión se inicia automáticamente al detectar el EA.** No hace falta pulsar
otro botón para activar el conector. La clave se muestra una vez y se guarda su hash.
El EA vuelve a comprobar login, servidor, demo hedging y permisos antes de ejecutar.
Stratix y MT5 deben permanecer abiertos en el mismo PC/VPS Windows. Es un puente
local; no es un servicio en la nube. Dos cuentas simultáneas necesitan dos terminales.
El puente Python anterior sigue siendo compatible con cuentas ya configuradas.

## Ejecutar cualquier algoritmo

**Mis algoritmos → Ejecutar en cuenta → elegir cuenta demo → Iniciar en demo.**

Todo sucede en esa ventana. El inicio crea una sesión activa con el tamaño,
las entradas y las salidas del algoritmo guardado. No exige crear otro gestor de
riesgo ni volver a configurar lote, presupuesto, pérdida diaria o drawdown.
Los límites que el propio algoritmo ya trae se conservan. Un límite diario o de
cuenta desactivado en el algoritmo no se reemplaza por un límite externo obligatorio.
Solo se ofrecen equivalencias de símbolos como ajuste opcional cuando el bróker
usa nombres distintos, por ejemplo EURUSD → EURUSDm.

En **Cuentas → Mapear símbolos** hay una fila por instrumento y un buscador:
escribe a la derecha el nombre exacto que muestra MT5 y pulsa Guardar equivalencias.
No hace falta JSON. También puedes editar los símbolos usados por un algoritmo en
su ventana Ejecutar en cuenta. Las equivalencias se guardan por cuenta y se aplican
en los próximos inicios; no cambian las posiciones de sesiones que ya están abiertas.

En **Portafolios guardados → Ejecutar en cuenta** se usa la misma ventana y el
presupuesto de riesgo/pesos del portafolio. Esta organización se apoya en las guías
oficiales de TradingNote; el acceso directo para un algoritmo es una simplificación
solicitada para Stratix, no una afirmación de que sea la UI exacta de TradingNote:
- https://tradingnote.co/es/docs/mis-algoritmos
- https://tradingnote.co/es/docs/portafolios

**Copy Master se usa únicamente para master → seguidoras.** Se retiraron de allí
la asignación y gestión de algoritmos, y de Cuentas el botón especial Diagnóstico demo.
La configuración de tamaño de las seguidoras sigue perteneciendo al copy.

## Algoritmo de prueba guardado

**Mis algoritmos → Pruebas demo → STX · Test integral demo.**

Se lanza con el mismo botón y formulario que los demás algoritmos. Sus 20 casos
son un plan predefinido de diagnóstico, no una estrategia de inversión ni un
resultado del motor genético. No tiene métricas inventadas de rentabilidad.
Sus tamaños de prueba están definidos en el algoritmo (hasta 0.02 lotes y riesgo
inicial de 0.1% por entrada); no se pide un gestor adicional para ejecutarlo.

Primero audita 32 indicadores y 200 pares indicador/operador con velas M30 cerradas
obtenidas desde el terminal. Sin histórico suficiente espera y lo informa antes de
abrir operaciones. Si falla la auditoría, se pausa. Comprueba cálculo, evaluación
y estabilidad frente a velas futuras; no certifica rentabilidad ni equivalencia
numérica con todos los indicadores nativos de MT5/TradingNote.

Después recorre BUY/SELL a mercado con cierre completo, parcial, modificación de SL,
cierre por reloj, SL, TP, breakeven y actualización de trailing. También coloca,
modifica y cancela Buy/Sell Limit/Stop. Los casos son secuenciales. Una parcial
requiere al menos dos pasos de volumen; el riesgo no se eleva para conseguirla.
Las pendientes requieren la cuenta libre de otras posiciones/órdenes.

## Estado, resultados y log

Vuelve a **Ejecutar en cuenta** desde la tarjeta del algoritmo para ver sus sesiones.
Cada inicio, activación o reactivación abre un registro visible nuevo: se limpian
los mensajes anteriores de ese algoritmo en esa cuenta y solo se muestra la sesión
actual. La tabla del test muestra los resultados producidos desde esa activación,
sin arrastrar casos anteriores. No se reinicia el progreso interno ni se borran
tickets, acciones o protecciones contra reenvíos. Reanudar continúa las operaciones
existentes; para repetir los 20 casos completos hay que iniciar una sesión nueva
después de detener la anterior.
La misma ventana se actualiza cada 3 segundos y muestra:
- Estado de la sesión y controles Pausar, Reanudar, Detener y cerrar operaciones.
- Tabla de casos APROBADO / FALLÓ / INCONCLUSO para el algoritmo de prueba.
- Registro con hora, inicio de cada caso, ejecuciones y rechazos del bróker.

**Limpiar registro** borra únicamente los mensajes de esa sesión. Conserva sus
resultados, progreso, estado, órdenes y acciones persistidas. Los nuevos eventos
siguen apareciendo. Copy Master tiene su propio botón para limpiar sus mensajes,
sin eliminar registros de ejecución de algoritmos.

Un SL/TP solo se aprueba cuando el historial del bróker confirma el motivo.
Si el precio no activa una condición dentro de la espera configurada, queda
INCONCLUSO, no APROBADO. El trailing verifica una mejora del SL, no todos los
recorridos posibles. El cierre por reloj del test no certifica Exit After X Bars.
Se limpian únicamente posiciones y pendientes del magic de la sesión; no se
modifican operaciones manuales. Cerrar la ventana no detiene la sesión.

## Límites actuales

- Solo DEMO HEDGING. No se habilitan cuentas reales ni netting.
- Los algoritmos normales admiten MARKET, LIMIT y STOP y velas cerradas
  M30/H1/H4/D1. Las pendientes usan el desplazamiento del motor (0.2 ATR),
  vencen al cerrar la vela de entrada y requieren expiración especificada del
  bróker y EA actualizado. Se comprueban distancias mínimas antes de enviarlas.
- FIXED_RISK y FIXED_CASH aplican su multiplicador; FIXED_CASH requiere cuenta USD.
  FIXED_LOT conserva su lote sin multiplicador, como en el backtester.
- TIME_EXIT cuenta velas cerradas efectivas, hasta 900; no segundos de reloj.
- DCA/averaging, sizing por rachas y límites semanales/mensuales no implementados
  se rechazan explícitamente al asignar el algoritmo, sin ignorar sus parámetros.
- El copy sigue copiando posiciones ejecutadas, no el ciclo previo de pendientes.
- Una sesión por cuenta; para varios algoritmos usa un portafolio. No se admiten
  cadenas o ciclos de copy. Un cierre manual de una copia no provoca reapertura.
- Ante resultado de orden incierto se pausa y no se reenvía a ciegas; requiere
  reconciliación manual. No hay garantía de ejecución exactamente una vez.
- SL/TP enviados permanecen en el bróker. Copy, trailing, parciales y otras salidas
  dinámicas requieren EA, terminal y aplicación encendidos.

## Diagnóstico técnico

Desde EA **v1.02**, la pestaña **Expertos** muestra conexión/desconexión local y
del bróker, estado de asignaciones, señales con nombre/condiciones/vela, resultados
de órdenes y deals del terminal (incluidos cierres SL/TP). No imprime claves.
Al arrancar muestra el estado actual sin reproducir todo el historial. Los
mensajes web se entregan cuando no hay RPC pendiente, para priorizar ejecución;
las desconexiones repetidas se limitan a un aviso por minuto. Un mensaje de señal
no confirma fill: el retcode/deal posterior es su evidencia. La evaluación sigue
en el worker local; el EA transporta instrucciones y muestra el registro.

`data/copy_trading.sqlite3`: sesiones, cuentas, claves hasheadas, eventos y acciones.
`data/copy_logs/{account_id}.log`: errores del proceso local. Son archivos locales
excluidos de Git. Las sesiones conservan una copia del algoritmo al iniciarse.

API de ejecución común: POST `/api/execution/start`, GET `/api/execution/sessions`
y POST `/api/execution/sessions/{id}/{pause|resume|close-stop}`.
La batería automatizada usa SQLite temporal y bróker simulado, sin iniciar MT5:

```powershell
python -X utf8 -m pytest test_execution_flow.py test_ea_diagnostic.py test_indicator_audit.py test_copy_trading.py test_complete_suite.py test_nuevos_operadores.py test_workspace_features.py -q
```

Reinicia el backend y recarga Ctrl+F5 después de actualizar para cargar el nuevo flujo.

## Evidencia de ejecución del motor normal

`reports/mt5_execution_qa.json` conserva 27 comprobaciones reales de la demo:
los nueve modos de salida en BUY/SELL a mercado, cuatro pendientes LIMIT/STOP
y cinco casos de tamaño/multiplicador. Se usó el mismo `MT5Worker.algorithm`
de los algoritmos normales, con una señal de prueba forzada. Se verificaron
entrada, volumen, SL/TP, gestión y limpieza; **no significa que el mercado haya
disparado naturalmente cada salida**. Las 200 comprobaciones de indicadores
sobre datos del terminal verifican cálculo y causalidad, no equivalencia nativa
ni rentabilidad. `test_mt5_execution_semantics.py` prueba recorridos controlados
para breakeven, trailing, parciales, señal contraria, límite diario y velas.

Para repetir deliberadamente la batería real en una demo vacía:
`python -m reports.run_mt5_execution_qa --execute-demo`.
No ejecutar junto a una asignación activa. El runner verifica DEMO/HEDGING,
identidad y exclusividad, limita el lote y registra cada resultado; sin esa
opción solo consulta datos y audita indicadores.

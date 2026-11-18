# Motor genético → NinjaTrader: referencia y brecha de implementación

Estado actualizado: **ejecutor NT8 1.5.4-portfolio compilado y probado en simulación**, con varios símbolos
por cuenta local Simulator/Playback y un algoritmo por contrato. Mis algoritmos
y portafolios usan el mismo formulario de ejecución, mapeo explícito y contratos
enteros. Los pesos del portafolio distribuyen su presupuesto de riesgo. Reutiliza
el evaluador Python de MT5. PropPass no comparte una cuenta activa.

La ampliación multisímbolo recibió datos de MNQ, MYM y MGC y ejecutó una venta
Stop de oro por sus condiciones de ATR y RSI, con SL/TP nativos. La suscripción
se realiza fuera del bloqueo de los eventos de precios. El diagnóstico terminó
con 19 PASS y un breakeven SELL inconcluso por falta de condición favorable;
una comprobación nativa adicional de ese breakeven pasó. Se conservaron por
separado las evidencias y las reconciliaciones, sin repetir órdenes ambiguas.

PropPass cierra únicamente operaciones propias del grupo e instrumento aplicado,
excluyendo algoritmos del motor y exposiciones sin propiedad. La prueba con un
algoritmo abierto en SimAccount3 conservó posición y protecciones. El vínculo
activo se conserva; se archivó otro nunca utilizado. El informe reproducible
está en reports/INFORME_NINJA_PORTFOLIO_Y_PROPPASS.md.

Guardado: STX · Demo Ninja · 3 símbolos, id port_stx_demo_ninja_3_symbols:
NASDAQ→MNQ DEC26, US30→MYM DEC26, XAUUSD→MGC DEC26; Market/Limit/Stop y salidas
ATR_CLASSIC/TRAILING_ATR/BREAKEVEN; presupuesto total 3%, un contrato por símbolo.
Se guardó también STX · Test integral NinjaTrader (stx_nt8_audit_v1), perfil de
diagnóstico deliberado de 20 casos; requiere dos contratos para los parciales.
Sus entradas de prueba no representan señales de un algoritmo rentable.

Validación disponible: 32 indicadores y 200 combinaciones compatibles de operador
por instrumento pasaron auditorías sobre 1000 velas cerradas de MNQ, MYM y MGC
recibidas de NT8: 600 comprobaciones aprobadas.
El broker controlado cubre 54 combinaciones entrada/dirección/salida, gestión
trailing/breakeven/parcial/tiempo y cierre de todas las patas de un portafolio.
Se comprobó también en un broker MT5 controlado que dos instancias compradoras
repetidas y una vendedora sobre EURUSD mantienen identificadores y cierres separados.
La matriz controlada no equivale a 54 escenarios nativos separados; las operaciones
nativas están documentadas en el diagnóstico y no fueron con fondos reales.

Prueba en vivo: STX · Demo Ninja · MACD M30, generado por el motor (200 candidatos,
25 aprobados). Sim101 compró 1 MNQ DEC26 a 27227 por MACD histograma > 0 sobre
una vela M30 cerrada. NT8 aceptó SL 26989.5 y TP 27702 con OCO. El botón de cerrar
y detener canceló ambas protecciones y confirmó el cierre a 27220.75. Sesión
0fe2de279f88401bac2abedffe9c8052, terminada flat. No fue un cierre por señal ni
por alcanzar SL/TP. Score de búsqueda 75.4; holdout positivo en el histórico
NASDAQ usado. Estas métricas no son un backtest específico del futuro MNQ.

No se habilitaron varios algoritmos sobre el mismo contrato de una cuenta neta.
Las reglas incompatibles se rechazan al asignar. Limit/stop, modificación y
cancelación, parciales, SL/TP, breakeven y trailing tienen evidencia nativa.
MTF, calendarios, carga prolongada y parametrizaciones exhaustivas requieren
ampliar la matriz; las pruebas actuales no certifican todas las combinaciones. Los apartados siguientes documentan el diseño
y la validación que falta ampliar.

## Referencias públicas revisadas

- https://tradingnote.co/es/docs/instalacion-ninjatrader
  NT8 se enlaza mediante un AddOn y debe permanecer abierto y conectado.
- https://tradingnote.co/es/docs/live-trading
  La plataforma describe operación manual y automática sobre conexiones como NT8;
  las decisiones usan datos de la conexión de la cuenta elegida.
- https://tradingnote.co/es/docs/portafolios
  Los algoritmos guardados se combinan y se activan desde sesiones de portafolio.
- https://tradingnote.co/es/docs/del-backtest-al-vivo
  Documenta sesiones, MTF y modos de salida, y advierte que el cierre parcial
  completo sigue en validación en brokers reales. Por ello no constituye prueba
  de que todas las combinaciones tengan ejecución idéntica en cada plataforma.

## Diseño para Stratix

Mantener la asignación directa desde Mis Algoritmos y la asignación de portafolios,
como pidió el usuario. El tipo de cuenta determina el adaptador: EA para MT5,
AddOn para NT8. PropPass conserva su función específica y su cola de grupos.

Reutilizar el evaluador Python de señales existente con velas cerradas provenientes
DE NT8. No duplicar los 32 cálculos en C# ni sustituirlos por indicadores nativos
con fórmulas potencialmente distintas. La igualdad de cálculo no garantiza
igualdad de resultados si cambian datos, sesiones, volumen o contratos.

El adaptador NT8 debe aportar histórico cerrado y cotizaciones, metadatos del
contrato (tick size/point value/vencimiento), ejecución de órdenes, fills,
modificación/cancelación y reconciliación. Debe mantener SL/TP nativos con OCO y
atribuir órdenes a su sesión. Los contratos son enteros: un cierre parcial que
no alcance un contrato no puede redondearse arbitrariamente.

La asignación necesita validar el instrumento real y el sizing: NASDAQ CFD y NQ
no son el mismo contrato. No transformar lotes FX en contratos de futuros sin
una equivalencia y un riesgo explícitos. La cuenta/instrumento necesita un único
responsable de ejecución: evitar que Candle y otro algoritmo gestionen la misma
posición neta. Para varios algoritmos sobre un mismo futuro falta contabilidad
de posiciones virtuales y reconciliación con la posición neta del broker.

## Inventario actual y validación necesaria

El inventario generado está en reports/ninja_genetic_execution_inventory.json:
32 indicadores, 10 operadores, 3 entradas y 9 modos de salida del motor.
Su presencia en el catálogo NO implica ejecución general NT8 habilitada.

Además de mercado/limit/stop en ambas direcciones, hay que verificar trailing,
breakeven, parciales, tiempo, estructura, ATR suavizado, MTF, horarios, sizing,
cancelaciones, rechazos, fills parciales y recuperación sin repetir órdenes.

La inspección de copy_trading.compatibility también revela límites existentes
en MT5: averaging/DCA, sizing dinámico por racha y ciertos topes semanales,
mensuales y por racha están bloqueados. Por tanto la meta «todo lo del motor»
requiere cerrar brechas de ejecución, no solo añadir NinjaTrader al selector.

Cada función debe publicar por separado si está calculada, ejecutable y validada
por plataforma. Una función pendiente debe bloquear la asignación con una razón
concreta; nunca ignorar sus reglas ni presentar un algoritmo diferente como
compatible.

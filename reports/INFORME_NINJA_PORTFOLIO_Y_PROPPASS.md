# Pruebas NinjaTrader y aislamiento de PropPass

Fecha: 18/11/2026. AddOn cargado: 1.5.4-portfolio. Todas las operaciones fueron en cuentas locales simuladas.

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
| 1 | MARKET | BUY | CLOSE | PASS |
| 2 | MARKET | BUY | PARTIAL | PASS |
| 3 | MARKET | BUY | MODIFY | PASS |
| 4 | MARKET | BUY | TIME | PASS |
| 5 | MARKET | BUY | SL | PASS |
| 6 | MARKET | BUY | TP | PASS |
| 7 | MARKET | BUY | BREAKEVEN | PASS |
| 8 | MARKET | BUY | TRAILING | PASS |
| 9 | MARKET | SELL | CLOSE | PASS |
| 10 | MARKET | SELL | PARTIAL | PASS |
| 11 | MARKET | SELL | MODIFY | PASS |
| 12 | MARKET | SELL | TIME | PASS |
| 13 | MARKET | SELL | SL | PASS |
| 14 | MARKET | SELL | TP | PASS |
| 15 | MARKET | SELL | BREAKEVEN | INCONCLUSIVE |
| 16 | MARKET | SELL | TRAILING | PASS |
| 17 | LIMIT | BUY | MODIFY_CANCEL | PASS |
| 18 | LIMIT | SELL | MODIFY_CANCEL | PASS |
| 19 | STOP | BUY | MODIFY_CANCEL | PASS |
| 20 | STOP | SELL | MODIFY_CANCEL | PASS |

El caso de breakeven BUY se confirmó contra el registro nativo: el stop fue aceptado al precio de entrada y ejecutado antes del siguiente pulso. Se corrigió esa carrera del acuse, sin repetir la orden. El primer intento de modificar una pendiente coincidió con su activación: se archivó, se confirmó el rechazo anterior al cambio y se repitió con una nueva intención después de verificar la cuenta flat. Los cuatro casos finales de pendientes pasaron.

Los casos TIME del diagnóstico prueban un cierre programado. La salida del motor tras X velas se probó con recorridos controlados. Breakeven significa mover el SL a la entrada: el fill puede tener deslizamiento o comisiones.

## Uso y límites

En Mis portafolios, abre **STX · Demo Ninja · 3 símbolos**, pulsa ejecutar, selecciona la cuenta NinjaTrader, revisa las tres equivalencias y los contratos, y sigue su registro. En Mis algoritmos también está **STX · Test integral NinjaTrader**; requiere dos contratos para probar parciales. Sus entradas son deliberadas y no representan señales de inversión.

En NT8 se permite un algoritmo por contrato distinto dentro del portafolio. No está habilitada la mezcla de algoritmos sobre el mismo contrato neto. En MT5 hedging se comprobó en broker controlado la convivencia de instancias repetidas y direcciones opuestas sobre el mismo símbolo.

Estas pruebas validan funciones concretas, no rentabilidad ni todas las combinaciones de parámetros. MTF nativo, calendarios y cargas prolongadas requieren ampliar la matriz. DCA, martingala y otros límites no implementados siguen rechazándose al asignar.

Evidencia detallada: `ninja_portfolio_final_verified.json`, `proppass_close_scope_verified.json`, `ninja_short_breakeven_live.json` y archivos de reconciliación en esta carpeta.

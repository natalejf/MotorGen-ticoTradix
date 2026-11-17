# Verificación de ejecución MT5 — 17/11/2026

Cuenta demo hedging verificada; EURUSD → EURUSDm. Copy diferido por indicación del usuario.

| Batería | Resultado | Qué demuestra |
|---|---|---|
| Motor normal, operaciones reales | 27/27 PASS | BUY/SELL, MARKET/LIMIT/STOP, nueve configuraciones de salida, tamaños y multiplicadores; entrada, protección, gestión y limpieza |
| Indicadores y operadores sobre velas cerradas MT5 | 200/200 PASS; 32 indicadores | Cálculo, evaluación y causalidad en los parámetros auditados |
| STX · Test integral demo, repetición visible | 15 PASS, 0 FAIL, 5 INCONCLUSIVE | Cierres completos/parciales, cambios SL, tiempo, trailing, breakeven SELL y cuatro pendientes modificadas/canceladas |
| Regresión aislada anterior | 145 PASS | Flujo, límites, reglas, transporte y motor |
| Última verificación específica | 23 PASS | Incluye nuevo rechazo previo de lote indivisible en salidas parciales |

## Inconclusos reales

- BUY SL: Tiempo agotado sin condición de precio confirmada; se limpia el caso.
- BUY TP: Tiempo agotado sin condición de precio confirmada; se limpia el caso.
- BUY BREAKEVEN: Posición cerrada sin motivo esperado confirmado en historial MT5.
- SELL SL: Tiempo agotado sin condición de precio confirmada; se limpia el caso.
- SELL TP: Tiempo agotado sin condición de precio confirmada; se limpia el caso.

Una condición de precio no alcanzada no equivale a una prueba aprobada. El breakeven BUY terminó con la posición cerrada sin confirmar la modificación esperada. Las configuraciones de salida de la batería normal se comprobaron con órdenes reales, pero sus 27 PASS no significan que todas las salidas se activaran naturalmente. Los recorridos controlados comprueban la lógica separadamente. No certifica rentabilidad, todos los parámetros posibles ni equivalencia numérica de todos los indicadores nativos.

## Correcciones

- Cola del EA indexada: el polling ya no recorre el historial completo de comandos.
- Lecturas con reintento limitado; ninguna repetición automática de order_send incierto.
- OrderCheck se realiza antes de marcar una mutación en envío; un fallo de lectura no simula una orden enviada.
- Tamaño por riesgo y por dinero fijo aplica el multiplicador; lote fijo conserva su semántica.
- TIME_EXIT cuenta velas cerradas; límite diario de entradas y mínimo beneficio/riesgo respetados.
- LIMIT/STOP del motor normal con expiración de bróker y protección contra duplicados.
- Parcial de una sola ejecución; rechazo previo si el lote no permite dividirse.
- Reglas sin soporte (DCA/averaging, rachas, límites semanales/mensuales) se rechazan explícitamente al asignar; no se ignoran.

STX · Test integral demo está guardado en Mis algoritmos → Pruebas demo. Su última sesión terminó STOPPED. Verificados 0 posiciones y 0 pendientes al finalizar. EA actualizado y compilado sin errores/advertencias. El conector queda disponible; no queda ningún algoritmo operando.

Evidencia: `mt5_execution_qa.json`, `mt5_saved_diagnostic_retest.json`, `mt5_bridge_live_reads.json`. El último registra 30 lecturas reales sin fallos (mediana 1.52 s), no una garantía de latencia futura.

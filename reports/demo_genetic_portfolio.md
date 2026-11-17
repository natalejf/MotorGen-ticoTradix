# Algoritmos y portafolio conectados a demo — 17/11/2026

Se completaron tres búsquedas genéticas de 160 evaluaciones cada una sobre EURUSD M30. 
Histórico local: 2.792 velas, 25/08/2026–17/11/2026; 20% reservado. Costes: spread 1 pip y deslizamiento 0,2 pips. 
Clasificación demo: al menos 20 operaciones, WR 45%, PF 1,15, Sharpe 0,5, beneficio positivo y DD hasta 15%; DSR no exigido. 
Se eligieron candidatos compatibles con MT5 y revisión positiva en el tramo reservado. Como ese tramo intervino en la selección, no es una validación final independiente.

## Guardado

- Demo realista · Lote 1 Tendencia: 2 algoritmos.
- Demo realista · Lote 2 Momentum: 2 algoritmos.
- Demo realista · Lote 3 Estructura: 3 algoritmos.

Portafolio: **STX · Demo realista · 3 lotes**, guardado en Pruebas demo; tres algoritmos con pesos iguales.

| Algoritmo | Score del motor | Beneficio en tramo reservado (USD) | Operaciones en tramo reservado |
|---|---:|---:|---:|
| STX Demo L1.2 Tendencia · EURUSD M30 | 95.4 | 23.08 | 12 |
| STX Demo L2.1 Momentum · EURUSD M30 | 92.2 | 27.35 | 11 |
| STX Demo L3.3 Estructura · selección MT5 | 92.7 | 33.25 | 48 |

Los otros candidatos de score superior con tramo reservado negativo se conservaron en sus lotes, pero se excluyeron del portafolio. Las cifras son backtests, no rentabilidad futura. El portafolio usa un solo símbolo: la separación por familias no asegura diversificación.

## Evidencia real MT5

- Algoritmo individual score 92,7: señal SELL original sobre velas cerradas del terminal. OrderSend confirmado, ticket 756936376, 0,03 lotes. Sesión detenida con cierre confirmado antes de asignar el portafolio.
- Portafolio: sesión `1af44c9d62104b12bc3b7844b40e95ef`, estado **ACTIVE**, demo verificada. Presupuesto de riesgo 0,3% del equity, repartido entre tres pesos iguales (~0,1% por entrada antes de redondeo del bróker).
- Posiciones verificadas al finalizar la prueba:
  - Ticket 756937698: SELL EURUSDm, 0.02 lotes; SL 1.10068, TP 1.09471.
  - Ticket 756937903: SELL EURUSDm, 0.03 lotes; SL 1.09985, TP 1.09508.

El algoritmo de tendencia espera su señal: estar asignado no obliga a operar. No se forzaron condiciones ni se enviaron órdenes manuales. El portafolio permanece activo; su gestión dinámica requiere aplicación, terminal y EA encendidos.

## Corrección necesaria del motor

Se corrigió que los límites por rachas en 0 se aleatorizaran y que averaging desactivado pudiera generarse de todos modos. Los candidatos guardados se generaron después de la corrección, conservando sus reglas y métricas.

Evidencia detallada: `demo_genetic_portfolio.json`.

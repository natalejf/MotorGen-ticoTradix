# Prueba cruzada en terminales demo

Sesión del 18 de noviembre de 2026 (hora Argentina). Se enviaron órdenes reales
a una cuenta MT5 demo hedging y al simulador Sim101 de NinjaTrader. No se
operaron cuentas de examen ni reales. RocketPass conserva M5 cierre / EMA20.

| Caso | MT5 → NinjaTrader | NinjaTrader → MT5 |
|---|---|---|
| Apertura de mercado | Aprobado | Aprobado |
| Cambio de SL y TP | Aprobado | Aprobado |
| Cierre parcial y cierre del remanente | Aprobado | Aprobado tras corrección |
| Buy Limit: alta, cambio, cancelación | Aprobado | Aprobado |
| Sell Limit: alta, cambio, cancelación | Aprobado | Aprobado |
| Buy Stop: alta, cambio, cancelación | Aprobado | Aprobado |
| Sell Stop: alta, cambio, cancelación | Aprobado | Aprobado |
| Ejecución de pendiente sin duplicar y cierre | Aprobado | Inconcluso: no se alcanzó el stop de origen |

Instrumentos: USTECm y MNQ DEC26. Tamaño fijo destino: 2 contratos hacia
NinjaTrader; 0,10 lotes hacia MT5. El parcial dejó 1 contrato / 0,05 lotes.
Esta configuración es un ejemplo verificado, no una equivalencia económica
universal. Protecciones traducidas por distancias, escala 1.

## Correcciones verificadas

- MT5 cambió el comentario de la posición remanente después del parcial.
  El seguimiento ahora conserva ticket e identificador de posición, además
  de la etiqueta y el magic. Se repitió el ciclo Ninja → MT5 completo y pasó.
- NinjaTrader ahora limpia la confirmación del cierre parcial anterior antes
  de aceptar el siguiente cierre, e impide dos cierres simultáneos.
- La observación de pendientes creadas por el puente nativo publica su SL/TP.
- Las sesiones nativas que confirmaron su entrada y luego quedaron vacías
  se liberan para no acumular consultas por cada operación histórica.

Validación adicional: 47 pruebas automáticas de copy, pendientes, cruce y
ejecución Ninja aprobadas; compilación aislada de ambos servicios con las
referencias instaladas de NinjaTrader aprobada. El AddOn Stratix fue compilado
y utilizado dentro de NinjaTrader durante la prueba.

Al terminar se verificaron MT5 sin posiciones ni pendientes y Sim101 flat,
sin órdenes activas. Las asignaciones QA quedaron detenidas. Se restauró el
estado ACTIVE que tenía el algoritmo de usuario antes de suspenderlo para QA.
Los resultados detallados y las copias de seguridad de conectores permanecen
en `data/copy_logs`, excluidos de Git.

## Para repetir desde el panel

1. Ejecuta `python run.py` y abre el panel local. Mantén MT5 con su EA y
   NinjaTrader con StratixCandleService conectados al backend local.
2. En Copy registra la cuenta master y agrega la seguidora; usa una sola
   dirección activa para ese par de cuentas. La seguidora debe estar libre
   de otra asignación y, en NinjaTrader, flat y sin órdenes.
3. Mapea el símbolo y vencimiento exactos; configura tamaño destino, límite
   de riesgo y escala de distancias. Las asignaciones comienzan pausadas.
4. Activa y abre una operación NUEVA en la master con SL y TP identificables.
   Las operaciones preexistentes y las observadas durante una pausa no se
   importan. Revisa tickets y registro de la seguidora.

MT5 → MT5 y Ninja → Ninja no se probaron por falta de segundas cuentas.
La compatibilidad con ATM manuales concretos y la ejecución de pendiente
Ninja → MT5 siguen pendientes. Los precios de ambos mercados son distintos:
una pendiente puede ejecutarse en uno antes que en el otro; no se garantiza
ejecución simultánea ni se fuerza una entrada a mercado para alcanzarla.
Stop Limit no se admite. El copy nativo continúa limitado a Simulator/Playback;
esta prueba no habilita cuentas de fondeo NinjaTrader.

GitHub Pages es una vista estática de demostración. La ejecución depende del
servidor y los terminales locales. Consulta [COPY_TRADING.md](../COPY_TRADING.md)
para los límites y configuración completa.

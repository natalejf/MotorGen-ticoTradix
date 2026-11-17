# Rendimiento del motor y mezclas aleatorias

Comparación local: mismos 12 candidatos por grupo, semilla 410, 4.000 velas EURUSD/H1 y cProfile activo en ambas mediciones. Los tiempos son orientativos y dependen del equipo. No hubo órdenes a MT5.

| Mezcla | Antes (s) | Después (s) | Aceleración | Con operaciones antes/después |
|---|---:|---:|---:|---:|
| compact | 2.99 | 2.17 | 1.38× | 8/8 |
| broad | 3.12 | 2.20 | 1.42× | 9/9 |
| structural | 7.68 | 2.00 | 3.84× | 11/11 |

## Exploraciones en vivo por API

Instancia aislada en localhost:8013, histórico completo EURUSD/H1 guardado. Siete escenarios con clasificación por defecto; dos controles explícitamente permisivos para verificar aprobación y validadores. Los controles no modificaron la configuración del usuario ni prueban rentabilidad.

| Escenario | Creadas | Aprobadas | Sin operaciones | Tiempo (s) | Primera creada (s) |
|---|---:|---:|---:|---:|---:|
| compact | 24 | 0 | 0 | 8.48 | 0.36 |
| momentum | 24 | 0 | 0 | 7.11 | 0.39 |
| structural | 24 | 0 | 0 | 9.89 | 0.91 |
| broad_stress | 24 | 0 | 4 | 12.23 | 0.59 |
| all_operators | 24 | 0 | 1 | 11.44 | 0.28 |
| equality_only | 24 | 0 | 22 | 6.30 | 0.33 |
| validators_on | 24 | 0 | 0 | 9.31 | 0.34 |
| pipeline_control | 24 | 19 | 1 | 9.61 | 0.39 |
| validator_control | 4 | 4 | 0 | 10.00 | 0.28 |

Total de la batería final: 196 evaluaciones, sin errores de exploración.

Los siete escenarios con filtros normales no aprobaron candidatos. La falta de aprobadas se explica por los filtros medidos (principalmente DSR, Sharpe, win rate y beneficio), no por ausencia de creación. Igualdad sola produjo 22 candidatos sin operaciones de 24; no se recomienda como mezcla general. Los dos controles comprueban que los caminos de aprobación y validación siguen funcionando.

## Cambios

- Selección Fisher–Yates: 3–5 indicadores en total de familias distintas, una entrada, 1–2 salidas. Si los operadores personalizados solo admiten menos familias, se eligen únicamente indicadores compatibles.
- Máximo inicial de 2 condiciones por algoritmo; el usuario puede ampliar manualmente.
- WMA/HMA y RCI vectorizados; rangos, warmup, NaN, empates y causalidad cubiertos por pruebas de equivalencia.
- Timestamps convertidos una vez por backtest. Se conserva la caché con huella completa de datos.
- Evaluación serial publica cada candidato y progreso antes de terminar el lote; detención se comprueba entre candidatos.
- Igualdad tiene menos peso si se habilitan otros operadores; igualdad sola sigue disponible.
- Motivos de descarte y candidatos sin operaciones visibles en el panel.
- Los filtros de clasificación y validación del producto se conservan.

Archivos detallados: live_search_results.json, search_baseline_profile.txt, search_optimized_profile.txt.

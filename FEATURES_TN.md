# Funciones TN completadas

Temporalidades admitidas: **30m, 1h, 4h, 1d**. El modelado `ohlc_m1`
es una trayectoria sintética dentro de una vela, no una temporalidad descargable.
Cuotas y cola (S) quedan fuera del alcance por decisión del usuario.

## Clasificación

Exploraciones nuevas: Sharpe mínimo 1.2, drawdown máximo 15%, win rate mínimo
50%, DSR mínimo 0.3. `/api/config-defaults` publica `classification_defaults`.

## Macro FRED

`GET /api/macro-series` publica 29 series en 14 categorías, rangos de umbrales
en unidades originales, estado de caché y `publication_lag_days`. Los indicadores
`MACRO_*` se generan desde el mismo catálogo; se pueden seleccionar series
individuales o añadir una categoría completa desde la configuración.

Los documentos TN disponibles en `tn_docs/es_docs_explorar-indicadores.txt`
describen once categorías y ejemplos, no un catálogo exacto de 29 IDs. Se preservan
los IDs locales y se completa la cobertura con tasas internacionales, vivienda,
crédito y fiscal. Esto no afirma equivalencia exacta con un catálogo TN privado.
Fuentes y unidades: https://fred.stlouisfed.org/series/ECBDFR,
https://fred.stlouisfed.org/series/BOGMBASE,
https://fred.stlouisfed.org/series/GFDEGDQ188S.

La alineación usa la última publicación disponible en cada timestamp de vela.
Sin publicación previa devuelve NaN (no rellena con datos futuros), incluso
para múltiples velas intradía. `align_to_index(..., published_at=...)` admite
fechas reales de publicación. Sin ese calendario usa retrasos conservadores
desde el inicio del período observado: diaria 2 días, semanal 8, mensual 65,
trimestral 125, anual 400, definidos en el catálogo por serie. No son calendarios
reales verificados ni corrigen revisiones históricas del CSV de FRED: para una
reconstrucción estricta punto-en-el-tiempo se requieren vintages ALFRED.
No se fabrican series si descarga y caché fallan; se informa el error.
Las cachés anteriores a este cambio deben renovarse si procedían del antiguo
fallback sintético. Series discontinuadas conservan su último valor publicado.

## Sesiones

El panel «Espacio de trabajo» permite guardar, listar, abrir, renombrar, eliminar
y reanudar sesiones. Guarda configuración validada, selección/campos de UI,
candidatos completos, métricas y contadores. Persistencia: `data/sessions/*.json`,
con escritura atómica. Rutas `/api/sessions`, `/api/sessions/{id}` y acciones
`/{id}/open`, `/{id}/resume`.

Abrir restaura resultados sin ejecutar una exploración. Reanudar conserva los
candidatos y arranca una población nueva con esa configuración; no restaura
el estado aleatorio ni la población exacta de una ejecución interrumpida.
Detener la búsqueda activa antes de abrir o reanudar una sesión.

## Interfaz

Progreso visible en porcentaje (ronda actual para genético infinito); pills para
29 símbolos; vista grid/lista en resultados conservada en el navegador;
doble clic en nombres de candidatos, estrategias guardadas y portafolios
guardados para renombrar; validación de configuración mínima antes de explorar;
slider Neural Explorer de 0.25× a 3×.

## Riesgo de portafolios

En «Espacio de trabajo» seleccionar un portafolio guardado y calcular matriz y
Monte Carlo. `POST /api/portfolio/{id}/risk` admite `simulations` (100–10000),
`initial_capital`, `ruin_drawdown_pct`, `block_size` (1–60 días) y `seed`.
No guarda ni modifica el portafolio. Usa equity histórica disponible o recalcula
componentes; alinea retornos diarios por fecha en su calendario común. No usa la
antigua equity combinada basada en posiciones proporcionales de los arrays.

La simulación remuestrea bloques comunes de retornos preservando dependencia
entre componentes. Muestra matriz/heatmap (N/D si varianza cero), equity final y
DD máximo p5/p50/p95, bandas de equity y probabilidad de alcanzar el umbral de
DD definido como ruina. Falla claramente si no hay historia común suficiente.

## IDE

Monaco 0.52.2 vía jsDelivr, con editor de texto alternativo sin conexión. Abrir
una estrategia, editar JSON/texto/código, guardar versiones y consultar/restaurar
su contenido desde el historial. Al abrir de nuevo se carga la última versión.
`GET/POST /api/editor/{strategy_id}/versions`; `data/editor/*.json`.
Las versiones son borradores del editor: no se ejecutan ni reemplazan
automáticamente las reglas de una estrategia activa.

## Verificación

Python 3.10: `python -X utf8 -m pytest test_complete_suite.py test_nuevos_operadores.py test_workspace_features.py -q`.
También `python -m pyflakes backend`, `node --check frontend/app.js`,
`node --check frontend/workspace.js` y smokes A/B/C/E/F/H+L/K.
Las cachés, sesiones, versiones y artefactos personales no se suben a GitHub.

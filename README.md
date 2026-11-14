# TradingNote · Motor Genético & Creador de Algoritmos (Replica)

Replica completa del motor genético, creador de algoritmos y laboratorio de **TradingNote** ([https://tradingnote.co/es/docs](https://tradingnote.co/es/docs)), implementado con una estética monocromática elegante (blanco, negro y gamas de grises), arquitectura de alto rendimiento en Python / FastAPI y visualizaciones interactivas (Chart.js y Three.js 3D).

---

## 🚀 Características Principales

### 1. Datos Históricos & Auto-Actualizador (1 a 5 Años en H1, H4 y D1)
- **Pares Principales Soportados**:
  - `XAUUSD` (Oro spot / futuros)
  - `NASDAQ` (NQ=F / E-mini Nasdaq 100)
  - `EURUSD`, `USDJPY`, `AUDUSD`, `GBPUSD` (Divisas Forex principales)
  - `US30` (Dow Jones Industrial)
  - `BTCUSD` (Bitcoin / USD)
- **Resolución**:
  - **H1 (1 Hora)**: ~14.000 a 17.500 velas (~2 años continuos sin huecos).
  - **H4 (4 Horas)**: Remuestreo exacto con OHLCV de alta precisión (~4.400 velas).
  - **D1 (Diario)**: 5 años completos (2021 a 2026).
- **Auto-Actualización Diaria**:
  - Servicio en segundo plano (`auto_updater.py`) que descarga las velas recién cerradas al finalizar cada sesión y las concatena automáticamente sin duplicados.
  - Botón interactivo en la interfaz para forzar la actualización de todos los pares en 1 clic.

---

### 2. Motor Genético & Algorítmico
- **Población & Cromosomas**:
  - Cada algoritmo es un genoma compuesto por reglas lógicas de entrada (1 a 3 condiciones booleanas combinadas), dirección (Buy / Sell / Both), filtros de sesión/horario, modelos de salida y gestión de riesgo.
- **Operadores Genéticos**:
  - **Selección por Torneo**: Selección de los mejores individuos preservando diversidad génica.
  - **Cruce (Crossover)**: Mezcla reglas de compra de un padre con reglas de salida y gestión del otro.
  - **Mutación**: Deriva gaussiana de parámetros numéricos, alteración de multiplicadores ATR, cambio aleatorio de operadores y sustitución de indicadores.
  - **Elitismo**: Preservación del 10% superior de candidatos a través de generaciones.
- **11 Objetivos de Optimización (Fitness)**:
  - *Score Balanceado (TN Score 0-100)*: Mezcla ponderada de Sharpe (30%), Calmar (25%), Profit Factor (20%), Win Rate (15%) y suficiencia estadística (10%).
  - *Mayor Sharpe Ratio, Sortino, Calmar, PnL Absoluto, Menor Drawdown, Profit Factor, Expectancy, Win Rate, Recovery Factor y Pass Rate de Fondeo*.

---

### 3. Universo de 28 Indicadores Técnicos & Rangos
Implementación vectorizada ultrarrápida con caché en memoria:
- **Tendencia**: EMA, SMA, DEMA, TEMA, HMA, WMA, KAMA, SuperTrend.
- **Momentum**: RSI, Stochastic (%K, %D), MACD, CCI, ROC, Williams %R.
- **Volatilidad**: Bandas de Bollinger, ATR, Canales de Keltner, Canales de Donchian, Desviación Estándar.
- **Ciclo & Estructural**: RCI (Rank Correlation Index de Spearman - indicador estrella de TradingNote), ADX (+DI, -DI), Parabolic SAR, Ichimoku Cloud.
- **Volumen**: Volume SMA, OBV, Chaikin Money Flow (CMF), Money Flow Index (MFI).
- **Barrido de Rangos**: Cada indicador cuenta con controles `[Desde / Pasos / Hasta]` y un **Contador de Combinaciones Posibles en Tiempo Real**.

---

### 4. Salidas, Gestión de Riesgo & Horarios
- **Modos de Salida**:
  - ATR Clásico (`slAtr` / `tpAtr`)
  - Trailing Stop Dinámico por ATR (`trailAtr`)
  - Breakeven Automático (`beActivationAtr`)
  - Estructura Swing (máximo/mínimo de últimas N velas)
  - Salida por Tiempo (cierre forzado tras N barras)
  - Take Profit Parcial
- **Controles de Cuentas de Fondeo (Prop Firms)**:
  - Pérdida Máxima Diaria (`maxDailyLossPct` 1-5%)
  - Drawdown Total Máximo (`maxAccountLossPct` 5-15%)
  - Máximo de Operaciones Diarias
  - Cierre obligatorio antes del fin de semana (Viernes 20:00 UTC)
- **Modelos de Sizing**: Riesgo Fijo %, Lote Fijo, Martingala, Anti-martingala y DCA.

---

### 5. Batería de Validación & Filtros Anti-Overfitting
- **Deflated Sharpe Ratio (DSR)**:
  - Fórmula matemática de Bailey & Marcos López de Prado (2014) para penalizar el Sharpe en función del número $N$ de combinaciones probadas.
- **Walk-Forward Analysis (WFA)**:
  - División en ventanas deslizantes (In-Sample vs Out-of-Sample).
  - Cálculo de la eficiencia WFE ($OOS / IS$) y concatenación de la curva de capital fuera de muestra.
- **Multiverso Sintético (Monte Carlo)**:
  - Generación de 80 a 500 universos de mercado sintéticos mediante block-bootstrap que preservan la volatilidad y saltos del activo.
  - Medición del % de universos rentables y distribución de drawdowns en percentil 95.
- **Simulador de Fondeo Prop Firm**:
  - Calcula el pass rate real del reto (8% beneficio, 4% pérdida diaria, 8% drawdown total).

---

### 6. Visualización 3D: Neural Explorer & Monocromía
- **Diseño Monocromático**:
  - Paleta de negros puros (`#000000`, `#08080a`), fondos grafito (`#101014`), bordes zinc sutiles (`#24242a`) y blancos nítidos (`#ffffff`).
- **Neural Explorer 3D**:
  - Renderizado interactivo con Three.js que visualiza cada algoritmo como un nodo en una esfera 3D, conectando linajes con axones de mutación y emitiendo destellos de luz para los algoritmos aprobados.
- **Exportador a Producción**:
  - Descarga directa a **MetaTrader 5 Expert Advisor (.mq5)**, **Python autónomo (.py)** y **JSON**.

---

## 💻 Instalación y Uso

### 1. Iniciar el Servidor y la Interfaz
Simplemente ejecuta:
```bash
python run.py
```
O en Windows haz doble clic sobre:
```bash
start.bat
```
El servidor se iniciará en `http://127.0.0.1:8000` y abrirá tu navegador automáticamente.

### 2. Auto-Actualizador de Datos en Segundo Plano
Para mantener los datos siempre al día de forma desatendida:
```bash
python auto_updater.py
```
El servicio descargará las últimas velas de los 8 pares cada día al cierre de la sesión de Nueva York y cada 6 horas.

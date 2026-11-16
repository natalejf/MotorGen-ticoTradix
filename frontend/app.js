/**
 * TradingNote Genetic Engine Replica - Frontend Application
 * State management, live polling, chart rendering, and 3D Neural Explorer.
 */

// All 28 Indicators Meta with Generic Defaults
const ALL_28_INDICATORS_CONFIG = {
  // Tendencia (8)
  EMA: { name: 'Media Móvil Exponencial (EMA)', family: 'Tendencia', from: 10, step: 10, to: 200, unit: 'período' },
  SMA: { name: 'Media Móvil Simple (SMA)', family: 'Tendencia', from: 20, step: 20, to: 200, unit: 'período' },
  DEMA: { name: 'Doble Media Exponencial (DEMA)', family: 'Tendencia', from: 9, step: 5, to: 100, unit: 'período' },
  TEMA: { name: 'Triple Media Exponencial (TEMA)', family: 'Tendencia', from: 9, step: 5, to: 100, unit: 'período' },
  HMA: { name: 'Hull Moving Average (HMA)', family: 'Tendencia', from: 9, step: 3, to: 50, unit: 'período' },
  WMA: { name: 'Media Ponderada Lineal (WMA)', family: 'Tendencia', from: 10, step: 5, to: 100, unit: 'período' },
  KAMA: { name: 'Kaufman Adaptive (KAMA)', family: 'Tendencia', from: 10, step: 5, to: 50, unit: 'período' },
  SUPERTREND: { name: 'SuperTrend ATR Channel', family: 'Tendencia', from: 7, step: 7, to: 21, unit: 'período' },

  // Momentum (6)
  RSI: { name: 'Relative Strength Index (RSI)', family: 'Momentum', from: 7, step: 7, to: 28, unit: 'período' },
  STOCHASTIC: { name: 'Oscilador Estocástico (%K & %D)', family: 'Momentum', from: 9, step: 3, to: 21, unit: 'k_period' },
  MACD: { name: 'MACD (Histograma & Señal)', family: 'Momentum', from: 8, step: 2, to: 16, unit: 'fast' },
  CCI: { name: 'Commodity Channel Index (CCI)', family: 'Momentum', from: 14, step: 6, to: 40, unit: 'período' },
  ROC: { name: 'Rate of Change (ROC)', family: 'Momentum', from: 8, step: 4, to: 24, unit: 'período' },
  WILLIAMS_R: { name: 'Williams %R', family: 'Momentum', from: 10, step: 4, to: 28, unit: 'período' },

  // Volatilidad (5)
  BOLLINGER: { name: 'Bandas de Bollinger (%B)', family: 'Volatilidad', from: 10, step: 10, to: 50, unit: 'período' },
  ATR: { name: 'Average True Range (ATR)', family: 'Volatilidad', from: 10, step: 2, to: 24, unit: 'período' },
  KELTNER: { name: 'Canales de Keltner (EMA ± ATR)', family: 'Volatilidad', from: 10, step: 5, to: 40, unit: 'período' },
  DONCHIAN: { name: 'Canales de Donchian (High/Low)', family: 'Volatilidad', from: 10, step: 5, to: 50, unit: 'período' },
  STDDEV: { name: 'Desviación Estándar de Cierre', family: 'Volatilidad', from: 10, step: 5, to: 50, unit: 'período' },

  // Volumen (4)
  VOLUME_SMA: { name: 'Media Móvil de Volumen (SMA)', family: 'Volumen', from: 10, step: 5, to: 50, unit: 'período' },
  OBV: { name: 'On-Balance Volume (OBV)', family: 'Volumen', from: 1, step: 1, to: 1, unit: 'acumulado' },
  CMF: { name: 'Chaikin Money Flow (CMF)', family: 'Volumen', from: 10, step: 5, to: 40, unit: 'período' },
  MFI: { name: 'Money Flow Index (MFI)', family: 'Volumen', from: 10, step: 4, to: 28, unit: 'período' },

  // Ciclo & Estructurales (5)
  RCI: { name: 'Rank Correlation Index (RCI Spearman)', family: 'Ciclo & Estructura', from: 7, step: 2, to: 21, unit: 'período' },
  ADX: { name: 'Average Directional Index (ADX)', family: 'Ciclo & Estructura', from: 10, step: 5, to: 25, unit: 'período' },
  PSAR: { name: 'Parabolic SAR (Aceleración)', family: 'Ciclo & Estructura', from: 0.01, step: 0.01, to: 0.04, unit: 'step' },
  ICHIMOKU: { name: 'Ichimoku Cloud (Kijun-sen)', family: 'Ciclo & Estructura', from: 9, step: 1, to: 26, unit: 'período' },
  AROON: { name: 'Aroon Oscillator (Up - Down)', family: 'Ciclo & Estructura', from: 10, step: 4, to: 25, unit: 'período' },

  // Precio / Breakout (4) — TN parity
  HIGHEST: { name: 'Máximo N períodos (Breakout)', family: 'Precio', from: 10, step: 5, to: 50, unit: 'período' },
  LOWEST: { name: 'Mínimo N períodos (Breakdown)', family: 'Precio', from: 10, step: 5, to: 50, unit: 'período' },
  PIVOT_POINTS: { name: 'Pivot Points Clásicos (PP/R/S)', family: 'Precio', from: 5, step: 1, to: 5, unit: 'sub niveles', discrete: 5 },
  VWAP: { name: 'VWAP (ponderado por volumen)', family: 'Precio', from: 1, step: 1, to: 1, unit: 'acumulado', discrete: 1 }
};

// Global State
const TIMEFRAMES = ['30m', '1h', '4h', '1d'];
const state = {
  activeTab: 'config',
  symbolsMeta: [],
  selectedSymbol: 'EURUSD',
  selectedTimeframe: '1h',
  // Multi-symbol / multi-timeframe exploration
  selectedSymbols: new Set(['EURUSD']),
  selectedTimeframes: new Set(['1h']),
  // Macro FRED
  macroCatalog: [],
  selectedMacro: new Set(),
  useMacro: false,
  searchMode: 'genetic',
  initialDeposit: 10000,
  
  // Enabled indicators map: { EMA: true, SMA: true, ... }
  enabledIndicators: {},

  // Indicator parameter metadata (from /api/config-defaults) + user-edited sweep ranges
  indicatorMeta: null,
  indicatorRanges: {},
  // User-edited exit/risk sweep ranges {param: {from, step, to}}
  exitRanges: {},

  // Engine state
  isRunning: false,
  pollTimer: null,
  status: null,
  candidates: [],
  selectedCandidate: null,
  filterWfOnly: false,
  filterMultiverseOnly: false,

  // Saved Strategies State
  savedStrategies: [],
  savedPairFilter: 'ALL',
  savedBatchFilter: 'ALL',
  savedStrategiesViewMode: 'grid',
  strategyFolders: [],

  // Portfolio Builder & Saved Portfolios State
  availableForPortfolio: [],
  portfolioSelectedIds: new Set(),
  portfolioPairFilter: 'ALL',
  portfolioBatchFilter: 'ALL',
  portfolioFolders: [],
  savedPortfoliosViewMode: 'folders',
  savedPortfolioSelectedFolder: 'ALL',
  portEngineTimer: null,
  portEngineRunning: false,

  // 3D Neural Explorer
  neuralScene: null,
  neuralCamera: null,
  neuralRenderer: null,
  neuralGroup: null,
  neuralSpeed: 1.0,
  neuralPaused: false,
  neuralAnimFrame: null
};

// Initialize all 28 indicators to checked by default
Object.keys(ALL_28_INDICATORS_CONFIG).forEach(k => {
  state.enabledIndicators[k] = true;
});

// ============================================================================
// INITIALIZATION
// ============================================================================

// Delegated listener for exit/risk sweep From/Step/To inputs (barrido de salidas)
document.addEventListener('change', (e) => {
  const inp = e.target;
  if (!inp || !inp.classList || !inp.classList.contains('rng-input')) return;
  const row = inp.closest('[data-exit-param]');
  if (!row) return;
  const param = row.dataset.exitParam;
  const from = parseFloat(row.querySelector('.rng-from')?.value);
  const step = parseFloat(row.querySelector('.rng-step')?.value);
  const to = parseFloat(row.querySelector('.rng-to')?.value);
  if (isNaN(from) || isNaN(step) || isNaN(to)) {
    delete state.exitRanges[param];
  } else {
    state.exitRanges[param] = { from, step, to };
  }
  updateCombinationsCounter();
});

document.addEventListener('DOMContentLoaded', async () => {
  initTabs();
  const indCountBadge = document.getElementById('ind-count-badge');
  if (indCountBadge) indCountBadge.textContent = Object.keys(ALL_28_INDICATORS_CONFIG).length;
  render28IndicatorsGrid();
  await loadSymbols();
  await loadConfigDefaults();
  renderTfPills();
  await loadMacroCatalog();
  updateCombinationsCounter();
  initNeuralExplorer();

  // Keep multi-TF pills in sync with the primary timeframe select
  const tfSel = document.getElementById('select-timeframe');
  if (tfSel) {
    tfSel.addEventListener('change', () => {
      state.selectedTimeframe = tfSel.value;
      state.selectedTimeframes = new Set([tfSel.value]);
      renderTfPills();
      updateDataSummaryInfo();
    });
  }

  // Date range controls
  document.getElementById('btn-clear-dates')?.addEventListener('click', () => {
    const s = document.getElementById('input-start-date');
    const e = document.getElementById('input-end-date');
    if (s) s.value = '';
    if (e) e.value = '';
  });

  // Validators-during-exploration toggle
  const valToggle = document.getElementById('check-validate-during');
  if (valToggle) {
    valToggle.addEventListener('change', () => {
      const box = document.getElementById('validators-box');
      if (box) {
        box.classList.toggle('opacity-50', !valToggle.checked);
        box.classList.toggle('pointer-events-none', !valToggle.checked);
      }
    });
  }

  // Macro master toggle
  const macroToggle = document.getElementById('check-use-macro');
  if (macroToggle) {
    macroToggle.addEventListener('change', () => {
      state.useMacro = macroToggle.checked;
      const box = document.getElementById('macro-series-box');
      if (box) {
        box.classList.toggle('opacity-50', !state.useMacro);
        box.classList.toggle('pointer-events-none', !state.useMacro);
      }
      updateCombinationsCounter();
    });
  }

  // Macro select all / none
  document.getElementById('btn-macro-all')?.addEventListener('click', () => {
    state.selectedMacro = new Set(state.macroCatalog.map(s => s.series_id));
    renderMacroSeries();
    updateCombinationsCounter();
  });
  document.getElementById('btn-macro-none')?.addEventListener('click', () => {
    state.selectedMacro = new Set();
    renderMacroSeries();
    updateCombinationsCounter();
  });
  
  // Check engine status
  await pollStatus();
  refreshSidebarBadges();

  // Attach Button Listeners
  document.getElementById('btn-start-exploration').addEventListener('click', startExploration);
  document.getElementById('btn-stop-exploration').addEventListener('click', stopExploration);
  document.getElementById('btn-update-data').addEventListener('click', triggerDataUpdate);
  document.getElementById('btn-toggle-neural').addEventListener('click', openNeuralModal);
  document.getElementById('btn-close-neural').addEventListener('click', closeNeuralModal);
  document.getElementById('btn-close-modal').addEventListener('click', closeCandidateModal);
  
  // Indicator helper buttons
  document.getElementById('btn-select-all-ind').addEventListener('click', () => {
    Object.keys(state.enabledIndicators).forEach(k => state.enabledIndicators[k] = true);
    document.querySelectorAll('.ind-checkbox').forEach(cb => cb.checked = true);
    updateCombinationsCounter();
  });

  document.getElementById('btn-deselect-all-ind').addEventListener('click', () => {
    Object.keys(state.enabledIndicators).forEach(k => state.enabledIndicators[k] = false);
    document.querySelectorAll('.ind-checkbox').forEach(cb => cb.checked = false);
    updateCombinationsCounter();
  });

  document.getElementById('btn-random-ind').addEventListener('click', selectRandomIndicators);
  document.getElementById('btn-random-orders').addEventListener('click', selectRandomOrders);
  document.getElementById('btn-random-mix-all').addEventListener('click', () => {
    selectRandomIndicators();
    selectRandomOrders();
  });

  // Filter listeners
  document.getElementById('filter-wf')?.addEventListener('change', (e) => {
    state.filterWfOnly = e.target.checked;
    renderCandidates();
  });
  document.getElementById('filter-mv')?.addEventListener('change', (e) => {
    state.filterMultiverseOnly = e.target.checked;
    renderCandidates();
  });

  // Sync Max Candidates (Top Pool limit) between Config and Results tabs
  const maxCandConfig = document.getElementById('input-max-candidates');
  const maxCandResults = document.getElementById('input-max-candidates-results');
  if (maxCandConfig && maxCandResults) {
    maxCandConfig.addEventListener('input', () => { maxCandResults.value = maxCandConfig.value; });
    maxCandResults.addEventListener('input', () => { maxCandConfig.value = maxCandResults.value; });
  }

  // Position sizing & Prop Firm UI init
  updateSizingModeUI();
  togglePropFirmInputs();
});

// Position sizing mode dynamic display
function updateSizingModeUI() {
  const mode = document.getElementById('select-sizing-mode')?.value || 'FIXED_RISK';
  const riskField = document.getElementById('sizing-field-risk-pct');
  const lotField = document.getElementById('sizing-field-fixed-lot');
  const cashField = document.getElementById('sizing-field-fixed-cash');
  const martField = document.getElementById('sizing-field-martingale');

  if (riskField) riskField.classList.add('hidden');
  if (lotField) lotField.classList.add('hidden');
  if (cashField) cashField.classList.add('hidden');
  if (martField) martField.classList.add('hidden');

  if (mode === 'FIXED_RISK') {
    if (riskField) riskField.classList.remove('hidden');
  } else if (mode === 'FIXED_LOT') {
    if (lotField) lotField.classList.remove('hidden');
  } else if (mode === 'FIXED_CASH') {
    if (cashField) cashField.classList.remove('hidden');
  } else if (mode === 'MARTINGALE' || mode === 'ANTI_MARTINGALE') {
    if (riskField) riskField.classList.remove('hidden');
    if (martField) martField.classList.remove('hidden');
  }
}
window.updateSizingModeUI = updateSizingModeUI;

function togglePropFirmInputs() {
  const checked = document.getElementById('check-prop-firm-filter')?.checked || false;
  const container = document.getElementById('prop-firm-inputs-container');
  if (container) {
    if (checked) {
      container.classList.remove('opacity-50', 'pointer-events-none');
    } else {
      container.classList.add('opacity-50', 'pointer-events-none');
    }
  }
}
window.togglePropFirmInputs = togglePropFirmInputs;

// ============================================================================
// RENDER 28 INDICATORS GRID WITH GENERIC DEFAULTS
// ============================================================================

function render28IndicatorsGrid() {
  const container = document.getElementById('indicators-container');
  if (!container) return;
  container.innerHTML = '';

  // Group by family
  const families = {};
  Object.entries(ALL_28_INDICATORS_CONFIG).forEach(([key, conf]) => {
    if (!families[conf.family]) families[conf.family] = [];
    families[conf.family].push({ key, ...conf });
  });

  Object.entries(families).forEach(([familyName, items]) => {
    const section = document.createElement('div');
    section.className = 'p-4 rounded-lg bg-[#0e0e12] border border-[#22222a]';
    
    let html = `
      <div class="flex items-center justify-between mb-3 border-b border-[#1c1c24] pb-2">
        <span class="text-xs font-bold text-white uppercase tracking-wider">${familyName} (${items.length})</span>
        <span class="text-[10px] text-[#71717a]">Rangos editables: Desde / Paso / Hasta</span>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
    `;

    items.forEach(item => {
      const isChecked = state.enabledIndicators[item.key] !== false;
      const meta = state.indicatorMeta && state.indicatorMeta[item.key];
      const params = (meta && meta.params) || {};
      const paramNames = Object.keys(params);
      let paramsHtml = '';

      if (paramNames.length) {
        const hasNumeric = paramNames.some(pn => params[pn] && !params[pn].values);
        paramsHtml = '<div class="mt-2.5 pt-2 border-t border-[#1a1a22]">';
        if (hasNumeric) {
          paramsHtml += `
            <div class="flex items-center gap-1 text-[8px] text-[#55555f] uppercase tracking-wider mb-1.5">
              <span class="w-[56px] shrink-0"></span>
              <span class="flex-1 text-center">Desde</span>
              <span class="flex-1 text-center">Paso</span>
              <span class="flex-1 text-center">Hasta</span>
            </div>`;
        }
        paramNames.forEach(pname => {
          const defaultCfg = params[pname] || {};
          const rng = (state.indicatorRanges[item.key] && state.indicatorRanges[item.key][pname]) || defaultCfg;
          if (defaultCfg.values) {
            paramsHtml += `
              <div class="flex items-center gap-1 text-[9px] mb-1" title="${pname}: valores fijos">
                <span class="w-[56px] shrink-0 truncate text-[#a0a0ab]">${pname}</span>
                <span class="flex-1 truncate text-[#71717a] font-mono">${defaultCfg.values.join(' / ')}</span>
              </div>`;
          } else {
            paramsHtml += `
              <div class="flex items-center gap-1 mb-1" data-ind="${item.key}" data-param="${pname}">
                <span class="w-[56px] shrink-0 truncate text-[9px] text-[#a0a0ab]" title="${pname}">${pname}</span>
                <input type="number" class="rng-input rng-from flex-1 min-w-0 bg-[#0e0e12] border border-[#27272f] rounded px-1 py-0.5 text-[10px] text-white focus:border-white focus:outline-none transition-colors" value="${rng.from}" step="any" aria-label="${item.key} ${pname} desde">
                <input type="number" class="rng-input rng-step flex-1 min-w-0 bg-[#0e0e12] border border-[#27272f] rounded px-1 py-0.5 text-[10px] text-white focus:border-white focus:outline-none transition-colors" value="${rng.step}" step="any" aria-label="${item.key} ${pname} paso">
                <input type="number" class="rng-input rng-to flex-1 min-w-0 bg-[#0e0e12] border border-[#27272f] rounded px-1 py-0.5 text-[10px] text-white focus:border-white focus:outline-none transition-colors" value="${rng.to}" step="any" aria-label="${item.key} ${pname} hasta">
              </div>`;
          }
        });
        paramsHtml += '</div>';
      } else {
        paramsHtml = `
          <div class="mt-2.5 pt-2 border-t border-[#1a1a22] flex items-center justify-between text-[10px] font-mono text-[#71717a]">
            <span>[${item.from} → ${item.step} → ${item.to}]</span>
            <span class="text-[#a0a0ab]">${item.unit}</span>
          </div>`;
      }

      html += `
        <div class="p-3 rounded bg-[#131318] border border-[#1e1e26] flex flex-col justify-between hover:border-[#383844] transition-colors">
          <div class="flex items-start gap-2.5">
            <input type="checkbox" id="ind-${item.key}" value="${item.key}" ${isChecked ? 'checked' : ''} 
                   class="ind-checkbox w-4 h-4 accent-white mt-0.5 cursor-pointer">
            <div>
              <label for="ind-${item.key}" class="text-xs font-semibold text-white block cursor-pointer">
                ${item.key}
              </label>
              <span class="text-[10px] text-[#a0a0ab] leading-tight block">${item.name}</span>
            </div>
          </div>
          ${paramsHtml}
        </div>
      `;
    });

    html += `</div>`;
    section.innerHTML = html;
    container.appendChild(section);
  });

  // Attach change listeners to update combination counter
  document.querySelectorAll('.ind-checkbox').forEach(cb => {
    cb.addEventListener('change', (e) => {
      state.enabledIndicators[e.target.value] = e.target.checked;
      updateCombinationsCounter();
    });
  });

  // Delegated listener for editable From/Step/To range inputs (bound once on the container)
  if (!container._rangeListenerBound) {
    container._rangeListenerBound = true;
    container.addEventListener('change', (e) => {
      const inp = e.target;
      if (!inp || !inp.classList || !inp.classList.contains('rng-input')) return;
      const row = inp.closest('[data-ind]');
      if (!row) return;
      const ind = row.dataset.ind;
      const param = row.dataset.param;
      const from = parseFloat(row.querySelector('.rng-from')?.value);
      const step = parseFloat(row.querySelector('.rng-step')?.value);
      const to = parseFloat(row.querySelector('.rng-to')?.value);
      if (isNaN(from) || isNaN(step) || isNaN(to)) return;
      if (!state.indicatorRanges[ind]) state.indicatorRanges[ind] = {};
      state.indicatorRanges[ind][param] = { from, step, to };
      updateCombinationsCounter();
    });
  }
}

function selectRandomIndicators() {
  // Mezcla por clasificación: elige 1 o 2 indicadores de cada familia para asegurar variedad
  const families = {};
  Object.entries(ALL_28_INDICATORS_CONFIG).forEach(([key, conf]) => {
    if (!families[conf.family]) families[conf.family] = [];
    families[conf.family].push(key);
  });

  const selected = new Set();
  Object.values(families).forEach(keys => {
    const shuffled = [...keys].sort(() => 0.5 - Math.random());
    const take = Math.min(shuffled.length, Math.random() < 0.5 ? 1 : 2);
    shuffled.slice(0, take).forEach(k => selected.add(k));
  });

  Object.keys(ALL_28_INDICATORS_CONFIG).forEach(k => {
    state.enabledIndicators[k] = selected.has(k);
    const cb = document.getElementById(`ind-${k}`);
    if (cb) cb.checked = selected.has(k);
  });
  updateCombinationsCounter();
}

function selectRandomOrders() {
  // Random entry types
  const entries = ['entry-market', 'entry-limit', 'entry-stop'];
  entries.forEach(id => {
    const cb = document.getElementById(id);
    if (cb) cb.checked = Math.random() > 0.4;
  });
  // Ensure at least one entry type is checked
  if (!entries.some(id => document.getElementById(id).checked)) {
    document.getElementById('entry-market').checked = true;
  }

  // Random exit types
  const exits = ['exit-atr', 'exit-pips', 'exit-pct', 'exit-trailing', 'exit-breakeven', 'exit-swing', 'exit-time', 'exit-partial', 'exit-atr-smooth'];
  exits.forEach(id => {
    const cb = document.getElementById(id);
    if (cb) cb.checked = Math.random() > 0.4;
  });
  if (!exits.some(id => document.getElementById(id).checked)) {
    document.getElementById('exit-atr').checked = true;
  }
}

function rangePoints(cfg) {
  if (!cfg) return 1;
  if (Array.isArray(cfg.values) && cfg.values.length) return cfg.values.length;
  const from = parseFloat(cfg.from), step = parseFloat(cfg.step), to = parseFloat(cfg.to);
  if (isNaN(from) || isNaN(step) || isNaN(to) || step <= 0 || to < from) return 1;
  return Math.floor((to - from) / step) + 1;
}

function updateCombinationsCounter() {
  let totalCombos = 1;
  let activeCount = 0;
  const meta = state.indicatorMeta;

  Object.entries(ALL_28_INDICATORS_CONFIG).forEach(([key, conf]) => {
    if (state.enabledIndicators[key]) {
      activeCount++;
      const indMeta = meta && meta[key];
      if (indMeta && indMeta.params && Object.keys(indMeta.params).length) {
        // Usar la metadata real (32 indicadores) + rangos editados por el usuario
        const override = state.indicatorRanges[key] || {};
        Object.entries(indMeta.params).forEach(([pname, cfg]) => {
          totalCombos *= rangePoints(override[pname] || cfg);
        });
      } else if (indMeta) {
        // Indicador sin parámetros (p.ej. VWAP) → 1 punto
      } else {
        // Fallback: config estática
        const steps = conf.discrete
          ? conf.discrete
          : Math.max(1, Math.floor((conf.to - conf.from) / conf.step) + 1);
        totalCombos *= steps;
      }
    }
  });

  // Exit/risk sweep factor (TN: barrido de salidas/riesgo)
  Object.values(state.exitRanges || {}).forEach(cfg => { totalCombos *= rangePoints(cfg); });

  const fullSpace = totalCombos * 3 * 9; // x3 entry types x9 exits

  // Macro FRED factor: each selected series adds (threshold steps x 2 ops)
  let macroFactor = 1;
  if (state.useMacro && state.selectedMacro.size > 0) {
    state.selectedMacro.forEach(sid => {
      const entry = state.macroCatalog.find(s => s.series_id === sid);
      const r = entry && entry.range;
      if (r && r.step > 0 && r.to >= r.from) {
        const steps = Math.max(1, Math.floor((r.to - r.from) / r.step) + 1);
        macroFactor *= steps * 2;
      } else {
        macroFactor *= 50; // fallback estimate when range unknown
      }
    });
  }
  const grandTotal = fullSpace * macroFactor;

  const countEl = document.getElementById('combinations-counter');
  if (countEl) {
    countEl.textContent = activeCount > 0
      ? (grandTotal >= 1e15 ? grandTotal.toExponential(2) : grandTotal.toLocaleString())
      : '0';
  }
}

// ============================================================================
// TAB NAVIGATION
// ============================================================================

function initTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const target = btn.getAttribute('data-tab');
      state.activeTab = target;

      document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.add('hidden');
      });
      const activePanel = document.getElementById(`panel-${target}`);
      if (activePanel) activePanel.classList.remove('hidden');

      if (target === 'results') {
        renderCandidates();
      }
    });
  });
}

function switchTab(tabId) {
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (btn) btn.click();
}

// ============================================================================
// DATA & SYMBOLS FETCHING
// ============================================================================

async function loadSymbols() {
  try {
    const res = await fetch('/api/symbols');
    const data = await res.json();
    state.symbolsMeta = data;
    renderSymbolPills();
    updateDataSummaryInfo();
  } catch (err) {
    console.error('Error loading symbols:', err);
  }
}

async function loadConfigDefaults() {
  try {
    const res = await fetch('/api/config-defaults');
    const data = await res.json();
    if (data.all_indicators) {
      state.indicatorMeta = data.all_indicators;
      initIndicatorRangesFromMeta();
      render28IndicatorsGrid();
    }
    const objSelect = document.getElementById('opt-objective');
    if (objSelect && data.optimization_objectives) {
      objSelect.innerHTML = '';
      data.optimization_objectives.forEach(obj => {
        const opt = document.createElement('option');
        opt.value = obj.id;
        opt.textContent = obj.name;
        objSelect.appendChild(opt);
      });
    }
  } catch (err) {
    console.error('Error loading config defaults:', err);
  }
}

function initIndicatorRangesFromMeta() {
  if (!state.indicatorMeta) return;
  Object.entries(state.indicatorMeta).forEach(([ind, meta]) => {
    const params = (meta && meta.params) || {};
    if (!state.indicatorRanges[ind]) state.indicatorRanges[ind] = {};
    Object.entries(params).forEach(([pname, cfg]) => {
      if (state.indicatorRanges[ind][pname]) return;
      if (cfg && cfg.values) {
        state.indicatorRanges[ind][pname] = { values: [...cfg.values] };
      } else if (cfg && cfg.from !== undefined) {
        state.indicatorRanges[ind][pname] = { from: cfg.from, step: cfg.step, to: cfg.to };
      }
    });
  });
}

function renderSymbolPills() {
  const container = document.getElementById('symbol-pills-container');
  if (!container) return;
  container.innerHTML = '';

  // Master toggles
  const allBtn = document.createElement('button');
  allBtn.className = 'px-3 py-1.5 rounded text-xs font-semibold uppercase tracking-wider transition-all border ' +
    (state.selectedSymbols.size === state.symbolsMeta.length && state.symbolsMeta.length > 0
      ? 'bg-white text-black border-white shadow-md' : 'bg-[#141418] text-[#a0a0ab] border-[#27272f] hover:border-[#444450] hover:text-white');
  allBtn.textContent = 'TODOS';
  allBtn.addEventListener('click', () => {
    state.selectedSymbols = new Set(state.symbolsMeta.map(s => s.symbol));
    if (state.symbolsMeta.length) state.selectedSymbol = state.symbolsMeta[0].symbol;
    renderSymbolPills();
    updateDataSummaryInfo();
  });
  container.appendChild(allBtn);

  state.symbolsMeta.forEach(sym => {
    const isSelected = state.selectedSymbols.has(sym.symbol);
    const btn = document.createElement('button');
    btn.className = `px-3 py-1.5 rounded text-xs font-semibold uppercase tracking-wider transition-all border ${
      isSelected
        ? 'bg-white text-black border-white shadow-md'
        : 'bg-[#141418] text-[#a0a0ab] border-[#27272f] hover:border-[#444450] hover:text-white'
    }`;
    btn.textContent = sym.symbol;
    btn.title = `${sym.name} — clic para ${isSelected ? 'quitar' : 'añadir'}`;
    btn.addEventListener('click', () => {
      if (state.selectedSymbols.has(sym.symbol)) {
        // never allow empty set
        if (state.selectedSymbols.size > 1) state.selectedSymbols.delete(sym.symbol);
      } else {
        state.selectedSymbols.add(sym.symbol);
      }
      // primary symbol = first selected (stable order)
      const order = state.symbolsMeta.map(s => s.symbol).filter(s => state.selectedSymbols.has(s));
      state.selectedSymbol = order[0] || 'EURUSD';
      renderSymbolPills();
      updateDataSummaryInfo();
    });
    container.appendChild(btn);
  });
}

function renderTfPills() {
  const container = document.getElementById('tf-pills-container');
  if (!container) return;
  container.innerHTML = '';
  const tfs = TIMEFRAMES;
  tfs.forEach(tf => {
    const isSelected = state.selectedTimeframes.has(tf);
    const btn = document.createElement('button');
    btn.className = `px-2.5 py-1 rounded text-[11px] font-semibold uppercase tracking-wider transition-all border ${
      isSelected
        ? 'bg-white text-black border-white shadow-md'
        : 'bg-[#141418] text-[#a0a0ab] border-[#27272f] hover:border-[#444450] hover:text-white'
    }`;
    btn.textContent = tf;
    btn.title = `Timeframe ${tf} — explorar en este timeframe`;
    btn.addEventListener('click', () => {
      if (state.selectedTimeframes.has(tf)) {
        if (state.selectedTimeframes.size > 1) state.selectedTimeframes.delete(tf);
      } else {
        state.selectedTimeframes.add(tf);
      }
      // Primary TF preference: keep current if still selected, else 1h → 30m → 4h → 1d
      const selEl = document.getElementById('select-timeframe');
      let primary = (selEl && state.selectedTimeframes.has(selEl.value)) ? selEl.value : null;
      if (!primary) primary = ['1h', '30m', '4h', '1d'].find(t => state.selectedTimeframes.has(t));
      state.selectedTimeframe = primary || '1h';
      const sel = document.getElementById('select-timeframe');
      if (sel) sel.value = state.selectedTimeframe;
      renderTfPills();
      updateDataSummaryInfo();
    });
    container.appendChild(btn);
  });
}

async function loadMacroCatalog() {
  try {
    const res = await fetch('/api/macro-series');
    const data = await res.json();
    state.macroCatalog = data.series || [];
    renderMacroSeries();
  } catch (err) {
    console.error('Error loading macro catalog:', err);
  }
}

function renderMacroSeries() {
  const container = document.getElementById('macro-series-container');
  if (!container) return;
  if (!state.macroCatalog.length) {
    container.innerHTML = '<div class="text-[11px] text-[#71717a]">No hay series macro disponibles.</div>';
    return;
  }
  // group by category
  const cats = {};
  state.macroCatalog.forEach(s => {
    if (!cats[s.category]) cats[s.category] = [];
    cats[s.category].push(s);
  });
  let html = '';
  Object.entries(cats).forEach(([cat, items]) => {
    html += `<div class="mb-2"><div class="text-[10px] text-[#71717a] uppercase font-bold tracking-wider mb-1">${cat}</div><div class="flex flex-wrap gap-1.5">`;
    items.forEach(s => {
      const checked = state.selectedMacro.has(s.series_id);
      html += `<label class="flex items-center gap-1 cursor-pointer px-2 py-1 rounded bg-[#0e0e12] border ${checked ? 'border-white' : 'border-[#22222a]'} hover:border-[#444450] transition text-[11px]">
        <input type="checkbox" class="macro-cb accent-white" value="${s.series_id}" ${checked ? 'checked' : ''} data-name="${s.name}">
        <span class="${checked ? 'text-white' : 'text-[#a0a0ab]'}">${s.name}</span>
      </label>`;
    });
    html += '</div></div>';
  });
  container.innerHTML = html;
  container.querySelectorAll('.macro-cb').forEach(cb => {
    cb.addEventListener('change', (e) => {
      if (e.target.checked) state.selectedMacro.add(e.target.value);
      else state.selectedMacro.delete(e.target.value);
      renderMacroSeries();
      updateCombinationsCounter();
    });
  });
}

function updateDataSummaryInfo() {
  const infoEl = document.getElementById('symbol-data-info');
  if (infoEl) {
    const sym = state.symbolsMeta.find(s => s.symbol === state.selectedSymbol);
    if (sym) {
      const tfInfo = sym.timeframes[state.selectedTimeframe] || {};
      const nSym = state.selectedSymbols.size;
      const nTf = state.selectedTimeframes.size;
      const scopeLabel = (nSym > 1 || nTf > 1)
        ? `<div><span class="text-white font-medium">Alcance:</span> ${nSym} activo${nSym > 1 ? 's' : ''} × ${nTf} timeframe${nTf > 1 ? 's' : ''} (${[...state.selectedSymbols].join(', ')})</div>`
        : '';
      infoEl.innerHTML = `
        <div class="flex items-center gap-4 text-xs text-[#a0a0ab]">
          <div><span class="text-white font-medium">Activo:</span> ${sym.name} (${sym.category})</div>
          ${scopeLabel}
          <div><span class="text-white font-medium">Velas descargadas:</span> ${tfInfo.bars ? tfInfo.bars.toLocaleString() : 'Listo'}</div>
          <div><span class="text-white font-medium">Rango:</span> ${tfInfo.start ? tfInfo.start.split(' ')[0] : '2024'} al presente</div>
          <div><span class="text-white font-medium">Fuente:</span> Interbank Feeds & Futures continuos (Caché Parquet Local)</div>
        </div>
      `;
    }
  }
  updateDateRangeAvailability();
}

function updateDateRangeAvailability() {
  const availEl = document.getElementById('date-range-avail');
  const startInput = document.getElementById('input-start-date');
  const endInput = document.getElementById('input-end-date');
  if (!availEl || !startInput || !endInput) return;

  let commonStart = '';
  let commonEnd = '';
  const missing = [];
  state.selectedSymbols.forEach(symName => {
    const sym = state.symbolsMeta.find(s => s.symbol === symName);
    state.selectedTimeframes.forEach(tf => {
      const info = sym && sym.timeframes ? sym.timeframes[tf] : null;
      if (!info || !info.start) {
        missing.push(`${symName}/${tf}`);
        return;
      }
      const s = String(info.start).slice(0, 10);
      const e = String(info.end).slice(0, 10);
      if (!commonStart || s > commonStart) commonStart = s;
      if (!commonEnd || e < commonEnd) commonEnd = e;
    });
  });

  if (!commonStart) {
    availEl.textContent = missing.length
      ? `Sin datos locales: ${missing[0]} (descarga automática al iniciar)`
      : 'Disponible: —';
    startInput.min = ''; startInput.max = '';
    endInput.min = ''; endInput.max = '';
    return;
  }

  availEl.textContent = `Disponible: ${commonStart} → ${commonEnd}`;
  availEl.title = missing.length ? `Pares sin datos aún: ${missing.join(', ')}` : '';
  startInput.min = commonStart; startInput.max = commonEnd;
  endInput.min = commonStart; endInput.max = commonEnd;
  // Clamp previously chosen values to the newly available range
  if (startInput.value && startInput.value > commonEnd) startInput.value = '';
  if (startInput.value && startInput.value < commonStart) startInput.value = commonStart;
  if (endInput.value && endInput.value > commonEnd) endInput.value = commonEnd;
  if (endInput.value && endInput.value < commonStart) endInput.value = '';
}

// ============================================================================
// EXPLORATION CONTROLS (INFINITE GENERATION & CLASSIFICATION)
// ============================================================================

function buildExplorationConfig() {
  // Collect enabled indicators
  const enabledInds = Object.keys(state.enabledIndicators).filter(k => state.enabledIndicators[k]);
  if (enabledInds.length === 0) {
    alert('Debes tener al menos 1 indicador marcado.');
    return;
  }

  // Collect enabled entry types
  const enabledEntries = [];
  if (document.getElementById('entry-market')?.checked) enabledEntries.push('MARKET');
  if (document.getElementById('entry-limit')?.checked) enabledEntries.push('LIMIT');
  if (document.getElementById('entry-stop')?.checked) enabledEntries.push('STOP');
  if (enabledEntries.length === 0) enabledEntries.push('MARKET');

  // Collect enabled exit modes
  const enabledExits = [];
  if (document.getElementById('exit-atr')?.checked) enabledExits.push('ATR_CLASSIC');
  if (document.getElementById('exit-pips')?.checked) enabledExits.push('PIPS_FIXED');
  if (document.getElementById('exit-pct')?.checked) enabledExits.push('PCT_EXIT');
  if (document.getElementById('exit-trailing')?.checked) enabledExits.push('TRAILING_ATR');
  if (document.getElementById('exit-breakeven')?.checked) enabledExits.push('BREAKEVEN');
  if (document.getElementById('exit-swing')?.checked) enabledExits.push('STRUCTURE_SWING');
  if (document.getElementById('exit-time')?.checked) enabledExits.push('TIME_EXIT');
  if (document.getElementById('exit-partial')?.checked) enabledExits.push('PARTIAL_TP');
  if (document.getElementById('exit-atr-smooth')?.checked) enabledExits.push('ATR_SMOOTHED');
  if (enabledExits.length === 0) enabledExits.push('ATR_CLASSIC');

  const maxCandRaw = parseInt(document.getElementById('input-max-candidates')?.value) || 0;
  const maxCandResults = parseInt(document.getElementById('input-max-candidates-results')?.value) || 0;
  const numCombos = parseInt(document.getElementById('input-num-combinations')?.value) || 10000;

  const config = {
    symbol: state.selectedSymbol,
    timeframe: document.getElementById('select-timeframe').value,
    // Multi-symbol / multi-timeframe exploration
    symbols: [...state.selectedSymbols],
    timeframes: [...state.selectedTimeframes],
    mtf_mode: document.getElementById('select-mtf-mode')?.value || 'separate',
    // Date range (inclusive; empty = full history)
    start_date: document.getElementById('input-start-date')?.value || null,
    end_date: document.getElementById('input-end-date')?.value || null,
    holdout_pct: parseFloat(document.getElementById('input-holdout-pct')?.value) || 0,
    averaging_config: (document.getElementById('chk-avg-enabled')?.checked ? {
      enabled: true,
      mode: document.getElementById('select-avg-mode')?.value || 'dca',
      maxLevels: parseInt(document.getElementById('input-avg-levels')?.value) || 2,
      spacingUnit: document.getElementById('select-avg-spacing')?.value || 'atr',
      spacingValue: parseFloat(document.getElementById('input-avg-spacing-val')?.value) || 1.0,
      sizeMultiplier: parseFloat(document.getElementById('input-avg-mult')?.value) || 1.0,
      recomputeStopFromAvg: !!document.getElementById('chk-avg-recompute')?.checked
    } : { enabled: false }),
    // Macro FRED
    use_macro: state.useMacro && state.selectedMacro.size > 0,
    macro_series: [...state.selectedMacro],
    search_mode: document.getElementById('select-search-mode').value,
    initial_deposit: parseFloat(document.getElementById('input-deposit').value) || 10000,
    objective: document.getElementById('opt-objective').value,
    infinite_mode: document.getElementById('check-infinite-mode').checked,
    generations: 0,
    population_size: parseInt(document.getElementById('input-pop-size').value) || 30,
    num_combinations: numCombos,
    enabled_indicators: enabledInds,
    enabled_entry_types: enabledEntries,
    enabled_exit_modes: enabledExits,
    // Rangos de parámetros editados manualmente (Desde/Paso/Hasta)
    indicator_ranges: state.indicatorRanges,
    // Rangos de salidas/riesgo editados manualmente (barrido TN)
    exit_ranges: state.exitRanges,
    // Validadores adicionales durante la exploración (WF + Multiverso top-N)
    validate_during_exploration: document.getElementById('check-validate-during')?.checked ?? true,
    wf_top_n: parseInt(document.getElementById('input-wf-top-n')?.value) || 10,
    mv_top_n: parseInt(document.getElementById('input-mv-top-n')?.value) || 5,
    mv_universes: parseInt(document.getElementById('input-explore-mv-universes')?.value) || 25,
    wf_windows: parseInt(document.getElementById('input-explore-wf-windows')?.value) || 4,

    // Classification criteria
    min_win_rate: Number(document.getElementById('input-min-wr').value || 50.0),
    min_trades: parseInt(document.getElementById('input-min-trades').value) || 8,
    max_drawdown: Number(document.getElementById('input-max-dd').value || 15.0),
    min_net_profit_usd: parseFloat(document.getElementById('input-min-profit').value) || 0.0,
    min_sharpe: Number(document.getElementById('input-min-sharpe').value || 1.2),
    min_profit_factor: parseFloat(document.getElementById('input-min-pf').value) || 1.1,
    min_dsr: Number(document.getElementById('input-min-dsr').value || 0.30),
    max_candidates: maxCandRaw || maxCandResults || 0,
    min_indicators_per_strategy: parseInt(document.getElementById('input-min-indicators')?.value) || 1,
    max_indicators_per_strategy: parseInt(document.getElementById('input-max-indicators')?.value) || 3,

    // Backtest modeling, costs & parallelism
    modeling_mode: document.getElementById('select-modeling-mode')?.value || 'ohlc',
    parallel_workers: parseInt(document.getElementById('input-parallel-workers')?.value) || 0,
    spread_pips: document.getElementById('input-spread-pips')?.value !== '' && document.getElementById('input-spread-pips')?.value != null
      ? parseFloat(document.getElementById('input-spread-pips').value) : null,
    slippage_pips: document.getElementById('input-slippage-pips')?.value !== '' && document.getElementById('input-slippage-pips')?.value != null
      ? parseFloat(document.getElementById('input-slippage-pips').value) : null,
    commission_per_lot: document.getElementById('input-commission')?.value !== '' && document.getElementById('input-commission')?.value != null
      ? parseFloat(document.getElementById('input-commission').value) : null,
    swap_long: document.getElementById('input-swap-long')?.value !== '' && document.getElementById('input-swap-long')?.value != null
      ? parseFloat(document.getElementById('input-swap-long').value) : null,
    swap_short: document.getElementById('input-swap-short')?.value !== '' && document.getElementById('input-swap-short')?.value != null
      ? parseFloat(document.getElementById('input-swap-short').value) : null,

    // Risk & Sizing Mode
    sizing_mode: document.getElementById('select-sizing-mode')?.value || 'FIXED_RISK',
    risk_per_trade_pct: parseFloat(document.getElementById('input-risk-pct')?.value) || 1.0,
    fixed_lot: parseFloat(document.getElementById('input-fixed-lot')?.value) || 0.01,
    fixed_cash_risk: parseFloat(document.getElementById('input-fixed-cash')?.value) || 100.0,
    martingale_mult: parseFloat(document.getElementById('input-martingale-mult')?.value) || 1.5,
    risk_multiplier: parseFloat(document.getElementById('input-risk-mult')?.value) || 1.0,
    fixed_rr: parseFloat(document.getElementById('input-fixed-rr')?.value) || 0.0,
    reward_risk_ratio: parseFloat(document.getElementById('input-min-rr')?.value) || 0.0,
    max_daily_trades: parseInt(document.getElementById('input-max-daily-trades')?.value) || 4,
    max_open_trades: parseInt(document.getElementById('input-max-open-trades')?.value) || 1,

    // Risk loss/gain caps (0 = free to vary in generation)
    max_daily_loss_pct: parseFloat(document.getElementById('input-max-daily-loss')?.value) || 3.0,
    max_weekly_loss_pct: parseFloat(document.getElementById('input-max-weekly-loss')?.value) || 6.0,
    max_monthly_loss_pct: parseFloat(document.getElementById('input-max-monthly-loss')?.value) || 12.0,
    max_account_loss_pct: parseFloat(document.getElementById('input-max-account-loss')?.value) || 8.0,
    max_daily_gain_pct: parseFloat(document.getElementById('input-max-daily-gain')?.value) || 0.0,
    max_weekly_gain_pct: parseFloat(document.getElementById('input-max-weekly-gain')?.value) || 0.0,
    max_monthly_gain_pct: parseFloat(document.getElementById('input-max-monthly-gain')?.value) || 0.0,
    max_account_gain_pct: parseFloat(document.getElementById('input-max-account-gain')?.value) || 0.0,
    max_consecutive_wins: parseInt(document.getElementById('input-max-consec-wins')?.value) || 0,
    max_consecutive_losses: parseInt(document.getElementById('input-max-consec-losses')?.value) || 0,

    // Time rules
    close_before_weekend: document.getElementById('check-close-weekend')?.checked ?? true,
    close_before_ny_close: document.getElementById('check-close-ny')?.checked || false,
    no_new_trades_friday: document.getElementById('check-no-friday')?.checked || false,
    no_monday_open: document.getElementById('check-no-monday')?.checked || false,
    avoid_rollover: document.getElementById('check-avoid-rollover')?.checked || false,

    // Prop Firm Challenge
    prop_firm_filter: document.getElementById('check-prop-firm-filter')?.checked || false,
    prop_firm_daily_loss_pct: parseFloat(document.getElementById('input-prop-daily-loss')?.value) || 4.0,
    prop_firm_total_dd_pct: parseFloat(document.getElementById('input-prop-total-dd')?.value) || 8.0,
    prop_firm_target_pct: parseFloat(document.getElementById('input-prop-target')?.value) || 8.0,
    challenge_capital: parseFloat(document.getElementById('input-challenge-capital')?.value) || 10000.0,
    challenge_min_trading_days: parseInt(document.getElementById('input-challenge-days')?.value) || 5,
    challenge_simulations: parseInt(document.getElementById('input-challenge-sims')?.value) || 10,

    // Direction Filter (BOTH, LONG_ONLY, SHORT_ONLY)
    direction: document.querySelector('input[name="direction"]:checked')?.value || 'BOTH'
  };

  return config;
}

async function startExploration() {
  const config = buildExplorationConfig();
  if (!config) return;
  const error = window.explorationConfigError?.(config);
  if (error) { alert(error); return; }
  try {
    const res = await fetch('/api/start-exploration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`Error al iniciar: ${err.detail || 'Ocurrió un error'}`);
      return;
    }

    state.isRunning = true;
    updateUIExecutionState(true);
    switchTab('results');
    startPolling();
  } catch (err) {
    console.error('Error starting exploration:', err);
  }
}

async function stopExploration() {
  try {
    await fetch('/api/stop-exploration', { method: 'POST' });
    state.isRunning = false;
    updateUIExecutionState(false);
  } catch (err) {
    console.error('Error stopping exploration:', err);
  }
}

async function triggerDataUpdate() {
  const btn = document.getElementById('btn-update-data');
  const originalText = btn.innerHTML;
  btn.innerHTML = `<span class="animate-spin inline-block w-3 h-3 border-2 border-black border-t-transparent rounded-full mr-2"></span> Actualizando...`;
  btn.disabled = true;

  try {
    await fetch('/api/update-data', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    await loadSymbols();
    alert('✓ Datos históricos actualizados correctamente.');
  } catch (err) {
    alert('Error al actualizar datos.');
  } finally {
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(pollStatus, 800);
}

async function pollStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    state.status = data;
    state.isRunning = data.is_running;

    updateUIExecutionState(data.is_running);
    renderCounters(data);
    renderActivityLogs(data.log_messages);

    if (data.tested_count > 0) {
      await fetchCandidates();
      updateNeuralTree();
    }

    if (!data.is_running && state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  } catch (err) {
    console.error('Polling error:', err);
  }
}

function updateUIExecutionState(running) {
  const startBtn = document.getElementById('btn-start-exploration');
  const stopBtn = document.getElementById('btn-stop-exploration');
  const statusBadge = document.getElementById('engine-status-badge');
  const liveInd = document.getElementById('engine-live-indicator');

  if (running) {
    startBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');
    statusBadge.innerHTML = `<span class="inline-block w-2 h-2 rounded-full bg-white pulse-badge mr-2"></span> CREANDO CONTINUAMENTE`;
    statusBadge.className = 'tn-badge border-white text-white font-semibold flex items-center';
    if (liveInd) liveInd.textContent = 'MOTOR GENÉTICO ACTIVO';
  } else {
    startBtn.classList.remove('hidden');
    stopBtn.classList.add('hidden');
    statusBadge.innerHTML = `<span class="inline-block w-2 h-2 rounded-full bg-[#71717a] mr-2"></span> LISTO`;
    statusBadge.className = 'tn-badge text-[#a0a0ab] flex items-center';
    if (liveInd) liveInd.textContent = 'EN ESPERA';
  }
}

function renderCounters(data) {
  document.getElementById('kpi-generation').textContent = `Gen ${data.current_generation || 0}`;
  document.getElementById('kpi-tested').textContent = (data.tested_count || 0).toLocaleString();
  document.getElementById('kpi-discarded').textContent = (data.discarded_count || 0).toLocaleString();
  document.getElementById('kpi-candidates').textContent = (data.accepted_count || data.candidates_count || 0).toLocaleString();
  document.getElementById('kpi-best-sharpe').textContent = (data.best_sharpe || 0).toFixed(2);
  document.getElementById('kpi-avg-winrate').textContent = `${(data.avg_win_rate || 0).toFixed(1)}%`;
  
  const resultsBadge = document.getElementById('results-count-badge');
  if (resultsBadge) {
    resultsBadge.textContent = `${data.candidates_count || 0} Algoritmos Aprobados`;
  }
}

function renderActivityLogs(logs) {
  const container = document.getElementById('engine-logs-container');
  if (!container || !logs) return;
  container.innerHTML = logs.map(l => `<div class="py-0.5 text-[#a0a0ab] font-mono text-[11px]">${l}</div>`).join('');
  container.scrollTop = container.scrollHeight;
}

// ============================================================================
// CANDIDATES RENDERING WITH NET PROFIT & INITIAL CAPITAL DISPLAY
// ============================================================================

async function fetchCandidates() {
  try {
    const res = await fetch('/api/candidates');
    const data = await res.json();
    state.candidates = data;
    renderCandidates();
  } catch (err) {
    console.error('Error fetching candidates:', err);
  }
}

function changeCandidatesSort(val) {
  state.candidatesSortBy = val;
  renderCandidates();
}
window.changeCandidatesSort = changeCandidatesSort;

function renderCandidates() {
  const container = document.getElementById('candidates-grid');
  if (!container) return;

  let list = [...state.candidates];

  if (state.filterWfOnly) {
    list = list.filter(c => c.validation?.walk_forward?.passed);
  }
  if (state.filterMultiverseOnly) {
    list = list.filter(c => c.validation?.multiverse?.passed);
  }

  // Sort candidates according to user selection
  const sortBy = state.candidatesSortBy || 'tn_score';
  list.sort((a, b) => {
    const ma = a.metrics || {};
    const mb = b.metrics || {};
    if (sortBy === 'ret_dd') {
      const rA = (ma.total_return_usd || 0) / Math.max(1.0, ma.max_drawdown_usd || 1.0);
      const rB = (mb.total_return_usd || 0) / Math.max(1.0, mb.max_drawdown_usd || 1.0);
      return rB - rA;
    } else if (sortBy === 'net_profit') {
      return (mb.total_return_usd || 0) - (ma.total_return_usd || 0);
    } else if (sortBy === 'min_dd') {
      return (ma.max_drawdown_pct || 999) - (mb.max_drawdown_pct || 999);
    } else if (sortBy === 'sharpe') {
      return (mb.sharpe_ratio || 0) - (ma.sharpe_ratio || 0);
    } else if (sortBy === 'win_rate') {
      return (mb.win_rate_pct || 0) - (ma.win_rate_pct || 0);
    } else if (sortBy === 'trades') {
      return (mb.total_trades || 0) - (ma.total_trades || 0);
    } else { // 'tn_score'
      return (b.fitness || mb.tn_score || 0) - (a.fitness || ma.tn_score || 0);
    }
  });

  if (list.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-16 text-center text-[#71717a]">
        <div class="text-3xl mb-3">⚙️</div>
        <div class="text-sm font-medium text-white mb-1">Sin algoritmos aprobados todavía</div>
        <div class="text-xs">El motor evalúa combinaciones continuas. Las que cumplan los filtros de Clasificación aparecerán aquí automáticamente.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = list.map((cand, idx) => {
    const m = cand.metrics;
    const s = cand.strategy;
    const rank = idx + 1;
    const isLead = rank === 1;

    // Sparkline SVG path calculation
    const spark = cand.sparkline || [];
    let pathD = '';
    if (spark.length > 1) {
      const minV = Math.min(...spark);
      const maxV = Math.max(...spark);
      const range = (maxV - minV) || 1;
      const pts = spark.map((v, i) => {
        const x = (i / (spark.length - 1)) * 260;
        const y = 45 - ((v - minV) / range) * 35;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      });
      pathD = `M ${pts.join(' L ')}`;
    }

    const netProfitFormatted = `${m.total_return_usd >= 0 ? '+' : ''}$${m.total_return_usd.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    const initialDepositFormatted = `$${(m.initial_capital || 10000).toLocaleString()}`;

    return `
      <div class="candidate-card group" data-id="${s.id}">
        <!-- Top Card Row -->
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <span class="tn-badge ${isLead ? 'tn-badge-white' : ''}">#${rank}</span>
            <span class="text-xs font-semibold text-white tracking-wide" data-rename-kind="strategy" data-rename-id="${s.id}">${escapeWorkspaceText(s.name)}</span>
          </div>
          <span class="text-xs font-mono font-bold text-white px-2 py-0.5 rounded bg-[#1c1c24] border border-[#33333f]">
            TN ${m.tn_score}
          </span>
        </div>

        <!-- Badges Row -->
        <div class="flex flex-wrap gap-1.5 mb-3">
          <span class="tn-badge text-[10px]">${s.symbol}</span>
          <span class="tn-badge text-[10px]">${s.timeframe}</span>
          <span class="tn-badge text-[10px]">${s.entry_order_type || 'MARKET'}</span>
          <span class="tn-badge text-[10px] text-[#a0a0ab]">${s.exit_mode.replace('_', ' ')}</span>
        </div>

        <!-- Prominent Initial Capital & Net Profit Box -->
        <div class="p-2.5 rounded bg-[#09090c] border border-[#22222a] flex items-center justify-between my-2">
          <div>
            <div class="text-[10px] text-[#71717a] uppercase font-bold">Capital Inicial</div>
            <div class="text-xs font-mono text-[#a0a0ab]">${initialDepositFormatted}</div>
          </div>
          <div class="text-right">
            <div class="text-[10px] text-white uppercase font-bold">Net Profit</div>
            <div class="text-sm font-mono font-bold text-white">${netProfitFormatted} <span class="text-[11px] font-normal text-[#a0a0ab]">(${m.total_return_pct}%)</span></div>
          </div>
        </div>

        <!-- Mini Sparkline SVG -->
        <div class="h-10 w-full my-1 relative">
          <svg class="sparkline-svg" viewBox="0 0 260 50">
            <path class="sparkline-path" d="${pathD}" />
          </svg>
        </div>

        <!-- Metrics Grid -->
        <div class="grid grid-cols-4 gap-1.5 mt-2 pt-2 border-t border-[#1e1e26] text-center">
          <div>
            <div class="text-[9px] text-[#71717a] uppercase">Sharpe</div>
            <div class="text-xs font-mono font-semibold text-white">${m.sharpe_ratio.toFixed(2)}</div>
          </div>
          <div>
            <div class="text-[9px] text-[#71717a] uppercase">Win Rate</div>
            <div class="text-xs font-mono font-semibold text-white">${m.win_rate_pct.toFixed(1)}%</div>
          </div>
          <div>
            <div class="text-[9px] text-[#71717a] uppercase">Drawdown</div>
            <div class="text-xs font-mono font-semibold text-white">${m.max_drawdown_pct.toFixed(1)}%</div>
          </div>
          <div>
            <div class="text-[9px] text-[#71717a] uppercase">Trades</div>
            <div class="text-xs font-mono font-semibold text-white">${m.total_trades}</div>
          </div>
        </div>

        <!-- Card Click Action Button & Quick Save -->
        <div class="mt-3 pt-2 flex items-center justify-between border-t border-[#1e1e24]">
          <button type="button" class="btn-card-action flex items-center gap-1.5 text-xs text-[#a0a0ab] hover:text-white">
            <span class="text-[11px] font-medium">Ver análisis completo</span>
            <span class="group-hover:translate-x-1 transition-transform">→</span>
          </button>
          <button type="button" onclick="event.stopPropagation(); saveSingleStrategy('${s.id}')" class="text-[11px] py-1 px-2.5 rounded bg-[#16161c] hover:bg-white hover:text-black border border-[#2a2a34] text-white transition-all" title="Guardar estrategia en Mis Algoritmos">
            💾 Guardar
          </button>
        </div>
      </div>
    `;
  }).join('');

  // Attach direct click listeners to all candidate cards
  document.querySelectorAll('.candidate-card').forEach(card => {
    const candId = card.getAttribute('data-id');
    card.addEventListener('click', (e) => {
      openCandidateModal(candId);
    });
  });
}

// ============================================================================
// CANDIDATE DETAIL MODAL & CHARTS
// ============================================================================

let equityChartInstance = null;

async function openCandidateModal(candidateId) {
  try {
    const res = await fetch(`/api/candidate/${candidateId}`);
    if (!res.ok) {
      alert('No se pudo cargar el análisis del candidato.');
      return;
    }
    const cand = await res.json();
    state.selectedCandidate = cand;

    const modal = document.getElementById('candidate-modal');
    modal.classList.remove('hidden');

    // Populate titles
    document.getElementById('modal-title').textContent = cand.strategy.name;
    const dir = cand.strategy.direction || 'BOTH';
    const dirLbl = dir === 'LONG_ONLY' ? ' · Solo Compras' : dir === 'SHORT_ONLY' ? ' · Solo Ventas' : '';
    document.getElementById('modal-subtitle').textContent = `${cand.strategy.symbol} · ${cand.strategy.timeframe}${dirLbl} · Orden ${cand.strategy.entry_order_type || 'MARKET'} · Modo ${cand.strategy.exit_mode} · TN Score ${cand.metrics.tn_score}`;

    // Populate Key Figures
    const m = cand.metrics;
    document.getElementById('modal-metric-initial').textContent = `$${(m.initial_capital || 10000).toLocaleString()}`;
    document.getElementById('modal-metric-return').textContent = `${m.total_return_usd >= 0 ? '+' : ''}$${m.total_return_usd.toLocaleString(undefined, {minimumFractionDigits: 2})} (${m.total_return_pct}%)`;
    document.getElementById('modal-metric-sharpe').textContent = m.sharpe_ratio.toFixed(2);
    document.getElementById('modal-metric-drawdown').textContent = `${m.max_drawdown_pct.toFixed(1)}% ($${m.max_drawdown_usd.toLocaleString()})`;
    document.getElementById('modal-metric-winrate').textContent = `${m.win_rate_pct.toFixed(1)}% (${m.total_trades} trades)`;
    document.getElementById('modal-metric-pf').textContent = m.profit_factor.toFixed(2);
    const hoEl = document.getElementById('modal-metric-holdout');
    if (hoEl) {
      const ho = m.holdout;
      hoEl.textContent = ho
        ? `${ho.net_profit >= 0 ? '+' : ''}$${Number(ho.net_profit).toLocaleString(undefined, {minimumFractionDigits: 2})} · Sh ${ho.sharpe_ratio}`
        : '—';
      hoEl.classList.toggle('text-emerald-400', !!(ho && ho.net_profit >= 0));
      hoEl.classList.toggle('text-rose-400', !!(ho && ho.net_profit < 0));
    }

    // Populate Rules (ocultar columna de la dirección que nunca opera)
    const rulesDesc = cand.rules_desc;
    const buyCol = document.getElementById('modal-buy-rules-col');
    const sellCol = document.getElementById('modal-sell-rules-col');
    if (buyCol && sellCol) {
      const hideBuy = dir === 'SHORT_ONLY';
      const hideSell = dir === 'LONG_ONLY';
      buyCol.classList.toggle('hidden', hideBuy);
      sellCol.classList.toggle('hidden', hideSell);
      buyCol.classList.toggle('md:col-span-2', hideBuy);
      sellCol.classList.toggle('md:col-span-2', hideSell);
    }
    document.getElementById('modal-buy-rules').innerHTML = rulesDesc.buy_rules.map(r => `<li>${r}</li>`).join('');
    document.getElementById('modal-sell-rules').innerHTML = rulesDesc.sell_rules.map(r => `<li>${r}</li>`).join('');
    document.getElementById('modal-exit-rules').textContent = `${cand.strategy.entry_order_type || 'MARKET'} | ${rulesDesc.exit_rules}`;
    document.getElementById('modal-session-rules').textContent = rulesDesc.session;
    document.getElementById('modal-risk-rules').innerHTML = rulesDesc.risk_rules.map(r => `<li>${r}</li>`).join('');

    // Populate Trades Table
    renderTradesTable(cand.trades_sample || []);

    // Render Equity Chart
    renderEquityCurveChart(cand.equity_curve || []);

    // Setup Validation button
    const valBtn = document.getElementById('btn-run-validation');
    valBtn.onclick = () => runDeepValidation(cand.strategy.id);

    // Setup Save & Export buttons
    const saveBtn = document.getElementById('btn-save-strategy');
    if (saveBtn) {
      saveBtn.onclick = () => saveSingleStrategy(cand.strategy.id);
    }
    document.getElementById('btn-export-mql5').onclick = () => window.open(`/api/candidate/${cand.strategy.id}/export/mq5`, '_blank');
    document.getElementById('btn-export-python').onclick = () => window.open(`/api/candidate/${cand.strategy.id}/export/python`, '_blank');
    document.getElementById('btn-export-json').onclick = () => window.open(`/api/candidate/${cand.strategy.id}/export/json`, '_blank');

    document.getElementById('validation-results-container').classList.add('hidden');

  } catch (err) {
    console.error('Error loading candidate detail:', err);
  }
}

// Bind to window for absolute safety
window.openCandidateModal = openCandidateModal;

function closeCandidateModal() {
  document.getElementById('candidate-modal').classList.add('hidden');
  if (equityChartInstance) {
    equityChartInstance.destroy();
    equityChartInstance = null;
  }
}

function renderEquityCurveChart(curve) {
  const ctx = document.getElementById('equity-chart-canvas').getContext('2d');
  if (equityChartInstance) equityChartInstance.destroy();

  const labels = curve.map(c => c.time.split(' ')[0]);
  const dataEquity = curve.map(c => c.equity);
  const dataBalance = curve.map(c => c.balance);

  equityChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Equity (USD)',
          data: dataEquity,
          borderColor: '#ffffff',
          backgroundColor: 'rgba(255, 255, 255, 0.04)',
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          tension: 0.1
        },
        {
          label: 'Balance (USD)',
          data: dataBalance,
          borderColor: '#71717a',
          borderWidth: 1,
          borderDash: [4, 4],
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#a0a0ab', font: { size: 11 } } },
        tooltip: {
          backgroundColor: '#18181c',
          titleColor: '#ffffff',
          bodyColor: '#e4e4e7',
          borderColor: '#383842',
          borderWidth: 1
        }
      },
      scales: {
        x: {
          grid: { color: '#1a1a22' },
          ticks: { color: '#666672', maxTicksLimit: 8 }
        },
        y: {
          grid: { color: '#1a1a22' },
          ticks: { color: '#666672' }
        }
      }
    }
  });
}

function renderTradesTable(trades) {
  const tbody = document.getElementById('trades-table-body');
  if (!tbody) return;
  tbody.innerHTML = trades.map(t => `
    <tr class="border-b border-[#181820] hover:bg-[#15151c] transition-colors">
      <td class="py-2 px-3 text-xs text-[#71717a]">#${t.trade_num}</td>
      <td class="py-2 px-3 text-xs"><span class="tn-badge ${t.direction === 'BUY' ? 'tn-badge-white' : ''}">${t.direction}</span></td>
      <td class="py-2 px-3 text-xs font-mono text-[#a0a0ab]">${t.entry_time.split(' ')[0]}</td>
      <td class="py-2 px-3 text-xs font-mono text-white">${t.entry_price}</td>
      <td class="py-2 px-3 text-xs font-mono text-white">${t.exit_price}</td>
      <td class="py-2 px-3 text-xs font-mono font-semibold ${t.pnl_usd >= 0 ? 'text-white' : 'text-[#888894]'}">${t.pnl_usd >= 0 ? '+' : ''}$${t.pnl_usd.toFixed(2)}</td>
      <td class="py-2 px-3 text-xs font-mono text-[#a0a0ab]">${t.pips}</td>
      <td class="py-2 px-3 text-xs text-[#71717a]">${t.exit_reason}</td>
    </tr>
  `).join('');
}

async function runDeepValidation(candidateId) {
  const btn = document.getElementById('btn-run-validation');
  const originalText = btn.innerHTML;
  btn.innerHTML = `<span class="animate-spin inline-block w-3 h-3 border-2 border-black border-t-transparent rounded-full mr-2"></span> Ejecutando Walk-Forward y Multiverso...`;
  btn.disabled = true;

  try {
    const body = {
      wf_mode: document.getElementById('select-wf-mode')?.value || 'validation',
      wf_reopt_depth: document.getElementById('select-wf-depth')?.value || 'standard',
      wf_windows: parseInt(document.getElementById('input-wf-windows')?.value) || 4,
      wf_test_ratio: parseFloat(document.getElementById('input-wf-test-ratio')?.value) || 0.25,
      mv_universes: parseInt(document.getElementById('input-mv-universes')?.value) || 80,
      mv_preset: document.getElementById('select-mv-preset')?.value || 'balanced',
      mv_regimes: parseInt(document.getElementById('input-mv-regimes')?.value) || 3
    };
    const res = await fetch(`/api/candidate/${candidateId}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const val = await res.json();

    const container = document.getElementById('validation-results-container');
    container.classList.remove('hidden');

    const wf = val.walk_forward;
    const passRate = wf.pass_rate_pct != null ? wf.pass_rate_pct : '--';
    const wfe = wf.overall_wfe != null ? wf.overall_wfe : '--';
    const paramStab = wf.param_stability ? ` · Estabilidad params: ${wf.param_stability.score}` : '';
    document.getElementById('val-wf-status').innerHTML = `
      <div class="flex items-center justify-between p-3 rounded bg-[#16161c] border border-[#2a2a34]">
        <div>
          <div class="text-xs font-semibold text-white">Walk-Forward ${wf.mode || 'validation'} (WFE: ${wfe} · Pass: ${passRate}%)</div>
          <div class="text-[11px] text-[#a0a0ab]">${(wf.windows || []).length} ventanas fuera de muestra · Sharpe OOS medio: ${wf.sharpe_oos_mean ?? '--'}${paramStab}</div>
        </div>
        <span class="tn-badge ${wf.passed ? 'tn-badge-white' : ''}">${wf.passed ? 'SUPERADO (ROBUSTO)' : 'SOBREAJUSTADO'}</span>
      </div>
    `;

    const mv = val.multiverse;
    const regimes = mv.regimes
      ? Object.entries(mv.regimes).map(([k, v]) => `${k}: ${v.profitable_pct}%`).join(' · ')
      : '';
    document.getElementById('val-mv-status').innerHTML = `
      <div class="flex items-center justify-between p-3 rounded bg-[#16161c] border border-[#2a2a34]">
            <div>
              <div class="text-xs font-semibold text-white">Multiverso Score: ${mv.score ?? mv.profitable_pct}${mv.score != null ? '/100' : '%'} · ${mv.verdict || (mv.passed ? 'SUPERADO' : 'FRÁGIL')}</div>
              <div class="text-[11px] text-[#a0a0ab]">${mv.total_universes} universos · ${mv.profitable_pct}% rentables · Preset: ${mv.engine_preset || 'balanced'}${regimes ? ' · ' + regimes : ''}</div>
            </div>
        <span class="tn-badge ${mv.passed ? 'tn-badge-white' : ''}">${mv.passed ? 'SUPERADO (ALTA VENTAJA)' : (mv.verdict || 'FRÁGIL')}</span>
      </div>
    `;

    const pf = val.prop_firm;
    document.getElementById('val-prop-status').innerHTML = `
      <div class="flex items-center justify-between p-3 rounded bg-[#16161c] border border-[#2a2a34]">
        <div>
          <div class="text-xs font-semibold text-white">Simulador de Fondeo Prop Firm (${pf.pass_rate_pct}% Pass Rate)</div>
          <div class="text-[11px] text-[#a0a0ab]">${pf.passed_count}/${pf.total_simulations} retos aprobados respetando límite diario y total</div>
        </div>
        <span class="tn-badge ${pf.pass_rate_pct >= 60 ? 'tn-badge-white' : ''}">${pf.pass_rate_pct >= 60 ? 'VIABLE FONDEO' : 'RIESGOSO'}</span>
      </div>
    `;

  } catch (err) {
    alert('Error al ejecutar validación.');
  } finally {
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}

// ============================================================================
// 3D NEURAL EXPLORER (THREE.JS REPLICA)
// ============================================================================

function initNeuralExplorer() {
  const container = document.getElementById('neural-canvas-container');
  if (!container || !window.THREE) return;

  const width = container.clientWidth || 800;
  const height = 550;

  state.neuralScene = new THREE.Scene();
  state.neuralScene.background = new THREE.Color(0x060608);

  state.neuralCamera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
  state.neuralCamera.position.set(0, 0, 120);

  state.neuralRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  state.neuralRenderer.setSize(width, height);
  state.neuralRenderer.setPixelRatio(window.devicePixelRatio || 1);
  container.appendChild(state.neuralRenderer.domElement);

  const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
  state.neuralScene.add(ambientLight);
  const pointLight = new THREE.PointLight(0xffffff, 1.2, 300);
  pointLight.position.set(0, 50, 100);
  state.neuralScene.add(pointLight);

  state.neuralGroup = new THREE.Group();
  state.neuralScene.add(state.neuralGroup);

  animateNeural();

  document.getElementById('neural-speed-05')?.addEventListener('click', () => state.neuralSpeed = 0.5);
  document.getElementById('neural-speed-1')?.addEventListener('click', () => state.neuralSpeed = 1.0);
  document.getElementById('neural-speed-2')?.addEventListener('click', () => state.neuralSpeed = 2.0);
  document.getElementById('neural-pause')?.addEventListener('click', () => {
    state.neuralPaused = !state.neuralPaused;
    document.getElementById('neural-pause').textContent = state.neuralPaused ? 'Reanudar' : 'Pausa';
  });
}

function animateNeural() {
  state.neuralAnimFrame = requestAnimationFrame(animateNeural);

  if (!state.neuralPaused && state.neuralGroup) {
    state.neuralGroup.rotation.y += 0.003 * state.neuralSpeed;
    state.neuralGroup.rotation.x += 0.001 * state.neuralSpeed;
  }

  if (state.neuralRenderer && state.neuralScene && state.neuralCamera) {
    state.neuralRenderer.render(state.neuralScene, state.neuralCamera);
  }
}

async function updateNeuralTree() {
  if (!state.neuralScene || !state.neuralGroup) return;

  try {
    const res = await fetch('/api/neural-tree');
    const tree = await res.json();
    const nodes = tree.nodes || [];
    const edges = tree.edges || [];

    while (state.neuralGroup.children.length > 0) {
      state.neuralGroup.remove(state.neuralGroup.children[0]);
    }

    const sphereGeo = new THREE.SphereGeometry(1.2, 16, 16);
    const passedMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const normalMat = new THREE.MeshBasicMaterial({ color: 0x444450 });

    const nodePositions = {};

    nodes.forEach(n => {
      const mesh = new THREE.Mesh(sphereGeo, n.passed ? passedMat : normalMat);
      mesh.position.set(n.x, n.y, n.z);
      const scale = n.passed ? Math.max(1.5, n.tn_score / 35.0) : 0.8;
      mesh.scale.set(scale, scale, scale);
      state.neuralGroup.add(mesh);
      nodePositions[n.id] = mesh.position;
    });

    const lineMat = new THREE.LineBasicMaterial({ color: 0x22222a, transparent: true, opacity: 0.4 });
    edges.forEach(e => {
      const p1 = nodePositions[e.source];
      const p2 = nodePositions[e.target];
      if (p1 && p2) {
        const lineGeo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
        const line = new THREE.Line(lineGeo, lineMat);
        state.neuralGroup.add(line);
      }
    });

    document.getElementById('hud-nodes-count').textContent = nodes.length;
    document.getElementById('hud-generation').textContent = state.status?.current_generation || 1;

  } catch (err) {
    console.error('Error updating neural tree:', err);
  }
}

function openNeuralModal() {
  document.getElementById('neural-modal').classList.remove('hidden');
  updateNeuralTree();
}

function closeNeuralModal() {
  document.getElementById('neural-modal').classList.add('hidden');
}

// ============================================================================
// SIDEBAR NAVIGATION & SECTION TOGGLING (TradingNote Architecture)
// ============================================================================

function showSection(sectionId) {
  // Update sidebar item active classes
  document.querySelectorAll('.sidebar-item').forEach(item => {
    if (item.getAttribute('data-section') === sectionId) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  // Hide all sections
  document.querySelectorAll('.app-section').forEach(sec => {
    sec.classList.add('hidden');
  });

  // Show target section
  const target = document.getElementById(`section-${sectionId}`);
  if (target) {
    target.classList.remove('hidden');
  }

  // Trigger relevant data loaders
  if (sectionId === 'saved-strategies') {
    if (state.savedStrategiesViewMode === 'folders') {
      loadStrategyFolders();
    } else {
      loadSavedStrategies();
    }
  } else if (sectionId === 'portfolio-builder') {
    renderPortfolioStrategyChecklist();
  } else if (sectionId === 'retest-validation') {
    loadRetestView();
  } else if (sectionId === 'saved-portfolios') {
    if (state.savedPortfoliosViewMode === 'folders') {
      loadPortfolioFolders();
    } else {
      loadSavedPortfolios();
    }
  } else if (sectionId === 'engine') {
    if (state.activeTab === 'results') {
      renderCandidates();
    }
  }
}
window.showSection = showSection;

// ============================================================================
// STRATEGY PERSISTENCE (INDIVIDUAL & BATCH FOLDERS)
// ============================================================================

state.savedStrategies = [];
state.strategyFolders = [];
state.savedPairFilter = 'ALL';
state.savedBatchFilter = 'ALL';
state.savedStrategiesViewMode = 'folders';

async function saveSingleStrategy(strategyId) {
  try {
    const defaultFolder = state.selectedSymbol ? `Lote_${state.selectedSymbol}` : 'General';
    const folderName = prompt('Carpeta / Lote donde guardar esta estrategia:', defaultFolder) || defaultFolder;

    const res = await fetch('/api/strategy/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy_id: strategyId, folder: folderName })
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`Error al guardar: ${err.detail || 'No se pudo guardar la estrategia.'}`);
      return;
    }
    alert(`✓ Estrategia guardada exitosamente en la carpeta "${folderName}".`);
    refreshSidebarBadges();
  } catch (err) {
    console.error('Error saving strategy:', err);
    alert('Error de conexión al guardar la estrategia.');
  }
}
window.saveSingleStrategy = saveSingleStrategy;

async function deleteSavedStrategy(strategyId) {
  if (!confirm('¿Estás seguro de eliminar esta estrategia guardada?')) return;
  try {
    const res = await fetch(`/api/strategy/${strategyId}`, { method: 'DELETE' });
    if (res.ok) {
      loadSavedStrategies();
      refreshSidebarBadges();
    } else {
      alert('Error al eliminar la estrategia.');
    }
  } catch (err) {
    console.error('Error deleting strategy:', err);
  }
}
window.deleteSavedStrategy = deleteSavedStrategy;

async function saveAllApprovedBatch() {
  if (!state.candidates || state.candidates.length === 0) {
    alert('No hay algoritmos aprobados en los resultados aún para guardar.');
    return;
  }
  
  const tf = document.getElementById('select-timeframe')?.value || '1h';
  const sym = state.selectedSymbol || 'EURUSD';
  const dateStr = new Date().toISOString().slice(0, 10);
  const timeStr = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}).replace(':', '');
  const defaultBatch = `Lote_${sym}_${tf}_${dateStr}_${timeStr}`;
  const batchName = prompt(`Nombre de la Carpeta / Lote para guardar las ${state.candidates.length} estrategias aprobadas:`, defaultBatch) || defaultBatch;

  try {
    const res = await fetch('/api/strategy/batch-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        save_all_candidates: true,
        batch_name: batchName,
        folder: batchName
      })
    });
    const data = await res.json();
    alert(`✓ Se guardaron ${data.count} estrategias aprobadas organizadas en la carpeta:\n"${batchName}"`);
    refreshSidebarBadges();
    if (document.getElementById('section-saved-strategies')?.classList.contains('hidden') === false) {
      refreshStrategiesView();
    }
  } catch (err) {
    console.error('Error saving batch:', err);
    alert('Error al guardar el lote de estrategias.');
  }
}
window.saveAllApprovedBatch = saveAllApprovedBatch;

async function sendBatchToPortfolio() {
  if (!state.candidates || state.candidates.length === 0) {
    alert('No hay estrategias aprobadas aún para enviar a portafolio.');
    return;
  }

  // 1. Stop engine first if running
  if (state.isRunning) {
    await stopExploration();
  }

  // 2. Batch-save current candidates with auto label
  const tf = document.getElementById('select-timeframe')?.value || '1h';
  const sym = state.selectedSymbol || 'EURUSD';
  const dateStr = new Date().toISOString().slice(0, 10);
  const timeStr = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}).replace(':', '');
  const batchLabel = `Lote_${sym}_${tf}_${dateStr}_${timeStr}`;

  try {
    await fetch('/api/strategy/batch-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        save_all_candidates: true,
        batch_name: batchLabel,
        folder: batchLabel
      })
    });
    refreshSidebarBadges();
  } catch (e) {
    console.warn('Batch save during portfolio transfer:', e);
  }

  // 3. Pre-select all these candidates in the portfolio creator
  state.candidates.forEach(c => {
    state.portfolioSelectedIds.add(c.strategy.id);
  });

  // 4. Switch to portfolio builder section
  showSection('portfolio-builder');
}
window.sendBatchToPortfolio = sendBatchToPortfolio;

// ============================================================================
// STRATEGY FOLDERS & INDIVIDUAL VIEWS
// ============================================================================

function switchSavedStrategiesView(mode) {
  state.savedStrategiesViewMode = mode;
  const btnFolders = document.getElementById('btn-view-folders');
  const btnAll = document.getElementById('btn-view-all');
  const viewFolders = document.getElementById('view-strategy-folders');
  const viewIndividual = document.getElementById('view-strategy-individual');

  if (mode === 'folders') {
    if (btnFolders) {
      btnFolders.className = 'text-xs py-1 px-3 rounded bg-white text-black font-semibold transition';
    }
    if (btnAll) {
      btnAll.className = 'text-xs py-1 px-3 rounded text-[#a0a0ab] hover:text-white font-medium transition';
    }
    if (viewFolders) viewFolders.classList.remove('hidden');
    if (viewIndividual) viewIndividual.classList.add('hidden');
    loadStrategyFolders();
  } else {
    if (btnFolders) {
      btnFolders.className = 'text-xs py-1 px-3 rounded text-[#a0a0ab] hover:text-white font-medium transition';
    }
    if (btnAll) {
      btnAll.className = 'text-xs py-1 px-3 rounded bg-white text-black font-semibold transition';
    }
    if (viewFolders) viewFolders.classList.add('hidden');
    if (viewIndividual) viewIndividual.classList.remove('hidden');
    loadSavedStrategies();
  }
}
window.switchSavedStrategiesView = switchSavedStrategiesView;

function refreshStrategiesView() {
  if (state.savedStrategiesViewMode === 'folders') {
    loadStrategyFolders();
  } else {
    loadSavedStrategies();
  }
}
window.refreshStrategiesView = refreshStrategiesView;

async function loadStrategyFolders() {
  const container = document.getElementById('saved-folders-grid');
  const countBadge = document.getElementById('saved-folders-count');
  if (!container) return;

  container.innerHTML = `
    <div class="col-span-full py-12 text-center text-[#71717a]">
      <span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span> Cargando carpetas de estrategias...
    </div>
  `;

  try {
    const res = await fetch('/api/strategy-folders');
    const folders = await res.json();
    state.strategyFolders = folders;

    if (countBadge) {
      countBadge.textContent = `${folders.length} carpetas`;
    }

    if (!folders || folders.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-[#71717a]">
          <div class="text-3xl mb-3">📁</div>
          <div class="text-sm font-medium text-white mb-1">Aún no hay carpetas guardadas</div>
          <div class="text-xs">Genera estrategias en el Motor Genético y pulsa "Guardar Todas (Lote)" para crear tu primera carpeta.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = folders.map(f => {
      const symbolsBadges = (f.symbols || []).map(s => `<span class="tn-badge text-[10px] tn-badge-white font-bold">${s}</span>`).join(' ') || '<span class="tn-badge text-[10px]">N/A</span>';
      const timeframesBadges = (f.timeframes || []).map(t => `<span class="tn-badge text-[10px]">${t}</span>`).join(' ');
      const indicatorsBadges = (f.indicators || []).slice(0, 5).map(ind => `<span class="px-1.5 py-0.5 rounded text-[9px] bg-[#1a1a24] text-[#a0a0ab] border border-[#2d2d3a]">${ind}</span>`).join(' ');
      const moreInd = (f.indicators || []).length > 5 ? `<span class="text-[9px] text-[#71717a]">+${f.indicators.length - 5}</span>` : '';

      const netProfitFormatted = (f.total_profit || 0) >= 0
        ? `+$${(f.total_profit || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`
        : `-$${Math.abs(f.total_profit || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

      return `
        <div class="tn-card group hover:border-[#383848] transition flex flex-col justify-between">
          <div>
            <div class="flex items-start justify-between gap-2 mb-2">
              <div class="flex items-center gap-2">
                <span class="text-lg">📁</span>
                <span class="text-xs font-bold text-white tracking-wide truncate max-w-[190px]" title="${f.folder}">
                  ${f.folder}
                </span>
              </div>
              <span class="text-xs font-mono font-bold text-white px-2 py-0.5 rounded bg-[#1c1c24] border border-[#33333f] shrink-0">
                ${f.count} algos
              </span>
            </div>

            <div class="flex flex-wrap gap-1.5 mb-2.5">
              ${symbolsBadges}
              ${timeframesBadges}
            </div>

            <div class="mb-3">
              <div class="text-[10px] text-[#71717a] uppercase font-bold mb-1">Indicadores Usados:</div>
              <div class="flex flex-wrap items-center gap-1">
                ${indicatorsBadges} ${moreInd}
              </div>
            </div>

            <div class="p-2.5 rounded bg-[#09090c] border border-[#22222a] flex items-center justify-between my-2">
              <div>
                <div class="text-[10px] text-[#71717a] uppercase font-bold">Sharpe Medio</div>
                <div class="text-xs font-mono font-bold text-white">${(f.avg_sharpe || 0).toFixed(2)}</div>
              </div>
              <div>
                <div class="text-[10px] text-[#71717a] uppercase font-bold">Win Rate</div>
                <div class="text-xs font-mono font-bold text-white">${(f.avg_win_rate || 0).toFixed(1)}%</div>
              </div>
              <div class="text-right">
                <div class="text-[10px] text-white uppercase font-bold">Net Profit Lote</div>
                <div class="text-xs font-mono font-bold text-white">${netProfitFormatted}</div>
              </div>
            </div>

            <div class="text-[10px] text-[#71717a] mt-1">
              Última actualización: <span class="text-[#a0a0ab]">${f.created_at || 'Reciente'}</span>
            </div>
          </div>

          <div class="mt-4 pt-3 flex items-center justify-between border-t border-[#1e1e24] gap-2">
            <button onclick="viewFolderStrategies('${f.folder}')" class="btn-secondary text-[11px] py-1 px-2.5 flex-1" title="Ver estrategias de este lote">
              👁 Ver Estrategias (${f.count})
            </button>
            <button onclick="useFolderInPortfolio('${f.folder}')" class="btn-primary text-[11px] py-1 px-2.5" title="Enviar todas las estrategias al Creador de Portafolio">
              🧬 + Portafolio
            </button>
            <button onclick="deleteStrategyFolder('${f.folder}')" class="btn-danger text-[11px] py-1 px-2" title="Eliminar carpeta y sus estrategias">
              🗑
            </button>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    console.error('Error loading strategy folders:', err);
    container.innerHTML = `<div class="col-span-full py-8 text-center text-red-400 text-xs">Error al cargar carpetas.</div>`;
  }
}
window.loadStrategyFolders = loadStrategyFolders;

function viewFolderStrategies(folderName) {
  state.savedBatchFilter = folderName;
  const title = document.getElementById('individual-view-title');
  if (title) {
    title.textContent = `Carpeta: ${folderName}`;
  }
  switchSavedStrategiesView('all');
}
window.viewFolderStrategies = viewFolderStrategies;

async function useFolderInPortfolio(folderName) {
  try {
    const res = await fetch('/api/strategies/saved');
    const items = await res.json();
    const folderStrategies = items.filter(s => (s.folder === folderName) || (s.batch_name === folderName));
    
    if (folderStrategies.length === 0) {
      alert(`No se encontraron estrategias en la carpeta "${folderName}".`);
      return;
    }

    folderStrategies.forEach(s => {
      state.portfolioSelectedIds.add((s.strategy || s).id);
    });

    alert(`✓ Se agregaron ${folderStrategies.length} estrategias de la carpeta "${folderName}" al Creador de Portafolio.`);
    showSection('portfolio-builder');
  } catch (err) {
    console.error('Error using folder in portfolio:', err);
    alert('Error al transferir carpeta a portafolio.');
  }
}
window.useFolderInPortfolio = useFolderInPortfolio;

async function deleteStrategyFolder(folderName) {
  if (!confirm(`¿Estás seguro de eliminar la carpeta "${folderName}" y todos sus algoritmos?`)) return;
  try {
    const res = await fetch(`/api/strategy-folder/${encodeURIComponent(folderName)}`, { method: 'DELETE' });
    if (res.ok) {
      loadStrategyFolders();
      refreshSidebarBadges();
    } else {
      alert('Error al eliminar la carpeta.');
    }
  } catch (err) {
    console.error('Error deleting folder:', err);
  }
}
window.deleteStrategyFolder = deleteStrategyFolder;

// ============================================================================
// INDIVIDUAL SAVED STRATEGIES VIEW (WITH PAIR & BATCH FILTERS)
// ============================================================================

async function loadSavedStrategies() {
  const container = document.getElementById('saved-strategies-grid');
  const countBadge = document.getElementById('saved-strategies-count');
  if (!container) return;

  container.innerHTML = `
    <div class="col-span-full py-12 text-center text-[#71717a]">
      <span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span> Cargando estrategias guardadas...
    </div>
  `;

  try {
    const res = await fetch('/api/strategies/saved');
    state.savedStrategies = await res.json();
    
    if (countBadge) {
      countBadge.textContent = `${state.savedStrategies.length} estrategias`;
    }
    const sidebarBadge = document.getElementById('badge-sidebar-strategies');
    if (sidebarBadge) {
      sidebarBadge.textContent = state.savedStrategies.length;
    }

    renderSavedStrategiesFilters();
    renderSavedStrategiesGrid();

  } catch (err) {
    console.error('Error loading saved strategies:', err);
    container.innerHTML = `<div class="col-span-full py-8 text-center text-red-400 text-xs">Error al cargar estrategias guardadas.</div>`;
  }
}
window.loadSavedStrategies = loadSavedStrategies;

function renderSavedStrategiesFilters() {
  const pairContainer = document.getElementById('saved-pair-filters');
  const batchSelect = document.getElementById('saved-batch-select');
  if (!pairContainer || !batchSelect) return;

  // Extract unique symbols and batches/folders
  const symbols = Array.from(new Set(state.savedStrategies.map(s => (s.strategy || s).symbol).filter(Boolean)));
  const batches = Array.from(new Set(state.savedStrategies.map(s => s.folder || s.batch_name).filter(Boolean)));

  // Render pair filter buttons
  pairContainer.innerHTML = `
    <span class="text-[11px] text-[#71717a] uppercase font-bold mr-1">Filtrar Par:</span>
    <button class="pair-filter-btn ${state.savedPairFilter === 'ALL' ? 'active' : ''} text-xs py-1 px-2.5 rounded" data-pair="ALL" onclick="filterSavedStrategiesByPair('ALL')">TODOS</button>
    ${symbols.map(sym => `
      <button class="pair-filter-btn ${state.savedPairFilter === sym ? 'active' : ''} text-xs py-1 px-2.5 rounded" data-pair="${sym}" onclick="filterSavedStrategiesByPair('${sym}')">${sym}</button>
    `).join('')}
  `;

  // Render batch select options
  batchSelect.innerHTML = `
    <option value="ALL">Todas las Carpetas (${state.savedStrategies.length})</option>
    ${batches.map(b => `<option value="${b}" ${state.savedBatchFilter === b ? 'selected' : ''}>${b}</option>`).join('')}
  `;
}

function filterSavedStrategiesByPair(pair) {
  state.savedPairFilter = pair;
  document.querySelectorAll('.pair-filter-btn').forEach(b => {
    b.classList.toggle('active', b.getAttribute('data-pair') === pair);
  });
  renderSavedStrategiesGrid();
}
window.filterSavedStrategiesByPair = filterSavedStrategiesByPair;

function filterSavedStrategiesByBatch(batch) {
  state.savedBatchFilter = batch;
  renderSavedStrategiesGrid();
}
window.filterSavedStrategiesByBatch = filterSavedStrategiesByBatch;

function renderSavedStrategiesGrid() {
  const container = document.getElementById('saved-strategies-grid');
  if (!container) return;

  let items = state.savedStrategies;
  if (state.savedPairFilter !== 'ALL') {
    items = items.filter(cand => (cand.strategy || cand).symbol === state.savedPairFilter);
  }
  if (state.savedBatchFilter !== 'ALL') {
    items = items.filter(cand => (cand.folder === state.savedBatchFilter) || (cand.batch_name === state.savedBatchFilter));
  }

  if (items.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-12 text-center text-[#71717a]">
        <div class="text-3xl mb-3">💾</div>
        <div class="text-sm font-medium text-white mb-1">Sin estrategias en este filtro</div>
        <div class="text-xs">Prueba seleccionando otro par o lote en los filtros superiores.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = items.map((cand) => {
    const s = cand.strategy || cand;
    const m = cand.metrics || {};
    const netProfitFormatted = m.total_return_usd !== undefined
      ? `${m.total_return_usd >= 0 ? '+' : ''}$${m.total_return_usd.toLocaleString(undefined, {minimumFractionDigits: 2})}`
      : 'N/A';
    const initialDepositFormatted = `$${(m.initial_capital || 10000).toLocaleString()}`;
    const folderDisplay = cand.folder || cand.batch_name || '';

    return `
      <div class="candidate-card group">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-semibold text-white tracking-wide truncate max-w-[180px]" data-rename-kind="strategy" data-rename-id="${s.id}">${escapeWorkspaceText(s.name || s.id)}</span>
          <span class="text-xs font-mono font-bold text-white px-2 py-0.5 rounded bg-[#1c1c24] border border-[#33333f]">
            ${m.tn_score ? 'TN ' + m.tn_score : 'GUARDADA'}
          </span>
        </div>

        <div class="flex flex-wrap gap-1.5 mb-2">
          <span class="tn-badge text-[10px] tn-badge-white font-bold">${s.symbol || 'N/A'}</span>
          <span class="tn-badge text-[10px]">${s.timeframe || '1h'}</span>
          <span class="tn-badge text-[10px]">${s.entry_order_type || 'MARKET'}</span>
          <span class="tn-badge text-[10px] text-[#a0a0ab]">${(s.exit_mode || 'ATR_CLASSIC').replace('_', ' ')}</span>
        </div>

        ${folderDisplay ? `<div class="text-[10px] font-mono text-[#717182] truncate mb-2">📁 ${folderDisplay}</div>` : ''}

        <div class="p-2.5 rounded bg-[#09090c] border border-[#22222a] flex items-center justify-between my-1">
          <div>
            <div class="text-[10px] text-[#71717a] uppercase font-bold">Capital Inicial</div>
            <div class="text-xs font-mono text-[#a0a0ab]">${initialDepositFormatted}</div>
          </div>
          <div class="text-right">
            <div class="text-[10px] text-white uppercase font-bold">Net Profit</div>
            <div class="text-sm font-mono font-bold text-white">${netProfitFormatted}</div>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-1.5 mt-2 pt-2 border-t border-[#1e1e26] text-center">
          <div>
            <div class="text-[9px] text-[#71717a] uppercase">Sharpe</div>
            <div class="text-xs font-mono font-semibold text-white">${(m.sharpe_ratio || 0).toFixed(2)}</div>
          </div>
          <div>
            <div class="text-[9px] text-[#71717a] uppercase">Win Rate</div>
            <div class="text-xs font-mono font-semibold text-white">${(m.win_rate_pct || 0).toFixed(1)}%</div>
          </div>
          <div>
            <div class="text-[9px] text-[#71717a] uppercase">Drawdown</div>
            <div class="text-xs font-mono font-semibold text-white">${(m.max_drawdown_pct || 0).toFixed(1)}%</div>
          </div>
          <div>
            <div class="text-[9px] text-[#71717a] uppercase">Trades</div>
            <div class="text-xs font-mono font-semibold text-white">${m.total_trades || 0}</div>
          </div>
        </div>

        <div class="mt-3 pt-2.5 flex items-center justify-between border-t border-[#1e1e24] gap-2">
          <button onclick="openCandidateModal('${s.id}')" class="btn-secondary text-[11px] py-1 px-2.5 flex-1 flex items-center justify-center gap-1.5" title="Ver análisis completo, backtest y reglas">
            📊 Ver Análisis
          </button>
          <button onclick="useStrategyInPortfolio('${s.id}')" class="btn-primary text-[11px] py-1 px-2.5 flex-1" title="Añadir al Creador de Portafolio">
            + Portafolio
          </button>
          <button onclick="deleteSavedStrategy('${s.id}')" class="btn-danger text-[11px] py-1 px-2" title="Eliminar de guardadas">
            🗑
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function useStrategyInPortfolio(strategyId) {
  state.portfolioSelectedIds.add(strategyId);
  showSection('portfolio-builder');
}
window.useStrategyInPortfolio = useStrategyInPortfolio;

// ============================================================================
// PORTFOLIO BUILDER & CHECKLIST (MULTI-PAR & MULTI-LOTE SELECTION)
// ============================================================================

async function renderPortfolioStrategyChecklist() {
  const container = document.getElementById('portfolio-strategy-checklist');
  if (!container) return;

  if (!state.portfolioSelectedIds) {
    state.portfolioSelectedIds = new Set();
  }

  container.innerHTML = `
    <div class="col-span-full py-8 text-center text-[#71717a] text-xs">
      <span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span> Cargando estrategias entre pares y lotes...
    </div>
  `;

  try {
    const res = await fetch('/api/strategies/saved');
    let items = await res.json();
    if (!Array.isArray(items)) items = [];

    // Include any active candidates in engine if they aren't saved yet
    if (state.candidates && state.candidates.length > 0) {
      const savedIds = new Set(items.map(s => (s.strategy || s).id));
      state.candidates.forEach(c => {
        if (!savedIds.has(c.strategy.id)) {
          items.push(c);
        }
      });
    }

    state.availableForPortfolio = items;

    if (items.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-8 text-center text-[#71717a] text-xs">
          No hay estrategias guardadas ni candidatas activas aún.<br>
          <button onclick="showSection('engine')" class="btn-primary text-xs mt-3">Ir al Motor Genético y Crear Estrategias →</button>
        </div>
      `;
      updatePortfolioMultiPairBanner();
      return;
    }

    // Default select first 10 if nothing is selected yet
    if (state.portfolioSelectedIds.size === 0) {
      items.slice(0, 10).forEach(it => {
        const sid = (it.strategy || it).id;
        if (sid) state.portfolioSelectedIds.add(sid);
      });
    }

    renderPortfolioFilterControls();
    renderFilteredPortfolioChecklist();

  } catch (err) {
    console.error('Error rendering portfolio checklist:', err);
    container.innerHTML = `<div class="col-span-full py-8 text-center text-red-400 text-xs">Error al cargar lista de estrategias: ${err.message || err}</div>`;
  }
}
window.renderPortfolioStrategyChecklist = renderPortfolioStrategyChecklist;

function selectCurrentBatchOnly() {
  let targetItems = state.availableForPortfolio || [];
  if (state.portfolioBatchFilter && state.portfolioBatchFilter !== 'ALL') {
    targetItems = targetItems.filter(it => (it.folder === state.portfolioBatchFilter) || (it.batch_name === state.portfolioBatchFilter));
  }
  if (state.portfolioPairFilter && state.portfolioPairFilter !== 'ALL') {
    targetItems = targetItems.filter(it => (it.strategy || it).symbol === state.portfolioPairFilter);
  }

  targetItems.forEach(it => {
    const sid = (it.strategy || it).id;
    if (sid) state.portfolioSelectedIds.add(sid);
  });

  renderFilteredPortfolioChecklist();
}
window.selectCurrentBatchOnly = selectCurrentBatchOnly;

function renderPortfolioFilterControls() {
  const pairContainer = document.getElementById('portfolio-pair-filters');
  const batchSelect = document.getElementById('portfolio-batch-select');
  if (!pairContainer || !batchSelect) return;

  const items = state.availableForPortfolio || [];
  const symbols = Array.from(new Set(items.map(s => (s.strategy || s).symbol).filter(Boolean)));
  const batches = Array.from(new Set(items.map(s => s.folder || s.batch_name).filter(Boolean)));

  pairContainer.innerHTML = `
    <span class="text-[10px] text-[#71717a] uppercase font-bold mr-1">Filtrar Par:</span>
    <button class="port-pair-filter ${state.portfolioPairFilter === 'ALL' ? 'active' : ''} text-xs py-1 px-2.5 rounded" data-pair="ALL" onclick="filterPortfolioChecklistByPair('ALL')">TODOS</button>
    ${symbols.map(sym => `
      <button class="port-pair-filter ${state.portfolioPairFilter === sym ? 'active' : ''} text-xs py-1 px-2.5 rounded font-mono" data-pair="${sym}" onclick="filterPortfolioChecklistByPair('${sym}')">${sym}</button>
    `).join('')}
  `;

  batchSelect.innerHTML = `
    <option value="ALL">Todas las Carpetas / Lotes (${items.length})</option>
    ${batches.map(b => `<option value="${b}" ${state.portfolioBatchFilter === b ? 'selected' : ''}>${b}</option>`).join('')}
  `;
}

function filterPortfolioChecklistByPair(pair) {
  state.portfolioPairFilter = pair;
  document.querySelectorAll('.port-pair-filter').forEach(b => {
    b.classList.toggle('active', b.getAttribute('data-pair') === pair);
  });
  renderFilteredPortfolioChecklist();
}
window.filterPortfolioChecklistByPair = filterPortfolioChecklistByPair;

function filterPortfolioChecklistByBatch(batch) {
  state.portfolioBatchFilter = batch;
  renderFilteredPortfolioChecklist();
}
window.filterPortfolioChecklistByBatch = filterPortfolioChecklistByBatch;

function renderFilteredPortfolioChecklist() {
  const container = document.getElementById('portfolio-strategy-checklist');
  if (!container) return;

  if (!state.portfolioSelectedIds) {
    state.portfolioSelectedIds = new Set();
  }

  let items = state.availableForPortfolio || [];
  if (state.portfolioPairFilter && state.portfolioPairFilter !== 'ALL') {
    items = items.filter(it => (it.strategy || it).symbol === state.portfolioPairFilter);
  }
  if (state.portfolioBatchFilter && state.portfolioBatchFilter !== 'ALL') {
    items = items.filter(it => (it.folder === state.portfolioBatchFilter) || (it.batch_name === state.portfolioBatchFilter));
  }

  if (items.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-8 text-center text-[#71717a] text-xs">
        Sin estrategias en este filtro de par/lote.
      </div>
    `;
    updatePortfolioMultiPairBanner();
    return;
  }

  container.innerHTML = items.map((item, idx) => {
    const s = item.strategy || item || {};
    const m = item.metrics || {};
    const sid = s.id || `strat_${idx}`;
    const isChecked = state.portfolioSelectedIds.has(sid);
    const netProfit = m.total_return_usd !== undefined ? `${m.total_return_usd >= 0 ? '+' : ''}$${Number(m.total_return_usd).toFixed(0)}` : '';
    const folderDisplay = item.folder || item.batch_name || '';

    return `
      <label class="portfolio-strategy-check ${isChecked ? 'checked' : ''}" for="port-cb-${sid}">
        <input type="checkbox" id="port-cb-${sid}" value="${sid}" ${isChecked ? 'checked' : ''} class="port-strategy-cb w-4 h-4 accent-white mt-1 cursor-pointer">
        <div class="flex-1 min-w-0">
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-semibold text-white truncate max-w-[170px]">${s.name || sid}</span>
            <span class="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-white text-black">${s.symbol || 'N/A'}</span>
          </div>
          <div class="flex items-center justify-between text-[11px] text-[#a0a0ab]">
            <span>${s.timeframe || '1h'} · WR: <strong class="text-white">${Number(m.win_rate_pct || 0).toFixed(0)}%</strong> · Sh: <strong class="text-white">${Number(m.sharpe_ratio || 0).toFixed(1)}</strong></span>
            <span class="font-mono text-white font-semibold">${netProfit}</span>
          </div>
          ${folderDisplay ? `<div class="text-[9px] font-mono text-[#717182] mt-1 truncate">📁 ${folderDisplay}</div>` : ''}
        </div>
      </label>
    `;
  }).join('');

  document.querySelectorAll('.port-strategy-cb').forEach(cb => {
    cb.addEventListener('change', (e) => {
      const val = e.target.value;
      const parent = e.target.closest('.portfolio-strategy-check');
      if (e.target.checked) {
        state.portfolioSelectedIds.add(val);
        parent?.classList.add('checked');
      } else {
        state.portfolioSelectedIds.delete(val);
        parent?.classList.remove('checked');
      }
      updatePortfolioMultiPairBanner();
    });
  });

  updatePortfolioMultiPairBanner();
}

function updatePortfolioMultiPairBanner() {
  const counter = document.getElementById('portfolio-selected-count');
  const tagsContainer = document.getElementById('portfolio-active-pairs-tags');
  const mixScoreEl = document.getElementById('portfolio-mix-score');
  const summaryEl = document.getElementById('portfolio-selection-summary');

  const selectedList = state.availableForPortfolio.filter(it => state.portfolioSelectedIds.has((it.strategy || it).id));
  const totalCount = selectedList.length;

  if (counter) counter.textContent = totalCount;

  // Group by pair symbol
  const pairsMap = {};
  selectedList.forEach(it => {
    const sym = (it.strategy || it).symbol || 'N/A';
    pairsMap[sym] = (pairsMap[sym] || 0) + 1;
  });

  const distinctPairs = Object.keys(pairsMap);

  if (tagsContainer) {
    if (distinctPairs.length === 0) {
      tagsContainer.innerHTML = `<span class="text-[11px] text-[#71717a]">Ningún par seleccionado aún</span>`;
    } else {
      tagsContainer.innerHTML = distinctPairs.map(sym => `
        <span class="px-2 py-0.5 rounded bg-[#1c1c28] border border-[#333345] text-white font-mono font-bold text-[10px]">
          ${sym} (${pairsMap[sym]})
        </span>
      `).join('');
    }
  }

  if (mixScoreEl) {
    if (distinctPairs.length >= 3) {
      mixScoreEl.innerHTML = `<span class="text-emerald-400 font-bold">🔥 Óptima (${distinctPairs.length} pares distintos · ~45% - 50% amortiguación Drawdown)</span>`;
    } else if (distinctPairs.length === 2) {
      mixScoreEl.innerHTML = `<span class="text-white font-bold">⚡ Buena (2 pares distintos · ~30% amortiguación Drawdown)</span>`;
    } else if (distinctPairs.length === 1) {
      mixScoreEl.innerHTML = `<span class="text-[#a0a0ab]">⚠️ Monopar (Riesgo concentrado en 1 par · sin descorrelación cruzada)</span>`;
    } else {
      mixScoreEl.textContent = 'Sin selección';
    }
  }

  if (summaryEl) {
    if (distinctPairs.length >= 2) {
      summaryEl.innerHTML = `Excelente combinación multi-activo: mezcla estrategias entre <strong class="text-white">${distinctPairs.join(', ')}</strong> para suavizar la curva de equidad global.`;
    } else if (totalCount >= 2) {
      summaryEl.innerHTML = `Para una descorrelación superior según StrategyQuant y TradingNote, añade estrategias de otros pares (ej. combina EURUSD con XAUUSD o NASDAQ).`;
    } else {
      summaryEl.textContent = `Selecciona al menos 2 estrategias (preferiblemente de distintos pares) para crear el portafolio.`;
    }
  }
}

// 🎲 1 Mejor de Cada Par
function selectTopOnePerPair() {
  if (!state.availableForPortfolio || state.availableForPortfolio.length === 0) return;

  const bestByPair = {};
  state.availableForPortfolio.forEach(item => {
    const s = item.strategy || item;
    const m = item.metrics || {};
    const sym = s.symbol || 'N/A';
    const score = m.tn_score || (m.sharpe_ratio * 10) || 0;

    if (!bestByPair[sym] || score > bestByPair[sym].score) {
      bestByPair[sym] = { id: s.id, score: score };
    }
  });

  state.portfolioSelectedIds.clear();
  Object.values(bestByPair).forEach(entry => {
    state.portfolioSelectedIds.add(entry.id);
  });

  renderFilteredPortfolioChecklist();
  alert(`✓ Selección multi-par aplicada: Se marcó la mejor estrategia de cada uno de los ${Object.keys(bestByPair).length} pares disponibles (${Object.keys(bestByPair).join(', ')}).`);
}
window.selectTopOnePerPair = selectTopOnePerPair;

function selectAllVisiblePortfolioStrategies() {
  let items = state.availableForPortfolio || [];
  if (state.portfolioPairFilter && state.portfolioPairFilter !== 'ALL') {
    items = items.filter(it => (it.strategy || it).symbol === state.portfolioPairFilter);
  }
  if (state.portfolioBatchFilter && state.portfolioBatchFilter !== 'ALL') {
    items = items.filter(it => (it.folder === state.portfolioBatchFilter) || (it.batch_name === state.portfolioBatchFilter));
  }

  items.forEach(it => {
    const sid = (it.strategy || it).id;
    if (sid) state.portfolioSelectedIds.add(sid);
  });
  renderFilteredPortfolioChecklist();
}
window.selectAllVisiblePortfolioStrategies = selectAllVisiblePortfolioStrategies;

function deselectAllPortfolioStrategies() {
  state.portfolioSelectedIds.clear();
  renderFilteredPortfolioChecklist();
}
window.deselectAllPortfolioStrategies = deselectAllPortfolioStrategies;

async function createPortfolio() {
  const nameInput = document.getElementById('portfolio-name-input');
  const folderInput = document.getElementById('portfolio-folder-input');
  const maxInput = document.getElementById('portfolio-max-strategies');
  const riskInput = document.getElementById('portfolio-risk-budget');
  const btn = document.getElementById('btn-create-portfolio');

  if (state.portfolioSelectedIds.size < 2) {
    alert('Selecciona al menos 2 estrategias (preferiblemente de distintos pares) para combinar en el portafolio.');
    return;
  }

  const selectedIds = Array.from(state.portfolioSelectedIds);
  const maxStrategies = parseInt(maxInput?.value) || 10;
  const riskBudget = parseFloat(riskInput?.value) || 1.0;
  const portfolioFolder = folderInput?.value.trim() || 'Portafolios_Principales';
  const portfolioName = nameInput?.value.trim() || `Portafolio Multi-Par (${selectedIds.length} Algoritmos)`;

  const payload = {
    name: portfolioName,
    strategy_ids: selectedIds,
    max_strategies: maxStrategies,
    risk_budget: riskBudget,
    folder: portfolioFolder
  };

  const originalText = btn.innerHTML;
  btn.innerHTML = `<span class="animate-spin inline-block w-3 h-3 border-2 border-black border-t-transparent rounded-full mr-2"></span> Creando y Optimizando Multi-Par...`;
  btn.disabled = true;

  try {
    const res = await fetch('/api/portfolio/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      alert(`Error al crear portafolio: ${err.detail || 'Ocurrió un error.'}`);
      return;
    }

    const data = await res.json();
    const port = data.portfolio || {};
    const met = port.metrics || {};
    const symbolsList = (met.symbols || []).join(' + ') || 'Multi-Par';

    alert(`✓ Portafolio Multi-Par "${port.name}" creado con éxito en la carpeta "${portfolioFolder}"!\n\n• Pares combinados: ${symbolsList}\n• Total de estrategias: ${met.strategies_count}\n• Descorrelación / Diversificación: ${met.diversification_score}%\n• Reducción de Drawdown estimada: -${met.estimated_dd_reduction_pct}%\n• Net Profit combinado estimado: $${(met.combined_net_profit_usd || 0).toLocaleString()}`);

    showSection('saved-portfolios');

  } catch (err) {
    console.error('Error creating portfolio:', err);
    alert('Error de conexión al crear portafolio.');
  } finally {
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}
window.createPortfolio = createPortfolio;

// ============================================================================
// PORTFOLIO ENGINE (MULTI-PAIR EXPLORATION & LIVE RESULTS TOP)
// ============================================================================

function switchPortSubTab(subTabName) {
  const tabs = ['results', 'config', 'strategies'];
  tabs.forEach(t => {
    const btn = document.getElementById(`tab-port-btn-${t}`);
    const view = document.getElementById(`tab-port-view-${t}`);
    if (t === subTabName) {
      if (btn) {
        btn.className = 'py-3 font-semibold border-b-2 border-white text-white flex items-center gap-2';
      }
      if (view) view.classList.remove('hidden');
    } else {
      if (btn) {
        btn.className = 'py-3 font-medium border-b-2 border-transparent text-[#a0a0ab] hover:text-white flex items-center gap-2';
      }
      if (view) view.classList.add('hidden');
    }
  });
}
window.switchPortSubTab = switchPortSubTab;

async function startPortfolioEngine() {
  const minStrat = parseInt(document.getElementById('input-port-min-strat')?.value) || 2;
  const maxStrat = parseInt(document.getElementById('input-port-max-strat')?.value) || 5;
  const weightMode = document.getElementById('select-port-weight-mode')?.value || 'EQUAL';
  const objective = document.getElementById('select-port-objective')?.value || 'diversification_score';
  const minDiv = parseFloat(document.getElementById('input-port-min-div')?.value) || 25.0;
  const maxTop = parseInt(document.getElementById('input-port-max-top')?.value) || 50;
  const targetFolder = document.getElementById('input-port-target-folder')?.value?.trim() || 'Portafolios_Principales';

  const payload = {
    min_strategies: minStrat,
    max_strategies: maxStrat,
    weight_mode: weightMode,
    objective: objective,
    min_diversification: minDiv,
    max_portfolios: maxTop,
    folder: targetFolder
  };

  try {
    const res = await fetch('/api/portfolio-engine/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      alert('Error al iniciar motor de portafolios.');
      return;
    }

    state.portEngineRunning = true;
    updatePortEngineUIState(true);
    switchPortSubTab('results');

    // Start polling
    if (state.portEngineTimer) clearInterval(state.portEngineTimer);
    state.portEngineTimer = setInterval(pollPortfolioEngine, 1000);
    pollPortfolioEngine();

  } catch (err) {
    console.error('Error starting portfolio engine:', err);
    alert('Error de conexión al iniciar motor de portafolios.');
  }
}
window.startPortfolioEngine = startPortfolioEngine;

async function stopPortfolioEngine() {
  try {
    await fetch('/api/portfolio-engine/stop', { method: 'POST' });
    state.portEngineRunning = false;
    updatePortEngineUIState(false);
    if (state.portEngineTimer) {
      clearInterval(state.portEngineTimer);
      state.portEngineTimer = null;
    }
  } catch (err) {
    console.error('Error stopping portfolio engine:', err);
  }
}
window.stopPortfolioEngine = stopPortfolioEngine;

function updatePortEngineUIState(isRunning) {
  const startBtn = document.getElementById('btn-start-port-engine');
  const stopBtn = document.getElementById('btn-stop-port-engine');
  const pill = document.getElementById('port-engine-status-pill');

  if (startBtn) startBtn.classList.toggle('hidden', isRunning);
  if (stopBtn) stopBtn.classList.toggle('hidden', !isRunning);
  if (pill) pill.classList.toggle('hidden', !isRunning);
}

async function pollPortfolioEngine() {
  try {
    const [resStatus, resTop] = await Promise.all([
      fetch('/api/portfolio-engine/status'),
      fetch('/api/portfolio-engine/top')
    ]);

    if (!resStatus.ok || !resTop.ok) return;

    const st = await resStatus.json();
    const topItems = await resTop.json();

    state.portEngineRunning = st.is_running;
    updatePortEngineUIState(st.is_running);

    // Update Telemetry Bar
    const testedEl = document.getElementById('port-metric-tested');
    const acceptedEl = document.getElementById('port-metric-accepted');
    const bestDivEl = document.getElementById('port-metric-best-div');
    const bestSharpeEl = document.getElementById('port-metric-best-sharpe');
    const badgeTopCount = document.getElementById('badge-port-top-count');

    if (testedEl) testedEl.textContent = (st.tested_count || 0).toLocaleString();
    if (acceptedEl) acceptedEl.textContent = (st.accepted_count || 0).toLocaleString();
    if (badgeTopCount) badgeTopCount.textContent = topItems.length;

    if (st.best_portfolio && st.best_portfolio.metrics) {
      const bm = st.best_portfolio.metrics;
      if (bestDivEl) bestDivEl.textContent = `${(bm.diversification_score || 0).toFixed(1)}%`;
      if (bestSharpeEl) bestSharpeEl.textContent = (bm.combined_sharpe || 1.0).toFixed(2);
    }

    renderPortfolioEngineCards(topItems);

  } catch (err) {
    console.error('Error polling portfolio engine:', err);
  }
}

function changePortfoliosSort(val) {
  state.portfoliosSortBy = val;
  const badge = document.getElementById('port-ranking-badge');
  if (badge) {
    const labels = {
      ret_dd: 'ORDEN: POR RET / MAX DD',
      sq_corr: 'ORDEN: POR DESCORRELACIÓN SQ',
      net_profit: 'ORDEN: POR NET PROFIT',
      dd_reduction: 'ORDEN: POR REDUCCIÓN DE DD',
      min_dd: 'ORDEN: MENOR DRAWDOWN',
      sharpe: 'ORDEN: POR SHARPE',
      score: 'ORDEN: POR TN SCORE'
    };
    badge.textContent = labels[val] || 'ORDEN: POR RET / MAX DD';
  }
  renderPortfolioEngineCards(window.__livePortfoliosCache || []);
}
window.changePortfoliosSort = changePortfoliosSort;

function renderPortfolioEngineCards(items) {
  const container = document.getElementById('port-engine-cards-grid');
  if (!container) return;

  if (!items || items.length === 0) {
    if (!state.portEngineRunning) {
      container.innerHTML = `
        <div class="col-span-full py-16 text-center text-[#71717a]">
          <div class="text-4xl mb-3">🧬</div>
          <div class="text-sm font-medium text-white mb-1">El Motor de Portafolios está listo</div>
          <div class="text-xs max-w-md mx-auto mb-4">Haz clic en <strong>"Iniciar Motor de Portafolios"</strong> para comenzar a generar y clasificar combinaciones multi-par en tiempo real.</div>
          <button class="btn-primary text-xs py-2 px-5 font-bold" onclick="startPortfolioEngine()">
            ▶ Iniciar Exploración de Portafolios
          </button>
        </div>
      `;
    } else {
      container.innerHTML = `
        <div class="col-span-full py-16 text-center text-[#71717a]">
          <span class="animate-spin inline-block w-6 h-6 border-2 border-white border-t-transparent rounded-full mb-3"></span>
          <div class="text-sm font-medium text-white mb-1">Evaluando combinaciones multi-activo...</div>
          <div class="text-xs">Los mejores portafolios aparecerán aquí ordenados en el ranking TOP.</div>
        </div>
      `;
    }
    return;
  }

  // Cache live items in memory for modal preview
  window.__livePortfoliosCache = items;

  let sortedItems = [...items];
  const sortBy = state.portfoliosSortBy || 'ret_dd';
  sortedItems.sort((a, b) => {
    const ma = a.metrics || {};
    const mb = b.metrics || {};
    if (sortBy === 'ret_dd') {
      return (mb.ret_to_dd_ratio || 0) - (ma.ret_to_dd_ratio || 0);
    } else if (sortBy === 'sq_corr') {
      const sqA = ma.sq_correlation_index !== undefined ? ma.sq_correlation_index : 0.5;
      const sqB = mb.sq_correlation_index !== undefined ? mb.sq_correlation_index : 0.5;
      return sqA - sqB; // Lower SQ index = better decorrelation
    } else if (sortBy === 'net_profit') {
      return (mb.combined_net_profit_usd || 0) - (ma.combined_net_profit_usd || 0);
    } else if (sortBy === 'dd_reduction') {
      const redA = ma.dd_reduction_pct !== undefined ? ma.dd_reduction_pct : (ma.estimated_dd_reduction_pct || 0);
      const redB = mb.dd_reduction_pct !== undefined ? mb.dd_reduction_pct : (mb.estimated_dd_reduction_pct || 0);
      return redB - redA;
    } else if (sortBy === 'min_dd') {
      return (ma.combined_max_drawdown_pct || 999) - (mb.combined_max_drawdown_pct || 999);
    } else if (sortBy === 'sharpe') {
      return (mb.combined_sharpe || 0) - (ma.combined_sharpe || 0);
    } else { // 'score'
      return (mb.tn_score || 0) - (ma.tn_score || 0);
    }
  });

  container.innerHTML = sortedItems.map((p, idx) => {
    const m = p.metrics || {};
    const rank = idx + 1;
    const rankBadge = rank === 1 ? '🥇 #1' : rank === 2 ? '🥈 #2' : rank === 3 ? '🥉 #3' : `#${rank}`;
    const symbolsList = (m.symbols || []).map(sym => `<span class="tn-badge text-[10px] tn-badge-white font-bold">${sym}</span>`).join(' ');
    const netProfitFormatted = m.combined_net_profit_usd !== undefined
      ? `${m.combined_net_profit_usd >= 0 ? '+' : ''}$${Number(m.combined_net_profit_usd).toLocaleString(undefined, {minimumFractionDigits: 2})}`
      : 'N/A';
    const retToDd = (m.ret_to_dd_ratio || 0).toFixed(1);
    const maxDdPct = Number(m.combined_max_drawdown_pct || 0).toFixed(1);
    const ddRed = Number(m.dd_reduction_pct !== undefined ? m.dd_reduction_pct : (m.estimated_dd_reduction_pct || 0)).toFixed(1);
    const sqIndex = Number(m.sq_correlation_index || 0.20).toFixed(2);
    const sqRating = m.sq_rating || 'Excelente';

    return `
      <div class="candidate-card group flex flex-col justify-between min-h-[390px] p-4">
        <div>
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <span class="text-xs font-mono font-bold text-white px-2 py-0.5 rounded bg-[#1c1c24] border border-[#33333f]">
                ${rankBadge}
              </span>
              <span class="text-xs font-semibold text-white tracking-wide truncate max-w-[170px]" data-rename-kind="portfolio" data-rename-id="${p.id}">
                ${escapeWorkspaceText(p.name)}
              </span>
            </div>
            <span class="text-xs font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" title="Descorrelación según escala StrategyQuant (0.00 a 1.00)">
              SQ ${sqIndex} · ${sqRating}
            </span>
          </div>

          <div class="flex flex-wrap gap-1.5 mb-2.5">
            ${symbolsList}
            <span class="tn-badge text-[10px]">${m.strategies_count || 0} ESTRATEGIAS</span>
          </div>

          <!-- Sparkline Taller Preview (Curva de Balance Expandida) -->
          <div class="h-20 my-2.5 flex items-center justify-center overflow-hidden px-2 py-1 rounded-lg bg-[#08080b] border border-[#202028] relative">
            ${renderMiniSparklineSvg(p.sparkline || [], idx)}
          </div>

          <div class="p-2.5 rounded bg-[#09090c] border border-[#22222a] flex items-center justify-between my-2">
            <div>
              <div class="text-[10px] text-[#71717a] uppercase font-bold">Capital Inicial</div>
              <div class="text-xs font-mono text-[#a0a0ab]">$10,000</div>
            </div>
            <div class="text-right">
              <div class="text-[10px] text-white uppercase font-bold">Net Profit Comb.</div>
              <div class="text-sm font-mono font-bold text-white">${netProfitFormatted}</div>
            </div>
          </div>

          <!-- Key Metrics: Ret/DD, Max DD, DD Reducción, Sharpe -->
          <div class="grid grid-cols-4 gap-1.5 mt-2.5 pt-2 border-t border-[#1e1e26] text-center">
            <div>
              <div class="text-[9px] text-[#71717a] uppercase font-bold">Ret / Max DD</div>
              <div class="text-xs font-mono font-bold text-emerald-400">${retToDd}x</div>
            </div>
            <div>
              <div class="text-[9px] text-[#71717a] uppercase font-bold">Max DD</div>
              <div class="text-xs font-mono font-semibold text-red-400">${maxDdPct}%</div>
            </div>
            <div>
              <div class="text-[9px] text-[#71717a] uppercase font-bold">DD Reducción</div>
              <div class="text-xs font-mono font-bold text-emerald-400">-${ddRed}%</div>
            </div>
            <div>
              <div class="text-[9px] text-[#71717a] uppercase font-bold">Sharpe</div>
              <div class="text-xs font-mono font-semibold text-white">${Number(m.combined_sharpe || 1.0).toFixed(2)}</div>
            </div>
          </div>
        </div>

        <div class="mt-3.5 pt-2.5 flex items-center justify-between border-t border-[#1e1e24] gap-2">
          <button onclick="openLivePortfolioCandidateModal('${p.id}')" class="btn-secondary text-[11px] py-1.5 px-2.5 flex-1 flex items-center justify-center gap-1.5 font-medium" title="Ver análisis completo de la cartera y curva combinada superpuesta">
            📊 Ver Análisis
          </button>
          <button onclick="savePortfolioCandidateFromEngine('${p.id}')" class="btn-primary text-[11px] py-1.5 px-2.5 flex-1 flex items-center justify-center gap-1.5 font-bold" title="Guardar portafolio en disco">
            💾 Guardar
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function renderMiniSparklineSvg(sparkline, idx = 0) {
  if (!sparkline || sparkline.length < 2) {
    return `<div class="w-full text-center text-[10px] text-[#71717a]">Curva combinada suave</div>`;
  }
  const min = Math.min(...sparkline);
  const max = Math.max(...sparkline);
  const range = (max - min) || 1;
  const h = 64;
  const w = 320;
  const pad = 6;
  const points = sparkline.map((val, i) => {
    const x = (i / (sparkline.length - 1)) * w;
    const y = (h - pad) - ((val - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  const gradId = `spark-port-grad-${idx}-${Math.floor(Math.random() * 10000)}`;

  return `
    <svg viewBox="0 0 ${w} ${h}" class="w-full h-full overflow-visible" preserveAspectRatio="none">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.18" />
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0.01" />
        </linearGradient>
      </defs>
      <polygon fill="url(#${gradId})" points="0,${h} ${points} ${w},${h}" />
      <polyline fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" points="${points}" />
    </svg>
  `;
}

function openLivePortfolioCandidateModal(candId) {
  const p = (window.__livePortfoliosCache || []).find(it => it.id === candId);
  if (!p) {
    alert('Portafolio no encontrado.');
    return;
  }
  const modal = document.getElementById('portfolio-detail-modal');
  if (!modal) return;
  modal.classList.remove('hidden');

  document.getElementById('port-modal-title').textContent = p.name;
  document.getElementById('port-modal-subtitle').textContent = `Candidato Top · ${p.created_at} · Algoritmos Combinados: ${p.strategies?.length || 0}`;

  const met = p.metrics || {};
  document.getElementById('port-modal-pnl').textContent = `+$${Number(met.combined_net_profit_usd || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}`;
  
  // StrategyQuant KPIs: Max DD, Ret/DD, Real DD Reduction, SQ Correlation (0.0 to 1.0)
  const maxDdEl = document.getElementById('port-modal-max-dd');
  const avgIndDdEl = document.getElementById('port-modal-avg-ind-dd');
  const retDdEl = document.getElementById('port-modal-ret-dd');
  const ddRedEl = document.getElementById('port-modal-dd-red');
  const sqCorrEl = document.getElementById('port-modal-sq-corr');
  const wrEl = document.getElementById('port-modal-wr');

  if (maxDdEl) maxDdEl.textContent = `${Number(met.combined_max_drawdown_pct || 0).toFixed(2)}% ($${Number(met.combined_max_drawdown_usd || 0).toLocaleString()})`;
  if (avgIndDdEl) avgIndDdEl.textContent = `vs ${Number(met.avg_individual_dd_pct || 0).toFixed(2)}% individual prom.`;
  if (retDdEl) retDdEl.textContent = `${Number(met.ret_to_dd_ratio || 0).toFixed(1)}x`;
  if (ddRedEl) ddRedEl.textContent = `-${Number(met.dd_reduction_pct || met.estimated_dd_reduction_pct || 0).toFixed(1)}%`;
  if (sqCorrEl) sqCorrEl.textContent = `${Number(met.sq_correlation_index || 0.20).toFixed(2)} · ${met.sq_rating || 'Excelente'}`;
  if (wrEl) wrEl.textContent = `Win Rate: ${Number(met.weighted_win_rate_pct || 0).toFixed(1)}%`;

  const exportBtn = document.getElementById('btn-port-modal-export');
  if (exportBtn) {
    exportBtn.onclick = () => savePortfolioCandidateFromEngine(p.id);
    exportBtn.textContent = '💾 Guardar Este Portafolio';
  }

  const tbody = document.getElementById('port-modal-strategies-body');
  if (tbody) {
    const strats = p.strategies || [];
    const weights = p.weights || [];
    tbody.innerHTML = strats.map((st, i) => {
      const s = st.strategy || st;
      const m = st.metrics || {};
      const w = weights[i] || (1 / strats.length);
      const indDd = Number(m.max_drawdown_pct || 0).toFixed(1);
      return `
        <tr class="border-b border-[#1c1c24] hover:bg-[#14141a]">
          <td class="py-2.5 px-3 font-semibold text-white">${s.name || s.id}</td>
          <td class="py-2.5 px-3"><span class="tn-badge tn-badge-white text-[10px]">${s.symbol || '-'}</span></td>
          <td class="py-2.5 px-3 font-mono">${s.timeframe || '1h'}</td>
          <td class="py-2.5 px-3 font-mono font-bold text-white">${Math.round(w * 100)}%</td>
          <td class="py-2.5 px-3 font-mono text-[#a0a0ab]">${(m.win_rate_pct || 0).toFixed(1)}%</td>
          <td class="py-2.5 px-3 font-mono text-white font-semibold">+$${(m.total_return_usd || 0).toLocaleString()}</td>
          <td class="py-2.5 px-3 text-right">
            <button onclick="closePortfolioModal(); openCandidateModal('${s.id}')" class="btn-secondary text-[10px] py-0.5 px-2.5">
              Ver Estrategia
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  renderPortfolioEquityChart(p.equity_curve || [], p.individual_curves || []);
}
window.openLivePortfolioCandidateModal = openLivePortfolioCandidateModal;

async function savePortfolioCandidateFromEngine(candId) {
  const folder = document.getElementById('input-port-target-folder')?.value?.trim() || 'Portafolios_Principales';
  try {
    const res = await fetch('/api/portfolio-engine/save-candidate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candId, folder: folder })
    });
    if (res.ok) {
      const data = await res.json();
      alert(`✓ Portafolio "${data.portfolio.name}" guardado con éxito en la carpeta "${folder}"!`);
      refreshSidebarBadges();
    } else {
      const err = await res.json();
      alert(`Error al guardar: ${err.detail || 'Ocurrió un error'}`);
    }
  } catch (err) {
    console.error('Error saving portfolio candidate:', err);
    alert('Error al guardar portafolio.');
  }
}
window.savePortfolioCandidateFromEngine = savePortfolioCandidateFromEngine;

async function saveAllTopPortfoliosBatch() {
  const defaultFolder = `Lote_Portafolios_Top_${new Date().toISOString().slice(0,10)}`;
  const folder = prompt('Ingresa el nombre de la carpeta para guardar todos los portafolios del Top:', defaultFolder);
  if (!folder) return;

  try {
    const res = await fetch('/api/portfolio-engine/save-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: folder })
    });
    if (res.ok) {
      const data = await res.json();
      alert(`✓ Se guardaron con éxito ${data.count} portafolios en la carpeta "${data.folder}"!`);
      refreshSidebarBadges();
      showSection('saved-portfolios');
    } else {
      alert('Error al guardar lote de portafolios.');
    }
  } catch (err) {
    console.error('Error saving batch portfolios:', err);
    alert('Error de conexión al guardar lote.');
  }
}
window.saveAllTopPortfoliosBatch = saveAllTopPortfoliosBatch;

// ============================================================================
// SAVED PORTFOLIOS VIEW (FOLDERS & INDIVIDUAL)
// ============================================================================

function switchSavedPortfoliosView(mode, folderName = 'ALL') {
  state.savedPortfoliosViewMode = mode;
  state.savedPortfolioSelectedFolder = folderName;
  const btnFolders = document.getElementById('btn-view-port-folders');
  const btnAll = document.getElementById('btn-view-port-all');
  const viewFolders = document.getElementById('view-portfolio-folders');
  const viewIndividual = document.getElementById('view-portfolio-individual');

  if (mode === 'folders') {
    if (btnFolders) {
      btnFolders.className = 'text-xs py-1 px-3 rounded bg-white text-black font-semibold transition';
    }
    if (btnAll) {
      btnAll.className = 'text-xs py-1 px-3 rounded text-[#a0a0ab] hover:text-white font-medium transition';
    }
    if (viewFolders) viewFolders.classList.remove('hidden');
    if (viewIndividual) viewIndividual.classList.add('hidden');
    loadPortfolioFolders();
  } else {
    if (btnFolders) {
      btnFolders.className = 'text-xs py-1 px-3 rounded text-[#a0a0ab] hover:text-white font-medium transition';
    }
    if (btnAll) {
      btnAll.className = 'text-xs py-1 px-3 rounded bg-white text-black font-semibold transition';
    }
    if (viewFolders) viewFolders.classList.add('hidden');
    if (viewIndividual) viewIndividual.classList.remove('hidden');
    loadSavedPortfolios(folderName);
  }
}
window.switchSavedPortfoliosView = switchSavedPortfoliosView;

function refreshPortfoliosView() {
  if (state.savedPortfoliosViewMode === 'folders') {
    loadPortfolioFolders();
  } else {
    loadSavedPortfolios(state.savedPortfolioSelectedFolder || 'ALL');
  }
}
window.refreshPortfoliosView = refreshPortfoliosView;

async function loadPortfolioFolders() {
  const container = document.getElementById('saved-portfolio-folders-grid');
  const countBadge = document.getElementById('saved-portfolio-folders-count');
  if (!container) return;

  container.innerHTML = `
    <div class="col-span-full py-12 text-center text-[#71717a]">
      <span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span> Cargando carpetas de portafolios...
    </div>
  `;

  try {
    const res = await fetch('/api/portfolio-folders');
    const folders = await res.json();
    state.portfolioFolders = folders;

    if (countBadge) {
      countBadge.textContent = `${folders.length} carpetas`;
    }

    if (!folders || folders.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-[#71717a]">
          <div class="text-3xl mb-3">📁</div>
          <div class="text-sm font-medium text-white mb-1">Aún no hay carpetas de portafolios</div>
          <div class="text-xs">Crea portafolios en el "Creador de Portafolio" para verlos organizados aquí.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = folders.map(f => {
      const symbolsBadges = (f.symbols || []).map(s => `<span class="tn-badge text-[10px] tn-badge-white font-bold">${s}</span>`).join(' ') || '<span class="tn-badge text-[10px]">Multi-Par</span>';
      return `
        <div class="tn-card group hover:border-[#383848] transition flex flex-col justify-between">
          <div>
            <div class="flex items-start justify-between gap-2 mb-2">
              <div class="flex items-center gap-2">
                <span class="text-lg">📁</span>
                <span class="text-xs font-bold text-white tracking-wide truncate max-w-[190px]" title="${f.folder}">
                  ${f.folder}
                </span>
              </div>
              <span class="text-xs font-mono font-bold text-white px-2 py-0.5 rounded bg-[#1c1c24] border border-[#33333f] shrink-0">
                ${f.count} portafolios
              </span>
            </div>

            <div class="flex flex-wrap gap-1.5 mb-3">
              ${symbolsBadges}
            </div>

            <div class="p-2.5 rounded bg-[#09090c] border border-[#22222a] flex items-center justify-between my-2">
              <div>
                <div class="text-[10px] text-[#71717a] uppercase font-bold">Total Estrategias</div>
                <div class="text-xs font-mono font-bold text-white">${f.total_strategies || 0}</div>
              </div>
              <div class="text-right">
                <div class="text-[10px] text-white uppercase font-bold">Net Profit Comb.</div>
                <div class="text-xs font-mono font-bold text-white">+$${(f.total_profit || 0).toLocaleString()}</div>
              </div>
            </div>

            <div class="text-[10px] text-[#71717a] mt-1">
              Última actualización: <span class="text-[#a0a0ab]">${f.created_at || 'Reciente'}</span>
            </div>
          </div>

          <div class="mt-4 pt-3 flex items-center justify-between border-t border-[#1e1e24] gap-2">
            <button onclick="switchSavedPortfoliosView('all', '${f.folder}')" class="btn-secondary text-[11px] py-1 px-2.5 flex-1">
              👁 Ver Portafolios (${f.count})
            </button>
            <button onclick="deletePortfolioFolder('${f.folder}')" class="btn-danger text-[11px] py-1 px-2" title="Eliminar carpeta de portafolios">
              🗑
            </button>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    console.error('Error loading portfolio folders:', err);
    container.innerHTML = `<div class="col-span-full py-8 text-center text-red-400 text-xs">Error al cargar carpetas de portafolios.</div>`;
  }
}
window.loadPortfolioFolders = loadPortfolioFolders;

async function deletePortfolioFolder(folderName) {
  if (!confirm(`¿Estás seguro de eliminar la carpeta de portafolios "${folderName}"?`)) return;
  try {
    const res = await fetch(`/api/portfolio-folder/${encodeURIComponent(folderName)}`, { method: 'DELETE' });
    if (res.ok) {
      loadPortfolioFolders();
      refreshSidebarBadges();
    } else {
      alert('Error al eliminar la carpeta.');
    }
  } catch (err) {
    console.error('Error deleting portfolio folder:', err);
  }
}
window.deletePortfolioFolder = deletePortfolioFolder;

async function loadSavedPortfolios(folderFilter = 'ALL') {
  const container = document.getElementById('saved-portfolios-grid');
  const countBadge = document.getElementById('saved-portfolios-count');
  if (!container) return;

  container.innerHTML = `
    <div class="col-span-full py-12 text-center text-[#71717a]">
      <span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span> Cargando portafolios guardados...
    </div>
  `;

  try {
    const res = await fetch('/api/portfolios');
    let items = await res.json();
    if (!Array.isArray(items)) items = [];

    const totalCount = items.length;
    const sidebarBadge = document.getElementById('badge-sidebar-portfolios');
    if (sidebarBadge) {
      sidebarBadge.textContent = totalCount;
    }

    if (folderFilter && folderFilter !== 'ALL') {
      items = items.filter(p => (p.folder === folderFilter) || (p.batch_name === folderFilter));
    }

    if (countBadge) {
      countBadge.textContent = `${items.length} portafolios ${folderFilter !== 'ALL' ? 'en ' + folderFilter : ''}`;
    }

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-[#71717a]">
          <div class="text-3xl mb-3">📁</div>
          <div class="text-sm font-medium text-white mb-1">Sin portafolios en esta carpeta</div>
          <div class="text-xs">Usa el botón "← Volver a Carpetas" para ver otras carpetas.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(port => {
      const met = port.metrics || {};
      const subStrats = port.strategies_summary || [];
      const folderDisplay = port.folder || 'Portafolios_Principales';

      const sqCorrVal = Number(met.sq_correlation_index !== undefined ? met.sq_correlation_index : (1.0 - (met.diversification_score || 80)/100)).toFixed(2);
      const sqRatingVal = met.sq_rating || (sqCorrVal <= 0.25 ? 'Excelente' : sqCorrVal <= 0.45 ? 'Muy Buena' : 'Moderada');
      const maxDdParm = Number(met.combined_max_drawdown_pct || 0).toFixed(1);
      const retDdVal = Number(met.ret_to_dd_ratio || 0).toFixed(1);
      const ddRedVal = Number(met.dd_reduction_pct !== undefined ? met.dd_reduction_pct : (met.estimated_dd_reduction_pct || 35)).toFixed(1);

      return `
        <div class="tn-card flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-bold text-white uppercase tracking-wider">${port.name}</span>
              <span class="tn-badge tn-badge-white text-[10px]" title="Índice StrategyQuant: 0.00 (mínima correlación) a 1.00 (alta correlación)">
                SQ ${sqCorrVal} · ${sqRatingVal}
              </span>
            </div>
            <div class="text-[11px] text-[#71717a] mb-1">📁 Carpeta: <span class="font-mono text-[#a0a0ab]">${folderDisplay}</span></div>
            <div class="text-[11px] text-[#71717a] mb-3">Creado: ${port.created_at || 'Reciente'} · ID: <span class="font-mono text-[#a0a0ab]">${port.id}</span></div>

            <div class="grid grid-cols-4 gap-1.5 p-2 rounded bg-[#09090c] border border-[#22222a] text-center my-3">
              <div>
                <div class="text-[9px] text-[#71717a] uppercase font-bold">Net Profit</div>
                <div class="text-xs font-mono font-bold text-white mt-0.5">
                  +$${(met.combined_net_profit_usd || 0).toLocaleString()}
                </div>
              </div>
              <div>
                <div class="text-[9px] text-[#71717a] uppercase font-bold">Max DD</div>
                <div class="text-xs font-mono font-bold text-red-400 mt-0.5">
                  ${maxDdParm}%
                </div>
              </div>
              <div>
                <div class="text-[9px] text-[#71717a] uppercase font-bold">Ret / DD</div>
                <div class="text-xs font-mono font-bold text-emerald-400 mt-0.5">
                  ${retDdVal}x
                </div>
              </div>
              <div>
                <div class="text-[9px] text-[#71717a] uppercase font-bold">DD Red.</div>
                <div class="text-xs font-mono font-bold text-emerald-400 mt-0.5">
                  -${ddRedVal}%
                </div>
              </div>
            </div>

            <div class="mt-3">
              <div class="text-[10px] text-[#71717a] uppercase font-bold mb-1.5 flex items-center justify-between">
                <span>Estrategias (${subStrats.length})</span>
                <span>Pesos asignados</span>
              </div>
              <div class="space-y-1 max-h-32 overflow-y-auto">
                ${subStrats.map(sub => `
                  <div class="flex items-center justify-between p-1.5 rounded bg-[#131318] text-[11px]">
                    <span class="text-white font-medium truncate max-w-[170px]">${sub.symbol || ''} · ${sub.timeframe || ''} (${sub.name || sub.id})</span>
                    <span class="font-mono text-[#a0a0ab] font-bold">${Math.round((sub.weight || 0) * 100)}%</span>
                  </div>
                `).join('')}
              </div>
            </div>
          </div>

          <div class="mt-4 pt-3 border-t border-[#1e1e24] flex items-center justify-between gap-2">
            <button onclick="openPortfolioModal('${port.id}')" class="btn-primary text-[11px] py-1 px-2.5 flex-1 flex items-center justify-center gap-1.5" title="Ver análisis completo de la cartera y curva combinada">
              📊 Ver Análisis
            </button>
            <button onclick="exportPortfolioJson('${port.id}')" class="btn-secondary text-[11px] py-1 px-2" title="Descargar archivo de configuración JSON para bot">
              📥 Bot JSON
            </button>
            <button onclick="deleteSavedPortfolio('${port.id}')" class="btn-danger text-[11px] py-1 px-2" title="Eliminar portafolio">
              🗑
            </button>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    console.error('Error loading saved portfolios:', err);
    container.innerHTML = `<div class="col-span-full py-8 text-center text-red-400 text-xs">Error al cargar portafolios.</div>`;
  }
}
window.loadSavedPortfolios = loadSavedPortfolios;

async function deleteSavedPortfolio(portfolioId) {
  if (!confirm('¿Estás seguro de eliminar este portafolio?')) return;
  try {
    const res = await fetch(`/api/portfolio/${portfolioId}`, { method: 'DELETE' });
    if (res.ok) {
      loadSavedPortfolios();
    } else {
      alert('Error al eliminar portafolio.');
    }
  } catch (err) {
    console.error('Error deleting portfolio:', err);
  }
}
window.deleteSavedPortfolio = deleteSavedPortfolio;

async function exportPortfolioJson(portfolioId) {
  try {
    const res = await fetch(`/api/portfolio/${portfolioId}`);
    if (!res.ok) {
      alert('Error al descargar portafolio.');
      return;
    }
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${portfolioId}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error('Error exporting portfolio JSON:', err);
  }
}
async function refreshSidebarBadges() {
  try {
    const [resStrat, resPort, resRetest] = await Promise.all([
      fetch('/api/strategies/saved'),
      fetch('/api/portfolios'),
      fetch('/api/retest/results')
    ]);
    if (resStrat.ok) {
      const strats = await resStrat.json();
      const b1 = document.getElementById('badge-sidebar-strategies');
      if (b1) b1.textContent = strats.length;
    }
    if (resPort.ok) {
      const ports = await resPort.json();
      const b2 = document.getElementById('badge-sidebar-portfolios');
      if (b2) b2.textContent = ports.length;
    }
    if (resRetest.ok) {
      const retests = await resRetest.json();
      const appCount = (retests || []).filter(r => r.approved_for_portfolio).length;
      const b3 = document.getElementById('badge-sidebar-retest');
      if (b3) b3.textContent = appCount;
    }
  } catch (e) {
    // Silent badge update failure
  }
}
window.refreshSidebarBadges = refreshSidebarBadges;

// ============================================================================
// PORTFOLIO DETAIL MODAL & COMBINED EQUITY CURVE
// ============================================================================

let portfolioEquityChartInstance = null;

const INDIVIDUAL_PALETTE = [
  '#38bdf8', // Cyan
  '#a3e635', // Lima
  '#fb923c', // Naranja
  '#c084fc', // Púrpura
  '#facc15', // Amarillo
  '#f472b6', // Rosa
  '#2dd4bf', // Teal
  '#f87171', // Rojo suave
  '#818cf8', // Indigo
  '#e879f9'  // Fucsia
];

async function openPortfolioModal(portfolioId) {
  try {
    const res = await fetch(`/api/portfolio/${portfolioId}`);
    if (!res.ok) {
      alert('No se pudo cargar el análisis del portafolio.');
      return;
    }
    const port = await res.json();
    const modal = document.getElementById('portfolio-detail-modal');
    if (!modal) return;
    modal.classList.remove('hidden');

    // Títulos y metadatos
    document.getElementById('port-modal-title').textContent = port.name || 'Portafolio Multi-Estrategia';
    const folderDisplay = port.folder || 'Portafolios_Principales';
    document.getElementById('port-modal-subtitle').textContent = `📁 ${folderDisplay} · ID: ${port.id} · Creado: ${port.created_at || 'Reciente'}`;

    // Métricas clave
    const met = port.metrics || {};
    const netProfitVal = met.combined_net_profit_usd || 0;
    document.getElementById('port-modal-pnl').textContent = `${netProfitVal >= 0 ? '+' : ''}$${netProfitVal.toLocaleString(undefined, {minimumFractionDigits: 2})}`;

    // StrategyQuant KPIs: Max DD, Ret/DD, Real DD Reduction, SQ Correlation (0.0 to 1.0)
    const maxDdEl = document.getElementById('port-modal-max-dd');
    const avgIndDdEl = document.getElementById('port-modal-avg-ind-dd');
    const retDdEl = document.getElementById('port-modal-ret-dd');
    const ddRedEl = document.getElementById('port-modal-dd-red');
    const sqCorrEl = document.getElementById('port-modal-sq-corr');
    const wrEl = document.getElementById('port-modal-wr');

    if (maxDdEl) maxDdEl.textContent = `${Number(met.combined_max_drawdown_pct || 0).toFixed(2)}% ($${Number(met.combined_max_drawdown_usd || 0).toLocaleString()})`;
    if (avgIndDdEl) avgIndDdEl.textContent = `vs ${Number(met.avg_individual_dd_pct || 0).toFixed(2)}% individual prom.`;
    if (retDdEl) retDdEl.textContent = `${Number(met.ret_to_dd_ratio || 0).toFixed(1)}x`;
    const ddRedVal = met.dd_reduction_pct !== undefined ? met.dd_reduction_pct : (met.estimated_dd_reduction_pct || 0);
    if (ddRedEl) ddRedEl.textContent = `-${Number(ddRedVal).toFixed(1)}%`;
    const sqIndex = met.sq_correlation_index !== undefined ? met.sq_correlation_index : (1.0 - (met.diversification_score || 80)/100);
    if (sqCorrEl) sqCorrEl.textContent = `${Number(sqIndex).toFixed(2)} · ${met.sq_rating || 'Excelente'}`;
    if (wrEl) wrEl.textContent = `Win Rate: ${Number(met.weighted_win_rate_pct || 0).toFixed(1)}%`;

    // Botón de exportación
    const exportBtn = document.getElementById('btn-port-modal-export');
    if (exportBtn) {
      exportBtn.onclick = () => exportPortfolioJson(port.id);
      exportBtn.textContent = '📥 Descargar Bot JSON';
    }

    // Tabla de estrategias componentes
    const tbody = document.getElementById('port-modal-strategies-body');
    const strats = port.strategies || [];
    if (tbody) {
      tbody.innerHTML = strats.map(st => {
        const s = st.strategy || st;
        const m = st.metrics || {};
        const pnl = m.total_return_usd || 0;
        return `
          <tr class="border-b border-[#1c1c24] hover:bg-[#14141a]">
            <td class="py-2.5 px-3 font-semibold text-white">${s.name || s.id}</td>
            <td class="py-2.5 px-3"><span class="tn-badge tn-badge-white text-[10px]">${s.symbol || '-'}</span></td>
            <td class="py-2.5 px-3 font-mono">${s.timeframe || '1h'}</td>
            <td class="py-2.5 px-3 font-mono font-bold text-white">${Math.round((st.weight || 0) * 100)}%</td>
            <td class="py-2.5 px-3 font-mono text-[#a0a0ab]">${(m.win_rate_pct || 0).toFixed(1)}%</td>
            <td class="py-2.5 px-3 font-mono text-white font-semibold">${pnl >= 0 ? '+' : ''}$${pnl.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
            <td class="py-2.5 px-3 text-right">
              <button onclick="closePortfolioModal(); openCandidateModal('${s.id}')" class="btn-secondary text-[10px] py-0.5 px-2.5" title="Ver análisis y backtest individual">
                Ver Estrategia
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    // Graficar Curva Combinada + Curvas Individuales superpuestas
    renderPortfolioEquityChart(port.combined_equity_curve || [], port.individual_curves || []);
  } catch (err) {
    console.error('Error opening portfolio modal:', err);
    alert('Error al abrir el modal de portafolio.');
  }
}
window.openPortfolioModal = openPortfolioModal;

function closePortfolioModal() {
  const modal = document.getElementById('portfolio-detail-modal');
  if (modal) modal.classList.add('hidden');
}
window.closePortfolioModal = closePortfolioModal;

function renderPortfolioEquityChart(curve, individualCurves = []) {
  const canvas = document.getElementById('portfolio-equity-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (portfolioEquityChartInstance) {
    portfolioEquityChartInstance.destroy();
  }

  if (!curve || curve.length === 0) {
    curve = [{ equity: 10000, trade: 0 }];
  }

  const numPoints = curve.length;
  const labels = curve.map((_, i) => i === 0 ? 'Inicio' : `#${i}`);
  const combinedData = curve.map(pt => (typeof pt === 'number' ? pt : (pt.equity !== undefined ? pt.equity : pt.balance)));

  const datasets = [
    {
      label: '★ Cartera Combinada (Balance $)',
      data: combinedData,
      borderColor: '#ffffff',
      borderWidth: 2.8,
      backgroundColor: 'rgba(255, 255, 255, 0.06)',
      fill: true,
      pointRadius: numPoints > 60 ? 0 : 2,
      tension: 0.15,
      order: 0
    }
  ];

  if (Array.isArray(individualCurves) && individualCurves.length > 0) {
    individualCurves.forEach((ind, idx) => {
      const color = INDIVIDUAL_PALETTE[idx % INDIVIDUAL_PALETTE.length];
      const rawData = ind.data || [];
      let alignedData = rawData;
      if (rawData.length !== numPoints && rawData.length > 0) {
        alignedData = [];
        for (let i = 0; i < numPoints; i++) {
          const ratio = (numPoints <= 1) ? 0 : (i / (numPoints - 1));
          const srcIdx = Math.min(Math.floor(ratio * (rawData.length - 1)), rawData.length - 1);
          alignedData.push(rawData[srcIdx]);
        }
      }
      const weightPct = Math.round((ind.weight || (1 / individualCurves.length)) * 100);
      datasets.push({
        label: `${ind.symbol || 'ACTIVO'} · ${ind.name || 'Algo'} (${weightPct}%)`,
        data: alignedData,
        borderColor: color,
        borderWidth: 1.5,
        borderDash: [4, 3],
        backgroundColor: 'transparent',
        fill: false,
        pointRadius: 0,
        tension: 0.1,
        order: idx + 1
      });
    });
  }

  portfolioEquityChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            boxWidth: 12,
            boxHeight: 12,
            color: '#a0a0ab',
            font: { size: 10, family: 'monospace' },
            padding: 10
          }
        },
        tooltip: {
          backgroundColor: '#16161e',
          borderColor: '#2a2a38',
          borderWidth: 1,
          titleColor: '#fff',
          bodyColor: '#e0e0e0',
          padding: 8,
          callbacks: {
            label: (context) => ` ${context.dataset.label}: $${Number(context.parsed.y).toLocaleString(undefined, {minimumFractionDigits: 2})}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.03)' },
          ticks: { color: '#71717a', font: { size: 10 }, maxTicksLimit: 12 }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: {
            color: '#a0a0ab',
            font: { size: 10 },
            callback: (val) => '$' + Number(val).toLocaleString()
          }
        }
      }
    }
  });
}
window.renderPortfolioEquityChart = renderPortfolioEquityChart;

// ============================================================================
// RETEST & ROBUSTNESS ENGINE (RUTA TRADINGNOTE)
// ============================================================================

state.retestResults = [];
state.retestFilter = 'ALL';
state.retestRunning = false;

async function loadRetestView() {
  await loadRetestFolderOptions();
  await refreshRetestResults();
}
window.loadRetestView = loadRetestView;

async function loadRetestFolderOptions() {
  const sel = document.getElementById('select-retest-folder');
  if (!sel) return;
  try {
    const res = await fetch('/api/strategy-folders');
    if (res.ok) {
      const folders = await res.json();
      sel.innerHTML = `<option value="ALL">Todas las Estrategias Guardadas</option>` +
        folders.map(f => `<option value="${f.name}">${f.name} (${f.count} estrategias)</option>`).join('');
    }
  } catch (e) {
    console.error('Error loading retest folder options:', e);
  }
}

async function refreshRetestResults() {
  try {
    const res = await fetch('/api/retest/results');
    if (res.ok) {
      const data = await res.json();
      state.retestResults = data || [];
      updateRetestKpis();
      renderRetestCards();
      refreshSidebarBadges();
    }
  } catch (e) {
    console.error('Error fetching retest results:', e);
  }
}
window.refreshRetestView = refreshRetestResults;

function updateRetestKpis() {
  const list = state.retestResults || [];
  const total = list.length;
  const approved = list.filter(r => r.approved_for_portfolio).length;
  const discarded = total - approved;
  const avgScore = total > 0 ? (list.reduce((acc, r) => acc + (r.robustness_score || 0), 0) / total).toFixed(1) : '0.0';

  const elTot = document.getElementById('kpi-retest-total');
  const elApp = document.getElementById('kpi-retest-approved');
  const elDisc = document.getElementById('kpi-retest-discarded');
  const elAvg = document.getElementById('kpi-retest-avg-score');
  const elBadge = document.getElementById('retest-results-badge');

  if (elTot) elTot.textContent = total;
  if (elApp) elApp.textContent = approved;
  if (elDisc) elDisc.textContent = discarded;
  if (elAvg) elAvg.textContent = `${avgScore} pts`;
  if (elBadge) elBadge.textContent = `${total} EVALUADAS (${approved} APROBADAS)`;
}

async function runBatchRetest() {
  if (state.retestRunning) return;
  const folder = document.getElementById('select-retest-folder')?.value || 'ALL';

  const btn = document.getElementById('btn-run-batch-retest');
  const progressBox = document.getElementById('retest-progress-box');
  const progressBar = document.getElementById('retest-progress-bar');
  const progressText = document.getElementById('retest-progress-text');
  const progressCounter = document.getElementById('retest-progress-counter');

  state.retestRunning = true;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span> Retesteando...`;
  }
  if (progressBox) progressBox.classList.remove('hidden');
  if (progressBar) progressBar.style.width = '20%';
  if (progressText) progressText.textContent = `Analizando estrategias del lote "${folder}" con Walk-Forward y Monte Carlo...`;
  if (progressCounter) progressCounter.textContent = '20%';

  try {
    const res = await fetch('/api/retest/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: folder })
    });

    if (progressBar) progressBar.style.width = '85%';
    if (progressCounter) progressCounter.textContent = '85%';

    if (res.ok) {
      const data = await res.json();
      state.retestResults = data.results || [];
      if (progressBar) progressBar.style.width = '100%';
      if (progressCounter) progressCounter.textContent = '100%';
      if (progressText) progressText.textContent = `✓ Retest completado: ${data.approved_count} de ${data.tested_count} estrategias aprobadas para portafolio.`;
      updateRetestKpis();
      renderRetestCards();
      refreshSidebarBadges();
      setTimeout(() => {
        if (progressBox) progressBox.classList.add('hidden');
      }, 3500);
    } else {
      alert('Error al ejecutar el retest.');
      if (progressBox) progressBox.classList.add('hidden');
    }
  } catch (err) {
    console.error('Error running batch retest:', err);
    alert('Ocurrió un error al ejecutar el retest.');
    if (progressBox) progressBox.classList.add('hidden');
  } finally {
    state.retestRunning = false;
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<span>⚡</span> Iniciar Retest de Robustez`;
    }
  }
}
window.runBatchRetest = runBatchRetest;

function filterRetestCards(filterVal) {
  state.retestFilter = filterVal;
  renderRetestCards();
}
window.filterRetestCards = filterRetestCards;

function renderRetestCards() {
  const container = document.getElementById('retest-cards-grid');
  if (!container) return;

  let list = state.retestResults || [];
  if (state.retestFilter === 'APPROVED') {
    list = list.filter(r => r.approved_for_portfolio);
  } else if (state.retestFilter === 'MODERATE') {
    list = list.filter(r => r.verdict === 'MODERADO');
  } else if (state.retestFilter === 'DISCARDED') {
    list = list.filter(r => r.verdict === 'FRAGIL');
  }

  if (list.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-16 text-center text-[#71717a]">
        <div class="text-3xl mb-3">🛡️</div>
        <div class="text-sm font-medium text-white mb-1">No hay resultados para este filtro</div>
        <div class="text-xs">Ejecuta el retest o cambia el filtro superior para ver las estrategias analizadas.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = list.map(r => {
    const isApp = r.approved_for_portfolio;
    const badgeCls = isApp 
      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' 
      : r.verdict === 'MODERADO' 
        ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30' 
        : 'bg-red-500/10 text-red-400 border-red-500/30';

    const wf = r.walk_forward || {};
    const mc = r.monte_carlo || {};
    const mv = r.multiverse || {};

    const wfeVal = Number(wf.overall_wfe || 0).toFixed(2);
    const mcP95Dd = Number(mc.drawdown_p95_pct || 0).toFixed(1);
    const mcProfPct = Number(mc.profitable_pct || 0).toFixed(1);
    const mvProfPct = Number(mv.profitable_pct || 0).toFixed(1);

    return `
      <div class="candidate-card group flex flex-col justify-between p-4 ${isApp ? 'border-emerald-500/30 hover:border-emerald-400' : ''}">
        <div>
          <!-- Header -->
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-bold text-white tracking-wide truncate max-w-[170px]" title="${r.strategy_name || r.strategy_id}">
              ${r.strategy_name || r.strategy_id}
            </span>
            <span class="text-[11px] font-mono font-bold px-2 py-0.5 rounded border ${badgeCls}">
              ${r.verdict_badge || r.verdict}
            </span>
          </div>

          <div class="flex items-center gap-2 mb-3">
            <span class="tn-badge tn-badge-white text-[10px]">${r.symbol || 'N/A'}</span>
            <span class="text-[10px] font-mono text-[#a0a0ab]">${r.timeframe || '1h'}</span>
            <span class="text-[10px] text-[#71717a]">Probado: ${r.tested_at || 'Reciente'}</span>
          </div>

          <!-- Robustness Score Bar -->
          <div class="p-2.5 rounded bg-[#08080c] border border-[#202028] mb-3">
            <div class="flex items-center justify-between text-xs mb-1">
              <span class="text-[10px] text-[#71717a] uppercase font-bold">TradingNote Robustness Score</span>
              <span class="font-mono font-bold ${isApp ? 'text-emerald-400' : 'text-white'}">${r.robustness_score || 0} / 100</span>
            </div>
            <div class="w-full bg-[#1c1c24] h-1.5 rounded-full overflow-hidden">
              <div class="h-full ${isApp ? 'bg-emerald-400' : r.verdict === 'MODERADO' ? 'bg-yellow-400' : 'bg-red-400'}" style="width: ${r.robustness_score || 0}%"></div>
            </div>
          </div>

          <!-- 4 Layers Metrics Grid -->
          <div class="grid grid-cols-2 gap-2 text-center text-xs">
            <div class="p-2 rounded bg-[#09090c] border border-[#1e1e26]">
              <div class="text-[9px] text-[#71717a] uppercase font-bold">Walk-Forward WFE</div>
              <div class="text-xs font-mono font-bold text-white mt-0.5">${wfeVal}</div>
              <div class="text-[9px] text-[#a0a0ab]">${wfeVal >= 0.5 ? '✓ Robustez Temporal' : '⚠ Sobreajuste'}</div>
            </div>
            <div class="p-2 rounded bg-[#09090c] border border-[#1e1e26]">
              <div class="text-[9px] text-[#71717a] uppercase font-bold">Monte Carlo P95 DD</div>
              <div class="text-xs font-mono font-bold text-red-400 mt-0.5">${mcP95Dd}%</div>
              <div class="text-[9px] text-[#a0a0ab]">Peor caso 95% conf.</div>
            </div>
            <div class="p-2 rounded bg-[#09090c] border border-[#1e1e26]">
              <div class="text-[9px] text-[#71717a] uppercase font-bold">MC Rentable (1000 iter)</div>
              <div class="text-xs font-mono font-bold text-emerald-400 mt-0.5">${mcProfPct}%</div>
              <div class="text-[9px] text-[#a0a0ab]">Escenarios en verde</div>
            </div>
            <div class="p-2 rounded bg-[#09090c] border border-[#1e1e26]">
              <div class="text-[9px] text-[#71717a] uppercase font-bold">Multiverso Profitable</div>
              <div class="text-xs font-mono font-bold text-white mt-0.5">${mvProfPct}%</div>
              <div class="text-[9px] text-[#a0a0ab]">Mercados sintéticos</div>
            </div>
          </div>
        </div>

        <!-- Action Footer -->
        <div class="mt-3.5 pt-2.5 flex items-center justify-between border-t border-[#1e1e24] gap-2">
          ${isApp ? `
            <button onclick="sendSingleRetestToPortfolio('${r.strategy_id}')" class="btn-primary text-[11px] py-1.5 px-3 flex-1 flex items-center justify-center gap-1.5 font-bold" title="Enviar directamente a la Ruta de Portafolios Multi-Par">
              <span>🧬</span> Enviar a Portafolio
            </button>
          ` : `
            <span class="text-[10px] text-[#71717a] italic flex-1 text-center py-1">No apta para portafolio</span>
          `}
          <button onclick="openCandidateModal('${r.strategy_id}')" class="btn-secondary text-[11px] py-1.5 px-3 flex items-center justify-center gap-1" title="Ver análisis y backtest completo">
            📊 Detalles
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function sendSingleRetestToPortfolio(stratId) {
  state.portfolioSelectedIds.add(stratId);
  showSection('portfolio-builder');
  alert(`✓ Estrategia ${stratId} añadida a la selección del Creador de Portafolios.`);
}
window.sendSingleRetestToPortfolio = sendSingleRetestToPortfolio;

function sendAllApprovedRetestToPortfolio() {
  const approved = (state.retestResults || []).filter(r => r.approved_for_portfolio);
  if (approved.length === 0) {
    alert('No hay estrategias aprobadas en el retest todavía.');
    return;
  }
  approved.forEach(r => state.portfolioSelectedIds.add(r.strategy_id));
  showSection('portfolio-builder');
  alert(`✓ ¡${approved.length} estrategias aprobadas transferidas con éxito a la Ruta de Portafolios!`);
}
window.sendAllApprovedRetestToPortfolio = sendAllApprovedRetestToPortfolio;

// ============================================================================
// LIMPIEZA / CLEAR DE RESULTADOS POR FASE
// ============================================================================

async function clearEngineCandidates() {
  if (!confirm('¿Eliminar todos los algoritmos aprobados del motor genético actual?')) return;
  try {
    const res = await fetch('/api/engine/clear-results', { method: 'POST' });
    if (res.ok) {
      await fetchCandidates();
      renderCounters({ tested_count: 0, discarded_count: 0, accepted_count: 0, candidates_count: 0, best_sharpe: 0, avg_win_rate: 0, current_generation: 0, log_messages: [] });
      refreshSidebarBadges();
      alert('✓ Resultados del motor genético limpiados.');
    } else {
      alert('Error al limpiar resultados del motor.');
    }
  } catch (e) {
    console.error('Error clearing engine candidates:', e);
    alert('Error de conexión al limpiar resultados del motor.');
  }
}
window.clearEngineCandidates = clearEngineCandidates;

async function clearRetestResults() {
  if (!confirm('¿Eliminar todos los resultados de retest (Walk-Forward, Monte Carlo, Multiverso)?')) return;
  try {
    const res = await fetch('/api/retest/clear', { method: 'POST' });
    if (res.ok) {
      state.retestResults = [];
      updateRetestKpis();
      renderRetestCards();
      refreshSidebarBadges();
      alert('✓ Resultados de retest limpiados.');
    } else {
      alert('Error al limpiar resultados de retest.');
    }
  } catch (e) {
    console.error('Error clearing retest results:', e);
    alert('Error de conexión al limpiar resultados de retest.');
  }
}
window.clearRetestResults = clearRetestResults;

async function clearPortfolioEngineResults() {
  if (!confirm('¿Eliminar todos los portafolios del ranking TOP del motor de portafolios?')) return;
  try {
    const res = await fetch('/api/portfolio-engine/clear', { method: 'POST' });
    if (res.ok) {
      await pollPortfolioEngine();
      renderPortfolioEngineCards([]);
      refreshSidebarBadges();
      alert('✓ Ranking de portafolios limpiado.');
    } else {
      alert('Error al limpiar ranking de portafolios.');
    }
  } catch (e) {
    console.error('Error clearing portfolio engine:', e);
    alert('Error de conexión al limpiar portafolios.');
  }
}
window.clearPortfolioEngineResults = clearPortfolioEngineResults;

async function clearSavedStrategiesAction() {
  if (!confirm('¿Eliminar TODAS las estrategias guardadas y carpetas?')) return;
  try {
    const res = await fetch('/api/strategies/clear-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: 'ALL' })
    });
    if (res.ok) {
      loadSavedStrategies();
      loadStrategyFolders();
      refreshSidebarBadges();
      alert('✓ Estrategias guardadas eliminadas.');
    } else {
      alert('Error al eliminar estrategias guardadas.');
    }
  } catch (e) {
    console.error('Error clearing saved strategies:', e);
    alert('Error de conexión al eliminar estrategias.');
  }
}
window.clearSavedStrategiesAction = clearSavedStrategiesAction;

async function clearSavedPortfoliosAction() {
  if (!confirm('¿Eliminar TODOS los portafolios guardados y carpetas?')) return;
  try {
    const res = await fetch('/api/portfolios/clear-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: 'ALL' })
    });
    if (res.ok) {
      loadSavedPortfolios();
      loadPortfolioFolders();
      refreshSidebarBadges();
      alert('✓ Portafolios guardados eliminados.');
    } else {
      alert('Error al eliminar portafolios.');
    }
  } catch (e) {
    console.error('Error clearing saved portfolios:', e);
    alert('Error de conexión al eliminar portafolios.');
  }
}
window.clearSavedPortfoliosAction = clearSavedPortfoliosAction;

async function clearAllPhases() {
  if (!confirm('¿Eliminar TODOS los resultados y carpetas de todas las fases (motor, retest, portafolios)?')) return;
  try {
    const res = await fetch('/api/clear-all-phases', { method: 'POST' });
    if (res.ok) {
      await fetchCandidates();
      state.retestResults = [];
      updateRetestKpis();
      renderRetestCards();
      renderPortfolioEngineCards([]);
      loadSavedStrategies();
      loadStrategyFolders();
      loadSavedPortfolios();
      loadPortfolioFolders();
      refreshSidebarBadges();
      alert('✓ Se limpiaron todos los resultados de todas las fases.');
    } else {
      alert('Error al limpiar todos los resultados.');
    }
  } catch (e) {
    console.error('Error clearing all phases:', e);
    alert('Error de conexión al limpiar todas las fases.');
  }
}
window.clearAllPhases = clearAllPhases;

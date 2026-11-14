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
  AROON: { name: 'Aroon Oscillator (Up - Down)', family: 'Ciclo & Estructura', from: 10, step: 4, to: 25, unit: 'período' }
};

// Global State
const state = {
  activeTab: 'config',
  symbolsMeta: [],
  selectedSymbol: 'EURUSD',
  selectedTimeframe: '1h',
  searchMode: 'genetic',
  initialDeposit: 10000,
  
  // Enabled indicators map: { EMA: true, SMA: true, ... }
  enabledIndicators: {},

  // Engine state
  isRunning: false,
  pollTimer: null,
  status: null,
  candidates: [],
  selectedCandidate: null,
  filterWfOnly: false,
  filterMultiverseOnly: false,

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

document.addEventListener('DOMContentLoaded', async () => {
  initTabs();
  render28IndicatorsGrid();
  await loadSymbols();
  await loadConfigDefaults();
  updateCombinationsCounter();
  initNeuralExplorer();
  
  // Check engine status
  await pollStatus();

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
  document.getElementById('filter-wf').addEventListener('change', (e) => {
    state.filterWfOnly = e.target.checked;
    renderCandidates();
  });
  document.getElementById('filter-mv').addEventListener('change', (e) => {
    state.filterMultiverseOnly = e.target.checked;
    renderCandidates();
  });
});

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
        <span class="text-[10px] text-[#71717a]">Parámetros genéricos preconfigurados</span>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
    `;

    items.forEach(item => {
      const isChecked = state.enabledIndicators[item.key] !== false;
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
          
          <div class="mt-2.5 pt-2 border-t border-[#1a1a22] flex items-center justify-between text-[10px] font-mono text-[#71717a]">
            <span>[${item.from} → ${item.step} → ${item.to}]</span>
            <span class="text-[#a0a0ab]">${item.unit}</span>
          </div>
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
}

function selectRandomIndicators() {
  const keys = Object.keys(ALL_28_INDICATORS_CONFIG);
  // Pick between 4 and 8 random indicators
  const count = Math.floor(Math.random() * 5) + 4;
  const shuffled = [...keys].sort(() => 0.5 - Math.random());
  const selected = new Set(shuffled.slice(0, count));

  keys.forEach(k => {
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
  const exits = ['exit-atr', 'exit-trailing', 'exit-breakeven', 'exit-swing', 'exit-time', 'exit-partial'];
  exits.forEach(id => {
    const cb = document.getElementById(id);
    if (cb) cb.checked = Math.random() > 0.4;
  });
  if (!exits.some(id => document.getElementById(id).checked)) {
    document.getElementById('exit-atr').checked = true;
  }
}

function updateCombinationsCounter() {
  let totalCombos = 1;
  let activeCount = 0;

  Object.entries(ALL_28_INDICATORS_CONFIG).forEach(([key, conf]) => {
    if (state.enabledIndicators[key]) {
      activeCount++;
      const steps = Math.max(1, Math.floor((conf.to - conf.from) / conf.step) + 1);
      totalCombos *= Math.min(steps, 6); // cap representation per indicator
    }
  });

  const fullSpace = totalCombos * 3 * 6; // x3 entry types x6 exits

  const countEl = document.getElementById('combinations-counter');
  if (countEl) {
    countEl.textContent = activeCount > 0 ? (fullSpace > 1e12 ? '∞ Millones' : fullSpace.toLocaleString()) : '0';
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

function renderSymbolPills() {
  const container = document.getElementById('symbol-pills-container');
  if (!container) return;
  container.innerHTML = '';

  state.symbolsMeta.forEach(sym => {
    const isSelected = sym.symbol === state.selectedSymbol;
    const btn = document.createElement('button');
    btn.className = `px-3 py-1.5 rounded text-xs font-semibold uppercase tracking-wider transition-all border ${
      isSelected 
        ? 'bg-white text-black border-white shadow-md' 
        : 'bg-[#141418] text-[#a0a0ab] border-[#27272f] hover:border-[#444450] hover:text-white'
    }`;
    btn.textContent = sym.symbol;
    btn.addEventListener('click', () => {
      state.selectedSymbol = sym.symbol;
      renderSymbolPills();
      updateDataSummaryInfo();
    });
    container.appendChild(btn);
  });
}

function updateDataSummaryInfo() {
  const infoEl = document.getElementById('symbol-data-info');
  if (!infoEl) return;
  const sym = state.symbolsMeta.find(s => s.symbol === state.selectedSymbol);
  if (!sym) return;

  const tfInfo = sym.timeframes[state.selectedTimeframe] || {};
  infoEl.innerHTML = `
    <div class="flex items-center gap-4 text-xs text-[#a0a0ab]">
      <div><span class="text-white font-medium">Activo:</span> ${sym.name} (${sym.category})</div>
      <div><span class="text-white font-medium">Velas descargadas:</span> ${tfInfo.bars ? tfInfo.bars.toLocaleString() : 'Listo'}</div>
      <div><span class="text-white font-medium">Rango:</span> ${tfInfo.start ? tfInfo.start.split(' ')[0] : '2024'} al presente</div>
      <div><span class="text-white font-medium">Fuente:</span> Interbank Feeds & Futures continuos (Caché Parquet Local)</div>
    </div>
  `;
}

// ============================================================================
// EXPLORATION CONTROLS (INFINITE GENERATION & CLASSIFICATION)
// ============================================================================

async function startExploration() {
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
  if (document.getElementById('exit-trailing')?.checked) enabledExits.push('TRAILING_ATR');
  if (document.getElementById('exit-breakeven')?.checked) enabledExits.push('BREAKEVEN');
  if (document.getElementById('exit-swing')?.checked) enabledExits.push('STRUCTURE_SWING');
  if (document.getElementById('exit-time')?.checked) enabledExits.push('TIME_EXIT');
  if (document.getElementById('exit-partial')?.checked) enabledExits.push('PARTIAL_TP');
  if (enabledExits.length === 0) enabledExits.push('ATR_CLASSIC');

  const config = {
    symbol: state.selectedSymbol,
    timeframe: document.getElementById('select-timeframe').value,
    search_mode: document.getElementById('select-search-mode').value,
    initial_deposit: parseFloat(document.getElementById('input-deposit').value) || 10000,
    objective: document.getElementById('opt-objective').value,
    infinite_mode: document.getElementById('check-infinite-mode').checked,
    generations: 0,
    population_size: parseInt(document.getElementById('input-pop-size').value) || 30,
    enabled_indicators: enabledInds,
    enabled_entry_types: enabledEntries,
    enabled_exit_modes: enabledExits,
    
    // Classification criteria
    min_win_rate: parseFloat(document.getElementById('input-min-wr').value) || 35.0,
    min_trades: parseInt(document.getElementById('input-min-trades').value) || 8,
    max_drawdown: parseFloat(document.getElementById('input-max-dd').value) || 20.0,
    min_net_profit_usd: parseFloat(document.getElementById('input-min-profit').value) || 0.0,
    min_sharpe: parseFloat(document.getElementById('input-min-sharpe').value) || 0.8,
    min_profit_factor: parseFloat(document.getElementById('input-min-pf').value) || 1.1,
    min_dsr: parseFloat(document.getElementById('input-min-dsr').value) || 0.20
  };

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

function renderCandidates() {
  const container = document.getElementById('candidates-grid');
  if (!container) return;

  let list = state.candidates;

  if (state.filterWfOnly) {
    list = list.filter(c => c.validation?.walk_forward?.passed);
  }
  if (state.filterMultiverseOnly) {
    list = list.filter(c => c.validation?.multiverse?.passed);
  }

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
            <span class="text-xs font-semibold text-white tracking-wide">${s.name}</span>
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
    document.getElementById('modal-subtitle').textContent = `${cand.strategy.symbol} · ${cand.strategy.timeframe} · Orden ${cand.strategy.entry_order_type || 'MARKET'} · Modo ${cand.strategy.exit_mode} · TN Score ${cand.metrics.tn_score}`;

    // Populate Key Figures
    const m = cand.metrics;
    document.getElementById('modal-metric-initial').textContent = `$${(m.initial_capital || 10000).toLocaleString()}`;
    document.getElementById('modal-metric-return').textContent = `${m.total_return_usd >= 0 ? '+' : ''}$${m.total_return_usd.toLocaleString(undefined, {minimumFractionDigits: 2})} (${m.total_return_pct}%)`;
    document.getElementById('modal-metric-sharpe').textContent = m.sharpe_ratio.toFixed(2);
    document.getElementById('modal-metric-drawdown').textContent = `${m.max_drawdown_pct.toFixed(1)}% ($${m.max_drawdown_usd.toLocaleString()})`;
    document.getElementById('modal-metric-winrate').textContent = `${m.win_rate_pct.toFixed(1)}% (${m.total_trades} trades)`;
    document.getElementById('modal-metric-pf').textContent = m.profit_factor.toFixed(2);

    // Populate Rules
    const rulesDesc = cand.rules_desc;
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
    const res = await fetch(`/api/candidate/${candidateId}/validate`, { method: 'POST' });
    const val = await res.json();

    const container = document.getElementById('validation-results-container');
    container.classList.remove('hidden');

    const wf = val.walk_forward;
    document.getElementById('val-wf-status').innerHTML = `
      <div class="flex items-center justify-between p-3 rounded bg-[#16161c] border border-[#2a2a34]">
        <div>
          <div class="text-xs font-semibold text-white">Walk-Forward Temporal (WFE: ${wf.overall_wfe})</div>
          <div class="text-[11px] text-[#a0a0ab]">Ventanas evaluadas: ${wf.windows.length} tramos fuera de muestra</div>
        </div>
        <span class="tn-badge ${wf.passed ? 'tn-badge-white' : ''}">${wf.passed ? 'SUPERADO (ROBUSTO)' : 'SOBREAJUSTADO'}</span>
      </div>
    `;

    const mv = val.multiverse;
    document.getElementById('val-mv-status').innerHTML = `
      <div class="flex items-center justify-between p-3 rounded bg-[#16161c] border border-[#2a2a34]">
        <div>
          <div class="text-xs font-semibold text-white">Multiverso Sintético (${mv.profitable_pct}% rentables)</div>
          <div class="text-[11px] text-[#a0a0ab]">${mv.total_universes} universos sintéticos simulados · Sharpe mediano: ${mv.median_sharpe}</div>
        </div>
        <span class="tn-badge ${mv.passed ? 'tn-badge-white' : ''}">${mv.passed ? 'SUPERADO (ALTA VENTAJA)' : 'FRÁGIL'}</span>
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
    loadSavedStrategies();
  } else if (sectionId === 'portfolio-builder') {
    renderPortfolioStrategyChecklist();
  } else if (sectionId === 'saved-portfolios') {
    loadSavedPortfolios();
  } else if (sectionId === 'engine') {
    if (state.activeTab === 'results') {
      renderCandidates();
    }
  }
}
window.showSection = showSection;

// ============================================================================
// STRATEGY PERSISTENCE (INDIVIDUAL & BATCH)
// ============================================================================

async function saveSingleStrategy(strategyId) {
  try {
    const res = await fetch('/api/strategy/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy_id: strategyId })
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`Error al guardar: ${err.detail || 'No se pudo guardar la estrategia.'}`);
      return;
    }
    alert(`✓ Estrategia guardada exitosamente en Mis Algoritmos.`);
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
  try {
    const res = await fetch('/api/strategy/batch-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ save_all_candidates: true })
    });
    const data = await res.json();
    alert(`✓ Se guardaron ${data.count} estrategias aprobadas en Mis Algoritmos.`);
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

  // 2. Batch-save current candidates so they persist for the portfolio
  try {
    await fetch('/api/strategy/batch-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ save_all_candidates: true })
    });
  } catch (e) {
    console.warn('Batch save during portfolio transfer:', e);
  }

  // 3. Switch to portfolio builder section
  showSection('portfolio-builder');
}
window.sendBatchToPortfolio = sendBatchToPortfolio;

// ============================================================================
// LOAD SAVED STRATEGIES VIEW
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
    const items = await res.json();
    
    if (countBadge) {
      countBadge.textContent = `${items.length} estrategias`;
    }

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-[#71717a]">
          <div class="text-3xl mb-3">💾</div>
          <div class="text-sm font-medium text-white mb-1">Aún no hay estrategias guardadas</div>
          <div class="text-xs">Genera estrategias en el Motor Genético y guárdalas individualmente o en lote desde los Resultados.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map((cand, idx) => {
      const s = cand.strategy || cand;
      const m = cand.metrics || {};
      const netProfitFormatted = m.total_return_usd !== undefined
        ? `${m.total_return_usd >= 0 ? '+' : ''}$${m.total_return_usd.toLocaleString(undefined, {minimumFractionDigits: 2})}`
        : 'N/A';
      const initialDepositFormatted = `$${(m.initial_capital || 10000).toLocaleString()}`;

      return `
        <div class="candidate-card group">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-semibold text-white tracking-wide truncate max-w-[180px]">${s.name || s.id}</span>
            <span class="text-xs font-mono font-bold text-white px-2 py-0.5 rounded bg-[#1c1c24] border border-[#33333f]">
              ${m.tn_score ? 'TN ' + m.tn_score : 'GUARDADA'}
            </span>
          </div>

          <div class="flex flex-wrap gap-1.5 mb-3">
            <span class="tn-badge text-[10px]">${s.symbol || 'N/A'}</span>
            <span class="tn-badge text-[10px]">${s.timeframe || '1h'}</span>
            <span class="tn-badge text-[10px]">${s.entry_order_type || 'MARKET'}</span>
            <span class="tn-badge text-[10px] text-[#a0a0ab]">${(s.exit_mode || 'ATR_CLASSIC').replace('_', ' ')}</span>
          </div>

          <div class="p-2.5 rounded bg-[#09090c] border border-[#22222a] flex items-center justify-between my-2">
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

  } catch (err) {
    console.error('Error loading saved strategies:', err);
    container.innerHTML = `<div class="col-span-full py-8 text-center text-red-400 text-xs">Error al cargar estrategias guardadas.</div>`;
  }
}
window.loadSavedStrategies = loadSavedStrategies;

function useStrategyInPortfolio(strategyId) {
  showSection('portfolio-builder');
  setTimeout(() => {
    const cb = document.querySelector(`.port-strategy-cb[value="${strategyId}"]`);
    if (cb) {
      cb.checked = true;
      cb.closest('.portfolio-strategy-check')?.classList.add('checked');
      updatePortfolioSelectedCounter();
    }
  }, 200);
}
window.useStrategyInPortfolio = useStrategyInPortfolio;

// ============================================================================
// PORTFOLIO BUILDER & CHECKLIST
// ============================================================================

async function renderPortfolioStrategyChecklist() {
  const container = document.getElementById('portfolio-strategy-checklist');
  if (!container) return;

  container.innerHTML = `
    <div class="col-span-full py-8 text-center text-[#71717a] text-xs">
      <span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full mr-2"></span> Cargando estrategias disponibles...
    </div>
  `;

  try {
    const res = await fetch('/api/strategies/saved');
    let items = await res.json();

    if ((!items || items.length === 0) && state.candidates && state.candidates.length > 0) {
      items = state.candidates;
    }

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-8 text-center text-[#71717a] text-xs">
          No hay estrategias guardadas ni candidatas activas aún.<br>
          <button onclick="showSection('engine')" class="btn-primary text-xs mt-3">Ir al Motor Genético y Crear Estrategias →</button>
        </div>
      `;
      updatePortfolioSelectedCounter();
      return;
    }

    container.innerHTML = items.map((item, idx) => {
      const s = item.strategy || item;
      const m = item.metrics || {};
      const sid = s.id || `strat_${idx}`;
      const netProfit = m.total_return_usd !== undefined ? `${m.total_return_usd >= 0 ? '+' : ''}$${m.total_return_usd.toFixed(0)}` : '';

      return `
        <label class="portfolio-strategy-check checked" for="port-cb-${sid}">
          <input type="checkbox" id="port-cb-${sid}" value="${sid}" checked class="port-strategy-cb w-4 h-4 accent-white mt-1 cursor-pointer">
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between mb-1">
              <span class="text-xs font-semibold text-white truncate">${s.name || sid}</span>
              <span class="text-[10px] font-mono font-bold text-white">${s.symbol || ''} ${s.timeframe || ''}</span>
            </div>
            <div class="flex items-center justify-between text-[11px] text-[#a0a0ab]">
              <span>WR: <strong class="text-white">${(m.win_rate_pct || 0).toFixed(1)}%</strong> · Sh: <strong class="text-white">${(m.sharpe_ratio || 0).toFixed(2)}</strong></span>
              <span class="font-mono text-white font-semibold">${netProfit}</span>
            </div>
          </div>
        </label>
      `;
    }).join('');

    document.querySelectorAll('.port-strategy-cb').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const parent = e.target.closest('.portfolio-strategy-check');
        if (e.target.checked) {
          parent?.classList.add('checked');
        } else {
          parent?.classList.remove('checked');
        }
        updatePortfolioSelectedCounter();
      });
    });

    updatePortfolioSelectedCounter();

  } catch (err) {
    console.error('Error rendering portfolio checklist:', err);
    container.innerHTML = `<div class="col-span-full py-8 text-center text-red-400 text-xs">Error al cargar lista de estrategias.</div>`;
  }
}
window.renderPortfolioStrategyChecklist = renderPortfolioStrategyChecklist;

function updatePortfolioSelectedCounter() {
  const checked = document.querySelectorAll('.port-strategy-cb:checked');
  const counter = document.getElementById('portfolio-selected-count');
  if (counter) {
    counter.textContent = checked.length;
  }
}

function selectAllPortfolioStrategies() {
  document.querySelectorAll('.port-strategy-cb').forEach(cb => {
    cb.checked = true;
    cb.closest('.portfolio-strategy-check')?.classList.add('checked');
  });
  updatePortfolioSelectedCounter();
}
window.selectAllPortfolioStrategies = selectAllPortfolioStrategies;

function deselectAllPortfolioStrategies() {
  document.querySelectorAll('.port-strategy-cb').forEach(cb => {
    cb.checked = false;
    cb.closest('.portfolio-strategy-check')?.classList.remove('checked');
  });
  updatePortfolioSelectedCounter();
}
window.deselectAllPortfolioStrategies = deselectAllPortfolioStrategies;

async function createPortfolio() {
  const nameInput = document.getElementById('portfolio-name-input');
  const maxInput = document.getElementById('portfolio-max-strategies');
  const riskInput = document.getElementById('portfolio-risk-budget');
  const btn = document.getElementById('btn-create-portfolio');

  const selectedCbs = Array.from(document.querySelectorAll('.port-strategy-cb:checked'));
  if (selectedCbs.length < 2) {
    alert('Selecciona al menos 2 estrategias para combinar en el portafolio.');
    return;
  }

  const selectedIds = selectedCbs.map(cb => cb.value);
  const maxStrategies = parseInt(maxInput?.value) || 10;
  const riskBudget = parseFloat(riskInput?.value) || 1.0;
  const portfolioName = nameInput?.value.trim() || `Portafolio Multi-Estrategia (${selectedIds.length} Algoritmos)`;

  const payload = {
    name: portfolioName,
    strategy_ids: selectedIds,
    max_strategies: maxStrategies,
    risk_budget: riskBudget
  };

  const originalText = btn.innerHTML;
  btn.innerHTML = `<span class="animate-spin inline-block w-3 h-3 border-2 border-black border-t-transparent rounded-full mr-2"></span> Creando y Optimizando...`;
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

    alert(`✓ Portafolio "${port.name}" creado con éxito!\n\n• Estrategias combinadas: ${met.strategies_count}\n• Descorrelación / Diversificación: ${met.diversification_score}%\n• Reducción de Drawdown estimada: -${met.estimated_dd_reduction_pct}%\n• Net Profit combinado estimado: $${(met.combined_net_profit_usd || 0).toLocaleString()}`);

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
// SAVED PORTFOLIOS VIEW
// ============================================================================

async function loadSavedPortfolios() {
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
    const items = await res.json();

    if (countBadge) {
      countBadge.textContent = `${items.length} portafolios`;
    }

    if (!items || items.length === 0) {
      container.innerHTML = `
        <div class="col-span-full py-12 text-center text-[#71717a]">
          <div class="text-3xl mb-3">📁</div>
          <div class="text-sm font-medium text-white mb-1">Aún no hay portafolios guardados</div>
          <div class="text-xs">Crea tu primer portafolio multi-estrategia en la pestaña "Creador de Portafolio".</div>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(port => {
      const met = port.metrics || {};
      const subStrats = port.strategies_summary || [];

      return `
        <div class="tn-card flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-bold text-white uppercase tracking-wider">${port.name}</span>
              <span class="tn-badge tn-badge-white text-[10px]">
                ${met.diversification_score ? met.diversification_score + '% Descorrelación' : 'PORTAFOLIO'}
              </span>
            </div>
            <div class="text-[11px] text-[#71717a] mb-3">Creado: ${port.created_at || 'Reciente'} · ID: <span class="font-mono text-[#a0a0ab]">${port.id}</span></div>

            <div class="grid grid-cols-3 gap-2 p-2.5 rounded bg-[#09090c] border border-[#22222a] text-center my-3">
              <div>
                <div class="text-[9px] text-[#71717a] uppercase font-bold">Net Profit</div>
                <div class="text-xs font-mono font-bold text-white mt-0.5">
                  +$${(met.combined_net_profit_usd || 0).toLocaleString()}
                </div>
              </div>
              <div>
                <div class="text-[9px] text-[#71717a] uppercase font-bold">Win Rate</div>
                <div class="text-xs font-mono font-bold text-white mt-0.5">
                  ${(met.weighted_win_rate_pct || 0).toFixed(1)}%
                </div>
              </div>
              <div>
                <div class="text-[9px] text-[#71717a] uppercase font-bold">DD Reducción</div>
                <div class="text-xs font-mono font-bold text-white mt-0.5">
                  -${met.estimated_dd_reduction_pct || 35}%
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
            <button onclick="exportPortfolioJson('${port.id}')" class="btn-secondary text-[11px] py-1 px-2.5 flex-1" title="Descargar archivo de configuración JSON para bot">
              📥 Exportar Bot JSON
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
window.exportPortfolioJson = exportPortfolioJson;

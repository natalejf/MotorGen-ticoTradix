/* Shared historical catalogue: actual provider, coverage and resumable import. */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let timer;
  const dialog = document.createElement('dialog');
  dialog.className = 'history-dialog';
  dialog.innerHTML = `<div class="history-head"><div><h2>Datos históricos</h2><p>Base de diez años · H1, H4 y D1 · almacenamiento local comprimido</p></div><button class="btn-secondary" id="history-close">Cerrar</button></div>
    <div class="history-body"><p>Forex, oro e índices: Dukascopy BID. BTC/USD: Bitstamp. H4 y D1 se agregan desde H1 con cortes UTC; no son necesariamente las velas diarias de tu bróker. Los índices son CFD, no contratos de futuros.</p>
    <div class="history-toolbar"><button class="btn-primary" id="history-update">Actualizar / reanudar base</button><span id="history-progress" role="status" aria-live="polite"></span></div>
    <progress id="history-meter" max="1" value="0"></progress><div class="history-table-wrap"><table><thead><tr><th>Activo / fuente</th><th>H1</th><th>H4</th><th>D1</th><th>Espacio</th><th>Estado</th></tr></thead><tbody id="history-rows"></tbody></table></div>
    <p class="history-footnote">Las actualizaciones reutilizan meses guardados y renuevan los recientes. Los meses ausentes se informan; una importación incompleta no reemplaza la base activa. M30, si se utiliza, conserva su histórico independiente de Yahoo.</p><details id="history-errors-box" hidden><summary>Detalles de descarga</summary><pre id="history-errors"></pre></details></div>`;
  document.body.appendChild(dialog);
  const $ = id => dialog.querySelector(`#${id}`);
  const close = () => { dialog.close(); clearTimeout(timer); };
  $('history-close').onclick = close;
  dialog.addEventListener('close', () => clearTimeout(timer));
  dialog.addEventListener('click', event => { if (event.target === dialog) close(); });
  async function refresh() {
    try {
      const responses = await Promise.all([fetch('/api/symbols'), fetch('/api/history/status')]);
      if (responses.some(r => !r.ok)) throw new Error('No se pudo consultar la base histórica');
      const [symbols, job] = await Promise.all(responses.map(r => r.json()));
      $('history-rows').innerHTML = symbols.map(symbol => {
        const meta = symbol.history;
        const cells = ['1h', '4h', '1d'].map(tf => {
          const info = meta?.timeframes?.[tf];
          return `<td>${info ? `${Number(info.bars).toLocaleString()} velas<small>${escape(info.start.slice(0,10))} → ${escape(info.end.slice(0,10))}</small>` : 'Pendiente'}</td>`;
        }).join('');
        const size = Object.values(meta?.timeframes || {}).reduce((sum, tf) => sum + (tf.bytes || 0), 0);
        return `<tr><td><strong>${escape(symbol.symbol)}</strong><small>${escape(meta?.source || (symbol.symbol === 'BTCUSD' ? 'bitstamp' : 'dukascopy'))}</small></td>${cells}<td>${size ? (size/1048576).toFixed(2)+' MB' : '—'}</td><td>${meta?.status === 'complete' ? '<span class="history-ok">Disponible</span>' : meta ? `Incompleto: ${meta.missing_months.length} meses` : 'Pendiente'}</td></tr>`;
      }).join('');
      const running = job.status === 'running';
      $('history-update').disabled = running;
      $('history-progress').textContent = `${running ? 'Descargando' : ({completed:'Completado',partial:'Requiere reanudar',failed:'Falló',idle:'Sin descarga activa'}[job.status] || job.status)}${job.total ? ` · ${job.completed}/${job.total} meses · ${job.current_symbol || ''}` : ''}`;
      $('history-meter').max = job.total || 1;
      $('history-meter').value = job.completed || 0;
      $('history-errors-box').hidden = !job.errors?.length;
      $('history-errors').textContent = (job.errors || []).map(e => typeof e === 'string' ? e : `${e.symbol} · ${e.month}: ${e.error}`).join('\n');
      if (!running && typeof loadSymbols === 'function') await loadSymbols();
    } catch (error) { $('history-progress').textContent = error.message; }
    clearTimeout(timer);
    if (dialog.open) timer = setTimeout(refresh, 5000);
  }
  $('history-update').onclick = async () => {
    $('history-update').disabled = true;
    try {
      const response = await fetch('/api/history/update', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
      if (!response.ok) throw new Error('No se pudo iniciar la actualización');
      await refresh();
    } catch (error) { $('history-progress').textContent = error.message; $('history-update').disabled = false; }
  };
  window.historyCatalog = {open() { if (!dialog.open) dialog.showModal(); refresh(); }};
  const nav = document.querySelector('.sidebar-nav nav');
  if (nav) {
    const button = document.createElement('button');
    button.className = 'sidebar-item';
    button.innerHTML = '<span class="sidebar-item-icon">▤</span><span>Datos históricos</span>';
    button.onclick = () => window.historyCatalog.open();
    nav.appendChild(button);
  }
})();

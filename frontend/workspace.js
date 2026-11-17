/* Persistent workspace features. Editor text is never executed. */
function escapeWorkspaceText(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

window.explorationConfigError = config => {
  if (!config.symbols?.length) return 'Selecciona al menos un símbolo.';
  if (!config.timeframes?.length || config.timeframes.some(tf => !['30m','1h','4h','1d'].includes(tf))) return 'Selecciona una temporalidad válida.';
  if (!config.enabled_indicators?.length) return 'Selecciona al menos un indicador.';
  if (config.start_date && config.end_date && config.start_date > config.end_date) return 'La fecha inicial debe ser anterior o igual a la final.';
  return '';
};

document.addEventListener('DOMContentLoaded', () => {
  const style = document.createElement('style');
  style.textContent = `
    #workspace-tools {margin:16px;padding:14px;border:1px solid #353540;border-radius:10px;background:#101016;color:#eee;font-size:13px}
    #workspace-tools summary {cursor:pointer;font-weight:600} #workspace-tools fieldset {border:1px solid #333;padding:12px;margin-top:12px;border-radius:8px}
    #workspace-tools button,#workspace-tools select,#workspace-tools input {background:#20202b;color:#fff;border:1px solid #555;border-radius:5px;padding:6px;margin:4px}
    #workspace-tools button:disabled {opacity:.4} #workspace-editor {height:360px;border:1px solid #555;margin-top:8px}
    #workspace-editor textarea {width:100%;height:100%;background:#12121b;color:#eee;padding:10px;font-family:monospace}
    #workspace-message {white-space:pre-wrap;color:#a9d9ff;margin:8px} #workspace-risk-result {overflow:auto}
    #workspace-risk-result td,#workspace-risk-result th {padding:6px;border:1px solid #444;text-align:right}
    #workspace-progress {width:180px;vertical-align:middle} [data-rename-kind] {cursor:text}
    #candidates-grid.workspace-list {display:flex!important;flex-direction:column}
    #candidates-grid.workspace-list .candidate-card {min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
    @media(max-width:800px){#candidates-grid.workspace-list .candidate-card{display:block}}
  `;
  document.head.appendChild(style);
  const tools = document.createElement('div');
  tools.id = 'workspace-tools';
  tools.innerHTML = `<header><h1 style="font-size:22px;font-weight:600">IDE y herramientas</h1>
    <p>Editor de borradores y versiones. Guardar código aquí no modifica ni ejecuta los algoritmos del motor.</p></header>
    <div id="workspace-message" role="status" aria-live="polite"></div>
    <fieldset><legend>Sesiones de exploración</legend>
      <input id="workspace-session-name" placeholder="Nombre de sesión" maxlength="150" aria-label="Nombre de sesión">
      <button id="workspace-save">Guardar sesión actual</button><button id="workspace-refresh">Actualizar lista</button>
      <select id="workspace-sessions" aria-label="Sesiones"></select>
      <button id="workspace-open">Abrir</button><button id="workspace-resume">Reanudar</button>
      <button id="workspace-rename-session">Renombrar</button><button id="workspace-delete-session">Eliminar</button>
      <p>Reanudar conserva candidatos y comienza una población nueva con la configuración guardada.</p></fieldset>
    <fieldset><legend>IDE de estrategias · historial</legend>
      <select id="workspace-strategies" aria-label="Estrategia para editar"></select>
      <button id="workspace-load-strategies">Actualizar estrategias</button><button id="workspace-edit">Abrir estrategia</button>
      <select id="workspace-language" aria-label="Lenguaje"><option value="json">JSON de estrategia</option><option value="python">Python</option><option value="javascript">JavaScript</option><option value="plaintext">Texto</option></select>
      <button id="workspace-save-version">Guardar versión</button>
      <select id="workspace-versions" aria-label="Historial de versiones"></select><button id="workspace-restore-version">Ver versión</button>
      <div id="workspace-editor"><textarea aria-label="Editor de estrategia" spellcheck="false"></textarea></div>
      <p id="workspace-editor-status">Editor de texto disponible. Cargando Monaco…</p>
      <p>Sirve para revisar el JSON de una estrategia, tomar notas técnicas y conservar versiones. No es necesario para crear portafolios ni para usar copy trading.</p></fieldset>
    <fieldset><legend>Correlación y Monte Carlo del portafolio</legend>
      <select id="workspace-portfolios" aria-label="Portafolio"></select><button id="workspace-refresh-portfolios">Actualizar portafolios</button>
      <label>Simulaciones <input id="workspace-simulations" type="number" min="100" max="10000" value="1000"></label>
      <label>Ruina: DD % <input id="workspace-ruin" type="number" min="1" max="100" value="30"></label>
      <label>Bloque (días) <input id="workspace-block" type="number" min="1" max="60" value="5"></label>
      <button id="workspace-risk">Calcular matriz y Monte Carlo</button><div id="workspace-risk-result"></div></fieldset>`;
  const workspaceSection = document.createElement('section');
  workspaceSection.id = 'section-workspace';
  workspaceSection.className = 'app-section hidden';
  workspaceSection.appendChild(tools);
  document.getElementById('section-engine').before(workspaceSection);
  const workspaceNav = document.createElement('button');
  workspaceNav.className = 'sidebar-item';
  workspaceNav.dataset.section = 'workspace';
  workspaceNav.innerHTML = '<span class="sidebar-item-icon">⌨</span><span class="flex-1">IDE y herramientas</span>';
  workspaceNav.addEventListener('click', () => showSection('workspace'));
  document.querySelector('#app-sidebar nav').appendChild(workspaceNav);
  const $ = id => document.getElementById(id);
  const message = text => { $('workspace-message').textContent = text; };
  const api = async (url, method='GET', body) => {
    const response = await fetch(url, {method, headers:{'Content-Type':'application/json'}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
    return value;
  };
  const action = (id, fn) => $(id).addEventListener('click', async () => {
    $(id).disabled = true;
    try { await fn(); } catch(error) { message(error.message); } finally { $(id).disabled = false; }
  });
  const options = (id, list, label=x=>x.name) => {
    const previous = $(id).value;
    $(id).replaceChildren(...list.map(x => new Option(label(x), x.id)));
    if (list.some(x => x.id === previous)) $(id).value = previous;
  };
  const snapshotUI = () => ({
    fields: Array.from(document.querySelectorAll('input[id],select[id]')).filter(e=>!e.id.startsWith('workspace-')).map(e=>({id:e.id,value:e.value,checked:e.checked})),
    symbols:[...state.selectedSymbols],timeframes:[...state.selectedTimeframes],
    indicators:state.enabledIndicators,
    ranges:state.indicatorRanges,exitRanges:state.exitRanges
  });
  const restoreUI = saved => {
    if (!saved?.fields) return;
    saved.fields.forEach(field=>{const el=$(field.id);if(el){el.value=field.value;if('checked' in el)el.checked=field.checked;}});
    state.selectedSymbols=new Set(saved.symbols);state.selectedSymbol=saved.symbols[0];
    state.selectedTimeframes=new Set(saved.timeframes);state.selectedTimeframe=saved.timeframes[0];
    state.enabledIndicators=saved.indicators;
    state.indicatorRanges=saved.ranges;state.exitRanges=saved.exitRanges;
    renderSymbolPills();renderTfPills();renderMacroSeries();updateCombinationsCounter();
    document.querySelectorAll('.ind-checkbox').forEach(e=>{e.checked=!!state.enabledIndicators[e.value];});
  };
  const sessions = async () => options('workspace-sessions',await api('/api/sessions'),x=>`${x.name} (${x.candidate_count})`);
  action('workspace-refresh',sessions);
  action('workspace-save',async()=>{
    const config=buildExplorationConfig();if(!config) return;
    const error=window.explorationConfigError(config);if(error) throw new Error(error);
    await api('/api/sessions','POST',{name:$('workspace-session-name').value.trim()||'Exploración',config,ui_state:snapshotUI()});
    await sessions();message('Sesión guardada.');
  });
  const sessionKey=()=>{const key=$('workspace-sessions').value;if(!key)throw new Error('Selecciona una sesión.');return encodeURIComponent(key);};
  action('workspace-open',async()=>{
    const saved=await api(`/api/sessions/${sessionKey()}/open`,'POST');restoreUI(saved.ui_state);
    state.candidates=saved.candidates;renderCandidates();await pollStatus();message('Sesión abierta.');
  });
  action('workspace-resume',async()=>{
    const key=sessionKey(), saved=await api(`/api/sessions/${key}`);restoreUI(saved.ui_state);
    await api(`/api/sessions/${key}/resume`,'POST');startPolling();message('Exploración reanudada con candidatos guardados.');
  });
  action('workspace-rename-session',async()=>{
    const name=$('workspace-session-name').value.trim();if(!name)throw new Error('Escribe el nuevo nombre.');
    await api(`/api/sessions/${sessionKey()}`,'PATCH',{name});await sessions();
  });
  action('workspace-delete-session',async()=>{const key=sessionKey();if(!confirm('¿Eliminar esta sesión guardada?'))return;await api(`/api/sessions/${key}`,'DELETE');await sessions();});

  let strategies=[], versions=[], editor=null, activeStrategy='';
  const source=()=>editor?editor.getValue():$('workspace-editor').querySelector('textarea').value;
  const setSource=text=>{if(editor)editor.setValue(text);else $('workspace-editor').querySelector('textarea').value=text;};
  const loadStrategies=async()=>{
    const live=await api('/api/candidates'), saved=await api('/api/strategies/saved');
    const items=Array.isArray(saved)?saved:(saved.strategies||[]);
    strategies=Array.from(new Map([...live,...items].map(x=>[x.strategy?.id||x.id,x])).values());
    options('workspace-strategies',strategies.map(x=>({id:x.strategy?.id||x.id,name:x.strategy?.name||x.name})));
  };
  const loadVersions=async()=>{versions=await api(`/api/editor/${encodeURIComponent(activeStrategy)}/versions`);options('workspace-versions',versions.map(v=>({id:String(v.version),name:`v${v.version} · ${v.created_at}`})));};
  action('workspace-load-strategies',loadStrategies);
  action('workspace-edit',async()=>{
    activeStrategy=$('workspace-strategies').value;if(!activeStrategy)throw new Error('Selecciona una estrategia.');
    const item=strategies.find(x=>(x.strategy?.id||x.id)===activeStrategy);
    $('workspace-language').value='json';setSource(JSON.stringify(item.strategy||item,null,2));await loadVersions();
    if(versions.length){const latest=versions[versions.length-1];setSource(latest.source);$('workspace-language').value=latest.language;}
    if(editor)monaco.editor.setModelLanguage(editor.getModel(),$('workspace-language').value);
  });
  action('workspace-save-version',async()=>{
    if(!activeStrategy)throw new Error('Abre una estrategia primero.');
    if($('workspace-language').value==='json')JSON.parse(source());
    await api(`/api/editor/${encodeURIComponent(activeStrategy)}/versions`,'POST',{source:source(),language:$('workspace-language').value});
    await loadVersions();message('Versión guardada.');
  });
  action('workspace-restore-version',async()=>{
    const version=versions.find(v=>String(v.version)===$('workspace-versions').value);if(!version)throw new Error('Selecciona una versión.');
    setSource(version.source);$('workspace-language').value=version.language;
    if(editor)monaco.editor.setModelLanguage(editor.getModel(),version.language);
  });
  $('workspace-language').addEventListener('change',()=>{if(editor)monaco.editor.setModelLanguage(editor.getModel(),$('workspace-language').value);});
  const loader=document.createElement('script');loader.src='https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs/loader.js';
  loader.onload=()=>{
    window.require.config({paths:{vs:'https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs'}});
    window.require(['vs/editor/editor.main'],()=>{
      const value=source();$('workspace-editor').replaceChildren();
      editor=monaco.editor.create($('workspace-editor'),{value,language:'json',theme:'vs-dark',automaticLayout:true,minimap:{enabled:false}});
      $('workspace-editor-status').textContent='Monaco · Guardado manual e historial de versiones.';
    },()=>{$('workspace-editor-status').textContent='Monaco no disponible. Editor de texto e historial activos.';});
  };
  loader.onerror=()=>{$('workspace-editor-status').textContent='Sin conexión a Monaco. Editor de texto e historial activos.';};
  document.head.appendChild(loader);

  const portfolios=async()=>{const list=await api('/api/portfolios');options('workspace-portfolios',Array.isArray(list)?list:(list.portfolios||[]));};
  action('workspace-refresh-portfolios',portfolios);
  action('workspace-risk',async()=>{
    const key=$('workspace-portfolios').value;if(!key)throw new Error('Selecciona un portafolio guardado.');
    message('Calculando correlación y Monte Carlo…');
    const risk=await api(`/api/portfolio/${encodeURIComponent(key)}/risk`,'POST',{
      simulations:Number($('workspace-simulations').value),ruin_drawdown_pct:Number($('workspace-ruin').value),block_size:Number($('workspace-block').value)});
    const names=risk.labels.map(escapeWorkspaceText);
    let html=`<p>${risk.observations} días comunes · ${risk.simulations} simulaciones por bloques de ${risk.block_size} días.</p><table><thead><tr><th>Correlación</th>${names.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>`;
    risk.correlation.forEach((row,i)=>{html+=`<tr><th>${names[i]}</th>${row.map(v=>`<td style="background:${v===null?'#222':`rgba(${v<0?'60,130,220':'220,80,60'},${Math.abs(v)*.65})`}">${v===null?'N/D':v.toFixed(2)}</td>`).join('')}</tr>`;});
    html+='</tbody></table><table><tr><th>Percentil</th><th>Equity final</th><th>DD máximo %</th></tr>';
    ['p5','p50','p95'].forEach(p=>{html+=`<tr><th>${p}</th><td>${risk.terminal_equity[p].toFixed(2)}</td><td>${risk.max_drawdown_pct[p].toFixed(2)}%</td></tr>`;});
    html+=`</table><p>Probabilidad de alcanzar DD ≥ ${risk.ruin_drawdown_pct}%: ${risk.ruin_probability_pct.toFixed(2)}%</p>`;
    const paths=risk.equity_percentiles, min=Math.min(...paths.flat()),max=Math.max(...paths.flat()),span=max-min||1;
    html+='<svg viewBox="0 0 800 220" role="img" aria-label="Equity Monte Carlo percentiles 5, 50 y 95" style="width:100%;max-height:240px;background:#0b0b12">';
    paths.forEach((path,i)=>{const points=path.map((v,j)=>`${10+j*780/Math.max(1,path.length-1)},${210-(v-min)*195/span}`).join(' ');html+=`<polyline fill="none" stroke="${['#e88','#fff','#8e8'][i]}" stroke-width="2" points="${points}"/>`;});
    html+='</svg><p>Curvas: p5 rojo · p50 blanco · p95 verde. Correlación N/D: componente constante.</p>';
    $('workspace-risk-result').innerHTML=html;message('Análisis de portafolio completado.');
  });

  const start=$('btn-start-exploration');
  const progress=document.createElement('div');progress.innerHTML='<progress id="workspace-progress" max="100" value="0"></progress> <span id="workspace-percent">0%</span><span id="workspace-config-error" role="status"></span>';
  start.parentElement.appendChild(progress);
  const toggle=document.createElement('button');toggle.className='btn-secondary';toggle.textContent='Vista lista / grid';
  $('candidates-grid').before(toggle);
  let listView=localStorage.getItem('tn-candidates-view')==='list';
  const applyView=()=>$('candidates-grid').classList.toggle('workspace-list',listView);applyView();
  toggle.onclick=()=>{listView=!listView;localStorage.setItem('tn-candidates-view',listView?'list':'grid');applyView();};
  const speed=document.createElement('label');speed.textContent='Velocidad ';
  const slider=document.createElement('input');slider.type='range';slider.min='.25';slider.max='3';slider.step='.25';slider.value='1';slider.setAttribute('aria-label','Velocidad Neural Explorer');
  const speedLabel=document.createElement('span');speedLabel.textContent='1×';
  slider.oninput=()=>{state.neuralSpeed=Number(slider.value);speedLabel.textContent=`${slider.value}×`;};
  speed.append(slider,speedLabel);$('neural-pause').before(speed);
  setInterval(()=>{
    const status=state.status||{},pct=Math.max(0,Math.min(100,Number(status.progress_pct)||0));
    $('workspace-progress').value=pct;$('workspace-percent').textContent=`${pct.toFixed(1)}%${$('check-infinite-mode').checked?' · ronda actual':''}`;
    let error='';
    if(!state.selectedSymbols.size)error='Selecciona un símbolo.';
    else if(!state.selectedTimeframes.size)error='Selecciona una temporalidad.';
    else if(!Object.values(state.enabledIndicators).some(Boolean))error='Selecciona un indicador.';
    else if($('input-start-date').value && $('input-end-date').value && $('input-start-date').value>$('input-end-date').value)error='Rango de fechas inválido.';
    start.disabled=!!error||!!state.isRunning;$('workspace-config-error').textContent=error;
  },500);
  document.addEventListener('dblclick',async event=>{
    const target=event.target.closest('[data-rename-kind]');if(!target)return;
    const name=prompt('Nuevo nombre',target.textContent.trim());if(!name?.trim())return;
    try{
      await api(`/api/rename/${target.dataset.renameKind}/${encodeURIComponent(target.dataset.renameId)}`,'PATCH',{name:name.trim()});
      target.textContent=name.trim();
      const candidate=state.candidates.find(x=>x.strategy.id===target.dataset.renameId);if(candidate)candidate.strategy.name=name.trim();
      message('Nombre actualizado.');
    }catch(error){message(error.message);}
  });
  Promise.allSettled([sessions(),portfolios(),loadStrategies()]).then(results=>{const failed=results.filter(x=>x.status==='rejected');if(failed.length)message(failed.map(x=>x.reason.message).join('\n'));});
});

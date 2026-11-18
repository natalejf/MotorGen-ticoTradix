// Pages hosts the interface; execution remains on the local authenticated bridge.
if (location.hostname.endsWith('.github.io')) {
  const accounts = [
    {id:'preview-master',name:'Master · MT5 Demo',login:10001,server:'Demo',connection_mode:'EA',connected:false},
    {id:'preview-follower',name:'Seguidora · NinjaTrader',login:0,server:'NinjaTrader',platform:'NT8',connection_mode:'NT8',connected:false}
  ];
  const fixtures = {
    '/api/copy/status': {accounts,masters:[{id:'preview-master-record',name:'Operativa principal',account_id:'preview-master'}],
      groups:[{id:'preview-group',name:'Fondeo · Grupo de ejemplo',description:'Vista de diseño con datos ficticios',account_ids:['preview-follower'],risk_mode:'RISK_PERCENT',risk_percent:.25,fixed_lot:1,multiplier:1,max_daily_loss_pct:2,max_drawdown_pct:5}],deployments:[],events:[]},
    '/api/ninja/status':{connections:[],groups:[]},
    '/api/strategies/saved':[], '/api/portfolios':[], '/api/symbols':[],
    '/api/sessions':[], '/api/candidates':[], '/api/retest/results':[],
    '/api/rule-operators':[], '/api/config-defaults':{}, '/api/status':{}
  };
  const originalFetch=window.fetch.bind(window);
  window.fetch=(input,options={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    if(url.origin===location.origin&&url.pathname.startsWith('/api/')){
      const reading=(options.method||'GET').toUpperCase()==='GET';
      return Promise.resolve(new Response(JSON.stringify(reading?(fixtures[url.pathname]??{}):{detail:'Vista de diseño. Abre el panel local para guardar cambios y conectar terminales.'}),{status:reading?200:503,headers:{'Content-Type':'application/json'}}));
    }
    return originalFetch(input,options);
  };
  document.addEventListener('DOMContentLoaded', () => {
    const notice = document.createElement('div');
    notice.setAttribute('role', 'status');
    notice.style.cssText = 'position:fixed;bottom:12px;left:12px;right:12px;z-index:99999;padding:12px 18px;background:#17171c;border:1px solid #555;color:white;border-radius:8px;font:13px system-ui';
    notice.textContent = 'Vista online · Datos ficticios. Para conectar terminales y ejecutar operaciones, abre INICIAR_TRADINGNOTE.bat en tu PC.';
    document.body.append(notice);
  });
}

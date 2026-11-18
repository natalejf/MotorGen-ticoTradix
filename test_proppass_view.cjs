const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const context={escapeWorkspaceText:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/proppass-view.js','utf8'),context);
function fixture(){
 const settings={accounts:['A'],lots:4,symbol:'NQ DEC26',timeframe_minutes:5,tp_usd:1500,sl_usd:2000,daily_profit_limit:1500,daily_loss_limit:2000};
 const groups=[{id:'one',name:'Primero',settings},{id:'two',name:'Segundo',settings:{...settings,accounts:['B'],lots:1,tp_usd:150}}];
 return {groups,connections:[{id:'service',connected:true,active_group_id:'one',applied_settings:settings,
  snapshot:{accounts:[{name:'A',enabled:true,status:'PASS',lots:4},{name:'B',enabled:false,status:'EN PROCESO'}],master_enabled:true},
  queue:{state:'RUNNING',items:[{group_id:'one',state:'ACTIVE'},{group_id:'two',state:'PENDING'}]}}]};
}
function toggle(html,name){return [...html.matchAll(/<button class="pp-switch[^>]*>/g)].map(m=>m[0]).find(x=>x.includes(`data-account="${name}"`));}
test('terminal account toggle is off and locked, also after moving to next group',()=>{
 const data=fixture();let html=context.renderPropPass(data);
 assert(toggle(html,'A').includes('aria-checked="false"'));
 assert(toggle(html,'A').includes('disabled'));
 assert(toggle(html,'B').includes('aria-checked="true"'));
 data.connections[0].active_group_id='two';data.connections[0].queue.items[0].state='COMPLETED';
 html=context.renderPropPass(data);
 assert(toggle(html,'A').includes('aria-checked="false"'));
 assert(toggle(html,'A').includes('disabled'));
 assert(html.includes('Completado'));
});
test('pending group parameters and toggle do not alter another group or native data',()=>{
 const data=fixture(),before=context.renderPropPass(data);
 const first=html=>html.split('<article class="pp-group')[1].split('</article>')[0];
 const native=JSON.stringify(data.connections[0].snapshot);
 data.groups[1].settings={...data.groups[1].settings,tp_usd:555,account_overrides:{B:{enabled:false}}};
 const after=context.renderPropPass(data);
 assert.equal(first(before),first(after));
 assert(toggle(after,'B').includes('aria-checked="false"'));
 assert.equal(JSON.stringify(data.connections[0].snapshot),native);
});

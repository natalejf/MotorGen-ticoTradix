const {test}=require('node:test');
const assert=require('node:assert/strict');
require('./frontend/random-mix.js');
const catalog={};
for(let family=0;family<7;family++)for(let i=0;i<4;i++)catalog[`F${family}_${i}`]={family:String(family)};
let seed=41;
const rng=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};

test('compact mixes stay bounded, cover different families and retain every choice',()=>{
  const seen=new Set(),entries=new Set(),exits=new Set(),counts=new Set();
  for(let i=0;i<1000;i++){
    const selected=StratixMix.indicators(catalog,rng),orders=StratixMix.orders(rng);
    assert(selected.length===7);
    assert.equal(new Set(selected).size,selected.length);
    assert.equal(new Set(selected.map(key=>catalog[key].family)).size,selected.length);
    assert.equal(orders.entries.length,1);assert.equal(orders.exits.length,1);
    selected.forEach(key=>seen.add(key));orders.entries.forEach(key=>entries.add(key));orders.exits.forEach(key=>exits.add(key));counts.add(selected.length);
  }
  assert.equal(seen.size,28);assert.equal(entries.size,3);assert.equal(exits.size,9);
  assert.deepEqual([...counts].sort(),[7]);
});

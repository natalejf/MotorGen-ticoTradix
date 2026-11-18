/* Compact random sampling without the bias of Array.sort(Math.random). */
(function(root){
  function shuffle(values,rng=Math.random){
    const result=[...values];
    for(let i=result.length-1;i>0;i--){const j=Math.floor(rng()*(i+1));[result[i],result[j]]=[result[j],result[i]];}
    return result;
  }
  function indicators(catalog,rng=Math.random){
    const families={};
    for(const [key,meta] of Object.entries(catalog))(families[meta.family]??=[]).push(key);
    const groups=shuffle(Object.values(families),rng);
    return groups.map(keys=>keys[Math.floor(rng()*keys.length)]);
  }
  function orders(rng=Math.random){
    return {entries:shuffle(['entry-market','entry-limit','entry-stop'],rng).slice(0,1),
      exits:shuffle(['exit-atr','exit-pips','exit-pct','exit-trailing','exit-breakeven','exit-swing','exit-time','exit-partial','exit-atr-smooth'],rng).slice(0,1)};
  }
  root.StratixMix={shuffle,indicators,orders};
})(typeof window==='undefined'?globalThis:window);

"""Build RocketPass using the shared service/rotation shell and its own grid core."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).parent


def main():
    source=ROOT/'StratixCandleService.cs'
    code=source.read_text(encoding='utf-8')
    code=code.replace('StratixCandleService','RocketPassService').replace('"Stratix","NinjaTrader"','"Stratix","RocketPass"')
    code=code.replace('/api/ninja/','/api/rocket/').replace('CandleBridge.key','RocketBridge.key')
    code=code.replace('1.7.0-pending','1.9.0-vote40')
    code=code.replace('CandleServiceConfig.txt','RocketServiceConfig.txt').replace('CandleServiceScope.txt','RocketServiceScope.txt')
    assert r'\"closed_bars\":"+CurrentBar+' in code, 'No se encontro closed_bars en StratixCandleService.cs'
    code=code.replace(r'\"closed_bars\":"+CurrentBar+', r'\"closed_bars\":"+CurrentBar+RocketTrendJson()+')
    code=code.replace('EntryLong','RocketEntryLong').replace('EntryShort','RocketEntryShort')
    code=code.replace('"TP_"','"ROCKET_TP_"').replace('"SL_"','"ROCKET_SL_"')
    code=code.replace('if(n.StartsWith("TP_",StringComparison.OrdinalIgnoreCase)||n.StartsWith("SL_",StringComparison.OrdinalIgnoreCase))return true;\n            return false;', 'if(n.StartsWith("TP_",StringComparison.OrdinalIgnoreCase)||n.StartsWith("SL_",StringComparison.OrdinalIgnoreCase))return true;\n            if(RocketGridOrder(order))return true;\n            return false;')
    code=code.replace('EngineExecution(e);ObserveCandleExecution(e);','EngineExecution(e);RocketExecution(e);ObserveCandleExecution(e);')
    start=code.index('                if(CurrentBar>=2 && masterTradingEnabled')
    end=code.index('\n            }\n        }',start)
    code=code[:start]+'                RocketOnBar(open,close);'+code[end:]
    code=code.replace('double open=candleOpen,close=candleClose;candleSlot=slot;', 'long rocketClosedSlot=candleSlot;double open=candleOpen,close=candleClose;candleSlot=slot;')
    code=code.replace('                RocketOnBar(open,close);','                RocketFeed();')
    code=code.replace('CurrentBar++;','CurrentBar=rocketVotes.Count;')
    code=code.replace('ReleaseAccountReservations();masterTradingEnabled=false;','RocketStopFeed();ReleaseAccountReservations();masterTradingEnabled=false;')
    code=code.replace('if(Instrument!=null)PeriodicMonitoring();','RocketMonitor();RocketFeed();RocketTryEntry();')
    code=code.replace('long slot=lastTick.Ticks/', 'RocketMonitor();long slot=lastTick.Ticks/')
    code=code.replace('LoadEvaluationAccounts();LoadConfiguration();','RocketLoad();LoadEvaluationAccounts();LoadConfiguration();')
    code=code.replace('ReserveAccounts(selected.Concat(engineLeases.Values.Select(l=>l.Account)));','RocketConfigure(values);ReserveAccounts(selected.Concat(engineLeases.Values.Select(l=>l.Account)));')
    code=code.replace('foreach(string name in targets)StopCandleAccount(name,target);','foreach(string name in targets){RocketBasket basket;if(!rocketBaskets.TryGetValue(name,out basket)){basket=new RocketBasket();rocketBaskets[name]=basket;}basket.Closing=true;RocketCancelGrid(GetAccountCached(name));}RocketSave();')
    code=code.replace('bridgeHealth.Resume(DateTime.UtcNow);masterTradingEnabled=true;', 'bridgeHealth.Resume(DateTime.UtcNow);masterTradingEnabled=true;RocketTryEntry();')
    code=code.replace('else if(action=="pause")PauseEntries', 'else if(action=="pause")PauseEntries')
    code=code.replace('PROPPASS','ROCKETPASS').replace('PropPass','RocketPass')
    marker='        private readonly object serviceGate=new object();'
    code=code.replace('candleSlot=-1;CurrentBar=0;lastTick=', 'RocketStopFeed();candleSlot=-1;CurrentBar=0;lastTick=')
    code=code.replace(marker,ROOT.joinpath('RocketMath.fragment.cs').read_text(encoding='utf-8')+'\n'+ROOT.joinpath('RocketGrid.fragment.cs').read_text(encoding='utf-8')+'\n'+marker)
    ROOT.joinpath('RocketPassService.cs').write_text(code,encoding='utf-8')
    original=Path(r'C:\Users\yo\OneDrive\Documentos\NinjaTrader 8\bin\Custom\Strategies\TrendLimitGridBot.cs')
    ROOT.joinpath('rocket_manifest.json').write_text(json.dumps(dict(algorithm_source=str(original),algorithm_sha256=hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None,original_unchanged=True,shell_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),execution='SIM_OR_EXPLICIT_EVALUATION_ALLOWLIST',compile_status='PENDING'),indent=2),encoding='utf-8')
    print('RocketPass generado con configuración, grupos y cuadrícula independientes.')


if __name__=='__main__':main()

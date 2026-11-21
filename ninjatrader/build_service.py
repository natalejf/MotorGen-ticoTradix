"""Extract the user's trading/risk core into a chart-independent NT8 AddOn."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).parent
SOURCE=Path(r'C:\Users\yo\OneDrive\Escritorio\NinjaTrader EA Evals\CandleController.cs')


def main():
    raw=SOURCE.read_bytes();source=raw.decode('utf-8-sig')
    account=source[source.index('        public class AccountRiskSettings'):source.index('        //  ESTRUCTURA PARA REFERENCIAS UI')]
    account=account[:account.rfind('        // =====================================================================')]
    account=account.replace('Lots = 10;','Lots = 1;')
    account=account.replace('public double SessionRealizedPnl { get; set; }','public double SessionRealizedPnl { get; set; }\n            public int TradesWon,TradesLost,TradesClosed;')
    config=source[source.index('        private Account GetAccountCached'):source.index('        protected override void OnStateChange')]
    core=source[source.index('        private void EvaluateEntrySignals'):source.index('        //  UI HELPERS')]
    core=core[:core.rfind('        // =====================================================================')]
    # Discovery is independent from the execution authorization check.
    core=core.replace('Draw.HorizontalLine(this,','NoChart(')
    core=core.replace('private void OnGlobalExecutionUpdate(', 'private void ProcessAccountExecution(')
    core=core.replace('acc.Submit(', 'QueueSubmit(acc,').replace('acc.Cancel(', 'QueueCancel(acc,').replace('acc.Flatten(', 'QueueFlatten(acc,')
    core=core.replace('if (e.Execution == null || e.Execution.Account == null) return;', 'if (Instrument == null || e.Execution == null || e.Execution.Account == null || e.Execution.Order == null || e.Execution.Order.Instrument.FullName != Instrument.FullName || !groupAccounts.Contains(e.Execution.Account.Name)) return;')
    core=core.replace('foreach (var kvp in accountsConfig)','foreach (var kvp in accountsConfig.OrderBy(p=>Array.IndexOf(groupAccounts,p.Key)))')
    core=core.replace('settings.SessionRealizedPnl += tradePnl;',
        'settings.SessionRealizedPnl += tradePnl;\n                            if(e.Execution.Order!=null && !e.Execution.Order.Name.StartsWith("Entry",StringComparison.Ordinal)) {settings.TradesClosed++;if(tradePnl>0)settings.TradesWon++;else if(tradePnl<0)settings.TradesLost++;}')
    core=core.replace('if (targetRoom > 0)','if (eff.Target > 0 && targetRoom > 0)').replace('if (dailyProfitRoom > 0)','if (eff.DailyProfitLimit > 0 && dailyProfitRoom > 0)').replace('if (lossRoom > 0)','if (eff.MaxLoss > 0 && lossRoom > 0)').replace('if (dailyLossRoom > 0)','if (eff.DailyLossLimit > 0 && dailyLossRoom > 0)')
    core=core.replace('settings.DailyStatus == "EN PROCESO" && (dailyPnlFloating <= -eff.DailyLossLimit',
        'settings.DailyStatus == "EN PROCESO" && eff.DailyLossLimit > 0 && (dailyPnlFloating <= -eff.DailyLossLimit')
    core=core.replace('(dailyPnlRealized >= eff.DailyProfitLimit || dailyPnlRealized >= eff.Target || dailyPnlFloating >= eff.DailyProfitLimit || dailyPnlFloating >= eff.Target)',
        '((eff.DailyProfitLimit > 0 && (dailyPnlRealized >= eff.DailyProfitLimit || dailyPnlFloating >= eff.DailyProfitLimit)) || (eff.Target > 0 && (dailyPnlRealized >= eff.Target || dailyPnlFloating >= eff.Target)))')
    before,monitor=core.split('        private void PeriodicMonitoring()',1)
    monitor=monitor.replace('removedAccounts.Contains(kvp.Key) || !settings.Enabled || settings.Status != "EN PROCESO"',
        '!groupAccounts.Contains(kvp.Key) || removedAccounts.Contains(kvp.Key) || settings.Status != "EN PROCESO"')
    monitor=monitor.replace('if (pos != null && pos.MarketPosition != MarketPosition.Flat)',
        'if(!settings.Enabled && (pos==null || pos.MarketPosition==MarketPosition.Flat))continue;\n                        if (pos != null && pos.MarketPosition != MarketPosition.Flat)',1)
    core=before+'        private void PeriodicMonitoring()'+monitor
    core=core.replace('double tpDelta = tradeTpUsd / (qty * ptVal);\r\n            double slDelta = tradeSlUsd / (qty * ptVal);',
        'double commBuffer = qty * (settings.CommissionPerContract > 0 ? settings.CommissionPerContract * 2.0 : 4.50) + (Instrument.MasterInstrument.TickSize * ptVal * qty * 2.0);\r\n            double tpDelta = (tradeTpUsd + commBuffer) / (qty * ptVal);\r\n            double slDelta = Math.Max(Instrument.MasterInstrument.TickSize * ptVal * qty, tradeSlUsd - commBuffer) / (qty * ptVal);')
    core=core.replace('double tpDelta = tradeTpUsd / (qty * ptVal);\n            double slDelta = tradeSlUsd / (qty * ptVal);',
        'double commBuffer = qty * (settings.CommissionPerContract > 0 ? settings.CommissionPerContract * 2.0 : 4.50) + (Instrument.MasterInstrument.TickSize * ptVal * qty * 2.0);\n            double tpDelta = (tradeTpUsd + commBuffer) / (qty * ptVal);\n            double slDelta = Math.Max(Instrument.MasterInstrument.TickSize * ptVal * qty, tradeSlUsd - commBuffer) / (qty * ptVal);')
    core=core.replace('tpPrice = Math.Round(tpPrice / Instrument.MasterInstrument.TickSize) * Instrument.MasterInstrument.TickSize;\r\n            slPrice = Math.Round(slPrice / Instrument.MasterInstrument.TickSize) * Instrument.MasterInstrument.TickSize;',
        'tpPrice = (pos.MarketPosition == MarketPosition.Long ? Math.Ceiling(tpPrice / Instrument.MasterInstrument.TickSize) : Math.Floor(tpPrice / Instrument.MasterInstrument.TickSize)) * Instrument.MasterInstrument.TickSize;\r\n            slPrice = (pos.MarketPosition == MarketPosition.Long ? Math.Ceiling(slPrice / Instrument.MasterInstrument.TickSize) : Math.Floor(slPrice / Instrument.MasterInstrument.TickSize)) * Instrument.MasterInstrument.TickSize;')
    core=core.replace('tpPrice = Math.Round(tpPrice / Instrument.MasterInstrument.TickSize) * Instrument.MasterInstrument.TickSize;\n            slPrice = Math.Round(slPrice / Instrument.MasterInstrument.TickSize) * Instrument.MasterInstrument.TickSize;',
        'tpPrice = (pos.MarketPosition == MarketPosition.Long ? Math.Ceiling(tpPrice / Instrument.MasterInstrument.TickSize) : Math.Floor(tpPrice / Instrument.MasterInstrument.TickSize)) * Instrument.MasterInstrument.TickSize;\n            slPrice = (pos.MarketPosition == MarketPosition.Long ? Math.Ceiling(slPrice / Instrument.MasterInstrument.TickSize) : Math.Floor(slPrice / Instrument.MasterInstrument.TickSize)) * Instrument.MasterInstrument.TickSize;')
    core=core.replace('(Close.Count > 0 ? Close[0] : avgPrice)','avgPrice').replace('(Close.Count > 0 ? Close[0] : 0.0)','0.0')
    core=core.replace('            settings.Direction = direction;',
        '            if (!CanExecute(acc)) throw new Exception("Solo simulación autorizada");\n            settings.Direction = direction;',1)
    fragment=ROOT.joinpath('CandleService.fragment.cs').read_text(encoding='utf-8')
    imports='\n'.join(['using System;','using System.Collections.Generic;','using System.Linq;',
        'using System.IO;','using System.Text;','using System.Windows.Media;','using NinjaTrader.Cbi;',
        'using NinjaTrader.Data;','using NinjaTrader.Gui;','using NinjaTrader.NinjaScript;'])
    core=core.replace('if (Instrument == null || e.Execution', 'if(e.Execution!=null && e.Execution.Account!=null && (!candleOwnedAccounts.Contains(e.Execution.Account.Name)||candleOwnershipConflicts.Contains(e.Execution.Account.Name)))return;\n            if(e.Execution!=null && e.Execution.Order!=null && e.Execution.Order.Name.StartsWith("STXG_"))return;\n            if (Instrument == null || e.Execution')
    core=core.replace('            settings.Direction = direction;', '            candleOwnedAccounts.Add(acc.Name);\n            settings.Direction = direction;',1)
    core=core.replace('!groupAccounts.Contains(kvp.Key) || removedAccounts', '!CanManageCandle(GetAccountCached(kvp.Key),Instrument) || !groupAccounts.Contains(kvp.Key) || removedAccounts')
    core=core.replace('!groupAccounts.Contains(kvp.Key) || removedAccounts', 'engineLeases.Values.Any(l=>l.Account==kvp.Key) || !groupAccounts.Contains(kvp.Key) || removedAccounts')
    result=imports+'\nnamespace NinjaTrader.NinjaScript.AddOns {\n public class StratixCandleService : AddOnBase {\n'+account+ROOT.joinpath('EvaluationAccounts.fragment.cs').read_text(encoding='utf-8')+ROOT.joinpath('BridgeHealth.fragment.cs').read_text(encoding='utf-8')+ROOT.joinpath('EngineBridge.fragment.cs').read_text(encoding='utf-8')+ROOT.joinpath('CandleOwnership.fragment.cs').read_text(encoding='utf-8')+fragment+config+core+'\n }\n}\n'
    if 'ChartControl' in result or 'Draw.HorizontalLine' in result:raise RuntimeError('Quedó una dependencia del gráfico')
    ROOT.joinpath('StratixCandleService.cs').write_text(result,encoding='utf-8')
    ROOT.joinpath('service_manifest.json').write_text(json.dumps(dict(source=str(SOURCE),sha256=hashlib.sha256(raw).hexdigest(),
        original_unchanged=True,platform='NinjaTrader 8 AddOn',ui='WEB_ONLY',execution='SIM_ACCOUNTS_ONLY',
        candle_source='LIVE_TICKS_UTC',warmup='2 closed candles',compile_status='PENDING'),indent=2),encoding='utf-8')
    print('AddOn sin panel ni dependencia de gráfico generado.')


if __name__=='__main__':main()

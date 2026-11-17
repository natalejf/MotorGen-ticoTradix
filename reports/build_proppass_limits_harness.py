"""Exercise the generated C# limit/selection methods with deterministic account doubles.
No native orders or prices are fabricated in the live demo trial.
"""
from pathlib import Path
s=Path('ninjatrader/StratixCandleService.cs').read_text(encoding='utf-8')
def method(marker):
 start=s.index(marker);op=s.index('{',start);depth=1;i=op+1
 while depth:
  if s[i]=='{':depth+=1
  if s[i]=='}':depth-=1
  i+=1
 return s[start:i]
account=s[s.index('        public class AccountRiskSettings'):s.index('        private readonly object serviceGate')]
methods=method('        private void EvaluateEntrySignals')+'\n'+method('        private void PeriodicMonitoring')
stubs=r'''
using System;using System.Collections.Generic;using System.Linq;
enum MarketPosition { Flat,Long,Short } enum ConnectionStatus { Connected } enum Currency { UsDollar } enum AccountItem { CashValue,UnrealizedProfitLoss,RealizedProfitLoss } enum OrderAction { Buy,Sell }
class Order {} class Master {public string Name="NQ";} class Instrument {public string FullName="NQ DEC26";public Master MasterInstrument=new Master();}
class Position {public Instrument Instrument=new Instrument();public MarketPosition MarketPosition=MarketPosition.Flat;}
class Connection {public ConnectionStatus Status=ConnectionStatus.Connected;}
class Account {public string Name;public double Cash=50000,Open,Realized;public Connection Connection=new Connection();public List<Position> Positions=new List<Position>();public int Flattens;public double Get(AccountItem item,Currency c){return item==AccountItem.CashValue?Cash:item==AccountItem.UnrealizedProfitLoss?Open:Realized;}public void Flatten(Instrument[] symbols){Flattens++;Open=0;Positions.Clear();}}
class Harness {
'''
body=r'''
Dictionary<string,AccountRiskSettings> accountsConfig=new Dictionary<string,AccountRiskSettings>();Dictionary<string,Account> accounts=new Dictionary<string,Account>();HashSet<string> removedAccounts=new HashSet<string>();string[] groupAccounts;DateTime realtimeStartTime=DateTime.UtcNow.AddSeconds(-10);double lastRealtimePrice=20000;Instrument Instrument=new Instrument();string entered="";
Account GetAccountCached(string name){return accounts[name];}void Print(string text){}void SaveConfiguration(){}bool IsInTradingHours(AccountRiskSettings x){return true;}void ExecuteEntry(AccountRiskSettings x,AccountRiskSettings y,Account a,OrderAction action,string dir,double price){entered=a.Name;}void SyncTpSlOrders(Account a,AccountRiskSettings s,AccountRiskSettings e,Position p){}void CancelTpSlOrders(Account a,AccountRiskSettings s){}void ResetTradingState(Account a,AccountRiskSettings s){s.Direction="FLAT";}
void Setup(string[] names,double target){accounts.Clear();accountsConfig.Clear();groupAccounts=names;entered="";foreach(string name in names){accounts[name]=new Account{Name=name};accountsConfig[name]=new AccountRiskSettings(name){Enabled=true,Target=target,MaxLoss=2000,DailyProfitLimit=target,DailyLossLimit=2000,StartBalance=50000,DailyStartBalance=50000,LastResetDate=DateTime.UtcNow.AddHours(-3).ToString("yyyyMMdd")};}}
static void Check(bool b,string message){if(!b)throw new Exception(message);}
public static void Main(){var h=new Harness();int scenarios=0;foreach(var names in new[]{new[]{"Sim101","SimAccount2","SimAccount3","SimAccount4","SimAccount5"},new[]{"SimAccount6","SimAccount7","SimAccount8","SimAccount9","SimAccount10"}}){double target=names[0]=="Sim101"?1500:150;
 foreach(bool loss in new[]{false,true}){h.Setup(names,target);for(int i=0;i<names.Length;i++){var a=h.accounts[names[i]];var setting=h.accountsConfig[names[i]];a.Cash=50000+(loss?-2000:target);h.PeriodicMonitoring();Check(!setting.Enabled,"limit must disable account");Check(setting.Status==(loss?"BURNED":"PASS"),"terminal status");Check(a.Flattens==1,"flatten on limit");h.entered="";h.EvaluateEntrySignals(true,false);Check(h.entered==(i+1<names.Length?names[i+1]:""),"next account selection");scenarios++;}}
 h.Setup(names,target);h.accounts[names[0]].Cash=50000+target-1;h.PeriodicMonitoring();Check(h.accountsConfig[names[0]].Enabled,"must not pass below target");h.accounts[names[0]].Cash=48001;h.PeriodicMonitoring();Check(h.accountsConfig[names[0]].Enabled,"must not stop above stop");h.accounts[names[0]].Positions.Add(new Position{MarketPosition=MarketPosition.Long});h.EvaluateEntrySignals(true,false);Check(h.entered=="","existing position blocks new account");scenarios+=3;
 }Console.WriteLine("PASS "+scenarios+" C# scenarios: exact targets, stops, next accounts, final exhaustion, boundaries and open-position guard.");}
}
'''
Path('reports/PropPassLimitsHarness.cs').write_text(stubs+account+body[:body.index('public static void Main')]+methods+'\n'+body[body.index('public static void Main'):],encoding='utf-8')
print('Generated harness from actual C# methods')

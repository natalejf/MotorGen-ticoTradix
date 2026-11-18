
using System;using System.Collections.Generic;using System.Linq;
enum MarketPosition { Flat,Long,Short } enum ConnectionStatus { Connected } enum Currency { UsDollar } enum AccountItem { CashValue,UnrealizedProfitLoss,RealizedProfitLoss } enum OrderAction { Buy,Sell }
class Order {} class Master {public string Name="NQ";} class Instrument {public string FullName="NQ DEC26";public Master MasterInstrument=new Master();}
class Position {public Instrument Instrument=new Instrument();public MarketPosition MarketPosition=MarketPosition.Flat;}
class Connection {public ConnectionStatus Status=ConnectionStatus.Connected;}
class Account {public string Name;public double Cash=50000,Open,Realized;public Connection Connection=new Connection();public List<Position> Positions=new List<Position>();public int Flattens;public double Get(AccountItem item,Currency c){return item==AccountItem.CashValue?Cash:item==AccountItem.UnrealizedProfitLoss?Open:Realized;}public void Flatten(Instrument[] symbols){Flattens++;Open=0;Positions.Clear();}}
class Harness {
        public class AccountRiskSettings
        {
            public string Name { get; set; }
            public bool Enabled { get; set; }
            public bool Locked { get; set; }
            public int Lots { get; set; }
            public double TpUsd { get; set; }
            public double SlUsd { get; set; }
            public double Target { get; set; }
            public double MaxLoss { get; set; }
            public double DailyProfitLimit { get; set; }
            public double DailyLossLimit { get; set; }
            public double StartBalance { get; set; }
            public double MaxUnrealizedPnl { get; set; }
            public bool ExitOnlyInProfit { get; set; }
            public bool TimeFilterEnabled { get; set; }
            public string StartTime { get; set; }
            public string EndTime { get; set; }

            // Estado Operativo en vivo
            public string Status { get; set; }
            public string Direction { get; set; }
            public double AvgEntryPrice { get; set; }
            public int TotalPositionSize { get; set; }
            public double UnifiedTpPrice { get; set; }
            public double UnifiedSlPrice { get; set; }

            // Estado de re-entrada (no serializados)
            public int LastEntryBar { get; set; }
            public DateTime LastEntryTime { get; set; }

            // Seguimiento diario para VPS y Consistencia (serializados)
            public double DailyStartBalance { get; set; }
            public string LastResetDate { get; set; }
            public string DailyStatus { get; set; }

            public double SessionRealizedPnl { get; set; }
            public int TradesWon,TradesLost,TradesClosed;

            // Comisiones
            public double CommissionPerContract { get; set; }
            public double DailyCommissions { get; set; }
            public bool NinjaTraderHandlesCommissions { get; set; }

            // Referencias a órdenes en ejecución (no serializadas)
            public Order TpOrder { get; set; }
            public Order SlOrder { get; set; }

            public AccountRiskSettings(string name)
            {
                Name = name;
                Enabled = false;
                Locked = false;
                Lots = 1;
                TpUsd = 1500.0;
                SlUsd = 2000.0;
                Target = 1500.0;
                MaxLoss = 2000.0;
                DailyProfitLimit = 1500.0;
                DailyLossLimit = 2000.0;
                StartBalance = 50000.0;
                ExitOnlyInProfit = false;
                TimeFilterEnabled = false;
                StartTime = "09:30";
                EndTime = "16:00";
                Status = "EN PROCESO";
                Direction = "FLAT";
                AvgEntryPrice = 0.0;
                TotalPositionSize = 0;
                UnifiedTpPrice = 0.0;
                UnifiedSlPrice = 0.0;
                LastEntryBar = -1;
                LastEntryTime = DateTime.MinValue;
                DailyStartBalance = 50000.0;
                LastResetDate = "";
                DailyStatus = "EN PROCESO";
                SessionRealizedPnl = 0.0;

                CommissionPerContract = 2.25;
                DailyCommissions = 0.0;
                NinjaTraderHandlesCommissions = false;
            }
        }


Dictionary<string,AccountRiskSettings> accountsConfig=new Dictionary<string,AccountRiskSettings>();Dictionary<string,Account> accounts=new Dictionary<string,Account>();HashSet<string> removedAccounts=new HashSet<string>();string[] groupAccounts;DateTime realtimeStartTime=DateTime.UtcNow.AddSeconds(-10);double lastRealtimePrice=20000;Instrument Instrument=new Instrument();string entered="";
Account GetAccountCached(string name){return accounts[name];}void Print(string text){}void SaveConfiguration(){}bool IsInTradingHours(AccountRiskSettings x){return true;}void ExecuteEntry(AccountRiskSettings x,AccountRiskSettings y,Account a,OrderAction action,string dir,double price){entered=a.Name;}void SyncTpSlOrders(Account a,AccountRiskSettings s,AccountRiskSettings e,Position p){}void QueueFlatten(Account a,Instrument[] symbols){a.Flatten(symbols);}void CancelTpSlOrders(Account a,AccountRiskSettings s){}void ResetTradingState(Account a,AccountRiskSettings s){s.Direction="FLAT";}
void Setup(string[] names,double target){accounts.Clear();accountsConfig.Clear();groupAccounts=names;entered="";foreach(string name in names){accounts[name]=new Account{Name=name};accountsConfig[name]=new AccountRiskSettings(name){Enabled=true,Target=target,MaxLoss=2000,DailyProfitLimit=target,DailyLossLimit=2000,StartBalance=50000,DailyStartBalance=50000,LastResetDate=DateTime.UtcNow.AddHours(-3).ToString("yyyyMMdd")};}}
static void Check(bool b,string message){if(!b)throw new Exception(message);}
        private void EvaluateEntrySignals(bool isLongSignal, bool isShortSignal)
        {
            lock (accountsConfig)
            {
                try
                {
                    if ((DateTime.UtcNow - realtimeStartTime).TotalSeconds < 5) return;

                    // Verificar que no haya cuentas activas antes de disparar señal
                    bool anyAccountActive = false;
                    foreach (var kvp in accountsConfig.OrderBy(p=>Array.IndexOf(groupAccounts,p.Key)))
                    {
                        AccountRiskSettings accSettings = kvp.Value;
                        if (removedAccounts.Contains(kvp.Key) || !accSettings.Enabled || accSettings.Status != "EN PROCESO" || accSettings.DailyStatus != "EN PROCESO") continue;

                        Account acc = GetAccountCached(accSettings.Name);
                        if (acc == null) continue;
                        bool isSimCheck = acc.Name.StartsWith("SIM", StringComparison.OrdinalIgnoreCase);
                        if (!isSimCheck && (acc.Connection == null || acc.Connection.Status != ConnectionStatus.Connected)) continue;

                        Position pos = acc.Positions.Cast<Position>().FirstOrDefault(p => p.Instrument.FullName.Equals(Instrument.FullName, StringComparison.OrdinalIgnoreCase) || p.Instrument.MasterInstrument.Name.Equals(Instrument.MasterInstrument.Name, StringComparison.OrdinalIgnoreCase));
                        bool isActive = (pos != null && pos.MarketPosition != MarketPosition.Flat);
                        if (isActive)
                        {
                            anyAccountActive = true;
                            accSettings.Direction = pos.MarketPosition == MarketPosition.Long ? "LONG" : "SHORT";
                        }
                        else
                        {
                            accSettings.Direction = "FLAT";
                        }
                    }

                    if (anyAccountActive) return;

                    if (!isLongSignal && !isShortSignal) return;

                    bool executedAny = false;

                    // Ejecutar entradas en cuentas configuradas
                    foreach (var kvp in accountsConfig.OrderBy(p=>Array.IndexOf(groupAccounts,p.Key)))
                    {
                        AccountRiskSettings accSettings = kvp.Value;
                        if (removedAccounts.Contains(kvp.Key) || !accSettings.Enabled || accSettings.Status != "EN PROCESO" || accSettings.DailyStatus != "EN PROCESO") continue;

                        if ((DateTime.UtcNow - accSettings.LastEntryTime).TotalMilliseconds < 1000) continue;

                        Account acc = GetAccountCached(accSettings.Name);
                        if (acc == null) continue;
                        bool isSimCheck2 = acc.Name.StartsWith("SIM", StringComparison.OrdinalIgnoreCase);
                        if (!isSimCheck2 && (acc.Connection == null || acc.Connection.Status != ConnectionStatus.Connected)) continue;

                        Position pos = acc.Positions.Cast<Position>().FirstOrDefault(p => p.Instrument.FullName.Equals(Instrument.FullName, StringComparison.OrdinalIgnoreCase) || p.Instrument.MasterInstrument.Name.Equals(Instrument.MasterInstrument.Name, StringComparison.OrdinalIgnoreCase));
                        bool isFlat = (pos == null || pos.MarketPosition == MarketPosition.Flat);

                        if (isFlat && IsInTradingHours(accSettings))
                        {
                            double price = lastRealtimePrice;

                            if (isLongSignal)
                            {
                                Print(string.Format("[CCC] SEÑAL COMPRA en cuenta {0} a precio {1}", accSettings.Name, price));
                                ExecuteEntry(accSettings, accSettings, acc, OrderAction.Buy, "LONG", price);
                                executedAny = true;
                                break; // Operar strictly UNA cuenta por vez (secuencial)
                            }
                            else if (isShortSignal)
                            {
                                Print(string.Format("[CCC] SEÑAL VENTA en cuenta {0} a precio {1}", accSettings.Name, price));
                                ExecuteEntry(accSettings, accSettings, acc, OrderAction.Sell, "SHORT", price);
                                executedAny = true;
                                break; // Operar estrictamente UNA cuenta por vez (secuencial)
                            }
                        }
                    }

                    if (!executedAny)
                    {
                        Print(string.Format("[CCC] Señal {0} detectada pero no se ejecutó (Verifique que la cuenta esté Habilitada en la casilla del Dashboard y en estado EN PROCESO).", isLongSignal ? "COMPRA" : "VENTA"));
                    }
                }
                catch (Exception ex)
                {
                    Print("[CCC] Error en señales: " + ex.Message);
                }
            }
        }
        private void PeriodicMonitoring()
        {
            try
            {
                double currentPrice = lastRealtimePrice > 0 ? lastRealtimePrice : 0.0;

                lock (accountsConfig)
                {
                    foreach (var kvp in accountsConfig.OrderBy(p=>Array.IndexOf(groupAccounts,p.Key)))
                    {
                        AccountRiskSettings settings = kvp.Value;
                        AccountRiskSettings eff = settings;
                        if (!groupAccounts.Contains(kvp.Key) || removedAccounts.Contains(kvp.Key) || settings.Status != "EN PROCESO") continue;

                        Account acc = GetAccountCached(settings.Name);
                        if (acc == null) continue;

                        // Autocuración y sincronización del estado de posición
                        Position pos = acc.Positions.Cast<Position>().FirstOrDefault(p => p.Instrument.FullName.Equals(Instrument.FullName, StringComparison.OrdinalIgnoreCase) || p.Instrument.MasterInstrument.Name.Equals(Instrument.MasterInstrument.Name, StringComparison.OrdinalIgnoreCase));
                        if(!settings.Enabled && (pos==null || pos.MarketPosition==MarketPosition.Flat))continue;
                        if (pos != null && pos.MarketPosition != MarketPosition.Flat)
                        {
                            if (settings.Direction == "FLATTENING") continue;

                            string currentPosDir = pos.MarketPosition == MarketPosition.Long ? "LONG" : "SHORT";
                            if (settings.Direction != currentPosDir || settings.TpOrder == null || settings.SlOrder == null)
                            {
                                Print(string.Format("[CCC] Sync: posición activa en {0} ({1}). Generando órdenes...", settings.Name, currentPosDir));
                                SyncTpSlOrders(acc, settings, eff, pos);
                            }
                        }
                        else if (settings.Direction != "FLAT" && settings.Direction != "FLATTENING")
                        {
                            ResetTradingState(acc, settings);
                        }

                        double cash = acc.Get(AccountItem.CashValue, Currency.UsDollar);
                        if (cash <= 0) cash = settings.StartBalance > 0 ? settings.StartBalance : 50000.0;
                        double unrealized = acc.Get(AccountItem.UnrealizedProfitLoss, Currency.UsDollar);
                        double equity = cash + unrealized;
                        double netEquity = equity;

                        // --- SIMULACIÓN DE DRAWDOWN EOD GENERAL ---
                        if (eff.MaxLoss > 0 && netEquity <= (settings.StartBalance - eff.MaxLoss))
                        {
                            settings.Status = "BURNED";
                            settings.Enabled = false;
                            Print(string.Format("[CCC] ✓ ¡CUENTA QUEMADA! (Drawdown Máximo EOD alcanzado en {0}). Equidad Neta: ${1:F2} <= Límite: ${2:F2}", settings.Name, netEquity, settings.StartBalance - eff.MaxLoss));
                            CancelTpSlOrders(acc, settings);
                            QueueFlatten(acc,new[] { Instrument });
                            SaveConfiguration();
                            continue;
                        }

                        // --- REGLAS DIARIAS ---
                        string todayStr = DateTime.UtcNow.AddHours(-3).ToString("yyyyMMdd");
                        if (settings.LastResetDate != todayStr)
                        {
                            if (settings.Status != "BURNED")
                            {
                                settings.StartBalance = cash;
                            }
                            
                            settings.DailyStartBalance = cash;
                            settings.LastResetDate = todayStr;
                            settings.DailyStatus = "EN PROCESO";
                            settings.DailyCommissions = 0.0;
                            Print(string.Format("[CCC] VPS: Nuevo día ({0}) para {1}. Balance Inicial: {2:F2} | Límite Trailing EOD: {3:F2}", todayStr, settings.Name, settings.DailyStartBalance, settings.StartBalance - eff.MaxLoss));
                            SaveConfiguration();
                        }

                        double realPnlAcc = acc.Get(AccountItem.RealizedProfitLoss, Currency.UsDollar);
                        double dailyPnlFloating = equity - settings.DailyStartBalance;
                        double dailyPnlRealized = cash - settings.DailyStartBalance;
                        if (dailyPnlRealized <= 0 && settings.SessionRealizedPnl > 0)
                        {
                            dailyPnlRealized = settings.SessionRealizedPnl;
                        }
                        if (dailyPnlRealized <= 0 && realPnlAcc > 0)
                        {
                            dailyPnlRealized = realPnlAcc;
                        }

                        // Límite de Pérdida Diaria
                        if (settings.DailyStatus == "EN PROCESO" && eff.DailyLossLimit > 0 && (dailyPnlFloating <= -eff.DailyLossLimit || (settings.SessionRealizedPnl <= -eff.DailyLossLimit && settings.SessionRealizedPnl != 0)))
                        {
                            settings.DailyStatus = "LOSS_LIMIT_REACHED";
                            settings.Enabled = false;
                            Print(string.Format("[CCC] ❌ LÍMITE PÉRDIDA DIARIA ALCANZADO en {0}. PnL: ${1:F2}. Cuenta deshabilitada, pasando a la siguiente.", settings.Name, dailyPnlFloating));
                            CancelTpSlOrders(acc, settings);
                            QueueFlatten(acc,new[] { Instrument });
                            ResetTradingState(acc, settings);
                            SaveConfiguration();
                            continue;
                        }

                        // Objetivo de Ganancia Diaria (Max Profit / Target)
                        if (settings.DailyStatus == "EN PROCESO" && ((eff.DailyProfitLimit > 0 && (dailyPnlRealized >= eff.DailyProfitLimit || dailyPnlFloating >= eff.DailyProfitLimit)) || (eff.Target > 0 && (dailyPnlRealized >= eff.Target || dailyPnlFloating >= eff.Target))))
                        {
                            settings.DailyStatus = "TARGET_REACHED";
                            settings.Status = "PASS";
                            settings.Enabled = false;
                            Print(string.Format("[CCC] ✓ OBJETIVO DE GANANCIA (MAX PROFIT) ALCANZADO en {0}. PnL Realizado: ${1:F2}. Cuenta deshabilitada, pasando a la siguiente.", settings.Name, dailyPnlRealized));
                            CancelTpSlOrders(acc, settings);
                            QueueFlatten(acc,new[] { Instrument });
                            ResetTradingState(acc, settings);
                            SaveConfiguration();
                            continue;
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Print("[CCC] Error en PeriodicMonitoring: " + ex.Message);
            }
        }
public static void Main(){var h=new Harness();int scenarios=0;foreach(var names in new[]{new[]{"Sim101","SimAccount2","SimAccount3","SimAccount4","SimAccount5"},new[]{"SimAccount6","SimAccount7","SimAccount8","SimAccount9","SimAccount10"}}){double target=names[0]=="Sim101"?1500:150;
 foreach(bool loss in new[]{false,true}){h.Setup(names,target);for(int i=0;i<names.Length;i++){var a=h.accounts[names[i]];var setting=h.accountsConfig[names[i]];a.Cash=50000+(loss?-2000:target);h.PeriodicMonitoring();Check(!setting.Enabled,"limit must disable account");Check(setting.Status==(loss?"BURNED":"PASS"),"terminal status");Check(a.Flattens==1,"flatten on limit");h.entered="";h.EvaluateEntrySignals(true,false);Check(h.entered==(i+1<names.Length?names[i+1]:""),"next account selection");scenarios++;}}
 h.Setup(names,target);h.accounts[names[0]].Cash=50000+target-1;h.PeriodicMonitoring();Check(h.accountsConfig[names[0]].Enabled,"must not pass below target");h.accounts[names[0]].Cash=48001;h.PeriodicMonitoring();Check(h.accountsConfig[names[0]].Enabled,"must not stop above stop");h.accounts[names[0]].Positions.Add(new Position{MarketPosition=MarketPosition.Long});h.EvaluateEntrySignals(true,false);Check(h.entered=="","existing position blocks new account");scenarios+=3;
 }Console.WriteLine("PASS "+scenarios+" C# scenarios: exact targets, stops, next accounts, final exhaustion, boundaries and open-position guard.");}
}

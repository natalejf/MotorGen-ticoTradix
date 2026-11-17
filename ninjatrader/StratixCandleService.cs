using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Text;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
namespace NinjaTrader.NinjaScript.AddOns {
 public class StratixCandleService : AddOnBase {
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

        private readonly object serviceGate=new object();
        private System.Threading.Timer serviceTimer;
        private readonly string instance=Guid.NewGuid().ToString("N");
        private string connectionId="",connectionKey="",lastAck="",ackStatus="",ackDetail="";
        private bool masterTradingEnabled;
        private int pulseBusy,monitorBusy,timeframeMinutes=1;
        private DateTime lastSuccess=DateTime.UtcNow,lastTick=DateTime.MinValue;
        private long candleSlot=-1;
        private double candleOpen,candleClose;
        private int CurrentBar;
        private Instrument Instrument;
        private string[] groupAccounts=new string[0];
        private DateTime realtimeStartTime=DateTime.UtcNow;
        private double lastRealtimePrice;
        private readonly string[] allowedAccounts={"Sim101","SimAccount2","SimAccount3","SimAccount4","SimAccount5","SimAccount6","SimAccount7","SimAccount8","SimAccount9","SimAccount10"};
        private readonly List<string> serviceEvents=new List<string>();
        private Dictionary<string,AccountRiskSettings> accountsConfig=new Dictionary<string,AccountRiskSettings>();
        private HashSet<string> removedAccounts=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private AccountRiskSettings globalConfig=new AccountRiskSettings("GLOBAL");
        private readonly object fileLock=new object();
        private readonly Dictionary<string,Account> accountCache=new Dictionary<string,Account>();
        private string configFilePath;
        private void Print(string text) {
            lock(serviceEvents) {serviceEvents.Add(DateTime.UtcNow.ToString("HH:mm:ss")+" · "+text);if(serviceEvents.Count>40)serviceEvents.RemoveAt(0);}
            NinjaTrader.Code.Output.Process("[Stratix Web] "+text,PrintTo.OutputTab1);
        }
        private void RemoveDrawObject(string tag) { }
        private void NoChart(params object[] args) { }
        private static string J(string text) {return "\""+(text??"").Replace("\\","\\\\").Replace("\"","\\\"").Replace("\n","\\n").Replace("\r","\\r").Replace("\t","\\t")+"\"";}
        private static string N(double number) {return (double.IsNaN(number)||double.IsInfinity(number)?0:number).ToString(System.Globalization.CultureInfo.InvariantCulture);}
        private static string B(bool value) {return value?"true":"false";}
        protected override void OnStateChange() {
            if(State==State.SetDefaults) {Name="StratixCandleService";Description="Candle Controller: gestión web sin panel ni gráfico; simulación.";}
            else if(State==State.Active) {
                string root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Stratix","NinjaTrader");
                Directory.CreateDirectory(root);configFilePath=Path.Combine(root,"CandleServiceConfig.txt");
                string key=Path.Combine(root,"CandleBridge.key");
                if(File.Exists(key)) {string[] lines=File.ReadAllLines(key);if(lines.Length>=2){connectionId=lines[0].Trim();connectionKey=lines[1].Trim();}}
                LoadConfiguration();foreach(var item in accountsConfig.Values)item.Enabled=false;
                string scope=Path.Combine(root,"CandleServiceScope.txt");
                if(File.Exists(scope)) {
                    try {
                        string[] saved=File.ReadAllLines(scope);
                        if(saved.Length>=3) {
                            Instrument=NinjaTrader.Cbi.Instrument.GetInstrument(saved[0]);timeframeMinutes=Math.Max(1,Math.Min(60,int.Parse(saved[1])));
                            groupAccounts=saved[2].Split(',').Where(a=>allowedAccounts.Contains(a)).ToArray();
                            if(Instrument!=null) {
                                Instrument.MarketData.Update+=ServiceMarketData;
                                foreach(string name in groupAccounts) {
                                    Account acc=GetAccountCached(name);AccountRiskSettings setting;
                                    if(acc==null||!accountsConfig.TryGetValue(name,out setting))continue;
                                    var working=acc.Orders.Cast<Order>().Where(o=>o.Instrument.FullName==Instrument.FullName && (o.OrderState==OrderState.Working||o.OrderState==OrderState.Accepted||o.OrderState==OrderState.Submitted||o.OrderState==OrderState.PartFilled)).ToList();
                                    setting.TpOrder=working.FirstOrDefault(o=>o.Name=="TP_"+name);setting.SlOrder=working.FirstOrDefault(o=>o.Name=="SL_"+name);
                                    setting.Enabled=acc.Positions.Cast<Position>().Any(p=>p.Instrument.FullName==Instrument.FullName&&p.MarketPosition!=MarketPosition.Flat)||working.Any(o=>o.Name=="EntryLong"||o.Name=="EntryShort");
                                }
                            }
                        }
                    }catch(Exception ex){Print("No se pudo recuperar el alcance anterior: "+ex.Message);}
                }
                masterTradingEnabled=false;
                lock(Account.All) foreach(var acc in Account.All) if(allowedAccounts.Contains(acc.Name))acc.ExecutionUpdate+=OnGlobalExecutionUpdate;
                serviceTimer=new System.Threading.Timer(ServiceTick,null,1000,1000);
                Print("Servicio iniciado sin interfaz nativa. Configuración y grupos se gestionan desde la web.");
            } else if(State==State.Terminated) {
                masterTradingEnabled=false;if(serviceTimer!=null){serviceTimer.Dispose();serviceTimer=null;}
                if(Instrument!=null)Instrument.MarketData.Update-=ServiceMarketData;
                lock(Account.All) foreach(var acc in Account.All)acc.ExecutionUpdate-=OnGlobalExecutionUpdate;
            }
        }
        private void ServiceMarketData(object sender,MarketDataEventArgs e) {
            if(State!=State.Active || e.MarketDataType!=MarketDataType.Last || e.Price<=0)return;
            lock(serviceGate) {
                lastTick=DateTime.UtcNow;lastRealtimePrice=e.Price;
                long slot=lastTick.Ticks/(TimeSpan.TicksPerMinute*timeframeMinutes);
                if(candleSlot<0){candleSlot=slot;candleOpen=candleClose=e.Price;return;}
                if(slot==candleSlot){candleClose=e.Price;return;}
                double open=candleOpen,close=candleClose;candleSlot=slot;candleOpen=candleClose=e.Price;CurrentBar++;
                if((DateTime.UtcNow-lastSuccess).TotalSeconds>10)masterTradingEnabled=false;
                if(CurrentBar>=2 && masterTradingEnabled) {
                    Print("Vela cerrada "+Instrument.FullName+" M"+timeframeMinutes+" O="+N(open)+" C="+N(close));
                    EvaluateEntrySignals(close>open,close<open);
                }
            }
        }
        private void ServiceTick(object unused) {
            if(State!=State.Active || System.Threading.Interlocked.CompareExchange(ref monitorBusy,1,0)!=0)return;
            string payload="";
            try {
                lock(serviceGate) {
                    if((DateTime.UtcNow-lastSuccess).TotalSeconds>10)masterTradingEnabled=false;
                    if(Instrument!=null)PeriodicMonitoring();
                    if(masterTradingEnabled && !accountsConfig.Values.Any(s=>s.Enabled&&s.Status=="EN PROCESO"&&s.DailyStatus=="EN PROCESO")) {
                        masterTradingEnabled=false;Print("Entradas pausadas: todas las cuentas del grupo alcanzaron sus límites o quedaron inactivas.");
                    }
                    var rows=new List<string>();int quantity=0;
                    foreach(string name in allowedAccounts) {
                        Account acc=GetAccountCached(name);if(acc==null)continue;
                        Position pos=Instrument==null?null:acc.Positions.Cast<Position>().FirstOrDefault(p=>p.Instrument.FullName==Instrument.FullName && p.MarketPosition!=MarketPosition.Flat);
                        int qty=pos==null?0:pos.Quantity;quantity+=qty;
                        AccountRiskSettings settings;accountsConfig.TryGetValue(name,out settings);
                        var working=acc.Orders.Cast<Order>().Where(o=>Instrument!=null&&o.Instrument.FullName==Instrument.FullName&&(o.OrderState==OrderState.Working||o.OrderState==OrderState.Accepted||o.OrderState==OrderState.Submitted||o.OrderState==OrderState.PartFilled)).Select(o=>"{\"name\":"+J(o.Name)+",\"type\":"+J(o.OrderType.ToString())+",\"state\":"+J(o.OrderState.ToString())+",\"quantity\":"+o.Quantity+",\"limit\":"+N(o.LimitPrice)+",\"stop\":"+N(o.StopPrice)+"}");
                        double cash=acc.Get(AccountItem.CashValue,Currency.UsDollar),open=acc.Get(AccountItem.UnrealizedProfitLoss,Currency.UsDollar);
                        double daily=settings==null?acc.Get(AccountItem.RealizedProfitLoss,Currency.UsDollar)+open:cash+open-settings.DailyStartBalance-(settings.NinjaTraderHandlesCommissions?0:settings.DailyCommissions);
                        rows.Add("{\"name\":"+J(name)+",\"enabled\":"+B(settings!=null&&settings.Enabled)+",\"position_quantity\":"+qty+
                            ",\"direction\":"+J(pos==null?"Flat":pos.MarketPosition.ToString())+",\"balance\":"+N(acc.Get(AccountItem.CashValue,Currency.UsDollar))+
                            ",\"unrealized\":"+N(acc.Get(AccountItem.UnrealizedProfitLoss,Currency.UsDollar))+
                            ",\"status\":"+J(settings==null?"SIN CONFIGURAR":settings.Status)+",\"daily_status\":"+J(settings==null?"":settings.DailyStatus)+
                            ",\"lots\":"+(settings==null?1:settings.Lots)+",\"tp_usd\":"+N(settings==null?100:settings.TpUsd)+",\"sl_usd\":"+N(settings==null?100:settings.SlUsd)+"}");
                        rows[rows.Count-1]=rows[rows.Count-1].TrimEnd('}')+",\"working_orders\":["+string.Join(",",working)+"],\"daily_pnl\":"+N(daily)+
                            ",\"daily_loss_limit\":"+N(settings==null?0:settings.DailyLossLimit)+",\"daily_profit_limit\":"+N(settings==null?0:settings.DailyProfitLimit)+
                            ",\"wins\":"+(settings==null?0:settings.TradesWon)+",\"losses\":"+(settings==null?0:settings.TradesLost)+",\"closed_trades\":"+(settings==null?0:settings.TradesClosed)+"}";
                    }
                    string events;lock(serviceEvents)events=string.Join(",",serviceEvents.Select(J));
                    payload="{\"version\":\"1.1-ten-sims\",\"kind\":\"candle_service_v1\",\"account\":\"Sim101\",\"instance\":"+J(instance)+
                        ",\"realtime\":true,\"account_available\":"+B(rows.Count>0)+",\"master_enabled\":"+B(masterTradingEnabled)+
                        ",\"symbol\":"+J(Instrument==null?"":Instrument.FullName)+",\"timeframe_minutes\":"+timeframeMinutes+
                        ",\"data_ready\":"+B(Instrument!=null&&(DateTime.UtcNow-lastTick).TotalSeconds<15)+",\"closed_bars\":"+CurrentBar+
                        ",\"next_account\":"+J(groupAccounts.FirstOrDefault(n=>accountsConfig.ContainsKey(n)&&accountsConfig[n].Enabled&&accountsConfig[n].Status=="EN PROCESO"&&accountsConfig[n].DailyStatus=="EN PROCESO"))+
                        ",\"position_quantity\":"+quantity+",\"accounts\":["+string.Join(",",rows)+"],\"events\":["+events+"]"+
                        ",\"last_ack\":"+J(lastAck)+",\"ack_status\":"+J(ackStatus)+",\"ack_detail\":"+J(ackDetail)+"}";
                }
                if(string.IsNullOrEmpty(connectionId)||string.IsNullOrEmpty(connectionKey))return;
                if(System.Threading.Interlocked.CompareExchange(ref pulseBusy,1,0)!=0)return;
                System.Threading.Tasks.Task.Run(()=>SendPulse(payload));
            } catch(Exception ex) {masterTradingEnabled=false;Print("Error de servicio: "+ex.Message);}
            finally {System.Threading.Interlocked.Exchange(ref monitorBusy,0);}
        }
        private void SendPulse(string payload) {
            try {
                var request=(System.Net.HttpWebRequest)System.Net.WebRequest.Create("http://127.0.0.1:8000/api/ninja/bridge/"+Uri.EscapeDataString(connectionId)+"/pulse");
                request.Method="POST";request.ContentType="application/json";request.Timeout=2000;request.ReadWriteTimeout=2000;
                request.Headers["X-Stratix-Key"]=connectionKey;
                byte[] bytes=Encoding.UTF8.GetBytes(payload);request.ContentLength=bytes.Length;
                using(var stream=request.GetRequestStream())stream.Write(bytes,0,bytes.Length);
                string command;using(var response=request.GetResponse())using(var reader=new StreamReader(response.GetResponseStream()))command=reader.ReadToEnd();
                lock(serviceGate){if(State!=State.Active)return;lastSuccess=DateTime.UtcNow;if(!string.IsNullOrWhiteSpace(command))ApplyServiceCommand(command);}
            }catch {lock(serviceGate)masterTradingEnabled=false;}
            finally{System.Threading.Interlocked.Exchange(ref pulseBusy,0);}
        }
        private void ApplyServiceCommand(string command) {
            string[] parts=command.Split('|');if(parts.Length<4||parts[0]==lastAck)return;
            lastAck=parts[0];ackStatus="REJECTED";
            try {
                if(parts[1]!=instance || (DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds>double.Parse(parts[2],System.Globalization.CultureInfo.InvariantCulture))throw new Exception("Instancia incorrecta o comando vencido");
                string action=parts[3];
                var values=new Dictionary<string,string>();foreach(string part in parts.Skip(4)){int split=part.IndexOf('=');if(split>0)values[part.Substring(0,split)]=part.Substring(split+1);}
                if(action=="pause")masterTradingEnabled=false;
                else if(action=="account_pause"||action=="account_resume") {
                    string name=values["account"];AccountRiskSettings s;
                    if(!groupAccounts.Contains(name)||!accountsConfig.TryGetValue(name,out s))throw new Exception("Cuenta fuera del grupo aplicado");
                    if(action=="account_resume"&&(s.Status!="EN PROCESO"||s.DailyStatus!="EN PROCESO"))throw new Exception("Cuenta bloqueada por límites; reinicia su seguimiento explícitamente");
                    s.Enabled=action=="account_resume";SaveConfiguration();
                }
                else if(action=="close-stop") {
                    masterTradingEnabled=false;
                    string[] targets=values["accounts"].Split(',');if(targets.Any(n=>!allowedAccounts.Contains(n)))throw new Exception("Cuenta no autorizada");
                    Instrument target=NinjaTrader.Cbi.Instrument.GetInstrument(values["symbol"]);if(target==null)throw new Exception("Instrumento desconocido");
                    foreach(string name in targets) {
                        Account acc=GetAccountCached(name);AccountRiskSettings s;if(accountsConfig.TryGetValue(name,out s))s.Enabled=false;
                        if(acc!=null)acc.Flatten(new[]{target});
                    }
                    SaveConfiguration();
                }
                else if(action=="configure" || action=="reset") {
                    if(masterTradingEnabled)throw new Exception("Pausa primero las entradas");
                    foreach(string name in allowedAccounts) {
                        Account acc=GetAccountCached(name);if(acc!=null && acc.Positions.Cast<Position>().Any(p=>p.MarketPosition!=MarketPosition.Flat))throw new Exception("Configura con las cuentas simuladas sin posiciones");
                        if(acc!=null && acc.Orders.Cast<Order>().Any(o=>o.OrderState==OrderState.Working||o.OrderState==OrderState.Accepted||o.OrderState==OrderState.Submitted||o.OrderState==OrderState.PartFilled))throw new Exception("Hay órdenes pendientes en la cuenta simulada");
                    }
                    string[] selected=values["accounts"].Split(',');if(selected.Length==0||selected.Any(a=>!allowedAccounts.Contains(a)||GetAccountCached(a)==null))throw new Exception("Solo cuentas simuladas autorizadas y disponibles");
                    Instrument next=NinjaTrader.Cbi.Instrument.GetInstrument(values["symbol"]);if(next==null)throw new Exception("Instrumento no disponible");
                    int minutes=int.Parse(values["timeframe_minutes"]);if(minutes<1||minutes>60)throw new Exception("Temporalidad inválida");
                    if(Instrument==null||Instrument.FullName!=next.FullName||minutes!=timeframeMinutes) {
                        if(Instrument!=null)Instrument.MarketData.Update-=ServiceMarketData;
                        Instrument=next;timeframeMinutes=minutes;candleSlot=-1;CurrentBar=0;lastTick=DateTime.MinValue;
                        Instrument.MarketData.Update+=ServiceMarketData;
                    }
                    Func<string,double> number=name=>double.Parse(values[name],System.Globalization.CultureInfo.InvariantCulture);
                    groupAccounts=selected;
                    lock(accountsConfig) {
                        foreach(var settings in accountsConfig.Values)settings.Enabled=false;
                        foreach(string name in selected) {
                            AccountRiskSettings s;if(!accountsConfig.TryGetValue(name,out s)){s=new AccountRiskSettings(name);accountsConfig[name]=s;}
                            Func<string,double> perAccount=field=>values.ContainsKey(field+":"+name)?double.Parse(values[field+":"+name],System.Globalization.CultureInfo.InvariantCulture):number(field);
                            s.Lots=(int)perAccount("lots");s.TpUsd=perAccount("tp_usd");s.SlUsd=perAccount("sl_usd");s.Target=number("target");s.MaxLoss=number("max_loss");
                            s.DailyProfitLimit=perAccount("daily_profit_limit");s.DailyLossLimit=perAccount("daily_loss_limit");
                            s.StartBalance=number("start_balance");s.TimeFilterEnabled=values["time_filter"]=="1";s.StartTime=values["start_time"];s.EndTime=values["end_time"];
                            s.Enabled=!values.ContainsKey("enabled:"+name)||values["enabled:"+name]!="0";s.Locked=true;removedAccounts.Remove(name);
                            if(action=="reset") {
                                s.Status="EN PROCESO";s.Direction="FLAT";s.DailyStatus="EN PROCESO";s.SessionRealizedPnl=0;s.DailyCommissions=0;
                                s.DailyStartBalance=GetAccountCached(name).Get(AccountItem.CashValue,Currency.UsDollar);
                                s.LastResetDate=DateTime.UtcNow.AddHours(-3).ToString("yyyyMMdd");s.LastEntryBar=-1;s.LastEntryTime=DateTime.MinValue;
                                s.TradesClosed=s.TradesWon=s.TradesLost=0;
                            }
                        }
                    }
                    SaveConfiguration();
                    File.WriteAllLines(Path.Combine(Path.GetDirectoryName(configFilePath),"CandleServiceScope.txt"),new[]{Instrument.FullName,timeframeMinutes.ToString(),string.Join(",",groupAccounts)});
                } else if(action=="start") {
                    if(Instrument==null||(DateTime.UtcNow-lastTick).TotalSeconds>15)throw new Exception("Sin datos recientes del instrumento");
                    if(!accountsConfig.Values.Any(s=>s.Enabled&&s.Status=="EN PROCESO"&&s.DailyStatus=="EN PROCESO"))throw new Exception("No hay cuentas habilitadas dentro de sus límites");
                    masterTradingEnabled=true;
                } else throw new Exception("Acción desconocida");
                ackStatus="APPLIED";ackDetail=action;Print("Comando web confirmado: "+action);
            }catch(Exception ex){masterTradingEnabled=false;ackDetail=ex.Message;Print("Comando rechazado: "+ex.Message);}
        }
        private Account GetAccountCached(string name)
        {
            if (string.IsNullOrEmpty(name) || !allowedAccounts.Contains(name)) return null;
            lock (accountCache)
            {
                Account acc;
                if (accountCache.TryGetValue(name, out acc))
                {
                    return acc;
                }
            }
            lock (Account.All)
            {
                Account acc = Account.All.FirstOrDefault(a => a.Name.Equals(name, StringComparison.OrdinalIgnoreCase));
                if (acc != null)
                {
                    lock (accountCache)
                    {
                        accountCache[name] = acc;
                    }
                    return acc;
                }
            }
            return null;
        }

        // =====================================================================
        //  SISTEMA DE PERSISTENCIA TXT
        // =====================================================================
        private void SaveConfiguration()
        {
            List<string> lines = new List<string>();
            lock (accountsConfig)
            {
                try
                {
                    // Guardar la configuración global en la primera línea
                    string globalLine = string.Format("GLOBAL|0|0|{0}|{1}|{2}|0|0|0|{3}|{4}|{5}|{6}|{7}|{8}|{9}|0|0|0|0|0|{10}|0|{11}|{12}|0",
                        globalConfig.Lots,
                        globalConfig.TpUsd.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        globalConfig.SlUsd.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        globalConfig.Target.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        globalConfig.MaxLoss.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        globalConfig.DailyProfitLimit.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        globalConfig.StartBalance.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        globalConfig.TimeFilterEnabled ? "1" : "0",
                        globalConfig.StartTime,
                        globalConfig.EndTime,
                        globalConfig.ExitOnlyInProfit ? "1" : "0",
                        globalConfig.DailyLossLimit.ToString(System.Globalization.CultureInfo.InvariantCulture),
                        globalConfig.CommissionPerContract.ToString(System.Globalization.CultureInfo.InvariantCulture)
                    );
                    lines.Add(globalLine);

                    foreach (var kvp in accountsConfig)
                    {
                        AccountRiskSettings s = kvp.Value;
                        
                        string line = string.Format("{0}|{1}|{2}|{3}|{4}|{5}|0|0|0|{6}|{7}|{8}|{9}|{10}|{11}|{12}|{13}|{14}|{15}|{16}|{17}|{18}|0|0|0|0|0|0|{19}|0",
                            s.Name,
                            s.Enabled ? "1" : "0",
                            s.Locked ? "1" : "0",
                            s.Lots,
                            s.TpUsd.ToString(System.Globalization.CultureInfo.InvariantCulture),
                            s.SlUsd.ToString(System.Globalization.CultureInfo.InvariantCulture),
                            s.Target.ToString(System.Globalization.CultureInfo.InvariantCulture),
                            s.MaxLoss.ToString(System.Globalization.CultureInfo.InvariantCulture),
                            s.DailyProfitLimit.ToString(System.Globalization.CultureInfo.InvariantCulture),
                            s.StartBalance.ToString(System.Globalization.CultureInfo.InvariantCulture),
                            s.TimeFilterEnabled ? "1" : "0",
                            s.StartTime,
                            s.EndTime,
                            s.Status,
                            s.DailyStartBalance.ToString(System.Globalization.CultureInfo.InvariantCulture),
                            s.LastResetDate,
                            s.DailyStatus,
                            s.DailyLossLimit.ToString(System.Globalization.CultureInfo.InvariantCulture),
                            s.ExitOnlyInProfit ? "1" : "0",
                            s.CommissionPerContract.ToString(System.Globalization.CultureInfo.InvariantCulture)
                        );
                        lines.Add(line);
                    }

                    foreach (string remAcc in removedAccounts)
                    {
                        lines.Add("REMOVED|" + remAcc);
                    }
                }
                catch (Exception ex)
                {
                    Print("[CCC] Error serializando config: " + ex.Message);
                    return;
                }
            }

            System.Threading.Tasks.Task.Run(() =>
            {
                lock (fileLock)
                {
                    try
                    {
                        File.WriteAllLines(configFilePath, lines);
                    }
                    catch (Exception) { }
                }
            });
        }

        private void LoadConfiguration()
        {
            lock (accountsConfig)
            {
                try
                {
                    if (!File.Exists(configFilePath)) return;
                    string[] lines = File.ReadAllLines(configFilePath);
                    foreach (string line in lines)
                    {
                        if (string.IsNullOrEmpty(line)) continue;
                        string[] parts = line.Split('|');
                        if (parts.Length < 2) continue;

                        string name = parts[0];
                        if (name.Equals("REMOVED", StringComparison.OrdinalIgnoreCase))
                        {
                            if (parts.Length > 1 && !string.IsNullOrEmpty(parts[1]))
                            {
                                removedAccounts.Add(parts[1]);
                            }
                            continue;
                        }
                        if (parts.Length < 16) continue;

                        if (name.Equals("GLOBAL", StringComparison.OrdinalIgnoreCase))
                        {
                            int valInt;
                            double valDouble;

                            if (parts.Length > 3 && int.TryParse(parts[3], out valInt))
                                globalConfig.Lots = valInt;
                            if (parts.Length > 4 && double.TryParse(parts[4], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out valDouble))
                                globalConfig.TpUsd = valDouble;
                            if (parts.Length > 5 && double.TryParse(parts[5], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out valDouble))
                                globalConfig.SlUsd = valDouble;

                            if (parts.Length > 9 && double.TryParse(parts[9], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out valDouble))
                                globalConfig.Target = valDouble;
                            if (parts.Length > 10 && double.TryParse(parts[10], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out valDouble))
                                globalConfig.MaxLoss = valDouble;
                            if (parts.Length > 11 && double.TryParse(parts[11], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out valDouble))
                                globalConfig.DailyProfitLimit = valDouble;
                            if (parts.Length > 12 && double.TryParse(parts[12], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out valDouble))
                                globalConfig.StartBalance = valDouble;

                            globalConfig.TimeFilterEnabled = parts.Length > 13 && parts[13] == "1";
                            if (parts.Length > 14) globalConfig.StartTime = parts[14];
                            if (parts.Length > 15) globalConfig.EndTime = parts[15];

                            if (parts.Length > 21) globalConfig.ExitOnlyInProfit = parts[21] == "1";

                            if (parts.Length > 23 && double.TryParse(parts[23], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out valDouble))
                                globalConfig.DailyLossLimit = valDouble;
                            else
                                globalConfig.DailyLossLimit = globalConfig.MaxLoss;

                            if (parts.Length > 24 && double.TryParse(parts[24], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out valDouble))
                                globalConfig.CommissionPerContract = valDouble;
                            else
                                globalConfig.CommissionPerContract = 2.25;
                        }
                        else
                        {
                            string statusRead = parts.Length > 16 ? parts[16] : "EN PROCESO";
                            if (statusRead != "PASS" && statusRead != "BURNED" && statusRead != "EN PROCESO")
                            {
                                statusRead = "EN PROCESO";
                            }

                            double dailyStartBal = 50000.0;
                            if (parts.Length > 17) double.TryParse(parts[17], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out dailyStartBal);

                            string lastReset = parts.Length > 18 ? parts[18] : "";
                            string dailyStat = parts.Length > 19 ? parts[19] : "EN PROCESO";

                            double dailyLossLim = 2000.0;
                            if (parts.Length > 20) double.TryParse(parts[20], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out dailyLossLim);

                            bool exitOnlyProfit = false;
                            if (parts.Length > 21) exitOnlyProfit = parts[21] == "1";

                            double commPerContract = 2.25;
                            if (parts.Length > 28) double.TryParse(parts[28], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out commPerContract);

                            AccountRiskSettings s = new AccountRiskSettings(name);

                            s.Enabled = false; // Seguridad: Cuentas inician deshabilitadas hasta ser activadas manualmente por el usuario
                            if (parts.Length > 2) s.Locked = parts[2] == "1";
                            
                            int intTmp;
                            double dblTmp;
                            if (parts.Length > 3 && int.TryParse(parts[3], out intTmp)) s.Lots = intTmp;
                            if (parts.Length > 4 && double.TryParse(parts[4], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out dblTmp)) s.TpUsd = dblTmp;
                            if (parts.Length > 5 && double.TryParse(parts[5], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out dblTmp)) s.SlUsd = dblTmp;
                            
                            if (parts.Length > 9 && double.TryParse(parts[9], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out dblTmp)) s.Target = dblTmp;
                            if (parts.Length > 10 && double.TryParse(parts[10], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out dblTmp)) s.MaxLoss = dblTmp;
                            if (parts.Length > 11 && double.TryParse(parts[11], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out dblTmp)) s.DailyProfitLimit = dblTmp;
                            if (parts.Length > 12 && double.TryParse(parts[12], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out dblTmp)) s.StartBalance = dblTmp;

                            s.TimeFilterEnabled = parts.Length > 13 && parts[13] == "1";
                            if (parts.Length > 14) s.StartTime = parts[14];
                            if (parts.Length > 15) s.EndTime = parts[15];

                            s.Status = statusRead;
                            s.DailyStartBalance = dailyStartBal;
                            s.LastResetDate = lastReset;
                            s.DailyStatus = dailyStat;
                            s.DailyLossLimit = dailyLossLim;
                            s.ExitOnlyInProfit = exitOnlyProfit;
                            s.CommissionPerContract = commPerContract;

                            accountsConfig[name] = s;
                        }
                    }

                    foreach (string rem in removedAccounts.ToList())
                    {
                        if (accountsConfig.ContainsKey(rem))
                        {
                            accountsConfig.Remove(rem);
                        }
                    }
                }
                catch (Exception ex)
                {
                    Print("[CCC] Error cargando config: " + ex.Message);
                }
            }
        }

        // =====================================================================
        //  SISTEMA DE INICIALIZACIÓN
        // =====================================================================
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

        private void ExecuteEntry(AccountRiskSettings settings, AccountRiskSettings eff, Account acc, OrderAction action, string direction, double price)
        {
            if (!allowedAccounts.Contains(acc.Name)) throw new Exception("Solo simulación autorizada");
            settings.Direction = direction;
            settings.AvgEntryPrice = price;
            settings.TotalPositionSize = eff.Lots;
            settings.LastEntryBar = CurrentBar;
            settings.LastEntryTime = DateTime.UtcNow;
            settings.MaxUnrealizedPnl = 0.0;

            double ptVal = Instrument.MasterInstrument.PointValue;
            double slDelta = eff.SlUsd / (eff.Lots * ptVal);
            double tpDelta = eff.TpUsd / (eff.Lots * ptVal);

            if (direction == "LONG")
            {
                settings.UnifiedSlPrice = price - slDelta;
                settings.UnifiedTpPrice = price + tpDelta;
                SubmitOrderToAccount(acc, action, OrderType.Market, eff.Lots, 0.0, "EntryLong");
            }
            else
            {
                settings.UnifiedSlPrice = price + slDelta;
                settings.UnifiedTpPrice = price - tpDelta;
                SubmitOrderToAccount(acc, action, OrderType.Market, eff.Lots, 0.0, "EntryShort");
            }
            SaveConfiguration();
        }

        private void SubmitOrderToAccount(Account acc, OrderAction action, OrderType type, int qty, double price, string name)
        {
            try
            {
                if (acc == null)
                {
                    Print("[CCC] Error enviando orden: La cuenta especificada es null.");
                    return;
                }
                if (Instrument == null)
                {
                    Print("[CCC] Error enviando orden: El Instrumento de la estrategia es null.");
                    return;
                }
                if (!acc.Name.StartsWith("SIM", StringComparison.OrdinalIgnoreCase) && (acc.Connection == null || acc.Connection.Status != ConnectionStatus.Connected))
                {
                    Print("[CCC] Error enviando orden: La cuenta " + acc.Name + " no está conectada.");
                    return;
                }

                double limitPrice = 0.0;
                double stopPrice = 0.0;

                if (type == OrderType.Limit)
                {
                    limitPrice = price;
                }
                else if (type == OrderType.StopMarket)
                {
                    stopPrice = price;
                }
                else if (type == OrderType.StopLimit)
                {
                    limitPrice = price;
                    stopPrice = price;
                }

                Order orderObj = acc.CreateOrder(Instrument, action, type, OrderEntry.Manual, TimeInForce.Gtc, qty, limitPrice, stopPrice, "", name, DateTime.MinValue, null);
                if (orderObj != null)
                {
                    acc.Submit(new[] { orderObj });
                }
            }
            catch (Exception ex)
            {
                Print("[CCC] Error enviando orden: " + ex.Message + "\n" + ex.StackTrace);
            }
        }

        private void CancelTpSlOrders(Account acc, AccountRiskSettings settings)
        {
            try
            {
                var ordersToCancel = acc.Orders.Cast<Order>().Where(o => 
                    o.Instrument.FullName.Equals(Instrument.FullName, StringComparison.OrdinalIgnoreCase) &&
                    (o.OrderState == OrderState.Working || o.OrderState == OrderState.Accepted || o.OrderState == OrderState.PartFilled) &&
                    (o.Name.StartsWith("TP_" + settings.Name) || o.Name.StartsWith("SL_" + settings.Name))
                ).ToList();

                if (ordersToCancel.Count > 0)
                {
                    acc.Cancel(ordersToCancel.ToArray());
                }
            }
            catch (Exception ex)
            {
                Print("[CCC] Error cancelando TP/SL: " + ex.Message);
            }
            settings.TpOrder = null;
            settings.SlOrder = null;
        }

        private void SyncTpSlOrders(Account acc, AccountRiskSettings settings, AccountRiskSettings eff, Position pos)
        {
            CancelTpSlOrders(acc, settings);

            if (pos == null || pos.MarketPosition == MarketPosition.Flat)
                return;

            double avgPrice = pos.AveragePrice;
            int qty = pos.Quantity;
            double ptVal = Instrument.MasterInstrument.PointValue;

            double cashBalance = acc.Get(AccountItem.CashValue, Currency.UsDollar);
            if (cashBalance <= 0) cashBalance = eff.StartBalance > 0 ? eff.StartBalance : 50000.0;
            double targetEquity = eff.StartBalance + eff.Target;
            double maxLossEquity = eff.StartBalance - eff.MaxLoss;

            double targetRoom = targetEquity - cashBalance;
            double lossRoom = cashBalance - maxLossEquity;

            double dailyProfitRoom = (settings.DailyStartBalance + eff.DailyProfitLimit) - cashBalance;
            double dailyLossRoom = cashBalance - (settings.DailyStartBalance - eff.DailyLossLimit);

            double tradeTpUsd = eff.TpUsd;
            double tradeSlUsd = eff.SlUsd;

            if (eff.Target > 0 && targetRoom > 0) tradeTpUsd = Math.Min(tradeTpUsd, targetRoom);
            if (eff.DailyProfitLimit > 0 && dailyProfitRoom > 0) tradeTpUsd = Math.Min(tradeTpUsd, dailyProfitRoom);
            tradeTpUsd = Math.Max(1.0, tradeTpUsd);

            if (eff.MaxLoss > 0 && lossRoom > 0) tradeSlUsd = Math.Min(tradeSlUsd, lossRoom);
            if (eff.DailyLossLimit > 0 && dailyLossRoom > 0) tradeSlUsd = Math.Min(tradeSlUsd, dailyLossRoom);
            tradeSlUsd = Math.Max(1.0, tradeSlUsd);

            double tpDelta = tradeTpUsd / (qty * ptVal);
            double slDelta = tradeSlUsd / (qty * ptVal);

            double tpPrice = 0.0;
            double slPrice = 0.0;
            OrderAction exitAction;

            if (pos.MarketPosition == MarketPosition.Long)
            {
                tpPrice = avgPrice + tpDelta;
                slPrice = avgPrice - slDelta;
                exitAction = OrderAction.Sell;
            }
            else
            {
                tpPrice = avgPrice - tpDelta;
                slPrice = avgPrice + slDelta;
                exitAction = OrderAction.Buy;
            }

            tpPrice = Math.Round(tpPrice / Instrument.MasterInstrument.TickSize) * Instrument.MasterInstrument.TickSize;
            slPrice = Math.Round(slPrice / Instrument.MasterInstrument.TickSize) * Instrument.MasterInstrument.TickSize;

            double currentPrice = lastRealtimePrice > 0 ? lastRealtimePrice : avgPrice;
            double tickSize = Instrument.MasterInstrument.TickSize;
            double safetyBuffer = 2.0 * tickSize;

            if (pos.MarketPosition == MarketPosition.Long && slPrice >= currentPrice - safetyBuffer)
            {
                Print(string.Format("[CCC] [WARN] SL calculado ({0}) >= precio actual con buffer ({1}). Ejecutando cierre a mercado (Flatten) de seguridad para {2}.", slPrice, currentPrice - safetyBuffer, settings.Name));
                acc.Flatten(new[] { Instrument });
                return;
            }
            else if (pos.MarketPosition == MarketPosition.Short && slPrice <= currentPrice + safetyBuffer)
            {
                Print(string.Format("[CCC] [WARN] SL calculated ({0}) <= precio actual con buffer ({1}). Ejecutando cierre a mercado (Flatten) de seguridad para {2}.", slPrice, currentPrice + safetyBuffer, settings.Name));
                acc.Flatten(new[] { Instrument });
                return;
            }

            settings.UnifiedTpPrice = tpPrice;
            settings.UnifiedSlPrice = slPrice;
            settings.TotalPositionSize = qty;
            settings.AvgEntryPrice = avgPrice;
            settings.Direction = pos.MarketPosition == MarketPosition.Long ? "LONG" : "SHORT";

            // Dibujar las líneas en el gráfico
            NoChart( "SL_Line", slPrice, Brushes.Red, DashStyleHelper.Dash, 2);
            NoChart( "TP_Line", tpPrice, Brushes.Green, DashStyleHelper.Dash, 2);

            string ocoId = "OCO_" + settings.Name + "_" + DateTime.Now.Ticks;

            try
            {
                Order tpOrderObj = acc.CreateOrder(Instrument, exitAction, OrderType.Limit, OrderEntry.Manual, TimeInForce.Gtc, qty, tpPrice, 0.0, ocoId, "TP_" + settings.Name, DateTime.MinValue, null);
                Order slOrderObj = acc.CreateOrder(Instrument, exitAction, OrderType.StopMarket, OrderEntry.Manual, TimeInForce.Gtc, qty, 0.0, slPrice, ocoId, "SL_" + settings.Name, DateTime.MinValue, null);

                if (tpOrderObj != null && slOrderObj != null)
                {
                    settings.TpOrder = tpOrderObj;
                    settings.SlOrder = slOrderObj;
                    acc.Submit(new[] { tpOrderObj, slOrderObj });
                }
            }
            catch (Exception ex)
            {
                Print("[CCC] Error enviando TP/SL OCO: " + ex.Message);
            }
        }

        private void OnGlobalExecutionUpdate(object sender, ExecutionEventArgs e)
        {
            if (e.Execution == null || e.Execution.Account == null) return;
            string accName = e.Execution.Account.Name;

            lock (accountsConfig)
            {
                if (accountsConfig.ContainsKey(accName))
                {
                    AccountRiskSettings settings = accountsConfig[accName];
                    Account acc = e.Execution.Account;

                    // Registro y seguimiento de comisiones
                    if (e.Execution.Order != null && (e.Execution.Order.OrderState == OrderState.Filled || e.Execution.Order.OrderState == OrderState.PartFilled))
                    {
                        double comm = e.Execution.Commission;
                        if (comm > 0)
                        {
                            settings.NinjaTraderHandlesCommissions = true;
                            settings.DailyCommissions += comm;
                        }
                        else
                        {
                            double manualComm = e.Execution.Quantity * settings.CommissionPerContract;
                            settings.DailyCommissions += manualComm;
                        }
                    }

                    Position pos = acc.Positions.Cast<Position>().FirstOrDefault(p => p.Instrument.FullName.Equals(Instrument.FullName, StringComparison.OrdinalIgnoreCase));
                    if (pos == null || pos.MarketPosition == MarketPosition.Flat)
                    {
                        if (settings.AvgEntryPrice > 0 && e.Execution != null && e.Execution.Price > 0 && Instrument != null && Instrument.MasterInstrument != null)
                        {
                            double ptVal = Instrument.MasterInstrument.PointValue;
                            double tradePnl = 0.0;
                            if (settings.Direction == "LONG")
                            {
                                tradePnl = (e.Execution.Price - settings.AvgEntryPrice) * e.Execution.Quantity * ptVal;
                            }
                            else if (settings.Direction == "SHORT")
                            {
                                tradePnl = (settings.AvgEntryPrice - e.Execution.Price) * e.Execution.Quantity * ptVal;
                            }
                            settings.SessionRealizedPnl += tradePnl;
                            if(e.Execution.Order!=null && !e.Execution.Order.Name.StartsWith("Entry",StringComparison.Ordinal)) {settings.TradesClosed++;if(tradePnl>0)settings.TradesWon++;else if(tradePnl<0)settings.TradesLost++;}
                            Print(string.Format("[CCC] Operación realizada en {0}: ${1:F2} | PnL Sesión: ${2:F2}", settings.Name, tradePnl, settings.SessionRealizedPnl));
                        }

                        RemoveDrawObject("SL_Line");
                        RemoveDrawObject("TP_Line");
                        ResetTradingState(acc, settings);
                        SaveConfiguration();
                    }
                }
            }
        }

        private void ResetTradingState(Account acc, AccountRiskSettings settings)
        {
            RemoveDrawObject("SL_Line");
            RemoveDrawObject("TP_Line");

            if (acc != null)
            {
                CancelTpSlOrders(acc, settings);
            }
            settings.Direction = "FLAT";
            settings.AvgEntryPrice = 0.0;
            settings.TotalPositionSize = 0;
            settings.UnifiedSlPrice = 0.0;
            settings.UnifiedTpPrice = 0.0;
            settings.MaxUnrealizedPnl = 0.0;
        }

        private bool IsInTradingHours(AccountRiskSettings settings)
        {
            if (!settings.TimeFilterEnabled) return true;
            try
            {
                DateTime now = DateTime.UtcNow.AddHours(-3);
                DateTime start = DateTime.ParseExact(settings.StartTime, "HH:mm", System.Globalization.CultureInfo.InvariantCulture);
                DateTime end = DateTime.ParseExact(settings.EndTime, "HH:mm", System.Globalization.CultureInfo.InvariantCulture);

                DateTime combinedStart = new DateTime(now.Year, now.Month, now.Day, start.Hour, start.Minute, 0);
                DateTime combinedEnd = new DateTime(now.Year, now.Month, now.Day, end.Hour, end.Minute, 0);

                if (combinedStart <= combinedEnd)
                    return now >= combinedStart && now <= combinedEnd;
                else
                    return now >= combinedStart || now <= combinedEnd;
            }
            catch
            {
                return true;
            }
        }

        // =====================================================================
        //  MONITOREO DE LÍMITES EN TIEMPO REAL
        // =====================================================================
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
                            acc.Flatten(new[] { Instrument });
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
                            acc.Flatten(new[] { Instrument });
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
                            acc.Flatten(new[] { Instrument });
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


 }
}

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

        private HashSet<string> evaluationAccounts=new HashSet<string>();
        private readonly Dictionary<string,FileStream> accountReservations=new Dictionary<string,FileStream>();
        private void LoadEvaluationAccounts() {
            string path=Path.Combine(Path.GetDirectoryName(configFilePath),"EvaluationAccounts.txt");
            if(File.Exists(path))evaluationAccounts=new HashSet<string>(File.ReadAllLines(path).Where(x=>x.Length>0));
        }
        private void ReleaseAccountReservations() {foreach(var f in accountReservations.Values)f.Dispose();accountReservations.Clear();}
        private void ReserveAccounts(IEnumerable<string> names) {
            var selected=new HashSet<string>(names);var added=new List<string>();
            string folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Stratix","AccountReservations");Directory.CreateDirectory(folder);
            try {
                foreach(string name in selected.Where(x=>!accountReservations.ContainsKey(x))) {
                    string hash;using(var sha=System.Security.Cryptography.SHA256.Create())hash=BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(name))).Replace("-","");
                    try{accountReservations[name]=new FileStream(Path.Combine(folder,hash+".lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);added.Add(name);}
                    catch(IOException){throw new Exception("La cuenta "+name+" está reservada a otro servicio (PropPass/RocketPass/copy). Libérala desde ese servicio, flat y sin órdenes.");}
                }
            }catch{foreach(string name in added){accountReservations[name].Dispose();accountReservations.Remove(name);}throw;}
            foreach(string name in accountReservations.Keys.Where(x=>!selected.Contains(x)).ToArray()) {
                var a=GetAccountCached(name);if(a!=null&&(a.Positions.Cast<Position>().Any(p=>p.MarketPosition!=MarketPosition.Flat)||a.Orders.Cast<Order>().Any(EngineWorking)))continue;
                accountReservations[name].Dispose();accountReservations.Remove(name);
            }
        }
        private sealed class BridgeHealth {
            public const double TimeoutSeconds=10;
            public DateTime LastSuccess;
            public int Failures;
            public string LastError="",PauseCode="",PauseReason="";
            public DateTime PauseAt=DateTime.MinValue;
            public bool Paused;
            public BridgeHealth(DateTime now) {LastSuccess=now;}
            public static bool FatalHttp(int status) {return status>=400&&status<500&&status!=408&&status!=429;}
            public bool Expired(DateTime now) {return (now-LastSuccess).TotalSeconds>=TimeoutSeconds;}
            public void Failure(string error) {Failures++;LastError=error;}
            public void Success(DateTime now) {LastSuccess=now;Failures=0;LastError="";}
            public void Pause(string code,string reason,DateTime now) {Paused=true;PauseCode=code;PauseReason=reason;PauseAt=now;}
            public bool Check(DateTime now) {
                if(Paused||!Expired(now))return false;
                Pause("COMMUNICATION_TIMEOUT","Sin confirmación del servidor durante 10 segundos. Último error: "+(LastError.Length==0?"sin respuesta":LastError),now);
                return true;
            }
            public void Resume(DateTime now) {
                if(Expired(now))throw new InvalidOperationException("No se reanuda sin comunicación reciente con el servidor");
                Paused=false;PauseCode="";PauseReason="";PauseAt=DateTime.MinValue;
            }
        }
        private class EngineLease {
            public string Id,Account,Symbol,Parent,Comment="",Phase="FLAT",Fault="",CloseReason="CLOSE";
            public Instrument Instrument;public long Ticket,Magic,Opened;
            public double Sl,Tp,SlDistance,TpDistance,AwaitPrice;public Order Entry,Stop,Target,Exit;
            public string AwaitId="",AwaitKind="";public DateTime AwaitAt;public long Expiration;
            public int CloseQuantity;public bool CancelForClose;
            public bool CopyMode;public int CopyQuantity,CopySide;public double CopyAverage;
        }
        private readonly Dictionary<string,EngineLease> engineLeases=new Dictionary<string,EngineLease>();
        private readonly Dictionary<string,string> engineReplies=new Dictionary<string,string>();
        private readonly Queue<string> engineReplyOrder=new Queue<string>();
        private readonly Dictionary<string,BarsRequest> engineBars=new Dictionary<string,BarsRequest>();
        private readonly Dictionary<string,Instrument> engineFeeds=new Dictionary<string,Instrument>();
        private readonly System.Collections.Concurrent.ConcurrentDictionary<string,DateTime> engineTickTimes=new System.Collections.Concurrent.ConcurrentDictionary<string,DateTime>();
        private readonly HashSet<string> engineSeen=new HashSet<string>();
        private readonly Dictionary<string,long> copyObservedTickets=new Dictionary<string,long>();
        private readonly Dictionary<string,long> copyObservedTimes=new Dictionary<string,long>();
        private readonly Dictionary<string,int> copyObservedDirections=new Dictionary<string,int>();
        private long copyNextTicket=DateTime.UtcNow.Ticks/100;
        private readonly Dictionary<string,DateTime> copyNativeFilledAt=new Dictionary<string,DateTime>();
        private readonly Dictionary<string,long> copyNativeOrders=new Dictionary<string,long>();
        private long CopyOrderTicket(Order o) {long value;if(!copyNativeOrders.TryGetValue(o.OrderId,out value)){value=++copyNextTicket;copyNativeOrders[o.OrderId]=value;}return value;}
        private string CopyObserve(Account acc) {
            var rows=new List<string>();var active=new HashSet<string>();var pending=new List<string>();var quotes=new List<string>();
            foreach(var o in acc.Orders.Cast<Order>().Where(o=>EngineWorking(o)&&(o.OrderAction==OrderAction.Buy||o.OrderAction==OrderAction.SellShort)&&!acc.Positions.Cast<Position>().Any(p=>p.Instrument.FullName==o.Instrument.FullName&&p.MarketPosition==MarketPosition.Short&&o.OrderAction==OrderAction.Buy)&&(o.OrderType==OrderType.Limit||o.OrderType==OrderType.StopMarket))) {
                long ticket=CopyOrderTicket(o);bool buy=o.OrderAction==OrderAction.Buy;
                var known=engineLeases.Values.FirstOrDefault(l=>l.Account==acc.Name&&l.Entry!=null&&l.Entry.OrderId==o.OrderId);
                pending.Add("{\"ticket\":"+ticket+",\"symbol\":"+J(o.Instrument.FullName)+",\"type\":"+(buy?(o.OrderType==OrderType.Limit?2:4):(o.OrderType==OrderType.Limit?3:5))+",\"volume\":"+(o.Quantity-o.Filled)+",\"price_open\":"+N(o.OrderType==OrderType.Limit?o.LimitPrice:o.StopPrice)+",\"sl\":"+N(known==null?0:known.Sl)+",\"tp\":"+N(known==null?0:known.Tp)+",\"time\":"+(long)(o.Time.ToUniversalTime()-new DateTime(1970,1,1)).TotalSeconds+"}");
            }
            foreach(var instrument in acc.Orders.Cast<Order>().Where(EngineWorking).Select(o=>o.Instrument).Concat(acc.Positions.Cast<Position>().Select(p=>p.Instrument)).GroupBy(i=>i.FullName).Select(g=>g.First())){quotes.Add(J(instrument.FullName)+":{\"bid\":"+N(instrument.MarketData.Bid.Price)+",\"ask\":"+N(instrument.MarketData.Ask.Price)+"}");}
            foreach(var p in acc.Positions.Cast<Position>().Where(p=>p.MarketPosition!=MarketPosition.Flat)) {
                string key=acc.Name+":"+p.Instrument.FullName;active.Add(key);
                int side=p.MarketPosition==MarketPosition.Long?0:1;
                if(!copyObservedTickets.ContainsKey(key)||copyObservedDirections[key]!=side) {
                    copyObservedTickets[key]=++copyNextTicket;copyObservedDirections[key]=side;
                    copyObservedTimes[key]=(long)(DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds;
                }
                var exits=acc.Orders.Cast<Order>().Where(o=>o.Instrument.FullName==p.Instrument.FullName&&EngineWorking(o)&&
                    (side==0?o.OrderAction==OrderAction.Sell:(o.OrderAction==OrderAction.BuyToCover||o.OrderAction==OrderAction.Buy))).ToArray();
                var stops=exits.Where(o=>o.OrderType==OrderType.StopMarket||o.OrderType==OrderType.StopLimit).ToArray();
                var targets=exits.Where(o=>o.OrderType==OrderType.Limit).ToArray();
                double sl=stops.Length==1?stops[0].StopPrice:0,tp=targets.Length==1?targets[0].LimitPrice:0;
                var sourceOrders=acc.Orders.Cast<Order>().Where(o=>o.Instrument.FullName==p.Instrument.FullName&&o.Filled>0&&copyNativeOrders.ContainsKey(o.OrderId)&&copyNativeFilledAt.ContainsKey(o.OrderId)&&copyNativeFilledAt[o.OrderId]>=new DateTime(1970,1,1).AddSeconds(copyObservedTimes[key]-3)&&((side==0&&o.OrderAction==OrderAction.Buy)||(side==1&&o.OrderAction==OrderAction.SellShort))).Select(o=>CopyOrderTicket(o).ToString()).ToArray();
                rows.Add("{\"ticket\":"+copyObservedTickets[key]+",\"symbol\":"+J(p.Instrument.FullName)+",\"type\":"+side+",\"volume\":"+p.Quantity+",\"price_open\":"+N(p.AveragePrice)+",\"sl\":"+N(sl)+",\"tp\":"+N(tp)+",\"source_orders\":["+string.Join(",",sourceOrders)+"],\"magic\":0,\"comment\":\"NT8 master\",\"time\":"+copyObservedTimes[key]+"}");
            }
            foreach(string key in copyObservedTickets.Keys.Where(k=>k.StartsWith(acc.Name+":")&&!active.Contains(k)).ToArray()) {
                copyObservedTickets.Remove(key);copyObservedTimes.Remove(key);copyObservedDirections.Remove(key);
            }
            double cash=acc.Get(AccountItem.CashValue,Currency.UsDollar),open=acc.Get(AccountItem.UnrealizedProfitLoss,Currency.UsDollar);
            return "{\"balance\":"+N(cash)+",\"equity\":"+N(cash+open)+",\"positions\":["+string.Join(",",rows)+"],\"orders\":["+string.Join(",",pending)+"],\"quotes\":{"+string.Join(",",quotes)+"}}";
        }
        private string EngineResults() {return "["+string.Join(",",engineReplies.Select(k=>"{\"id\":"+J(k.Key)+",\"value\":"+k.Value+"}"))+"]";}
        private void EngineReply(string id,string value) {lock(serviceGate){engineReplies[id]=value;engineReplyOrder.Enqueue(id);while(engineReplyOrder.Count>64||engineReplies.Values.Sum(x=>x.Length)>350000){string old=engineReplyOrder.Dequeue();if(old!=id)engineReplies.Remove(old);}}}
        private void EngineError(string id,string reason) {EngineReply(id,"{\"error\":"+J(reason)+"}");Print("Motor NT8: "+reason);}
        private void EngineTrack(string symbol) {
            if(engineFeeds.ContainsKey(symbol))return;
            var instrument=NinjaTrader.Cbi.Instrument.GetInstrument(symbol);if(instrument==null)throw new Exception("Contrato no disponible: "+symbol);
            engineFeeds[symbol]=instrument;
            instrument.MarketData.Update+=EngineMarketData;
        }
        private void EngineMarketData(object sender,MarketDataEventArgs e) {if(e.MarketDataType==MarketDataType.Last)engineTickTimes[e.Instrument.FullName]=DateTime.UtcNow;}
        private bool PrepareEngineFeed(string command) {
            string[] parts=command.Split('|');if(parts.Length<4||parts[3]!="engine"||parts[1]!=instance)return true;
            if(parts.Contains("method=observe"))return true;
            // NT subscriptions can synchronously wait for a market-data callback.
            // Never subscribe while holding the gate used by those callbacks.
            string symbol=parts.Skip(4).FirstOrDefault(p=>p.StartsWith("symbol="));if(symbol==null)return true;
            try{EngineTrack(symbol.Substring(7));return true;}
            catch(Exception ex){EngineError(parts[0],ex.Message);return false;}
        }
        private bool EngineWorking(Order o) {return o!=null&&(o.OrderState==OrderState.Initialized||o.OrderState==OrderState.Submitted||o.OrderState==OrderState.Accepted||o.OrderState==OrderState.Working||o.OrderState==OrderState.PartFilled||o.OrderState==OrderState.CancelPending||o.OrderState==OrderState.ChangePending);}
        private class EngineHolding {public int Quantity;public double AveragePrice;public MarketPosition MarketPosition;}
        private EngineHolding EnginePosition(EngineLease l) {
            if(l.CopyMode)return l.CopyQuantity<=0?null:new EngineHolding{Quantity=l.CopyQuantity,AveragePrice=l.CopyAverage,MarketPosition=l.CopySide==0?MarketPosition.Long:MarketPosition.Short};
            var p=GetAccountCached(l.Account).Positions.Cast<Position>().FirstOrDefault(x=>x.Instrument.FullName==l.Symbol&&x.MarketPosition!=MarketPosition.Flat);
            return p==null?null:new EngineHolding{Quantity=p.Quantity,AveragePrice=p.AveragePrice,MarketPosition=p.MarketPosition};
        }
        private readonly HashSet<string> engineExecutionSeen=new HashSet<string>();
        private void EngineExecution(ExecutionEventArgs e) {
            if(e.Execution==null||e.Execution.Order==null||!engineExecutionSeen.Add(e.Execution.ExecutionId))return;
            var order=e.Execution.Order;copyNativeFilledAt[order.OrderId]=DateTime.UtcNow;
            foreach(var l in engineLeases.Values.Where(x=>x.CopyMode&&x.Account==e.Execution.Account.Name)) {
                if(order.Name=="STXG_ENTRY_"+l.Id) {
                    int before=l.CopyQuantity;l.CopyQuantity+=e.Execution.Quantity;l.CopyAverage=(l.CopyAverage*before+e.Execution.Price*e.Execution.Quantity)/l.CopyQuantity;
                    l.CopySide=order.OrderAction==OrderAction.Buy?0:1;SaveEngineLeases();break;
                }
                if(order.Name.StartsWith("STXG_")&&order.Name.EndsWith("_"+l.Id)) {l.CopyQuantity=Math.Max(0,l.CopyQuantity-e.Execution.Quantity);SaveEngineLeases();break;}
            }
        }
        private Order[] EngineProtection(EngineLease l) {return new[]{l.Stop,l.Target}.Where(EngineWorking).ToArray();}
        private string EngineResult(EngineLease l,int retcode,double qty,string detail) {return "{\"native_order_id\":"+J(l.Entry==null?"":l.Entry.OrderId)+",\"retcode\":"+retcode+",\"order\":"+l.Ticket+",\"volume\":"+N(qty)+",\"comment\":"+J(detail)+"}";}
        private void SaveEngineLeases() {
            if(string.IsNullOrEmpty(configFilePath))return;
            File.WriteAllLines(Path.Combine(Path.GetDirectoryName(configFilePath),"EngineLeases.txt"),engineLeases.Values.Select(l=>string.Join("|",new[]{l.Id,l.Account,l.Symbol,l.Ticket.ToString(),l.Magic.ToString(),N(l.Sl),N(l.Tp),N(l.SlDistance),N(l.TpDistance),l.Opened.ToString(),l.Comment,l.Parent,l.CopyMode?"1":"0",l.CopyQuantity.ToString(),N(l.CopyAverage),l.CopySide.ToString()})));
        }
        private void LoadEngineLeases() {
            string file=Path.Combine(Path.GetDirectoryName(configFilePath),"EngineLeases.txt");if(!File.Exists(file))return;
            foreach(string line in File.ReadAllLines(file))try {
                var p=line.Split('|');if(p.Length!=11&&p.Length!=12&&p.Length!=16)continue;EngineTrack(p[2]);
                var l=new EngineLease{Id=p[0],Parent=p.Length>=12?p[11]:p[0],Account=p[1],Symbol=p[2],Instrument=engineFeeds[p[2]],Ticket=long.Parse(p[3]),Magic=long.Parse(p[4]),Sl=double.Parse(p[5],System.Globalization.CultureInfo.InvariantCulture),Tp=double.Parse(p[6],System.Globalization.CultureInfo.InvariantCulture),SlDistance=double.Parse(p[7],System.Globalization.CultureInfo.InvariantCulture),TpDistance=double.Parse(p[8],System.Globalization.CultureInfo.InvariantCulture),Opened=long.Parse(p[9]),Comment=p[10]};
                if(p.Length==16){l.CopyMode=p[12]=="1";l.CopyQuantity=int.Parse(p[13]);l.CopyAverage=double.Parse(p[14],System.Globalization.CultureInfo.InvariantCulture);l.CopySide=int.Parse(p[15]);}
                var acc=GetAccountCached(l.Account);if(acc==null||!CanExecute(acc))continue;
                l.Stop=acc.Orders.Cast<Order>().FirstOrDefault(o=>o.Name=="STXG_SL_"+l.Id&&EngineWorking(o));l.Target=acc.Orders.Cast<Order>().FirstOrDefault(o=>o.Name=="STXG_TP_"+l.Id&&EngineWorking(o));
                l.Entry=acc.Orders.Cast<Order>().FirstOrDefault(o=>o.Name=="STXG_ENTRY_"+l.Id&&EngineWorking(o));
                l.Exit=acc.Orders.Cast<Order>().FirstOrDefault(o=>o.Name=="STXG_CLOSE_"+l.Id&&EngineWorking(o));
                l.Phase=l.Entry!=null?"ENTRY_PENDING":acc.Positions.Cast<Position>().Any(position=>position.Instrument.FullName==l.Symbol&&position.MarketPosition!=MarketPosition.Flat)?"OPEN":"FLAT";
                engineLeases[l.Id]=l;
            }catch(Exception ex){Print("Recuperación de sesión del motor: "+ex.Message);}
        }
        private string EngineState(EngineLease l) {
            var acc=GetAccountCached(l.Account);var i=l.Instrument;var p=EnginePosition(l);var q=i.MarketData;
            double cash=acc.Get(AccountItem.CashValue,Currency.UsDollar),open=acc.Get(AccountItem.UnrealizedProfitLoss,Currency.UsDollar);
            string position=p==null?"[]":"[{\"ticket\":"+l.Ticket+",\"symbol\":"+J(l.Symbol)+",\"type\":"+(p.MarketPosition==MarketPosition.Long?0:1)+",\"volume\":"+p.Quantity+",\"price_open\":"+N(p.AveragePrice)+",\"sl\":"+N(l.Sl)+",\"tp\":"+N(l.Tp)+",\"magic\":"+l.Magic+",\"comment\":"+J(l.Comment)+",\"time\":"+l.Opened+"}]";
            string protections="["+string.Join(",",new[]{l.Stop,l.Target}.Where(o=>o!=null).Select(o=>"{\"name\":"+J(o.Name)+",\"state\":"+J(o.OrderState.ToString())+",\"quantity\":"+o.Quantity+",\"stop\":"+N(o.StopPrice)+",\"limit\":"+N(o.LimitPrice)+"}"))+"]";
            string orders=EngineWorking(l.Entry)?"[{\"ticket\":"+l.Ticket+",\"magic\":"+l.Magic+",\"type\":"+(l.Entry.OrderAction==OrderAction.Buy?(l.Entry.OrderType==OrderType.Limit?2:4):(l.Entry.OrderType==OrderType.Limit?3:5))+",\"volume\":"+(l.Entry.Quantity-l.Entry.Filled)+",\"expiration\":"+l.Expiration+",\"symbol\":"+J(l.Symbol)+",\"comment\":"+J(l.Comment)+",\"price_open\":"+N(l.Entry.OrderType==OrderType.Limit?l.Entry.LimitPrice:l.Entry.StopPrice)+",\"sl\":"+N(l.Sl)+",\"tp\":"+N(l.Tp)+"}]":"[]";
            var lastExit=new[]{l.Stop,l.Target,l.Exit}.FirstOrDefault(o=>o!=null&&o.OrderState==OrderState.Filled);
            string exit=lastExit==null?"null":"{\"name\":"+J(lastExit.Name)+",\"price\":"+N(lastExit.AverageFillPrice)+",\"quantity\":"+lastExit.Filled+",\"stop_price\":"+N(lastExit.StopPrice)+"}";
            DateTime t;engineTickTimes.TryGetValue(l.Symbol,out t);
            return "{\"execution_allowed\":"+B(CanExecute(acc)&&l.Fault.Length==0)+",\"fault\":"+J(l.Fault)+",\"account\":"+J(l.Account)+",\"balance\":"+N(cash)+",\"equity\":"+N(cash+open)+",\"tick_size\":"+N(i.MasterInstrument.TickSize)+",\"point_value\":"+N(i.MasterInstrument.PointValue)+",\"bid\":"+N(q.Bid.Price)+",\"ask\":"+N(q.Ask.Price)+",\"tick_time\":"+N(t==DateTime.MinValue?0:(t-new DateTime(1970,1,1)).TotalSeconds)+",\"positions\":"+position+",\"position_ticket\":"+l.Ticket+",\"last_exit\":"+exit+",\"protections\":"+protections+",\"orders\":"+orders+"}";
        }
        private void EngineBarsReply(string id,BarsRequest request,int minutes,int count) {
            var rows=new List<string>();var bars=request.Bars;DateTime epoch=new DateTime(1970,1,1,0,0,0,DateTimeKind.Utc);
            for(int i=Math.Max(0,bars.Count-count-1);i<bars.Count;i++) {
                DateTime end=bars.GetTime(i).ToUniversalTime();if(end>DateTime.UtcNow)continue;
                rows.Add("{\"time\":"+(long)(end.AddMinutes(-minutes)-epoch).TotalSeconds+",\"open\":"+N(bars.GetOpen(i))+",\"high\":"+N(bars.GetHigh(i))+",\"low\":"+N(bars.GetLow(i))+",\"close\":"+N(bars.GetClose(i))+",\"tick_volume\":"+bars.GetVolume(i)+"}");
            }
            EngineReply(id,"["+string.Join(",",rows.Skip(Math.Max(0,rows.Count-count)))+"]");
        }
        private void EngineCommand(string id,Dictionary<string,string> v) {
            if(!engineSeen.Add(id))return;
            try {
                string method=v["method"],sid=v["session"],account=v["account"],symbol=v["symbol"],parent=v.ContainsKey("parent")?v["parent"]:v["session"];
                if(sid.Length!=32||sid.Any(c=>!Uri.IsHexDigit(c)))throw new Exception("Sesión inválida");
                if(parent.Length!=32||parent.Any(c=>!Uri.IsHexDigit(c)))throw new Exception("Portafolio inválido");
                var acc=GetAccountCached(account);if(!CanExecute(acc))throw new Exception("Solo cuentas locales Simulator/Playback");
                if(method=="observe"){EngineReply(id,CopyObserve(acc));return;}
                EngineTrack(symbol);
                if(method=="claim") {
                    bool copy=v.ContainsKey("copy_mode")&&v["copy_mode"]=="1";
                    EngineLease old;if(engineLeases.TryGetValue(sid,out old)){if(old.Account!=account||old.Symbol!=symbol||old.Parent!=parent)throw new Exception("La sesión cambió de identidad");EngineReply(id,"{\"ok\":true}");return;}
                    AccountRiskSettings settings;if(groupAccounts.Contains(account)&&accountsConfig.TryGetValue(account,out settings)&&settings.Enabled&&settings.Status=="EN PROCESO")throw new Exception("La cuenta está reservada a PropPass");
                    if(engineLeases.Values.Any(lease=>lease.Account==account&&(lease.Parent!=parent||lease.Symbol==symbol&&(!copy||!lease.CopyMode))))throw new Exception("La cuenta pertenece a otra sesión o el contrato ya está asignado");
                    if(!copy||!engineLeases.Values.Any(x=>x.Account==account&&x.Parent==parent&&x.CopyMode)) {
                        if(acc.Positions.Cast<Position>().Any(p=>p.MarketPosition!=MarketPosition.Flat)||acc.Orders.Cast<Order>().Any(EngineWorking))throw new Exception("Asigna con la cuenta flat y sin órdenes");
                    } else if(acc.Orders.Cast<Order>().Any(o=>EngineWorking(o)&&!engineLeases.Values.Any(x=>x.Account==account&&(o.Name.EndsWith("_"+x.Id)))))throw new Exception("Hay órdenes ajenas a la copia");
                    ReserveAccounts(accountReservations.Keys.Concat(new[]{account}).ToArray());
                    engineLeases[sid]=new EngineLease{Id=sid,Parent=parent,Account=account,Symbol=symbol,Instrument=engineFeeds[symbol],Magic=long.Parse(v["magic"]),CopyMode=copy};SaveEngineLeases();EngineReply(id,"{\"ok\":true}");return;
                }
                EngineLease l;if(!engineLeases.TryGetValue(sid,out l)||l.Account!=account||l.Symbol!=symbol)throw new Exception("La sesión no posee esta cuenta/instrumento");
                if(method=="state"){EngineReply(id,EngineState(l));return;}
                if(method=="release"){if(EnginePosition(l)!=null||EngineWorking(l.Entry)||EngineProtection(l).Length>0)throw new Exception("No se libera una sesión con posiciones/órdenes");engineLeases.Remove(sid);if(!engineLeases.Values.Any(x=>x.Account==account)&&!groupAccounts.Contains(account))ReserveAccounts(accountReservations.Keys.Where(x=>x!=account).ToArray());SaveEngineLeases();EngineReply(id,"{\"ok\":true}");return;}
                if(method=="bars") {
                    int minutes=int.Parse(v["minutes"]),count=int.Parse(v["count"]);if(!new[]{30,60,240,1440}.Contains(minutes)||count<200||count>1000)throw new Exception("Histórico solicitado inválido");
                    string key=symbol+":"+minutes;BarsRequest request;
                    if(engineBars.TryGetValue(key,out request)){EngineBarsReply(id,request,minutes,count);return;}
                    request=new BarsRequest(l.Instrument,count+1);request.BarsPeriod=new BarsPeriod{BarsPeriodType=BarsPeriodType.Minute,Value=minutes};request.TradingHours=TradingHours.Get("Default 24 x 7");
                    request.Update+=(sender,e)=>{};
                    request.Request((b,code,message)=>{if(code!=ErrorCode.NoError){EngineError(id,"Histórico NT8: "+code+" "+message);b.Dispose();return;}lock(serviceGate){engineBars[key]=b;EngineBarsReply(id,b,minutes,count);}});return;
                }
                if(method!="mutate")throw new Exception("RPC no admitida");
                Func<string,double> number=k=>double.Parse(v[k],System.Globalization.CultureInfo.InvariantCulture);
                int action=int.Parse(v["action"]);var pos=EnginePosition(l);double tick=l.Instrument.MasterInstrument.TickSize;
                if(action==7) {
                    if(!EngineWorking(l.Entry)||pos!=null||long.Parse(v["order"])!=l.Ticket){EngineReply(id,EngineResult(l,10030,0,"Pendiente activada o finalizada antes de modificar; no se modificó"));return;}
                    double entry=Math.Round(number("price")/tick)*tick;l.Sl=Math.Round(number("sl")/tick)*tick;l.Tp=Math.Round(number("tp")/tick)*tick;
                    bool buyEntry=l.Entry.OrderAction==OrderAction.Buy;
                    if(l.Sl<=0||l.Tp<=0||(buyEntry?l.Sl>=entry||l.Tp<=entry:l.Sl<=entry||l.Tp>=entry))throw new Exception("Protecciones pendientes inválidas");
                    l.SlDistance=Math.Abs(entry-l.Sl);l.TpDistance=Math.Abs(entry-l.Tp);if(v.ContainsKey("expiration"))l.Expiration=long.Parse(v["expiration"]);
                    if(l.Entry.OrderType==OrderType.Limit)l.Entry.LimitPriceChanged=entry;else l.Entry.StopPriceChanged=entry;
                    acc.Dispatcher.BeginInvoke(new Action(()=>acc.Change(new[]{l.Entry})));SaveEngineLeases();
                    l.AwaitId=id;l.AwaitKind="pending_modify";l.AwaitPrice=entry;l.AwaitAt=DateTime.UtcNow;return;
                }
                if(action==6) {
                    if(pos==null){EngineReply(id,EngineResult(l,10030,0,"La posición ya terminó; no se modificó"));return;}
                    l.Sl=Math.Round(number("sl")/tick)*tick;l.Tp=Math.Round(number("tp")/tick)*tick;
                    EngineEnsureProtection(l,pos);SaveEngineLeases();l.AwaitId=id;l.AwaitKind="modify";l.AwaitAt=DateTime.UtcNow;return;
                }
                if(action==8){if(EngineWorking(l.Entry))QueueCancel(acc,new[]{l.Entry});l.AwaitId=id;l.AwaitKind="cancel";l.AwaitAt=DateTime.UtcNow;return;}
                int qty=(int)number("volume");if(qty<1||qty>100||number("volume")!=qty)throw new Exception("Cantidad de contratos inválida");
                if(v.ContainsKey("position")) {
                    if(pos==null||long.Parse(v["position"])!=l.Ticket||qty>pos.Quantity){EngineReply(id,EngineResult(l,10030,0,"La posición ya terminó o cambió de volumen; no se envió otra salida"));return;}
                    if(EngineWorking(l.Exit))throw new Exception("Ya existe un cierre en curso; espera su confirmación");
                    l.Exit=null; // A previous partial close must never acknowledge this new close.
                    l.CloseQuantity=qty;l.CloseReason="CLOSE";l.CancelForClose=true;l.AwaitId=id;l.AwaitKind="close";l.AwaitAt=DateTime.UtcNow;
                    var protection=EngineProtection(l);if(protection.Length>0)QueueCancel(acc,protection);return;
                }
                if(pos!=null||EngineWorking(l.Entry)||EngineProtection(l).Length>0)throw new Exception("Ya existe posición o entrada/protección pendiente");
                l.Stop=l.Target=l.Exit=null;
                int type=int.Parse(v["type"]);bool buy=type==0||type==2||type==4;
                if(l.CopyMode&&engineLeases.Values.Any(x=>x.Id!=l.Id&&x.Account==account&&x.Symbol==symbol&&((x.CopyQuantity>0&&(x.CopySide==0)!=buy)||(EngineWorking(x.Entry)&&(x.Entry.OrderAction==OrderAction.Buy)!=buy))))throw new Exception("NT8 netting: no se admiten copias simultáneas opuestas en el mismo contrato");double price=number("price"),sl=number("sl"),tp=number("tp");
                if(sl<=0||tp<=0||(buy?sl>=price||tp<=price:sl<=price||tp>=price))throw new Exception("SL/TP inválidos");
                l.Ticket=++copyNextTicket;l.Comment=v["comment"];l.Opened=(long)(DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds;l.SlDistance=Math.Abs(price-sl);l.TpDistance=Math.Abs(tp-price);l.Sl=sl;l.Tp=tp;
                l.Expiration=v.ContainsKey("expiration")?long.Parse(v["expiration"]):0;
                OrderType orderType=action==1?OrderType.Market:(type==2||type==3?OrderType.Limit:OrderType.StopMarket);
                l.Entry=acc.CreateOrder(l.Instrument,buy?OrderAction.Buy:OrderAction.SellShort,orderType,OrderEntry.Automated,TimeInForce.Gtc,qty,orderType==OrderType.Limit?Math.Round(price/tick)*tick:0,orderType==OrderType.StopMarket?Math.Round(price/tick)*tick:0,"","STXG_ENTRY_"+sid,DateTime.MinValue,null);
                l.Phase="ENTRY_PENDING";SaveEngineLeases();QueueSubmit(acc,new[]{l.Entry});Print("Motor NT8 · entrada "+account+" "+symbol+" "+qty+" "+orderType);
                l.AwaitId=id;l.AwaitKind=action==5?"pending":"entry";l.AwaitAt=DateTime.UtcNow;
            }catch(Exception ex){EngineError(id,ex.Message);}
        }
        private void EngineEnsureProtection(EngineLease l,EngineHolding p) {
            var acc=GetAccountCached(l.Account);double tick=l.Instrument.MasterInstrument.TickSize;
            if(l.Fault.Length>0)return;
            double bid=l.Instrument.MarketData.Bid.Price,ask=l.Instrument.MarketData.Ask.Price;
            bool crossedStop=p.MarketPosition==MarketPosition.Long?bid>0&&bid<=l.Sl:ask>0&&ask>=l.Sl;
            bool crossedTarget=p.MarketPosition==MarketPosition.Long?bid>0&&bid>=l.Tp:ask>0&&ask<=l.Tp;
            if((crossedStop||crossedTarget)&&EngineProtection(l).Length==0) {
                l.CloseReason=crossedStop?"SL":"TP";l.CloseQuantity=p.Quantity;l.CancelForClose=true;
                Print("Motor NT8 · "+l.Account+" · "+l.CloseReason+" cruzado durante reposición: cierre del remanente, sin enviar un stop inválido");return;
            }
            if((l.Stop!=null&&l.Stop.OrderState==OrderState.Rejected)||(l.Target!=null&&l.Target.OrderState==OrderState.Rejected)) {
                l.Fault="Protección rechazada; cierre preventivo de la posición de esta sesión";Print(l.Fault);
                l.CloseQuantity=p.Quantity;l.CancelForClose=true;var protection=EngineProtection(l);if(protection.Length>0)QueueCancel(acc,protection);return;
            }
            if(l.Phase=="ENTRY_PENDING") {l.Sl=p.AveragePrice+(p.MarketPosition==MarketPosition.Long?-1:1)*l.SlDistance;l.Tp=p.AveragePrice+(p.MarketPosition==MarketPosition.Long?1:-1)*l.TpDistance;l.Sl=Math.Round(l.Sl/tick)*tick;l.Tp=Math.Round(l.Tp/tick)*tick;l.Phase="OPEN";SaveEngineLeases();}
            if(EngineWorking(l.Stop)&&EngineWorking(l.Target)) {
                if(l.Stop.Quantity!=p.Quantity||l.Stop.StopPrice!=l.Sl||l.Target.Quantity!=p.Quantity||l.Target.LimitPrice!=l.Tp) {
                    l.Stop.QuantityChanged=p.Quantity;l.Stop.StopPriceChanged=l.Sl;l.Target.QuantityChanged=p.Quantity;l.Target.LimitPriceChanged=l.Tp;
                    acc.Dispatcher.BeginInvoke(new Action(()=>acc.Change(new[]{l.Stop,l.Target})));
                }return;
            }
            if(EngineProtection(l).Length>0)return;
            string oco="STXG_"+l.Id+"_"+DateTime.UtcNow.Ticks;var action=p.MarketPosition==MarketPosition.Long?OrderAction.Sell:OrderAction.Buy;
            l.Stop=acc.CreateOrder(l.Instrument,action,OrderType.StopMarket,OrderEntry.Automated,TimeInForce.Gtc,p.Quantity,0,l.Sl,oco,"STXG_SL_"+l.Id,DateTime.MinValue,null);
            l.Target=acc.CreateOrder(l.Instrument,action,OrderType.Limit,OrderEntry.Automated,TimeInForce.Gtc,p.Quantity,l.Tp,0,oco,"STXG_TP_"+l.Id,DateTime.MinValue,null);
            QueueSubmit(acc,new[]{l.Stop,l.Target});
        }
        private readonly Dictionary<string,DateTime> copyMismatchSince=new Dictionary<string,DateTime>();
        private void MonitorEngine() {
            foreach(var group in engineLeases.Values.Where(x=>x.CopyMode).GroupBy(x=>x.Account+"|"+x.Symbol)) {
                var first=group.First();var account=GetAccountCached(first.Account);if(account==null)continue;
                var physical=account.Positions.Cast<Position>().FirstOrDefault(x=>x.Instrument.FullName==first.Symbol&&x.MarketPosition!=MarketPosition.Flat);
                int actual=physical==null?0:physical.Quantity*(physical.MarketPosition==MarketPosition.Long?1:-1);
                int expected=group.Sum(x=>x.CopyQuantity*(x.CopySide==0?1:-1));
                if(actual==expected){copyMismatchSince.Remove(group.Key);continue;}
                DateTime since;if(!copyMismatchSince.TryGetValue(group.Key,out since)){copyMismatchSince[group.Key]=DateTime.UtcNow;continue;}
                if((DateTime.UtcNow-since).TotalSeconds<3)continue;
                foreach(var lease in group){lease.Fault="Posición externa o cierre manual: copia pausada; reconciliar en el terminal";if(actual==0)lease.CopyQuantity=0;var owned=new[]{lease.Entry,lease.Stop,lease.Target}.Where(EngineWorking).ToArray();if(owned.Length>0)QueueCancel(account,owned);}
                SaveEngineLeases();
            }
            foreach(var l in engineLeases.Values.ToArray())try {
                var acc=GetAccountCached(l.Account);if(acc==null)continue;var p=EnginePosition(l);
                if(l.CopyMode&&l.Fault.Length>0)continue;
                if(EngineWorking(l.Entry)&&l.Expiration>0&&(DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds>=l.Expiration)QueueCancel(acc,new[]{l.Entry});
                if(l.CancelForClose&&EngineProtection(l).Length==0) {
                    l.CancelForClose=false;l.Stop=l.Target=null;
                    if(p!=null){l.Exit=acc.CreateOrder(l.Instrument,p.MarketPosition==MarketPosition.Long?OrderAction.Sell:OrderAction.Buy,OrderType.Market,OrderEntry.Automated,TimeInForce.Gtc,Math.Min(l.CloseQuantity,p.Quantity),0,0,"","STXG_"+l.CloseReason+"_"+l.Id,DateTime.MinValue,null);QueueSubmit(acc,new[]{l.Exit});}
                }
                if(p!=null&&!l.CancelForClose&&!EngineWorking(l.Exit))EngineEnsureProtection(l,p);
                if(p==null&&!EngineWorking(l.Entry)&&l.Phase=="OPEN") {var orders=EngineProtection(l);if(orders.Length>0)QueueCancel(acc,orders);l.Phase="FLAT";SaveEngineLeases();}
                if(l.AwaitId.Length>0) {
                    Order order=l.AwaitKind=="entry"||l.AwaitKind.StartsWith("pending")?l.Entry:l.Exit;
                    bool protectionsReady=l.Stop!=null&&l.Target!=null&&(l.Stop.OrderState==OrderState.Accepted||l.Stop.OrderState==OrderState.Working)&&(l.Target.OrderState==OrderState.Accepted||l.Target.OrderState==OrderState.Working);
                    bool changedAndFilled=(l.Stop!=null&&l.Stop.OrderState==OrderState.Filled&&l.Stop.StopPrice==l.Sl)||(l.Target!=null&&l.Target.OrderState==OrderState.Filled&&l.Target.LimitPrice==l.Tp);
                    if(l.AwaitKind=="modify"&&((protectionsReady&&l.Stop.StopPrice==l.Sl&&l.Target.LimitPrice==l.Tp)||changedAndFilled)){EngineReply(l.AwaitId,EngineResult(l,10009,p==null?0:p.Quantity,"SL/TP confirmado, incluso si se ejecutó antes del siguiente pulso"));l.AwaitId="";}
                    else if(l.AwaitKind=="pending_modify"&&l.Entry!=null&&(l.Entry.OrderType==OrderType.Limit?l.Entry.LimitPrice:l.Entry.StopPrice)==l.AwaitPrice&&(l.Entry.OrderState==OrderState.Working||l.Entry.OrderState==OrderState.Accepted||l.Entry.OrderState==OrderState.Filled||l.Entry.OrderState==OrderState.PartFilled)){EngineReply(l.AwaitId,EngineResult(l,10009,l.Entry.Quantity,"Pendiente modificada confirmada"));l.AwaitId="";}
                    else if(l.AwaitKind=="cancel"&&!EngineWorking(l.Entry)){EngineReply(l.AwaitId,EngineResult(l,p==null?10009:10030,0,p==null?"Cancelación confirmada":"La pendiente se ejecutó antes de cancelar"));l.AwaitId="";}
                    else if(l.AwaitKind=="pending"&&l.Entry!=null&&(l.Entry.OrderState==OrderState.Working||l.Entry.OrderState==OrderState.Accepted)){EngineReply(l.AwaitId,EngineResult(l,10008,l.Entry.Quantity,"Pendiente aceptada"));l.AwaitId="";}
                    else if((l.AwaitKind=="entry"||l.AwaitKind=="close"||l.AwaitKind=="pending")&&order!=null&&order.OrderState==OrderState.Filled){EngineReply(l.AwaitId,EngineResult(l,10009,order.Filled,"Ejecución confirmada"));l.AwaitId="";}
                    else if(order!=null&&(order.OrderState==OrderState.Rejected||order.OrderState==OrderState.Cancelled)){EngineReply(l.AwaitId,EngineResult(l,order.Filled>0?10010:10030,order.Filled,"Orden terminada: "+order.OrderState));l.AwaitId="";}
                    else if(l.AwaitKind=="close"&&p==null){EngineReply(l.AwaitId,EngineResult(l,10009,l.CloseQuantity,"Posición cerrada"));l.AwaitId="";}
                    else if((DateTime.UtcNow-l.AwaitAt).TotalSeconds>35){EngineError(l.AwaitId,"Orden sin confirmación final; no reenviar");l.AwaitId="";}
                }
            }catch(Exception ex){Print("Protección motor NT8: "+ex.Message);if(l.AwaitId.Length>0){EngineError(l.AwaitId,ex.Message);l.AwaitId="";}}
        }


        private readonly HashSet<string> candleOwnedAccounts=new HashSet<string>();
        private readonly HashSet<string> candleOwnershipConflicts=new HashSet<string>();
        private readonly Dictionary<string,DateTime> candleFlatSince=new Dictionary<string,DateTime>();
        private bool IsCandleOrder(string account,Order order) {
            if(order==null)return false;
            string n=order.Name??"";
            if(string.IsNullOrEmpty(n)||n.Equals("Close",StringComparison.OrdinalIgnoreCase)||n.Equals("Flatten",StringComparison.OrdinalIgnoreCase)||n.IndexOf("Flatten",StringComparison.OrdinalIgnoreCase)>=0)return true;
            if(n.StartsWith("ROCKET_",StringComparison.OrdinalIgnoreCase)||n.StartsWith("STX",StringComparison.OrdinalIgnoreCase))return true;
            if(n.StartsWith("Entry",StringComparison.OrdinalIgnoreCase)||n.StartsWith("RocketEntry",StringComparison.OrdinalIgnoreCase))return true;
            if(n.StartsWith("TP_",StringComparison.OrdinalIgnoreCase)||n.StartsWith("SL_",StringComparison.OrdinalIgnoreCase))return true;
            return false;
        }
        private bool CanManageCandle(Account account,Instrument instrument) {
            if(account==null||instrument==null||!groupAccounts.Contains(account.Name)||!candleOwnedAccounts.Contains(account.Name)||candleOwnershipConflicts.Contains(account.Name))return false;
            if(engineLeases.Values.Any(l=>l.Account==account.Name))return false;
            return !account.Orders.Cast<Order>().Any(o=>o.Instrument.FullName==instrument.FullName&&EngineWorking(o)&&!IsCandleOrder(account.Name,o));
        }
        private void ObserveCandleExecution(ExecutionEventArgs e) {
            if(e.Execution==null||e.Execution.Account==null||e.Execution.Order==null||Instrument==null)return;
            var account=e.Execution.Account;var order=e.Execution.Order;
            if(order.Instrument.FullName!=Instrument.FullName||!candleOwnedAccounts.Contains(account.Name)||engineLeases.Values.Any(l=>l.Account==account.Name))return;
            if(IsCandleOrder(account.Name,order))return;
            AccountRiskSettings setting;
            if(accountsConfig.TryGetValue(account.Name,out setting)) {
                if(setting.Status=="PASS"||setting.Status=="BURNED"||setting.DailyStatus=="TARGET_REACHED"||setting.DailyStatus=="LOSS_LIMIT_REACHED") return;
                setting.Enabled=false;
            }
            candleOwnershipConflicts.Add(account.Name);
            PauseEntries("OWNERSHIP_CONFLICT","Se detectó una operación externa mezclada en "+account.Name+"; PropPass no cerrará esa cuenta automáticamente");
        }
        private void RefreshCandleOwnership() {
            foreach(string name in candleOwnedAccounts.ToArray()) {
                var account=GetAccountCached(name);if(account==null||Instrument==null)continue;
                AccountRiskSettings setting;if(accountsConfig.TryGetValue(name,out setting)&&(DateTime.UtcNow-setting.LastEntryTime).TotalSeconds<15)continue;
                if(!account.Positions.Cast<Position>().Any(p=>p.Instrument.FullName==Instrument.FullName&&p.MarketPosition!=MarketPosition.Flat)&&!account.Orders.Cast<Order>().Any(o=>o.Instrument.FullName==Instrument.FullName&&EngineWorking(o)&&IsCandleOrder(name,o))) {
                    DateTime since;if(!candleFlatSince.TryGetValue(name,out since)){candleFlatSince[name]=DateTime.UtcNow;continue;}
                    if((DateTime.UtcNow-since).TotalSeconds<2)continue;
                    candleOwnedAccounts.Remove(name);candleOwnershipConflicts.Remove(name);
                    candleFlatSince.Remove(name);
                }else candleFlatSince.Remove(name);
            }
        }
        private void StopCandleAccount(string name,Instrument instrument) {
            var account=GetAccountCached(name);AccountRiskSettings setting;if(accountsConfig.TryGetValue(name,out setting))setting.Enabled=false;
            if(!CanManageCandle(account,instrument)){Print("Cerrar PropPass: se excluye "+name+"; sin posición propia o gestionada por otro algoritmo");return;}
            var orders=account.Orders.Cast<Order>().Where(o=>o.Instrument.FullName==instrument.FullName&&EngineWorking(o)&&IsCandleOrder(name,o)).ToArray();
            if(orders.Length>0)QueueCancel(account,orders);
            QueueFlatten(account,new[]{instrument});
        }
        private readonly object serviceGate=new object();
        private System.Threading.Timer serviceTimer;
        private readonly string instance=Guid.NewGuid().ToString("N");
        private string connectionId="",connectionKey="",lastAck="",ackStatus="",ackDetail="";
        private bool masterTradingEnabled;
        private int pulseBusy,monitorBusy,timeframeMinutes=1;
        private DateTime lastTick=DateTime.MinValue,lastCommunicationLog=DateTime.MinValue;
        private readonly BridgeHealth bridgeHealth=new BridgeHealth(DateTime.UtcNow);
        private long candleSlot=-1;
        private double candleOpen,candleClose;
        private int CurrentBar;
        private Instrument Instrument;
        private string[] groupAccounts=new string[0];
        private DateTime realtimeStartTime=DateTime.UtcNow;
        private double lastRealtimePrice;
        private readonly HashSet<Account> subscribedAccounts=new HashSet<Account>();
        private Account[] ConnectedAccounts() {Account[] all;lock(Account.All)all=Account.All.ToArray();return all.Where(a=>a.ConnectionStatus==ConnectionStatus.Connected || a.Provider==Provider.Simulator || a.Provider==Provider.Playback).ToArray();}
        private bool CanExecute(Account a) {return a!=null&&(a.Provider==Provider.Simulator||a.Provider==Provider.Playback||a.ConnectionStatus==ConnectionStatus.Connected&&evaluationAccounts.Contains(a.Name));}
        private string[] allowedAccounts {get{return ConnectedAccounts().Where(CanExecute).Select(a=>a.Name).ToArray();}}
        private void RefreshAccounts() {foreach(var a in ConnectedAccounts())if(subscribedAccounts.Add(a))a.ExecutionUpdate+=OnGlobalExecutionUpdate;}
        private void OnGlobalExecutionUpdate(object sender,ExecutionEventArgs e) {System.Threading.Tasks.Task.Run(()=>{lock(serviceGate){if(State==State.Active){EngineExecution(e);ObserveCandleExecution(e);ProcessAccountExecution(sender,e);}}});}
        private void QueueSubmit(Account a,Order[] orders) {if(!CanExecute(a))throw new Exception("Cuenta sin autorización de ejecución");a.Dispatcher.BeginInvoke(new Action(()=>{try{a.Submit(orders);}catch(Exception ex){Print("Submit rechazado: "+ex.Message);}}));}
        private void QueueCancel(Account a,Order[] orders) {a.Dispatcher.BeginInvoke(new Action(()=>a.Cancel(orders)));}
        private void QueueFlatten(Account a,Instrument[] symbols) {var owned=symbols.Where(i=>CanManageCandle(a,i)).ToArray();if(CanExecute(a)&&owned.Length>0)a.Dispatcher.BeginInvoke(new Action(()=>{Instrument[] current;lock(serviceGate){current=owned.Where(i=>CanManageCandle(a,i)).ToArray();}if(current.Length>0)a.Flatten(current);}));}
        private bool PendingOrOpen() {
            foreach(string n in groupAccounts){
                AccountRiskSettings s;
                if(accountsConfig.TryGetValue(n,out s)){
                    if(s.Status=="PASS"||s.Status=="BURNED"||s.DailyStatus=="TARGET_REACHED"||s.DailyStatus=="LOSS_LIMIT_REACHED"){
                        var accFlat=GetAccountCached(n);if(accFlat==null)continue;
                        bool hasPos=Instrument!=null&&accFlat.Positions.Cast<Position>().Any(p=>p.Instrument.FullName==Instrument.FullName&&p.MarketPosition!=MarketPosition.Flat);
                        if(!hasPos)continue;
                    }
                }
                var a=GetAccountCached(n);if(a==null)continue;
                if(Instrument!=null&&a.Positions.Cast<Position>().Any(p=>p.Instrument.FullName==Instrument.FullName&&p.MarketPosition!=MarketPosition.Flat))return true;
                if(Instrument!=null&&a.Orders.Cast<Order>().Any(o=>o.Instrument.FullName==Instrument.FullName&&(o.OrderState==OrderState.Initialized||o.OrderState==OrderState.Submitted||o.OrderState==OrderState.Accepted||o.OrderState==OrderState.Working||o.OrderState==OrderState.PartFilled||o.OrderState==OrderState.CancelPending)))return true;
            }
            return false;
        }

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
                LoadEvaluationAccounts();LoadConfiguration();foreach(var item in accountsConfig.Values)item.Enabled=false;
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
                                    if(working.Any(o=>IsCandleOrder(name,o)))candleOwnedAccounts.Add(name);
                                    setting.Enabled=candleOwnedAccounts.Contains(name);
                                }
                            }
                        }
                    }catch(Exception ex){Print("No se pudo recuperar el alcance anterior: "+ex.Message);}
                }
                masterTradingEnabled=false;
                RefreshAccounts();LoadEngineLeases();try{ReserveAccounts(groupAccounts.Concat(engineLeases.Values.Select(l=>l.Account)));}catch(Exception ex){groupAccounts=new string[0];Print(ex.Message);}
                serviceTimer=new System.Threading.Timer(ServiceTick,null,1000,1000);
                Print("Servicio iniciado sin interfaz nativa. Configuración y grupos se gestionan desde la web.");
            } else if(State==State.Terminated) {
                ReleaseAccountReservations();masterTradingEnabled=false;if(serviceTimer!=null){serviceTimer.Dispose();serviceTimer=null;}
                if(Instrument!=null)Instrument.MarketData.Update-=ServiceMarketData;
                foreach(var acc in subscribedAccounts)acc.ExecutionUpdate-=OnGlobalExecutionUpdate;subscribedAccounts.Clear();
                foreach(var request in engineBars.Values)request.Dispose();engineBars.Clear();
                foreach(var feed in engineFeeds.Values)feed.MarketData.Update-=EngineMarketData;
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
                CheckBridgeHealth();
                if(CurrentBar>=2 && masterTradingEnabled && !PendingOrOpen()) {
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
                    CheckBridgeHealth();
                    RefreshAccounts();RefreshCandleOwnership();MonitorEngine();if(Instrument!=null)PeriodicMonitoring();
                    if(masterTradingEnabled && !accountsConfig.Values.Any(s=>s.Enabled&&s.Status=="EN PROCESO"&&s.DailyStatus=="EN PROCESO")) {
                        PauseEntries("NO_ELIGIBLE_ACCOUNTS","Todas las cuentas alcanzaron sus límites o quedaron inactivas");
                    }
                    var rows=new List<string>();int quantity=0;
                    foreach(Account acc in ConnectedAccounts()) {
                        string name=acc.Name;
                        Position pos=Instrument==null?null:acc.Positions.Cast<Position>().FirstOrDefault(p=>p.Instrument.FullName==Instrument.FullName && p.MarketPosition!=MarketPosition.Flat);
                        if(engineLeases.Values.Any(l=>l.Account==name))pos=acc.Positions.Cast<Position>().FirstOrDefault(p=>p.MarketPosition!=MarketPosition.Flat);
                        int qty=pos==null?0:pos.Quantity;if(engineLeases.Values.Any(l=>l.Account==name))qty=acc.Positions.Cast<Position>().Where(p=>p.MarketPosition!=MarketPosition.Flat).Sum(p=>p.Quantity);quantity+=qty;
                        AccountRiskSettings settings;accountsConfig.TryGetValue(name,out settings);
                        var working=acc.Orders.Cast<Order>().Where(o=>(Instrument!=null&&o.Instrument.FullName==Instrument.FullName||engineLeases.Values.Any(l=>l.Account==name&&l.Symbol==o.Instrument.FullName))&&(o.OrderState==OrderState.Working||o.OrderState==OrderState.Accepted||o.OrderState==OrderState.Submitted||o.OrderState==OrderState.PartFilled)).Select(o=>"{\"name\":"+J(o.Name)+",\"type\":"+J(o.OrderType.ToString())+",\"state\":"+J(o.OrderState.ToString())+",\"quantity\":"+o.Quantity+",\"limit\":"+N(o.LimitPrice)+",\"stop\":"+N(o.StopPrice)+"}");
                        double cash=acc.Get(AccountItem.CashValue,Currency.UsDollar),open=acc.Get(AccountItem.UnrealizedProfitLoss,Currency.UsDollar);
                        double daily=settings==null?acc.Get(AccountItem.RealizedProfitLoss,Currency.UsDollar)+open:cash+open-settings.DailyStartBalance-(settings.NinjaTraderHandlesCommissions?0:settings.DailyCommissions);
                        rows.Add("{\"name\":"+J(name)+",\"connected\":true,\"execution_allowed\":"+B(CanExecute(acc))+",\"provider\":"+J(acc.Provider.ToString())+",\"enabled\":"+B(settings!=null&&settings.Enabled)+",\"position_quantity\":"+qty+
                            ",\"direction\":"+J(pos==null?"Flat":pos.MarketPosition.ToString())+",\"balance\":"+N(acc.Get(AccountItem.CashValue,Currency.UsDollar))+
                            ",\"unrealized\":"+N(acc.Get(AccountItem.UnrealizedProfitLoss,Currency.UsDollar))+
                            ",\"status\":"+J(settings==null?"SIN CONFIGURAR":settings.Status)+",\"daily_status\":"+J(settings==null?"":settings.DailyStatus)+
                            ",\"lots\":"+(settings==null?1:settings.Lots)+",\"tp_usd\":"+N(settings==null?100:settings.TpUsd)+",\"sl_usd\":"+N(settings==null?100:settings.SlUsd)+"}");
                        rows[rows.Count-1]=rows[rows.Count-1].TrimEnd('}')+",\"proppass_position_quantity\":"+(candleOwnedAccounts.Contains(name)&&!engineLeases.Values.Any(l=>l.Account==name)&&pos!=null&&Instrument!=null&&pos.Instrument.FullName==Instrument.FullName?pos.Quantity:0)+",\"proppass_working_orders\":"+(candleOwnedAccounts.Contains(name)&&!engineLeases.Values.Any(l=>l.Account==name)?acc.Orders.Cast<Order>().Count(o=>Instrument!=null&&o.Instrument.FullName==Instrument.FullName&&EngineWorking(o)&&IsCandleOrder(name,o)):0)+",\"working_orders\":["+string.Join(",",working)+"],\"daily_pnl\":"+N(daily)+
                            ",\"daily_loss_limit\":"+N(settings==null?0:settings.DailyLossLimit)+",\"daily_profit_limit\":"+N(settings==null?0:settings.DailyProfitLimit)+
                            ",\"wins\":"+(settings==null?0:settings.TradesWon)+",\"losses\":"+(settings==null?0:settings.TradesLost)+",\"closed_trades\":"+(settings==null?0:settings.TradesClosed)+"}";
                    }
                    string events;lock(serviceEvents)events=string.Join(",",serviceEvents.Select(J));
                    payload="{\"engine_results\":"+EngineResults()+",\"pause_code\":"+J(bridgeHealth.PauseCode)+",\"pause_reason\":"+J(bridgeHealth.PauseReason)+",\"bridge_failures\":"+bridgeHealth.Failures+",\"bridge_last_error\":"+J(bridgeHealth.LastError)+",\"pause_at\":"+J(bridgeHealth.PauseAt==DateTime.MinValue?"":bridgeHealth.PauseAt.ToString("o"))+",\"version\":\"1.7.0-pending\",\"kind\":\"candle_service_v1\",\"account\":\"Sim101\",\"instance\":"+J(instance)+
                        ",\"realtime\":true,\"account_available\":"+B(rows.Count>0)+",\"master_enabled\":"+B(masterTradingEnabled)+
                        ",\"symbol\":"+J(Instrument==null?"":Instrument.FullName)+",\"timeframe_minutes\":"+timeframeMinutes+
                        ",\"data_ready\":"+B(Instrument!=null&&(DateTime.UtcNow-lastTick).TotalSeconds<15)+",\"closed_bars\":"+CurrentBar+
                        ",\"next_account\":"+J(groupAccounts.FirstOrDefault(n=>accountsConfig.ContainsKey(n)&&accountsConfig[n].Enabled&&accountsConfig[n].Status=="EN PROCESO"&&accountsConfig[n].DailyStatus=="EN PROCESO"))+
                        ",\"position_quantity\":"+quantity+",\"accounts\":["+string.Join(",",rows)+"],\"events\":["+events+"]"+
                        ",\"last_ack\":"+J(lastAck)+",\"ack_status\":"+J(ackStatus)+",\"ack_detail\":"+J(ackDetail)+"}";
                }
                if(string.IsNullOrEmpty(connectionId)||string.IsNullOrEmpty(connectionKey)) {
                    string pairing=Path.Combine(Path.GetDirectoryName(configFilePath),"CandleBridge.key");
                    if(File.Exists(pairing)){string[] lines=File.ReadAllLines(pairing);if(lines.Length>=2){connectionId=lines[0].Trim();connectionKey=lines[1].Trim();}}
                    if(string.IsNullOrEmpty(connectionId)||string.IsNullOrEmpty(connectionKey))return;
                }
                if(System.Threading.Interlocked.CompareExchange(ref pulseBusy,1,0)!=0)return;
                System.Threading.Tasks.Task.Run(()=>SendPulse(payload));
            } catch(Exception ex) {PauseEntries("SERVICE_ERROR",ex.Message);}
            finally {System.Threading.Interlocked.Exchange(ref monitorBusy,0);}
        }
        private void PauseEntries(string code,string reason) {
            masterTradingEnabled=false;bridgeHealth.Pause(code,reason,DateTime.UtcNow);Print("ENTRADAS PAUSADAS ["+code+"]: "+reason+". Reanuda explícitamente desde PropPass.");
        }
        private void CheckBridgeHealth() {
            if(masterTradingEnabled&&bridgeHealth.Check(DateTime.UtcNow)) {masterTradingEnabled=false;Print("ENTRADAS PAUSADAS ["+bridgeHealth.PauseCode+"]: "+bridgeHealth.PauseReason+". Reanuda explícitamente desde PropPass.");}
        }
        private Instrument PrepareCandleFeed(string command) {
            var parts=command.Split('|');
            if(parts.Length<4||parts[1]!=instance||(parts[3]!="configure"&&parts[3]!="reset"))return null;
            var symbol=parts.Skip(4).FirstOrDefault(x=>x.StartsWith("symbol="));
            if(symbol==null)throw new Exception("Falta instrumento");
            return NinjaTrader.Cbi.Instrument.GetInstrument(symbol.Substring(7));
        }
        private void SendPulse(string payload) {
            Instrument prepared=null,previous=null;bool subscribed=false;
            try {
                var request=(System.Net.HttpWebRequest)System.Net.WebRequest.Create("http://127.0.0.1:8000/api/ninja/bridge/"+Uri.EscapeDataString(connectionId)+"/pulse");
                request.Method="POST";request.ContentType="application/json";request.Timeout=2000;request.ReadWriteTimeout=2000;
                request.Headers["X-Stratix-Key"]=connectionKey;
                byte[] bytes=Encoding.UTF8.GetBytes(payload);request.ContentLength=bytes.Length;
                using(var stream=request.GetRequestStream())stream.Write(bytes,0,bytes.Length);
                string command;using(var response=request.GetResponse())using(var reader=new StreamReader(response.GetResponseStream()))command=reader.ReadToEnd();
                if(!string.IsNullOrWhiteSpace(command)&&!PrepareEngineFeed(command))command="";
                prepared=string.IsNullOrWhiteSpace(command)?null:PrepareCandleFeed(command);
                previous=Instrument;
                // A subscription can wait for its callback: never hold serviceGate here.
                if(prepared!=null&&prepared!=previous){prepared.MarketData.Update+=ServiceMarketData;subscribed=true;}
                lock(serviceGate){if(State!=State.Active)return;CheckBridgeHealth();bool recovered=bridgeHealth.Failures>0;bridgeHealth.Success(DateTime.UtcNow);if(recovered)Print(bridgeHealth.Paused?"Conexión recuperada; las entradas siguen pausadas. Motivo: "+bridgeHealth.PauseReason:"Conexión recuperada de un fallo transitorio; las entradas conservaron su estado.");if(!string.IsNullOrWhiteSpace(command))ApplyServiceCommand(command,prepared);}
            }catch(Exception ex) {lock(serviceGate) {
                    if(State!=State.Active)return;
                    var web=ex as System.Net.WebException;var response=web==null?null:web.Response as System.Net.HttpWebResponse;
                    int status=response==null?0:(int)response.StatusCode;
                    string error=web==null?ex.GetType().Name:web.Status.ToString()+(status==0?"":" HTTP "+status);
                    if(response!=null)response.Close();bridgeHealth.Failure(error);
                    if((DateTime.UtcNow-lastCommunicationLog).TotalSeconds>=30) {Print("Comunicación con Stratix: "+error+"; fallos consecutivos="+bridgeHealth.Failures+". Se toleran interrupciones menores de 10 segundos.");lastCommunicationLog=DateTime.UtcNow;}
                    if(masterTradingEnabled&&BridgeHealth.FatalHttp(status))PauseEntries("COMMUNICATION_REJECTED","El servidor rechazó el conector: "+error);
                    else CheckBridgeHealth();
                }}
            finally{
                if(subscribed){if(Instrument!=prepared)prepared.MarketData.Update-=ServiceMarketData;else if(previous!=null)previous.MarketData.Update-=ServiceMarketData;}
                System.Threading.Interlocked.Exchange(ref pulseBusy,0);
            }
        }
        private void ApplyServiceCommand(string command,Instrument prepared) {
            string[] parts=command.Split('|');if(parts.Length<4||parts[0]==lastAck)return;
            lastAck=parts[0];ackStatus="REJECTED";
            try {
                if(parts[1]!=instance || (DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds>double.Parse(parts[2],System.Globalization.CultureInfo.InvariantCulture))throw new Exception("Instancia incorrecta o comando vencido");
                string action=parts[3];
                var values=new Dictionary<string,string>();foreach(string part in parts.Skip(4)){int split=part.IndexOf('=');if(split>0)values[part.Substring(0,split)]=part.Substring(split+1);}
                if(action=="engine"){EngineCommand(lastAck,values);}
                else if(action=="authorize-evaluation") {
                    string[] selected=values["accounts"].Split(',').Where(n=>n.Length>0).ToArray();
                    if(selected.Any(n=>!ConnectedAccounts().Any(a=>a.Name==n)))throw new Exception("Cuenta no conectada");
                    if(evaluationAccounts.Except(selected).Any(n=>{var a=GetAccountCached(n);return a!=null&&(a.Positions.Cast<Position>().Any(p=>p.MarketPosition!=MarketPosition.Flat)||a.Orders.Cast<Order>().Any(EngineWorking));}))throw new Exception("No retires una autorización con posiciones u órdenes activas");
                    evaluationAccounts=new HashSet<string>(selected);File.WriteAllLines(Path.Combine(Path.GetDirectoryName(configFilePath),"EvaluationAccounts.txt"),selected);
                }
                else if(action=="release") {
                    if(engineLeases.Count>0)throw new Exception("Detén primero las asignaciones del motor/copy antes de liberar las cuentas");
                    if(ConnectedAccounts().Where(a=>accountReservations.ContainsKey(a.Name)).Any(a=>a.Positions.Cast<Position>().Any(p=>p.MarketPosition!=MarketPosition.Flat)||a.Orders.Cast<Order>().Any(EngineWorking)))throw new Exception("No se liberan cuentas con posiciones u órdenes");
                    PauseEntries("RELEASED","Cuentas liberadas");foreach(var setting in accountsConfig.Values)setting.Enabled=false;groupAccounts=new string[0];ReleaseAccountReservations();
                    File.WriteAllLines(Path.Combine(Path.GetDirectoryName(configFilePath),"CandleServiceScope.txt"),new[]{"","1",""});
                }
                else if(action=="pause")PauseEntries("MANUAL","Pausa solicitada desde la web");
                else if(action=="account_pause"||action=="account_resume") {
                    string name=values["account"];AccountRiskSettings s;
                    if(!groupAccounts.Contains(name)||!accountsConfig.TryGetValue(name,out s))throw new Exception("Cuenta fuera del grupo aplicado");
                    if(action=="account_resume"&&(s.Status!="EN PROCESO"||s.DailyStatus!="EN PROCESO"))throw new Exception("Cuenta bloqueada por límites; reinicia su seguimiento explícitamente");
                    s.Enabled=action=="account_resume";SaveConfiguration();
                }
                else if(action=="close-stop") {
                    PauseEntries("CLOSE_STOP","Cerrar y detener solicitado desde la web");
                    string[] targets=values["accounts"].Split(',');if(targets.Any(n=>!allowedAccounts.Contains(n)))throw new Exception("Cuenta no autorizada");
                    Instrument target=NinjaTrader.Cbi.Instrument.GetInstrument(values["symbol"]);if(target==null)throw new Exception("Instrumento desconocido");
                    if(Instrument==null||target.FullName!=Instrument.FullName||targets.Any(n=>!groupAccounts.Contains(n)))throw new Exception("El cierre está limitado al instrumento y cuentas del grupo PropPass aplicado");
                    foreach(string name in targets)StopCandleAccount(name,target);
                    SaveConfiguration();
                }
                else if(action=="configure" || action=="reset") {
                    if(masterTradingEnabled)throw new Exception("Pausa primero las entradas");
                    string[] selected=values["accounts"].Split(',');
                    if(values["accounts"].Split(',').Any(n=>engineLeases.Values.Any(l=>l.Account==n)))throw new Exception("Una cuenta seleccionada pertenece a un algoritmo del motor; detén esa asignación primero");
                    foreach(string name in selected) {
                        Account acc=GetAccountCached(name);if(acc!=null && acc.Positions.Cast<Position>().Any(p=>p.MarketPosition!=MarketPosition.Flat))throw new Exception("Configura con las cuentas simuladas sin posiciones");
                        if(acc!=null && acc.Orders.Cast<Order>().Any(o=>o.OrderState==OrderState.Working||o.OrderState==OrderState.Accepted||o.OrderState==OrderState.Submitted||o.OrderState==OrderState.PartFilled))throw new Exception("Hay órdenes pendientes en la cuenta simulada");
                    }
                    if(selected.Length==0||selected.Any(a=>!allowedAccounts.Contains(a)||GetAccountCached(a)==null))throw new Exception("Solo cuentas simuladas autorizadas y disponibles");
                    Instrument next=prepared;if(next==null)throw new Exception("Instrumento no disponible");
                    int minutes=int.Parse(values["timeframe_minutes"]);if(minutes<1||minutes>60)throw new Exception("Temporalidad inválida");
                    if(Instrument==null||Instrument.FullName!=next.FullName||minutes!=timeframeMinutes) {
                        Instrument=next;timeframeMinutes=minutes;candleSlot=-1;CurrentBar=0;lastTick=DateTime.MinValue;
                    }
                    Func<string,double> number=name=>double.Parse(values[name],System.Globalization.CultureInfo.InvariantCulture);
                    ReserveAccounts(selected.Concat(engineLeases.Values.Select(l=>l.Account)));groupAccounts=selected;
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
                    bridgeHealth.Resume(DateTime.UtcNow);masterTradingEnabled=true;
                } else throw new Exception("Acción desconocida");
                ackStatus="APPLIED";ackDetail=action;Print("Comando web confirmado: "+action);
            }catch(Exception ex){PauseEntries("COMMAND_REJECTED",ex.Message);ackDetail=ex.Message;Print("Comando rechazado: "+ex.Message);}
        }
        private Account GetAccountCached(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
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
            if (!CanExecute(acc)) throw new Exception("Solo simulación autorizada");
            candleOwnedAccounts.Add(acc.Name);
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
                    QueueSubmit(acc,new[] { orderObj });
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
                    QueueCancel(acc,ordersToCancel.ToArray());
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
                QueueFlatten(acc,new[] { Instrument });
                return;
            }
            else if (pos.MarketPosition == MarketPosition.Short && slPrice <= currentPrice + safetyBuffer)
            {
                Print(string.Format("[CCC] [WARN] SL calculated ({0}) <= precio actual con buffer ({1}). Ejecutando cierre a mercado (Flatten) de seguridad para {2}.", slPrice, currentPrice + safetyBuffer, settings.Name));
                QueueFlatten(acc,new[] { Instrument });
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
                    QueueSubmit(acc,new[] { tpOrderObj, slOrderObj });
                }
            }
            catch (Exception ex)
            {
                Print("[CCC] Error enviando TP/SL OCO: " + ex.Message);
            }
        }

        private void ProcessAccountExecution(object sender, ExecutionEventArgs e)
        {
            if(e.Execution!=null && e.Execution.Account!=null && (!candleOwnedAccounts.Contains(e.Execution.Account.Name)||candleOwnershipConflicts.Contains(e.Execution.Account.Name)))return;
            if(e.Execution!=null && e.Execution.Order!=null && e.Execution.Order.Name.StartsWith("STXG_"))return;
            if (Instrument == null || e.Execution == null || e.Execution.Account == null || e.Execution.Order == null || e.Execution.Order.Instrument.FullName != Instrument.FullName || !groupAccounts.Contains(e.Execution.Account.Name)) return;
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
                        if (!CanManageCandle(GetAccountCached(kvp.Key),Instrument) || engineLeases.Values.Any(l=>l.Account==kvp.Key) || !groupAccounts.Contains(kvp.Key) || removedAccounts.Contains(kvp.Key) || settings.Status != "EN PROCESO") continue;

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


 }
}

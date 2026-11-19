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



        private int rocketTrend=20,rocketLimits=5,rocketLimitContracts=2,rocketStops=0,rocketStopContracts=2,rocketMax=30;
        private string rocketDirection="AUTO";
        private readonly List<double> rocketCloses=new List<double>();
        private double rocketEma=double.NaN;
        private class RocketBasket {public bool Closing;public DateTime FlatAt;public int Quantity;public double Average;public HashSet<string> Used=new HashSet<string>();public Dictionary<string,Order> Grid=new Dictionary<string,Order>();}
        private readonly Dictionary<string,RocketBasket> rocketBaskets=new Dictionary<string,RocketBasket>();
        private void RocketSave() {
            if(string.IsNullOrEmpty(configFilePath))return;
            File.WriteAllLines(Path.Combine(Path.GetDirectoryName(configFilePath),"RocketBaskets.txt"),rocketBaskets.Select(x=>x.Key+"|"+(x.Value.Closing?"1":"0")+"|"+string.Join(",",x.Value.Used)));
        }
        private void RocketLoad() {
            string root=Path.GetDirectoryName(configFilePath),path=Path.Combine(root,"RocketGrid.txt");
            if(File.Exists(path)){var a=File.ReadAllLines(path);if(a.Length==8){rocketTrend=20;rocketDirection=a[1];rocketLimits=int.Parse(a[2]);rocketLimitContracts=int.Parse(a[3]);rocketStops=int.Parse(a[4]);rocketStopContracts=int.Parse(a[5]);rocketMax=int.Parse(a[6]);}}
            path=Path.Combine(root,"RocketBaskets.txt");if(File.Exists(path))foreach(var line in File.ReadAllLines(path)){var a=line.Split('|');if(a.Length==3)rocketBaskets[a[0]]=new RocketBasket{Closing=a[1]=="1",Used=new HashSet<string>(a[2].Split(',').Where(x=>x.Length>0))};}
        }
        private void RocketConfigure(Dictionary<string,string> v) {
            if(PendingOrOpen())throw new Exception("Configura RocketPass con el grupo anterior flat y sin pendientes");
            int trend=int.Parse(v["trend_period"]),limits=int.Parse(v["limit_count"]),stops=int.Parse(v["stop_count"]),lc=int.Parse(v["limit_contracts"]),sc=int.Parse(v["stop_contracts"]),maximum=int.Parse(v["max_contracts"]);
            if(trend!=20||int.Parse(v["timeframe_minutes"])!=5)throw new Exception("RocketPass requiere M5 y EMA 20; actualiza y aplica el grupo");
            if(limits<0||limits>10||stops<0||stops>10||lc<1||sc<1||maximum>100||int.Parse(v["lots"])+limits*lc+stops*sc>maximum)throw new Exception("Cuadrícula inválida o superior al máximo total de contratos");
            rocketTrend=trend;rocketLimits=limits;rocketStops=stops;rocketLimitContracts=lc;rocketStopContracts=sc;rocketMax=maximum;rocketDirection=v["direction"];
            if(!new[]{"AUTO","LONG","SHORT"}.Contains(rocketDirection))throw new Exception("Dirección inválida");
            rocketBaskets.Clear();RocketSave();
            File.WriteAllLines(Path.Combine(Path.GetDirectoryName(configFilePath),"RocketGrid.txt"),new[]{rocketTrend.ToString(),rocketDirection,rocketLimits.ToString(),lc.ToString(),rocketStops.ToString(),sc.ToString(),maximum.ToString(),"v1"});
        }
        private void RocketOnBar(double close) {
            if(timeframeMinutes!=5)return;
            if(rocketCloses.Count==0)rocketEma=double.NaN;
            if(rocketCloses.Count<rocketTrend){rocketCloses.Add(close);if(rocketCloses.Count<rocketTrend)return;rocketEma=rocketCloses.Average();}
            else rocketEma=RocketMath.NextEma(rocketEma,close,rocketTrend);
            if(!masterTradingEnabled||PendingOrOpen()||rocketBaskets.Values.Any(x=>x.Closing))return;
            int signal=RocketMath.EmaSignal(close,rocketEma,rocketDirection);
            Print("RocketPass M5 · cierre="+N(close)+" · EMA20="+N(rocketEma)+" · señal="+signal);
            EvaluateEntrySignals(signal==1,signal==-1);
        }
        private bool RocketGridOrder(Order o) {return o!=null&&(o.Name.StartsWith("ROCKET_LIMIT_")||o.Name.StartsWith("ROCKET_STOP_"));}
        private void RocketCancelGrid(Account acc) {var orders=acc.Orders.Cast<Order>().Where(o=>Instrument!=null&&o.Instrument.FullName==Instrument.FullName&&RocketGridOrder(o)&&EngineWorking(o)).ToArray();if(orders.Length>0)QueueCancel(acc,orders);}
        private void RocketExecution(ExecutionEventArgs e) {
            if(e.Execution==null||e.Execution.Order==null||!rocketBaskets.ContainsKey(e.Execution.Account.Name))return;
            var order=e.Execution.Order;var basket=rocketBaskets[e.Execution.Account.Name];
            if(RocketGridOrder(order))basket.Used.Add(order.Name);
            if(order.Name.StartsWith("ROCKET_TP_")||order.Name.StartsWith("ROCKET_SL_")){basket.Closing=true;RocketCancelGrid(e.Execution.Account);}
            RocketSave();
        }
        private void RocketMonitor() {
            if(Instrument==null)return;
            foreach(string name in groupAccounts)try {
                AccountRiskSettings s;if(!accountsConfig.TryGetValue(name,out s))continue;var acc=GetAccountCached(name);if(acc==null)continue;
                var p=acc.Positions.Cast<Position>().FirstOrDefault(x=>x.Instrument.FullName==Instrument.FullName&&x.MarketPosition!=MarketPosition.Flat);
                RocketBasket b;if(!rocketBaskets.TryGetValue(name,out b)){b=new RocketBasket();rocketBaskets[name]=b;}
                foreach(var o in acc.Orders.Cast<Order>().Where(o=>o.Instrument.FullName==Instrument.FullName&&RocketGridOrder(o)&&EngineWorking(o)))b.Grid[o.Name]=o;
                if(!CanManageCandle(acc,Instrument)){RocketCancelGrid(acc);if(p!=null&&candleOwnedAccounts.Contains(name))PauseEntries("OWNERSHIP_CONFLICT","RocketPass no gestionará una posición mezclada: "+name);continue;}
                double cash=acc.Get(AccountItem.CashValue,Currency.UsDollar),equity=cash+acc.Get(AccountItem.UnrealizedProfitLoss,Currency.UsDollar);
                string day=DateTime.UtcNow.AddHours(-3).ToString("yyyyMMdd");
                if(s.LastResetDate!=day){s.LastResetDate=day;s.DailyStartBalance=cash;s.DailyCommissions=0;s.DailyStatus="EN PROCESO";SaveConfiguration();}
                double daily=equity-s.DailyStartBalance;
                if((s.Target>0&&equity>=s.StartBalance+s.Target)||(s.DailyProfitLimit>0&&daily>=s.DailyProfitLimit)){s.Status="PASS";s.DailyStatus="TARGET_REACHED";s.Enabled=false;b.Closing=true;}
                if((s.MaxLoss>0&&equity<=s.StartBalance-s.MaxLoss)||(s.DailyLossLimit>0&&daily<=-s.DailyLossLimit)){s.Status="BURNED";s.DailyStatus="LOSS_LIMIT_REACHED";s.Enabled=false;b.Closing=true;}
                if(b.Closing){
                    RocketCancelGrid(acc);var entries=acc.Orders.Cast<Order>().Any(o=>o.Instrument.FullName==Instrument.FullName&&RocketGridOrder(o)&&EngineWorking(o));
                    if(!entries&&p!=null){CancelTpSlOrders(acc,s);if(!acc.Orders.Cast<Order>().Any(o=>o.Instrument.FullName==Instrument.FullName&&EngineWorking(o)))QueueFlatten(acc,new[]{Instrument});}
                    if(!entries&&p==null&&!acc.Orders.Cast<Order>().Any(o=>o.Instrument.FullName==Instrument.FullName&&EngineWorking(o))){if(b.FlatAt==DateTime.MinValue)b.FlatAt=DateTime.UtcNow;if((DateTime.UtcNow-b.FlatAt).TotalSeconds>=2){b.Closing=false;b.FlatAt=DateTime.MinValue;b.Used.Clear();b.Grid.Clear();b.Quantity=0;RocketSave();SaveConfiguration();}}
                    continue;
                }
                if(p==null){RocketCancelGrid(acc);if((DateTime.UtcNow-s.LastEntryTime).TotalSeconds>3){b.Used.Clear();b.Grid.Clear();b.Quantity=0;RocketSave();}continue;}
                if(p.Quantity>rocketMax){s.Enabled=false;b.Closing=true;PauseEntries("MAX_CONTRACTS","Se superó el máximo de contratos RocketPass");RocketSave();continue;}
                double point=Instrument.MasterInstrument.PointValue,tick=Instrument.MasterInstrument.TickSize;int sign=p.MarketPosition==MarketPosition.Long?1:-1;
                double loss=s.SlUsd,profit=s.TpUsd;
                if(s.MaxLoss>0)loss=Math.Min(loss,cash-(s.StartBalance-s.MaxLoss));if(s.DailyLossLimit>0)loss=Math.Min(loss,cash-(s.DailyStartBalance-s.DailyLossLimit));
                if(s.Target>0)profit=Math.Min(profit,s.StartBalance+s.Target-cash);if(s.DailyProfitLimit>0)profit=Math.Min(profit,s.DailyStartBalance+s.DailyProfitLimit-cash);
                if(loss<=0||profit<=0){b.Closing=true;RocketSave();continue;}
                var protection=RocketMath.Protection(p.AveragePrice,p.Quantity,point,loss,profit,sign,tick);double sl=protection[0],tp=protection[1];
                double quote=sign==1?Instrument.MarketData.Bid.Price:Instrument.MarketData.Ask.Price;
                if(quote>0&&(sign*(quote-sl)<=0||sign*(tp-quote)<=0)){b.Closing=true;RocketSave();continue;}
                RocketProtection(acc,s,p,sl,tp);
                if(!masterTradingEnabled||!s.Enabled){RocketCancelGrid(acc);continue;}
                bool changed=b.Quantity!=p.Quantity||b.Average!=p.AveragePrice;b.Quantity=p.Quantity;b.Average=p.AveragePrice;
                s.AvgEntryPrice=p.AveragePrice;s.TotalPositionSize=p.Quantity;s.Direction=sign==1?"LONG":"SHORT";
                RocketLevels(acc,b,p,sl,false,rocketLimits,rocketLimitContracts,changed);
                RocketLevels(acc,b,p,tp,true,rocketStops,rocketStopContracts,changed);
            }catch(Exception ex){PauseEntries("ROCKET_ERROR",ex.Message);}
        }
        private void RocketProtection(Account acc,AccountRiskSettings s,Position p,double sl,double tp) {
            if(s.SlOrder==null||s.TpOrder==null){
                s.SlOrder=acc.Orders.Cast<Order>().FirstOrDefault(o=>o.Name=="ROCKET_SL_"+s.Name&&EngineWorking(o));s.TpOrder=acc.Orders.Cast<Order>().FirstOrDefault(o=>o.Name=="ROCKET_TP_"+s.Name&&EngineWorking(o));
            }
            var action=p.MarketPosition==MarketPosition.Long?OrderAction.Sell:OrderAction.Buy;
            if(s.SlOrder==null&&s.TpOrder==null){string oco="ROCKET_"+Guid.NewGuid().ToString("N");s.SlOrder=acc.CreateOrder(Instrument,action,OrderType.StopMarket,OrderEntry.Automated,TimeInForce.Gtc,p.Quantity,0,sl,oco,"ROCKET_SL_"+s.Name,DateTime.MinValue,null);s.TpOrder=acc.CreateOrder(Instrument,action,OrderType.Limit,OrderEntry.Automated,TimeInForce.Gtc,p.Quantity,tp,0,oco,"ROCKET_TP_"+s.Name,DateTime.MinValue,null);QueueSubmit(acc,new[]{s.SlOrder,s.TpOrder});return;}
            if(s.SlOrder==null||s.TpOrder==null||s.SlOrder.OrderState==OrderState.Rejected||s.TpOrder.OrderState==OrderState.Rejected){rocketBaskets[s.Name].Closing=true;RocketCancelGrid(acc);return;}
            if((s.SlOrder.OrderState==OrderState.Working||s.SlOrder.OrderState==OrderState.Accepted)&&(s.TpOrder.OrderState==OrderState.Working||s.TpOrder.OrderState==OrderState.Accepted)&&(s.SlOrder.Quantity!=p.Quantity||s.SlOrder.StopPrice!=sl||s.TpOrder.Quantity!=p.Quantity||s.TpOrder.LimitPrice!=tp)){
                s.SlOrder.QuantityChanged=p.Quantity;s.SlOrder.StopPriceChanged=sl;s.TpOrder.QuantityChanged=p.Quantity;s.TpOrder.LimitPriceChanged=tp;acc.Dispatcher.BeginInvoke(new Action(()=>acc.Change(new[]{s.SlOrder,s.TpOrder})));
            }
        }
        private void RocketLevels(Account acc,RocketBasket b,Position p,double edge,bool favor,int count,int contracts,bool changed) {
            string prefix=favor?"ROCKET_STOP_":"ROCKET_LIMIT_";var remaining=Enumerable.Range(1,count).Select(i=>prefix+i).Where(n=>!b.Used.Contains(n)).ToArray();
            double tick=Instrument.MasterInstrument.TickSize;int sign=p.MarketPosition==MarketPosition.Long?1:-1;
            var prices=RocketMath.Levels(p.AveragePrice,edge,tick,remaining.Length);
            for(int i=0;i<remaining.Length;i++){
                string name=remaining[i];double price=prices[i];
                double quote=sign==1?Instrument.MarketData.Ask.Price:Instrument.MarketData.Bid.Price;
                if(quote<=0||(favor?sign*(price-quote)<=tick:sign*(quote-price)<=tick))continue;
                Order o;if(b.Grid.TryGetValue(name,out o)){
                    if(o.Filled>0){b.Used.Add(name);RocketSave();continue;}
                    if(o.OrderState==OrderState.Rejected||o.OrderState==OrderState.Cancelled){b.Used.Add(name);RocketSave();continue;}
                    if(changed&&(o.OrderState==OrderState.Working||o.OrderState==OrderState.Accepted)&&(favor?o.StopPrice:o.LimitPrice)!=price){if(favor)o.StopPriceChanged=price;else o.LimitPriceChanged=price;acc.Dispatcher.BeginInvoke(new Action(()=>acc.Change(new[]{o})));}
                    continue;
                }
                int pending=b.Grid.Values.Where(EngineWorking).Sum(x=>x.Quantity-x.Filled);if(p.Quantity+pending+contracts>rocketMax)continue;
                o=acc.CreateOrder(Instrument,sign==1?OrderAction.Buy:OrderAction.SellShort,favor?OrderType.StopMarket:OrderType.Limit,OrderEntry.Automated,TimeInForce.Gtc,contracts,favor?0:price,favor?price:0,"",name,DateTime.MinValue,null);b.Grid[name]=o;QueueSubmit(acc,new[]{o});
            }
        }

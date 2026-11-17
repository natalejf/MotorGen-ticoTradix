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

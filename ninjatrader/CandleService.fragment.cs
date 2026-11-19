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
        private bool PendingOrOpen() {foreach(string n in groupAccounts){var a=GetAccountCached(n);if(a==null)continue;if(a.Positions.Cast<Position>().Any(p=>p.Instrument.FullName==Instrument.FullName&&p.MarketPosition!=MarketPosition.Flat)||a.Orders.Cast<Order>().Any(o=>o.Instrument.FullName==Instrument.FullName&&(o.OrderState==OrderState.Initialized||o.OrderState==OrderState.Submitted||o.OrderState==OrderState.Accepted||o.OrderState==OrderState.Working||o.OrderState==OrderState.PartFilled||o.OrderState==OrderState.CancelPending)))return true;}return false;}

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
                if(string.IsNullOrEmpty(connectionId)||string.IsNullOrEmpty(connectionKey))return;
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
        private void SendPulse(string payload) {
            try {
                var request=(System.Net.HttpWebRequest)System.Net.WebRequest.Create("http://127.0.0.1:8000/api/ninja/bridge/"+Uri.EscapeDataString(connectionId)+"/pulse");
                request.Method="POST";request.ContentType="application/json";request.Timeout=2000;request.ReadWriteTimeout=2000;
                request.Headers["X-Stratix-Key"]=connectionKey;
                byte[] bytes=Encoding.UTF8.GetBytes(payload);request.ContentLength=bytes.Length;
                using(var stream=request.GetRequestStream())stream.Write(bytes,0,bytes.Length);
                string command;using(var response=request.GetResponse())using(var reader=new StreamReader(response.GetResponseStream()))command=reader.ReadToEnd();
                if(!string.IsNullOrWhiteSpace(command)&&!PrepareEngineFeed(command))command="";
                lock(serviceGate){if(State!=State.Active)return;CheckBridgeHealth();bool recovered=bridgeHealth.Failures>0;bridgeHealth.Success(DateTime.UtcNow);if(recovered)Print(bridgeHealth.Paused?"Conexión recuperada; las entradas siguen pausadas. Motivo: "+bridgeHealth.PauseReason:"Conexión recuperada de un fallo transitorio; las entradas conservaron su estado.");if(!string.IsNullOrWhiteSpace(command))ApplyServiceCommand(command);}
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
            finally{System.Threading.Interlocked.Exchange(ref pulseBusy,0);}
        }
        private void ApplyServiceCommand(string command) {
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
                    Instrument next=NinjaTrader.Cbi.Instrument.GetInstrument(values["symbol"]);if(next==null)throw new Exception("Instrumento no disponible");
                    int minutes=int.Parse(values["timeframe_minutes"]);if(minutes<1||minutes>60)throw new Exception("Temporalidad inválida");
                    if(Instrument==null||Instrument.FullName!=next.FullName||minutes!=timeframeMinutes) {
                        if(Instrument!=null)Instrument.MarketData.Update-=ServiceMarketData;
                        Instrument=next;timeframeMinutes=minutes;candleSlot=-1;CurrentBar=0;lastTick=DateTime.MinValue;
                        Instrument.MarketData.Update+=ServiceMarketData;
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

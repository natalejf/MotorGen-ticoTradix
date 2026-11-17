        // Integrated by build_controller.py into a renamed copy; original remains untouched.
        [NinjaScriptProperty]
        [Display(Name = "Web control (Sim101 only)", GroupName = "Stratix", Order = 0)]
        public bool StratixWebEnabled { get; set; }
        [NinjaScriptProperty]
        [Display(Name = "Connection ID", GroupName = "Stratix", Order = 1)]
        public string StratixConnectionId { get; set; }
        [NinjaScriptProperty]
        [Display(Name = "Connection key", GroupName = "Stratix", Order = 2)]
        public string StratixConnectionKey { get; set; }
        private readonly string stratixInstance = Guid.NewGuid().ToString("N");
        private DateTime stratixLastPulse = DateTime.MinValue;
        private DateTime stratixLastSuccess = DateTime.UtcNow;
        private int stratixBusy;
        private string stratixAck = "", stratixAckStatus = "", stratixAckDetail = "";
        private bool stratixWasConnected;
        private string stratixLocalId="",stratixLocalKey="";
        private void StratixRefreshMasterButton() {
            if (btnMasterSwitch == null) return;
            if (!btnMasterSwitch.Dispatcher.CheckAccess()) {btnMasterSwitch.Dispatcher.InvokeAsync(() => StratixRefreshMasterButton());return;}
            btnMasterSwitch.Content = masterTradingEnabled ? "BOT: ON" : "BOT: OFF";
            btnMasterSwitch.Background = new SolidColorBrush(masterTradingEnabled ? Color.FromRgb(35,134,54) : Color.FromRgb(178,34,34));
        }
        private void StratixReadLocalPairing() {
            if (!string.IsNullOrWhiteSpace(StratixConnectionId) && !string.IsNullOrWhiteSpace(StratixConnectionKey)) {
                stratixLocalId=StratixConnectionId;stratixLocalKey=StratixConnectionKey;return;
            }
            if (!string.IsNullOrWhiteSpace(stratixLocalKey)) return;
            string path=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Stratix","NinjaTrader","CandleBridge.key");
            if (!File.Exists(path)) return;
            string[] lines=File.ReadAllLines(path);
            if(lines.Length>=2) {stratixLocalId=lines[0].Trim();stratixLocalKey=lines[1].Trim();}
        }
        private static string StxQuote(string value) {
            return "\"" + (value ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n").Replace("\t", "\\t") + "\"";
        }
        private static string StxNumber(double value) {
            return (double.IsNaN(value) || double.IsInfinity(value) ? 0 : value).ToString(System.Globalization.CultureInfo.InvariantCulture);
        }
        private void StratixWebPulse() {
            if (!StratixWebEnabled || State != State.Realtime) return;
            StratixRefreshMasterButton();
            if ((DateTime.UtcNow - stratixLastSuccess).TotalSeconds > 10 && masterTradingEnabled) {
                masterTradingEnabled = false;
                Print("[Stratix] Web desconectada: nuevas entradas pausadas; gestion y SL/TP siguen activos.");
            }
            try {StratixReadLocalPairing();} catch {return;}
            if (string.IsNullOrWhiteSpace(stratixLocalId) || string.IsNullOrWhiteSpace(stratixLocalKey)) return;
            if ((DateTime.UtcNow - stratixLastPulse).TotalSeconds < 2 || System.Threading.Interlocked.CompareExchange(ref stratixBusy, 1, 0) != 0) return;
            stratixLastPulse = DateTime.UtcNow;
            Account sim = GetAccountCached("Sim101");
            AccountRiskSettings settings;
            lock (accountsConfig) {
                if (!accountsConfig.TryGetValue("Sim101", out settings)) {
                    settings = new AccountRiskSettings("Sim101"); settings.Lots = 1;
                }
            }
            Position position = sim == null ? null : sim.Positions.Cast<Position>().FirstOrDefault(p => p.Instrument.FullName == Instrument.FullName && p.MarketPosition != MarketPosition.Flat);
            string payload = "{\"account\":\"Sim101\",\"instance\":" + StxQuote(stratixInstance)
                + ",\"realtime\":true,\"account_available\":" + (sim != null ? "true" : "false")
                + ",\"master_enabled\":" + (masterTradingEnabled ? "true" : "false")
                + ",\"symbol\":" + StxQuote(Instrument.FullName)
                + ",\"position_quantity\":" + (position == null ? "0" : position.Quantity.ToString())
                + ",\"direction\":" + StxQuote(position == null ? "Flat" : position.MarketPosition.ToString())
                + ",\"status\":" + StxQuote(settings.Status) + ",\"daily_status\":" + StxQuote(settings.DailyStatus)
                + ",\"lots\":" + settings.Lots + ",\"tp_usd\":" + StxNumber(settings.TpUsd)
                + ",\"sl_usd\":" + StxNumber(settings.SlUsd) + ",\"target\":" + StxNumber(settings.Target)
                + ",\"max_loss\":" + StxNumber(settings.MaxLoss) + ",\"start_balance\":" + StxNumber(settings.StartBalance)
                + ",\"daily_profit_limit\":" + StxNumber(settings.DailyProfitLimit)
                + ",\"daily_loss_limit\":" + StxNumber(settings.DailyLossLimit)
                + ",\"time_filter\":" + (settings.TimeFilterEnabled ? "true" : "false")
                + ",\"start_time\":" + StxQuote(settings.StartTime) + ",\"end_time\":" + StxQuote(settings.EndTime)
                + ",\"exit_only_profit\":" + (settings.ExitOnlyInProfit ? "true" : "false")
                + ",\"last_ack\":" + StxQuote(stratixAck) + ",\"ack_status\":" + StxQuote(stratixAckStatus)
                + ",\"ack_detail\":" + StxQuote(stratixAckDetail) + "}";
            string connectionId = stratixLocalId, connectionKey = stratixLocalKey;
            System.Threading.Tasks.Task.Run(() => {
                try {
                    var request = (System.Net.HttpWebRequest)System.Net.WebRequest.Create("http://127.0.0.1:8000/api/ninja/bridge/" + Uri.EscapeDataString(connectionId) + "/pulse");
                    request.Method = "POST"; request.ContentType = "application/json";
                    request.Timeout = 2000; request.ReadWriteTimeout = 2000;
                    request.Headers["X-Stratix-Key"] = connectionKey;
                    byte[] bytes = System.Text.Encoding.UTF8.GetBytes(payload); request.ContentLength = bytes.Length;
                    using (var stream = request.GetRequestStream()) stream.Write(bytes, 0, bytes.Length);
                    string command;
                    using (var response = request.GetResponse())
                    using (var reader = new System.IO.StreamReader(response.GetResponseStream())) command = reader.ReadToEnd();
                    if (ChartControl != null) ChartControl.Dispatcher.InvokeAsync(() => {
                        if (State != State.Realtime) return;
                        stratixLastSuccess = DateTime.UtcNow;
                        if (!stratixWasConnected) Print("[Stratix] Conectado a la web. Control limitado a Sim101.");
                        stratixWasConnected = true;
                        if (!string.IsNullOrWhiteSpace(command)) StratixApplyCommand(command);
                    });
                } catch {
                    if (ChartControl != null) ChartControl.Dispatcher.InvokeAsync(() => {
                        if (stratixWasConnected) Print("[Stratix] Sin conexion web. Nuevas entradas pausadas.");
                        stratixWasConnected = false; masterTradingEnabled = false;
                    });
                } finally { System.Threading.Interlocked.Exchange(ref stratixBusy, 0); }
            });
        }
        private void StratixApplyCommand(string command) {
            string[] parts = command.Split('|');
            if (parts.Length < 4 || parts[0] == stratixAck) return;
            stratixAck = parts[0]; stratixAckStatus = "REJECTED";
            try {
                if (!StratixWebEnabled || parts[1] != stratixInstance) throw new Exception("Instancia incorrecta");
                double expires;
                if (!double.TryParse(parts[2], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out expires)
                    || (DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds > expires) throw new Exception("Comando vencido");
                string action = parts[3];
                if (action == "pause") masterTradingEnabled = false;
                else {
                    Account sim = GetAccountCached("Sim101");
                    if (sim == null) throw new Exception("Sim101 no disponible");
                    if (sim.Positions.Cast<Position>().Any(p => p.Instrument.FullName == Instrument.FullName && p.MarketPosition != MarketPosition.Flat))
                        throw new Exception("Configura/activa sin posiciones en el instrumento");
                    AccountRiskSettings settings;
                    lock (accountsConfig) {
                        if (!accountsConfig.TryGetValue("Sim101", out settings)) {
                            settings = new AccountRiskSettings("Sim101"); accountsConfig["Sim101"] = settings;
                        }
                        if (action == "configure") {
                            if (masterTradingEnabled) throw new Exception("Pausa las entradas antes de configurar");
                            var values = new Dictionary<string, string>();
                            foreach (string part in parts.Skip(4)) {
                                int split = part.IndexOf('='); if (split > 0) values[part.Substring(0, split)] = part.Substring(split + 1);
                            }
                            Func<string,double> number = name => double.Parse(values[name], System.Globalization.CultureInfo.InvariantCulture);
                            settings.Lots = (int)number("lots"); settings.TpUsd = number("tp_usd"); settings.SlUsd = number("sl_usd");
                            settings.Target = number("target"); settings.MaxLoss = number("max_loss");
                            settings.DailyProfitLimit = number("daily_profit_limit"); settings.DailyLossLimit = number("daily_loss_limit");
                            settings.StartBalance = number("start_balance");
                            settings.TimeFilterEnabled = values["time_filter"] == "1";
                            settings.StartTime = values["start_time"]; settings.EndTime = values["end_time"];
                            settings.ExitOnlyInProfit = values["exit_only_profit"] == "1";
                            settings.Enabled = true; settings.Locked = true; removedAccounts.Remove("Sim101");
                            SaveConfiguration();
                        } else if (action == "start") {
                            if (!settings.Enabled || settings.Status != "EN PROCESO" || settings.DailyStatus != "EN PROCESO")
                                throw new Exception("La cuenta esta deshabilitada o bloqueada por sus limites");
                            masterTradingEnabled = true;
                        } else throw new Exception("Accion desconocida");
                    }
                }
                stratixAckStatus = "APPLIED"; stratixAckDetail = parts[3];
                Print("[Stratix] Comando confirmado: " + parts[3] + ". Sim101 / " + Instrument.FullName);
            } catch (Exception error) {
                masterTradingEnabled = false; stratixAckDetail = error.Message;
                Print("[Stratix] Comando rechazado: " + error.Message);
            }
            StratixRefreshMasterButton();
        }

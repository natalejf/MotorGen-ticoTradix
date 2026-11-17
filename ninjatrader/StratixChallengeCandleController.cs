using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;

namespace NinjaTrader.NinjaScript.Strategies
{
    public class StratixChallengeCandleController : Strategy
    {
        // =====================================================================
        //  ESTRUCTURA DE PARÁMETROS POR CUENTA
        // =====================================================================
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
                Lots = 1; // Conservative default for the separate Sim101 integration.
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

        // =====================================================================
        //  ESTRUCTURA PARA REFERENCIAS UI POR CUENTA
        // =====================================================================
        private class AccountUIElements
        {
            public TextBlock NameText;
            public TextBlock EquityText;
            public TextBlock ExamPnlText;
            public TextBlock DailyPnlText;
            public TextBlock ParamsText;
            public CheckBox EnabledCheck;
            public Border CardBorder;
            public Border BadgeBorder;
            public TextBlock BadgeText;
            public Button LockButton;
        }

        // =====================================================================
        //  CAMPOS PRIVADOS
        // =====================================================================
        private Dictionary<string, AccountRiskSettings> accountsConfig = new Dictionary<string, AccountRiskSettings>();
        private HashSet<string> removedAccounts = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private AccountRiskSettings globalConfig = new AccountRiskSettings("GLOBAL");
        private string configFilePath;
        private readonly object fileLock = new object();
        private DispatcherTimer uiRefreshTimer;
        private readonly Dictionary<string, Account> accountCache = new Dictionary<string, Account>();

        // WPF Panel
        private System.Windows.Controls.Grid chartGrid;
        private System.Windows.Controls.ColumnDefinition panelColumn;
        private System.Windows.Controls.Border panelBorder;
        private System.Windows.Controls.StackPanel accountsListPanel;

        // Dashboard de métricas
        private TextBlock dashActiveCount;
        private TextBlock dashProfitCount;
        private TextBlock dashLossCount;
        private TextBlock summaryBalanceText;
        private TextBlock summaryPnLText;

        // Master Switch
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

        private bool masterTradingEnabled = false;
        private System.Windows.Controls.Button btnMasterSwitch;

        // Gráfico P&L en vivo
        private System.Windows.Controls.Canvas pnlChartCanvas;
        private System.Windows.Shapes.Polyline pnlChartLine;
        private System.Windows.Shapes.Line pnlZeroLine;
        private TextBlock pnlCurrentLabel;
        private TextBlock pnlMaxLabel;
        private TextBlock pnlMinLabel;
        private List<double> pnlHistory = new List<double>();

        // Mapa de elementos UI por cuenta
        private Dictionary<string, AccountUIElements> accountUIMap = new Dictionary<string, AccountUIElements>();

        private DateTime realtimeStartTime = DateTime.MinValue;
        private double lastRealtimePrice = 0.0;

        // =====================================================================
        //  CACHE DE CUENTAS
        // =====================================================================
        private Account GetAccountCached(string name)
        {
            if (StratixWebEnabled && !string.Equals(name, "Sim101", StringComparison.Ordinal)) return null;
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
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Controlador Centralizado Multicuenta - Estrategia 1 Vela de Duración (Opción A)";
                Name = "StratixChallengeCandleController";
                StratixWebEnabled = false; StratixConnectionId = ""; StratixConnectionKey = "";
                Calculate = Calculate.OnBarClose; // Clave: Ejecución estricta en cierre/apertura de vela
                RealtimeErrorHandling = RealtimeErrorHandling.IgnoreAllErrors;
            }
            else if (State == State.Configure)
            {
            }
            else if (State == State.DataLoaded)
            {
                configFilePath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "StratixChallengeCandleConfig.txt");
                LoadConfiguration();

                // Configuración global por defecto
                globalConfig.StartBalance = 50000.0;
                globalConfig.Lots = 1; // Sim101 integration default.
                globalConfig.TpUsd = 1500.0;
                globalConfig.SlUsd = 2000.0;
                globalConfig.Target = 1500.0;
                globalConfig.MaxLoss = 2000.0;
                globalConfig.DailyProfitLimit = 1500.0;
                globalConfig.DailyLossLimit = 2000.0;
                globalConfig.TimeFilterEnabled = false;

                // Reiniciar estado de cuentas a EN PROCESO al arrancar el bot
                foreach (var kvp in accountsConfig)
                {
                    kvp.Value.Enabled = false;
                    kvp.Value.Status = "EN PROCESO";
                    kvp.Value.DailyStatus = "EN PROCESO";
                }
                SaveConfiguration();

                // Suscribirse a eventos de ejecución
                lock (Account.All)
                {
                    foreach (Account acc in Account.All)
                    {
                        if (acc != null)
                        {
                            acc.ExecutionUpdate -= OnGlobalExecutionUpdate;
                            acc.ExecutionUpdate += OnGlobalExecutionUpdate;
                        }
                    }
                }

                // Iniciar DispatcherTimer nativo de WPF para UI
                if (System.Windows.Application.Current != null)
                {
                    System.Windows.Application.Current.Dispatcher.InvokeAsync(() =>
                    {
                        try
                        {
                            uiRefreshTimer = new DispatcherTimer();
                            uiRefreshTimer.Interval = TimeSpan.FromSeconds(1);
                            uiRefreshTimer.Tick += UiRefreshTimer_Tick;
                            uiRefreshTimer.Start();
                            Print("[CCC] DispatcherTimer de UI iniciado correctamente.");
                        }
                        catch (Exception ex)
                        {
                            Print("[CCC] Error iniciando DispatcherTimer: " + ex.Message);
                        }
                    });
                }
            }
            else if (State == State.Realtime)
            {
                realtimeStartTime = DateTime.UtcNow;
            }
            else if (State == State.Terminated)
            {
                if (uiRefreshTimer != null)
                {
                    uiRefreshTimer.Stop();
                    uiRefreshTimer = null;
                }

                if (ChartControl != null && ChartControl.Dispatcher != null)
                {
                    ChartControl.Dispatcher.InvokeAsync(() =>
                    {
                        RemoveDockPanel();
                    });
                }

                lock (Account.All)
                {
                    foreach (Account acc in Account.All)
                    {
                        if (acc != null)
                        {
                            acc.ExecutionUpdate -= OnGlobalExecutionUpdate;
                        }
                    }
                }
            }
        }

        private void UiRefreshTimer_Tick(object sender, EventArgs e)
        {
            StratixWebPulse();
            try
            {
                if (ChartControl == null) return;

                ChartControl.Dispatcher.InvokeAsync(() =>
                {
                    try
                    {
                        if (State == State.Realtime)
                        {
                            PeriodicMonitoring();
                        }

                        if (chartGrid == null)
                        {
                            Print("[CCC] Gráfico detectado. Inicializando panel premium...");
                            InitializeDockPanel();
                        }
                        else
                        {
                            UpdateAccountsUIValues();
                        }
                    }
                    catch (Exception ex)
                    {
                        Print("[CCC] Error en ciclo UI: " + ex.Message);
                    }
                });
            }
            catch (Exception ex)
            {
                Print("[CCC] Error en refresco UI: " + ex.Message);
            }
        }

        protected override void OnBarUpdate()
        {
            if (StratixWebEnabled && (DateTime.UtcNow - stratixLastSuccess).TotalSeconds > 10) masterTradingEnabled = false;
            if (State != State.Realtime) return;

            if (Close.Count > 0)
            {
                lastRealtimePrice = Close[0];
            }

            PeriodicMonitoring();

            if (CurrentBar < 2) return;

            // Lógica de Entrada en Apertura de Vela (Evaluado al cierre de vela bajo Calculate.OnBarClose)
            if (masterTradingEnabled)
            {
                // Estrategia: Vela anterior verde (Close[0] > Open[0]) -> COMPRA. Vela anterior roja (Close[0] < Open[0]) -> VENTA.
                bool isLongSignal = Close[0] > Open[0];
                bool isShortSignal = Close[0] < Open[0];

                EvaluateEntrySignals(isLongSignal, isShortSignal);
            }
        }

        // =====================================================================
        //  LÓGICA DE TRADING
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
                    foreach (var kvp in accountsConfig)
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
                    foreach (var kvp in accountsConfig)
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
            if (StratixWebEnabled && (acc == null || acc.Name != "Sim101")) throw new Exception("Stratix web solo Sim101");
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

            if (targetRoom > 0) tradeTpUsd = Math.Min(tradeTpUsd, targetRoom);
            if (dailyProfitRoom > 0) tradeTpUsd = Math.Min(tradeTpUsd, dailyProfitRoom);
            tradeTpUsd = Math.Max(1.0, tradeTpUsd);

            if (lossRoom > 0) tradeSlUsd = Math.Min(tradeSlUsd, lossRoom);
            if (dailyLossRoom > 0) tradeSlUsd = Math.Min(tradeSlUsd, dailyLossRoom);
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

            double currentPrice = lastRealtimePrice > 0 ? lastRealtimePrice : (Close.Count > 0 ? Close[0] : avgPrice);
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
            Draw.HorizontalLine(this, "SL_Line", slPrice, Brushes.Red, DashStyleHelper.Dash, 2);
            Draw.HorizontalLine(this, "TP_Line", tpPrice, Brushes.Green, DashStyleHelper.Dash, 2);

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
                double currentPrice = lastRealtimePrice > 0 ? lastRealtimePrice : (Close.Count > 0 ? Close[0] : 0.0);

                lock (accountsConfig)
                {
                    foreach (var kvp in accountsConfig)
                    {
                        AccountRiskSettings settings = kvp.Value;
                        AccountRiskSettings eff = settings;
                        if (removedAccounts.Contains(kvp.Key) || !settings.Enabled || settings.Status != "EN PROCESO") continue;

                        Account acc = GetAccountCached(settings.Name);
                        if (acc == null) continue;

                        // Autocuración y sincronización del estado de posición
                        Position pos = acc.Positions.Cast<Position>().FirstOrDefault(p => p.Instrument.FullName.Equals(Instrument.FullName, StringComparison.OrdinalIgnoreCase) || p.Instrument.MasterInstrument.Name.Equals(Instrument.MasterInstrument.Name, StringComparison.OrdinalIgnoreCase));
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
                        if (settings.DailyStatus == "EN PROCESO" && (dailyPnlFloating <= -eff.DailyLossLimit || (settings.SessionRealizedPnl <= -eff.DailyLossLimit && settings.SessionRealizedPnl != 0)))
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
                        if (settings.DailyStatus == "EN PROCESO" && (dailyPnlRealized >= eff.DailyProfitLimit || dailyPnlRealized >= eff.Target || dailyPnlFloating >= eff.DailyProfitLimit || dailyPnlFloating >= eff.Target))
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

        // =====================================================================
        //  UI HELPERS
        // =====================================================================
        private System.Windows.Controls.Button CreateControlButton(string text, Color bgColor)
        {
            return new System.Windows.Controls.Button
            {
                Content = text,
                Padding = new Thickness(3, 5, 3, 5),
                Margin = new Thickness(2),
                FontSize = 10,
                FontWeight = FontWeights.Bold,
                Foreground = Brushes.White,
                Background = new SolidColorBrush(bgColor),
                BorderThickness = new Thickness(0),
                Cursor = System.Windows.Input.Cursors.Hand
            };
        }

        private TextBlock CreateMetricCard(System.Windows.Controls.Grid parent, int column, string label, string value, Color valueColor)
        {
            System.Windows.Controls.Border border = new System.Windows.Controls.Border
            {
                Background = new SolidColorBrush(Color.FromRgb(22, 27, 34)),
                BorderBrush = new SolidColorBrush(Color.FromRgb(33, 38, 45)),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(6),
                Padding = new Thickness(4, 8, 4, 8),
                Margin = new Thickness(2)
            };

            System.Windows.Controls.StackPanel stack = new System.Windows.Controls.StackPanel { HorizontalAlignment = HorizontalAlignment.Center };
            stack.Children.Add(new TextBlock
            {
                Text = label,
                FontSize = 8,
                Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)),
                HorizontalAlignment = HorizontalAlignment.Center
            });

            TextBlock valueText = new TextBlock
            {
                Text = value,
                FontSize = 16,
                FontWeight = FontWeights.Bold,
                Foreground = new SolidColorBrush(valueColor),
                HorizontalAlignment = HorizontalAlignment.Center
            };
            stack.Children.Add(valueText);

            border.Child = stack;
            System.Windows.Controls.Grid.SetColumn(border, column);
            parent.Children.Add(border);

            return valueText;
        }

        private System.Windows.Controls.Button CreateActionButton(string text, Color bgColor)
        {
            return new System.Windows.Controls.Button
            {
                Content = text,
                Foreground = Brushes.White,
                Background = new SolidColorBrush(bgColor),
                Width = 28,
                Height = 22,
                Margin = new Thickness(2, 0, 0, 0),
                FontSize = 10,
                FontWeight = FontWeights.Bold,
                BorderThickness = new Thickness(0),
                Cursor = System.Windows.Input.Cursors.Hand,
                HorizontalContentAlignment = HorizontalAlignment.Center,
                VerticalContentAlignment = VerticalAlignment.Center
            };
        }

        // =====================================================================
        //  INTERFAZ VISUAL PREMIUM (WPF)
        // =====================================================================
        private void InitializeDockPanel()
        {
            try
            {
                Print("[CCC] Inicializando panel premium...");

                DependencyObject parentObj = ChartControl.Parent;
                while (parentObj != null && !(parentObj is System.Windows.Controls.Grid))
                {
                    parentObj = VisualTreeHelper.GetParent(parentObj);
                }

                if (parentObj == null || !(parentObj is System.Windows.Controls.Grid))
                {
                    Print("[CCC] No se pudo encontrar el Grid contenedor.");
                    return;
                }

                chartGrid = (System.Windows.Controls.Grid)parentObj;

                panelColumn = new System.Windows.Controls.ColumnDefinition();
                panelColumn.Width = new System.Windows.GridLength(520, System.Windows.GridUnitType.Pixel);
                chartGrid.ColumnDefinitions.Add(panelColumn);

                panelBorder = new System.Windows.Controls.Border();
                panelBorder.Background = new SolidColorBrush(Color.FromRgb(13, 17, 23));
                panelBorder.BorderBrush = new SolidColorBrush(Color.FromRgb(33, 38, 45));
                panelBorder.BorderThickness = new Thickness(1, 0, 0, 0);
                System.Windows.Controls.Grid.SetColumn(panelBorder, chartGrid.ColumnDefinitions.Count - 1);

                System.Windows.Controls.Grid mainContainer = new System.Windows.Controls.Grid();
                panelBorder.Child = mainContainer;

                mainContainer.RowDefinitions.Add(new RowDefinition() { Height = GridLength.Auto }); // Header
                mainContainer.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(1, GridUnitType.Star) }); // Scroll

                // HEADER SECTION
                System.Windows.Controls.Border headerBorder = new System.Windows.Controls.Border
                {
                    Background = new LinearGradientBrush(
                        Color.FromRgb(13, 17, 23),
                        Color.FromRgb(22, 33, 62),
                        90
                    ),
                    BorderBrush = new SolidColorBrush(Color.FromRgb(33, 38, 45)),
                    BorderThickness = new Thickness(0, 0, 0, 1),
                    Padding = new Thickness(12, 10, 12, 10)
                };
                System.Windows.Controls.StackPanel headerStack = new System.Windows.Controls.StackPanel();
                headerBorder.Child = headerStack;

                TextBlock titleText = new TextBlock
                {
                    Text = "⚡ CHALLENGE CANDLE CONTROLLER",
                    FontWeight = FontWeights.Bold,
                    FontSize = 15,
                    Foreground = new SolidColorBrush(Color.FromRgb(0, 212, 255))
                };
                headerStack.Children.Add(titleText);

                TextBlock subtitleText = new TextBlock
                {
                    Text = "Candle-by-Candle Strategy Dashboard v1.0",
                    FontSize = 9.5,
                    Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)),
                    Margin = new Thickness(0, 2, 0, 0)
                };
                headerStack.Children.Add(subtitleText);

                // BARRA DE CONTROL
                System.Windows.Controls.Grid controlGrid = new System.Windows.Controls.Grid { Margin = new Thickness(0, 10, 0, 0) };
                controlGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                controlGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                controlGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                controlGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                controlGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

                System.Windows.Controls.Button btnDetect = CreateControlButton("🔍 Detectar", Color.FromRgb(31, 81, 155));
                btnDetect.Click += (s, e) => { DetectAndRefreshAccounts(); };
                System.Windows.Controls.Grid.SetColumn(btnDetect, 0);
                controlGrid.Children.Add(btnDetect);

                System.Windows.Controls.Button btnConfigGlobal = CreateControlButton("⚙ Config", Color.FromRgb(55, 62, 71));
                btnConfigGlobal.Click += (s, e) => { OpenConfigModal("GLOBAL"); };
                System.Windows.Controls.Grid.SetColumn(btnConfigGlobal, 1);
                controlGrid.Children.Add(btnConfigGlobal);

                System.Windows.Controls.Button btnListoAll = CreateControlButton("✅ Listo", Color.FromRgb(25, 80, 45));
                btnListoAll.Click += (s, e) => { ToggleAllAccounts(true); };
                System.Windows.Controls.Grid.SetColumn(btnListoAll, 2);
                controlGrid.Children.Add(btnListoAll);

                System.Windows.Controls.Button btnResetAll = CreateControlButton("♺ Reset", Color.FromRgb(75, 75, 90));
                btnResetAll.Click += (s, e) => { ResetAllAccounts(); };
                System.Windows.Controls.Grid.SetColumn(btnResetAll, 3);
                controlGrid.Children.Add(btnResetAll);

                btnMasterSwitch = CreateControlButton(
                    masterTradingEnabled ? "🔴 BOT: ON" : "⚪ BOT: OFF",
                    masterTradingEnabled ? Color.FromRgb(35, 134, 54) : Color.FromRgb(178, 34, 34)
                );
                btnMasterSwitch.Click += (s, e) =>
                {
                    masterTradingEnabled = !masterTradingEnabled;
                    btnMasterSwitch.Content = masterTradingEnabled ? "🔴 BOT: ON" : "⚪ BOT: OFF";
                    btnMasterSwitch.Background = new SolidColorBrush(
                        masterTradingEnabled ? Color.FromRgb(35, 134, 54) : Color.FromRgb(178, 34, 34)
                    );
                };
                System.Windows.Controls.Grid.SetColumn(btnMasterSwitch, 4);
                controlGrid.Children.Add(btnMasterSwitch);

                headerStack.Children.Add(controlGrid);

                // DASHBOARD DE MÉTRICAS (3 tarjetas)
                System.Windows.Controls.Grid metricsGrid = new System.Windows.Controls.Grid { Margin = new Thickness(0, 10, 0, 0) };
                metricsGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                metricsGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                metricsGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

                dashActiveCount = CreateMetricCard(metricsGrid, 0, "ACTIVAS", "0", Color.FromRgb(200, 200, 220));
                dashProfitCount = CreateMetricCard(metricsGrid, 1, "PROFIT", "0", Color.FromRgb(0, 230, 118));
                dashLossCount = CreateMetricCard(metricsGrid, 2, "LOSS", "0", Color.FromRgb(255, 82, 82));

                headerStack.Children.Add(metricsGrid);

                // BALANCE / PNL BAR
                System.Windows.Controls.Grid balanceGrid = new System.Windows.Controls.Grid { Margin = new Thickness(0, 8, 0, 0) };
                balanceGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                balanceGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

                System.Windows.Controls.StackPanel balStack = new System.Windows.Controls.StackPanel { Margin = new Thickness(0, 0, 4, 0) };
                balStack.Children.Add(new TextBlock { Text = "Balance Total", FontSize = 9, Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)) });
                summaryBalanceText = new TextBlock { Text = "$0.00", FontSize = 14, FontWeight = FontWeights.Bold, Foreground = Brushes.White };
                balStack.Children.Add(summaryBalanceText);
                System.Windows.Controls.Grid.SetColumn(balStack, 0);
                balanceGrid.Children.Add(balStack);

                System.Windows.Controls.StackPanel pnlStackHeader = new System.Windows.Controls.StackPanel { Margin = new Thickness(4, 0, 0, 0) };
                pnlStackHeader.Children.Add(new TextBlock { Text = "PnL Acumulado", FontSize = 9, Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)) });
                summaryPnLText = new TextBlock { Text = "$0.00", FontSize = 14, FontWeight = FontWeights.Bold, Foreground = Brushes.White };
                pnlStackHeader.Children.Add(summaryPnLText);
                System.Windows.Controls.Grid.SetColumn(pnlStackHeader, 1);
                balanceGrid.Children.Add(pnlStackHeader);

                headerStack.Children.Add(balanceGrid);

                System.Windows.Controls.Grid.SetRow(headerBorder, 0);
                mainContainer.Children.Add(headerBorder);

                // CONTENIDO SCROLLABLE
                System.Windows.Controls.ScrollViewer scrollViewer = new System.Windows.Controls.ScrollViewer
                {
                    VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                    HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                    Padding = new Thickness(0)
                };

                System.Windows.Controls.StackPanel contentStack = new System.Windows.Controls.StackPanel { Margin = new Thickness(12, 8, 12, 8) };
                scrollViewer.Content = contentStack;

                // GRÁFICO P&L EN VIVO
                TextBlock chartTitle = new TextBlock
                {
                    Text = "📈 P&L EN VIVO",
                    FontWeight = FontWeights.Bold,
                    FontSize = 11,
                    Foreground = new SolidColorBrush(Color.FromRgb(200, 200, 220)),
                    Margin = new Thickness(0, 0, 0, 6)
                };
                contentStack.Children.Add(chartTitle);

                System.Windows.Controls.Border chartBorder = new System.Windows.Controls.Border
                {
                    Background = new SolidColorBrush(Color.FromRgb(13, 17, 23)),
                    BorderBrush = new SolidColorBrush(Color.FromRgb(33, 38, 45)),
                    BorderThickness = new Thickness(1),
                    CornerRadius = new CornerRadius(6),
                    Height = 130,
                    Margin = new Thickness(0, 0, 0, 12)
                };

                System.Windows.Controls.Grid chartContainer = new System.Windows.Controls.Grid();
                chartBorder.Child = chartContainer;

                pnlChartCanvas = new System.Windows.Controls.Canvas
                {
                    ClipToBounds = true,
                    Margin = new Thickness(2)
                };
                chartContainer.Children.Add(pnlChartCanvas);

                pnlZeroLine = new System.Windows.Shapes.Line
                {
                    X1 = 0,
                    X2 = 400,
                    Stroke = new SolidColorBrush(Color.FromRgb(88, 166, 255)),
                    StrokeThickness = 0.5,
                    Opacity = 0.4
                };
                pnlZeroLine.StrokeDashArray = new DoubleCollection(new double[] { 4, 4 });
                pnlChartCanvas.Children.Add(pnlZeroLine);

                pnlChartLine = new System.Windows.Shapes.Polyline
                {
                    Stroke = new SolidColorBrush(Color.FromRgb(0, 230, 118)),
                    StrokeThickness = 2,
                    StrokeLineJoin = PenLineJoin.Round
                };
                pnlChartCanvas.Children.Add(pnlChartLine);

                System.Windows.Controls.Grid labelsGrid = new System.Windows.Controls.Grid();

                pnlCurrentLabel = new TextBlock
                {
                    Text = "$0.00",
                    FontSize = 11,
                    FontWeight = FontWeights.Bold,
                    Foreground = Brushes.White,
                    HorizontalAlignment = HorizontalAlignment.Right,
                    VerticalAlignment = VerticalAlignment.Bottom,
                    Margin = new Thickness(0, 0, 8, 5)
                };
                labelsGrid.Children.Add(pnlCurrentLabel);

                pnlMaxLabel = new TextBlock
                {
                    Text = "",
                    FontSize = 8,
                    Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)),
                    HorizontalAlignment = HorizontalAlignment.Left,
                    VerticalAlignment = VerticalAlignment.Top,
                    Margin = new Thickness(5, 3, 0, 0)
                };
                labelsGrid.Children.Add(pnlMaxLabel);

                pnlMinLabel = new TextBlock
                {
                    Text = "",
                    FontSize = 8,
                    Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)),
                    HorizontalAlignment = HorizontalAlignment.Left,
                    VerticalAlignment = VerticalAlignment.Bottom,
                    Margin = new Thickness(5, 0, 0, 22)
                };
                labelsGrid.Children.Add(pnlMinLabel);

                chartContainer.Children.Add(labelsGrid);
                contentStack.Children.Add(chartBorder);

                TextBlock accountsTitle = new TextBlock
                {
                    Text = "📋 CUENTAS DETECTADAS",
                    FontWeight = FontWeights.Bold,
                    FontSize = 11,
                    Foreground = new SolidColorBrush(Color.FromRgb(200, 200, 220)),
                    Margin = new Thickness(0, 0, 0, 6)
                };
                contentStack.Children.Add(accountsTitle);

                accountsListPanel = new System.Windows.Controls.StackPanel
                {
                    HorizontalAlignment = System.Windows.HorizontalAlignment.Stretch
                };
                contentStack.Children.Add(accountsListPanel);

                System.Windows.Controls.Grid.SetRow(scrollViewer, 1);
                mainContainer.Children.Add(scrollViewer);

                chartGrid.Children.Add(panelBorder);

                BuildAccountsListUI();

                Print("[CCC] Panel premium inicializado correctamente.");
            }
            catch (Exception ex)
            {
                Print("[CCC] Error en InitializeDockPanel: " + ex.Message);
            }
        }

        private void RemoveDockPanel()
        {
            try
            {
                if (chartGrid != null)
                {
                    if (panelBorder != null && chartGrid.Children.Contains(panelBorder))
                        chartGrid.Children.Remove(panelBorder);

                    if (panelColumn != null && chartGrid.ColumnDefinitions.Contains(panelColumn))
                        chartGrid.ColumnDefinitions.Remove(panelColumn);

                    chartGrid = null;
                }
            }
            catch (Exception ex)
            {
                Print("[CCC] Error removiendo panel: " + ex.Message);
            }
        }

        private void DetectAndRefreshAccounts()
        {
            lock (accountsConfig)
            {
                removedAccounts.Clear();
            }

            lock (Account.All)
            {
                foreach (Account acc in Account.All)
                {
                    if (acc != null)
                    {
                        acc.ExecutionUpdate -= OnGlobalExecutionUpdate;
                        acc.ExecutionUpdate += OnGlobalExecutionUpdate;
                    }
                }
            }

            lock (accountCache)
            {
                accountCache.Clear();
            }

            BuildAccountsListUI();
            SaveConfiguration();
            Print("[CCC] Cuentas re-detectadas y refrescadas.");
        }

        private void ToggleAllAccounts(bool active)
        {
            foreach (var kvp in accountsConfig)
            {
                kvp.Value.Enabled = active;
            }
            SaveConfiguration();
            BuildAccountsListUI();
        }

        private void ResetAllAccounts()
        {
            if (System.Windows.MessageBox.Show("¿Reiniciar el estado de TODAS las cuentas?", "Confirmar Reset General", System.Windows.MessageBoxButton.YesNo) == System.Windows.MessageBoxResult.Yes)
            {
                lock (accountsConfig)
                {
                    foreach (var kvp in accountsConfig)
                    {
                        AccountRiskSettings settings = kvp.Value;
                        Account acc = GetAccountCached(settings.Name);
                        
                        double currentCash = 0;
                        if (acc != null)
                        {
                            currentCash = acc.Get(AccountItem.CashValue, Currency.UsDollar);
                        }
                        if (currentCash <= 0) currentCash = settings.StartBalance > 0 ? settings.StartBalance : 50000.0;
                        
                        settings.Status = "EN PROCESO";
                        settings.DailyStatus = "EN PROCESO";
                        settings.Enabled = false;
                        settings.StartBalance = currentCash;
                        settings.DailyStartBalance = currentCash;
                        settings.LastResetDate = "";
                        settings.DailyCommissions = 0.0;
                        settings.NinjaTraderHandlesCommissions = false;
                        ResetTradingState(acc, settings);
                    }
                }
                SaveConfiguration();
                BuildAccountsListUI();
            }
        }

        // =====================================================================
        //  CONSTRUCCIÓN DE LISTA DE CUENTAS (UI PREMIUM)
        // =====================================================================
        private void BuildAccountsListUI()
        {
            if (accountsListPanel == null) return;
            accountsListPanel.Children.Clear();
            accountUIMap.Clear();

            lock (Account.All)
            {
                foreach (Account acc in Account.All)
                {
                    if (acc == null) continue;

                    string nameUpper = acc.Name.ToUpper();

                    if (nameUpper.Contains("BACKTEST") ||
                        nameUpper.StartsWith("PLAYBACK") ||
                        nameUpper.StartsWith("VIRTUAL"))
                        continue;

                    bool isSimAccount = nameUpper.StartsWith("SIM");

                    if (!isSimAccount)
                    {
                        if (acc.Connection == null || acc.Connection.Status != ConnectionStatus.Connected)
                            continue;
                    }

                    string accName = acc.Name;
                    if (removedAccounts.Contains(accName)) continue;

                    if (!accountsConfig.ContainsKey(accName))
                    {
                        double cashVal = acc.Get(AccountItem.CashValue, Currency.UsDollar);
                        if (cashVal <= 0) cashVal = globalConfig.StartBalance > 0 ? globalConfig.StartBalance : 50000.0;

                        AccountRiskSettings newSettings = new AccountRiskSettings(accName)
                        {
                            StartBalance = cashVal,
                            Lots = globalConfig.Lots,
                            TpUsd = globalConfig.TpUsd,
                            SlUsd = globalConfig.SlUsd,
                            Target = globalConfig.Target,
                            MaxLoss = globalConfig.MaxLoss,
                            DailyProfitLimit = globalConfig.DailyProfitLimit,
                            DailyLossLimit = globalConfig.DailyLossLimit,
                            TimeFilterEnabled = globalConfig.TimeFilterEnabled,
                            StartTime = globalConfig.StartTime,
                            EndTime = globalConfig.EndTime
                        };
                        accountsConfig[accName] = newSettings;
                    }
                    AccountRiskSettings settings = accountsConfig[accName];
                    AccountRiskSettings eff = settings;

                    Position pos = acc.Positions.Cast<Position>().FirstOrDefault(p => p.Instrument.FullName.Equals(Instrument.FullName, StringComparison.OrdinalIgnoreCase) || p.Instrument.MasterInstrument.Name.Equals(Instrument.MasterInstrument.Name, StringComparison.OrdinalIgnoreCase));
                    bool isOperating = pos != null && pos.MarketPosition != MarketPosition.Flat;

                    AccountUIElements uiElems = new AccountUIElements();

                    System.Windows.Controls.Border cardBorder = new System.Windows.Controls.Border
                    {
                        CornerRadius = new CornerRadius(6),
                        Margin = new Thickness(0, 0, 0, 8),
                        Padding = new Thickness(12, 10, 12, 10),
                        BorderThickness = new Thickness(1.5)
                    };
                    uiElems.CardBorder = cardBorder;

                    System.Windows.Controls.Grid mainCardGrid = new System.Windows.Controls.Grid();
                    mainCardGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    mainCardGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    mainCardGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    mainCardGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    mainCardGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    mainCardGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

                    cardBorder.Child = mainCardGrid;

                    // ROW 0: Header
                    System.Windows.Controls.Grid headerGrid = new System.Windows.Controls.Grid();
                    headerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                    headerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

                    System.Windows.Controls.StackPanel leftHeader = new System.Windows.Controls.StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
                    CheckBox activeCheck = new CheckBox
                    {
                        IsChecked = settings.Enabled,
                        VerticalAlignment = VerticalAlignment.Center,
                        Margin = new Thickness(0, 0, 8, 0)
                    };
                    activeCheck.Checked += (s, e) => { settings.Enabled = true; SaveConfiguration(); };
                    activeCheck.Unchecked += (s, e) => { settings.Enabled = false; SaveConfiguration(); };
                    uiElems.EnabledCheck = activeCheck;
                    leftHeader.Children.Add(activeCheck);

                    TextBlock nameText = new TextBlock
                    {
                        Text = isOperating ? accName + " ● OPERANDO" : accName,
                        FontWeight = FontWeights.Bold,
                        FontSize = 12.5,
                        Foreground = isOperating ? new SolidColorBrush(Color.FromRgb(0, 191, 255)) : Brushes.White,
                        VerticalAlignment = VerticalAlignment.Center
                    };
                    uiElems.NameText = nameText;
                    leftHeader.Children.Add(nameText);

                    System.Windows.Controls.Grid.SetColumn(leftHeader, 0);
                    headerGrid.Children.Add(leftHeader);

                    System.Windows.Controls.StackPanel rightHeader = new System.Windows.Controls.StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
                    System.Windows.Controls.Button lockBtn = new System.Windows.Controls.Button
                    {
                        Content = settings.Locked ? "🔒" : "🔓",
                        FontSize = 10,
                        Width = 20,
                        Height = 20,
                        Margin = new Thickness(0, 0, 6, 0),
                        Background = new SolidColorBrush(Color.FromRgb(48, 48, 62)),
                        Foreground = Brushes.White,
                        BorderThickness = new Thickness(0)
                    };
                    uiElems.LockButton = lockBtn;
                    lockBtn.Click += (s, e) =>
                    {
                        settings.Locked = !settings.Locked;
                        lockBtn.Content = settings.Locked ? "🔒" : "🔓";
                        SaveConfiguration();
                    };
                    rightHeader.Children.Add(lockBtn);

                    System.Windows.Controls.Border badgeBorder = new System.Windows.Controls.Border
                    {
                        CornerRadius = new CornerRadius(3),
                        Padding = new Thickness(6, 2, 6, 2),
                        VerticalAlignment = VerticalAlignment.Center
                    };
                    TextBlock badgeText = new TextBlock { FontSize = 8, FontWeight = FontWeights.Bold };
                    badgeBorder.Child = badgeText;
                    SetBadgeStyle(badgeBorder, badgeText, settings.Status, eff);
                    uiElems.BadgeBorder = badgeBorder;
                    uiElems.BadgeText = badgeText;
                    rightHeader.Children.Add(badgeBorder);

                    System.Windows.Controls.Grid.SetColumn(rightHeader, 1);
                    headerGrid.Children.Add(rightHeader);

                    System.Windows.Controls.Grid.SetRow(headerGrid, 0);
                    mainCardGrid.Children.Add(headerGrid);

                    System.Windows.Controls.Separator sep1 = new System.Windows.Controls.Separator { Background = new SolidColorBrush(Color.FromRgb(40, 44, 52)), Margin = new Thickness(0, 6, 0, 6) };
                    System.Windows.Controls.Grid.SetRow(sep1, 1);
                    mainCardGrid.Children.Add(sep1);

                    // ROW 2: Métricas (Balance, PnL Diario)
                    System.Windows.Controls.Grid mGrid = new System.Windows.Controls.Grid();
                    mGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                    mGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

                    System.Windows.Controls.StackPanel m1Stack = new System.Windows.Controls.StackPanel { HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Center };
                    m1Stack.Children.Add(new TextBlock { Text = "BALANCE", FontSize = 8.5, Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)), FontWeight = FontWeights.SemiBold });
                    TextBlock eqVal = new TextBlock { Text = "$0", FontSize = 12, FontWeight = FontWeights.Bold, Foreground = Brushes.White, Margin = new Thickness(0, 2, 0, 0) };
                    uiElems.EquityText = eqVal;
                    m1Stack.Children.Add(eqVal);
                    System.Windows.Controls.Grid.SetColumn(m1Stack, 0);
                    mGrid.Children.Add(m1Stack);

                    System.Windows.Controls.StackPanel m2Stack = new System.Windows.Controls.StackPanel { HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center };
                    m2Stack.Children.Add(new TextBlock { Text = "PNL DIARIO", FontSize = 8.5, Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)), FontWeight = FontWeights.SemiBold });
                    TextBlock dailyVal = new TextBlock { Text = "$0", FontSize = 13, FontWeight = FontWeights.Bold, Foreground = Brushes.White, Margin = new Thickness(0, 1, 0, 0) };
                    uiElems.DailyPnlText = dailyVal;
                    m2Stack.Children.Add(dailyVal);
                    System.Windows.Controls.Grid.SetColumn(m2Stack, 1);
                    mGrid.Children.Add(m2Stack);

                    System.Windows.Controls.Grid.SetRow(mGrid, 2);
                    mainCardGrid.Children.Add(mGrid);

                    System.Windows.Controls.Separator sep2 = new System.Windows.Controls.Separator { Background = new SolidColorBrush(Color.FromRgb(40, 44, 52)), Margin = new Thickness(0, 6, 0, 6) };
                    System.Windows.Controls.Grid.SetRow(sep2, 3);
                    mainCardGrid.Children.Add(sep2);

                    // ROW 4: Parámetros de Riesgo
                    System.Windows.Controls.StackPanel footerLeft = new System.Windows.Controls.StackPanel { VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 0, 4) };
                    TextBlock paramsText = new TextBlock
                    {
                        Text = string.Format("TP/SL:${0:F0}/${1:F0} | Lím:+${2:F0}/-${3:F0}",
                            eff.TpUsd, eff.SlUsd, eff.DailyProfitLimit, eff.DailyLossLimit),
                        FontSize = 8.5,
                        Foreground = new SolidColorBrush(Color.FromRgb(140, 140, 160))
                    };
                    uiElems.ParamsText = paramsText;
                    footerLeft.Children.Add(paramsText);

                    System.Windows.Controls.Grid.SetRow(footerLeft, 4);
                    mainCardGrid.Children.Add(footerLeft);

                    // ROW 5: Botones de Acción
                    System.Windows.Controls.StackPanel actionButtons = new System.Windows.Controls.StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 4, 0, 0) };
                    
                    string captureAccName = accName;
                    System.Windows.Controls.Button configBtn = CreateActionButton("⚙", Color.FromRgb(55, 62, 71));
                    configBtn.ToolTip = "Configuración";
                    configBtn.Click += (s, e) => { OpenConfigModal(captureAccName); };
                    actionButtons.Children.Add(configBtn);

                    System.Windows.Controls.Button panicBtn = CreateActionButton("✕", Color.FromRgb(178, 34, 34));
                    panicBtn.ToolTip = "Cerrar Posiciones (Pánico)";
                    panicBtn.Click += (s, e) =>
                    {
                        if (MessageBox.Show("¿Cerrar todas las posiciones de " + captureAccName + "?", "PÁNICO", MessageBoxButton.YesNo) == MessageBoxResult.Yes)
                        {
                            acc.Flatten(new[] { Instrument });
                            ResetTradingState(acc, settings);
                            SaveConfiguration();
                        }
                    };
                    actionButtons.Children.Add(panicBtn);

                    System.Windows.Controls.Button resetBtn = CreateActionButton("♺", Color.FromRgb(75, 75, 90));
                    resetBtn.ToolTip = "Resetear Límites de Cuenta";
                    resetBtn.Click += (s, e) =>
                    {
                        if (MessageBox.Show("¿Reiniciar límites para " + captureAccName + "?", "Reset Cuenta", MessageBoxButton.YesNo) == MessageBoxResult.Yes)
                        {
                            lock (accountsConfig)
                            {
                                double currentCash = acc.Get(AccountItem.CashValue, Currency.UsDollar);
                                if (currentCash <= 0) currentCash = settings.StartBalance > 0 ? settings.StartBalance : 50000.0;
                                settings.Status = "EN PROCESO";
                                settings.DailyStatus = "EN PROCESO";
                                settings.Enabled = false;
                                settings.StartBalance = currentCash;
                                settings.DailyStartBalance = currentCash;
                                settings.LastResetDate = "";
                                settings.DailyCommissions = 0.0;
                                settings.NinjaTraderHandlesCommissions = false;
                                ResetTradingState(acc, settings);
                            }
                            SaveConfiguration();
                            BuildAccountsListUI();
                        }
                    };
                    actionButtons.Children.Add(resetBtn);

                    System.Windows.Controls.Button deleteBtn = CreateActionButton("🗑", Color.FromRgb(140, 35, 35));
                    deleteBtn.ToolTip = "Eliminar Cuenta de la Lista";
                    deleteBtn.Click += (s, e) =>
                    {
                        if (MessageBox.Show("¿Eliminar la cuenta " + captureAccName + " de la lista?", "Eliminar Cuenta", MessageBoxButton.YesNo) == MessageBoxResult.Yes)
                        {
                            lock (accountsConfig)
                            {
                                if (accountsConfig.ContainsKey(captureAccName))
                                {
                                    accountsConfig[captureAccName].Enabled = false;
                                    accountsConfig.Remove(captureAccName);
                                }
                                removedAccounts.Add(captureAccName);
                            }
                            SaveConfiguration();
                            BuildAccountsListUI();
                        }
                    };
                    actionButtons.Children.Add(deleteBtn);

                    System.Windows.Controls.Grid.SetRow(actionButtons, 5);
                    mainCardGrid.Children.Add(actionButtons);

                    // ESTILO VISUAL POR ESTADO
                    SolidColorBrush bgBrush = new SolidColorBrush(Color.FromRgb(22, 27, 34));
                    SolidColorBrush borderBrush = new SolidColorBrush(Color.FromRgb(33, 38, 45));
                    double borderThickness = 1.0;

                    if (settings.Status == "PASS")
                    {
                        bgBrush = new SolidColorBrush(Color.FromRgb(15, 45, 25));
                        borderBrush = new SolidColorBrush(Color.FromRgb(0, 230, 118));
                        borderThickness = 1.5;
                    }
                    else if (settings.Status == "BURNED" || settings.DailyStatus == "LOSS_LIMIT_REACHED")
                    {
                        bgBrush = new SolidColorBrush(Color.FromRgb(50, 20, 25));
                        borderBrush = new SolidColorBrush(Color.FromRgb(255, 82, 82));
                        borderThickness = 1.5;
                    }
                    else if (isOperating)
                    {
                        bgBrush = new SolidColorBrush(Color.FromRgb(15, 30, 50));
                        borderBrush = new SolidColorBrush(Color.FromRgb(0, 191, 255));
                        borderThickness = 1.5;
                    }

                    cardBorder.Background = bgBrush;
                    cardBorder.BorderBrush = borderBrush;
                    cardBorder.BorderThickness = new Thickness(borderThickness);

                    accountsListPanel.Children.Add(cardBorder);

                    accountUIMap[accName] = uiElems;
                }
            }
        }

        private void SetBadgeStyle(System.Windows.Controls.Border border, TextBlock text, string status, AccountRiskSettings eff)
        {
            if (status == "PASS")
            {
                border.Background = new SolidColorBrush(Color.FromRgb(15, 45, 25));
                text.Foreground = new SolidColorBrush(Color.FromRgb(0, 230, 118));
                text.Text = "✓ PASS";
            }
            else if (status == "BURNED")
            {
                border.Background = new SolidColorBrush(Color.FromRgb(50, 20, 25));
                text.Foreground = new SolidColorBrush(Color.FromRgb(255, 82, 82));
                text.Text = "✓ BURNED";
            }
            else if (eff.DailyStatus == "LOSS_LIMIT_REACHED")
            {
                border.Background = new SolidColorBrush(Color.FromRgb(60, 15, 20));
                text.Foreground = new SolidColorBrush(Color.FromRgb(255, 82, 82));
                text.Text = "LÍM. PÉRDIDA";
            }
            else if (eff.DailyStatus == "TARGET_REACHED")
            {
                border.Background = new SolidColorBrush(Color.FromRgb(15, 40, 60));
                text.Foreground = new SolidColorBrush(Color.FromRgb(0, 212, 255));
                text.Text = "LÍM. GANANCIA";
            }
            else
            {
                border.Background = new SolidColorBrush(Color.FromRgb(50, 40, 10));
                text.Foreground = new SolidColorBrush(Color.FromRgb(255, 193, 7));
                text.Text = "EN PROCESO";
            }
        }

        // =====================================================================
        //  ACTUALIZACIÓN EN VIVO DE VALORES
        // =====================================================================
        private void UpdateAccountsUIValues()
        {
            if (accountsListPanel == null) return;

            int activeCount = 0;
            int profitCount = 0;
            int lossCount = 0;
            double totalBalance = 0.0;
            double totalPnL = 0.0;

            foreach (var kvp in accountUIMap)
            {
                string accName = kvp.Key;
                AccountUIElements ui = kvp.Value;

                if (!accountsConfig.ContainsKey(accName)) continue;
                AccountRiskSettings settings = accountsConfig[accName];
                AccountRiskSettings eff = settings;

                Account acc = GetAccountCached(accName);
                if (acc == null) continue;

                try
                {
                    double cash = acc.Get(AccountItem.CashValue, Currency.UsDollar);
                    double unrealized = acc.Get(AccountItem.UnrealizedProfitLoss, Currency.UsDollar);
                    double equity = cash + unrealized;
                    double pnl = equity - eff.StartBalance;
                    double dailyPnl = equity - settings.DailyStartBalance;

                    if (settings.DailyCommissions > 0 && !settings.NinjaTraderHandlesCommissions)
                    {
                        pnl -= settings.DailyCommissions;
                        dailyPnl -= settings.DailyCommissions;
                    }

                    totalBalance += (settings.DailyCommissions > 0 && !settings.NinjaTraderHandlesCommissions) ? (equity - settings.DailyCommissions) : equity;
                    totalPnL += pnl;

                    if (settings.Enabled)
                    {
                        activeCount++;
                        if (pnl > 0) profitCount++;
                        else if (pnl < 0) lossCount++;
                    }

                    if (ui.EquityText != null)
                        ui.EquityText.Text = "$" + equity.ToString("N0", System.Globalization.CultureInfo.InvariantCulture);

                    if (ui.DailyPnlText != null)
                    {
                        ui.DailyPnlText.Text = (dailyPnl >= 0 ? "+" : "") + "$" + dailyPnl.ToString("N0", System.Globalization.CultureInfo.InvariantCulture);
                        ui.DailyPnlText.Foreground = dailyPnl >= 0 ? new SolidColorBrush(Color.FromRgb(0, 230, 118)) : new SolidColorBrush(Color.FromRgb(255, 82, 82));
                    }

                    if (ui.EnabledCheck != null && ui.EnabledCheck.IsChecked != settings.Enabled)
                        ui.EnabledCheck.IsChecked = settings.Enabled;

                    Position pos = acc.Positions.Cast<Position>().FirstOrDefault(p => p.Instrument.FullName.Equals(Instrument.FullName, StringComparison.OrdinalIgnoreCase) || p.Instrument.MasterInstrument.Name.Equals(Instrument.MasterInstrument.Name, StringComparison.OrdinalIgnoreCase));
                    bool isOperating = pos != null && pos.MarketPosition != MarketPosition.Flat;

                    SolidColorBrush bgBrush = new SolidColorBrush(Color.FromRgb(22, 27, 34));
                    SolidColorBrush borderBrush = new SolidColorBrush(Color.FromRgb(33, 38, 45));
                    double borderThickness = 1.0;

                    if (settings.Status == "PASS")
                    {
                        bgBrush = new SolidColorBrush(Color.FromRgb(15, 45, 25));
                        borderBrush = new SolidColorBrush(Color.FromRgb(0, 230, 118));
                        borderThickness = 2.0;
                    }
                    else if (settings.Status == "BURNED" || settings.DailyStatus == "LOSS_LIMIT_REACHED")
                    {
                        bgBrush = new SolidColorBrush(Color.FromRgb(50, 20, 25));
                        borderBrush = new SolidColorBrush(Color.FromRgb(255, 82, 82));
                        borderThickness = 2.0;
                    }
                    else if (isOperating)
                    {
                        bgBrush = new SolidColorBrush(Color.FromRgb(15, 30, 50));
                        borderBrush = new SolidColorBrush(Color.FromRgb(0, 191, 255));
                        borderThickness = 2.0;
                    }

                    if (ui.CardBorder != null)
                    {
                        ui.CardBorder.Background = bgBrush;
                        ui.CardBorder.BorderBrush = borderBrush;
                        ui.CardBorder.BorderThickness = new Thickness(borderThickness);
                    }

                    if (ui.NameText != null)
                    {
                        ui.NameText.Text = isOperating ? accName + " ● OPERANDO" : accName;
                        ui.NameText.Foreground = isOperating ? new SolidColorBrush(Color.FromRgb(0, 191, 255)) : Brushes.White;
                    }

                    if (ui.BadgeBorder != null && ui.BadgeText != null)
                        SetBadgeStyle(ui.BadgeBorder, ui.BadgeText, settings.Status, eff);
                }
                catch
                {
                    if (ui.EquityText != null)
                        ui.EquityText.Text = "Desconectada";
                }
            }

            bool anyAccountActiveToTrade = false;
            lock (accountsConfig)
            {
                foreach (var kvp in accountsConfig)
                {
                    if (kvp.Value.Enabled && kvp.Value.Status == "EN PROCESO" && kvp.Value.DailyStatus == "EN PROCESO")
                    {
                        anyAccountActiveToTrade = true;
                        break;
                    }
                }
            }

            if (!anyAccountActiveToTrade && masterTradingEnabled)
            {
                masterTradingEnabled = false;
                if (btnMasterSwitch != null)
                {
                    btnMasterSwitch.Content = "⚪ BOT: OFF";
                    btnMasterSwitch.Background = new SolidColorBrush(Color.FromRgb(178, 34, 34));
                }
                Print("[CCC] No quedan cuentas activas. BOT apagado.");
            }

            if (dashActiveCount != null) dashActiveCount.Text = activeCount.ToString();
            if (dashProfitCount != null) dashProfitCount.Text = profitCount.ToString();
            if (dashLossCount != null) dashLossCount.Text = lossCount.ToString();
            if (summaryBalanceText != null) summaryBalanceText.Text = "$" + totalBalance.ToString("N2", System.Globalization.CultureInfo.InvariantCulture);
            if (summaryPnLText != null)
            {
                summaryPnLText.Text = (totalPnL >= 0 ? "+" : "") + "$" + totalPnL.ToString("N2", System.Globalization.CultureInfo.InvariantCulture);
                summaryPnLText.Foreground = totalPnL >= 0 ? new SolidColorBrush(Color.FromRgb(0, 230, 118)) : new SolidColorBrush(Color.FromRgb(255, 82, 82));
            }

            UpdatePnLChart(totalPnL);
        }

        // =====================================================================
        //  GRÁFICO P&L EN VIVO
        // =====================================================================
        private void UpdatePnLChart(double totalPnL)
        {
            pnlHistory.Add(totalPnL);
            if (pnlHistory.Count > 300) pnlHistory.RemoveAt(0);

            if (pnlChartLine == null || pnlChartCanvas == null) return;
            if (pnlHistory.Count < 2) return;

            double canvasW = pnlChartCanvas.ActualWidth > 0 ? pnlChartCanvas.ActualWidth : 380;
            double canvasH = pnlChartCanvas.ActualHeight > 0 ? pnlChartCanvas.ActualHeight : 120;

            double minVal = pnlHistory.Min();
            double maxVal = pnlHistory.Max();
            double range = maxVal - minVal;
            if (range < 1) range = 1;

            double padding = range * 0.15;
            minVal -= padding;
            maxVal += padding;
            range = maxVal - minVal;

            PointCollection points = new PointCollection();
            double xStep = canvasW / (pnlHistory.Count - 1);

            for (int i = 0; i < pnlHistory.Count; i++)
            {
                double x = i * xStep;
                double y = canvasH - ((pnlHistory[i] - minVal) / range * canvasH);
                points.Add(new Point(x, y));
            }

            pnlChartLine.Points = points;

            double currentPnL = pnlHistory[pnlHistory.Count - 1];
            pnlChartLine.Stroke = currentPnL >= 0
                ? new SolidColorBrush(Color.FromRgb(0, 230, 118))
                : new SolidColorBrush(Color.FromRgb(255, 82, 82));

            if (pnlZeroLine != null)
            {
                double zeroY = canvasH - ((0 - minVal) / range * canvasH);
                zeroY = Math.Max(0, Math.Min(canvasH, zeroY));
                pnlZeroLine.Y1 = zeroY;
                pnlZeroLine.Y2 = zeroY;
                pnlZeroLine.X2 = canvasW;
            }

            if (pnlCurrentLabel != null)
            {
                pnlCurrentLabel.Text = (currentPnL >= 0 ? "+" : "") + "$" + currentPnL.ToString("F2");
                pnlCurrentLabel.Foreground = currentPnL >= 0
                    ? new SolidColorBrush(Color.FromRgb(0, 230, 118))
                    : new SolidColorBrush(Color.FromRgb(255, 82, 82));
            }
            if (pnlMaxLabel != null)
                pnlMaxLabel.Text = "▲ $" + (maxVal - padding).ToString("F0");
            if (pnlMinLabel != null)
                pnlMinLabel.Text = "▼ $" + (minVal + padding).ToString("F0");
        }

        // =====================================================================
        //  VENTANA CONFIGURACIÓN (MODAL WPF)
        // =====================================================================
        private TextBox AddFormInput(System.Windows.Controls.StackPanel parent, string label, string value)
        {
            System.Windows.Controls.Grid g = new System.Windows.Controls.Grid { Margin = new Thickness(0, 0, 0, 8) };
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(180, GridUnitType.Pixel) });
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            TextBlock lbl = new TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Foreground = Brushes.White };
            TextBox tb = new TextBox { Text = value, Padding = new Thickness(4, 3, 4, 3), Background = new SolidColorBrush(Color.FromRgb(45, 50, 60)), Foreground = Brushes.White, BorderBrush = new SolidColorBrush(Color.FromRgb(65, 70, 80)), BorderThickness = new Thickness(1) };

            System.Windows.Controls.Grid.SetColumn(lbl, 0);
            System.Windows.Controls.Grid.SetColumn(tb, 1);
            g.Children.Add(lbl);
            g.Children.Add(tb);
            parent.Children.Add(g);

            return tb;
        }

        private void OpenConfigModal(string accName)
        {
            AccountRiskSettings settings;
            bool isGlobal = accName.Equals("GLOBAL", StringComparison.OrdinalIgnoreCase);

            if (isGlobal)
            {
                settings = globalConfig;
            }
            else if (accountsConfig.ContainsKey(accName))
            {
                settings = accountsConfig[accName];
            }
            else
            {
                settings = new AccountRiskSettings(accName);
                accountsConfig[accName] = settings;
            }

            Window configWin = new Window
            {
                Title = isGlobal ? "⚙ Configuración GLOBAL" : "⚙ Configuración — " + accName,
                Width = 460,
                Height = 420,
                WindowStartupLocation = WindowStartupLocation.CenterScreen,
                ResizeMode = ResizeMode.NoResize,
                Background = new SolidColorBrush(Color.FromRgb(30, 33, 40))
            };

            System.Windows.Controls.StackPanel stack = new System.Windows.Controls.StackPanel { Margin = new Thickness(18) };

            ScrollViewer sv = new ScrollViewer
            {
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Content = stack
            };
            configWin.Content = sv;

            stack.Children.Add(new TextBlock
            {
                Text = isGlobal ? "⚡ PARÁMETROS GLOBALES" : "⚡ " + accName.ToUpper(),
                FontWeight = FontWeights.Bold,
                FontSize = 15,
                Foreground = new SolidColorBrush(Color.FromRgb(0, 212, 255)),
                Margin = new Thickness(0, 0, 0, 12)
            });

            // RIESGO
            stack.Children.Add(new TextBlock { Text = "─── RIESGO ───", FontSize = 10, Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)), Margin = new Thickness(0, 0, 0, 6) });

            TextBox dailyProfitInput = AddFormInput(stack, "Objetivo Diario Ganancia ($):", settings.DailyProfitLimit.ToString(System.Globalization.CultureInfo.InvariantCulture));
            TextBox dailyLossInput = AddFormInput(stack, "Límite Diario Pérdida ($):", settings.DailyLossLimit.ToString(System.Globalization.CultureInfo.InvariantCulture));
            TextBox lotsInput = AddFormInput(stack, "Contratos (Lotes):", settings.Lots.ToString());
            TextBox tpInput = AddFormInput(stack, "Take Profit (USD):", settings.TpUsd.ToString(System.Globalization.CultureInfo.InvariantCulture));
            TextBox slInput = AddFormInput(stack, "Stop Loss (USD):", settings.SlUsd.ToString(System.Globalization.CultureInfo.InvariantCulture));
            TextBox commissionInput = AddFormInput(stack, "Comisión por Contrato/Lado ($):", settings.CommissionPerContract.ToString(System.Globalization.CultureInfo.InvariantCulture));

            // HORARIO
            stack.Children.Add(new TextBlock { Text = "─── FILTRO HORARIO ───", FontSize = 10, Foreground = new SolidColorBrush(Color.FromRgb(125, 133, 144)), Margin = new Thickness(0, 6, 0, 6) });

            CheckBox timeCheck = new CheckBox { Content = "Habilitar Filtro Horario", IsChecked = settings.TimeFilterEnabled, Margin = new Thickness(0, 0, 0, 5), Foreground = Brushes.White };
            stack.Children.Add(timeCheck);

            TextBox startTimeInput = AddFormInput(stack, "Hora Inicio (HH:MM):", settings.StartTime);
            TextBox endTimeInput = AddFormInput(stack, "Hora Fin (HH:MM):", settings.EndTime);

            // GUARDAR
            System.Windows.Controls.Button saveBtn = new System.Windows.Controls.Button
            {
                Content = "💾 GUARDAR PARÁMETROS",
                Background = new SolidColorBrush(Color.FromRgb(0, 140, 70)),
                Foreground = Brushes.White,
                FontWeight = FontWeights.Bold,
                FontSize = 13,
                Padding = new Thickness(10),
                Margin = new Thickness(0, 20, 0, 0),
                BorderThickness = new Thickness(0),
                Cursor = System.Windows.Input.Cursors.Hand
            };
            saveBtn.Click += (s, e) =>
            {
                try
                {
                    settings.DailyProfitLimit = double.Parse(dailyProfitInput.Text, System.Globalization.CultureInfo.InvariantCulture);
                    settings.DailyLossLimit = double.Parse(dailyLossInput.Text, System.Globalization.CultureInfo.InvariantCulture);
                    settings.Lots = int.Parse(lotsInput.Text);
                    settings.TpUsd = double.Parse(tpInput.Text, System.Globalization.CultureInfo.InvariantCulture);
                    settings.SlUsd = double.Parse(slInput.Text, System.Globalization.CultureInfo.InvariantCulture);
                    settings.CommissionPerContract = double.Parse(commissionInput.Text, System.Globalization.CultureInfo.InvariantCulture);
                    settings.TimeFilterEnabled = timeCheck.IsChecked ?? false;
                    settings.StartTime = startTimeInput.Text;
                    settings.EndTime = endTimeInput.Text;

                    if (isGlobal)
                    {
                        foreach (var kvp in accountsConfig)
                        {
                            AccountRiskSettings accSettings = kvp.Value;
                            if (accSettings.Locked) continue;

                            accSettings.DailyProfitLimit = settings.DailyProfitLimit;
                            accSettings.DailyLossLimit = settings.DailyLossLimit;
                            accSettings.Lots = settings.Lots;
                            accSettings.TpUsd = settings.TpUsd;
                            accSettings.SlUsd = settings.SlUsd;
                            accSettings.CommissionPerContract = settings.CommissionPerContract;
                            accSettings.TimeFilterEnabled = settings.TimeFilterEnabled;
                            accSettings.StartTime = settings.StartTime;
                            accSettings.EndTime = settings.EndTime;
                        }
                    }

                    SaveConfiguration();
                    BuildAccountsListUI();
                    configWin.Close();
                }
                catch (Exception ex)
                {
                    MessageBox.Show("Error en los datos: " + ex.Message);
                }
            };
            stack.Children.Add(saveBtn);

            configWin.ShowDialog();
        }
    }
}

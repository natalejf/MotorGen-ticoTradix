    public static class StratixLicenseHub {
        public static string ServerUrl = "http://127.0.0.1:8000";
        public static string LicenseKey = "";
        public static string Plan = "SIN VERIFICAR";
        public static string Holder = "";
        public static string StatusMessage = "Sin conectar";
        public static bool IsValid = false;

        public static string BaseDir {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Stratix"); }
        }
        public static string ConfigPath {
            get { return Path.Combine(BaseDir, "StratixLicense.cfg"); }
        }

        public static void LoadSavedConfig() {
            try {
                if (!File.Exists(ConfigPath)) return;
                foreach (string raw in File.ReadAllLines(ConfigPath)) {
                    int idx = raw.IndexOf('=');
                    if (idx <= 0) continue;
                    string k = raw.Substring(0, idx).Trim().ToLowerInvariant();
                    string v = raw.Substring(idx + 1).Trim();
                    if (k == "url" && (v.StartsWith("http://", StringComparison.OrdinalIgnoreCase) || v.StartsWith("https://", StringComparison.OrdinalIgnoreCase)))
                        ServerUrl = v.TrimEnd('/');
                    else if (k == "license_key")
                        LicenseKey = v;
                }
            } catch {}
        }

        public static void SaveConfig(string url, string key) {
            Directory.CreateDirectory(BaseDir);
            ServerUrl = string.IsNullOrWhiteSpace(url) ? "http://127.0.0.1:8000" : url.Trim().TrimEnd('/');
            LicenseKey = (key ?? "").Trim();
            File.WriteAllLines(ConfigPath, new[] { "url=" + ServerUrl, "license_key=" + LicenseKey });
        }

        private static string EscapeJson(string s) {
            return "\"" + (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "").Replace("\n", "") + "\"";
        }

        public static bool ValidateAndProvision(string url, string key, out string message) {
            SaveConfig(url, key);
            if (string.IsNullOrEmpty(LicenseKey)) {
                IsValid = false;
                StatusMessage = "Ingresa tu Clave de Licencia Stratix";
                message = StatusMessage;
                return false;
            }
            try {
                var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create(ServerUrl + "/api/licenses/validate?format=wire");
                req.Method = "POST";
                req.ContentType = "application/json";
                req.Accept = "text/plain";
                req.Timeout = 5000;
                req.ReadWriteTimeout = 5000;
                string body = "{\"license_key\":" + EscapeJson(LicenseKey) + ",\"machine_name\":" + EscapeJson(Environment.MachineName) + ",\"machine_id\":" + EscapeJson(Environment.UserName + "@" + Environment.MachineName) + "}";
                byte[] bytes = Encoding.UTF8.GetBytes(body);
                req.ContentLength = bytes.Length;
                using (var s = req.GetRequestStream()) s.Write(bytes, 0, bytes.Length);
                string respText;
                using (var resp = req.GetResponse())
                using (var reader = new StreamReader(resp.GetResponseStream()))
                    respText = reader.ReadToEnd();

                var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                foreach (string line in respText.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)) {
                    int idx = line.IndexOf('=');
                    if (idx > 0) map[line.Substring(0, idx).Trim()] = line.Substring(idx + 1).Trim();
                }
                if (!map.ContainsKey("ok") || map["ok"] != "1") {
                    IsValid = false;
                    StatusMessage = "Licencia rechazada por el servidor";
                    message = StatusMessage;
                    return false;
                }
                Plan = map.ContainsKey("plan") ? map["plan"] : "PRO";
                Holder = map.ContainsKey("holder") ? map["holder"] : "";
                if (map.ContainsKey("proppass_id") && !string.IsNullOrEmpty(map["proppass_id"]) && map.ContainsKey("proppass_token")) {
                    string ppDir = Path.Combine(BaseDir, "NinjaTrader");
                    Directory.CreateDirectory(ppDir);
                    File.WriteAllLines(Path.Combine(ppDir, "CandleBridge.key"), new[] { map["proppass_id"], map["proppass_token"] });
                }
                if (map.ContainsKey("rocket_id") && !string.IsNullOrEmpty(map["rocket_id"]) && map.ContainsKey("rocket_token")) {
                    string rkDir = Path.Combine(BaseDir, "RocketPass");
                    Directory.CreateDirectory(rkDir);
                    File.WriteAllLines(Path.Combine(rkDir, "RocketBridge.key"), new[] { map["rocket_id"], map["rocket_token"] });
                }
                IsValid = true;
                StatusMessage = "Licencia ACTIVA (" + Plan + ") · PropPass y RocketPass vinculados";
                message = StatusMessage;
                return true;
            } catch (System.Net.WebException wex) {
                IsValid = false;
                string detail = wex.Message;
                try {
                    if (wex.Response != null) {
                        using (var r = new StreamReader(wex.Response.GetResponseStream())) detail = r.ReadToEnd();
                    }
                } catch {}
                StatusMessage = "Error de licencia/conexión: " + detail;
                message = StatusMessage;
                return false;
            } catch (Exception ex) {
                IsValid = false;
                StatusMessage = "Error: " + ex.Message;
                message = StatusMessage;
                return false;
            }
        }
    }

    public class StratixSuiteMenu : AddOnBase {
        private NTMenuItem menuItem;
        private NTMenuItem parentMenu;

        protected override void OnStateChange() {
            if (State == State.SetDefaults) {
                Name = "StratixSuiteMenu";
                Description = "Stratix Connector Unificado (Licencia, PropPass y RocketPass)";
            } else if (State == State.Active) {
                StratixLicenseHub.LoadSavedConfig();
                if (!string.IsNullOrEmpty(StratixLicenseHub.LicenseKey)) {
                    System.Threading.Tasks.Task.Run(() => {
                        string msg;
                        StratixLicenseHub.ValidateAndProvision(StratixLicenseHub.ServerUrl, StratixLicenseHub.LicenseKey, out msg);
                        Print("Stratix Connector: " + msg);
                    });
                }
            }
        }

        protected override void OnWindowCreated(Window window) {
            ControlCenter cc = window as ControlCenter;
            if (cc == null) return;
            parentMenu = cc.FindFirst("ControlCenterMenuItemNew") as NTMenuItem;
            if (parentMenu == null) return;
            menuItem = new NTMenuItem { Header = "Stratix Connector (Licencia)" };
            menuItem.Click += OnMenuItemClick;
            parentMenu.Items.Add(menuItem);
        }

        protected override void OnWindowDestroyed(Window window) {
            if (menuItem != null && parentMenu != null) {
                menuItem.Click -= OnMenuItemClick;
                parentMenu.Items.Remove(menuItem);
                menuItem = null;
            }
        }

        private void OnMenuItemClick(object sender, RoutedEventArgs e) {
            StratixLicenseHub.LoadSavedConfig();
            var win = new Window {
                Title = "STRATIX · Connector Unificado & Licencia",
                Width = 480,
                Height = 360,
                WindowStartupLocation = WindowStartupLocation.CenterScreen,
                ResizeMode = ResizeMode.NoResize,
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#101210")),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#e8ece2"))
            };

            var root = new StackPanel { Margin = new Thickness(22) };
            var title = new TextBlock {
                Text = "STRATIX CONNECTOR UNIFICADO",
                FontSize = 16,
                FontWeight = FontWeights.Bold,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#d6ae79")),
                Margin = new Thickness(0, 0, 0, 4)
            };
            var sub = new TextBlock {
                Text = "Conecta PropPass + RocketPass con tu Clave de Licencia (Local o VPS).",
                FontSize = 11,
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#aeb5a4")),
                Margin = new Thickness(0, 0, 0, 16)
            };

            var lblUrl = new TextBlock { Text = "URL del Servidor Stratix (Local o Nube/VPS)", FontSize = 11, Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#8f978b")) };
            var txtUrl = new TextBox {
                Text = StratixLicenseHub.ServerUrl,
                Margin = new Thickness(0, 4, 0, 12),
                Padding = new Thickness(8, 6, 8, 6),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#1b1e19")),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#e8ece2")),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#52442e"))
            };

            var lblKey = new TextBlock { Text = "Clave de Licencia Stratix (ej. STX-PRO-XXXX-XXXX)", FontSize = 11, Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#8f978b")) };
            var txtKey = new TextBox {
                Text = StratixLicenseHub.LicenseKey,
                Margin = new Thickness(0, 4, 0, 16),
                Padding = new Thickness(8, 6, 8, 6),
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#1b1e19")),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#e8ece2")),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#52442e"))
            };

            var statusText = new TextBlock {
                Text = StratixLicenseHub.StatusMessage,
                TextWrapping = TextWrapping.Wrap,
                FontSize = 11,
                Margin = new Thickness(0, 12, 0, 0),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(StratixLicenseHub.IsValid ? "#51d58a" : "#d6ae79"))
            };

            var btnConnect = new Button {
                Content = "Validar Licencia y Conectar Todo",
                Padding = new Thickness(14, 10, 14, 10),
                FontWeight = FontWeights.Bold,
                Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#bc8a50")),
                Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#14120c")),
                BorderBrush = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#d0a36c")),
                Cursor = System.Windows.Input.Cursors.Hand
            };

            btnConnect.Click += (s, ev) => {
                btnConnect.IsEnabled = false;
                statusText.Text = "Validando licencia y sincronizando PropPass + RocketPass...";
                statusText.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#d6ae79"));
                string u = txtUrl.Text, k = txtKey.Text;
                System.Threading.Tasks.Task.Run(() => {
                    string msg;
                    bool ok = StratixLicenseHub.ValidateAndProvision(u, k, out msg);
                    win.Dispatcher.BeginInvoke(new Action(() => {
                        btnConnect.IsEnabled = true;
                        statusText.Text = msg;
                        statusText.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(ok ? "#51d58a" : "#ef7171"));
                    }));
                });
            };

            root.Children.Add(title);
            root.Children.Add(sub);
            root.Children.Add(lblUrl);
            root.Children.Add(txtUrl);
            root.Children.Add(lblKey);
            root.Children.Add(txtKey);
            root.Children.Add(btnConnect);
            root.Children.Add(statusText);
            win.Content = root;
            win.Show();
        }
    }

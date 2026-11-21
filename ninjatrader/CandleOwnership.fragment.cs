        private readonly HashSet<string> candleOwnedAccounts=new HashSet<string>();
        private readonly HashSet<string> candleOwnershipConflicts=new HashSet<string>();
        private readonly Dictionary<string,DateTime> candleFlatSince=new Dictionary<string,DateTime>();
        private bool IsCandleOrder(string account,Order order) {
            if(order==null)return false;
            string n=order.Name??"";
            if(string.IsNullOrEmpty(n)||n.IndexOf("Close",StringComparison.OrdinalIgnoreCase)>=0||n.IndexOf("Flatten",StringComparison.OrdinalIgnoreCase)>=0)return true;
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

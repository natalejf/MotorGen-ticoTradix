        private readonly HashSet<string> candleOwnedAccounts=new HashSet<string>();
        private readonly HashSet<string> candleOwnershipConflicts=new HashSet<string>();
        private readonly Dictionary<string,DateTime> candleFlatSince=new Dictionary<string,DateTime>();
        private bool IsCandleOrder(string account,Order order) {
            return order!=null&&(order.Name=="EntryLong"||order.Name=="EntryShort"||order.Name=="TP_"+account||order.Name=="SL_"+account);
        }
        private bool CanManageCandle(Account account,Instrument instrument) {
            if(account==null||instrument==null||!groupAccounts.Contains(account.Name)||!candleOwnedAccounts.Contains(account.Name)||candleOwnershipConflicts.Contains(account.Name))return false;
            if(engineLeases.Values.Any(l=>l.Account==account.Name))return false;
            return !account.Orders.Cast<Order>().Any(o=>o.Instrument.FullName==instrument.FullName&&EngineWorking(o)&&!IsCandleOrder(account.Name,o)&&o.Name!="Close");
        }
        private void ObserveCandleExecution(ExecutionEventArgs e) {
            if(e.Execution==null||e.Execution.Account==null||e.Execution.Order==null||Instrument==null)return;
            var account=e.Execution.Account;var order=e.Execution.Order;
            if(order.Instrument.FullName!=Instrument.FullName||!candleOwnedAccounts.Contains(account.Name)||engineLeases.Values.Any(l=>l.Account==account.Name))return;
            if(!IsCandleOrder(account.Name,order)&&order.Name!="Close") {
                candleOwnershipConflicts.Add(account.Name);
                AccountRiskSettings setting;if(accountsConfig.TryGetValue(account.Name,out setting))setting.Enabled=false;
                PauseEntries("OWNERSHIP_CONFLICT","Se detectó una operación externa mezclada en "+account.Name+"; PropPass no cerrará esa cuenta automáticamente");
            }
        }
        private void RefreshCandleOwnership() {
            foreach(string name in candleOwnedAccounts.ToArray()) {
                var account=GetAccountCached(name);if(account==null||Instrument==null)continue;
                AccountRiskSettings setting;if(accountsConfig.TryGetValue(name,out setting)&&(DateTime.UtcNow-setting.LastEntryTime).TotalSeconds<15)continue;
                if(!account.Positions.Cast<Position>().Any(p=>p.Instrument.FullName==Instrument.FullName&&p.MarketPosition!=MarketPosition.Flat)&&!account.Orders.Cast<Order>().Any(o=>o.Instrument.FullName==Instrument.FullName&&EngineWorking(o)&&IsCandleOrder(name,o))) {
                    DateTime since;if(!candleFlatSince.TryGetValue(name,out since)){candleFlatSince[name]=DateTime.UtcNow;continue;}
                    if((DateTime.UtcNow-since).TotalSeconds<15)continue;
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

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

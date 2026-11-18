        private sealed class BridgeHealth {
            public const double TimeoutSeconds=10;
            public DateTime LastSuccess;
            public int Failures;
            public string LastError="",PauseCode="",PauseReason="";
            public DateTime PauseAt=DateTime.MinValue;
            public bool Paused;
            public BridgeHealth(DateTime now) {LastSuccess=now;}
            public static bool FatalHttp(int status) {return status>=400&&status<500&&status!=408&&status!=429;}
            public bool Expired(DateTime now) {return (now-LastSuccess).TotalSeconds>=TimeoutSeconds;}
            public void Failure(string error) {Failures++;LastError=error;}
            public void Success(DateTime now) {LastSuccess=now;Failures=0;LastError="";}
            public void Pause(string code,string reason,DateTime now) {Paused=true;PauseCode=code;PauseReason=reason;PauseAt=now;}
            public bool Check(DateTime now) {
                if(Paused||!Expired(now))return false;
                Pause("COMMUNICATION_TIMEOUT","Sin confirmación del servidor durante 10 segundos. Último error: "+(LastError.Length==0?"sin respuesta":LastError),now);
                return true;
            }
            public void Resume(DateTime now) {
                if(Expired(now))throw new InvalidOperationException("No se reanuda sin comunicación reciente con el servidor");
                Paused=false;PauseCode="";PauseReason="";PauseAt=DateTime.MinValue;
            }
        }

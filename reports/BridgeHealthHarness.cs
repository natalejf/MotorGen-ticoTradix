using System;class Program {
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
                Pause("COMMUNICATION_TIMEOUT","Sin confirmaciÃ³n del servidor durante 10 segundos. Ãšltimo error: "+(LastError.Length==0?"sin respuesta":LastError),now);
                return true;
            }
            public void Resume(DateTime now) {
                if(Expired(now))throw new InvalidOperationException("No se reanuda sin comunicaciÃ³n reciente con el servidor");
                Paused=false;PauseCode="";PauseReason="";PauseAt=DateTime.MinValue;
            }
        }

static void Assert(bool condition,string message){if(!condition)throw new Exception(message);}
static void Main(){var now=new DateTime(2026,11,17,0,0,0,DateTimeKind.Utc);var h=new BridgeHealth(now);Assert(!BridgeHealth.FatalHttp(408)&&!BridgeHealth.FatalHttp(429)&&!BridgeHealth.FatalHttp(503),"transient HTTP status");Assert(BridgeHealth.FatalHttp(401)&&BridgeHealth.FatalHttp(403)&&BridgeHealth.FatalHttp(409),"authentication and instance errors pause immediately");
h.Failure("Timeout");Assert(!h.Check(now.AddSeconds(2)),"single timeout must not pause");Assert(!h.Check(now.AddSeconds(9.999)),"grace period");h.Success(now.AddSeconds(3));Assert(h.Failures==0,"recovery resets failures");Assert(!h.Paused,"transient recovery preserves running state");
h.Failure("Timeout");h.Failure("ConnectFailure");Assert(h.Check(now.AddSeconds(13)),"ten seconds pauses");Assert(h.PauseCode=="COMMUNICATION_TIMEOUT","pause has code");Assert(h.PauseReason.Contains("ConnectFailure"),"pause has last error");Assert(!h.Check(now.AddSeconds(14)),"no repeated pause event");h.Success(now.AddSeconds(14));Assert(h.Paused,"recovery must not rearm");h.Resume(now.AddSeconds(14));Assert(!h.Paused&&h.PauseReason=="","explicit resume clears pause");
h.Pause("MANUAL","User pause",now.AddSeconds(15));h.Success(now.AddSeconds(16));Assert(h.Paused&&h.PauseCode=="MANUAL","manual pause survives recovery");
try{h.Resume(now.AddSeconds(26));throw new Exception("stale resume accepted");}catch(InvalidOperationException){}
h.Success(now.AddSeconds(27));h.Resume(now.AddSeconds(27));Assert(!h.Paused,"recent explicit resume accepted");
h.Pause("COMMUNICATION_REJECTED","HTTP 401",now.AddSeconds(28));Assert(h.Paused&&h.PauseCode=="COMMUNICATION_REJECTED","protocol rejection has explicit cause");
Console.WriteLine("PASS: brief failures tolerated; exact 10s cutoff; error reason; recovery never rearms; explicit resume; stale resume rejected; manual and protocol pauses preserved.");}

}
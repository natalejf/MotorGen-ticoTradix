$ErrorActionPreference='Stop'
$taskRoot=Split-Path $PSScriptRoot -Parent
$taskMath=(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'RocketMath.fragment.cs') -Raw).Replace('private static class RocketMath','public static class RocketMath')
$taskChecks=@'
class Check {
 static void Assert(bool v,string m){if(!v)throw new Exception(m);}
 static int Main(){
  var exits=RocketMath.Protection(20000,2,2,2000,1500,1,.25);
  Assert(exits[0]==19500 && exits[1]==20375,"MNQ 2 contracts USD global protection");
  var threeLimits=RocketMath.Levels(20000,19750,.25,3);
  var threeStops=RocketMath.Levels(20000,20187.5,.25,3);
  Assert(threeLimits.SequenceEqual(new[]{19937.5,19875.0,19812.5}),"three limits at 25 50 75 percent, excluding SL");
  Assert(threeStops.SequenceEqual(new[]{20047.0,20093.75,20140.5}),"three stops at 25 50 75 percent, excluding TP");
  var limits=RocketMath.Levels(20000,exits[0],.25,10);var stops=RocketMath.Levels(20000,exits[1],.25,10);
  Assert(limits.Length==10&&limits.Distinct().Count()==10&&limits.All(x=>x>19500&&x<20000),"10 distinct limits inside SL");
  Assert(stops.All(x=>x>20000&&x<20375),"stops between entry and TP");
  var scaled=RocketMath.Protection(19950,4,2,2000,1500,1,.25);
  Assert(Math.Abs((19950-scaled[0])*4*2-2000)<.001,"same basket cash loss after scale in");
  var shortExits=RocketMath.Protection(20000,2,2,2000,1500,-1,.25);
  Assert(shortExits[0]==20500&&shortExits[1]==19625,"short geometry");
  bool rejected=false;try{RocketMath.Levels(20000,20000.5,.25,10);}catch(ArgumentException){rejected=true;}Assert(rejected,"reject levels that do not fit tick size");
  var bulls=Enumerable.Repeat(1,21).Concat(Enumerable.Repeat(-1,19));
  var bears=Enumerable.Repeat(-1,21).Concat(Enumerable.Repeat(1,19));
  Assert(RocketMath.VoteSignal(bulls,"AUTO")==1,"majority bullish buys");
  Assert(RocketMath.VoteSignal(bears,"AUTO")==-1,"majority bearish sells");
  Assert(RocketMath.VoteSignal(Enumerable.Repeat(1,20).Concat(Enumerable.Repeat(-1,20)),"AUTO")==0,"tie has no signal");
  Assert(RocketMath.VoteSignal(bears,"LONG")==0,"long-only respects vote");
  Assert(RocketMath.VoteSignal(bulls,"SHORT")==0,"short-only respects vote");
  Assert(RocketMath.VoteSignal(Enumerable.Repeat(1,39),"AUTO")==0,"warmup needs 40 closed candles");
  Assert(RocketMath.VoteSignal(Enumerable.Repeat(0,40),"AUTO")==0,"doji ignored");
  Console.WriteLine("Rocket native math: 15 checks passed");return 0;
 }
}

'@
$taskSource=Join-Path $taskRoot 'reports\RocketMathHarness.cs'
$taskExe=Join-Path $taskRoot 'reports\RocketMathHarness.exe'
('using System;using System.Linq;'+[Environment]::NewLine+$taskMath+[Environment]::NewLine+$taskChecks) | Set-Content -LiteralPath $taskSource -Encoding utf8
& 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe' /nologo ('/out:'+$taskExe) $taskSource
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $taskExe
exit $LASTEXITCODE

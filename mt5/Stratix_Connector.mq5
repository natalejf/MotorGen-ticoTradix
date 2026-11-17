#property strict
#property version "1.02"
#property description "Stratix local connector - DEMO HEDGING only"
input string StratixURL="http://127.0.0.1:8000";
input string AccountID="";
input string ConnectionKey="";
input long ExpectedLogin=0;
input string ExpectedServer="";
string fields[];
long lastEventSeq=-1;
int previousHttpStatus=0;
datetime lastConnectionWarning=0;
bool identityWarning=false,brokerWarning=false;

string Quote(string s) {
   StringReplace(s,"\\","\\\\"); StringReplace(s,"\"","\\\"");
   StringReplace(s,"\r","\\r"); StringReplace(s,"\n","\\n"); StringReplace(s,"\t","\\t");
   return "\""+s+"\"";
}
string Num(double v) { return DoubleToString(v,10); }
string Int(long v) { return IntegerToString(v); }
string Bool(bool v) { return v?"true":"false"; }
string Arg(string name,string fallback="") {
   string prefix=name+"=";
   for(int i=2;i<ArraySize(fields);i++) if(StringFind(fields[i],prefix)==0) return StringSubstr(fields[i],StringLen(prefix));
   return fallback;
}
double Val(string name,double fallback=0) { return StringToDouble(Arg(name,Num(fallback))); }
bool Identity() {
   return ExpectedLogin>0 && AccountInfoInteger(ACCOUNT_LOGIN)==ExpectedLogin &&
      AccountInfoString(ACCOUNT_SERVER)==ExpectedServer && AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
      AccountInfoInteger(ACCOUNT_MARGIN_MODE)==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
}
int Http(string method,string path,string body,string &response) {
   char data[],result[]; string headers;
   StringToCharArray(body,data,0,WHOLE_ARRAY,CP_UTF8);
   if(ArraySize(data)>0) ArrayResize(data,ArraySize(data)-1);
   int status=WebRequest(method,StratixURL+"/api/copy/ea/"+AccountID+path,
      "Content-Type: application/json\r\nX-Stratix-Key: "+ConnectionKey+"\r\n",2000,data,result,headers);
   response=CharArrayToString(result,0,WHOLE_ARRAY,CP_UTF8);
   return status;
}
string Positions() {
   string out="[";
   for(int i=0;i<PositionsTotal();i++) {
      ulong ticket=PositionGetTicket(i); if(ticket==0) continue;
      if(StringLen(out)>1) out+=",";
      out+="{\"ticket\":"+Int((long)ticket)+",\"symbol\":"+Quote(PositionGetString(POSITION_SYMBOL))+
         ",\"type\":"+Int(PositionGetInteger(POSITION_TYPE))+",\"volume\":"+Num(PositionGetDouble(POSITION_VOLUME))+
         ",\"price_open\":"+Num(PositionGetDouble(POSITION_PRICE_OPEN))+",\"sl\":"+Num(PositionGetDouble(POSITION_SL))+
         ",\"tp\":"+Num(PositionGetDouble(POSITION_TP))+",\"magic\":"+Int(PositionGetInteger(POSITION_MAGIC))+
         ",\"comment\":"+Quote(PositionGetString(POSITION_COMMENT))+",\"time\":"+Int(PositionGetInteger(POSITION_TIME))+"}";
   }
   return out+"]";
}
string Orders() {
   string out="[";
   for(int i=0;i<OrdersTotal();i++) {
      ulong ticket=OrderGetTicket(i); if(ticket==0) continue;
      if(StringLen(out)>1) out+=",";
      out+="{\"ticket\":"+Int((long)ticket)+",\"symbol\":"+Quote(OrderGetString(ORDER_SYMBOL))+
         ",\"type\":"+Int(OrderGetInteger(ORDER_TYPE))+",\"volume\":"+Num(OrderGetDouble(ORDER_VOLUME_CURRENT))+
         ",\"price_open\":"+Num(OrderGetDouble(ORDER_PRICE_OPEN))+",\"sl\":"+Num(OrderGetDouble(ORDER_SL))+
         ",\"tp\":"+Num(OrderGetDouble(ORDER_TP))+",\"magic\":"+Int(OrderGetInteger(ORDER_MAGIC))+
         ",\"comment\":"+Quote(OrderGetString(ORDER_COMMENT))+",\"time\":"+Int(OrderGetInteger(ORDER_TIME_SETUP))+"}";
   }
   return out+"]";
}
string Execute(string method) {
   if(!Identity()) return "{\"error\":\"Solo DEMO HEDGING y login/servidor vinculados\"}";
   string symbol=Arg("symbol");
   if(method=="account_info") return "{\"login\":"+Int(AccountInfoInteger(ACCOUNT_LOGIN))+
      ",\"server\":"+Quote(AccountInfoString(ACCOUNT_SERVER))+",\"trade_mode\":0,\"margin_mode\":2,\"equity\":"+
      Num(AccountInfoDouble(ACCOUNT_EQUITY))+",\"balance\":"+Num(AccountInfoDouble(ACCOUNT_BALANCE))+
      ",\"currency\":"+Quote(AccountInfoString(ACCOUNT_CURRENCY))+",\"trade_allowed\":"+Bool((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))+"}";
   if(method=="terminal_info") return "{\"connected\":"+Bool((bool)TerminalInfoInteger(TERMINAL_CONNECTED))+
      ",\"trade_allowed\":"+Bool((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && (bool)MQLInfoInteger(MQL_TRADE_ALLOWED))+"}";
   if(method=="positions_get") return Positions();
   if(method=="orders_get") return Orders();
   if(method=="history") {
      if(!HistorySelectByPosition((ulong)Val("position"))) return "[]";
      string out="[";
      for(int i=0;i<HistoryDealsTotal();i++) {
         ulong deal=HistoryDealGetTicket(i); if(deal==0) continue;
         if(StringLen(out)>1) out+=",";
         out+="{\"reason\":"+Int(HistoryDealGetInteger(deal,DEAL_REASON))+",\"volume\":"+Num(HistoryDealGetDouble(deal,DEAL_VOLUME))+"}";
      }
      return out+"]";
   }
   if(method=="symbol_select") return Bool(SymbolSelect(symbol,true));
   if(method=="symbol_info") {
      if(!SymbolSelect(symbol,true)) return "{\"error\":\"Simbolo no disponible\"}";
      return "{\"point\":"+Num(SymbolInfoDouble(symbol,SYMBOL_POINT))+",\"digits\":"+Int(SymbolInfoInteger(symbol,SYMBOL_DIGITS))+
         ",\"volume_min\":"+Num(SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN))+",\"volume_max\":"+Num(SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX))+
         ",\"volume_step\":"+Num(SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP))+",\"trade_stops_level\":"+Int(SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL))+
         ",\"trade_freeze_level\":"+Int(SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL))+",\"filling_mode\":"+Int(SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE))+
         ",\"trade_exemode\":"+Int(SymbolInfoInteger(symbol,SYMBOL_TRADE_EXEMODE))+
         ",\"expiration_mode\":"+Int(SymbolInfoInteger(symbol,SYMBOL_EXPIRATION_MODE))+"}";
   }
   if(method=="tick") {
      MqlTick tick; if(!SymbolInfoTick(symbol,tick)) return "{\"error\":\"Sin tick\"}";
      return "{\"bid\":"+Num(tick.bid)+",\"ask\":"+Num(tick.ask)+",\"time\":"+Int((long)tick.time)+"}";
   }
   if(method=="profit") {
      double profit;
      if(!OrderCalcProfit((ENUM_ORDER_TYPE)(int)Val("type"),symbol,Val("volume"),Val("price"),Val("sl"),profit)) return "null";
      return Num(profit);
   }
   if(method=="bars") {
      ResetLastError();
      if(!SymbolSelect(symbol,true)) return "{\"error\":"+Quote("Simbolo MT5 no disponible: "+symbol+"; codigo "+Int(GetLastError()))+"}";
      MqlRates rates[]; int count=MathMin(1000,(int)Val("count",1000));
      int n=CopyRates(symbol,(ENUM_TIMEFRAMES)(int)Val("timeframe"),(int)Val("start",1),count,rates);
      if(n<0) return "{\"error\":"+Quote("Esperando historico: "+symbol+"; TF "+Arg("timeframe")+"; codigo "+Int(GetLastError()))+"}";
      string out="[";
      for(int i=0;i<n;i++) {
         if(i>0) out+=",";
         out+="{\"time\":"+Int((long)rates[i].time)+",\"open\":"+Num(rates[i].open)+",\"high\":"+Num(rates[i].high)+
            ",\"low\":"+Num(rates[i].low)+",\"close\":"+Num(rates[i].close)+",\"tick_volume\":"+Int(rates[i].tick_volume)+"}";
      }
      return out+"]";
   }
   if(method=="order_check" || method=="order_send") {
      if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
         return "{\"error\":\"Trading algoritmico deshabilitado\"}";
      MqlTradeRequest req={};
      req.action=(ENUM_TRADE_REQUEST_ACTIONS)(int)Val("action"); req.symbol=symbol;
      req.magic=(ulong)Val("magic"); req.order=(ulong)Val("order"); req.position=(ulong)Val("position");
      req.volume=Val("volume"); req.price=Val("price"); req.sl=Val("sl"); req.tp=Val("tp");
      req.deviation=(ulong)Val("deviation"); req.type=(ENUM_ORDER_TYPE)(int)Val("type");
      req.type_filling=(ENUM_ORDER_TYPE_FILLING)(int)Val("type_filling"); req.type_time=(ENUM_ORDER_TYPE_TIME)(int)Val("type_time");
      req.comment=Arg("comment"); req.expiration=(datetime)Val("expiration");
      if(req.magic<100000000 || StringFind(req.comment,"STX")!=0) return "{\"error\":\"Instruccion sin atribucion Stratix\"}";
      // The bridge never modifies a manual position/order even with a malformed command.
      if(req.position>0 && (!PositionSelectByTicket(req.position) || PositionGetInteger(POSITION_MAGIC)!=(long)req.magic))
         return "{\"error\":\"Posicion ajena o inexistente\"}";
      if(req.order>0 && (!OrderSelect(req.order) || OrderGetInteger(ORDER_MAGIC)!=(long)req.magic))
         return "{\"error\":\"Orden ajena o inexistente\"}";
      if(method=="order_check") {
         MqlTradeCheckResult check={}; bool ok=OrderCheck(req,check);
         return "{\"retcode\":"+Int(ok?0:(check.retcode==0?-1:(long)check.retcode))+",\"comment\":"+Quote(check.comment)+"}";
      }
      MqlTradeResult result={}; bool sent=OrderSend(req,result);
      Print("Stratix | ORDEN | accion=",(int)req.action," tipo=",(int)req.type," simbolo=",req.symbol,
            " volumen=",req.volume," ticket=",result.order," posicion=",req.position,
            " retcode=",result.retcode," ",result.comment);
      if(!sent && result.retcode==0) return "{\"error\":\"OrderSend sin resultado confirmado\"}";
      return "{\"retcode\":"+Int(result.retcode)+",\"order\":"+Int((long)result.order)+",\"volume\":"+Num(result.volume)+",\"comment\":"+Quote(result.comment)+"}";
   }
   return "{\"error\":\"Metodo no admitido\"}";
}
int OnInit() {
   if(StringFind(StratixURL,"http://127.0.0.1:")!=0 || AccountID=="" || ConnectionKey=="" || !Identity()) {
      Print("Stratix: configura URL local, cuenta, clave, login y servidor DEMO HEDGING exactos."); return INIT_PARAMETERS_INCORRECT;
   }
   EventSetMillisecondTimer(100); Print("Stratix EA v1.02 iniciado. Esperando instrucciones locales."); return INIT_SUCCEEDED;
}
void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result) {
   if(trans.type!=TRADE_TRANSACTION_DEAL_ADD || trans.deal==0 || !HistoryDealSelect(trans.deal)) return;
   if(HistoryDealGetInteger(trans.deal,DEAL_MAGIC)<100000000) return;
   string comment=HistoryDealGetString(trans.deal,DEAL_COMMENT);
   long entry=HistoryDealGetInteger(trans.deal,DEAL_ENTRY);
   long reason=HistoryDealGetInteger(trans.deal,DEAL_REASON);
   Print("Stratix | DEAL confirmado | ticket=",trans.deal," simbolo=",trans.symbol,
         " entrada/salida=",entry," motivo=",reason," volumen=",HistoryDealGetDouble(trans.deal,DEAL_VOLUME),
         " precio=",HistoryDealGetDouble(trans.deal,DEAL_PRICE)," comentario=",comment);
}
void OnDeinit(const int reason) { EventKillTimer(); Print("Stratix | EA detenido. Motivo=",reason,". SL/TP del broker permanecen; gestion dinamica requiere conexion."); }
void OnTimer() {
   if(!Identity()) {
      if(!identityWarning) Print("Stratix | BLOQUEADO: login/servidor o tipo DEMO HEDGING no coincide. No se ejecutan instrucciones.");
      identityWarning=true; Comment("Stratix: identidad de cuenta incorrecta"); return;
   }
   if(identityWarning) Print("Stratix | Identidad de cuenta recuperada.");
   identityWarning=false;
   bool brokerConnected=(bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   if(!brokerConnected && !brokerWarning) Print("Stratix | MT5 DESCONECTADO del broker; servidor local puede seguir conectado.");
   if(brokerConnected && brokerWarning) Print("Stratix | Conexion al broker recuperada.");
   brokerWarning=!brokerConnected;
   string response;
   int status=Http("GET","/poll?log_events=true&after_event_seq="+Int(lastEventSeq),"",response);
   if(status!=200) {
      if(status!=previousHttpStatus || TimeLocal()-lastConnectionWarning>=60) {
         Print("Stratix | DESCONECTADO | HTTP=",status," error=",GetLastError(),". Revisar servidor local, clave y WebRequest.");
         lastConnectionWarning=TimeLocal();
      }
      previousHttpStatus=status;
      Comment("Stratix: sin conexion (HTTP ",status,"). Permite WebRequest para ",StratixURL); return;
   }
   if(previousHttpStatus!=200) Print("Stratix | CONECTADO al servidor local. Cuenta demo verificada: ",ExpectedLogin);
   previousHttpStatus=200;
   Comment("Stratix EA DEMO | ",ExpectedLogin," | conectado");
   if(response=="") return;
   if(StringSplit(response,'|',fields)<2) return;
   if(fields[1]=="log") {
      long seq=(long)Val("seq",-1);
      if(lastEventSeq<0 || seq>lastEventSeq) { Print("Stratix | ",Arg("message")); lastEventSeq=seq; }
      return;
   }
   string id=fields[0],payload=Execute(fields[1]),ignored;
   if(Http("POST","/result/"+id,payload,ignored)!=200) Print("Stratix: respuesta no confirmada, NO se repite la operacion ",id);
}

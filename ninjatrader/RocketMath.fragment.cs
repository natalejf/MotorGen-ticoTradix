        private static class RocketMath {
            public static int VoteSignal(System.Collections.Generic.IEnumerable<int> candles,string direction) {
                var votes=candles.ToArray();
                if(votes.Length==0)return 0;
                if(votes.Any(v=>v < -1 || v > 1))throw new ArgumentException("Vela inválida");
                int balance=votes.Count(v=>v>0)-votes.Count(v=>v<0);
                if(balance>0&&direction!="SHORT")return 1;
                if(balance<0&&direction!="LONG")return -1;
                return 0;
            }
            public static double[] Levels(double entry,double edge,double tick,int count) {
                if(count<0||count>10||tick<=0||double.IsNaN(entry)||double.IsNaN(edge))throw new ArgumentException("CuadrÃ­cula invÃ¡lida");
                if(count==0)return new double[0];
                if(Math.Abs(edge-entry)/tick<count+1)throw new ArgumentException("No caben niveles distintos entre entrada y salida con el tick del contrato");
                var levels=Enumerable.Range(1,count).Select(i=>Math.Round((entry+(edge-entry)*i/(count+1))/tick)*tick).ToArray();
                if(levels.Distinct().Count()!=count||levels.Any(x=>x<=Math.Min(entry,edge)||x>=Math.Max(entry,edge)))throw new ArgumentException("Niveles solapados con entrada/SL/TP");
                return levels;
            }
            public static double[] Protection(double average,int quantity,double point,double loss,double profit,int side,double tick) {
                if(quantity<=0||point<=0||tick<=0||loss<=0||profit<=0||Math.Abs(side)!=1)throw new ArgumentException("Riesgo de cesta invÃ¡lido");
                return new[]{Math.Round((average-side*loss/(quantity*point))/tick)*tick,Math.Round((average+side*profit/(quantity*point))/tick)*tick};
            }
        }

        private static class RocketMath {
            public static double NextEma(double previous,double close,int period) {
                if(period<1||double.IsNaN(close)||double.IsInfinity(close))throw new ArgumentException("EMA inválida");
                return previous+(2.0/(period+1))*(close-previous);
            }
            public static int EmaSignal(double close,double ema,string direction) {
                if(double.IsNaN(ema))return 0;
                if(close>ema&&direction!="SHORT")return 1;
                if(close<ema&&direction!="LONG")return -1;
                return 0;
            }
            public static double[] Levels(double entry,double edge,double tick,int count) {
                if(count<0||count>10||tick<=0||double.IsNaN(entry)||double.IsNaN(edge))throw new ArgumentException("Cuadrícula inválida");
                if(count==0)return new double[0];
                if(Math.Abs(edge-entry)/tick<count+1)throw new ArgumentException("No caben niveles distintos entre entrada y salida con el tick del contrato");
                var levels=Enumerable.Range(1,count).Select(i=>Math.Round((entry+(edge-entry)*i/(count+1))/tick)*tick).ToArray();
                if(levels.Distinct().Count()!=count||levels.Any(x=>x<=Math.Min(entry,edge)||x>=Math.Max(entry,edge)))throw new ArgumentException("Niveles solapados con entrada/SL/TP");
                return levels;
            }
            public static double[] Protection(double average,int quantity,double point,double loss,double profit,int side,double tick) {
                if(quantity<=0||point<=0||tick<=0||loss<=0||profit<=0||Math.Abs(side)!=1)throw new ArgumentException("Riesgo de cesta inválido");
                return new[]{Math.Round((average-side*loss/(quantity*point))/tick)*tick,Math.Round((average+side*profit/(quantity*point))/tick)*tick};
            }
        }

# RocketPass y cuentas de examen

## Qué hace

RocketPass tiene una pestaña propia con la interfaz, los grupos y la cola
secuencial de PropPass, y ejecuta una lógica de tendencia y cuadrícula basada en
`TrendLimitGridBot.cs`. El archivo original de la estrategia no fue modificado.

Una entrada inicial abre los contratos configurados. Para una compra:

- Los **Buy Limit** se distribuyen entre la entrada y el SL global.
- Los **Buy Stop Market** se distribuyen entre la entrada y el TP global.
- En una venta, se invierten los lados de la cuadrícula.
- Cada lado permite de 0 a 10 niveles, con contratos por nivel independientes.
- Los niveles pendientes se redistribuyen con el precio promedio y el volumen
  actuales. Los niveles ejecutados o cancelados no se vuelven a enviar.
- SL y TP protegen la cesta completa. Sus distancias cambian con el promedio y
  el número de contratos para conservar el importe global configurado en USD.
- Las protecciones respetan también el margen que queda hasta los límites de
  cuenta y del día. Si queda menos margen, pueden cerrarse antes del TP/SL de cesta.
- Primero cancela las entradas pendientes y verifica el cierre de la cesta;
  después puede pasar a otra cuenta. Nunca avanza con órdenes propias pendientes.

Ejemplo de cálculo: en MNQ, con valor por punto USD 2, una entrada de 2 contratos
y SL USD 2.000 tiene una distancia inicial de 500 puntos. Diez limits quedan
separados por aproximadamente 45,45 puntos (ajustados al tick). Con TP USD 1.500,
los stops a favor se distribuyen dentro de los 375 puntos superiores, no dentro
del tramo inferior del SL. El AddOn usa el valor por punto real del instrumento.

El máximo total incluye entrada inicial y todas las pendientes: 2 contratos
iniciales + 10 limits de 2 + 10 stops de 2 requiere un máximo de al menos 42.
La configuración se rechaza si excede ese máximo o si los niveles no caben como
precios distintos dentro del rango permitido por el tick.

## Señal y gestión de cuentas

La dirección automática compara el último cierre con el cierre de hace N velas,
como en la estrategia original. Puedes elegir solo compras o solo ventas.
El período predeterminado es 40 y necesita 41 velas cerradas desde que se carga
esa serie. Para una prueba breve en simulación se puede usar período 2.
Cambiar de instrumento o temporalidad reinicia el calentamiento.

Cada cuenta tiene objetivo y pérdida máxima; además puedes configurar límites
diarios. Al alcanzar un objetivo o pérdida límite, se cancelan las pendientes,
se cierra la cesta y se deshabilita esa cuenta. El servicio continúa con la
siguiente elegible. La cola pasa de grupo cuando todas sus cuentas terminaron
y están flat y sin pendientes. Estos son límites configurados por ti, no una
descarga automática de las reglas de cada empresa de fondeo.

Esta adaptación conserva la lógica principal de tendencia, cuadrícula y salidas
globales. No incorpora todavía las opciones originales de break-even automático
ni de TP fijado al precio inicial; el TP de RocketPass es global por importe.

## Instalación y separación respecto a PropPass

1. Actualiza el EA MT5 y el AddOn PropPass a la versión **1.7.0-pending**.
   El EX5 del repositorio también está recompilado.
2. Descarga `RocketPassService.cs` desde **RocketPass → Conexiones** y añádelo
   a AddOns en NinjaScript. Compila en NinjaTrader con F5.
3. RocketPass tiene un vínculo propio. Guarda sus dos líneas (ID y clave) en
   `%LOCALAPPDATA%/Stratix/RocketPass/RocketBridge.key`.
   PropPass conserva su vínculo en `Stratix/NinjaTrader/CandleBridge.key`.
4. Reinicia los servicios y abre el panel local con `INICIAR_TRADINGNOTE.bat`.
5. Crea el grupo RocketPass, selecciona las cuentas, el contrato exacto con
   vencimiento, el tamaño, la cuadrícula y los objetivos. Guardar no activa órdenes.
6. Activa el grupo desde la web cuando quieras comenzar la prueba. Debe estar
   flat, sin órdenes y con datos recientes. Desactiva la estrategia original y
   cualquier otro algoritmo que utilice esas mismas cuentas.

Los grupos, colas, claves y configuraciones de RocketPass están separados de
PropPass. Ambos servicios usan una reserva exclusiva por cuenta. Para cambiar
una cuenta de servicio, detén y cierra sus asignaciones, espera a estar flat y
usa **Conexiones → Liberar cuentas (flat)** en el servicio que la tiene reservada.
Una reserva no se libera con órdenes o posiciones activas.

Pausar entradas cancela las pendientes de la cuadrícula y mantiene la gestión
de la posición abierta. Las protecciones ya aceptadas siguen en el bróker.
Al reiniciar el AddOn, las entradas quedan pausadas y no se reenvían niveles
ejecutados. La recuperación con posiciones abiertas requiere revisión en terminal.

## Preparar las cuentas de examen en PropPass o RocketPass

1. Conecta tu proveedor en NinjaTrader para que aparezcan las cuentas.
2. En la pestaña correspondiente, entra en **Conexiones → Cuentas de examen**.
3. Selecciona exclusivamente tus cuentas de evaluación y guarda la autorización.
   El AddOn debe confirmar esa autorización y publicar la capacidad de ejecución.
4. Añádelas al grupo y configura los importes adecuados a cada examen.
5. Aplica y activa el grupo cuando vayas a operar.

La autorización es explícita por nombre de cuenta y por servicio. No se habilitan
todas las cuentas externas por detectar el proveedor. Autorizar una cuenta tampoco
activa el algoritmo. Todavía no se ha enviado ninguna operación a tus exámenes.

## Próxima prueba en terminales

Se preparó el siguiente recorrido, pendiente de que abras MT5 y NinjaTrader:

1. MT5 demo → NinjaTrader Simulator: mercado, Buy/Sell Limit, Buy/Sell Stop,
   cambios de precio, cambios de SL/TP, cancelación, activación y cierre.
2. NinjaTrader Simulator → MT5 demo: el mismo recorrido, comprobando también
   el comportamiento de las protecciones ATM y la equivalencia de tamaño.
3. Verificar que al activarse una pendiente no se abre una segunda entrada.
4. Probar RocketPass en simulación: cuadrícula, redistribución, salida global y
   cancelación de pendientes al detener. La rotación de cuenta/grupo real exige
   disponer de más de una cuenta; por ahora su validación es automatizada.

MT5 → MT5 y NinjaTrader → NinjaTrader quedan pendientes hasta que tengas una
segunda cuenta de cada plataforma. Compilación y pruebas simuladas no equivalen
a validación completa con los terminales conectados.

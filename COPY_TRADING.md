# Copy entre MT5 y NinjaTrader

## Estado de esta versión

Implementado para pruebas en MT5 demo hedging y NinjaTrader Simulator/Playback:
MT5 → MT5, MT5 → NT8, NT8 → MT5 y NT8 → NT8. Se pueden agrupar cuentas
de una misma empresa o de distintas empresas; el motor no impone una empresa.
Los grupos usan el diseño de PropPass y aplican tamaño y límites a sus copias.

**No está habilitada la ejecución en cuentas reales o de fondeo conectadas a un
proveedor externo.** El AddOn compila con las referencias locales de NinjaTrader,
pero todavía requiere validación de ejecución en ambos terminales conectados.
PropPass y RocketPass permiten autorizar explícitamente cuentas de examen; consulta ROCKETPASS.md. El copy continúa limitado a demo/simulación.
Las pruebas automatizadas usan brókers simulados; no se enviaron operaciones a
tus terminales. Esto no equivale aún a un copiador comercial validado en producción.

## Para ponerlo a funcionar

1. Ejecuta `INICIAR_TRADINGNOTE.bat` y abre `http://127.0.0.1:8000`.
   Mantén el servidor y los terminales abiertos durante toda la copia.
2. **MT5:** registra cada cuenta desde Cuentas, inicia sesión en el terminal y
   vincula el EA desde Configuración → Vincular EA, o conecta el puente Python.
   Cada cuenta simultánea necesita un terminal independiente. Autoriza WebRequest
   para `http://127.0.0.1:8000` y habilita el trading algorítmico si usas EA.
3. **NinjaTrader:** descarga el AddOn actualizado desde Futuros → Conexiones →
   Descargar AddOn. Actualiza `StratixCandleService.cs` en el editor NinjaScript
   (AddOns), compila con F5 y reinicia el AddOn/NinjaTrader según tu instalación.
   Debe informar versión **1.7.0-pending**. Conserva el vínculo existente o vincúlalo
   desde Conexiones si todavía no lo tienes. Usa cuentas Simulator/Playback.
4. En **Cuentas → Añadir NinjaTrader al copy**, selecciona cada cuenta que vayas
   a utilizar como master o seguidora. Este registro no envía órdenes.
5. En **Grupos**, crea los grupos de seguidoras y define tamaño y límites.
   Para combinar plataformas, empieza con **Riesgo porcentual**. Si los símbolos
   destino son distintos, configura las equivalencias en cada copia individual.
6. En **Copy Master**, registra la cuenta origen y añade una seguidora o grupo.
   Configura el símbolo exacto: por ejemplo `NAS100` → `MNQ DEC26`. Sustituye el
   vencimiento por el contrato que realmente tengas disponible. Para NT8 → NT8
   añade el mapeo explícito aunque los nombres sean iguales. Puedes usar los
   campos «Otro símbolo master» y «Su símbolo destino».
7. Configura el máximo de tamaño destino y el riesgo. Las copias se crean
   pausadas. Asegúrate de que las seguidoras NT8 estén flat y sin órdenes y de
   que no estén reservadas a PropPass u otro algoritmo. Activa las copias demo.
8. Espera a que las cuentas estén conectadas y abre una **nueva** operación en
   la master con SL y TP. Comprueba su apertura, modificación de SL/TP, parcial
   y cierre en la seguidora y en el registro antes de ampliar el grupo.

Las posiciones que existían al crear/iniciar el seguimiento no se importan.
Las señales observadas mientras la copia está pausada tampoco se importan al
reanudar. Pausar impide entradas; los cierres de posiciones ya copiadas siguen
gestionándose mientras los conectores estén funcionando.

## Conversión de tamaño y precio

- **Riesgo porcentual:** presupuesto = equity destino × porcentaje / 100.
  Tamaño = presupuesto / pérdida de una unidad destino entre entrada y SL.
  MT5 obtiene esa pérdida mediante `order_calc_profit`, en la moneda de la cuenta.
  NT8 usa distancia de precio × `MasterInstrument.PointValue`, en USD.
- **Lote/tamaño fijo:** el valor introducido ya está expresado en unidades
  destino: lotes en MT5, contratos enteros en NT8.
- **Espejo / multiplicador / proporcional:** puedes indicar cuántas unidades
  destino corresponden a una unidad origen. Esa relación es obligatoria entre
  plataformas; debes calcularla con las especificaciones reales de tu bróker.
  Proporcional aplica además equity destino / equity origen. Para equities de
  monedas distintas usa riesgo porcentual; no hay conversión FX de balances.
- No hay una tabla universal de lotes CFD a contratos. Un NQ tiene diez veces
  el valor por punto de un MNQ; las especificaciones de NAS100 CFD dependen del
  bróker. El máximo de tamaño y el riesgo por entrada también limitan el resultado.
- El volumen siempre se redondea hacia abajo al paso permitido. Si no alcanza
  el mínimo, se rechaza la entrada; no se fuerza un contrato aumentando el riesgo.
- Entre plataformas, SL/TP se trasladan como distancias desde la entrada master
  a la entrada destino. `Escala de distancias` adapta distintas unidades de precio.
  Ejemplo: master entrada 20.000 y SL 19.990; destino entrada 20.003 y escala 1
  da SL 19.993. NT8 normaliza las protecciones al tick del contrato.

## Tickets, cierres y recuperación

La relación persistente guarda ticket origen, orden destino, ticket de posición
destino, símbolos, tamaños iniciales y una etiqueta de propiedad. El ticket de
posición se confirma con la posición del bróker; no se asume que sea la orden.
Cada envío tiene una clave única persistida. Un resultado incierto pausa la
asignación y no se reenvía automáticamente.

Los cierres y parciales se aplican a posiciones identificadas por magic y etiqueta
de esa copia. Un parcial mantiene la fracción del tamaño inicial, ajustada al paso
destino; un contrato indivisible puede permanecer hasta el cierre completo.
Una posición cerrada manualmente en la seguidora no se reabre.

Una master con datos obsoletos no provoca cierres inferidos. Si se reinicia la
master NT8, los identificadores observados cambian de generación: reconcilia
las posiciones, detén la copia y crea una nueva. El registro explica el bloqueo.

## Límites actuales que debes conocer

- Se copian Buy/Sell Limit y Buy/Sell Stop Market, sus cambios de precio,
  protecciones y cancelaciones. El cambio de ticket al ejecutarse se reconcilia
  con la posición resultante. Stop Limit (doble precio stop/limit) aún no se admite.
- Si una pendiente NT8 no publica las protecciones ATM antes de ejecutarse,
  configura SL/TP propios en la seguidora MT5. Sin SL/TP ni protecciones propias
  no se envía la entrada pendiente. Los pips propios se expresan en el símbolo
  destino. La prueba con tus ATM concretos sigue pendiente.
- NT8 usa posiciones netas. Cada copia tiene su relación de órdenes y una
  cantidad virtual propia dentro de la posición neta. No se permiten señales
  opuestas simultáneas sobre un mismo contrato, ni operaciones manuales mezcladas
  con el motor en esa cuenta. El límite de entradas incluye pendientes.
- Las ampliaciones sobre una posición neta NT8 ya abierta no se agregan a la
  seguidora; para esta versión, abre una entrada y luego reduce o cierra.
- La observación nativa es periódica. Un cierre y reapertura completos entre dos
  lecturas pueden no distinguirse. No usar esta versión para scalping de alta
  frecuencia ni como sustituto de un flujo de ejecuciones por evento.
- La master necesita SL y TP identificables. Si NT8 tiene varias protecciones
  ambiguas del mismo tipo para un instrumento, la entrada se rechaza.
- Las equivalencias son explícitas; no se adivinan sufijos ni vencimientos.
- Si falta conexión, el servidor local no puede gestionar salidas dinámicas.
  Las protecciones ya aceptadas permanecen en el bróker.

Para RocketPass, cuentas de examen y el plan de prueba cruzada, consulta
[ROCKETPASS.md](ROCKETPASS.md).

## GitHub y vista online

Interfaz: https://natalejf.github.io/MotorGen-ticoTradix/

GitHub Pages publica archivos estáticos y muestra datos ficticios para revisar
el diseño. Las acciones de conexión y escritura están deshabilitadas en esa vista.
El backend Python y los terminales se ejecutan desde el panel local. No se
publica la base de cuentas, claves del puente ni tickets de tu instalación.

## Referencias de diseño funcional

- https://tradingnote.co/es/docs/copy-master
- https://tradingnote.co/es/docs/grupos

Se siguió el comportamiento documentado de masters/seguidoras, equivalencias,
tamaño por riesgo y reglas de grupo. La documentación pública no expone el
algoritmo interno de reconciliación de tickets; esta implementación es propia.

# NinjaTrader 8 · Candle Controller gestionado desde la web

La interfaz del gráfico fue retirada por pedido del usuario. El componente actual
es **StratixCandleService**, un AddOn sin ventanas ni dependencia de un gráfico.
NinjaTrader ejecuta; la web gestiona cuentas, grupos, instrumento, temporalidad,
contratos, TP/SL, límites, horario y activación/pausa.

## Uso

- **PropPass → Conexiones / Registro**: conexión del servicio, datos recibidos, cuentas y
  registro nativo. NinjaTrader debe estar abierto y conectado a datos.
- **PropPass → Panel**: crear, editar, eliminar y aplicar
  grupos. «Activar en cola» agrega el grupo al final de la cola de activación.
  El grupo actual no se interrumpe. Solo al terminar todas sus cuentas por
  target o stop y estar flat/sin órdenes pendientes, se configura el siguiente.
- Un grupo ejecutándose por servicio y otros en espera. La secuencia tiene
  dos niveles: cuentas dentro del grupo y después grupos en orden de activación.
- Detección dinámica mediante Account.All; hasta 200 cuentas por grupo. La ejecución de esta fase se limita a los proveedores nativos Simulator/Playback. No se habilitaron
  cuentas de fondeo ni copy entre plataformas.
- «Pausar entradas» conserva la gestión nativa y los TP/SL. Ante desconexión web
  se pausan nuevas entradas; no se reactiva automáticamente al reconectar.

## Algoritmo

Se extrajeron del archivo original la configuración, señales, creación de órdenes,
brackets OCO, comisiones y supervisión de límites. El original permanece intacto;
su hash está en `ninjatrader/service_manifest.json`. El AddOn construye velas con
ticks Last en intervalos UTC completos de 1–60 minutos; necesita **dos velas
cerradas** de calentamiento, sin inventar histórico. Una vela verde compra; roja
vende; doji no genera entrada.

La agregación de ticks reemplaza las series del gráfico. Por ello, la validación
del primer adaptador no se presenta como certificación automática del AddOn.
Los registros de pruebas nativas distinguen ambas versiones.

No se añadió una salida de una vela: `LastEntryBar` no se utilizaba para ella en
el original. `ExitOnlyInProfit` tampoco tenía lógica de salida y la API rechaza
activarlo. No se garantiza aprobar reglas de una empresa de fondeo por este test.

## Instalación local

Fuente: `ninjatrader/StratixCandleService.cs`. Copia únicamente ese archivo a
`NinjaTrader 8/bin/Custom/AddOns`, compila con NinjaScript Editor y autoriza la
extensión manualmente cuando la plataforma lo solicite. Según la carga de la
plataforma, puede ser necesario reiniciar NT8. No se requiere asignar una
estrategia a un gráfico ni usar el antiguo panel Candle Controller.

La vinculación local está en `%LOCALAPPDATA%/Stratix/NinjaTrader/CandleBridge.key`:
ID en la primera línea, clave en la segunda. El servidor conserva su hash, no
la clave. No se incluye en reportes ni URLs. El servicio usa exclusivamente
`http://127.0.0.1:8000`. Su configuración se guarda en `CandleServiceConfig.txt`
del mismo directorio, separada del original.

Los comandos tienen vencimiento, instancia de destino y ACK aplicado/rechazado.
Una entrega HTTP no equivale a una orden ejecutada. Los comandos entregados no
se reenvían automáticamente.

## Evidencia y alcance

- Primer adaptador de estrategia: entrada LONG de 1 GC DEC26 a 3861,2,
  TP a 3862,2, SL a 3860,2 cancelado por OCO; +100 USD simulados antes de la
  contabilización de comisiones del controlador. Sim101 terminó flat y pausado.
  Evidencia: `reports/ninja_native_test.json`, `reports/ninja_orders_verification.txt`.
- AddOn sin interfaz: compilación aislada con las bibliotecas instaladas de NT8
  sin errores; su prueba de grupos se registra separadamente.
- Siete pruebas aisladas de API/contrato: grupos, edición, confirmación, expiración,
  autenticación y exclusión de cuentas no autorizadas.
- Dos grupos de demostración guardados desde la API web: individual (Sim101)
  y dos cuentas (SimAccount2/SimAccount3). Guardarlos no activa operaciones.

El AddOn general de copy MT5↔NT8 sigue sin ejecución habilitada. Requiere mapeo
de contratos/vencimientos, tick value, contratos enteros, reconciliación netting
frente a hedging y atribución fiable de órdenes/fills. Los viejos scripts nativos
StratixMaster/StratixSlave usan otra API y no fueron activados ni modificados.

Referencias oficiales:
https://tradingnote.co/es/docs/instalacion
https://tradingnote.co/es/docs/copy-master
https://static.ninjatrader.com/support/helpGuides/nt8/getinstrument.htm
https://static.ninjatrader.com/support/helpGuides/nt8/state.htm


## PropPass: dos grupos de cinco demos (17/11/2026)

- Grupo A: Sim101 y SimAccount2–5; NQ DEC26, M5, 4 contratos;
  objetivo acumulado por cuenta +1.500 USD, pérdida máxima −2.000 USD.
- Grupo B: SimAccount6–10; NQ DEC26, M5, 1 contrato;
  objetivo acumulado por cuenta +150 USD, pérdida máxima −2.000 USD.
- Los brackets TP/SL y los límites diarios se guardaron con los mismos importes
  para que no aparezca un límite previo más pequeño. El balance de referencia
  de estas demos es 50.000 USD. No equivale a modificar su balance nativo.
- Alcanzar un límite deshabilita la cuenta y solicita el cierre; la próxima
  cuenta elegible recibe la siguiente señal de vela. No abre inmediatamente
  al marcar PASS/SL. No hay diez posiciones simultáneas.
- Hay **un grupo ejecutándose por servicio** y una cola de grupos activados.
  No se alternan por trade: primero terminan todas las cuentas del actual.
- La prueba conectada utiliza la conexión **Simulación** de NinjaTrader:
  ejecuciones en las cuentas locales de simulación sobre las cotizaciones que
  recibe NT8. Sus resultados comprueban la integración, no la rentabilidad.
- Evidencia conectada: `reports/proppass_requested_groups.json`.
- Prueba determinista: `reports/PropPassLimitsHarness.cs` extrae literalmente los
  métodos de monitoreo y selección del servicio. Sus 26 escenarios utilizan
  dobles de cuentas y NO representan ejecuciones en NinjaTrader.

## Usarlo en otra PC o VPS Windows

El navegador es el control; **NinjaTrader y el AddOn son el ejecutor**. Una cuenta
no se conecta desde la web ingresando las credenciales de NinjaTrader. Esas
credenciales se introducen en la propia plataforma por su titular.

La opción compatible hoy es ejecutar **Stratix y NinjaTrader juntos en la otra
PC/VPS**. El AddOn se conecta al servidor de esa máquina por 127.0.0.1:8000;
127.0.0.1 siempre significa la máquina donde se ejecuta el programa.

1. Preparar el proyecto Stratix y su entorno Python en esa PC Windows; iniciar
   `INICIAR_TRADINGNOTE.bat` desde la carpeta del proyecto. Los scripts locales
   de arranque están disponibles, pero no se ha probado aquí una instalación
   limpia de Windows/VPS ni se entrega un instalador de dependencias.
2. Abrir NinjaTrader 8, iniciar sesión personalmente y conectar un proveedor
   de datos. Para comprobar el flujo, usar primero cuentas simuladas.
3. En la web de ESA instalación abrir PropPass → Conexiones → Vincular servicio.
   Guardar ID (primera línea) y clave (segunda línea) en el archivo
   `%LOCALAPPDATA%\Stratix\NinjaTrader\CandleBridge.key` de esa PC.
   Crear la carpeta si falta. Mantener privada la clave; no enviarla por chat.
4. Descargar `StratixCandleService.cs` desde esa web; copiarlo a la carpeta real
   de documentos de NT8: `NinjaTrader 8\bin\Custom\AddOns`. Puede estar en
   OneDrive si Windows redirige Documentos. Abrir NinjaScript Editor y compilar
   con F5. Aceptar personalmente la autorización del AddOn si NT8 la solicita;
   reiniciar NT8 si la vinculación no se carga. El `.cs` es fuente, no un ZIP
   importable desde Tools → Import → NinjaScript Add-On.
5. Esperar en PropPass «NT8 conectado», las cuentas y ticks recientes.
   El conector descubre las cuentas disponibles por nombre y proveedor, sin una
   lista fija de SimAccount. Cuentas conectadas de otros proveedores aparecen
   como solo lectura en esta fase; ejecutar se limita a simuladores locales.
6. Crear el grupo: instrumento exacto y vencimiento admitido por el proveedor,
   M5, contratos y objetivos por cuenta. Revisar el balance de referencia.
   «Guardar» no activa operaciones. «Reiniciar seguimiento» requiere flat y
   pausa; borra los contadores del controlador, no el historial de NT8.
7. Pulsar «Activar en cola». Los grupos siguientes quedan en espera. Esperar ACK nativo del grupo actual. Desde una suscripción nueva
   hacen falta dos cierres M5, entre cinco y diez minutos aproximadamente.
   Después opera la primera cuenta elegible si la vela tiene dirección.
8. Ver «Actual», «Siguiente elegible» y Registro. Pausar entradas conserva la
   gestión de salidas; «Cerrar y detener» solicita liquidar las posiciones del
   instrumento/grupo aplicado. Confirmar posiciones flat, además del ACK.

Para gestionar esa PC desde un navegador en otra máquina hace falta acceso
privado al servidor de Stratix. Una alternativa es un túnel SSH con un servidor
SSH ya configurado: `ssh -N -L 8000:127.0.0.1:8000 usuario@equipo-remoto`;
luego abrir `http://127.0.0.1:8000` en el navegador local. El puerto local 8000
debe estar libre. El túnel y la instalación remota **no se probaron en esta
sesión**. La API actual no tiene autenticación de usuarios para publicarla en
Internet: no exponer el puerto 8000 directamente ni usar un túnel público.
No se implementó todavía un servicio central cloud al que conectarse desde
cualquier PC descargando solo el AddOn.

El PC/VPS debe permanecer encendido, con NT8, servidor, datos y conectividad.
Cerrar el navegador no equivale a parar el algoritmo. Una pérdida de conexión
con el servidor pausa nuevas entradas en unos diez segundos; nunca vuelve a
activar entradas automáticamente tras reconectar.


## Detección y compilación corregidas (actualización)

Se instala **una sola vez como AddOn en AddOns**, no como estrategia en cada
cuenta ni en cada gráfico. Al cargar NT8, el servicio consulta `Account.All`,
publica las cuentas conectadas y vuelve a descubrir nuevas cuentas en sus
pulsos. Con veinte cuentas disponibles se pueden seleccionar esas veinte en un
grupo (máximo técnico actual: 200). Crear un grupo no activa entradas.

No guardar otra copia de la clase `StratixCandleService` en `Strategies`: genera
una definición duplicada al compilar toda la biblioteca NinjaScript. Se encontró
una copia idéntica y se respaldó fuera de Custom en
`reports/native_backup/StratixCandleService.duplicate.cs.bak`.

La fuente nueva se compiló de forma aislada y dentro de NinjaTrader; el DLL
contiene `1.2-discovery`. Después de actualizar hay que verificar en PropPass
que el servicio está conectado y publica esa versión; compilar no demuestra
que la instancia anterior ya haya sido reemplazada. Si no aparece, reiniciar
NT8 y comprobar la vinculación local. No duplicar la instalación para resolverlo.

La interfaz Cuentas muestra las asignaciones MT5 y las cuentas publicadas por
NinjaTrader; para gestionar Candle y sus grupos se abre PropPass.


## Cola de grupos: regla obligatoria

Los grupos activados se ejecutan en su orden de activación. Un grupo se completa
solo si **cada cuenta** tiene PASS/BURNED o TARGET_REACHED/LOSS_LIMIT_REACHED,
ninguna posición y ninguna orden pendiente. Una cuenta simplemente deshabilitada,
pausada o ausente no cuenta como finalizada. Al completar el grupo se espera el
ACK de configuración del siguiente antes de activarlo. No se reinician los PASS
anteriores al cambiar de grupo ni al reanudar la cola.

«Pausar entradas» pausa la cola completa. Activar otro grupo mientras hay uno en
curso lo agrega en espera; no reemplaza al actual. La API bloquea configure,
reset y start manuales durante la cola activa. Cambiar de instancia de NT8 pausa
la cola y requiere reanudación explícita.

La configuración del grupo actual se conserva durante su ejecución: editar su
plantilla no modifica órdenes en curso. Editar un grupo pendiente actualiza solo
su configuración en la cola; no cambia el grupo actual ni otros grupos. Dos
grupos de la misma cola no pueden compartir cuentas.

Prueba conectada del 17/11: Sim101 abrió 4 NQ por vela M5 verde, ejecutó su TP,
SL cancelado por OCO y PASS; SimAccount6 abrió 1 NQ por otra vela M5 verde,
ejecutó TP y quedó PASS. Ese ensayo probaba una cuenta por grupo; no era el flujo
final de cola. Tras la corrección solicitada, el grupo 1 reanudó desde SimAccount2,
con Sim101 PASS conservado y el grupo 2 en espera. Las pruebas aisladas de cola
verifican que completar una sola cuenta no permite avanzar al otro grupo.


## Toggles y decisiones independientes por grupo

Al alcanzar target o stop, el toggle de la cuenta se muestra apagado y bloqueado
hasta reiniciar explícitamente el seguimiento. Esto se conserva al cambiar al
siguiente grupo. El grupo se marca completado cuando todas sus cuentas han
terminado y no quedan posiciones ni órdenes pendientes.

Editar contratos, límites o el toggle de un grupo pendiente solo actualiza ese
grupo en la cola. El toggle nativo de una cuenta del grupo actual se conserva al
reanudar ese grupo y no se propaga a otros. Intentar reiniciar un grupo distinto
al actual se rechaza antes de pausar o modificar el servicio en ejecución.
Activar un grupo pendiente tampoco reanuda por sí solo un grupo actual pausado;
para ello se utiliza «Reanudar este grupo» en el grupo actual. «Pausar entradas»
de la cabecera sigue siendo un control global explícito de toda la cola.


## Watchdog 1.3: errores transitorios y pausas visibles

Un timeout aislado o un HTTP 408/429/5xx no apaga las entradas de inmediato.
El servicio conserva su estado mientras no pasen 10 segundos desde la última
respuesta confirmada. Al cumplir ese plazo pausa las entradas, mantiene la gestión
nativa de salidas y registra COMMUNICATION_TIMEOUT con el último error.
Los rechazos HTTP 4xx de autenticación/protocolo (excepto 408/429) pausan de
inmediato con COMMUNICATION_REJECTED. No se reenvían comandos entregados.

Al recuperar comunicación se registra la recuperación. Una pausa de seguridad,
manual o por error NO se reactiva sola: se reanuda explícitamente desde PropPass.
La telemetría publica pause_code, pause_reason, pause_at, bridge_failures y
bridge_last_error. La cola conserva la causa y las últimas 20 pausas; PropPass
muestra la causa en el estado del motor y en la cola. Los fallos se registran con
código HTTP o estado WebException, sin imprimir claves del conector.

La lógica temporal se comprobó compilando BridgeHealthHarness.cs contra el mismo
fragmento C# que incorpora el AddOn. Las pruebas son deterministas, sin cortar
la conexión de una cuenta que tenga posiciones abiertas.

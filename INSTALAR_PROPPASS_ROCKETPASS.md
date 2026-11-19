# Usar PropPass y RocketPass sin la IA

La IA no es parte del motor de ejecución. Necesitas NinjaTrader, su conexión de
datos y el servidor local de TradingNote abiertos. GitHub Pages es una vista de
demostración; desde allí no se vinculan cuentas ni se activan operaciones.

## Primera instalación

1. Abre `INICIAR_TRADINGNOTE.bat` en esta carpeta. Conserva abierta la ventana
   del servidor y entra a **http://127.0.0.1:8000** en tu navegador.
2. En **PropPass → Conexiones → Descargar AddOn** descarga
   `StratixCandleService.cs`. En **RocketPass → Conexiones → Descargar AddOn**
   descarga `RocketPassService.cs`.
3. Copia ambos `.cs` en la carpeta de datos de NinjaTrader:
   `Documentos\NinjaTrader 8\bin\Custom\AddOns`. Si Documentos está en OneDrive,
   utiliza esa carpeta redirigida. En este equipo es
   `C:\Users\yo\OneDrive\Documentos\NinjaTrader 8\bin\Custom\AddOns`.
   Estos archivos fuente se copian; no se importan como un paquete ZIP.
4. En NinjaTrader abre **Nueva → Editor de NinjaScript**. Los dos servicios
   deben aparecer en **AddOns**. Pulsa **F5** y espera que finalice sin errores.
   Los AddOns se ejecutan en segundo plano: no los agregues como estrategias
   al gráfico ni ejecutes simultáneamente el antiguo controlador de gráfico.
5. En cada pestaña pulsa **Vincular NinjaTrader**. Si ya hay un vínculo correcto,
   se reutiliza; **Vincular otro equipo** crea uno nuevo y no es un botón de
   reconexión diaria.
6. Descarga el **archivo de vínculo** y colócalo según el servicio:

   | Servicio | Archivo completo |
   |---|---|
   | PropPass | `%LOCALAPPDATA%\Stratix\NinjaTrader\CandleBridge.key` |
   | RocketPass | `%LOCALAPPDATA%\Stratix\RocketPass\RocketBridge.key` |

   Puedes pegar la carpeta en la barra de direcciones del Explorador y crear
   las carpetas faltantes. Activa la visualización de extensiones: el archivo
   debe terminar en `.key`, sin `.txt` agregado. Contiene ID y clave en dos
   líneas y es privado. Cada servicio utiliza su propio archivo.
7. Si es un vínculo nuevo y el archivo aún no existía, el conector actualizado
   lo detecta. Si reemplazaste un vínculo anterior, reinicia NinjaTrader o
   recompila con F5 para que vuelva a leerlo. Conecta el proveedor de datos.
8. Verifica **Conectado** en la pestaña correspondiente y las cuentas recibidas.
   Crea el grupo, elige sus cuentas y el instrumento con vencimiento exacto.
   **Guardar** guarda la plantilla; **Activar en cola** aplica y activa el grupo
   después de la confirmación de NinjaTrader.

Una cuenta no puede pertenecer a dos servicios activos. Para moverla, pausa y
cierra sus operaciones, espera a estar flat y sin órdenes y usa **Conexiones →
Liberar cuentas (flat)** en el servicio anterior.

## Cada día

Abre NinjaTrader y su conexión de datos, ejecuta `INICIAR_TRADINGNOTE.bat`, entra
al panel local y verifica ambos estados. Las claves y grupos se conservan;
no vuelvas a crear vínculos. Después de reiniciar el AddOn las entradas quedan
pausadas; reaplica/reanuda el grupo explícitamente. Cerrar el chat de la IA no
detiene el algoritmo; cerrar el servidor local provoca una pausa de entradas.

## RocketPass actual

Versión **1.9.0-vote40**: consulta el historial de NinjaTrader y cuenta hacia
atrás las últimas **40 velas M5 cerradas**, excluyendo la vela en formación.
Más alcistas que bajistas: compra; más bajistas: venta; empate: sin entrada.
Los doji no suman y el tamaño de cada vela no pondera el voto. No hay espera
de 40 velas nuevas. Si el proveedor no entrega suficiente historial, se indica
que falta historial y no se inventan datos. La carga histórica prepara la
tendencia y se evalúa al activar; luego se actualiza en cada cierre M5.

Los contratos aceptan enteros. Hay **tres limits y tres stops** por defecto.
Con **Mismos contratos que la entrada inicial** marcado, los niveles usan los
contratos iniciales de su cuenta; desmárcalo para introducir otro tamaño entero.
El máximo global suma posición y entradas pendientes, no las órdenes de salida.

Configuración solicitada para las pruebas:

| Servicio | Cuentas simuladas | Instrumento | Entrada | TP / objetivo | SL / pérdida máxima |
|---|---|---|---:|---:|---:|
| RocketPass | Sim101, SimAccount2–5 | MNQ DEC26 | 4 | USD 1.500 | USD 2.000 |
| PropPass | SimAccount6–10 | NQ DEC26 | 4 | USD 1.500 | USD 2.000 |

RocketPass: 3 limits × 4 y 3 stops × 4; máximo global 40. Total potencial
inicial: 28 contratos. Los grupos son secuenciales: opera una cuenta elegible
y pasa a otra al llegar a sus límites. No abre cinco cestas a la vez.

## Si aparece Offline

- Confirma que el panel sea local y el servidor siga abierto.
- Comprueba que compilaste el servicio correcto y guardaste su `.key` en la
  carpeta de `%LOCALAPPDATA%`, no en AddOns ni en Descargas.
- Un archivo correcto tiene dos líneas. No mezcles las claves de ambos servicios.
- Si sustituyes una clave, recarga el servicio. No crees más vínculos por cada
  intento de conexión.
- Si aparece **Sin datos**, comprueba el contrato y la conexión de mercado.
  Estar vinculado y recibir datos son comprobaciones distintas.

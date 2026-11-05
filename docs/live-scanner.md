# Escáner en directo

El escáner se abre desde **Hoard Hub → Kinect Hoard → Escáner 3D**, con One fija y Persona
seleccionados. La web usa el tema común de HoardLink y su lanzador oficial de
Faustus. `setup-mcp.ps1` instala la biblioteca común sin enlaces al repo de origen.
La interfaz escucha en `127.0.0.1:64321`; **Conectar cámara** abre el motor en un puerto libre (64320 o 64322–64325),
publicado en `data/scanner-endpoint.json`. Abrir el Hub, el catálogo o MCP no inicia cámaras.

La web permite conectar, ver la máscara, iniciar, pausar, finalizar, girar la
superficie y descargar OBJ/MTL/PNG/PLY. Desconecta antes de cambiar los ajustes.
Las herramientas de stdio MCP se publican también con sus argumentos tipados
en `/api/agent/tools` y `/api/agent/call` mediante el contrato común de HoardLink.
El acceso de Faustus usa el relé común; no hay un modelo de texto propio.

En **Geometría** hay dos entradas que abren el mismo espacio de escaneo:

- **Cámara móvil:** selección inicial Kinect 360; recorre una persona o un objeto
  con la cámara en la mano.
- **Cámara fija:** selección inicial Kinect One; deja la cámara en el trípode y
  gira la persona o el objeto delante de ella.

La cámara se puede cambiar. Ambas opciones admiten Persona y Objeto. En cámara
fija, se estima movimiento relativo del sujeto; no se impone una pose identidad
ni un ángulo conocido de un turntable.

La imagen izquierda permite colocarse. En Objeto, pulsa sobre el sujeto antes de
iniciar. **Iniciar**, **Pausar** y **Finalizar** controlan la toma. La vista derecha
se genera desde el volumen con color; arrastra para observarlo desde otro ángulo
y usa **Vista de cámara** para volver al punto de vista seguido.

Finalizar conserva `scan.ply`, `session.khr`, su calibración y `live.scan.json`.
La sesión conserva la profundidad original; el JSON conserva la selección de
primer plano como pares inicio/longitud para poder repetir el texturizado.
Después genera `scan.obj`, `scan.mtl`, `scan-albedo.png` y `scan.scan.json` desde
las poses aceptadas y el RGB original. **Abrir OBJ** abre ese resultado. Cerrar una
toma antes de finalizar conserva sesión, poses y PLY; no afirma haber producido
el atlas. Cada toma usa una carpeta nueva bajo `captures/`.

## Motor y límites

Microsoft.Kinect.Fusion.x64 2.0.1410.19000 proporciona la integración de
profundidad/color, el raycasting de la vista y la malla. La pose la calcula el seguimiento de ICP con color descrito abajo; las
correspondencias SIFT con RANSAC 3D quedan como propuesta de recolocación (y como
seguimiento anterior completo, `tracker: sift`, para comparar). Los fotogramas
rechazados no se integran. El archivo de RGB usa otra cola con capacidad limitada
para desacoplar compresión y reconstrucción, y las vistas PNG se codifican fuera
del hilo de captura.

Persona con One emplea índices y TrackingId del SDK. En 360 y Objeto, el
seguimiento de ICP con color separa el sujeto en toda la imagen de profundidad
(la componente que pulses o la mayor cerca del centro, como el refinado); con
`tracker: sift` se usa la componente continua de profundidad que sigue su centro
proyectado. Puede incluir una mesa o silla en contacto: todavía no equivale a
segmentación semántica de objetos. El volumen inicial mide 1,5 m de lado y usa vóxeles de 3,90625 mm.
Necesita runtime Kinect v2 y GPU compatible con Fusion AMP.

El seguimiento en directo es rígido. La compensación de postura, cuello, ropa y
objetos deformables con un campo de deformación **no está implementada**; el
seguimiento y el refinado descartan por vista el movimiento de brazos y manos. El giro natural completo de una persona sigue pendiente de la prueba
física de `PENDIENTES.md`. Vistas RGB y casos sintéticos no
acreditan por sí solos calidad de busto u objeto físico. Las superficies con
pocas referencias de forma/color necesitan validación adicional.

La [investigación de motores](scanner-research.md) recoge alternativas y sus
límites, incluidas reconstrucción no rígida y segmentación aprendida.

## Seguimiento en directo (ICP con color)

Desde el 05-11-2026 el escáner sigue al sujeto con el método del refinado, hecho
incremental y dentro del presupuesto de cada fotograma (`ColorIcpTracker.cs`,
`LiveIcpTracker.cs`, `SubjectGate.cs`):

1. **Sujeto:** la misma máscara que el refinado, fotograma a fotograma: banda de
   profundidad, plano del suelo (buscado una vez), componentes separadas en los
   saltos de profundidad, cilindro de 0,5 m alrededor del eje del sujeto y prueba
   de continuidad. Una vista sin sujeto (fuera de imagen, máscara en la pared) no
   se sigue ni se integra. Con One y Persona parte de la máscara corporal del SDK;
   en Objeto, de toda la imagen y del punto que pulses.
2. **ICP con color contra vistas clave:** punto-a-plano más un término de
   intensidad (gradiente de la vista clave) con núcleo de Tukey, de grueso a fino
   (5 cm, 2,5 cm, 1,25 cm), asociación proyectiva a media resolución contra las 4
   últimas vistas clave (una cada 6° de giro), predicción de velocidad constante
   por unidad de tiempo y una prioridad suave sobre el ritmo de giro cuando el
   intervalo es corto (sensor en directo).
3. **Brazos y manos:** un punto que las vistas clave recientes no ven igual (más de
   1 cm de diferencia, o delante de una superficie que otra vista vio detrás) no
   tira de la pose ni se integra.
4. **Recolocación:** si falla, giros de ±10–40° del sujeto alrededor de su eje
   vertical (también recentrado), después una propuesta SIFT y un barrido sobre
   las vistas clave ordenado por solape × coincidencia de cromaticidad. Tras una
   vista seguida no admite más de 30–45° respecto a la predicción (sin vuelta de
   180° de un torso simétrico).
5. **Cierre de la vuelta en directo:** al volver a ver un lado tras más de 150° de
   giro se registra la vista clave contra la antigua; un grafo de poses (Gauss-Newton,
   poda de aristas incoherentes) se resuelve en segundo plano y, si mueve las
   poses, el volumen se rehace con las vistas clave corregidas: la superficie en
   pantalla no se duplica al volver al frente.

Se probó además descartar al integrar los píxeles a más de 1,5 cm del volumen
(la segunda pasada del refinado): con la persona sintética abría huecos (malla en
1562 piezas frente a 675, completitud a 1 cm del 77 % frente al 82 %) y costaba
4–9 ms por fotograma, así que no se usa en directo.

`live.scan.json` guarda además `trajectory` (todas las vistas seguidas, con poses
corregidas por el grafo), `tracking` (seguidas, recolocadas, perdidas, cierres,
reconstrucciones del volumen…) y `latency` (milisegundos por fotograma frente a los
33 ms de 30 fps). El seguimiento anterior por rasgos SIFT sigue disponible como
`tracker: sift` para comparar.

## Reproducir como en directo

Sin sensor, **Reproducir como en directo** (debajo de *Refinar una toma*) lleva
una toma guardada (`captures/live-*` o la persona sintética `synthetic-*`) por el
mismo `FusionScanner.Process` que la cámara, al ritmo de sus marcas de tiempo:
si el proceso se retrasa, se descartan los fotogramas que el sensor habría
sustituido. Se ve igual que una toma real (cámara con máscara y superficie que
crece, que puedes girar) y al terminar mide la reproducción y exporta malla y
atlas en `captures/replay-*`. Elige seguimiento (ICP con color o rasgos SIFT) y
ritmo (tiempo de la toma, mitad, doble o sin pausa).

`replay_score.py` escribe `replay-score.json`: con la persona sintética, error de
rotación frente a la verdad y precisión/completitud de la superficie; con una
toma refinada, error de pose y solape en sus 35 pares de control para la
reproducción, lo grabado en directo y el refinado; siempre, residuo
malla–profundidad con las máscaras del refinado y latencia por fotograma. La
interfaz lo muestra como tabla (reproducción, grabado en directo, refinado).

### Resultados (05-11-2026, al ritmo de la toma, AMP, sin atlas)

| Medida | Rasgos SIFT (antes) | ICP con color (ahora) | Refinado sin cámara |
| --- | --- | --- | --- |
| Persona sintética: rotación RMS / máx. / final | 35,5° / 67,7° / 8,5° | 0,56° / 2,19° / 0,55° | 2,0° / 7,7° / 1,6° |
| Persona sintética: superficie mediana / completitud a 1 cm | 21,0 mm / 39 % | 1,65 mm / 82 % | 0,84 mm / 82 % |
| Persona sintética: residuo malla–profundidad | 8,5 mm | 2,1 mm | — |
| Toma real 19-10: vistas del sujeto seguidas | 8 de 109 (y 24 sin sujeto) | 108 de 109 (0 sin sujeto) | 102 de 109 |
| Toma real: error de pose en 35 pares (mediana / p90) | 32 pares sin pose | 3,1° / 15,9° | 1,1° / 11,0° |
| Toma real: solape a 1 cm (mediana) | — | 77 % | 87 % |
| Toma real: residuo malla–profundidad | 3,2 mm (8 vistas) | 4,4 mm | 3,3 mm |
| Silla 360: residuo malla–profundidad | 1,2 mm | 0,97 mm | 0,87 mm |
| Seguimiento por fotograma (mediana / p95) | 40 / 56 ms | 11 / 16 ms | — |
| Proceso completo por fotograma, persona sintética (mediana / p95) | 55 / 96 ms | 20 / 55 ms | — |

En la toma real lo grabado en directo con el seguidor anterior daba 11,3° / 23,1°
de error en los pares de control, 36 % de solape y una malla a 820 mm de su
profundidad (integraba las 187 vistas sin sujeto). La persona sintética se
reprodujo a 10 fps reales; en este equipo, compartido con otras cargas, el 64 %
de los fotogramas entró en 33 ms y el p95 los supera (picos al rehacer el volumen
tras un cierre). La toma real del 19-10 se grabó a 2,5 Hz y la silla, a 640×480,
gasta 18 ms en el raycast de la vista. Prueba automática: `tests/live-replay.py`
(persona sintética: RMS < 5°, final < 4°, al menos un cierre, residuo < 6 mm).

## Refinado sin cámara

**Refinar una toma**, debajo del estado, vuelve a procesar una toma guardada
(`captures/live-*`) sin abrir el sensor y conserva el resultado nativo. Escribe
`refined/refined.obj`, `.mtl`, `refined-albedo.png`, `refined.ply` y
`refine.json` (`turn_refine.py`, también `fusion.py --refine-live CARPETA`):

1. **Sujeto:** banda de profundidad, plano del suelo, componentes separadas por
   saltos de profundidad, cilindro vertical alrededor del eje del sujeto y una
   prueba de continuidad que descarta vistas en las que el sujeto salió del
   encuadre o la máscara saltó a otra superficie.
2. **Seguimiento:** ICP con color de grueso a fino (2 cm, 1 cm, 5 mm) con núcleo
   robusto de Tukey contra las últimas vistas clave y predicción de velocidad
   constante. Si falla, se reintenta con escala gruesa de 4 cm y después con
   FPFH + RANSAC contra todas las vistas clave. Una recolocación justo después de
   una vista seguida no puede alejarse más de 30° de la predicción, y las
   propuestas se ordenan por solape × coincidencia de cromaticidad: un torso casi
   simétrico ya no se da la vuelta 180°.
3. **Cierre de la vuelta:** pares que vuelven a ver el mismo lado tras más de
   150° de giro se registran por separado; un grafo de poses (Levenberg-Marquardt
   con poda de aristas inciertas) reparte la deriva.
4. **Movimiento no rígido pequeño:** el núcleo robusto ignora brazos y manos
   durante el seguimiento; antes de la fusión final, en cada vista se eliminan los
   píxeles a más de 1,5 cm de una primera superficie de consenso. No hay campo de
   deformación: cambios de postura mayores se descartan, no se modelan.
5. **Fusión y atlas:** TSDF de 4 mm, eliminación de fragmentos sueltos y atlas
   desde el RGB original de una vista por sector alrededor del sujeto.

`refine.json` mide con las mismas máscaras la trayectoria y la malla nativas y
las refinadas: solape a 1 cm y error de pose en pares de control (15–45° de
separación, registrados de forma independiente y fuera del grafo), error de
cierre de la vuelta, residuo malla–profundidad, profundidad explicada a 1 cm,
piezas de la malla y giro cubierto. La interfaz lo muestra como tabla.

Resultados medidos el 05-11-2026:

| Toma | Medida | Nativo | Refinado |
| --- | --- | --- | --- |
| Persona sintética girando 1,12 vueltas, brazos ±12°, 132 vistas (verdad conocida) | Error de rotación RMS / máx. / final | 32,4° / 56,5° / 6,0° | 2,0° / 7,7° / 1,6° |
| | Superficie: mediana a la verdad / completitud a 1 cm | 33,4 mm / 44 % | 0,8 mm / 82 % |
| Toma real One, Luis girando (296 vistas, 187 sin sujeto) | Error de pose en pares de control (mediana / p90) | 11,3° / 23,1° | 1,1° / 11,0° |
| | Solape a 1 cm en pares de control | 36 % | 87 % |
| | Error al cerrar la vuelta (mediana, antes → después del grafo) | — | 1,5° → 0,3° |
| | Residuo malla–profundidad (mediana) / piezas | 820 mm (pared integrada) / 7831 | 3,3 mm / 1 |
| | Vistas integradas sin sujeto | 187 | 0 |
| Silla 360 estática (78 vistas) | Residuo malla–profundidad (mediana) | 7,1 mm (1,7 mm con X corregida) | 0,9 mm |

La toma real de persona no contiene una vuelta completa: Luis estaba a
0,6–0,75 m, fuera del encuadre en gran parte de la toma y la máscara antigua
saltó a la pared. Sirve para medir el seguimiento, no para acreditar un busto
de 360°. La prueba física pendiente está en `PENDIENTES.md`.

`tests/turn_synthetic.py` genera la persona sintética con ruido de Kinect, suelo,
pared y una caja junto al sujeto; `tests/turn_benchmark.py` puntúa una
reproducción nativa (`--scanner-replay`) y su refinado contra la verdad, y
`tests/turn-refine-smoke.py` es la prueba automática. `tests/fusion-convention.py`
reproduce una persona estática con el motor Fusion en CPU y comprueba que la
malla nativa queda en el marco de sus poses (0,76 mm de mediana a la verdad).

## Convención de coordenadas

Kinect Fusion espera la imagen espejada del SDK. Hasta el 05-11-2026 recibía el
fotograma canónico, de modo que su mundo, sus poses ICP y `scan.ply` quedaban con
X negada, mientras el seguimiento RGBD, el archivo y la textura usaban la cámara
sin espejar. En la silla 360 la malla nativa solo explicaba el 44 % de la
profundidad observada; espejada, el 99,9 %. Ahora Fusion recibe la profundidad y
el color espejados con el punto principal canónico (Fusion lo lee en la imagen
espejada; espejarlo también desplaza la malla (W − 1 − 2·cx)/fx·z, 3,5 cm con la
One a 1,2 m), la vista de superficie se devuelve a la orientación de cámara y
`live.scan.json` declara `mesh_coordinate_space: camera`. Las tomas antiguas se
corrigen con x' = −x + (W − 1 − 2·cx)/fx·z.
`quality_scan.py --texture-live` y el refinado detectan las tomas antiguas sin
esa marca y corrigen su malla antes de texturizar o medir.

## API y MCP

La API existe en `127.0.0.1:64320` mientras el escáner está abierto:

- `GET /api/scan/status`: modo, cámara, seguimiento, salida y limitaciones.
- `GET /api/scan/preview.png`, `/api/scan/surface.png`: vistas actuales.
- `POST /api/scan/start`, `/pause`, `/finish`, `/close`.
- `POST /api/scan/select?x=0.5&y=0.5`: punto inicial normalizado.
- `POST /api/scan/orbit?x=0.1&y=0`: giro de la vista, radianes; `/follow` la restaura.

MCP: `start_live_scan(mode, generation, subject)`, `live_scan_status()` y
`control_live_scan(action, x, y)`. La apertura queda en vista previa, sin capturar.
`exporting` debe alcanzar `finished` antes de considerar terminado el OBJ.

La utilidad nativa `--scanner-replay SESION MODELO MODO DIRECTORIO cpu|amp [icp|sift] [ritmo]`
prueba la misma reconstrucción con capturas existentes, sin accionar el sensor
(ritmo 1 = marcas de tiempo de la toma, 0 = sin pausa; mide al terminar).
`--scanner-replay-server SESION icp|sift RITMO PUERTO [DIRECTORIO]` abre el mismo
motor con su API HTTP: es lo que usan el botón y la herramienta MCP.

Reproducción: `replay_live_capture(capture, tracker, speed)`, `list_live_replays()`
y `replay_score(replay)` en MCP y en `/api/agent/*`; la página usa
`POST /api/scanner/replay`, `GET /api/scanner/replays` y
`GET /api/scanner/replay-score?replay=replay-...`. Durante la reproducción,
`live_scan_status()` añade `replay` (fotogramas entregados, descartados por
retraso), `tracking` y `latency`. Una reproducción terminada cede el motor a
**Conectar cámara**; una en curso no se interrumpe sin **Desconectar**.
`quality_scan.py --texture-live DIRECTORIO` reintenta solo el atlas de una toma
que ya conserva malla y poses.

Refinado: `list_live_captures()`, `refine_live_scan(capture, texture, radius_metres)`
y `refine_status(capture)` en MCP y en `/api/agent/*`; la página usa
`GET /api/scanner/captures`, `POST /api/scanner/refine` y
`GET /api/scanner/refine?capture=live-...`. `capture` vacío elige la toma más
reciente. El trabajo corre en segundo plano (`refined/progress.json`,
`refined/refine.log`); los archivos se descargan desde
`/api/workspace/file/<toma>/refined/<archivo>`.

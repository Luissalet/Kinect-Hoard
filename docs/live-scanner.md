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

Microsoft.Kinect.Fusion.x64 2.0.1410.19000 proporciona el seguimiento contra el
volumen, integración de profundidad/color, raycasting y CameraPoseFinder.
Correspondencias SIFT, RANSAC 3D y ajuste rígido SVD proponen poses verificadas
con profundidad de ambos fotogramas y vistas anteriores. Los fotogramas rechazados no se integran;
una recuperación requiere confirmación. El archivo de RGB usa otra cola con
capacidad limitada para desacoplar compresión y reconstrucción.

Persona con One emplea índices y TrackingId del SDK. En 360 y Objeto se usa una
componente continua de profundidad que sigue su centro proyectado. Puede incluir
una mesa o silla en contacto: todavía no equivale a segmentación semántica de
objetos. El volumen inicial mide 1,5 m de lado y usa vóxeles de 3,90625 mm.
Necesita runtime Kinect v2 y GPU compatible con Fusion AMP.

El seguimiento en directo es rígido. La compensación de postura, cuello, ropa y
objetos deformables con un campo de deformación **no está implementada**; el
refinado sin cámara (abajo) descarta por vista el movimiento pequeño de brazos y
manos. El giro natural completo de una persona sigue pendiente de la prueba
física de `PENDIENTES.md`. Vistas RGB y casos sintéticos no
acreditan por sí solos calidad de busto u objeto físico. Las superficies con
pocas referencias de forma/color necesitan validación adicional.

La [investigación de motores](scanner-research.md) recoge alternativas y sus
límites, incluidas reconstrucción no rígida y segmentación aprendida.

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
profundidad observada; espejada, el 99,9 %. Ahora Fusion recibe la profundidad,
el color y el punto principal espejados, la vista de superficie se devuelve a la
orientación de cámara y `live.scan.json` declara `mesh_coordinate_space: camera`.
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

La utilidad nativa `--scanner-replay SESION MODELO MODO DIRECTORIO cpu|amp` prueba
la misma reconstrucción con capturas existentes, sin accionar el sensor.
`quality_scan.py --texture-live DIRECTORIO` reintenta solo el atlas de una toma
que ya conserva malla y poses.

Refinado: `list_live_captures()`, `refine_live_scan(capture, texture, radius_metres)`
y `refine_status(capture)` en MCP y en `/api/agent/*`; la página usa
`GET /api/scanner/captures`, `POST /api/scanner/refine` y
`GET /api/scanner/refine?capture=live-...`. `capture` vacío elige la toma más
reciente. El trabajo corre en segundo plano (`refined/progress.json`,
`refined/refine.log`); los archivos se descargan desde
`/api/workspace/file/<toma>/refined/<archivo>`.

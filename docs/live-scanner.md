# Escáner en directo

La entrada principal está en **Hoard Hub → Kinect Hoard**, con One fija y Persona
seleccionados. La web usa el tema común de HoardLink y su lanzador oficial de
Faustus. `setup-mcp.ps1` instala la biblioteca común sin enlaces al repo de origen.
La interfaz escucha en `127.0.0.1:64321`; **Conectar cámara** abre el motor en
`127.0.0.1:64320`. Abrir el Hub, el catálogo o MCP no inicia cámaras.

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

El seguimiento actual es rígido. La compensación de postura, cuello, ropa y
objetos deformables **no está implementada**. Tampoco se da por resuelto el giro
natural de personas al añadir estos controles. Vistas RGB y casos sintéticos no
acreditan por sí solos calidad de busto u objeto físico. Las superficies con
pocas referencias de forma/color necesitan validación adicional.

La [investigación de motores](scanner-research.md) recoge alternativas y sus
límites, incluidas reconstrucción no rígida y segmentación aprendida.

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

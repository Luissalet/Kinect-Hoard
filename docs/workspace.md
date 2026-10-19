# Modos de Kinect Hoard

La entrada del Hub abre el menú completo, sin arrancar sensores. Cámara; cuerpo,
esqueleto y avatar; escáner; rostro; audio y voz; gestos e interacción; geometría;
grabación y reproducción; integraciones; sensores y diagnóstico. Las diez áreas
agrupan las 26 capacidades de `docs/capabilities.json`. «Todas las referencias»
permite buscar las muestras originales y abrir contratos y código propio.

Cada modo tiene acciones ejecutables, ajustes, guía y referencias. La web y MCP
llaman a las mismas funciones. Las operaciones largas aparecen en Actividad y
devuelven enlaces a archivos locales. Archivos y sesiones muestra capturas,
WAV, PLY/OBJ/texturas y KHR; los KHR se pueden inspeccionar o reproducir en el
estudio con pausa, avance, avatar y análisis de gestos sin volver a abrir el sensor.

## Cámara e integraciones

Conectar abre un lector compartido para el flujo elegido. One: RGB, profundidad,
IR, IR largo, índice corporal, esqueleto, persona sin fondo y RGB registrado.
La ruta libfreenect de 360 ofrece RGB, profundidad, IR y RGB registrado; no
proporciona esqueleto ni audio. La selección de una función One no cambia drivers.
Las capturas y grabaciones liberan temporalmente la vista previa y la restauran.
Un escaneo activo se conserva y requiere finalizar/desconectar antes de otra toma.

«Conectar esqueleto a Blender» abre ColorDepth One (o conserva Skeleton activo) y Blender instalado con
`integrations/blender_kinect.py`. El panel Kinect muestra conexión y cuerpos; crea
un armature por TrackingId. «Grabar movimiento» inserta keyframes de posición,
rotación y escala. Coordenadas Kinect X/Y/Z en metros pasan a Blender X/Z/Y.
El script se puede ejecutar desde el editor de texto o registrar como complemento.
El panel usa la [API oficial de regiones de Blender 5.2](https://docs.blender.org/api/5.2/bpy.types.Region.html).
La prueba con Blender 5.2 verificó creación de huesos, movimiento y animación;
una escena sin persona produce cero cuerpos, no un esqueleto inventado.

La salida limpia `/camera-output` se usa como fuente Navegador de OBS. Para que
otra aplicación la reciba como webcam se inicia la cámara virtual de OBS. Hoard
no instala un driver DirectShow propio. Los ejemplos OpenCV y MATLAB reciben
RGB o matrices uint16 desde los endpoints de este mismo lector.

## Puertos y errores

La UI usa 64321. Los motores comprueban disponibilidad real de los puertos
64320/64322–64325 y publican el elegido en `data/*-endpoint.json`; MCP y web leen
ese mismo estado. Un socket saliente Bound/CloseWait también puede ocupar un
puerto. No se mata el proceso ajeno ni se confunde ese fallo con un problema USB.
El log conservado en `data/scanner-worker.log` o `camera-worker.log` explica los
fallos del proceso en lugar de mostrar únicamente «código 1».

Las consultas de estado usan el último diagnóstico del lector y no ejecutan WMI
por cada petición HTTP. Audio drena el flujo de muestras sin consultar PnP en cada
bloque. WAV parciales conservan duración medida y `complete=false`.

## MCP

Además de las herramientas anteriores: `list_modes`, `start_camera`,
`camera_status`, `get_live_frame`, `close_camera`, `list_artifacts`, `open_demo`,
`replay_session` y `connect_blender`. El catálogo y transporte stdio no abren
sensores. Las herramientas de familia usan `/api/agent/tools` y `/api/agent/call`.

El escaneo mantiene sus límites reales en [live-scanner.md](live-scanner.md).
La cobertura de menús no acredita haber resuelto deformaciones o deriva al
escanear una persona girando; esas pruebas y mejoras siguen en 937/939.

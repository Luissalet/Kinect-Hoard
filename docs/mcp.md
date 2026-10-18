# MCP y Faustus

`mcp_server.py` usa el SDK oficial de MCP 2.3.0 y transporte `stdio`. No abre un puerto ni envía datos a una nube. Las capturas de imagen y audio devuelven rutas locales sin adjuntar los medios. Las herramientas de análisis sí devuelven metadatos de voz, rostro o gestos; el cliente decide si abre los archivos completos.

## Instalar y probar

Con Python 3.11 o superior y la aplicación compilada o extraída del ZIP:

```powershell
.\setup-mcp.ps1
& '.\.venv\Scripts\python.exe' '.\tests\smoke_mcp.py'  # solo en el repositorio fuente
```

Faustus admite un manifiesto `faustus-plugin.json` junto a la aplicación. Este repositorio lo incluye con `id` `kinect-hoard`, un comando para la UI y el servidor MCP. En la carpeta instalada, ejecuta `setup-mcp.ps1` antes de conectar el plugin y configura `KINECT_HOARD_DIR` como esa carpeta. Como Hoard es una aplicación WinForms y no ofrece `/api/health`, Faustus necesita que el usuario configure el perfil de lanzamiento; no debe adivinar un proceso o puerto.

## Herramientas disponibles

| Herramienta | Resultado |
| --- | --- |
| `list_capabilities(generation)` | Catálogo con estado real de One o 360 |
| `get_capability(capability_id)` | Datos, muestras del Toolkit, rutas de código y documentación |
| `read_hoard_source(relative_path)` | Código del catálogo y todos los Markdown de `docs/`; rechaza rutas ajenas al proyecto |
| `sensor_status()` | Detección USB y backend sin iniciar un flujo |
| `capture_artifact(kind, generation)` | Crea PNG, PGM, JSON o PLY bajo `captures/` y devuelve la ruta; `generation` puede ser `one` o `360` |
| `record_session(stream, seconds, generation)` | Graba una sesión `.khr` local; el backend nativo 360 admite Color, Depth, Infrared y ColorDepth |
| `record_audio(seconds)` | Intenta grabar WAV de One; devuelve error si el runtime no produce muestras |
| `recognize_speech(seconds)` | Graba WAV local y devuelve eventos de comandos reconocidos, sin adjuntar el audio |
| `analyze_face(generation)` | Captura RGB de One o 360 y devuelve rectángulos faciales y rutas locales |
| `capture_face3d(seconds)` | Captura malla facial HD de One y devuelve rutas, calidad y recuentos, sin adjuntar geometría |
| `scan_head(seconds)` | Intenta construir un modelo facial personalizado desde varias vistas; informa el estado de captura sin adjuntar geometría |
| `capture_gestures(seconds)` | Captura esqueleto de One y devuelve eventos y ruta del informe |
| `analyze_gesture_session(filename)` | Calcula eventos de una sesión de esqueleto en `captures/` |
| `scan_3d(seconds, tracking, generation, foreground_max_depth?, roi?)` | Graba ColorDepth de One o 360 y exporta malla TSDF color e informe local; los parámetros opcionales aíslan primer plano |
| `fuse_session(filename, tracking, foreground_max_depth?, roi?)` | Reconstruye una sesión ColorDepth existente en `captures/`, con el mismo recorte opcional |
| `scan_textured(seconds, generation, tracking, texture_size, max_triangles)` | Graba One o 360 y exporta OBJ, MTL, atlas PNG, PLY e informe de calidad |
| `scan_dual_textured(extrinsics_filename, seconds, texture_size, max_triangles)` | Graba ambas en paralelo y fusiona con un JSON de calibración medido en `captures/`; prueba física pendiente |
| `calibrate_dual_landmarks(first_points_metres, second_points_metres, threshold_metres)` | Calcula extrínsecos rígidos de One←360 desde puntos XYZ correspondientes, con RANSAC y error RMS |
| `fuse_textured_sessions(first_filename, second_filename?, extrinsics_filename?, tracking, texture_size, max_triangles)` | Reconstruye una o dos sesiones existentes; dos requieren extrínsecos medidos |
| `session_info(filename)` | Resume una sesión de `captures/` sin leer sus píxeles al modelo |

El recurso `kinect-hoard://capabilities` ofrece el JSON completo y `kinect-hoard://toolkit-map` el mapa de adaptación. Los tipos de captura aceptados son `color`, `depth`, `infrared`, `long_infrared`, `body_index`, `skeleton_image`, `background_removed`, `registered_color`, `bodies`, `point_cloud`, `mesh`, `color_cloud` y `color_mesh`.

`generation` vale `one` de forma predeterminada para mantener compatibles los clientes actuales. La ruta nativa 360 admite `color`, `depth`, `infrared`, `registered_color`, `point_cloud`, `mesh`, `color_cloud` y `color_mesh`. Estas capturas y el registro RGBD se probaron físicamente con la cámara `045E:02AE` y `libusbK`. Las capacidades de cuerpo y audio 360 siguen dependiendo de trabajo posterior.

## Contrato para un agente de implementación

1. Consulta `list_capabilities`; trata `planned` como tarea pendiente, `implemented_unverified` como código sin validación física, `stream_only` como flujo sin interpretación completa validada y `partial` como salida real con pasos esenciales pendientes.
2. Lee `get_capability` y el código señalado por `read_hoard_source` antes de adaptar una función. Respeta unidades, espacio de coordenadas y formato de exportación.
3. Captura datos de prueba solo cuando el usuario o el flujo de trabajo lo requiera. La Kinect puede estar ocupada por la UI; si una captura falla, cierra el flujo de la UI o reintenta después de un corte USB.
4. No presentes la vista previa de profundidad o IR como medida científica: consulta `Values`, PGM o PLY.

La integración con Faustus está preparada como manifiesto y MCP independiente; todavía no se ha probado dentro de una instalación de Faustus del usuario. Hoard también tiene una [API HTTP local](webserver.md) que se inicia por separado para consumidores de fotogramas. Su [formato de plugins](https://github.com/Luissalet/Faustus/blob/master/docs/api/plugins.md) fue la referencia de esta integración.

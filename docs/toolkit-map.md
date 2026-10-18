# Mapa de adaptación del Developer Toolkit 1.8

El catálogo estructurado `docs/capabilities.json` relaciona capacidades con muestras del Toolkit instalado en `C:\Program Files\Microsoft SDKs\Kinect\Developer Toolkit v1.8.0\Samples`. Es un inventario de **capacidades**, no una copia del código de Microsoft. Cada estado distingue lo verificado con hardware de lo que solo compila o sigue pendiente.

| Familia de muestras | Equivalente de Hoard hoy | Trabajo pendiente |
| --- | --- | --- |
| ColorBasics, DepthBasics, InfraredBasics, KinectExplorer | Vista previa, datos crudos, diagnóstico, reconexión | Validar 360 física |
| SkeletonBasics, CoordinateMappingBasics, Avateering | Esqueleto One con persona real seguida, vista de avatar 2D, coordenadas cámara/profundidad, RGB registrado y PLY color | Validar avatar con cuerpo real, precisión y 360 |
| BackgroundRemoval, InteractionGallery, AdaptiveUI, ControlsBasics, ShapeGame, TicTacToe | Índice corporal y composición RGB sincronizada One; motor de gestos y eventos; ShapeGame y TicTacToe manejados con mano real; AdaptiveUI escala controles según distancia | Validar recorte y AdaptiveUI con persona; calibrar barridos laterales |
| AudioBasics, AudioCaptureRaw, SpeechBasics | WAV y ángulo de One; comandos locales con gramática editable y motor de voz de Windows | Validar voces humanas y ruido; 360 |
| FaceTrackingBasics/3D | Detector Haar 2D; Face v2 con puntos, propiedades, orientación y malla HD PLY probada con persona | Validar Haar con persona; giros, oclusión y seguimiento de varias personas |
| KinectFusionBasics, ColorBasics, Explorer, MultiStaticCameras, HeadScanning | Nube/malla PLY, Fusion TSDF y escáner OBJ con UV y atlas PNG; 360 física estática y cierre de bucle sintético probados | Barrido real de varias vistas, calibración y prueba física de dos cámaras, escaneo de cabeza |
| Kinect Studio, WebserverBasics | Sesiones `.khr`, reproducción de UI, diagnóstico, MCP y API HTTP local de fotogramas | Sincronización multifujo y pruebas largas con varios clientes |

La UI del Toolkit 1.8 muestra muchas entradas de C#, C++ y VB que repiten una capacidad. Hoard registra esa capacidad una vez con código propio y ejemplos específicos por generación. No se marca como «funciona» una muestra solo porque un ensamblado cargue o una imagen esté vacía.

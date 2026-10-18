# Grabación y reproducción para depuración

El menú **Sesión → Grabar 10 segundos** guarda el flujo abierto a un máximo de 5 fotogramas por segundo. **Sesión → Reproducir archivo** abre esa sesión sin necesidad de Kinect; **Abrir archivo en pausa** muestra el primer fotograma y deja avanzar con **Fotograma siguiente** (`Ctrl+→`). **Pausar/Reanudar reproducción** usa `Ctrl+Espacio`. `Guardar PNG` y `Guardar datos` sirven también sobre el fotograma reproducido. El avatar, los eventos de gestos y la galería pueden consumir una sesión Skeleton mientras se avanza paso a paso. Los cortes USB pueden dejar huecos de tiempo, pero la sesión conserva los fotogramas que llegaron.

Desde CLI:

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --record '.\prueba.khr' 10 Depth
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --session-info '.\prueba.khr' '.\prueba-info.json'
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --replay-last '.\prueba.khr' '.\ultimo-fotograma.png'
```

El formato `.khr` usa GZip y una cabecera `KINECT_HOARD_SESSION_1` o `KINECT_HOARD_SESSION_2`. La implementación precisa está en `KinectHoard.Core/SessionArchive.cs`. Cada registro conserva hora UTC, dimensiones, imagen BGRA, muestras originales `ushort` cuando existen y articulaciones de cuerpos cuando existen. Un lector valida tamaños y recuentos antes de reservar memoria. Cada sesión registra un `StreamKind`; `ColorDepth` combina color registrado y profundidad en el mismo fotograma y guarda un archivo `*.intrinsics.json` con calibración para [Fusion](fusion.md). Las demás combinaciones de varios flujos siguen pendientes.

La versión 2 añade opcionalmente RGB original, sus dimensiones y dos coordenadas `float32` por píxel de profundidad para mapearlo. La captura de calidad One lo usa para conservar los 1920×1080 de color antes de crear la vista registrada de 512×424. La ruta 360 escribe versión 2 sin imagen extra porque su RGB ya es de 640×480. Los lectores de Hoard y `fusion.py` aceptan ambas versiones; las sesiones antiguas no se convierten automáticamente. El [escáner con textura](quality-scanner.md) utiliza esos datos adicionales al crear el atlas.

La prueba local grabó seis segundos de Depth en un archivo de 3,9 MB y reconstruyó un PNG sin volver a abrir el sensor. Otra sesión Skeleton tuvo **23 fotogramas con cuerpo de 28**, detectó un gesto de mano levantada y permitió inspeccionar el avatar y AdaptiveUI paso a paso sin sensor. La reproducción automática de UI usa 5 fps fijos; las marcas de tiempo UTC quedan en el archivo para un reproductor con ritmo exacto posterior.

En MCP, `record_session` devuelve la ruta del archivo y `session_info` devuelve metadatos sin incluir píxeles. Los archivos de sesión pueden contener imágenes del entorno o personas: `captures/` y `captura-*.khr` están excluidos de Git y no se adjuntan por defecto a un modelo.

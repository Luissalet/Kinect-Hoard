# Rostro 2D y malla facial HD de Kinect One

## Seguimiento facial 3D

**Rostro > Capturar rostro HD (hasta 20 s)...** usa el lector corporal y las fuentes Face y High Definition Face del SDK 2.0. Elige el cuerpo seguido más cercano, asigna su `TrackingId` a ambos lectores, y guarda un informe JSON y una malla PLY triangular en cuanto llega un fotograma HD. El visor 3D abre automáticamente la malla y permite girarla y acercarla. La cámara de la UI se cierra durante la captura y se recupera al terminar.

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --face3d '.\rostro-hd.json' '.\rostro-hd.ply' 20
```

MCP ofrece `capture_face3d(seconds)` y devuelve **solo rutas y recuentos**; un agente puede consultar el contrato sin recibir la geometría facial. El JSON completo contiene `ColorBoundingBox` y cinco puntos faciales en píxeles RGB 1920×1080, propiedades del rostro, cuaternión de orientación, punto pivote de la cabeza, calidad de alineación, vértices y triángulos. `VerticesMetres` está en el espacio de cámara de Kinect: X a la derecha, Y hacia arriba, Z alejándose del sensor, todo en metros. El PLY conserva esas coordenadas. El `TrackingId` identifica una trayectoria en esa sesión; no es una identidad biométrica persistente.

Prueba física del 18 de octubre de 2026: una persona delante de la One produjo seguimiento facial básico y HD de calidad `High`, cinco puntos 2D, orientación y una malla de **1.347 vértices y 2.630 triángulos**. La captura desde el menú guardó seis fotogramas faciales y abrió una malla cuyo relieve se inspeccionó en el visor. Falta validar continuidad ante giros, oclusiones, varias personas y pérdidas USB. La malla es el modelo paramétrico alineado del SDK, no un escaneo fotogramétrico texturizado ni una prueba de identidad.

**Rostro > Escanear modelo facial personalizado (hasta 90 s)...** inicia `FaceModelBuilder` y espera sus vistas frontal, izquierda, derecha y hacia arriba. También se puede usar `--headscan informe.json malla.ply 90` o `scan_head(seconds)` por MCP. El informe registra `ModelCollectionStatus` y `ModelCaptureStatus`; durante la captura se actualiza `informe.progress.json` aproximadamente cada segundo y la interfaz muestra la vista que falta. Solo exporta PLY cuando el modelo personalizado se completa. En dos pruebas con una persona real se recogieron 158 y 321 fotogramas faciales; al final el SDK seguía pidiendo `LeftViewsNeeded` y `TiltedUpViewsNeeded`, respectivamente. **Todavía no se ha validado una colección completa ni una malla personalizada.** El tiempo indicado es un máximo de espera, no una duración fija.

## Detector frontal 2D

**Rostro > Analizar imagen RGB actual...** toma RGB, ejecuta un detector frontal Haar de OpenCV y guarda PNG con rectángulos y JSON. El flujo de cámara se detiene después; **Abrir cámara** vuelve al directo. MCP ofrece `analyze_face()` y devuelve rectángulos y rutas locales, sin adjuntar la fotografía.

El análisis de la **imagen RGB actual** acepta One o 360 porque opera sobre píxeles ya capturados. La One se probó físicamente; la ruta 360 compila, pero aún no se pudo verificar por el bloqueo de su controlador. El comando `--face-capture` y la herramienta MCP siguen usando One.

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --face-capture '.\rostro.json' '.\rostro.png'
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --face-image '.\foto.png' '.\resultado.json' '.\anotada.png'
```

`faces` contiene `{x,y,width,height}` en píxeles RGB. Una lista vacía puede deberse a giro, iluminación u oclusión; también puede haber falsos positivos. El 18 de octubre de 2026, la ruta RGB física entregó 1920×1080 y el detector Haar encontró un rostro real; guardó el rectángulo y PNG anotado. No se han medido falsos positivos ni robustez ante giro, iluminación u oclusión. Este detector no usa la fuente Face del SDK ni entrega puntos 3D.

Los informes y mallas faciales se guardan **localmente** en la ruta elegida. Son datos personales sensibles: pide permiso a la persona capturada antes de guardarlos o compartirlos y elimínalos cuando ya no se necesiten. Hoard no los envía a ningún servicio por sí mismo.

El modelo `models/haarcascade_frontalface_default.xml` procede del [repositorio oficial de OpenCV](https://github.com/opencv/opencv/blob/4.x/data/haarcascades/haarcascade_frontalface_default.xml) y contiene su aviso original. La aplicación usa OpenCvSharp4.Windows.Slim bajo Apache 2.0 y, para HD, Microsoft.Kinect.Face 2.0 con su base de datos de modelos.

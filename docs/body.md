# Cuerpo, articulaciones e índice corporal

`Skeleton` abre `BodyFrameReader` de Kinect One. Cada `TrackedBody` incluye `TrackingId` y articulaciones. Las posiciones `X`, `Y`, `Z` están en **metros en espacio de cámara**. `DepthX` y `DepthY` están en **píxeles de la imagen de profundidad**, calculados con `CoordinateMapper.MapCameraPointToDepthSpace`. `TrackingState` corresponde al estado del SDK: 0 sin seguimiento, 1 inferido, 2 seguido.

La vista de esqueleto une las articulaciones principales cuando ambos extremos tienen seguimiento y caen dentro de 512×424. Exporta el fotograma a JSON desde «Guardar datos» o con:

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --bodies '.\captura-bodies.json'
```

Una respuesta `[]` significa que **llegó un fotograma** pero no había un cuerpo completo seguido. No se debe interpretar `[]` como fallo del lector. Con una persona de pie delante de la One, el esqueleto apareció en la UI a unos 21 fps y se siguió un cuerpo en 117 de 134 fotogramas de una prueba de diez segundos. La mano derecha sirvió de puntero para ShapeGame y TicTacToe. Faltan medidas de precisión a varias distancias.

**Gestos > Mostrar avatar 2D** cambia la vista de huesos por un personaje plano: torso, extremidades, cabeza y manos siguen las articulaciones confirmadas. Los datos JSON y la sesión grabada siguen siendo el esqueleto original; el avatar es una visualización. El avatar se inspeccionó con una sesión de 28 fotogramas capturada de una persona real, con torso, cabeza, brazos y piernas movidos por sus articulaciones.

`BodyIndex` asigna cada píxel a uno de hasta seis cuerpos, o 255 al fondo. Sirve para preparar máscaras de recorte. La composición sincronizada de Color, Depth y BodyIndex está implementada en `BackgroundRemoved`; se inspeccionó con una persona real y reveló huecos en la máscara que todavía necesitan corrección. No uses la paleta de la vista previa como identificador estable de persona: el índice puede cambiar entre fotogramas; para identidad temporal usa `TrackingId`.

La Kinect 360 usa otro conjunto de articulaciones y formato de seguimiento. La normalización de su esqueleto está pendiente y se documentará con un sensor 360 físico.

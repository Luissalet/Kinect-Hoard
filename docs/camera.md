# Flujos de cámara

La API propia está en `KinectHoard.Core/Camera.cs`. `StreamKind` selecciona el flujo y `CameraFrame` cruza el límite entre controladores. `Bgra` contiene cuatro bytes por píxel en orden B, G, R y alfa; el origen está arriba a la izquierda. `Values` conserva datos de 16 bits cuando los hay. No uses la imagen de vista previa para mediciones: sus tonos son solo una representación.

| Flujo One | Resolución observada | Datos | Muestra de Toolkit relacionada |
| --- | ---: | --- | --- |
| Color | 1920×1080 | BGRA | ColorBasics-WPF |
| Depth | 512×424 | `ushort` en milímetros; 0 indica sin medida válida | DepthBasics-WPF |
| Infrared | 512×424 | `ushort` de intensidad, sin unidades radiométricas | InfraredBasics-WPF |
| LongExposureInfrared | 512×424 | `ushort` de intensidad con exposición larga | No existe equivalente directo en Toolkit 1.8 |
| BodyIndex | 512×424 | 0–5 para un cuerpo; 255 para fondo | BackgroundRemovalBasics-WPF |
| ColorDepth | 512×424 | RGB registrado en BGRA y profundidad `ushort` en milímetros; calibración lateral al grabar | CoordinateMappingBasics-WPF, KinectFusionColorBasics-WPF |

`FrameRenderer` produce la imagen visible. La profundidad se muestra con una escala según el rango fiable comunicado por el sensor. El infrarrojo calcula contraste de los percentiles aproximados 1–99 % de cada fotograma. Esas transformaciones **no cambian** `Values`.

La ruta nativa 360 usa libfreenect para RGB, profundidad en milímetros e IR de 8 bits. El backend convierte RGB a BGRA e IR a `ushort` multiplicando cada muestra por 257; este último valor es intensidad reescalada, no una lectura original de 16 bits. Las dimensiones vienen del modo negociado con la cámara. Estas conversiones compilan, pero aún no se han validado con fotogramas físicos porque la cámara de este equipo continúa enlazada al controlador Microsoft. La calibración de profundidad que usa la nube PLY 360 es una aproximación por campo de visión, no una calibración de fábrica; consulta [geometría](geometry.md).

`FrameExporter.SavePgm` escribe PGM P5 de 16 bits en orden de bytes grande, como exige PGM. Se puede abrir con herramientas de imagen científica. El comentario de PGM es genérico: interpreta las unidades según el flujo.

## Usar desde otra aplicación .NET

Referencia `KinectHoard.Core.dll` y el módulo de la generación que necesites. Los backends SDK 1.8 y 2.0 tienen dependencias con el mismo nombre `Microsoft.Kinect`, por lo que Hoard los carga en `AppDomain` separados mediante `Program.LoadBackend`. El módulo 360 nativo no carga el SDK 1.8. Si tu programa solo usa One, puede instanciar `OneCamera` directamente tras instalar el runtime Kinect 2.x.

```csharp
using (var camera = new KinectHoard.Driver.One.OneCamera())
{
    camera.Open(KinectHoard.Core.StreamKind.Depth);
    KinectHoard.Core.CameraFrame frame;
    while (!camera.TryRead(out frame)) System.Threading.Thread.Sleep(30);
    ushort millimetres = frame.Values[100 * frame.Width + 100];
}
```

El dispositivo puede desaparecer del bus durante el flujo en algunos hosts. Cierra el lector tras varios segundos sin fotogramas y vuelve a abrirlo después de que Windows lo enumere; `KinectHoard.App/Program.cs` contiene esa recuperación. Usa `diagnose-usb.ps1` para comparar el registro de la aplicación con los eventos Kernel-PnP 1010.

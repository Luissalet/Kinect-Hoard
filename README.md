# Kinect Hoard

Estudio local para explorar, depurar y reutilizar capacidades Kinect. Detecta Kinect 360 y Kinect One con una API de cámara común, catálogo documentado y servidor MCP para agentes que necesiten consultar el código o integrar una función en otra aplicación. La One conectada en este equipo ha entregado RGB, profundidad, infrarrojos, infrarrojos de larga exposición, índice corporal, esqueleto de una persona real, rostro 2D y HD, gestos y nubes y mallas PLY con y sin color registrado. El recorte de fondo conservó a una persona real, aunque mostró huecos visibles en la máscara.

## Ejecutar

En PowerShell, desde esta carpeta:

```powershell
.\run.ps1
```

La aplicación muestra ambos modelos, su estado USB y la disponibilidad de la cámara. Intenta abrir la Kinect One al iniciar y espera a que reaparezca si Windows la está reconectando. El selector abre **Color RGB**, **Profundidad** e **Infrarrojos** en ambos módulos; **IR larga exposición**, **Índice corporal**, **Esqueleto** y **Sin fondo** son funciones de la One en esta versión. El panel derecho permite recorrer capacidades, muestras originales, estado real de validación y documentación. `Guardar PNG` exporta la vista, `Guardar datos` guarda PGM de 16 bits o articulaciones JSON según el flujo, y `Nube PLY` exporta puntos 3D cuando está abierta la profundidad de la One.

El menú **Sesión** graba diez segundos del flujo abierto y reproduce el archivo `.khr` sin Kinect. También permite abrirlo en pausa y avanzar fotograma a fotograma para depurar avatar, gestos y AdaptiveUI. La sesión conserva la imagen, los valores crudos y las articulaciones disponibles. Véase [formato y comandos](docs/session.md).

Para generar una captura sin la interfaz:

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --capture '.\captura.png' Color
```

El tercer argumento puede ser `Depth`, `Infrared`, `LongExposureInfrared`, `BodyIndex`, `Skeleton`, `BackgroundRemoved` o `ColorDepth` (RGB registrado sobre profundidad). Para exportar valores originales de 16 bits, usa `--capture-raw '.\profundidad.pgm' Depth`. `--bodies '.\bodies.json'` exporta articulaciones; `--point-cloud`, `--mesh`, `--color-cloud` y `--color-mesh` exportan geometría PLY. `--record '.\sesion.khr' 10 Depth` graba una sesión y `--replay-last '.\sesion.khr' '.\ultimo.png'` reproduce su último fotograma. `--audio-record '.\audio.wav' 10` intenta capturar el micrófono de One y devuelve error si no hay muestras. `--diagnose '.\diagnostico.txt'` escribe el estado USB y de los dos controladores. Las capturas PNG/PGM esperan hasta 25 segundos y vuelven a intentarlo tras un corte USB.

## Paquete para usar Kinect One

`package.ps1` crea `KinectHoard-One.zip` con ejecutable, módulo de cámara, biblioteca facial, documentación, catálogo y MCP. Para usarlo en otro PC Windows x64, extrae el ZIP y abre `KinectHoard.App.exe`. Si falta Kinect Runtime 2.x, ejecuta `install-one-runtime.ps1` desde PowerShell: descarga el paquete **oficial de Microsoft**, comprueba su SHA-256 y solicita permisos de administrador para instalar el controlador. El sensor debe estar desconectado del USB durante esa instalación, como indica [Microsoft](https://www.microsoft.com/en-us/download/details.aspx?id=100067). El runtime puede llegar también mediante Windows Update. El ZIP incluye los archivos de Microsoft.Kinect.Face necesarios para la malla facial; el runtime y el controlador USB se instalan por separado.

El ZIP está almacenado en **Git LFS** porque supera los 100 MB. Se puede [descargar directamente desde GitHub](https://github.com/Luissalet/Kinect-Hoard/raw/refs/heads/main/KinectHoard-One.zip) con el botón **Download raw file**, sin instalar Git LFS. Para obtenerlo desde un clon de GitHub, instala Git LFS y ejecuta `git lfs pull`; abrir el archivo puntero de Git como ZIP no funciona.

El ZIP incluye `KinectHoard.Fusion.exe` y sus dependencias para reconstrucción 3D; no requiere instalar Python. Quien compile desde el código fuente puede ejecutar `setup-scan.ps1` para usar el script o `build-scan.ps1` para crear el ejecutable autónomo. Fusion acepta ahora un límite de profundidad y una región de interés para aislar un objeto o cabeza próximos; esta ruta necesita aún un escaneo humano de varias vistas. La vista de cámara, grabación y exportación PLY de una toma funcionan sin Fusion.
El menú **Geometría** permite ver y girar cualquier malla PLY exportada; al terminar Fusion, el visor se abre automáticamente.

El paquete aún no incorpora todas las demos del Developer Toolkit. El [catálogo](docs/capabilities.json) señala expresamente las funciones verificadas, las parciales, las que solo entregaron un flujo, las que compilan sin validación funcional y las pendientes. El [micrófono de One](docs/audio.md) entregó una grabación completa de 30 segundos y un monitor visual de nivel y haz en directo tras reconectar el USB, pero falta comprobar su estabilidad prolongada y calibrar la dirección del haz. La [demo de voz](docs/speech.md) reconoce comandos locales con una gramática editable. El [motor de gestos](docs/gestures.md) detectó una mano levantada real; ShapeGame y TicTacToe se jugaron con la mano derecha. Las [demos faciales](docs/face.md) localizaron un rostro RGB y capturaron puntos, orientación y malla HD; `FaceModelBuilder` recogió varias vistas reales, pero no completó el modelo personalizado. La [demo Fusion](docs/fusion.md) reconstruye sesiones RGBD en una malla TSDF, pero aún necesita una prueba real de varias vistas.

## Documentación e integración con agentes

- [Flujos y formatos](docs/camera.md), [cuerpo y articulaciones](docs/body.md), [eliminación de fondo](docs/background.md), [geometría](docs/geometry.md), [Fusion 3D](docs/fusion.md), [rostro 2D y 3D](docs/face.md), [gestos](docs/gestures.md), [audio](docs/audio.md), [voz](docs/speech.md), [servidor local](docs/webserver.md), [grabación y reproducción](docs/session.md), [arquitectura](docs/architecture.md), [mapa del Toolkit](docs/toolkit-map.md), [inventario de las 56 muestras instaladas](docs/toolkit-inventory.md) y [contratos de las demos pendientes](docs/next-capabilities.md).
- [MCP y Faustus](docs/mcp.md): ejecuta `setup-mcp.ps1` una vez para instalar el SDK MCP en `.venv` y conecta `faustus-plugin.json` con `KINECT_HOARD_DIR` apuntando a la carpeta de Hoard. El servidor ofrece catálogo, código permitido, diagnóstico y capturas locales. No adjunta datos de cámara automáticamente al modelo.
- [Puentes externos](docs/webserver.md): `examples/opencv_live.py` consume RGB y `examples/opencv_raw.py` profundidad cruda desde la API local; ambos se probaron con la One. `examples/matlab_live.m` y `examples/matlab_depth.m` están preparados para RGB y matrices uint16, pero MATLAB no está instalado para probarlos.
- [Privacidad](PRIVACY.md): qué datos se procesan, cuándo se guardan y qué interfaces locales pueden acceder a ellos.

## Cortes USB y recuperación

En el ASUS G513IH usado para probar la Kinect One, Windows registró el evento Kernel-PnP **1010**: `USB\VID_045E&PID_02C4` desapareció inesperadamente del bus durante la transmisión. Ocurrió también al abrir profundidad y RGB **directamente con el SDK oficial, sin Hoard**. En 35 segundos de prueba con Hoard y profundidad se registraron **2 pérdidas USB, 289 fotogramas y 3 aperturas del flujo**. Hoard recupera la transmisión cuando Windows vuelve a enumerar el sensor; no puede evitar que Windows pierda el dispositivo físico.

Una segunda prueba de 15 segundos el 18 de octubre de 2026 obtuvo **155 fotogramas, una pérdida USB y dos aperturas**, con un evento 1010 correspondiente en Windows.

Para repetir la medición:

```powershell
.\diagnose-usb.ps1 -Stream Depth -Seconds 35
```

El script relaciona los cortes observados por la aplicación con los eventos 1010 de Windows. Antes de cambiar controladores o la configuración de energía conviene comprobar cable USB 3, adaptador de corriente y compatibilidad del controlador USB 3. Microsoft pide un [controlador USB 3 dedicado, concentrador de alimentación y cableado correctos](https://www.microsoft.com/en-us/download/details.aspx?id=100067). El corte medido sucede con el sensor transmitiendo, así que no hay evidencia suficiente para atribuirlo a la suspensión selectiva de USB.

En Windows 11 conviene revisar **Configuración > Sistema > Sonido > Entrada > Varios micrófonos (Xbox NUI Sensor) > Mejoras de audio**. [Varios usuarios de Kinect v2 informaron](https://learn.microsoft.com/en-au/answers/questions/5609514/kinect-for-windows-11-has-broken-solve-found) de que desactivarlas terminó con sus reconexiones USB. En este equipo estaba activado **Voice Clarity**; se desactivó y `diagnose-audio.ps1` confirmó el cambio. Una retirada USB y una parada de RGB ocurrieron después. Al reconectar el USB en el mismo puerto con la alimentación conectada, volvieron a transmitir los siete flujos probados. RGB se mantuvo tres minutos con 2660 fotogramas y sin cortes; RGB y profundidad combinados entregaron 1914 y, en una prueba posterior, 1888 fotogramas durante tres minutos cada una, con una sola apertura y sin pérdidas USB. Falta medir la estabilidad durante horas. Las cifras y sus límites están en [mediciones de estabilidad](docs/usb-findings.md).

## Arquitectura y límites actuales

- `KinectHoard.Core` define la API propia `ICameraBackend`, el formato común de fotograma BGRA y la detección USB sin SDK.
- `KinectHoard.Driver.One` usa el runtime Kinect 2.0 presente en Windows para transmitir RGB, profundidad, infrarrojos, infrarrojos de larga exposición, índice corporal y esqueleto, además de convertir profundidad a nube de puntos.
- `KinectHoard.Driver.ThreeSixty` usa el runtime Kinect 1.8 para RGB, profundidad e infrarrojos. Está compilado y carga por separado, pero aún no se ha probado con un sensor 360 conectado.
- `KinectHoard.App` carga ambos módulos, muestra las demos y el catálogo documentado. Ejecuta cada controlador en su propio `AppDomain` porque los dos SDK publican el mismo nombre de ensamblado `Microsoft.Kinect`; en un único dominio, el runtime 2.0 sustituía erróneamente al 1.8. Al perder fotogramas durante 3 segundos, cierra el lector y vuelve a abrirlo cuando el dispositivo aparece en USB.

La API común es nuestra, pero **la transmisión de vídeo aún depende de los runtimes de Microsoft y de sus drivers de Windows**. Por eso el paquete actual no es autónomo frente a una actualización que rompa esos drivers. Para eliminar esa dependencia harían falta módulos basados en `libfreenect` y `libfreenect2` u otra implementación del protocolo USB. [`libfreenect2`](https://github.com/OpenKinect/libfreenect2) ofrece en Windows una ruta UsbDk que puede coexistir con el SDK oficial y una ruta libusbK que sustituye el driver del dispositivo. Estas rutas no proporcionan por sí solas todas las funciones de cuerpo, rostro y Fusion. No se ha cambiado ningún driver del sistema.

## Etapas de las demos del Developer Toolkit

El Toolkit 1.8 incluye demos de C#, C++ y VB, a menudo varias interfaces para la misma capacidad. La intención es integrar las **capacidades**, compartiendo la interfaz entre sensores, y adaptar las diferencias reales entre generaciones:

1. **Flujos de cámara:** color, profundidad, infrarrojos, infrarrojos de larga exposición e índice corporal de One implementados. RGB, profundidad e infrarrojos de 360 están compilados pero falta un sensor físico para validarlos.
2. **Cuerpo e interacción:** esqueleto One con persona real, avatar 2D, coordenadas cámara/profundidad, eliminación de fondo y eventos de gestos implementados. El recorte se inspeccionó con persona y presentó huecos interiores. ShapeGame y TicTacToe se validaron con la mano derecha; avatar y AdaptiveUI se comprobaron con una sesión corporal humana (cabeza a 1,34 m, controles de tamaño cercano). Queda calibrar barridos, falsos disparos y los otros rangos de distancia. Los esqueletos de ambas generaciones tienen articulaciones y seguimiento distintos; la API común normalizará la parte compartida.
3. **Audio y voz:** captura WAV y metadatos de dirección implementados para One; una grabación de 30 segundos quedó completa tras desactivar Voice Clarity y reconectar el USB. La gramática de comandos usa el reconocedor local de Windows; dos comandos sintetizados y reproducidos hacia el micrófono físico se reconocieron. Faltan pruebas con voces humanas, calibración de dirección y una prueba prolongada del micrófono.
4. **Escaneo 3D y rostro:** nube y malla de una toma, Fusion TSDF color desde sesiones RGBD y detector de rostro frontal 2D implementados. El detector Haar localizó un rostro humano; el seguimiento facial HD produjo una malla real. Falta validar Fusion con movimiento de varias vistas y completar el modelo personalizado y el escaneo volumétrico de cabeza. Las demos originales de Fusion 1.8 no se pueden ejecutar sin cambios sobre Kinect One.
5. **Herramientas y ejemplos de aplicación:** sesiones grabadas, reproducción offline, servidor HTTP local y galería de dos juegos implementados; faltan otros ejemplos de UI. Algunas herramientas como Kinect Studio son depuradores propios del SDK y se reimplementan como funciones de la aplicación, no como copias del ejecutable.

Una demo se marcará como compatible con una generación solo después de probarla con ese sensor físico. Por ahora solo la Kinect One está disponible para validación.

## Compilar

Requiere Windows, .NET Framework 4.8 y el SDK .NET 9 instalado para `dotnet build`. Este equipo ya tiene las referencias 1.8 y 2.0 necesarias. Ejecuta `build.ps1`; los módulos quedan junto a `KinectHoard.App.exe` en `KinectHoard.App\bin\Release\net48`.

# Kinect Hoard

Estudio local para explorar, depurar y reutilizar capacidades Kinect. Detecta Kinect 360 y Kinect One con una API de cámara común, catálogo documentado y servidor MCP para agentes que necesiten consultar el código o integrar una función en otra aplicación. La One conectada en este equipo ha entregado RGB, profundidad, infrarrojos, infrarrojos de larga exposición, índice corporal, esqueleto de una persona real, rostro 2D y HD, gestos y nubes y mallas PLY con y sin color registrado. El recorte de fondo conservó a una persona real, aunque mostró huecos visibles en la máscara.

## Ejecutar

Desde **Hoard Hub**, abre **Kinect Hoard**. Su interfaz usa el tema compartido de
la familia, el acceso común a Faustus y el mismo catálogo de herramientas que MCP.
Arranca bajo demanda: abrir la interfaz no enciende el sensor. **Conectar cámara**
abre la vista previa y **Iniciar escaneo** comienza a integrar.

El flujo inicial es **One · Cámara fija · Persona**. La máscara corporal separa
el fondo; la superficie con color crece en directo y **Finalizar y texturizar**
exporta OBJ, MTL y PNG. El seguimiento es experimental: el giro natural completo
de una persona **todavía no está validado** y no hay corrección no rígida de
postura. Consulta [escáner en directo](docs/live-scanner.md) para los controles,
las salidas reales y las limitaciones. La aplicación nativa y sus herramientas
anteriores siguen disponibles con el comando de abajo.

En PowerShell, desde esta carpeta:

```powershell
.\run.ps1
```

La aplicación muestra ambos modelos, su estado USB y la disponibilidad de la cámara. Al iniciar selecciona el modelo conectado y espera a que reaparezca si Windows lo está reconectando. El selector implementa **Color RGB**, **Profundidad**, **Infrarrojos** y **Color registrado sobre profundidad** para ambos módulos. **Esqueleto** está verificado con One; el backend SDK 1.8 de la 360 lo implementa, pero ese SDK no reconoce esta cámara en Windows 11. **IR larga exposición**, **Índice corporal** y **Sin fondo** son funciones de la One. El panel derecho permite recorrer capacidades, muestras originales, estado real de validación y documentación. `Guardar PNG` exporta la vista, `Guardar datos` guarda PGM de 16 bits o articulaciones JSON según el flujo, y `Nube PLY` exporta puntos 3D cuando está abierta la profundidad. Los cuatro flujos de cámara de la 360 se han capturado físicamente mediante su controlador nativo.

El menú **Sesión** graba diez segundos del flujo abierto y reproduce el archivo `.khr` sin Kinect. También permite abrirlo en pausa y avanzar fotograma a fotograma para depurar avatar, gestos y AdaptiveUI. La sesión conserva la imagen, los valores crudos y las articulaciones disponibles. Véase [formato y comandos](docs/session.md).

Para generar una captura sin la interfaz:

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --capture '.\captura.png' Color
```

El tercer argumento puede ser `Depth`, `Infrared`, `LongExposureInfrared`, `BodyIndex`, `Skeleton`, `BackgroundRemoved` o `ColorDepth` (RGB registrado sobre profundidad). Para exportar valores originales de 16 bits, usa `--capture-raw '.\profundidad.pgm' Depth`. `--bodies '.\bodies.json'` exporta articulaciones; `--point-cloud`, `--mesh`, `--color-cloud` y `--color-mesh` exportan geometría PLY. `--record '.\sesion.khr' 10 Depth` graba una sesión y `--replay-last '.\sesion.khr' '.\ultimo.png'` reproduce su último fotograma. Para elegir la 360 en CLI se usan `--capture-model 360 archivo.png ColorDepth`, `--capture-raw-model 360 archivo.pgm Depth`, `--record-model 360 archivo.khr 10 ColorDepth`, `--point-cloud-model 360 archivo.ply`, `--mesh-model 360 archivo.ply`, `--color-cloud-model 360 archivo.ply` y `--color-mesh-model 360 archivo.ply`. El esqueleto y `--bodies-model 360` requieren que funcione el SDK 1.8, que no reconoce este sensor en este equipo. `--audio-record '.\audio.wav' 10` intenta capturar el micrófono de One y devuelve error si no hay muestras. `--diagnose '.\diagnostico.txt'` escribe el estado USB y de los dos controladores, incluidos errores de PnP. Las capturas PNG/PGM esperan hasta 25 segundos y vuelven a intentarlo tras un corte USB.

## Paquete para usar Kinect One

`package.ps1` crea `KinectHoard-One.zip` con ejecutable, módulo de cámara, biblioteca facial, documentación, catálogo y MCP. Para usarlo en otro PC Windows x64, extrae el ZIP y abre `KinectHoard.App.exe`. Si falta Kinect Runtime 2.x, ejecuta `install-one-runtime.ps1` desde PowerShell: descarga el paquete **oficial de Microsoft**, comprueba su SHA-256 y solicita permisos de administrador para instalar el controlador. El sensor debe estar desconectado del USB durante esa instalación, como indica [Microsoft](https://www.microsoft.com/en-us/download/details.aspx?id=100067). El runtime puede llegar también mediante Windows Update. El ZIP incluye los archivos de Microsoft.Kinect.Face necesarios para la malla facial; el runtime y el controlador USB se instalan por separado.

El ZIP está almacenado en **Git LFS** porque supera los 100 MB. Se puede [descargar directamente desde GitHub](https://github.com/Luissalet/Kinect-Hoard/raw/refs/heads/main/KinectHoard-One.zip) con el botón **Download raw file**, sin instalar Git LFS. Para obtenerlo desde un clon de GitHub, instala Git LFS y ejecuta `git lfs pull`; abrir el archivo puntero de Git como ZIP no funciona.

El ZIP incluye `KinectHoard.Fusion.exe` y sus dependencias para reconstrucción 3D de sesiones RGBD de One o 360; no requiere instalar Python. Quien compile desde el código fuente puede ejecutar `setup-scan.ps1` para usar el script o `build-scan.ps1` para crear el ejecutable autónomo. Fusion acepta un límite de profundidad y una región de interés para aislar un objeto o cabeza próximos; esta ruta necesita aún un escaneo humano de varias vistas. La vista de cámara, grabación y exportación PLY de una toma funcionan sin Fusion.
El nuevo [escáner con textura](docs/quality-scanner.md) añade `--quality` al mismo ejecutable y exporta **OBJ + MTL + atlas PNG**, además de PLY e informe. La UI ofrece una captura de 15 segundos para cualquiera de las dos cámaras. La One guarda en sesiones de calidad su color original de 1920×1080 y el mapa hacia profundidad; esa ampliación necesita aún validación física con One. La 360 produjo un OBJ texturizado real desde una escena estática, aunque la prueba se hizo con poca luz. La captura dual y fusión con extrínsecos medidos tienen CLI, UI y MCP; `--calibrate` calcula la matriz desde puntos 3D correspondientes. La fusión y el calibrador dual pasaron pruebas sintéticas; la captura física conjunta y su calibración real siguen pendientes.
El menú **Geometría** permite ver y girar cualquier malla PLY exportada; al terminar Fusion, el visor se abre automáticamente.

Para usar la cámara nativa 360 en Windows, `install-360-driver.ps1` comprueba el dispositivo `045E:02AE`, descarga Zadig firmado, verifica su SHA-256 y guía el cambio manual a `libusbK` solo para esa cámara. El script configura Zadig para mostrar dispositivos con controlador y preseleccionar `libusbK`; comprueba siempre que el ID USB sea `045E:02AE` antes de pulsar «Replace Driver». El motor y el audio 360 conservan sus controladores; la One no se modifica. En este equipo se completó el enlace y se validaron físicamente RGB, IR, profundidad y RGBD.

El paquete aún no incorpora todas las demos del Developer Toolkit. El [catálogo](docs/capabilities.json) señala expresamente las funciones verificadas, las parciales, las que solo entregaron un flujo, las que compilan sin validación funcional y las pendientes. El [micrófono de One](docs/audio.md) entregó una grabación completa de 30 segundos y un monitor visual de nivel y haz en directo tras reconectar el USB, pero falta comprobar su estabilidad prolongada y calibrar la dirección del haz. La [demo de voz](docs/speech.md) reconoce comandos locales con una gramática editable. El [motor de gestos](docs/gestures.md) detectó una mano levantada real; ShapeGame y TicTacToe se jugaron con la mano derecha. Las [demos faciales](docs/face.md) localizaron un rostro RGB y capturaron puntos, orientación y malla HD; `FaceModelBuilder` recogió varias vistas reales, pero no completó el modelo personalizado. La [demo Fusion](docs/fusion.md) reconstruye sesiones RGBD en una malla TSDF, pero aún necesita una prueba real de varias vistas.

## Documentación e integración con agentes

- [Flujos y formatos](docs/camera.md), [cuerpo y articulaciones](docs/body.md), [eliminación de fondo](docs/background.md), [geometría](docs/geometry.md), [Fusion 3D](docs/fusion.md), [escáner OBJ con textura](docs/quality-scanner.md), [escaneo dual One + 360](docs/dual-scan.md), [rostro 2D y 3D](docs/face.md), [gestos](docs/gestures.md), [audio](docs/audio.md), [voz](docs/speech.md), [servidor local](docs/webserver.md), [grabación y reproducción](docs/session.md), [arquitectura](docs/architecture.md), [conflicto de controlador 360](docs/driver-360.md), [mapa del Toolkit](docs/toolkit-map.md), [inventario de las 56 muestras instaladas](docs/toolkit-inventory.md) y [contratos de las demos pendientes](docs/next-capabilities.md).
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
- `KinectHoard.Driver.ThreeSixty.Native` usa libfreenect/libusb para RGB, profundidad, infrarrojos y RGB registrado sobre profundidad de 360 sin SDK 1.8. El controlador nativo está compilado y validado con la cámara física `045E:02AE` enlazada a `libusbK`. Procesa eventos USB en un hilo continuo y proyecta la nube de puntos con la calibración de fábrica. El backend SDK 1.8 se conserva para instalaciones donde funcione. Véase [diagnóstico del controlador 360](docs/driver-360.md).
- `KinectHoard.App` carga ambos módulos, muestra las demos y el catálogo documentado. Ejecuta cada controlador en su propio `AppDomain` porque los dos SDK publican el mismo nombre de ensamblado `Microsoft.Kinect`; en un único dominio, el runtime 2.0 sustituía erróneamente al 1.8. Al perder fotogramas durante 3 segundos, cierra el lector y vuelve a abrirlo cuando el dispositivo aparece en USB.

La API común es nuestra. La One sigue dependiendo del runtime y controlador 2.0 de Microsoft; la ruta nativa de 360 evita el runtime 1.8 y necesita libusbK en la cámara. `build-native360.ps1` permite reconstruir sus DLL con fuentes fijadas. Cada backend se abre en un dominio .NET separado, de modo que ambos modelos pueden coexistir en el mismo proceso. El 19 de octubre se verificaron ambas vistas físicas en un sobremesa: 60 segundos de RGB simultáneo con 618 fotogramas One y 847 de 360, cero pérdidas USB y una apertura por sensor; otra prueba de RGBD simultáneo de 30 segundos obtuvo 219 y 374 fotogramas con las mismas condiciones. Las rutas nativas no proporcionan por sí solas todos los análisis corporales y faciales del Toolkit.

El menú **Cámaras > Ver ambas a la vez** abre dos vistas independientes. Cada una permite elegir RGB, profundidad o IR y reintenta su propia conexión sin cerrar la otra. `--stress-dual '.\prueba-ambas' 60 Color Depth` abre One RGB y 360 profundidad en paralelo durante 60 segundos, y escribe `one.txt` y `360.txt` con fotogramas, reaperturas y cortes. El [escaneo dual](docs/dual-scan.md) captura dos sesiones y acepta una calibración medida para fusionarlas. La reconstrucción normaliza la orientación horizontal de One SDK y conserva su mapa hacia el RGB original. El visor OBJ carga los materiales y la textura. La primera reconstrucción humana dual sigue sin calidad aceptable: tiene huecos, artefactos y partes del fondo adheridas. La coexistencia USB no demuestra un escaneo limpio ni un busto completo.

## Etapas de las demos del Developer Toolkit

El Toolkit 1.8 incluye demos de C#, C++ y VB, a menudo varias interfaces para la misma capacidad. La intención es integrar las **capacidades**, compartiendo la interfaz entre sensores, y adaptar las diferencias reales entre generaciones:

1. **Flujos de cámara:** color, profundidad, infrarrojos, infrarrojos de larga exposición e índice corporal de One implementados. RGB, profundidad, infrarrojos y RGBD registrado de 360 funcionan con la ruta nativa y `libusbK`; el esqueleto 360 sigue disponible solo mediante el SDK 1.8, que no reconoce este sensor en Windows 11.
2. **Cuerpo e interacción:** esqueleto One con persona real, avatar 2D, coordenadas cámara/profundidad, eliminación de fondo y eventos de gestos implementados. El recorte se inspeccionó con persona y presentó huecos interiores. ShapeGame y TicTacToe se validaron con la mano derecha; avatar y AdaptiveUI se comprobaron con una sesión corporal humana (cabeza a 1,34 m, controles de tamaño cercano). Queda calibrar barridos, falsos disparos y los otros rangos de distancia. Los esqueletos de ambas generaciones tienen articulaciones y seguimiento distintos; la API común normalizará la parte compartida.
3. **Audio y voz:** captura WAV y metadatos de dirección implementados para One; una grabación de 30 segundos quedó completa tras desactivar Voice Clarity y reconectar el USB. La gramática de comandos usa el reconocedor local de Windows; dos comandos sintetizados y reproducidos hacia el micrófono físico se reconocieron. Faltan pruebas con voces humanas, calibración de dirección y una prueba prolongada del micrófono.
4. **Escaneo 3D y rostro:** nube y malla de una toma, Fusion TSDF color desde sesiones RGBD y detector de rostro frontal 2D implementados. El detector Haar localizó un rostro humano; el seguimiento facial HD produjo una malla real. Falta validar Fusion con movimiento de varias vistas y completar el modelo personalizado y el escaneo volumétrico de cabeza. Las demos originales de Fusion 1.8 no se pueden ejecutar sin cambios sobre Kinect One.
5. **Herramientas y ejemplos de aplicación:** sesiones grabadas, reproducción offline, servidor HTTP local y galería de dos juegos implementados; faltan otros ejemplos de UI. Algunas herramientas como Kinect Studio son depuradores propios del SDK y se reimplementan como funciones de la aplicación, no como copias del ejecutable.

Una demo se marcará como compatible con una generación solo después de probarla con ese sensor físico. La Kinect 360 está conectada y su cámara usa `libusbK`: Hoard entrega RGB, profundidad, IR y RGBD registrado aunque el SDK 1.8 no entregue imágenes en este equipo. El [diagnóstico](docs/driver-360.md) incluye las mediciones y el corte USB observado.

## Compilar

Requiere Windows, .NET Framework 4.8 y el SDK .NET 9 instalado para `dotnet build`. Este equipo ya tiene las referencias 1.8 y 2.0 necesarias. Ejecuta `build.ps1`; los módulos quedan junto a `KinectHoard.App.exe` en `KinectHoard.App\bin\Release\net48`.

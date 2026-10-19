# Escáner 3D con textura

El escáner de calidad toma una o dos sesiones `ColorDepth` y exporta cuatro artefactos: malla geométrica PLY, malla OBJ con coordenadas UV, material MTL y atlas PNG. Es una ruta nueva junto a Fusion. Usa Open3D 0.19 para odometría RGBD, cierres de bucle cercanos, optimización de poses y volumen TSDF; usa xatlas 0.0.11 para desplegar la malla en UV. Para cada texel proyecta la superficie sobre los fotogramas, comprueba profundidad y elige la observación más frontal y cercana. El informe `*.scan.json` contiene poses, pérdidas de seguimiento, solape temporal y proporción de texels cubiertos por color observado.

La malla usa un vóxel de 5 mm por defecto, elimina discontinuidades de profundidad mayores de 50 mm y limita el atlas a 100 000 triángulos por defecto. `--max-triangles` permite subir el límite a costa de tiempo y memoria; una prueba de 120 000 caras tardó cerca de dos minutos y medio en este equipo. Estos parámetros no sustituyen una medición de precisión. Un atlas PNG de 2048×2048 es la opción inicial; 4096×4096 aumenta memoria y tiempo. Las zonas sin una observación válida conservan el color por vértice del TSDF como respaldo; `texture_observed_coverage` permite distinguirlas.

## Una cámara

En la UI: **Geometría > Escáner con textura OBJ (15 segundos)...**. Elige One o 360 en el selector de cámaras. Al terminar, la sesión, la calibración, el OBJ, MTL, PNG, PLY y el informe quedan junto a la ruta elegida. El visor abre el OBJ con textura.

En el ZIP, sin instalar Python:

```powershell
& '.\KinectHoard.Fusion.exe' --quality '.\escena.khr' '.\escena.obj' --capture 15 --model one --tracking auto
& '.\KinectHoard.Fusion.exe' --quality '.\escena360.khr' '.\escena360.obj' --capture 15 --model 360 --tracking auto
& '.\KinectHoard.Fusion.exe' --quality '.\escena360.khr' '.\otra.obj' --tracking fixed --texture-size 4096
& '.\KinectHoard.Fusion.exe' --view '.\escena360.obj'
```

`auto` estima movimiento de cámara en una escena rígida; `fixed` promedia tomas con la cámara y el objeto inmóviles. Si el sujeto gira ante una cámara fija, el escáner necesita estimar correctamente esa rotación: una sesión fallida no debe interpretarse como una malla completa. Para un objeto pequeño, coloca iluminación uniforme y evita movimiento rápido, reflejos y superficies transparentes. El color de la textura procede de las imágenes reales; el exportador no aclara ni inventa detalle.

Las capturas de calidad usan `KINECT_HOARD_SESSION_2`. Con One, guardan también el color original de 1920×1080 y el mapa de píxeles de profundidad hacia esa imagen; el atlas interpola ese mapa para conservar detalle fotográfico. Esta ruta compila y pasa una prueba sintética, pero **aún no se ha validado físicamente con la One** después de añadir el formato 2. La 360 conserva RGB registrado de 640×480. Las sesiones antiguas de formato 1 siguen admitidas, aunque su color ya está reducido a la resolución de profundidad. El archivo de formato 2 puede ocupar bastante más disco porque preserva el RGB original de One.

## Dos cámaras

La interfaz ofrece **Geometría > Escaneo dual con calibración...**. Pide un JSON de calibración medida, graba dos sesiones RGBD en paralelo y reconstruye en el sistema de la primera cámara. También se puede ejecutar:

```powershell
& '.\KinectHoard.Fusion.exe' --quality '.\one.khr' '.\ambas.obj' `
  --second-session '.\360.khr' --extrinsics '.\calibracion.json' `
  --capture-dual 15 --tracking fixed
```

El JSON debe tener `format: "KINECT_HOARD_DUAL_EXTRINSICS_1"`, una matriz rígida `world_from_second` de 4×4 en **metros**, `calibration_method` y `rms_error_metres` medido y no superior a 0,03. La primera cámara define el mundo. La aplicación rechaza reflejos, escalas y matrices inválidas. Escribir una identidad arbitraria no alinea cámaras enfrentadas.

Hoard calcula la transformación a partir de un JSON de **al menos cuatro puntos 3D correspondientes y extendidos en tres dimensiones**, medidos sobre una pieza rígida que puedan observar ambas cámaras. La estructura es `format: "KINECT_HOARD_DUAL_LANDMARKS_1"`, `first_points_metres: [[x,y,z], ...]` y `second_points_metres: [[x,y,z], ...]`, en el mismo orden. Se ajusta una transformación rígida con RANSAC, se descartan correspondencias incoherentes y se guarda el error RMS:

```powershell
& '.\KinectHoard.Fusion.exe' --calibrate '.\puntos.json' '.\calibracion.json'
```

La utilidad pasó una prueba sintética con 11 de 12 pares aceptados y 2,8 mm RMS, incluido un punto erróneo. **Aún falta una herramienta de selección de puntos en el visor y calibrar los sensores físicos.** La captura simultánea física sigue pendiente; hasta medirla, el modo dual se considera **implementado sin validar**. El [diseño dual](dual-scan.md) define la prueba de aceptación.

## Validación actual y límites

La reconstrucción normaliza las sesiones de One SDK reflejadas horizontalmente antes de fusionar: invierte RGB registrado y profundidad juntos, ajusta `cx` y reordena el mapa hacia el RGB original. La textura original conserva su resolución. Las sesiones antiguas se identifican por el método de intrínsecos del SDK; el campo opcional `image_orientation` del JSON admite `mirrored_x` o `camera` para indicar explícitamente la convención. Los extrínsecos del escáner se miden después de esta normalización, en ejes ópticos X derecha, Y abajo y Z hacia delante. `horizontal_flip_applied` deja constancia del ajuste en cada informe.

El visor carga el OBJ con posprocesado de materiales para conservar UV y atlas PNG; un OBJ sin colores por vértice no se debe mostrar como una superficie blanca si tiene textura. `tests/session-orientation.py` comprueba geometría asimétrica, principal óptico descentrado y correspondencia del RGB original. Una prueba física de captura One+360 simultánea transmitió RGB durante 60 segundos y RGBD durante 30 segundos sin pérdidas USB; esto valida la captura, no la calidad del busto. La primera reconstrucción humana dual presentó huecos, artefactos y fondo adherido y no se considera un escaneo aceptado.

Una sesión real estática de la 360 se procesó en un OBJ de 99 999 caras y atlas 1024×1024 con 98,4 % de texels observados; Open3D volvió a abrir el OBJ con UV y textura. Una captura nueva en formato 2 de la 360 produjo 49 999 caras y 99,3 % de cobertura. La habitación estaba oscura y el PNG resultó oscuro, como la captura registrada. La prueba sintética verifica formato 2 con color de mayor resolución, lectura del OBJ y unión de dos sesiones con extrínsecos conocidos; también rechaza una matriz reflejada.

Faltan una captura One física en formato 2, una captura dual física, calibración entre sensores, prueba real de varias vistas alrededor de un objeto, medición de error dimensional y evaluación de calidad visual frente al escáner comunitario de referencia. La salida puede conservar huecos; no se garantiza una malla cerrada ni una textura uniforme en zonas sin fotografía. El límite de detalle geométrico lo impone la profundidad real de cada sensor, aunque el atlas de One pueda usar color de mayor resolución.

Referencias de implementación: [sistema de reconstrucción Open3D](https://www.open3d.org/docs/release/tutorial/reconstruction_system/system_overview.html), [odometría y grafo de poses](https://www.open3d.org/docs/release/tutorial/reconstruction_system/make_fragments.html) y [xatlas Python](https://github.com/mworchel/xatlas-python).

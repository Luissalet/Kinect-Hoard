# Fusion RGBD y reconstrucción 3D

La demo graba color registrado y profundidad de One o 360 en una sesión `.khr` de tipo `ColorDepth`. Guarda junto a ella `*.intrinsics.json` con la calibración de profundidad del sensor. `fusion.py` estima el movimiento entre fotogramas RGBD con odometría y los integra en un volumen TSDF; exporta una malla PLY con color y un informe JSON con las poses, el número de fotogramas aceptados y las pérdidas de seguimiento.

## Activación

El ZIP incluye `KinectHoard.Fusion.exe` con Open3D 0.19.0; basta extraerlo entero. La versión 0.20.0 de Open3D tiene una [regresión TSDF reportada](https://github.com/isl-org/Open3D/issues/7592) que produce mallas vacías con profundidad métrica; la versión probada queda fijada en `requirements-scan.txt`. Al compilar desde el código, `setup-scan.ps1` prepara Python 3.12 y `build-scan.ps1` genera el ejecutable autónomo. Fusion y MCP tienen ejecutables o entornos separados.

Desde la UI: **Geometría > Fusion: escanear 15 segundos...**. La cámara de la vista previa se cierra durante la grabación y se reabre al terminar. La malla, la sesión RGBD, la calibración y el informe quedan en la carpeta elegida.

Al acabar se abre un visor 3D para girar y acercar la malla con el ratón. **Geometría > Ver malla PLY...** permite abrirla después. El visor realza automáticamente el color si la escena quedó oscura; solo cambia la vista, no el PLY. Para comparar los colores originales, usa `KinectHoard.Fusion.exe --view escena.ply --raw-colors`.

Desde CLI, en la carpeta de Hoard:

```powershell
& '.\KinectHoard.Fusion.exe' '.\escena.khr' '.\escena.ply' --capture 15 --tracking auto
& '.\KinectHoard.Fusion.exe' '.\escena-360.khr' '.\escena-360.ply' --capture 15 --model 360 --tracking auto
& '.\KinectHoard.Fusion.exe' '.\escena.khr' '.\otra-malla.ply' --tracking auto
```

MCP ofrece `scan_3d(seconds, tracking, generation)` y `fuse_session(filename, tracking)`. `generation` selecciona `one` o `360`. `auto` estima la pose con color y profundidad; `fixed` integra todos los fotogramas en una misma pose, útil para reducir ruido con el sensor inmóvil. Cuando la odometría falla o propone más de 25 cm / 25 grados entre fotogramas, se descarta ese fotograma y el informe incrementa `tracking_losses`.

Para aislar un objeto cercano o una cabeza ante una cámara fija, `--foreground-max-depth METROS` pone a cero el fondo lejano **antes** de la odometría y la integración. `--roi X Y W H` restringe además la imagen de profundidad (512×424 en One; 640×480 en 360) a un rectángulo fijo. El informe conserva ambos parámetros. Ejemplo experimental, ajustando el rectángulo y el límite a la posición real del sujeto:

```powershell
& '.\KinectHoard.Fusion.exe' '.\cabeza.khr' '.\cabeza.ply' --capture 30 --tracking auto --foreground-max-depth 1.8 --roi 130 20 260 180
```

Esta ruta integra un volumen TSDF del primer plano; puede seguir un objeto que gira si la odometría encuentra geometría suficiente. No usa todavía una máscara facial exacta ni corrige movimientos de traslación de la cabeza fuera de la región. **No se ha probado con una persona real ni se puede afirmar que reconstruya toda la cabeza.**

En el repositorio sin ejecutable de Fusion también sirven los mismos comandos sustituyendo `KinectHoard.Fusion.exe` por `.venv-scan\Scripts\python.exe fusion.py` después de ejecutar `setup-scan.ps1`.

El PLY usa el sistema de coordenadas de Open3D respecto a la **primera cámara**: X derecha, Y abajo, Z adelante, en metros. La calibración conserva también los coeficientes radiales que devuelve el SDK; la integración TSDF actual utiliza la aproximación pinhole de Open3D. La salida es una malla de superficies observadas, sin garantía de cierre ni textura UV. El informe registra posiciones, dimensiones, vértices y caras; no adjunta las imágenes a MCP.

## Prueba realizada y límites

Una captura real de la One de cinco segundos produjo siete fotogramas RGBD; los siete se integraron con odometría automática y se exportaron 122 682 vértices y 197 151 caras con color. En otra captura **estática**, cinco fotogramas dieron 118 612 vértices, 187 816 caras y una traslación estimada inferior a unos milímetros. La prueba automatizada sintética verifica que el TSDF no vuelva a quedar vacío.

Con la 360 física y `libusbK`, una sesión de diez fotogramas RGBD estáticos se integró 10/10 con `fixed` y 10/10 con `auto`; este último produjo 84 164 vértices y 143 167 caras. Esto verifica captura, calibración, registro RGB y reconstrucción en una escena fija. No mide precisión ni reconstrucción alrededor del objeto.

**Falta validar un escaneo de varias vistas con movimiento real del sensor u objeto**, medir deriva, recuperación tras pérdida de tracking y geometría de superficies ocultas. El modo de región y distancia se verificó con datos RGBD sintéticos, pero no con una cabeza. Tampoco hay cierre de bucle ni detección automática de cabeza. La One sigue usando Kinect Runtime 2.0 para adquirir los fotogramas; Open3D solo realiza la reconstrucción.

El modo de dos cámaras enfrentadas captura dos sesiones en paralelo y las fusiona con una calibración extrínseca suministrada. Se probó sintéticamente; faltan calibración real y prueba física simultánea. Su contrato y límites se describen en [escaneo dual](dual-scan.md).

Para obtener OBJ con UV y atlas PNG en lugar de solo color por vértice, usa el [escáner con textura](quality-scanner.md). Ese modo tiene su propia prueba y sus límites documentados.

Referencias de implementación: [integración TSDF](https://www.open3d.org/docs/latest/tutorial/pipelines/rgbd_integration.html), [odometría RGBD](https://www.open3d.org/docs/latest/tutorial/pipelines/rgbd_odometry.html) y [sesión Hoard](session.md).

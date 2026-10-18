# Geometría y nube de puntos

La One transforma un fotograma Depth con `CoordinateMapper.MapDepthFrameToCameraSpace`. Hoard conserva una tripleta XYZ por píxel, en **metros**. En el espacio de cámara de Kinect, X apunta a la derecha, Y hacia arriba y Z hacia delante. Las medidas de profundidad inválidas se omiten del PLY.

La ruta nativa 360 convierte profundidad de libfreenect (milímetros) a XYZ mediante `freenect_camera_to_world`, que usa la calibración de fábrica leída del sensor. El backend SDK 1.8 alternativo usa `CoordinateMapper.MapDepthFrameToSkeletonFrame` cuando ese runtime reconoce el sensor. Se habilitaron nube y malla en la UI y los comandos `--point-cloud-model 360 salida.ply` y `--mesh-model 360 salida.ply`. Con la cámara física se exportó una nube de 234566 puntos válidos y una malla de una toma con 240490 vértices y 454653 caras. No se ha medido la precisión métrica con un patrón conocido.

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --point-cloud '.\escena.ply'
```

El archivo PLY de nube es ASCII y tiene `vertex` con propiedades `float x`, `float y`, `float z`. No contiene RGB ni caras. La prueba local exportó 176 156 puntos válidos de un fotograma de 512×424.

`--mesh archivo.ply` y **Geometría > Exportar malla PLY...** producen una malla de **una sola toma**. Cada cuadrícula de cuatro píxeles de profundidad puede formar dos triángulos; se descarta cualquier triángulo con un lado 3D superior a 6 cm para no unir superficies separadas por un salto de profundidad. `capture_artifact("mesh")` ofrece la misma exportación a MCP. En la One conectada se exportó y se comprobó un PLY con 177 797 vértices, 324 938 caras e índices válidos. Sigue siendo una superficie abierta vista desde una sola posición, sin textura ni partes ocultas.

El flujo **RGB + profundidad** abre una captura sincronizada de ambos sensores y registra el color sobre cada píxel de profundidad con `CoordinateMapper`. La UI muestra la vista registrada de 512×424 y permite exportar nube o malla con propiedades PLY `red`, `green` y `blue`. Desde CLI: `--color-cloud salida.ply` y `--color-mesh salida.ply`; MCP admite `registered_color`, `color_cloud` y `color_mesh`. Los píxeles fuera del campo RGB quedan negros. La One entregó una malla color PLY válida con 177 698 vértices y 324 790 caras; 154 904 vértices tenían algún canal RGB no nulo. El primer fotograma de arranque incompleto se descarta.

Para hacer un escáner 3D completo falta registrar tomas sucesivas, estimar la pose y fusionar superficies. `KinectFusionBasics-WPF` y las demás muestras de Fusion del Toolkit 1.8 son referencias funcionales para esa adaptación, pero sus clases no funcionan automáticamente sobre Kinect One. La nube y la malla actuales preservan unidades métricas para ese trabajo.

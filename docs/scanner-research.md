# Escaneo RGB-D con movimiento libre

Investigación del 19-10-2026 para el escáner de Hoard. El primer busto dual fue
rechazado: fondo adherido, huecos y superficies partidas. No es una referencia de
calidad aceptada.

## Resultados y código comprobado

| Referencia primaria | Qué resuelve | Uso en Hoard / límite comprobado |
| --- | --- | --- |
| [Microsoft KinectFusion](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/kinectfusion-uist-comp.pdf) y [API ColorReconstruction](https://learn.microsoft.com/en-us/previous-versions/windows/kinect/dn799303(v=ieb.10)) | Seguimiento contra el volumen, integración TSDF, visualización por raycasting, malla con color. El paquete también describe mover el objeto ante la cámara. | Primera base para reconstrucción viva. Usar el motor, no ejecutar su aplicación de ejemplo. Recortar el sujeto antes de seguirlo cuando se mueve ante un fondo fijo. El modelo rígido no compensa por sí solo articulaciones o ropa. |
| [CameraPoseFinder](https://learn.microsoft.com/zh-tw/previous-versions/windows/kinect/dn799295(v=ieb.10)) | Guarda vistas y propone poses para recuperar seguimiento. | Recuperar y validar una pose antes de volver a integrar. Una pérdida de seguimiento no debe producir otra copia del objeto. |
| [KScan3D, anuncio oficial de LMI](https://lmi3d.com/news/lmi-technologies-offer-kscan3d-12-3d-modeling-software-no-cost/) | LMI documenta Kinect, Xbox One y Xtion y exportación OBJ/STL. | Referencia de producto. El anuncio gratuito no publica su motor; no se ha localizado en esta investigación código oficial reutilizable ni se ha probado aquí la app antigua. |
| [Skanect, manual oficial](https://support.structure.io/article/388-what-do-all-of-these-settings-do) | Cámara alrededor del objeto, seguimiento, reconstrucción, edición y colorización. | Referencia del flujo y del feedback. El manual distingue pérdida de seguimiento y modos de captura. No se ha obtenido código de su motor. |
| [ScanLan](https://github.com/benkuper/ScanLan), [capturador nativo](https://github.com/benkuper/ScanLan/blob/main/native/kinect-capture/src/main.cpp), [motor vivo](https://github.com/benkuper/ScanLan/blob/main/worker/scanlan/realtime.py) | Kinect v2 con Fusion; captura y archivo desacoplados; poses verificadas, recuperación, TSDF y exportación. | Código inspeccionado: FusionTracker llama realmente a DepthToDepthFloatFrame/ProcessFrame; el motor confirma recuperaciones antes de integrar. GPLv3. No se ha ejecutado ni se adopta su README como prueba de calidad. |
| [Open3D Dense SLAM](https://github.com/isl-org/Open3D/blob/main/docs/tutorial/t_reconstruction_system/dense_slam.rst) | Seguimiento frame-to-model y TSDF con API Python/C++. | Sus autores avisan expresamente de precisión limitada y ausencia de relocalización. No basta incorporar el ejemplo como escáner terminado. |
| [BundleSDF](https://github.com/NVlabs/BundleSDF) y [licencia](https://github.com/NVlabs/BundleSDF/blob/master/LICENSE.txt) | Objeto rígido desconocido moviéndose, seguimiento 6D y geometría/apariencia neuronal, máscara inicial. | Candidato de investigación para objetos. Dependencias CUDA/C++ y entorno Docker; la distribución no incluye la integración XMem para segmentación online. Licencia de investigación/evaluación no comercial. No es un componente listo para Windows ni resuelve movimiento articulado humano. |
| [FoundationPose](https://github.com/NVlabs/FoundationPose) | Estimación/seguimiento de pose de objetos, modalidades con y sin modelo. | No confundir un estimador de pose con un escáner completo. El camino sin modelo recurre a reconstrucción neuronal y tiene dependencias adicionales. Licencia de investigación/evaluación no comercial. |
| [SurfelWarp](https://github.com/weigao95/surfelwarp), [Windows](https://github.com/weigao95/surfelwarp/blob/master/doc/windows_cilantro_build.md), [licencia](https://github.com/weigao95/surfelwarp/blob/master/LICENSE.md) | Reconstrucción no rígida de una sola cámara, sin plantilla humana. | Código disponible BSD-3. Es candidato para deformaciones de personas y objetos. Toolchain documentado antiguo (CUDA9/10, VS2017), requiere adaptación; su TODO incluye albedo. No se promete ya un OBJ texturizado completo solo con este componente. |
| [DoubleFusion](https://arxiv.org/abs/1804.06023) | Captura humana dinámica con modelo corporal y superficie exterior. | Evidencia de que el movimiento humano exige algo más que una transformación rígida. No se ha localizado una entrega oficial de código lista para integrar. |
| [4DTAM](https://muskie82.github.io/4dtam/paper/4dtam_paper.pdf), [código](https://github.com/muskie82/4dtam) | Seguimiento y reconstrucción no rígida con Gaussianas y campo neuronal. | El artículo mide 1,5 fps en RTX4090 y reconoce que limita el uso en tiempo real; el vídeo de reconstrucción lleva aceleración 8x. Ubuntu/CUDA y licencia restrictiva de investigación. No presentarlo como solución inmediata de 30fps ni confundir render rápido con reconstrucción rápida. |

## Decisión de implementación

Dos modos explícitos, ambos para personas y objetos:

- **Cámara móvil:** la Kinect recorre el sujeto. Selección inicial 360.
- **Cámara fija:** el sujeto gira/mueve delante del sensor. Selección inicial One,
  pensada para el trípode. El fondo fijo se excluye del seguimiento del sujeto.

Primero integrar y medir el motor nativo Fusion con segmentación, seguimiento
contra el volumen y recuperación. Mantener captura y vista independientes del
archivo y del atlas final. Conservar RGB original para textura, además del color
del volumen en directo. No exigir turntable ni un eje de rotación conocido.

La corrección no rígida sigue siendo necesaria para tolerar cambios de postura;
no se da por resuelta al añadir los dos modos. IA de visión puede ayudar a
segmentar, relacionar vistas y compensar deformaciones. Faustus puede operar las
herramientas MCP; un LLM no sustituye el seguimiento geométrico por fotograma.

## Comprobaciones locales de dependencias

Se descargaron paquetes oficiales NuGet sin ejecutar instaladores ni cambiar
controladores. Microsoft.Kinect.Fusion normal contiene DLLs x86 y no carga en el
proceso x64. Microsoft.Kinect.Fusion.x64 2.0.1410.19000 contiene las DLLs correctas,
firmadas por Microsoft; se pudo cargar la API y crear/destruir un volumen CPU
64³ en 19ms. Esto verifica disponibilidad del motor en este Windows, no calidad
de escaneo ni velocidad de reconstrucción.

La enumeración de Fusion devuelve RTX4070Ti e Intel UHD770. Antes de evaluar AMP
en la RTX se reserva VRAM en el Hub. Las pruebas de busto con giro y objeto real,
recuperación tras pérdida y textura final siguen siendo el criterio de aceptación.

# Escaneo 3D con One y 360 enfrentadas

## Objetivo

Una One y una 360 miran lados opuestos de un objeto o persona. Hoard captura las dos vistas en un intervalo corto y reconstruye una malla única en un sistema de coordenadas común. Esta capacidad está **planificada**: la vista dual ya abre dos lectores independientes, pero no existe aún captura RGBD conjunta, calibración entre sensores ni fusión de sus mallas. La prueba física simultánea también está pendiente.

La 360 aporta otra línea de visión y puede cubrir superficies que la One no ve. La resolución y calidad de cada zona se han de medir sobre las capturas reales; unir dos sensores no crea automáticamente detalle donde ambos carecen de datos.

## Contrato de captura

Cada sensor conserva su identificador, generación, intrínsecos de profundidad, mapa RGB registrado, profundidad original en milímetros, estado USB y tiempo de adquisición. Una sesión dual guarda los fotogramas en dos pistas independientes y registra las marcas temporales del host en el momento de recepción. Debe indicar si faltó un fotograma o hubo una reconexión, sin fabricar una pareja sincronizada. Los archivos `.khr` actuales guardan sesiones de una cámara; ampliar el formato exige versionarlo y mantener lectura de sesiones anteriores.

One y 360 no tienen en Hoard un disparo de hardware común. El primer modo utilizable será para un sujeto **inmóvil**: seleccionar parejas de fotogramas próximas por marca temporal y registrar la diferencia temporal real en el informe. Para movimiento, habrá que medir el desfase y la deformación y rechazar parejas que superen un umbral validado experimentalmente. No se debe prometer captura simultánea exacta.

## Calibración y fusión

1. Medir los intrínsecos y el error de profundidad de cada sensor en su intervalo útil. Hoard ya guarda intrínsecos y proyección de fábrica; queda contrastarlos con un patrón físico.
2. Obtener una transformación rígida `world_from_one` y `world_from_360` con un objeto de calibración visible desde ambos lados o con posiciones conocidas en una estructura rígida. Al estar enfrentadas, un tablero plano visto por una sola cara no basta. Guardar matrices 4×4, unidades en metros, método, fecha y error residual; rechazar calibraciones con error alto.
3. Aplicar las transformaciones a las dos nubes. Filtrar profundidad inválida, bordes, píxeles sin color y puntos de baja confianza. Revisar en el visor la superposición antes de fusionar.
4. Integrar las dos observaciones en un volumen TSDF común con pesos por confianza y visibilidad; resolver solapes sin duplicar superficies. Exportar PLY, informe y ambas sesiones originales para depuración y reproducción.

El sistema de mundo puede fijarse en la One, pero esa elección debe constar en el informe. Los ejes de las nubes Hoard y el espacio pinhole usado por Open3D no son idénticos; la conversión debe hacerse explícita y verificarse con un objeto asimétrico para detectar reflejos o inversiones.

## Hardware y validación

La One requiere su enlace USB 3.x estable; la 360 usa su propia conexión USB y alimentación. La prueba debe registrar topología del controlador host, ancho de banda, fotogramas perdidos y reaperturas con ambas cámaras abiertas. Un concentrador que solo multiplica puertos no garantiza capacidad del bus. Este portátil no tiene ahora dos puertos utilizables para la prueba física conjunta; también se puede estudiar captura en dos ordenadores con sincronización de relojes medida.

Con los sensores enfrentados se debe comprobar empíricamente si la iluminación infrarroja de uno degrada la profundidad del otro y si hay zonas o materiales que pierden datos. La aceptación requiere: captura dual estable, extrínsecos medidos, residual de calibración, error de solape sobre una pieza de dimensiones conocidas, informe de diferencia temporal y una malla que incluya superficies exclusivas de cada cámara. Después vendría la prueba con una persona y movimiento.

La demo del Toolkit `KinectFusionExplorerMultiStaticCameras-WPF` es una referencia de flujo de varias cámaras, no una implementación válida directamente para mezclar Kinect 360 y One. La [arquitectura](architecture.md), [grabación](session.md) y [Fusion](fusion.md) describen las piezas existentes.

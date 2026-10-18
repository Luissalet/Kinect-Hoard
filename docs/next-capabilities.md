# Capacidades pendientes: contratos para implementar

Este documento describe lo que falta para equivaler a las demos del Kinect Developer Toolkit. `docs/capabilities.json` es la fuente de verdad del estado por generación. Voz y servidor local ya tienen implementaciones propias; sus límites restantes se señalan aquí y en sus documentos específicos.

La demo de comandos de voz de One ya se implementó y probó con audio reproducido hacia el micrófono físico; véase [voz](speech.md). Falta validar voces humanas y ruido.

## Rostro (`FaceTrackingBasics`, `FaceTracking3D`)

La [detección frontal 2D](face.md) localizó un rostro humano en RGB de 1920×1080 y guardó la imagen anotada. `FaceTracking3D` usa la biblioteca oficial de rostro v2 con cuerpo seguido: captura puntos, orientación, propiedades y una malla HD real. El 18 de octubre de 2026 se comprobó con persona y calidad `High`. La ruta adicional `FaceModelBuilder` recogió 321 fotogramas de una persona, pero pidió vistas con la cabeza inclinada hacia arriba y todavía no completó el modelo personalizado. Quedan pruebas de giro, oclusión, varias personas y continuidad después de un corte USB. El contrato distingue las coordenadas RGB en píxeles de las medidas de cámara en metros.

## Fusion y escaneo 3D (`KinectFusion*`, `HeadScanning`)

La [demo Fusion](fusion.md) registra poses entre fotogramas RGBD, integra un volumen TSDF y exporta PLY con color. El [escáner de calidad](quality-scanner.md) añade cierre de bucle cercano, UV y atlas PNG en OBJ. La 360 física produjo una textura de escena inmóvil; One y dos sensores juntos solo pasan pruebas sintéticas de estas funciones nuevas. Falta validar movimiento alrededor de un objeto, medir deriva y recuperación tras pérdida de tracking, calibrar cámaras enfrentadas y medir dimensiones conocidas. La UI guarda informes y abre las mallas; aún no ofrece reinicio interactivo del volumen. El escaneo de cabeza añade segmentación y consentimiento explícito para exportar geometría facial.

## Interacción (`AdaptiveUI`, `ControlsBasics`, `InteractionGallery`, `ShapeGame`, `TicTacToe`)

El [motor de gestos](gestures.md) ya consume `TrackedBody[]`, procesa sesiones `.khr` y expone eventos en la UI, CLI y MCP. Una persona activó y terminó `right_hand_raised` en vivo; la galería, ShapeGame y TicTacToe se jugaron con el puntero de mano derecha y selección por permanencia. También admiten ratón y teclado. `AdaptiveUI` cambió el tamaño de sus controles con una sesión humana pausada que registró la cabeza a 1,34 m; faltan los otros rangos de distancia. También falta calibrar barridos laterales, medir falsos disparos y normalizar el esqueleto 360 al conjunto compartido. Los juegos son aplicaciones de ejemplo, no sensores adicionales.

La API HTTP local de One está implementada y probada con profundidad; véase [servidor local](webserver.md). Faltan pruebas largas con varios clientes y durante una reconexión USB.

## Pruebas cruzadas

La Kinect 360 está conectada a este equipo mediante libusbK solo en su cámara. RGB, profundidad, IR, RGBD registrado, nube, malla, grabación, reproducción y escáner OBJ con textura de una escena estática se comprobaron con datos físicos. Siguen pendientes el esqueleto y audio 360 independientes del SDK 1.8, el barrido real de varias vistas y la captura dual física. Cada función se valida por separado con el hardware correspondiente y una captura inspeccionable. Las demos originales del Toolkit se usan como referencia de comportamiento, sin copiar su código al paquete.

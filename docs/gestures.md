# Gestos y eventos de interacción

`GestureEngine` convierte el esqueleto común (`TrackedBody[]`) en eventos reutilizables. Usa coordenadas de cámara en **metros**: X hacia la derecha, Y hacia arriba, Z alejándose del sensor. Solo acepta articulaciones con `TrackingState == 2` (seguimiento confirmado). Cada evento incluye `tracking_id`, `gesture`, `state`, `timestamp_utc` y `confidence`. El identificador de seguimiento es una cadena decimal para conservar los 64 bits en consumidores JavaScript.

Gestos disponibles: `left_hand_raised`, `right_hand_raised` y `hands_together` emiten `started` y `ended`; `left_hand_swipe_left/right` y `right_hand_swipe_left/right` emiten `detected`. Las manos elevadas deben superar 10 cm sobre su hombro; las manos juntas deben distar menos de 18 cm. El desplazamiento horizontal requiere al menos 35 cm en 0,12–0,8 s, con límites para movimiento vertical y de profundidad, y 750 ms de espera entre detecciones. Si un cuerpo desaparece más de 500 ms, los estados activos terminan.

## Uso

- En la UI, selecciona **Esqueleto**, abre la cámara y activa **Gestos > Mostrar eventos en directo**. El panel de registro muestra las transiciones.
- **Gestos > Analizar sesión de esqueleto...** procesa una grabación `.khr` existente y guarda JSON.
- CLI: `KinectHoard.App.exe --gestures-live informe.json 10`, `KinectHoard.App.exe --gestures-live-model 360 informe.json 10` o `KinectHoard.App.exe --gestures-session sesion.khr informe.json`.
- MCP: `capture_gestures(seconds)` y `analyze_gesture_session(filename)` devuelven eventos y ruta al JSON. El segundo solo acepta archivos de `captures/`.

`frames` cuenta fotogramas del flujo; `tracked_frames` cuenta fotogramas con al menos un cuerpo. Una lista vacía de eventos con `tracked_frames == 0` **no valida gestos humanos**. En la One conectada, una prueba de diez segundos con persona produjo 134 fotogramas, 117 con cuerpo seguido, y eventos `right_hand_raised` `started` y `ended`. No detectó un barrido lateral en esa prueba; queda calibrar velocidad, amplitud y falsos disparos a distintas distancias. Una sesión sintética `.khr` produjo inicio y fin de mano derecha levantada y desplazamiento de la izquierda, verificados por `tests/gesture-engine.ps1`.

La ruta de la 360 usa el esqueleto v1 normalizado al contrato común; está compilada, pero el controlador USB bloqueado impide validar aún seguimiento, gestos y controles con una persona real.

**Gestos > Galería: ShapeGame, TicTacToe y AdaptiveUI...** abre tres ejemplos interactivos. La galería cambia al flujo Esqueleto del modelo seleccionado y usa la posición proyectada de la mano derecha como puntero; permanecer sobre un botón durante 1,2 segundos lo activa. ShapeGame pide encontrar círculo, cuadrado o triángulo y cuenta aciertos. TicTacToe enfrenta X contra un jugador automático que prioriza ganar y bloquear. AdaptiveUI muestra controles cuyo ancho y tamaño de texto cambian con la distancia de la cabeza detectada: tres escalas para menos de 1,6 m, entre 1,6 y 2,8 m, y más de 2,8 m. También se pueden usar ratón, teclado, `R` para reiniciar y `1`/`2`/`3` para cambiar de pestaña. En una prueba con persona, la One sostuvo ~21 fps y un cuerpo seguido, la mano derecha seleccionó cuatro figuras de ShapeGame y puso una X en TicTacToe; el rival contestó con O. Una sesión corporal humana reproducida en pausa hizo que AdaptiveUI mostrase cabeza a **1,34 m** y redujese los botones al tamaño cercano. Faltan pruebas de los otros rangos de distancia y falsos disparos en los juegos.

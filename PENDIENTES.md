# Pendientes de Luis

## Prueba física del giro de una persona (Ágora #939)

Solo falta lo que exige estar delante del sensor. Todo lo demás está medido sin
cámara (ver `docs/live-scanner.md`). La toma real del 19-10 no sirve como prueba:
estabas a 0,6–0,75 m, fuera del encuadre buena parte del tiempo, y no hubo una
vuelta completa.

**Preparación (2 minutos)**

- Kinect One en trípode, a la altura del pecho y nivelada.
- Ponte a **1,3–1,5 m** de la cámara: en la imagen deben verse cabeza, hombros y
  la cintura con algo de margen por arriba y a los lados.
- Nada a menos de 0,5 m de ti (silla, mesa, puerta abierta); la pared, a 0,6 m o
  más por detrás. Luz de la habitación estable, sin sol directo.
- Camiseta con color o dibujo (la de dos colores vale); evita negro liso o
  tejidos brillantes. Brazos relajados y algo separados del cuerpo, sin cruzar.

**Toma (unos 45 segundos)**

1. Hub → Kinect Hoard → **Escáner 3D**. Movimiento *Cámara fija*, sensor
   *Kinect One*, sujeto *Persona*. **Conectar cámara**.
2. Comprueba en la vista izquierda que la máscara cubre tu cuerpo entero.
3. **Iniciar escaneo**. Gira sobre tu eje con pasos cortos, a ritmo constante:
   **una vuelta completa en 30–40 s** y sigue otros 45° hasta volver a ver tu
   frente. Cabeza quieta respecto al torso, mirada al frente, sin hablar.
4. **Finalizar y texturizar** y espera a *Guardado*.
5. En **Refinar una toma**, elige la toma nueva (la primera de la lista) y pulsa
   **Refinar giro** con *Con textura* marcada. Tarda 3–5 minutos.
6. Si da tiempo, repite una segunda toma con la vuelta en 60 s.

**Criterio de aprobado** (columna *Refinado* de la tabla, o `refine_status`)

| Medida | Aprobado |
| --- | --- |
| Vistas del sujeto con seguimiento (nota bajo la tabla) | ≥ 90 % |
| Giro cubierto | ≥ 90 % |
| Cierres de vuelta | ≥ 3 |
| Error al cerrar la vuelta (mediana) | ≤ 2° |
| Error de pose en pares de control | mediana ≤ 2°, p90 ≤ 5° |
| Residuo malla–profundidad (mediana) | ≤ 4 mm |
| Profundidad explicada a 1 cm | ≥ 85 % |
| Piezas sueltas de la malla | ≤ 3 |

**Criterio del seguimiento en directo** (columna *Nativo* de la misma tabla, que
ahora es el ICP con color en directo; o `live.scan.json` → `tracking`/`latency`)

| Medida | Aprobado |
| --- | --- |
| Error de pose en pares de control (mediana) | ≤ 3° |
| Solape a 1 cm en pares de control (mediana) | ≥ 75 % |
| Residuo malla–profundidad (mediana) | ≤ 6 mm |
| Cierres de vuelta en directo (`loop_closures`) | ≥ 1 |
| Seguimiento por fotograma (`track_ms_median`) | ≤ 20 ms |

Durante la toma, en la vista derecha, la superficie no debe duplicarse al volver
a ver tu frente. Sin cámara, **Reproducir como en directo** sobre la toma del
19-10 (a 0,6 m, sin vuelta completa) da 3,1° (justo por encima), 77 % y 4,4 mm.

Y a la vista, abriendo `refined.obj`: cabeza, hombros, espalda y pecho cerrados,
sin nariz ni orejas duplicadas y sin colores de delante pintados detrás. Con la
persona sintética el refinado ya da 2,0° RMS y 0,8 mm de mediana; el seguidor
SIFT anterior, 32,4° y 33 mm; el ICP en directo, 0,56° y 1,65 mm.

**Qué devolver:** el nombre de la carpeta `captures/live-…` (se queda en el
equipo; no hace falta enviar archivos). Con eso se cierra #939 o se ajusta el
umbral que falle.

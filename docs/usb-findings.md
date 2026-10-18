# Mediciones de estabilidad en el ASUS G513IH

Sensor Kinect One `USB\\VID_045E&PID_02C4`, conectado al puerto disponible del portátil mediante el adaptador de alimentación. Windows 11, Kinect Runtime 2.0 y Hoard. `diagnose-usb.ps1` cuenta fotogramas, aperturas del lector, ausencias USB y eventos Kernel-PnP 1010 de retirada inesperada.

La ruta PnP del sensor es `PCIROOT(0)#PCI(0801)#PCI(0004)#USBROOT(0)#USB(5)`. Su concentrador principal cuelga del controlador `PCI\\VEN_1022&DEV_1639...&0&0441`, identificado por Windows como **AMD USB 3.10 eXtensible Host Controller (Microsoft)**. El portátil enumera otro controlador AMD con sufijo `&0&0341`; esta observación identifica el controlador en uso, pero no demuestra que sea el origen de los cortes ni permite deducir por software la ubicación física del conector.

| Ajuste del micrófono Kinect | Prueba | Resultado |
| --- | --- | --- |
| Voice Clarity activado | Profundidad, 35 s | 289 fotogramas, 2 pérdidas USB, 3 aperturas |
| Voice Clarity activado | Profundidad, 15 s | 155 fotogramas, 1 pérdida USB, 2 aperturas; evento 1010 |
| Mejoras de audio desactivadas | Profundidad, 35 s | 685 fotogramas, 0 pérdidas USB, 1 apertura |
| Mejoras de audio desactivadas | RGB, 35 s | 182 fotogramas, 0 pérdidas USB, 7 aperturas por pérdida de fotogramas |
| Mejoras de audio desactivadas | RGB, 30 s posterior | 0 fotogramas, 0 pérdidas USB, 10 aperturas y 9 tiempos de espera; el SDK indicó `IsAvailable=False` |
| USB reconectado en el mismo puerto, mejoras de audio desactivadas | Profundidad, 35 s | 688 fotogramas, 0 pérdidas USB, 1 apertura, 0 tiempos de espera |
| USB reconectado en el mismo puerto, mejoras de audio desactivadas | RGB, 35 s | 495 fotogramas, 0 pérdidas USB, 1 apertura, 0 tiempos de espera |
| USB reconectado en el mismo puerto, mejoras de audio desactivadas | RGB, 180 s | 2660 fotogramas, 0 pérdidas USB, 1 apertura, 0 tiempos de espera y 0 eventos 1010 |
| USB reconectado en el mismo puerto, mejoras de audio desactivadas | IR, IR larga, índice corporal, esqueleto, 10 s cada uno | 182, 158, 158 y 160 fotogramas respectivamente; 0 pérdidas USB y 0 tiempos de espera |
| USB reconectado en el mismo puerto, mejoras de audio desactivadas | Recorte de fondo, 10 s, mapeo original | 5 fotogramas, 3 aperturas y 2 tiempos de espera; 0 pérdidas USB |
| USB reconectado en el mismo puerto, mejoras de audio desactivadas | Recorte de fondo, 35 s, mapeo optimizado | 379 fotogramas, 0 pérdidas USB, 1 apertura, 0 tiempos de espera |
| Segunda reconexión manual el 18/10/2026, mejoras de audio desactivadas | RGB, 120 s | 1758 fotogramas, 0 pérdidas USB, 1 apertura, 0 tiempos de espera |
| Segunda reconexión manual el 18/10/2026, mejoras de audio desactivadas | RGB + profundidad, 180 s | 1914 fotogramas, 0 pérdidas USB, 1 apertura, 0 tiempos de espera |
| Tras ciclo de alimentación y reinicio de servicios el 18/10/2026 | RGB + profundidad, 12 s | 114 fotogramas, 0 pérdidas USB, 1 apertura, 0 tiempos de espera |
| Mismo puerto y configuración el 18/10/2026, durante trabajo de empaquetado | RGB + profundidad, 180 s | 1888 fotogramas, 0 pérdidas USB, 1 apertura, 0 tiempos de espera; 0 eventos PnP 1010 y 225 |

Tras desactivar Voice Clarity, una captura de audio obtuvo 172032 bytes float32 y valores de dirección con confianza no nula. También hubo una retirada USB inesperada posterior y varias capturas de audio vacías o parciales. El ajuste mejoró la primera prueba de profundidad, pero **no ha eliminado todos los fallos**. La prueba RGB separa la ausencia del bus de un lector que deja de entregar fotogramas mientras el USB sigue enumerado.

Antes de la reconexión manual, Windows seguía enumerando el sensor pero el SDK mantenía `IsAvailable=False` y RGB no entregaba fotogramas. Desconectar y reconectar el USB en el mismo puerto, sin interrumpir la alimentación, recuperó todos los flujos probados. El reinicio puntual mediante `pnputil /restart-device` requiere permisos de administrador y no se completó; tras recuperar la transmisión no fue necesario repetirlo. No se cambió ni sustituyó el controlador USB. El recorte de fondo presentaba además un cuello de botella en el mapeo de 1920×1080 píxeles de color a profundidad, corregido al mapear los 512×424 píxeles de profundidad al color.

Los eventos 1010 se observaron también al usar el SDK oficial sin Hoard. La recuperación actual cierra y reabre el lector tras tres segundos sin fotogramas; no repara una retirada física del bus ni garantiza que el runtime vuelva a transmitir. Una prueba de estabilidad se considera satisfactoria únicamente si hay fotogramas, una sola apertura, cero tiempos de espera y cero pérdidas USB. Las pruebas continuas más largas tras la reconexión duraron tres minutos para RGB y para RGB + profundidad; no demuestran estabilidad durante horas ni identifican la causa física del evento anterior.

El 18/10/2026 a las 20:21:46 Windows volvió a registrar Kernel-PnP 1010 para `VID_045E&PID_02C4`. Más tarde Windows mostraba el dispositivo como `OK` pero RGB no llegó durante una espera de 25 s. Una segunda reconexión manual del mismo USB recuperó RGB en 3 s; la prueba posterior de 120 s figura arriba. El estado PnP `OK` no basta para afirmar que el runtime esté entregando fotogramas.

Tras esa segunda reconexión, `--audio-record` obtuvo 1.921.024 bytes de muestras float32 a 16 kHz (30,016 s, 903 bloques) en una solicitud de 30 s y terminó con código 0. Esta prueba no incluyó habla ni una fuente de sonido con posición conocida.

El 18/10/2026 a las 21:42 se intentó reiniciar solo el dispositivo compuesto con `pnputil /restart-device`; devolvió **3010** (reinicio de Windows pendiente). Kernel-PnP **225** identificó dos procesos con interfaces abiertas: el servicio de captura de vídeo de Brave sobre `MI_00` y `audiodg.exe` sobre el audio `MI_02`. Se cerró solo el proceso auxiliar de captura de Brave, se cortó la alimentación del adaptador 20 s y se reiniciaron `KinectMonitor` y `KinectManagement`. Esto explica por qué Windows no completó aquel reinicio de dispositivo; **no demuestra que Brave causara los eventos 1010 anteriores**.

Durante esa revisión, varias invocaciones de prueba pasaron a `Start-Process` una ruta de salida con espacios sin entrecomillarla. `Start-Process` la dividió y abrió la interfaz gráfica en vez del comando `--diagnose` o `--gestures-live`; los aparentes bloqueos de 15–70 s de esos intentos **no son evidencia de bloqueo del SDK**. Con rutas relativas sin espacios, `--diagnose` respondió en menos de un segundo. El SDK seguía indicando `IsAvailable=False`, pero RGB + profundidad entregó **114 fotogramas en 12 s**, y Skeleton **28 fotogramas en 8 s, 23 con cuerpo**. Por tanto, la disponibilidad del SDK tampoco basta para decidir si el sensor transmite: hay que medir fotogramas reales.

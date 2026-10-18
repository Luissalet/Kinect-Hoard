# Audio y dirección de sonido

La Kinect One expone un micrófono de matriz y un haz de escucha. `OneAudio` abre el `AudioBeam` del runtime 2.0; `IAudioBackend` mantiene la captura separada del controlador de imagen. El contrato `AudioChunk` contiene muestras mono IEEE float32 a 16 kHz, ángulo del haz en radianes, confianza y fecha UTC. `FloatWaveWriter` guarda las muestras sin conversión en un WAV estándar. El archivo JSON asociado incluye muestras de dirección cada 200 ms.

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --audio-record '.\captura-audio.wav' 10
```

El proceso devuelve código 0 solo si el WAV contiene al menos el 80 % de la duración solicitada. El JSON informa `audio_bytes`, `audio_seconds` y `requested_seconds`; un archivo parcial queda disponible para depuración aunque el proceso devuelva 2. La grabación comienza a contar su duración desde el primer bloque para no descontar el tiempo de apertura del sensor.

**Audio y voz > Explorador: nivel y dirección...** abre una vista en directo del nivel RMS en dBFS y del ángulo y confianza del haz. La cámara se pausa mientras el monitor usa el micrófono y se reabre al cerrarlo. Se comprobó en la One física: el monitor recibió muestras, actualizó el nivel de ruido ambiente alrededor de −90 dBFS y mostró el haz. Sin una fuente sonora conocida, el ángulo y la confianza permanecieron en cero; falta calibrarlos con una persona que hable desde distintas posiciones.

En el ASUS G513IH de prueba, Windows enumera `Varios micrófonos (Xbox NUI Sensor)`. Antes de cambiar los efectos, el SDK informó `sensor_available=True, audio_active=True, beams=1` pero entregó cero bytes. En Configuración se encontró **Mejoras de audio: Voice Clarity** y se cambió a **Desactivado** solo para ese micrófono; `diagnose-audio.ps1` confirmó `Disable_SysFx=1`. Después se obtuvo un WAV parcial con muestras no nulas y metadatos de dirección, pero otras grabaciones se detuvieron o quedaron vacías. Tras reconectar manualmente el USB en el mismo puerto, una captura de 10 segundos produjo 642092 bytes de WAV y salió con código 0. Una segunda reconexión permitió grabar **30,016 segundos**, 1.921.024 bytes de audio, 903 bloques y código 0. Falta repetir sesiones largas y contrastar el ángulo del haz con posiciones conocidas.

La dirección del haz indica hacia dónde escucha el dispositivo; no equivale necesariamente a una estimación de la dirección exacta de la persona que habla. El [reconocimiento de voz local](speech.md) ya está implementado con el motor de Windows y una gramática editable.

Para investigar el micrófono y posibles reconexiones USB en Windows 11, ejecuta `diagnose-audio.ps1` y revisa **Configuración > Sistema > Sonido > Entrada > Varios micrófonos (Xbox NUI Sensor) > Mejoras de audio**. [Se ha comunicado](https://learn.microsoft.com/en-au/answers/questions/5609514/kinect-for-windows-11-has-broken-solve-found) que ponerlas en **Desactivado** evita los reinicios de Kinect v2 en algunos equipos. En este portátil mejoró la primera medición de profundidad, pero aún se observó una retirada USB posterior y paradas del flujo RGB; véase [mediciones de estabilidad](usb-findings.md).

Referencia del formato del SDK: [AudioBeam en Microsoft Learn](https://learn.microsoft.com/en-us/previous-versions/windows/kinect/dn772690(v=ieb.10)) y [AudioBeamSubFrame](https://learn.microsoft.com/en-us/previous-versions/windows/kinect/dn772680(v=ieb.10)).

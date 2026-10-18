# Comandos de voz de Kinect One

Hoard graba el micrófono de la Kinect One como WAV float32 mono a 16 kHz y pasa las muestras a `System.Speech` como PCM16. `speech-commands.txt` contiene la cultura y las frases de una gramática editable. El motor de reconocimiento se ejecuta localmente; requiere un reconocedor de Windows instalado para la cultura indicada. Este equipo tiene `es-ES` y `en-US`. No se realizan acciones automáticamente al reconocer una frase: la salida es un evento que otra aplicación puede interpretar.

Desde la interfaz, **Audio y voz > Grabar y reconocer 10 segundos...** guarda el WAV, los metadatos del haz en un JSON y los comandos reconocidos en `*.speech.json`. Cierra temporalmente la vista de cámara y la reabre al terminar. Desde PowerShell:

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --speech-live '.\voz.wav' 10
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --speech-recognize '.\voz.wav' '.\voz-reconocida.json'
```

El segundo comando admite WAV mono de 16 kHz, PCM16 o IEEE float32. `speech-commands.txt` debe estar junto al ejecutable; puedes cambiar `culture=es-ES` y las frases para adaptar la demo. Cada resultado incluye texto, confianza del motor y posición temporal dentro del audio. `recognized: []` es una salida válida si no se pronunció ningún comando. Para ejecutar una acción conviene establecer un umbral de confianza y confirmar el contexto de la aplicación.

Validación local: una muestra sintetizada de «abrir color» se reconoció desde archivo con confianza 0,78. Al reproducirla dos veces por los altavoces durante una grabación del micrófono físico de la One, la demo entregó dos eventos «abrir color» con confianzas 0,82 y 0,82. La grabación tuvo 10,064 segundos de audio y terminó sin error. Falta comprobar voces humanas, ruido y distintos locales antes de usarla como interfaz fiable.

Referencia: [entrada de audio de `SpeechRecognitionEngine`](https://learn.microsoft.com/en-us/dotnet/api/system.speech.recognition.speechrecognitionengine.setinputtoaudiostream?view=netframework-4.8) y [selección de reconocedor por cultura](https://learn.microsoft.com/en-us/dotnet/api/system.speech.recognition.speechrecognitionengine.-ctor?view=netframework-4.8).

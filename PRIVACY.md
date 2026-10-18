# Privacidad de Kinect Hoard

Kinect Hoard procesa localmente vídeo RGB, profundidad, infrarrojos, cuerpos, audio, voz y rostros captados por una Kinect conectada al PC. La aplicación no registra estos datos por defecto ni los envía a OpenAI, Microsoft, Faustus u otro servicio. La vista previa se mantiene en memoria hasta cerrar el flujo.

Al elegir **Guardar**, **Grabar** o una herramienta MCP de captura, Hoard escribe el archivo en la ruta solicitada. Los datos pueden incluir imágenes de personas, grabaciones de voz, articulaciones y mallas faciales 3D. Quien maneje la cámara debe avisar a las personas presentes y obtener su consentimiento antes de grabar o compartir esas capturas. Los archivos de `captures/` permanecen en el PC hasta que el usuario los borre.

El servidor HTTP opcional escucha únicamente en `127.0.0.1` y expone fotogramas a procesos locales mientras está iniciado. El servidor MCP usa entrada y salida estándar con el cliente que el usuario configure. Sus herramientas devuelven principalmente rutas y metadatos; el cliente puede abrir los archivos si el usuario se lo permite. Los instaladores y dependencias se descargan solamente cuando el usuario ejecuta scripts de instalación o compilación.

La tecnología Kinect Runtime y Face proviene de Microsoft. Consulta también los [términos de Kinect SDK 2.0](https://download.microsoft.com/download/0/D/C/0DC5308E-36A7-4DCD-B299-B01CDFC8E345/Kinect-SDK2.0-EULA_en-US.pdf) y el [aviso de terceros](THIRD_PARTY_NOTICES.md).

# Servidor local de la Kinect One

La demo **Servidor local** abre un lector de la One en un proceso separado y publica una vista web en `http://127.0.0.1:8765/`. Se limita a la interfaz local del equipo. En la aplicación, selecciona el flujo y usa **Servidor local > Iniciar vista web**; la cámara de escritorio se cierra mientras el servidor posee el lector. **Detener servidor** lo libera y reabre la vista de escritorio si estaba activa.

Para depurar desde PowerShell, el puerto, flujo y tiempo son parámetros del ejecutable. Un tiempo `0` deja el servidor activo hasta cerrar el proceso:

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --webserver 8765 Depth 30
```

| Ruta | Respuesta |
| --- | --- |
| `/` | Página local que refresca la imagen y el estado |
| `/api/health` | USB presente, flujo, número de fotogramas, último fotograma y error actual |
| `/api/frame` | Metadatos del último fotograma y articulaciones si el flujo es `Skeleton` |
| `/frame.png` | Imagen renderizada del último fotograma |
| `/frame.raw` | Datos crudos `uint16_le` de profundidad, IR o índice corporal; `503` cuando no existen |

`/api/frame` declara `width`, `height`, `stream`, `raw_format` y `raw_unit`. En profundidad, cada valor es un milímetro; IR contiene intensidad sin calibración radiométrica; índice corporal usa 0–5 para cuerpos y 255 para fondo. Los clientes deben leer los metadatos antes del binario. La cámara se reabre después de tres segundos sin fotogramas y el estado informa si Windows sigue enumerando el USB.

Validación local: con `Depth`, `/api/health` informó transmisión activa, `/api/frame` informó 512×424 y `uint16_le`, `/frame.raw` entregó 434176 bytes (= 512×424×2) y `/frame.png` entregó una imagen. No se ha ensayado aún con varios clientes ni durante horas; el proceso atiende peticiones HTTP sucesivas y la página consulta el fotograma actual.

## Clientes de ejemplo

Con el servidor en modo `Color`, `examples/opencv_live.py` obtiene `/api/frame` y `/frame.png`, decodifica el PNG con OpenCV y muestra el vídeo. Instala `opencv-python` y `numpy` en su entorno Python y ejecuta `python examples/opencv_live.py`; `--no-window --seconds 5` permite usarlo en automatización. En una prueba con la One física recibió **102 imágenes en 5 segundos** sin error. En modo `Depth`, `examples/opencv_raw.py` lee `/frame.raw` como matriz NumPy `uint16` de 512×424 en milímetros; recibió **68 matrices en 5 segundos** y midió una mediana de 1745 mm. También acepta IR, IR de larga exposición, índice corporal y profundidad con color registrado si se selecciona ese flujo en el servidor. `examples/matlab_live.m` consume RGB PNG mediante `webread`, `websave` e `imshow`; `examples/matlab_depth.m` lee matrices `uint16` sin Image Processing Toolbox. MATLAB no está instalado en este equipo, por lo que ambos ejemplos quedan sin prueba de ejecución en MATLAB.

Referencia de implementación: [`HttpListener` de .NET Framework](https://learn.microsoft.com/en-us/dotnet/api/system.net.httplistener?view=netframework-4.8). El prefijo usa exclusivamente `127.0.0.1`; no se abre una dirección de red pública.

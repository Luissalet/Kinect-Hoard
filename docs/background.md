# Eliminación de fondo en Kinect One

`BackgroundRemoved` abre un `MultiSourceFrameReader` de Color, Depth y BodyIndex para recibir fotogramas de los tres flujos en una misma toma. Hoard usa `CoordinateMapper.MapDepthFrameToColorSpace` para buscar, para cada píxel de profundidad, su posición en la imagen de color. Copia el RGB si el índice corporal allí está entre 0 y 5; deja negro el fondo. La salida es de 512×424 píxeles, la resolución del sensor de profundidad.

La ruta entregó 379 fotogramas en 35 segundos sin tiempos de espera tras cambiar el mapeo de color a la cuadrícula de profundidad; antes entregaba cinco fotogramas en diez segundos y reabría el lector dos veces. Una captura inicial de 512×424 fue negra porque no había un cuerpo seguido delante del sensor. El 18 de octubre de 2026 se grabó otra sesión con una persona real: el último fotograma conservó cuerpo, cabeza y ropa sobre fondo negro. Se ven huecos negros en la máscara, incluso en el interior del cuerpo; el contorno necesita mejorar antes de usarlo como recorte de calidad de producción.

```powershell
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --capture '.\sin-fondo.png' BackgroundRemoved
```

Este demo mantiene el fondo negro, no transparencia. Para integrarlo en una app, puedes cambiar el destino de los píxeles descartados a alfa 0 y conservar el RGB de primer plano. La captura humana reveló huecos extensos, de modo que conviene añadir relleno de máscara y validarlo sobre movimiento y oclusiones antes de reutilizarlo para vídeo final.

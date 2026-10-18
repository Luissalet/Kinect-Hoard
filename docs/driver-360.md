# Kinect 360 en Windows 11: diagnóstico y ruta nativa

## Qué se observó en este equipo (18/10/2026)

La Kinect 360 se enumera como cámara `USB\VID_045E&PID_02AE\A00362A18841123A`, motor `PID_02B0` y dispositivo de audio `PID_02BB`. Al principio el motor tenía **código 39**: Windows había elegido `oem22.inf` de PrimeSense (`psdrv3.sys`, 2013). Kernel-PnP registró evento 219 con `STATUS_DRIVER_UNABLE_TO_LOAD`; CodeIntegrity registró eventos 3077 y 3004 para ese archivo. Una firma Authenticode válida no basta para superar la política de integridad de Windows.

Se exportaron los paquetes PrimeSense `oem22.inf` y `oem35.inf` a `.cache/driver-backup-360/` en esta máquina y se retiraron mediante PnPUtil elevado. Windows eligió el controlador Microsoft firmado para el motor (`oem112.inf`), y motor, cámara y audio quedaron con código de problema cero. Los números `oem*.inf` son **locales de este PC** y nunca deben copiarse a un script universal.

Pese a ello, el SDK oficial 1.8 no entregó imágenes: `KinectSensor.KinectSensors` no ve un sensor conectado; la muestra oficial **Color Basics** dice «No ready Kinect found» y Kinect Explorer muestra `DeviceNotSupported` para el concentrador interno. El [SDK 1.8 de Microsoft](https://www.microsoft.com/en-us/download/details.aspx?id=40278) se publicó para Windows 7/8/8.1, no Windows 11. No hay prueba de que el SDK 2.0 de One esté reemplazando el ensamblado 1.8 dentro de Hoard; cada backend usa un `AppDomain` distinto.

## Ruta independiente del SDK 1.8

`KinectHoard.Native360` y `KinectHoard.Driver.ThreeSixty.Native` están compilados con [OpenKinect/libfreenect](https://github.com/OpenKinect/libfreenect) y libusb 1.0.27. La biblioteca detectaba una Kinect (`freenect_num_devices=1`), pero la apertura devolvía `LIBUSB_ERROR_NOT_SUPPORTED (-12)` mientras la cámara usaba el servicio Microsoft `KinectCamera`.

Se enlazó **solo la cámara `045E:02AE`** con `libusbK` mediante Zadig. Windows indicó servicio `libusbK` y estado PnP OK; el motor y el audio 360 conservaron sus controladores. El INF Microsoft de la cámara se exportó antes a `.cache/driver-backup-360/microsoft-camera/` para poder revertirlo. El nombre de la cámara en Zadig fue `Xbox NUI Camera`, por lo que el ID USB es la comprobación decisiva.

La primera versión de la ruta nativa entregaba uno o dos fotogramas y luego se detenía: `freenect_process_events_timeout` se llamaba solo al solicitar una imagen desde la UI, que pausa entre peticiones. El registro de libfreenect mostró paquetes isócronos perdidos. Ahora un hilo propio procesa eventos USB continuamente y el lector copia el fotograma más reciente. Con esa corrección se midieron RGB: 151 fotogramas en 10 s, profundidad: 311 en 20 s, e IR: 150 en 10 s, cada uno sin reapertura ni pérdida USB. Se inspeccionaron PNG de las tres cámaras y PGM de profundidad e IR, además de nubes y mallas PLY. La nube usa la calibración de fábrica leída por libfreenect.

Hubo **un corte USB real** en una primera prueba de profundidad: 64 fotogramas en unos seis segundos, seguidos de una desaparición temporal del dispositivo. Windows lo reenumeró y las siguientes pruebas de profundidad de 20 s y 60 s transcurrieron sin cortes; la de 60 s entregó 957 fotogramas con una sola apertura. Hace falta medir periodos de horas antes de atribuir estabilidad definitiva. La captura simultánea con One sigue pendiente de conectar ambos sensores a puertos adecuados. La ruta nativa no aporta automáticamente seguimiento corporal, voz o rostro 3D.

El ZIP incluye las DLL nativas x64 y su backend .NET; `build-native360.ps1` permite recompilarlas desde versiones fijadas de los proyectos originales. La elección del backend nativo se hace por presencia de las DLL. Si se retiran, Hoard recurre al módulo SDK 1.8. El protocolo de prueba se encuentra en `docs/architecture.md` y las capacidades verificadas en `docs/capabilities.json`.

## Diagnóstico sin modificar Windows

```powershell
Get-PnpDevice -PresentOnly | Where-Object InstanceId -match 'VID_045E&PID_02(AE|B0|BB)'
Get-PnpDeviceProperty -InstanceId 'USB\VID_045E&PID_02AE\A00362A18841123A' `
  -KeyName DEVPKEY_Device_Service,DEVPKEY_Device_DriverInfPath
& '.\KinectHoard.App\bin\Release\net48\KinectHoard.App.exe' --diagnose '.\diagnostico.txt'
```

Referencias: [código 39](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/cm-prob-driver-failed-load), [códigos NTSTATUS](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55) y [sintaxis de PnPUtil](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/pnputil-command-syntax).

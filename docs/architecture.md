# Arquitectura del estudio

`KinectHoard.Core` define datos serializables, exportadores, renderizadores y detección USB. `KinectHoard.Driver.One` encapsula Kinect Runtime 2.x; `KinectHoard.Driver.ThreeSixty` encapsula Runtime 1.8. `KinectHoard.App` es el estudio WinForms, CLI y servidor HTTP local. `mcp_server.py` es una fachada local de documentación, diagnóstico y capturas que invoca el CLI: no mantiene otro lector abierto permanentemente. El servidor web sí mantiene un lector mientras está activo; la UI cierra su vista al iniciarlo.

```
Faustus / cliente MCP ── stdio ── mcp_server.py ── CLI de Hoard
                                       │
                                       └── docs/capabilities.json + código

UI / CLI de Hoard ── ICameraBackend ── AppDomain One ── Kinect Runtime 2.x
                                  └── AppDomain 360 ── Kinect Runtime 1.8
```

Los runtimes 1.8 y 2.x publican un ensamblado `Microsoft.Kinect` con el mismo nombre. Hoard aísla las cargas en `AppDomain` distintos para impedir que CLR resuelva el ensamblado de la generación equivocada. Los DTO de `Core` llevan `[Serializable]` para cruzar el dominio.

`UsbDiscovery` consulta Windows PnP por VID/PID, independientemente del SDK. `OneCamera` abre exactamente un lector por demo. La UI detecta tres segundos sin fotogramas, cierra el backend y vuelve a abrirlo cuando Windows enumera de nuevo la cámara. Esto recupera la aplicación después de un corte del bus; no corrige una interrupción eléctrica o del controlador host.

Para Fusion, `OneCamera` usa un lector multifuente RGB+Depth y escribe calibración `DepthIntrinsics` al grabar. `fusion.py` lee esa sesión en secuencia, estima poses RGBD con Open3D 0.19 y genera una malla TSDF color. El módulo se instala con `setup-scan.ps1` en `.venv-scan`; la UI y MCP lo invocan como proceso separado, por lo que un fallo de reconstrucción no bloquea el lector de la aplicación principal.

El catálogo `docs/capabilities.json` es la fuente única de estados que consulta MCP y muestra la UI. Al adaptar otra muestra, añade código, documento, entrada de catálogo y evidencia de validación. Una muestra del Toolkit 1.8 no se considera portada por tener un nombre parecido: valida datos, unidades y comportamiento en hardware real.

# Kinect Hoard

El manifiesto raíz es la entrada del Hub y de Faustus. Ejecutar `setup-mcp.ps1`
instala MCP, FastAPI y la biblioteca HoardLink del repositorio hermano sin enlaces.
El Hub abre `hoard_server.py` en 64321; el sensor sigue cerrado hasta Conectar.
MCP stdio ofrece las mismas herramientas que `/api/agent/tools` y el contrato
autenticado `/api/agent/call`. Conectar MCP o consultar catálogo no abre ventanas.
La interfaz utiliza el tema y el copilot oficial de HoardLink, sin LLM propio.

La portada es el menú de diez modos y 26 capacidades, con logo y referencias.
`list_modes` devuelve recetas, acciones, fuentes y muestras. Nueve herramientas
nuevas (33 entonces; 39 con las tres del refinado y las tres de reproducción) publican lector compartido, datos de articulaciones, archivos,
demos, reproducción y Blender. `connect_blender` abre articulaciones One con RGBD o Skeleton y un armature
animable en Blender; la vista limpia es una fuente Navegador para OBS. Guía:
`docs/workspace.md`. La validación física confirmó los ocho flujos One, KHR y PLY
color; audio produce 3,008 s para una solicitud de 3 s. La prueba Blender crea
huesos y keyframes; sin persona delante el SDK informa cero cuerpos.

El fallo «código 1» se reprodujo: 64320 estaba ocupado por un socket saliente
Bound/CloseWait. Los lectores eligen un puerto disponible y comparten el endpoint
entre web y MCP; no se mata el proceso ajeno. Los errores del worker quedan en
`data/*-worker.log`. Estado HTTP y captura de audio no consultan WMI por bloque.

Escáner: inicio One fija/Persona, RGB con máscara corporal SDK, seguimiento
en directo por ICP con color contra vistas clave sobre el sujeto enmascarado
(`ColorIcpTracker.cs`, `LiveIcpTracker.cs`, `SubjectGate.cs`: máscara del
refinado, descarte de brazos que se mueven, recolocación por giros del sujeto y
SIFT, cierre de la vuelta con grafo de poses que rehace el volumen) + Fusion
nativo, superficie con color, pausa, finalización y exportación OBJ/MTL/PNG/PLY.
`tracker: sift` conserva el seguidor anterior para comparar. La 360 móvil y las herramientas de estudio se conservan.
`open_studio` abre el estudio nativo después de desconectar el escáner.

Estado real: ambas cámaras dieron RGBD en directo; una silla estática 360 produjo
superficie y atlas. El busto dual anterior fue rechazado y una prueba One en modo
Objeto perdió seguimiento (con el seguidor SIFT anterior). No
se acredita giro humano natural completo ni calidad comercial. No hay corrección
no rígida ni segmentación semántica general de objetos. No anunciar esas funciones
como resueltas. Investigación y límites: `docs/scanner-research.md`.

Las tomas están en `captures/live-*`: sesión RGBD, intrínsecos, poses/máscara,
malla y textura si finalizó la exportación. No borrar capturas al corregir el motor.

Refinado sin cámara (05-11-2026): `turn_refine.py` y las herramientas
`list_live_captures`, `refine_live_scan`, `refine_status` (también botón
**Refinar giro** y `/api/scanner/refine`) escriben `refined/` en cada toma con
OBJ/MTL/PNG/PLY y `refine.json`. Persona sintética girando con brazos en
movimiento: 2,0° RMS frente a 32,4° del seguimiento nativo, superficie a 0,8 mm
de la verdad frente a 33 mm. Toma real de Luis: error de pose en pares de control
1,1° frente a 11,3°, sin las 187 vistas sin sujeto que integraba el nativo.
Fusion en directo recibe ya la imagen espejada que espera (antes su malla quedaba
con X negada respecto a las poses); `live.scan.json` marca
`mesh_coordinate_space: camera` y las tomas antiguas se corrigen al texturizar o
medir. Benchmark reproducible: `tests/turn_synthetic.py` + `--scanner-replay` +
`tests/turn_benchmark.py`; prueba automática `tests/turn-refine-smoke.py`.
Reproducir como en directo (05-11-2026): `LiveReplaySource.cs` pasa una toma
guardada o la persona sintética (`captures/synthetic-*`) por `FusionScanner.Process`
al ritmo de sus marcas de tiempo (descarta fotogramas si se retrasa); botón
**Reproducir como en directo**, `/api/scanner/replay`, `/api/scanner/replays`,
`/api/scanner/replay-score` y MCP `replay_live_capture`, `list_live_replays`,
`replay_score`; `replay_score.py` mide `captures/replay-*`. Persona sintética:
0,56° RMS / 2,2° máx. / 0,55° final (SIFT 35,5° / 67,7° / 8,5°), superficie a
1,65 mm y 82 % de completitud, residuo 2,1 mm, seguimiento 11 ms y proceso 20 ms
por fotograma (mediana) a 10 fps. Revisión 05-11: el volumen corregido tras un
cierre se rehace en un segundo volumen unas vistas clave por fotograma (pico
9–36 ms, antes 150–450 ms); la reproducción descomprime en otro hilo con
temporizador de 1 ms (a 30 fps descartaba 534 de 806 fotogramas, ahora 23); la
latencia solo mide fotogramas con sujeto (`idle_frames` aparte) y añade p99,
componentes y `trajectory_live`. Persona sintética a 30 fps: 0,83° RMS, 82 % de
completitud, 91 % de fotogramas en 33 ms, p95 44 ms (raycast de la vista). Toma real 19-10: 108 de 109
vistas seguidas, pares de control 3,1° de mediana (grabado en directo 11,3°,
refinado 1,1°), solape 77 %, residuo 4,4 mm (grabado 820 mm). Prueba
`tests/live-replay.py`.
Prueba física pendiente y su criterio de aprobado: `PENDIENTES.md`.
Las imágenes permanecen locales; la UI no envía píxeles al copilot automáticamente.

## Icono de la familia (2026-11-02)

Dragon turquesa con sensor y figura corporal dorados. Cabecera, escaner y favicon usan app-icon.svg (PNG incrustado); el Hub usa app-icon.png y el ejecutable usa app-icon.ico con seis resoluciones. Arte final con ala corregida, sin cambios de funciones ni inicio de sensores.

## Skills

The `skills` block of `faustus-plugin.json` names the procedures of the family's skill library that fit this app's work: `depth-camera-capture`, `web-3d-asset-pipeline`. The hub's Skills tab shows and changes them. This app does not hand them to connecting agents yet.

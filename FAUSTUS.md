# Kinect Hoard

El manifiesto raíz es la entrada del Hub y de Faustus. Ejecutar `setup-mcp.ps1`
instala MCP, FastAPI y la biblioteca HoardLink del repositorio hermano sin enlaces.
El Hub abre `hoard_server.py` en 64321; el sensor sigue cerrado hasta Conectar.
MCP stdio ofrece las mismas herramientas que `/api/agent/tools` y el contrato
autenticado `/api/agent/call`. Conectar MCP o consultar catálogo no abre ventanas.
La interfaz utiliza el tema y el copilot oficial de HoardLink, sin LLM propio.

Escáner: inicio One fija/Persona, RGB con máscara corporal SDK, seguimiento
rígido RGBD + Fusion nativo, superficie con color, pausa, finalización y exportación
OBJ/MTL/PNG/PLY. La 360 móvil y las herramientas de estudio se conservan.
`open_studio` abre el estudio nativo después de desconectar el escáner.

Estado real: ambas cámaras dieron RGBD en directo; una silla estática 360 produjo
superficie y atlas. El busto dual anterior fue rechazado y una prueba One en modo
Objeto perdió seguimiento. Las pruebas sintéticas rápidas muestran deriva: no
se acredita giro humano natural completo ni calidad comercial. No hay corrección
no rígida ni segmentación semántica general de objetos. No anunciar esas funciones
como resueltas. Investigación y límites: `docs/scanner-research.md`.

Las tomas están en `captures/live-*`: sesión RGBD, intrínsecos, poses/máscara,
malla y textura si finalizó la exportación. No borrar capturas al corregir el motor.
Las imágenes permanecen locales; la UI no envía píxeles al copilot automáticamente.

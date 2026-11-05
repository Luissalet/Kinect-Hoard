# Objetivos del escáner

- Prioridad actual: One fija, persona girando libremente, busto con textura.
- Hecho el 05-11-2026: refinado sin cámara de las tomas guardadas
  (`turn_refine.py`, botón **Refinar giro**, MCP `refine_live_scan`): máscara del
  sujeto, ICP con color de grueso a fino, cierre de la vuelta con grafo de poses,
  descarte por vista de brazos y manos que se movieron, métricas nativo/refinado.
  Fusion en directo recibe ahora la imagen espejada que espera, de modo que su
  malla y sus poses comparten la convención de cámara (malla nativa estática:
  0,8 mm de mediana a la verdad, antes 12 mm).
- Hecho el 05-11-2026: seguimiento en directo por ICP con color contra vistas
  clave sobre el sujeto enmascarado, descarte de brazos que se mueven,
  recolocación y cierre de la vuelta en directo con grafo de poses que rehace el
  volumen; **Reproducir como en directo** (UI, REST, MCP `replay_live_capture`)
  lo mide sin cámara. Persona sintética al ritmo real: 0,56° RMS (SIFT 35,5°);
  toma real 19-10: pares de control 3,1° de mediana (antes 11,3°).
- Hecho el 05-11-2026 (revisión): el volumen corregido tras un cierre se rehace
  en un segundo volumen, unas vistas clave por fotograma, y se intercambia (pico
  por fotograma 9–36 ms, antes 150–450 ms); la reproducción descomprime por
  adelantado y a 30 fps reales ya no pierde dos fotogramas de cada tres. Persona
  sintética a 30 fps: 91 % de los fotogramas en 33 ms, p95 44 ms, p99 52 ms.
- Bajar el p95 restante (44 ms a 30 fps en este equipo): lo que queda por encima
  es el raycast de la vista de superficie (17–25 ms, en buena parte espera a la
  GPU compartida), aplazado a fotogramas con hueco con un máximo de 300 ms.
  Candidatos: raycast propio sobre las vistas clave fuera del hilo de captura, o
  volumen de vista de menor resolución.
- Más de 160 vistas clave (unas 2,7 vueltas a 6°) dejan de añadirse y de cerrar
  vueltas: para tomas largas, sustituir las más antiguas de cada sector de giro.
- Sin máscaras archivadas (persona sintética pasada como *objeto*), la máscara en
  directo (`SubjectGate`) separa sola al sujeto de pared, suelo y caja (0,58° RMS,
  82 % de completitud), pero `turn_refine.segment` solo encuentra al sujeto en 40
  de 269 vistas y el residuo de malla de `replay_score` sale a 1,2 m. Las tomas
  reales siempre archivan máscara; igualar la segmentación del refinado a la del
  directo antes de refinar tomas sin ella.
- Acercar la toma real al refinado (3,1° frente a 1,1° en pares de control):
  registrar también contra el volumen raycast y no solo contra vistas clave.
- Compensar cambios de postura mayores que el umbral de 1,5 cm con un campo de
  deformación (SurfelWarp, BSD-3, es el candidato con licencia utilizable).
- Aislar objetos sin incorporar soportes o mobiliario en contacto.
- Mantener cámara móvil 360 y fija One como opciones del mismo Hoard.

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
- Bajar el p95 por fotograma (55 ms en este equipo) por debajo de 33 ms: el pico
  está en rehacer el volumen tras un cierre; hacerlo en un segundo volumen en
  segundo plano y cambiarlo al terminar.
- Acercar la toma real al refinado (3,1° frente a 1,1° en pares de control):
  registrar también contra el volumen raycast y no solo contra vistas clave.
- Compensar cambios de postura mayores que el umbral de 1,5 cm con un campo de
  deformación (SurfelWarp, BSD-3, es el candidato con licencia utilizable).
- Aislar objetos sin incorporar soportes o mobiliario en contacto.
- Mantener cámara móvil 360 y fija One como opciones del mismo Hoard.

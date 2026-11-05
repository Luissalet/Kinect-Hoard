# Objetivos del escáner

- Prioridad actual: One fija, persona girando libremente, busto con textura.
- Hecho el 05-11-2026: refinado sin cámara de las tomas guardadas
  (`turn_refine.py`, botón **Refinar giro**, MCP `refine_live_scan`): máscara del
  sujeto, ICP con color de grueso a fino, cierre de la vuelta con grafo de poses,
  descarte por vista de brazos y manos que se movieron, métricas nativo/refinado.
  Fusion en directo recibe ahora la imagen espejada que espera, de modo que su
  malla y sus poses comparten la convención de cámara (malla nativa estática:
  0,8 mm de mediana a la verdad, antes 12 mm).
- Llevar al seguimiento en directo lo que el refinado ya mide mejor: la persona
  sintética deriva 32° RMS con el seguidor nativo de rasgos SIFT y 2,0° con el
  ICP con color contra modelo. Medir con `tests/turn_benchmark.py` antes y
  después; un contador de fotogramas aceptados no acredita precisión.
- Cierre de la vuelta en directo (no solo al refinar), para que la superficie que
  crece en pantalla no se duplique al volver al frente.
- Compensar cambios de postura mayores que el umbral de 1,5 cm con un campo de
  deformación (SurfelWarp, BSD-3, es el candidato con licencia utilizable).
- Aislar objetos sin incorporar soportes o mobiliario en contacto.
- Mantener cámara móvil 360 y fija One como opciones del mismo Hoard.

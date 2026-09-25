# Parte 2 — Proceso actual vs. propuesto y mejoras priorizadas

Contenido definido y aprobado. Alimenta las secciones "Proceso actual vs propuesto"
y "Mejoras priorizadas" del sitio.

## Proceso actual (por responsable), con 4 puntos de error

1. **Árbitro** llena la cédula a mano — alineaciones, marcador, goles, tarjetas.
2. **[ERROR] Delegado del equipo local** entrega la cédula el lunes siguiente — un solo
   responsable, y el calendario es desbalanceado (Real Chapalita fue local 10/10 veces,
   Atlético Tlaquepaque 0/10).
3. **[ERROR] Coordinador** captura en Excel sin validación — de aquí salen variantes de
   nombre de equipo, fechas en dos formatos, un partido duplicado (P061) y un marcador
   capturado en un partido suspendido (P042).
4. **[ERROR - CAUSA RAÍZ] Comisión** revisa tarjetas una vez por semana, en un día fijo —
   hay dos causas distintas de incumplimiento. (a) Rojas directas (4 de 8 incumplidas): la
   sesión fija no cubre las jornadas entre semana (miércoles), así que la sanción llega
   después del siguiente partido del equipo. (b) Dobles amarillas y acumulación de
   amarillas (10 de las 14 sanciones incumplidas): NUNCA llegan a la hoja Sanciones, así
   que no hay control alguno sobre ellas, independientemente de cuándo sesione la
   Comisión. La causa (b) es la mayor.
5. **Coordinador** notifica sanciones por WhatsApp, sin control de si llegó a tiempo.
6. **[ERROR] Coordinador** actualiza tabla y goleo, y publica en redes sociales sin
   conciliar contra los datos — de ahí la tabla publicada con errores.

Se repite cada semana.

## Proceso propuesto, con 5 mejoras (numeradas por orden de implementación)

1. **Árbitro** llena la cédula (sin cambio).
2. **[Mejora 1] Delegado o árbitro** sube foto de la cédula por WhatsApp al terminar el
   partido. La entrega física del lunes se mantiene como respaldo legal, pero deja de ser
   el cuello de botella.
3. **[Mejora 3] Coordinador** captura en una Google Sheet con listas desplegables de equipo
   y formato de fecha fijo, y aviso si un id de partido se repite. Depende de la Mejora 1.
4. **[Mejora 2] Coordinador**: ante CUALQUIER evento que genera suspensión (roja directa,
   doble amarilla, o al alcanzar 5 amarillas acumuladas, detectado por conteo simple en la
   Google Sheet de la Mejora 3), notifica ese mismo día a los delegados de los dos
   equipos, sin esperar a la sesión semanal. Ataca las dos causas del punto 4 del proceso
   actual: el cuello de botella semanal de las rojas, y la ausencia total de control de
   doble amarilla y acumulación.
5. **Comisión** sesiona semanalmente (sin cambio en frecuencia), pero ahora solo para
   revisar casos dudosos, no como único filtro para rojas directas.
6. **[Mejora 5] Checklist de elegibilidad automática**: cruza la alineación de cada partido
   contra los suspendidos vigentes antes de darla por válida. Depende de que las Mejoras 1
   a 3 ya funcionen.
7. **[Mejora 4] Conciliación automática** (suma de goles a favor = suma en contra, cada
   equipo una vez por jornada, ningún partido suspendido cuenta como jugado) y publicación.

Se repite cada semana.

## Tabla de mejoras priorizadas

| # | Mejora | Problema que resuelve | Esfuerzo | Impacto | Riesgo | Indicador | Meta |
|---|---|---|---|---|---|---|---|
| 1 | Captura inmediata por foto | Delegado único, entrega hasta el lunes | Bajo | Alto (habilita todo lo demás) | Bajo: fotos borrosas, mitigar con prueba previa | Días entre partido y captura | De hasta 5 días a máximo 1 |
| 2 | Notificar por evento, no por calendario | Causa mayor: dobles amarillas y acumulación nunca llegan a Sanciones; causa menor: sesión fija no cubre jornada entre semana para las rojas | Bajo | Alto | Depende de revisión el mismo día con las ~10h/semana del coordinador | % de suspensiones notificadas antes del partido a impedir | De 21.1% (4 de 19) a 100% |
| 3 | Captura con validación (Google Sheet) | Errores de nombres, fechas, duplicados | Medio | Alto | Resistencia del coordinador voluntario a cambiar de herramienta | Hallazgos de calidad de datos por jornada | De >1 por partido a 0 |
| 4 | Conciliación automática antes de publicar | Tabla publicada con errores (queja 1) | Bajo | Medio-alto | Ninguno relevante | Diferencias tabla publicada vs recalculada | De 5/12 equipos con error a 0 |
| 5 | Checklist de elegibilidad antes de alinear | Alineación indebida (queja 2, 15 casos en 14 partidos) | Medio-alto, depende de mejoras 1-3 | Alto | Falsos negativos si la mejora 2 no se cumple | Casos de alineación indebida por temporada | De 15 a 0 |

## Restricciones de la liga

Toda propuesta debe respetarlas:

- Sin presupuesto (la liga se financia con cuotas de inscripción).
- Coordinador voluntario, ~10 h/semana.
- 5 árbitros, varios mayores de 50 años.
- Mala señal de celular en los campos.
- Todos los delegados usan WhatsApp.
- La liga tiene cuenta gratuita de Google.

# CLAUDE.md — Prueba técnica: Liga Municipal de Fútbol Amateur

## 1. Contexto

Prueba técnica para el puesto **Process Engineering & Data Science** en Garantía. Plazo: 24 h.
Se evalúa cómo se analizan datos, se detectan problemas en un proceso, se proponen soluciones y se **comunica** la información.
La prueba contiene a propósito información incompleta, datos sucios y afirmaciones que suenan correctas pero no lo son.

Caso: liga amateur de 12 equipos, Torneo Apertura 2026, todos contra todos a una vuelta (11 jornadas), los 8 primeros pasan a liguilla. Hay datos hasta la jornada 10.

Entregables de la prueba:
- **Parte 1.** Tabla de posiciones correcta vs publicada (con origen de cada diferencia, clasificación a liguilla y lo que aún puede cambiar); goleo correcto (top 5) vs publicado; estadísticas (goles/partido, % local/empate/visitante, tarjetas por partido total y por árbitro, con conclusión justificada sobre árbitros).
- **Parte 2.** Diagrama del proceso actual por carriles (árbitro, delegados, coordinador, Comisión) con puntos de error; propuesta de mejoras priorizada (problema ligado a hallazgo, esfuerzo, impacto, riesgo, indicador, meta); diagrama del proceso propuesto.
- **Parte 3.** Dashboard / página web con todo lo anterior.

**Este repositorio construye:** (1) un pipeline reproducible de limpieza y cálculo en Python y (2) un sitio web estático publicado con link compartible. El pipeline es parte del mensaje: el análisis debe ser auditable y re-ejecutable.

## 2. Reglas de trabajo para Claude Code

- **Nunca inventar datos ni resultados.** Todo número del sitio sale del pipeline.
- **Llave de jugador = (equipo normalizado, dorsal) → id_jugador.** Nunca cruzar por nombre (hay homónimos).
- Todo supuesto vive en `config/assumptions.yaml`; el código no debe tener supuestos hardcodeados.
- Toda corrección aplicada a los datos se registra en el log de hallazgos con su regla (ID), registro afectado, valor original y valor corregido.
- Los valores de control de la sección 8 son **pruebas automáticas** (`pytest`). Si no se reproducen, detenerse y reportar, no ajustar el código para "forzar" el número.
- No subir al repo el Word de instrucciones de la empresa. El Excel de datos sí (es sintético), salvo indicación contraria.
- Idioma del sitio: español. Código e identificadores: en inglés o español, pero consistentes.
- No usar bordes ni líneas separadoras decorativas en encabezados (estilo limpio y minimalista).

## 3. Estructura del repositorio

```
/
├── CLAUDE.md
├── README.md                  # cómo correr el pipeline y ver el sitio
├── data/raw/Datos_prueba_liga.xlsx
├── config/assumptions.yaml
├── pipeline/
│   ├── load.py                # lectura cruda
│   ├── clean.py               # reglas R01–R12, genera log de hallazgos
│   ├── standings.py           # tabla, escenarios, clasificación
│   ├── scorers.py
│   ├── stats.py               # goles, resultados, tarjetas, prueba estadística árbitros
│   ├── discipline.py          # cumplimiento de sanciones, alineación indebida
│   └── build.py               # orquesta y escribe site/data/*.json
├── tests/test_control_values.py
├── site/
│   ├── index.html
│   ├── css/styles.css
│   ├── js/app.js
│   └── data/                  # JSON generados (commit incluido para GitHub Pages)
└── .github/workflows/deploy.yml
```

## 4. Datos de entrada (Datos_prueba_liga.xlsx)

Sin hojas, filas o columnas ocultas; sin fórmulas ni comentarios (verificado).

| Hoja | Filas | Columnas |
|---|---|---|
| Léeme | — | Corte: datos al 1-sep-2026 (J1–J10). Origen: capturas del coordinador desde cédulas en papel, sin limpiar. En autogoles, `equipo` = equipo del jugador que lo anotó |
| Equipos | 12 | equipo, delegado |
| Jugadores | 218 | id_jugador, nombre, equipo, dorsal, fecha_alta, fecha_baja |
| Partidos | 61 | id_partido, jornada, fecha (texto), local, goles_local, goles_visitante, visitante, estatus, arbitro |
| Alineaciones | 1652 | id_partido, equipo, dorsal, nombre (14 por equipo por partido; no distingue titulares/suplentes) |
| Eventos | 352 | id_partido, minuto, equipo, dorsal, nombre, evento ∈ {Gol, Autogol, Amarilla, Roja} |
| Sanciones | 8 | fecha_sesion, jugador, equipo, motivo, partidos_suspension, fecha_notificacion |
| Tabla_publicada | 12 | Pos, Equipo, PJ, G, E, P, GF, GC, DG, Pts |
| Goleo_publicado | 10 | Pos, Jugador, Equipo, Goles |

Reglamento relevante: G=3, E=1, P=0. El marcador de la cédula es el resultado oficial. Toda roja = suspensión automática de al menos 1 partido, que se cumple en el siguiente partido oficial **disputado** por su equipo. 5 amarillas acumuladas = 1 partido. Registro cierra al término de la J5 (8-ago-2026). Partidos suspendidos se reprograman. Desempates: art. 18 (no proporcionado). Alineación indebida: art. 32 (no proporcionado).

## 5. Reglas de limpieza

| ID | Regla | Detalle |
|---|---|---|
| R01 | Normalizar nombres de equipo | En Partidos: `Oblatos`, `Dvo. Oblatos` → Deportivo Oblatos; `Atl. Tlaquepaque` → Atlético Tlaquepaque; `Halcones Country` → Halcones del Country; `Leones Tonalá` → Leones de Tonalá; `Santa Tere FC` → Club Santa Tere. Validar contra hoja Equipos (12 nombres canónicos) |
| R02 | Parsear fechas mixtas | Texto en `aaaa-mm-dd` o `dd/mm/aaaa`. Parsear por patrón, **nunca** con `dayfirst` global (convierte 2026-07-11 en 7-nov). Validar que cada jornada tenga una sola fecha |
| R03 | Eliminar partido duplicado | P061 es duplicado exacto de P020 (J4 Juventud 1-0 Halcones). Criterio general: mismo jornada + local + visitante |
| R04 | Excluir partidos no jugados | P042 (J7 Racing vs Sporting) estatus Suspendido: no cuenta; su marcador 0-0 capturado es inválido. Queda pendiente de reprogramación |
| R05 | Llave de jugador | (equipo_n, dorsal) → id_jugador. 100% de alineaciones y eventos cruzan |
| R06 | Autogoles | El gol se acredita al rival del equipo en `equipo`; no cuenta para goleo individual |
| R07 | Conciliar marcador vs eventos | Marcador oficial manda. Registrar discrepancias. Caso conocido: P011 marcador 4-1, eventos 3-1 (falta 1 gol de Estrella Providencia sin autor) |
| R08 | Eventos duplicados | Mismo partido, jugador, minuto y tipo de evento. Caso: P040 Óscar Aguilar García (J038) tiene 2 amarillas en min 85 → quitar una (quedan 2: min 65 y 85) |
| R09 | Eventos imposibles | Evento de un jugador posterior a su roja. Caso: P053 Raúl Reyes Chávez (J184) roja min 56 y amarilla min 86. Registrar; no eliminar sin supuesto |
| R10 | Doble amarilla sin roja | Detectar ≥2 amarillas del mismo jugador en un partido. 10 casos. Tratamiento según supuesto `double_yellow_is_red` |
| R11 | Elegibilidad por registro | Alineado con fecha_alta posterior al cierre del registro, o fuera de [fecha_alta, fecha_baja]. Caso: J218 Kevin Alonso Ibarra Soto (Juventud), alta 27-ago, jugó J10 (P059) |
| R12 | Datos posteriores al corte | Registros con fecha > 1-sep-2026. Caso: sanción de Raúl Reyes (sesión 2-sep, notificación 3-sep). Se conservan pero se marcan |

Falsos positivos a documentar (no son error): homónimos Juan Carlos Pérez Ruiz (J040 Real Chapalita #4 / J147 Tapatíos #21); traspaso de Rubén Flores Ortiz (Unión #15, baja 3-ago → Estrella #1, alta 5-ago, dentro de plazo).

## 6. Reglas confirmadas por la empresa y supuestos (`config/assumptions.yaml`)

### Respuestas de la empresa (confirmadas)

- **Art. 18 (desempates), en orden:** (1) resultado del partido entre los empatados; (2) si son 3 o más, minitabla de puntos entre ellos; (3) diferencia de goles general; (4) goles a favor; (5) menos tarjetas rojas; (6) sorteo.
- **Art. 32 (alineación indebida):** el infractor pierde 3-0; si en cancha perdió por diferencia mayor, se conserva ese marcador. Se aplica de oficio, aunque el rival no proteste. **Los goles individuales anotados en ese partido sí cuentan para el goleo.**
- **Doble amarilla = expulsión** (confirmado).
- **Alineación indebida se configura cuando el jugador jugó el partido.** En los datos, "jugó" = aparece en Alineaciones (no hay distinción titular/suplente).
- **Una suspensión cumplida en un partido posterior NO se considera cumplida:** jugar el partido que correspondía es alineación indebida.
- **P011:** la cédula física existe; el 4-1 es oficial; uno de los goles de Estrella Providencia no tiene anotador legible → queda sin autor y fuera del goleo.
- **Goleo:** los empatados comparten lugar.
- **P042:** aún sin fecha de reprogramación.
- **Recursos de la liga (para Parte 2):** sin presupuesto (se financia con cuotas de inscripción); coordinador voluntario ~10 h/semana; 5 árbitros, varios mayores de 50 años; mala señal de celular en los campos; todos los delegados usan WhatsApp; la liga tiene cuenta gratuita de Google.
- **Dashboard:** preferiblemente actualizable.
- **Entrega:** en español; puede ser un enlace.

### Supuestos propios (declarar en el sitio)

```yaml
cutoff_date: 2026-09-01
registration_close: 2026-08-08          # fin de J5
double_yellow_is_red: true              # confirmado
ineligible_if_in_lineup: true           # confirmado (jugó = aparece en Alineaciones)
late_served_suspension_is_valid: false  # confirmado
suspension_scope: next_match_only       # SUPUESTO: la suspensión corresponde solo al siguiente partido disputado;
                                        # si se viola, la consecuencia es el art. 32 en ese partido (no se arrastra)
art32_sanction: forfeit_3_0_keep_worse  # confirmado
art32_goals_count_for_scorers: true     # confirmado
tiebreakers: [head_to_head_or_minitable, goal_diff, goals_for, fewer_reds, draw]  # confirmado
reds_for_tiebreak: direct_reds_only     # SUPUESTO: solo rojas directas registradas (no se usa en el corte actual)
yellows_in_red_match_count_for_accumulation: true  # SUPUESTO; no cambia ningún caso actual
scorers_tie_policy: shared_rank         # confirmado
p042_rescheduled: pending               # confirmado
stats_use_field_score: true             # SUPUESTO: estadísticas de juego (goles, local/visitante) con marcador en cancha;
                                        # la tabla usa el resultado oficial tras art. 32
```

Mantener como escenarios alternativos en el sitio: (1) tabla "en cancha" (sin art. 32) y (2) art. 32 sin doble amarilla. Así se ve el impacto de cada regla.

## 7. Cálculos y hallazgos que el sitio debe explicar

**Tabla publicada.** Se reproduce exactamente con: (a) P061 duplicado contado, (b) P042 contado como 0-0, (c) GC de Unión Zapopan capturado como 11 en vez de 9 (su DG publicado 4 sí es correcto → fila inconsistente). Prueba interna: en la publicada ΣGF=157 ≠ ΣGC=159. Además, la publicada **no aplica el art. 32**, que es de oficio.

**Goleo publicado.** Errores: agrupa por nombre (suma JC Pérez Ruiz de Tapatíos 3 + Chapalita 2 = 5 y lo asigna a Tapatíos); cuenta autogoles (Andrés Ruiz Rojas 4 incluye autogol en P003); omite a Iván Cruz García (3).

**Calendario.** Home/away desbalanceado (Real Chapalita local 10/10, Atlético Tlaquepaque 0/10) → el % de victoria local no permite concluir ventaja de local. J6 (12-ago) y J9 (26-ago) fueron miércoles.

**Disciplina.** El proceso (entrega de cédula el lunes, Comisión semanal, notificación al día siguiente) no alcanza a sancionar antes del siguiente partido cuando hay jornada entre semana. Además no hay control de doble amarilla, de acumulación ni de cierre de registro. Visualizar como línea de tiempo por sanción: fecha del evento → siguiente partido → sesión → notificación → ¿jugó?

**Árbitros.** No concluir "más estricto" sin prueba: muestras de 9–16 partidos, asignación no aleatoria, datos con errores. Mostrar media con intervalo de confianza y la prueba.

**Restricciones para la Parte 2.** Cualquier mejora debe funcionar sin presupuesto, sin señal en cancha (la cédula en papel se mantiene o se captura offline), con árbitros mayores poco digitales, con ~10 h/semana del coordinador y usando WhatsApp + Google gratuito.

**Actualizable.** Diseñar el pipeline para que la fuente pueda ser una Google Sheet (cuenta gratuita de la liga) publicada como CSV; un GitHub Action programado (y manual) re-ejecuta pipeline + pruebas y republica. En esta entrega la fuente es el Excel; dejar la ruta a Google Sheets como configuración documentada.

**Uso de IA.** Incluir en la sección de metodología una nota transparente de cómo se usó IA (análisis, validación cruzada, construcción con Claude Code) y cómo se verificaron los resultados.

## 8. Valores de control (pruebas automáticas)

Después de R01–R08 y con las reglas confirmadas:

**Partidos:** 59 válidos (60 únicos − P042). Cada equipo aparece una vez por jornada. Racing Jardines y Sporting Americana: 9 PJ; resto: 10.

**Tabla en cancha (sin art. 32) — escenario de referencia:**

| Equipo | PJ | G | E | P | GF | GC | DG | Pts |
|---|---|---|---|---|---|---|---|---|
| Juventud Mezquitán | 10 | 6 | 1 | 3 | 19 | 10 | 9 | 19 |
| Atlético Tlaquepaque | 10 | 5 | 3 | 2 | 11 | 8 | 3 | 18 |
| Real Chapalita | 10 | 3 | 6 | 1 | 19 | 15 | 4 | 15 |
| Unión Zapopan | 10 | 4 | 3 | 3 | 13 | 9 | 4 | 15 |
| Leones de Tonalá | 10 | 4 | 3 | 3 | 13 | 12 | 1 | 15 |
| Racing Jardines | 9 | 4 | 2 | 3 | 15 | 13 | 2 | 14 |
| Sporting Americana | 9 | 3 | 4 | 2 | 9 | 9 | 0 | 13 |
| Deportivo Oblatos | 10 | 4 | 1 | 5 | 14 | 15 | -1 | 13 |
| Club Santa Tere | 10 | 4 | 1 | 5 | 9 | 14 | -5 | 13 |
| Estrella Providencia | 10 | 4 | 0 | 6 | 15 | 14 | 1 | 12 |
| Halcones del Country | 10 | 3 | 2 | 5 | 10 | 15 | -5 | 11 |
| Tapatíos United | 10 | 1 | 2 | 7 | 9 | 22 | -13 | 5 |

Con art. 18, el orden en cancha a 15 pts es Unión (minitabla 4), Chapalita (2), Leones (1); a 13 pts: Santa Tere (3), Sporting (1, DG 0), Oblatos (1, DG −1).

**Diferencias publicada − en cancha:** Juventud (+1 PJ, +1 G, +1 GF, +1 DG, +3 Pts); Halcones (+1 PJ, +1 P, +1 GC, −1 DG); Racing y Sporting (+1 PJ, +1 E, +1 Pts); Unión (+2 GC). Los otros 7 equipos coinciden.

**Partidos con alineación indebida (14) → resultado oficial por art. 32:**

| Partido | J | En cancha | Oficial | Infractor | Jugador (motivo) |
|---|---|---|---|---|---|
| P010 | 2 | Chapalita 2-2 Halcones | 0-3 | Real Chapalita | Emilio Ruiz Medina (doble amarilla P003) |
| P014 | 3 | Tapatíos 3-2 Sporting | 0-3 | Tapatíos United | Ricardo Reyes González (doble amarilla P009) |
| P026 | 5 | Estrella 1-0 Tapatíos | 0-3 | Estrella Providencia | Víctor Gutiérrez Ruiz (doble amarilla P021) |
| P031 | 6 | Estrella 0-1 Oblatos | 0-3 | Estrella Providencia | Héctor Gutiérrez Ramírez (doble amarilla P026) |
| P032 | 6 | Halcones 2-1 Leones | 3-0 | Leones de Tonalá | Óscar Díaz López (roja P027) |
| P036 | 6 | Racing 2-2 Tlaquepaque | 3-0 | Atlético Tlaquepaque | Ricardo Cruz Castillo (roja P030) |
| P039 | 7 | Halcones 1-0 Santa Tere | 0-3 | Halcones del Country | Daniel Rojas Mendoza (roja P032) |
| P044 | 8 | Leones 2-0 Santa Tere | 3-0 | Club Santa Tere | Rodrigo Anaya Lozano (5 amarillas) y Héctor Reyes Lozano (doble amarilla P039) |
| P045 | 8 | Chapalita 3-2 Estrella | 0-3 | Real Chapalita | Óscar Aguilar García (doble amarilla P040) |
| P049 | 9 | Oblatos 1-2 Santa Tere | 0-3 | Deportivo Oblatos | Óscar Torres Ramírez (doble amarilla P043) |
| P051 | 9 | Leones 1-0 Tlaquepaque | 0-3 | Leones de Tonalá | Fernando Medina González (doble amarilla P044) |
| P053 | 9 | Halcones 1-1 Sporting | 0-3 | Halcones del Country | Luis Ibarra Ibarra (doble amarilla P046) |
| P058 | 10 | Leones 0-0 Sporting | 3-0 | Sporting Americana | Raúl Reyes Chávez (roja P053) |
| P059 | 10 | Juventud 1-0 Estrella | 0-3 | Juventud Mezquitán | Kevin Alonso Ibarra Soto (alta fuera de plazo) |

Ningún partido tiene infractores de ambos equipos. Ningún caso conserva marcador en cancha (ningún infractor perdió por más de 3).

**Tabla oficial J10 (reglas confirmadas) — valor de control principal:**

| Pos | Equipo | PJ | G | E | P | GF | GC | DG | Pts |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Atlético Tlaquepaque | 10 | 6 | 2 | 2 | 12 | 8 | 4 | 20 |
| 2 | Sporting Americana | 9 | 5 | 2 | 2 | 12 | 8 | 4 | 17 |
| 3 | Club Santa Tere | 10 | 5 | 1 | 4 | 13 | 13 | 0 | 16 |
| 4 | Juventud Mezquitán | 10 | 5 | 1 | 4 | 18 | 13 | 5 | 16 |
| 5 | Racing Jardines | 9 | 5 | 1 | 3 | 16 | 11 | 5 | 16 |
| 6 | Estrella Providencia | 10 | 5 | 0 | 5 | 18 | 15 | 3 | 15 |
| 7 | Unión Zapopan | 10 | 4 | 3 | 3 | 13 | 9 | 4 | 15 |
| 8 | Leones de Tonalá | 10 | 4 | 2 | 4 | 15 | 16 | -1 | 14 |
| 9 | Deportivo Oblatos | 10 | 4 | 1 | 5 | 15 | 16 | -1 | 13 |
| 10 | Real Chapalita | 10 | 2 | 5 | 3 | 14 | 17 | -3 | 11 |
| 11 | Halcones del Country | 10 | 3 | 0 | 7 | 10 | 17 | -7 | 9 |
| 12 | Tapatíos United | 10 | 1 | 2 | 7 | 9 | 22 | -13 | 5 |

Desempates aplicados: a 16 pts, minitabla Santa Tere 6, Juventud 3, Racing 0 (los 3 partidos entre ellos jugados: P008, P029, P034). A 15 pts, Estrella le ganó a Unión (P038, 4-2).

**Impacto vs publicada:** dentro de liguilla entran Club Santa Tere y Estrella Providencia; salen Real Chapalita (3° publicado → 10°) y Deportivo Oblatos. El líder cambia (Juventud → Atlético Tlaquepaque).

**Escenario alternativo (art. 32 sin doble amarilla, 6 partidos: P032, P036, P039, P044, P058, P059):** Leones 17, Tlaquepaque 17, Santa Tere 16, Juventud 16, Racing 16, Chapalita 15, Estrella 15, Unión 15, Oblatos 13, Sporting 12, Halcones 8, Tapatíos 5. Muestra que la regla de doble amarilla decide quién entra a la liguilla entre Sporting Americana y Real Chapalita.

**J11 pendiente (pares):** Juventud–Unión, Santa Tere–Sporting, Chapalita–Racing, Tapatíos–Leones, Halcones–Estrella, Oblatos–Tlaquepaque. Más P042 Racing–Sporting (sin fecha).

**Escenarios por puntos sobre la tabla oficial (J11 + P042):** clasificados matemáticamente: Atlético Tlaquepaque y Sporting Americana. Eliminados: Halcones del Country y Tapatíos United. En disputa: los otros 8 (Real Chapalita solo puede llegar al 8° con empates a su favor).

**Pendiente disciplinario para J11:** Raúl Reyes Chávez (Sporting) fue notificado el 3-sep; con `suspension_scope: next_match_only` su suspensión correspondía a P058 (ya sancionado por art. 32). Declarar este supuesto y señalar la alternativa (que deba cumplir en J11).

**Goleo (sin autogoles, por id_jugador; incluye goles de partidos sancionados por art. 32):** 1° Víctor Navarro Morales (J205, Racing) 4. Empate en 2° a 3 goles (10 jugadores): Óscar Aguilar García J038, Hugo Silva Ramírez J054, Emilio Ruiz Sánchez J171, Andrés Ruiz Rojas J179, Sergio Vázquez Hernández J117, Fernando Morales Chávez J168, Iván Cruz García J093, Iván Castillo Ruiz J027, Carlos Flores Anaya J188, Juan Carlos Pérez Ruiz J147. JC Pérez Ruiz J040 (Chapalita): 2. Autogoles: 7. Gol sin autor: 1 (P011, Estrella; ilegible en la cédula).

**Estadísticas (marcador en cancha):** 156 goles / 59 partidos = 2.644. Local 24 (40.7%), empate 14 (23.7%), visitante 21 (35.6%). Tarjetas: 189 amarillas + 8 rojas = 197 crudas (196 tras R08) → 3.34 (3.32) por partido. Expulsiones por doble amarilla: 10 (no registradas como roja).

| Árbitro | Partidos | Tarjetas crudas | Por partido |
|---|---|---|---|
| A. Núñez | 16 | 43 | 2.69 |
| B. Salas | 9 | 33 (32 tras R08) | 3.67 (3.56) |
| C. Pineda | 10 | 29 | 2.90 |
| D. Villa | 13 | 55 | 4.23 |
| E. Ríos | 11 | 37 | 3.36 |

Kruskal-Wallis entre árbitros: p ≈ 0.13 (datos crudos). Villa vs resto (Mann-Whitney): p ≈ 0.035 sin corregir, ≈ 0.17 con Bonferroni ×5 → no significativo.

**Métricas de la queja 2:** eventos que generan suspensión: 19 (8 rojas, 10 dobles amarillas, 1 acumulación). Cumplidos a tiempo: 5 (4 rojas de J1–J3 y la doble amarilla de Arturo López Martínez). No cumplidos: 14 (73.7%). Rojas: 4/8 (50%). Más 1 alta fuera de plazo. Total: 15 casos de alineación indebida en 14 partidos, de 59 jugados (23.7%).

## 9. Sitio web

**Stack:** HTML + CSS + JavaScript vanilla, Chart.js (gráficas), Mermaid (diagramas). Sin framework ni paso de build. Datos desde `site/data/*.json`. Librerías desde CDN con versión fija.

**Diseño:** escritorio primero, responsivo para celular.
- Escritorio: navegación lateral fija, tablas completas, gráficas lado a lado, ancho máximo de contenido ~1200 px.
- Celular: navegación colapsa a menú superior, gráficas apiladas, tablas anchas con scroll horizontal dentro de su contenedor (nunca scroll lateral del body).
- Tema claro con soporte de modo oscuro por `prefers-color-scheme`. Tipografía legible, paleta sobria, un color de acento, rojo/verde solo para error/correcto (acompañado de texto o ícono, no solo color).

**Secciones (en orden, como historia):**
1. Resumen ejecutivo: 3–4 KPIs de impacto y los hallazgos principales.
2. Tabla de posiciones: oficial vs publicada con diferencias resaltadas y su causa (errores de captura y art. 32); selector de escenarios (oficial / en cancha / sin doble amarilla); desempates del art. 18 explicados; línea de corte de liguilla; estado clasificado / en disputa / eliminado.
3. Goleo: correcto vs publicado con explicación de cada diferencia.
4. Estadísticas del torneo, con advertencia sobre sesgo de localía y prueba estadística de árbitros (media ± IC).
5. Disciplina: línea de tiempo por tarjeta roja y lista de incumplimientos.
6. Calidad de datos: log de hallazgos filtrable por regla, hoja y severidad.
7. Proceso actual vs propuesto: diagramas por carriles con puntos de error marcados.
8. Mejoras priorizadas: matriz esfuerzo-impacto; por mejora: problema/hallazgo, esfuerzo, impacto, riesgo, indicador, meta. Respetar las restricciones de la sección 7.
9. Supuestos y metodología: supuestos (y respuestas de la empresa), reglas de limpieza, cómo reproducir, uso de IA, descarga de datos limpios (CSV/JSON).

## 10. Despliegue

GitHub Actions en cada push a `main` y de forma manual/programada (para la actualización desde Google Sheets): instalar dependencias → `pytest` → `python pipeline/build.py` → publicar `site/` en GitHub Pages. Si fallan las pruebas, no se publica.
Repo público sin el Word de instrucciones (GitHub Pages gratis requiere repo público). Alternativa: repo privado + Netlify/Vercel.

## 11. Estado

- [x] Respuestas de la empresa (sección 6), incluida doble amarilla = expulsión. Supuesto `suspension_scope: next_match_only` validado por el candidato; se declara en el sitio.
- [ ] Pipeline con supuestos parametrizados y pruebas en verde.
- [ ] Estructura del sitio con secciones.
- [ ] Contenido de Parte 2 (diagramas y mejoras).
- [ ] Ajuste de parámetros con respuestas y publicación final.

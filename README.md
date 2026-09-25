# Liga Municipal de Fútbol Amateur — Torneo Apertura 2026

Pipeline reproducible de limpieza y cálculo sobre los datos de la liga (J1–J10,
corte al 1-sep-2026). Todo número publicado sale de este pipeline: no hay cifras
escritas a mano.

## Requisitos

- Python 3.12 (se instaló con `winget install Python.Python.3.12`)
- Las dependencias de `requirements.txt` (pandas, openpyxl, scipy, pytest, pyyaml)

## Puesta en marcha

```bash
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1        # PowerShell
# source .venv/Scripts/activate   # bash
pip install -r requirements.txt
```

## Correr el pipeline

```bash
python pipeline/build.py          # o: python -m pipeline.build
```

Lee `data/raw/Datos_prueba_liga.xlsx` y `config/assumptions.yaml`, y escribe los
JSON que consume el sitio en `site/data/`:

| Archivo | Contenido |
|---|---|
| `standings.json` | Tabla publicada, en cancha, oficial y sin doble amarilla |
| `scorers.json` | Goleo correcto, publicado y la explicación de cada diferencia |
| `stats.json` | Goles, resultados, tarjetas, árbitros y pruebas estadísticas |
| `discipline.json` | Disparadores, infracciones, cumplimiento y línea de tiempo |
| `j11.json` | Clasificados, eliminados, en disputa y partidos pendientes |
| `matches.json` | Partidos válidos y excluidos con su motivo |
| `findings_log.json` | Log de hallazgos (regla, registro, valor original y corregido) |
| `meta.json` | Fecha de generación, commit, supuestos usados y conteos |

## Correr las pruebas

```bash
pytest -v
```

Las pruebas de `tests/test_control_values.py` son los **valores de control** de la
sección 8 de `CLAUDE.md`: la tabla oficial J10 fila por fila, los 14 partidos con
alineación indebida con su marcador antes y después del art. 32, el goleo, las
estadísticas y las pruebas de árbitros.

> Si una prueba de control falla, la regla del proyecto es **detenerse y reportar
> la discrepancia**, nunca ajustar el pipeline para forzar el número.

## Cómo está organizado

```
config/assumptions.yaml   Todos los supuestos. El código no hardcodea ninguno.
pipeline/
  load.py                 Lectura cruda y validación de esquema
  clean.py                Reglas R01-R12 y log de hallazgos
  findings.py             Estructura del log de hallazgos
  discipline.py           Suspensiones, cumplimiento y art. 32
  standings.py            Tablas, desempates (art. 18) y clasificación
  scorers.py              Goleo por id_jugador
  stats.py                Estadísticas y pruebas de significancia
  build.py                Orquestación y escritura de JSON
tests/test_control_values.py
```

Dos decisiones que conviene conocer antes de leer el código:

- **Llave de jugador = (equipo, dorsal) → id_jugador.** Nunca se cruza por nombre:
  hay homónimos en equipos distintos. La única excepción es la hoja `Sanciones`,
  que no trae dorsal; ahí se resuelve el nombre *dentro del equipo* y el pipeline
  falla ruidosamente si hubiera ambigüedad.
- **Las reglas detectan por criterio, no por ID.** El código no contiene
  `if id_partido == "P061"`. Los identificadores concretos de `CLAUDE.md` viven
  solo en las pruebas, como guardas de regresión.

## Supuestos

`config/assumptions.yaml` separa las reglas confirmadas por la liga de los
supuestos propios de ingeniería, cada uno con el porqué y si cambia o no algún
resultado. Cambiar una clave y volver a correr el pipeline recalcula todo.

## Fuente de datos actualizable

`load.load_raw(path, source=...)` ya está preparado para recibir una Google Sheet
publicada como CSV sin tocar el resto del pipeline; en esta entrega la fuente es
el Excel y la rama de Google Sheets está declarada pero no implementada.

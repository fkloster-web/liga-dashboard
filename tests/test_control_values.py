"""Pruebas de control (CLAUDE.md sección 8). Si un valor no se reproduce, la regla
del proyecto es DETENERSE y reportar, no ajustar el pipeline para forzarlo."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from pipeline import build, clean, discipline, load, scorers, standings, stats

REPO_ROOT = Path(__file__).resolve().parents[1]
EXCEL_PATH = REPO_ROOT / "data" / "raw" / "Datos_prueba_liga.xlsx"
ASSUMPTIONS_PATH = REPO_ROOT / "config" / "assumptions.yaml"


@pytest.fixture(scope="session")
def assumptions() -> dict:
    with open(ASSUMPTIONS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def raw(assumptions):
    r = load.load_raw(EXCEL_PATH)
    load.validate_schema(r)
    return r


@pytest.fixture(scope="session")
def cleaned(raw, assumptions):
    return clean.clean_all(raw, assumptions)


def assert_close(actual, expected, *, abs_tol: float = 0, label: str = ""):
    assert actual == pytest.approx(expected, abs=abs_tol), (
        f"[{label}] valor de control no reproducido: esperado={expected!r}, "
        f"obtenido={actual!r}. No ajustar el pipeline para forzar este número; "
        f"reportar la discrepancia."
    )


class TestEsquemaCrudo:
    def test_hojas_y_conteos(self):
        raw = load.load_raw(EXCEL_PATH)
        load.validate_schema(raw)
        assert len(raw.teams) == 12
        assert len(raw.players) == 218
        assert len(raw.matches) == 61
        assert len(raw.lineups) == 1652
        assert len(raw.events) == 352
        assert len(raw.sanctions) == 8
        assert len(raw.published_table) == 12
        assert len(raw.published_scorers) == 10


class TestPartidosValidos:
    def test_59_partidos_validos(self, cleaned):
        assert_close(len(cleaned.matches_valid), 59, label="partidos válidos")

    def test_pj_por_equipo(self, cleaned):
        pj_local = cleaned.matches_valid["local"].value_counts()
        pj_visit = cleaned.matches_valid["visitante"].value_counts()
        pj = pj_local.add(pj_visit, fill_value=0).astype(int)
        assert_close(pj["Racing Jardines"], 9, label="PJ Racing Jardines")
        assert_close(pj["Sporting Americana"], 9, label="PJ Sporting Americana")
        otros = pj.drop(["Racing Jardines", "Sporting Americana"])
        assert (otros == 10).all(), f"Equipos con PJ != 10 (se esperaba 10): {otros[otros != 10].to_dict()}"

    def test_cada_equipo_una_vez_por_jornada(self, cleaned):
        for jornada, group in cleaned.matches_valid.groupby("jornada"):
            teams_in_jornada = list(group["local"]) + list(group["visitante"])
            assert len(teams_in_jornada) == len(set(teams_in_jornada)), (
                f"Jornada {jornada} tiene un equipo repetido: {teams_in_jornada}"
            )


def assert_tabla(actual_df, esperado: list[dict], label: str):
    """Compara fila por fila (orden incluido) una tabla de posiciones contra el
    valor de control de CLAUDE.md sección 8."""
    filas = actual_df.to_dict("records")
    assert len(filas) == len(esperado), (
        f"[{label}] se esperaban {len(esperado)} filas, hay {len(filas)}"
    )
    for pos, (fila, exp) in enumerate(zip(filas, esperado), start=1):
        assert fila["equipo"] == exp["equipo"], (
            f"[{label}] posición {pos}: se esperaba {exp['equipo']!r}, "
            f"se obtuvo {fila['equipo']!r}"
        )
        for col in ("pj", "g", "e", "p", "gf", "gc", "dg", "pts"):
            assert_close(
                fila[col], exp[col], label=f"{label} pos {pos} {exp['equipo']} {col.upper()}"
            )


# CLAUDE.md sección 8: "Tabla en cancha (sin art. 32) — escenario de referencia"
TABLA_EN_CANCHA = [
    {"equipo": "Juventud Mezquitán",   "pj": 10, "g": 6, "e": 1, "p": 3, "gf": 19, "gc": 10, "dg": 9,   "pts": 19},
    {"equipo": "Atlético Tlaquepaque", "pj": 10, "g": 5, "e": 3, "p": 2, "gf": 11, "gc": 8,  "dg": 3,   "pts": 18},
    {"equipo": "Unión Zapopan",        "pj": 10, "g": 4, "e": 3, "p": 3, "gf": 13, "gc": 9,  "dg": 4,   "pts": 15},
    {"equipo": "Real Chapalita",       "pj": 10, "g": 3, "e": 6, "p": 1, "gf": 19, "gc": 15, "dg": 4,   "pts": 15},
    {"equipo": "Leones de Tonalá",     "pj": 10, "g": 4, "e": 3, "p": 3, "gf": 13, "gc": 12, "dg": 1,   "pts": 15},
    {"equipo": "Racing Jardines",      "pj": 9,  "g": 4, "e": 2, "p": 3, "gf": 15, "gc": 13, "dg": 2,   "pts": 14},
    {"equipo": "Club Santa Tere",      "pj": 10, "g": 4, "e": 1, "p": 5, "gf": 9,  "gc": 14, "dg": -5,  "pts": 13},
    {"equipo": "Sporting Americana",   "pj": 9,  "g": 3, "e": 4, "p": 2, "gf": 9,  "gc": 9,  "dg": 0,   "pts": 13},
    {"equipo": "Deportivo Oblatos",    "pj": 10, "g": 4, "e": 1, "p": 5, "gf": 14, "gc": 15, "dg": -1,  "pts": 13},
    {"equipo": "Estrella Providencia", "pj": 10, "g": 4, "e": 0, "p": 6, "gf": 15, "gc": 14, "dg": 1,   "pts": 12},
    {"equipo": "Halcones del Country", "pj": 10, "g": 3, "e": 2, "p": 5, "gf": 10, "gc": 15, "dg": -5,  "pts": 11},
    {"equipo": "Tapatíos United",      "pj": 10, "g": 1, "e": 2, "p": 7, "gf": 9,  "gc": 22, "dg": -13, "pts": 5},
]


@pytest.fixture(scope="session")
def tabla_en_cancha(cleaned, assumptions):
    return standings.build_standings(
        cleaned.matches_valid, cleaned.events, [], assumptions, scenario="en_cancha"
    )


class TestTablaEnCancha:
    def test_tabla_completa(self, tabla_en_cancha):
        assert_tabla(tabla_en_cancha, TABLA_EN_CANCHA, "tabla en cancha")

    def test_desempate_15_pts_minitabla(self, tabla_en_cancha):
        """Con art. 18, el orden en cancha a 15 pts es Unión (minitabla 4),
        Chapalita (2), Leones (1)."""
        a_15 = tabla_en_cancha[tabla_en_cancha["pts"] == 15]["equipo"].tolist()
        assert a_15 == ["Unión Zapopan", "Real Chapalita", "Leones de Tonalá"]

    def test_desempate_13_pts(self, tabla_en_cancha):
        """A 13 pts: Santa Tere (minitabla 3), Sporting (1, DG 0), Oblatos (1, DG -1)."""
        a_13 = tabla_en_cancha[tabla_en_cancha["pts"] == 13]["equipo"].tolist()
        assert a_13 == ["Club Santa Tere", "Sporting Americana", "Deportivo Oblatos"]

    def test_criterio_desempate_registrado(self, tabla_en_cancha):
        """Santa Tere se separa por minitabla; Sporting y Oblatos siguen empatados
        en la minitabla (1 pt) y los separa la diferencia de goles."""
        criterio = dict(zip(tabla_en_cancha["equipo"], tabla_en_cancha["criterio_desempate"]))
        assert criterio["Club Santa Tere"] == "head_to_head_or_minitable"
        assert criterio["Sporting Americana"] == "goal_diff"
        assert criterio["Deportivo Oblatos"] == "goal_diff"
        assert criterio["Juventud Mezquitán"] is None, "el líder no estuvo empatado en puntos"

    def test_ningun_sorteo_requerido(self, tabla_en_cancha):
        con_sorteo = tabla_en_cancha[tabla_en_cancha["requiere_sorteo"]]["equipo"].tolist()
        assert con_sorteo == [], f"El art. 18 debería resolver todos los empates: {con_sorteo}"


# CLAUDE.md sección 8: empate en 2° a 3 goles (10 jugadores), por id_jugador
EMPATADOS_A_3_GOLES = {
    "J038", "J054", "J171", "J179", "J117", "J168", "J093", "J027", "J188", "J147",
}


@pytest.fixture(scope="session")
def goleo(cleaned, assumptions):
    return scorers.build_scorers_table(cleaned.events, cleaned.players, assumptions)


class TestGoleo:
    def test_lider_de_goleo(self, goleo):
        lider = goleo.iloc[0]
        assert lider["id_jugador"] == "J205", f"se esperaba J205, se obtuvo {lider['id_jugador']}"
        assert lider["nombre"] == "Víctor Navarro Morales"
        assert lider["equipo"] == "Racing Jardines"
        assert_close(lider["goles"], 4, label="goles del líder de goleo")
        assert_close(lider["posicion"], 1, label="posición del líder")

    def test_empate_en_segundo_a_3_goles(self, goleo):
        segundos = goleo[goleo["posicion"] == 2]
        assert_close(len(segundos), 10, label="jugadores empatados en 2° lugar")
        assert set(segundos["id_jugador"]) == EMPATADOS_A_3_GOLES
        assert (segundos["goles"] == 3).all()

    def test_homonimo_jc_perez_chapalita_con_2_goles(self, goleo):
        """J040 (Chapalita) y J147 (Tapatíos) son personas distintas: 2 y 3 goles,
        nunca 5 sumados."""
        j040 = goleo[goleo["id_jugador"] == "J040"].iloc[0]
        j147 = goleo[goleo["id_jugador"] == "J147"].iloc[0]
        assert_close(j040["goles"], 2, label="goles JC Pérez Ruiz J040 (Chapalita)")
        assert_close(j147["goles"], 3, label="goles JC Pérez Ruiz J147 (Tapatíos)")

    def test_autogoles(self, cleaned):
        assert_close(scorers.count_own_goals(cleaned.events), 7, label="autogoles")

    def test_gol_sin_autor(self, cleaned):
        sin_autor = scorers.goals_without_author(cleaned.matches_valid, cleaned.events)
        assert_close(
            int(sin_autor["goles_sin_autor"].sum()), 1, label="goles sin autor"
        )
        fila = sin_autor.iloc[0]
        assert fila["id_partido"] == "P011"
        assert fila["equipo"] == "Estrella Providencia"


@pytest.fixture(scope="session")
def comparacion(goleo, raw, cleaned):
    return scorers.compare_vs_published(goleo, raw.published_scorers, cleaned.events)


class TestGoleoPublicado:
    def test_tres_errores_detectados(self, comparacion):
        errores = comparacion[comparacion["tipo"] != "coincide"]
        assert_close(len(errores), 3, label="errores en el goleo publicado")

    def test_error_agrupacion_por_nombre(self, comparacion):
        fila = comparacion[comparacion["jugador"] == "Juan Carlos Pérez Ruiz"].iloc[0]
        assert_close(fila["goles_publicado"], 5, label="JC Pérez publicado")
        assert_close(fila["goles_correcto"], 3, label="JC Pérez correcto (J147)")
        assert "agrupa por nombre" in fila["motivo"]

    def test_error_autogol_contado(self, comparacion):
        fila = comparacion[comparacion["jugador"] == "Andrés Ruiz Rojas"].iloc[0]
        assert_close(fila["goles_publicado"], 4, label="Andrés Ruiz publicado")
        assert_close(fila["goles_correcto"], 3, label="Andrés Ruiz correcto")
        assert "autogol" in fila["motivo"]

    def test_error_omision(self, comparacion):
        omitidos = comparacion[comparacion["tipo"] == "omitido"]
        assert_close(len(omitidos), 1, label="jugadores omitidos del goleo publicado")
        fila = omitidos.iloc[0]
        assert fila["jugador"] == "Iván Cruz García"
        assert fila["id_jugador"] == "J093"
        assert_close(fila["goles_correcto"], 3, label="goles de Iván Cruz García")


# CLAUDE.md sección 8: tabla de árbitros con TARJETAS CRUDAS (pre-R08)
ARBITROS_CRUDOS = {
    "A. Núñez":  {"partidos": 16, "tarjetas": 43, "por_partido": 2.69},
    "B. Salas":  {"partidos": 9,  "tarjetas": 33, "por_partido": 3.67},
    "C. Pineda": {"partidos": 10, "tarjetas": 29, "por_partido": 2.90},
    "D. Villa":  {"partidos": 13, "tarjetas": 55, "por_partido": 4.23},
    "E. Ríos":   {"partidos": 11, "tarjetas": 37, "por_partido": 3.36},
}


class TestEstadisticasGenerales:
    def test_goles_por_partido(self, cleaned, assumptions):
        g = stats.compute_general_stats(cleaned.matches_valid, assumptions)
        assert_close(g["goles"], 156, label="goles totales")
        assert_close(g["partidos"], 59, label="partidos")
        assert_close(g["goles_por_partido"], 2.644, abs_tol=0.005, label="goles por partido")

    def test_reparto_de_resultados(self, cleaned, assumptions):
        r = stats.compute_general_stats(cleaned.matches_valid, assumptions)["resultados"]
        assert_close(r["local"]["partidos"], 24, label="victorias locales")
        assert_close(r["empate"]["partidos"], 14, label="empates")
        assert_close(r["visitante"]["partidos"], 21, label="victorias visitantes")
        assert_close(r["local"]["pct"], 40.7, abs_tol=0.05, label="% local")
        assert_close(r["empate"]["pct"], 23.7, abs_tol=0.05, label="% empate")
        assert_close(r["visitante"]["pct"], 35.6, abs_tol=0.05, label="% visitante")

    def test_desbalance_de_localia(self, cleaned):
        """El calendario está desbalanceado: por eso el % local no concluye ventaja."""
        ha = stats.compute_home_away_raw(cleaned.matches_valid).set_index("equipo")
        assert_close(ha.loc["Real Chapalita", "como_local"], 10, label="Chapalita como local")
        assert_close(ha.loc["Real Chapalita", "como_visitante"], 0, label="Chapalita como visitante")
        assert_close(ha.loc["Atlético Tlaquepaque", "como_local"], 0, label="Tlaquepaque como local")
        assert_close(ha.loc["Atlético Tlaquepaque", "como_visitante"], 10, label="Tlaquepaque como visitante")


class TestTarjetas:
    @staticmethod
    def _stats(raw, cleaned):
        return stats.compute_cards_stats(raw.events, cleaned.events, cleaned.matches_valid)

    def test_totales_crudas_y_post_r08(self, raw, cleaned):
        c = self._stats(raw, cleaned)
        assert_close(c["amarillas_crudas"], 189, label="amarillas crudas")
        assert_close(c["rojas_crudas"], 8, label="rojas crudas")
        assert_close(c["total_crudas"], 197, label="tarjetas crudas")
        assert_close(c["total_post_r08"], 196, label="tarjetas tras R08")

    def test_por_partido(self, raw, cleaned):
        c = self._stats(raw, cleaned)
        assert_close(c["por_partido_crudas"], 3.34, abs_tol=0.005, label="tarjetas/partido crudas")
        assert_close(c["por_partido_post_r08"], 3.32, abs_tol=0.005, label="tarjetas/partido tras R08")

    def test_expulsiones_por_doble_amarilla(self, raw, cleaned):
        c = self._stats(raw, cleaned)
        assert_close(c["expulsiones_doble_amarilla"], 10, label="expulsiones por doble amarilla")


@pytest.fixture(scope="session")
def tabla_arbitros(raw, cleaned):
    return stats.compute_referee_stats(raw.events, cleaned.matches_valid).set_index("arbitro")


@pytest.fixture(scope="session")
def prueba_arbitros(raw, cleaned, assumptions):
    return stats.run_referee_significance(raw.events, cleaned.matches_valid, assumptions)


class TestArbitros:
    """Los valores de control de la sección 8 son sobre TARJETAS CRUDAS, así que
    estas pruebas usan raw.events. El resultado sobre datos limpios se calcula
    aparte en build.py (la conclusión no cambia)."""

    def test_cinco_arbitros(self, tabla_arbitros):
        assert set(tabla_arbitros.index) == set(ARBITROS_CRUDOS)

    def test_tabla_por_arbitro(self, tabla_arbitros):
        for arbitro, esperado in ARBITROS_CRUDOS.items():
            assert_close(tabla_arbitros.loc[arbitro, "partidos"], esperado["partidos"],
                         label=f"partidos de {arbitro}")
            assert_close(tabla_arbitros.loc[arbitro, "tarjetas"], esperado["tarjetas"],
                         label=f"tarjetas de {arbitro}")
            assert_close(tabla_arbitros.loc[arbitro, "por_partido"], esperado["por_partido"],
                         abs_tol=0.005, label=f"tarjetas por partido de {arbitro}")

    def test_partidos_suman_59(self, tabla_arbitros):
        assert_close(int(tabla_arbitros["partidos"].sum()), 59,
                     label="partidos arbitrados en total")

    def test_kruskal_wallis(self, prueba_arbitros):
        assert_close(prueba_arbitros["kruskal"]["pvalue"], 0.13, abs_tol=0.02,
                     label="Kruskal-Wallis p (datos crudos)")

    def test_mann_whitney_villa_vs_resto(self, prueba_arbitros):
        mw = prueba_arbitros["mannwhitney"]
        assert mw["arbitro"] == "D. Villa", (
            f"el árbitro con más tarjetas por partido debería ser D. Villa, "
            f"se obtuvo {mw['arbitro']}"
        )
        assert_close(mw["pvalue"], 0.035, abs_tol=0.02, label="Mann-Whitney p sin corregir")
        assert_close(mw["pvalue_bonferroni"], 0.17, abs_tol=0.02, label="Mann-Whitney p Bonferroni")

    def test_no_significativo_tras_correccion(self, prueba_arbitros):
        assert prueba_arbitros["significativo"] is False
        assert "No hay evidencia suficiente" in prueba_arbitros["interpretacion"]


# CLAUDE.md sección 8: "Partidos con alineación indebida (14) -> resultado oficial por art. 32"
CASOS_ART32 = [
    {"id_partido": "P010", "jornada": 2,  "en_cancha": (2, 2), "oficial": (0, 3),
     "infractor": "Real Chapalita",       "jugadores": {"Emilio Ruiz Medina"}},
    {"id_partido": "P014", "jornada": 3,  "en_cancha": (3, 2), "oficial": (0, 3),
     "infractor": "Tapatíos United",      "jugadores": {"Ricardo Reyes González"}},
    {"id_partido": "P026", "jornada": 5,  "en_cancha": (1, 0), "oficial": (0, 3),
     "infractor": "Estrella Providencia", "jugadores": {"Víctor Gutiérrez Ruiz"}},
    {"id_partido": "P031", "jornada": 6,  "en_cancha": (0, 1), "oficial": (0, 3),
     "infractor": "Estrella Providencia", "jugadores": {"Héctor Gutiérrez Ramírez"}},
    {"id_partido": "P032", "jornada": 6,  "en_cancha": (2, 1), "oficial": (3, 0),
     "infractor": "Leones de Tonalá",     "jugadores": {"Óscar Díaz López"}},
    {"id_partido": "P036", "jornada": 6,  "en_cancha": (2, 2), "oficial": (3, 0),
     "infractor": "Atlético Tlaquepaque", "jugadores": {"Ricardo Cruz Castillo"}},
    {"id_partido": "P039", "jornada": 7,  "en_cancha": (1, 0), "oficial": (0, 3),
     "infractor": "Halcones del Country", "jugadores": {"Daniel Rojas Mendoza"}},
    {"id_partido": "P044", "jornada": 8,  "en_cancha": (2, 0), "oficial": (3, 0),
     "infractor": "Club Santa Tere",
     "jugadores": {"Rodrigo Anaya Lozano", "Héctor Reyes Lozano"}},
    {"id_partido": "P045", "jornada": 8,  "en_cancha": (3, 2), "oficial": (0, 3),
     "infractor": "Real Chapalita",       "jugadores": {"Óscar Aguilar García"}},
    {"id_partido": "P049", "jornada": 9,  "en_cancha": (1, 2), "oficial": (0, 3),
     "infractor": "Deportivo Oblatos",    "jugadores": {"Óscar Torres Ramírez"}},
    {"id_partido": "P051", "jornada": 9,  "en_cancha": (1, 0), "oficial": (0, 3),
     "infractor": "Leones de Tonalá",     "jugadores": {"Fernando Medina González"}},
    {"id_partido": "P053", "jornada": 9,  "en_cancha": (1, 1), "oficial": (0, 3),
     "infractor": "Halcones del Country", "jugadores": {"Luis Ibarra Ibarra"}},
    {"id_partido": "P058", "jornada": 10, "en_cancha": (0, 0), "oficial": (3, 0),
     "infractor": "Sporting Americana",   "jugadores": {"Raúl Reyes Chávez"}},
    {"id_partido": "P059", "jornada": 10, "en_cancha": (1, 0), "oficial": (0, 3),
     "infractor": "Juventud Mezquitán",   "jugadores": {"Kevin Alonso Ibarra Soto"}},
]

# CLAUDE.md sección 8: escenario alternativo (art. 32 sin doble amarilla)
PARTIDOS_SIN_DOBLE_AMARILLA = {"P032", "P036", "P039", "P044", "P058", "P059"}


@pytest.fixture(scope="session")
def schedule(cleaned):
    """Calendario completo (válidos + excluidos), como lo usa discipline.py para
    poder saltar explícitamente los partidos suspendidos."""
    return pd.concat([cleaned.matches_valid, cleaned.matches_excluded], ignore_index=True)


@pytest.fixture(scope="session")
def disciplina(cleaned, schedule, assumptions):
    triggers = discipline.detect_all_triggers(cleaned.events, schedule, assumptions)
    violaciones, cumplimiento = discipline.check_lineup_violations(
        triggers, schedule, cleaned.lineups, assumptions
    )
    violaciones = violaciones + discipline.detect_registration_violations(
        cleaned.lineups, schedule
    )
    overrides = discipline.build_forfeit_overrides(violaciones)
    return {
        "triggers": triggers,
        "violaciones": violaciones,
        "cumplimiento": cumplimiento,
        "overrides": overrides,
        "resumen": discipline.discipline_summary(
            triggers, cumplimiento, violaciones, cleaned.matches_valid
        ),
    }


class TestDisciplinaDisparadores:
    def test_19_eventos_que_generan_suspension(self, disciplina):
        assert_close(len(disciplina["triggers"]), 19, label="eventos que generan suspensión")

    def test_desglose_por_tipo(self, disciplina):
        por_tipo = disciplina["resumen"]["triggers_por_tipo"]
        assert_close(por_tipo["red_direct"], 8, label="rojas directas")
        assert_close(por_tipo["double_yellow"], 10, label="dobles amarillas")
        assert_close(por_tipo["accumulation"], 1, label="acumulación de 5 amarillas")

    def test_caso_de_acumulacion(self, disciplina):
        """El único caso de acumulación no está en la hoja Sanciones: se calcula
        de Eventos y su 5a amarilla cae en J7, después del cierre de registro."""
        acum = [t for t in disciplina["triggers"] if t.trigger_type == "accumulation"]
        assert len(acum) == 1
        t = acum[0]
        assert t.nombre == "Rodrigo Anaya Lozano"
        assert t.equipo == "Club Santa Tere"
        assert t.origin_match == "P039"
        assert_close(t.jornada_origin, 7, label="jornada de la 5a amarilla")


class TestArt32Casos:
    def test_catorce_partidos_afectados(self, disciplina):
        assert_close(len(disciplina["overrides"]), 14, label="partidos con alineación indebida")
        assert {o.id_partido for o in disciplina["overrides"]} == {
            c["id_partido"] for c in CASOS_ART32
        }

    def test_quince_casos_en_catorce_partidos(self, disciplina):
        assert_close(len(disciplina["violaciones"]), 15, label="casos de alineación indebida")

    def test_infractor_y_jugadores_por_partido(self, disciplina):
        por_partido: dict[str, list] = {}
        for v in disciplina["violaciones"]:
            por_partido.setdefault(v.id_partido, []).append(v)
        for caso in CASOS_ART32:
            vs = por_partido[caso["id_partido"]]
            equipos = {v.equipo for v in vs}
            assert equipos == {caso["infractor"]}, (
                f"{caso['id_partido']}: infractor esperado {caso['infractor']!r}, "
                f"se obtuvo {equipos}"
            )
            assert {v.nombre for v in vs} == caso["jugadores"], (
                f"{caso['id_partido']}: jugadores infractores distintos a los esperados"
            )

    def test_marcadores_en_cancha_y_oficiales(self, cleaned, disciplina, assumptions):
        base = standings.compute_field_scores(cleaned.matches_valid).set_index("id_partido")
        oficial = standings.apply_forfeit_overrides(
            standings.compute_field_scores(cleaned.matches_valid),
            disciplina["overrides"], assumptions,
        ).set_index("id_partido")
        for caso in CASOS_ART32:
            p = caso["id_partido"]
            en_cancha = (int(base.at[p, "goles_local"]), int(base.at[p, "goles_visitante"]))
            aplicado = (int(oficial.at[p, "goles_local"]), int(oficial.at[p, "goles_visitante"]))
            assert en_cancha == caso["en_cancha"], f"{p}: marcador en cancha"
            assert aplicado == caso["oficial"], f"{p}: marcador oficial tras art. 32"

    def test_ningun_partido_con_infractores_de_ambos_equipos(self, disciplina):
        por_partido: dict[str, set] = {}
        for v in disciplina["violaciones"]:
            por_partido.setdefault(v.id_partido, set()).add(v.equipo)
        multiples = {p: e for p, e in por_partido.items() if len(e) > 1}
        assert multiples == {}, f"Partidos con infractores de ambos equipos: {multiples}"

    def test_p044_dos_infractores_un_solo_forfeit(self, disciplina):
        """Dos infractores del mismo equipo producen UN forfeit, y el conjunto de
        tipos conserva la acumulación para que el escenario sin doble amarilla
        no lo descarte."""
        p044 = [o for o in disciplina["overrides"] if o.id_partido == "P044"]
        assert len(p044) == 1
        assert p044[0].trigger_types == frozenset({"accumulation", "double_yellow"})
        assert p044[0].solo_por_doble_amarilla is False

    def test_subconjunto_sin_doble_amarilla(self, disciplina):
        sobreviven = {
            o.id_partido for o in disciplina["overrides"] if not o.solo_por_doble_amarilla
        }
        assert sobreviven == PARTIDOS_SIN_DOBLE_AMARILLA


class TestDisciplinaCumplimiento:
    def test_cumplidas_y_no_cumplidas(self, disciplina):
        r = disciplina["resumen"]
        assert_close(r["cumplidas_a_tiempo"], 5, label="suspensiones cumplidas a tiempo")
        assert_close(r["no_cumplidas"], 14, label="suspensiones no cumplidas")
        assert_close(r["pendientes"], 0, label="suspensiones pendientes")
        assert_close(r["pct_no_cumplidas"], 73.7, abs_tol=0.05, label="% no cumplidas")

    def test_rojas(self, disciplina):
        r = disciplina["resumen"]
        assert_close(r["rojas_total"], 8, label="rojas directas")
        assert_close(r["rojas_no_cumplidas"], 4, label="rojas no cumplidas")
        assert_close(r["pct_rojas_no_cumplidas"], 50.0, abs_tol=0.05, label="% rojas no cumplidas")

    def test_cumplidas_son_las_cuatro_rojas_de_j1_a_j3_y_una_doble_amarilla(self, disciplina):
        cumplidas = disciplina["cumplimiento"].query("estado == 'cumplida'")
        rojas = cumplidas[cumplidas["trigger_type"] == "red_direct"]
        assert_close(len(rojas), 4, label="rojas cumplidas a tiempo")
        assert set(rojas["jornada_origen"]) <= {1, 2, 3}, "las rojas cumplidas son de J1-J3"
        dobles = cumplidas[cumplidas["trigger_type"] == "double_yellow"]
        assert_close(len(dobles), 1, label="dobles amarillas cumplidas a tiempo")
        assert dobles.iloc[0]["nombre"] == "Arturo López Martínez"

    def test_alta_fuera_de_plazo_y_cobertura(self, disciplina):
        r = disciplina["resumen"]
        assert_close(r["alta_fuera_de_plazo"], 1, label="altas fuera de plazo")
        assert_close(r["casos_alineacion_indebida"], 15, label="casos totales")
        assert_close(r["partidos_afectados"], 14, label="partidos afectados")
        assert_close(r["partidos_jugados"], 59, label="partidos jugados")
        assert_close(r["pct_partidos_afectados"], 23.7, abs_tol=0.05,
                     label="% de partidos con alineación indebida")

    def test_motivo_de_la_violacion_por_registro(self, disciplina):
        registro = [v for v in disciplina["violaciones"] if v.trigger_type == "registration"]
        assert len(registro) == 1
        assert registro[0].nombre == "Kevin Alonso Ibarra Soto"
        assert "alta posterior al cierre de registro" in registro[0].motivo


# CLAUDE.md sección 8: "Tabla oficial J10 (reglas confirmadas) — valor de control principal"
TABLA_OFICIAL_J10 = [
    {"equipo": "Atlético Tlaquepaque", "pj": 10, "g": 6, "e": 2, "p": 2, "gf": 12, "gc": 8,  "dg": 4,   "pts": 20},
    {"equipo": "Sporting Americana",   "pj": 9,  "g": 5, "e": 2, "p": 2, "gf": 12, "gc": 8,  "dg": 4,   "pts": 17},
    {"equipo": "Club Santa Tere",      "pj": 10, "g": 5, "e": 1, "p": 4, "gf": 13, "gc": 13, "dg": 0,   "pts": 16},
    {"equipo": "Juventud Mezquitán",   "pj": 10, "g": 5, "e": 1, "p": 4, "gf": 18, "gc": 13, "dg": 5,   "pts": 16},
    {"equipo": "Racing Jardines",      "pj": 9,  "g": 5, "e": 1, "p": 3, "gf": 16, "gc": 11, "dg": 5,   "pts": 16},
    {"equipo": "Estrella Providencia", "pj": 10, "g": 5, "e": 0, "p": 5, "gf": 18, "gc": 15, "dg": 3,   "pts": 15},
    {"equipo": "Unión Zapopan",        "pj": 10, "g": 4, "e": 3, "p": 3, "gf": 13, "gc": 9,  "dg": 4,   "pts": 15},
    {"equipo": "Leones de Tonalá",     "pj": 10, "g": 4, "e": 2, "p": 4, "gf": 15, "gc": 16, "dg": -1,  "pts": 14},
    {"equipo": "Deportivo Oblatos",    "pj": 10, "g": 4, "e": 1, "p": 5, "gf": 15, "gc": 16, "dg": -1,  "pts": 13},
    {"equipo": "Real Chapalita",       "pj": 10, "g": 2, "e": 5, "p": 3, "gf": 14, "gc": 17, "dg": -3,  "pts": 11},
    {"equipo": "Halcones del Country", "pj": 10, "g": 3, "e": 0, "p": 7, "gf": 10, "gc": 17, "dg": -7,  "pts": 9},
    {"equipo": "Tapatíos United",      "pj": 10, "g": 1, "e": 2, "p": 7, "gf": 9,  "gc": 22, "dg": -13, "pts": 5},
]

# CLAUDE.md sección 8: escenario alternativo (art. 32 sin doble amarilla), solo puntos
PUNTOS_SIN_DOBLE_AMARILLA = [
    ("Leones de Tonalá", 17), ("Atlético Tlaquepaque", 17), ("Club Santa Tere", 16),
    ("Juventud Mezquitán", 16), ("Racing Jardines", 16), ("Real Chapalita", 15),
    ("Estrella Providencia", 15), ("Unión Zapopan", 15), ("Deportivo Oblatos", 13),
    ("Sporting Americana", 12), ("Halcones del Country", 8), ("Tapatíos United", 5),
]

# CLAUDE.md sección 8: "Diferencias publicada − en cancha"
DIFERENCIAS_PUBLICADA = {
    "Juventud Mezquitán":   {"pj": 1, "g": 1, "gf": 1, "dg": 1, "pts": 3},
    "Halcones del Country": {"pj": 1, "p": 1, "gc": 1, "dg": -1},
    "Racing Jardines":      {"pj": 1, "e": 1, "pts": 1},
    "Sporting Americana":   {"pj": 1, "e": 1, "pts": 1},
    "Unión Zapopan":        {"gc": 2},
}


@pytest.fixture(scope="session")
def escenarios(cleaned, disciplina, assumptions):
    return standings.build_standings_scenarios(
        cleaned.matches_valid, cleaned.events, disciplina["overrides"], assumptions
    )


class TestTablaOficialJ10:
    def test_tabla_completa(self, escenarios):
        assert_tabla(escenarios["oficial"], TABLA_OFICIAL_J10, "tabla oficial J10")

    def test_minitabla_a_16_puntos(self, escenarios, cleaned, disciplina, assumptions):
        """Santa Tere 6, Juventud 3, Racing 0 en los partidos entre ellos
        (P008, P029, P034)."""
        scores = standings.apply_forfeit_overrides(
            standings.compute_field_scores(cleaned.matches_valid),
            disciplina["overrides"], assumptions,
        )
        grupo = ["Club Santa Tere", "Juventud Mezquitán", "Racing Jardines"]
        mini = standings.minitable_points(grupo, scores)
        assert_close(mini["Club Santa Tere"], 6, label="minitabla Santa Tere")
        assert_close(mini["Juventud Mezquitán"], 3, label="minitabla Juventud")
        assert_close(mini["Racing Jardines"], 0, label="minitabla Racing")

    def test_orden_a_16_puntos(self, escenarios):
        a_16 = escenarios["oficial"].query("pts == 16")["equipo"].tolist()
        assert a_16 == ["Club Santa Tere", "Juventud Mezquitán", "Racing Jardines"]

    def test_orden_a_15_puntos_por_head_to_head(self, escenarios):
        """Estrella le ganó a Unión en P038 (4-2), así que va por delante."""
        a_15 = escenarios["oficial"].query("pts == 15")["equipo"].tolist()
        assert a_15 == ["Estrella Providencia", "Unión Zapopan"]

    def test_criterios_de_desempate_registrados(self, escenarios):
        criterio = dict(zip(escenarios["oficial"]["equipo"], escenarios["oficial"]["criterio_desempate"]))
        for equipo in ("Club Santa Tere", "Juventud Mezquitán", "Racing Jardines",
                       "Estrella Providencia", "Unión Zapopan"):
            assert criterio[equipo] == "head_to_head_or_minitable", (
                f"{equipo} debería resolverse por minitabla/head-to-head"
            )
        assert criterio["Atlético Tlaquepaque"] is None
        assert not escenarios["oficial"]["requiere_sorteo"].any()


class TestImpactoVsPublicada:
    def test_diferencias_publicada_vs_en_cancha(self, raw, tabla_en_cancha):
        publicada = raw.published_table.set_index("Equipo")
        cancha = tabla_en_cancha.set_index("equipo")
        columnas = {"pj": "PJ", "g": "G", "e": "E", "p": "P",
                    "gf": "GF", "gc": "GC", "dg": "DG", "pts": "Pts"}
        for equipo in cancha.index:
            esperado = DIFERENCIAS_PUBLICADA.get(equipo, {})
            for col, col_pub in columnas.items():
                delta = int(publicada.at[equipo, col_pub]) - int(cancha.at[equipo, col])
                assert_close(delta, esperado.get(col, 0),
                             label=f"diferencia publicada-cancha de {equipo} en {col.upper()}")

    def test_publicada_es_internamente_inconsistente(self, raw):
        """Prueba interna: en la publicada ΣGF != ΣGC, lo que es imposible."""
        publicada = raw.published_table
        assert_close(int(publicada["GF"].sum()), 157, label="ΣGF publicada")
        assert_close(int(publicada["GC"].sum()), 159, label="ΣGC publicada")
        assert int(publicada["GF"].sum()) != int(publicada["GC"].sum())

    def test_cambio_de_liguilla(self, escenarios, raw):
        oficial = escenarios["oficial"]
        top8_oficial = set(oficial.head(8)["equipo"])
        top8_publicada = set(raw.published_table.head(8)["Equipo"])
        assert top8_oficial - top8_publicada == {"Club Santa Tere", "Estrella Providencia"}
        assert top8_publicada - top8_oficial == {"Real Chapalita", "Deportivo Oblatos"}

    def test_cambio_de_lider(self, escenarios, raw):
        assert raw.published_table.iloc[0]["Equipo"] == "Juventud Mezquitán"
        assert escenarios["oficial"].iloc[0]["equipo"] == "Atlético Tlaquepaque"

    def test_chapalita_cae_de_3_a_10(self, escenarios, raw):
        publicada = raw.published_table.set_index("Equipo")
        oficial = escenarios["oficial"].set_index("equipo")
        assert_close(publicada.at["Real Chapalita", "Pos"], 3, label="posición publicada de Chapalita")
        assert_close(oficial.at["Real Chapalita", "posicion"], 10, label="posición oficial de Chapalita")


class TestEscenarioSinDobleAmarilla:
    def test_puntos_por_equipo(self, escenarios):
        tabla = escenarios["sin_doble_amarilla"]
        obtenido = list(zip(tabla["equipo"], tabla["pts"]))
        for (equipo_esp, pts_esp), (equipo_obt, pts_obt) in zip(PUNTOS_SIN_DOBLE_AMARILLA, obtenido):
            assert equipo_obt == equipo_esp, (
                f"orden distinto: se esperaba {equipo_esp!r}, se obtuvo {equipo_obt!r}"
            )
            assert_close(pts_obt, pts_esp, label=f"puntos de {equipo_esp} sin doble amarilla")

    def test_la_regla_decide_quien_entra_a_liguilla(self, escenarios):
        """Con doble amarilla entra Sporting (2°); sin ella, entra Chapalita y
        Sporting cae al 10°."""
        oficial = escenarios["oficial"].set_index("equipo")
        sin_da = escenarios["sin_doble_amarilla"].set_index("equipo")
        assert oficial.at["Sporting Americana", "posicion"] <= 8
        assert oficial.at["Real Chapalita", "posicion"] > 8
        assert sin_da.at["Sporting Americana", "posicion"] > 8
        assert sin_da.at["Real Chapalita", "posicion"] <= 8


class TestClasificacionJ11:
    @staticmethod
    def _clasificar(cleaned, escenarios):
        pendientes = standings.derive_pending_fixtures(
            cleaned.matches_valid, cleaned.matches_excluded, set(cleaned.teams["equipo"])
        )
        partidos = standings.pending_matches_as_pairs(cleaned.matches_excluded, pendientes)
        return pendientes, partidos, standings.classify_j11(escenarios["oficial"], partidos)

    def test_seis_pares_de_j11_derivados(self, cleaned, escenarios):
        pendientes, _, _ = self._clasificar(cleaned, escenarios)
        assert_close(len(pendientes), 6, label="emparejamientos de J11")
        assert {frozenset(p) for p in pendientes} == {
            frozenset({"Juventud Mezquitán", "Unión Zapopan"}),
            frozenset({"Club Santa Tere", "Sporting Americana"}),
            frozenset({"Real Chapalita", "Racing Jardines"}),
            frozenset({"Tapatíos United", "Leones de Tonalá"}),
            frozenset({"Halcones del Country", "Estrella Providencia"}),
            frozenset({"Deportivo Oblatos", "Atlético Tlaquepaque"}),
        }

    def test_siete_partidos_pendientes_con_p042(self, cleaned, escenarios):
        _, partidos, _ = self._clasificar(cleaned, escenarios)
        assert_close(len(partidos), 7, label="partidos pendientes (J11 + P042)")
        assert frozenset({"Racing Jardines", "Sporting Americana"}) in {
            frozenset(p) for p in partidos
        }

    def test_clasificados_eliminados_y_en_disputa(self, cleaned, escenarios):
        _, _, c = self._clasificar(cleaned, escenarios)
        assert set(c["clasificados"]) == {"Atlético Tlaquepaque", "Sporting Americana"}
        assert set(c["eliminados"]) == {"Halcones del Country", "Tapatíos United"}
        assert_close(len(c["en_disputa"]), 8, label="equipos en disputa")

    def test_chapalita_sigue_vivo_solo_con_empates_a_su_favor(self, cleaned, escenarios):
        """Chapalita llega como mucho a 14, que es justo lo que Leones ya tiene
        asegurado: depende de un empate en puntos resuelto a su favor."""
        _, _, c = self._clasificar(cleaned, escenarios)
        assert "Real Chapalita" in c["en_disputa"]
        assert_close(c["puntos_max"]["Real Chapalita"], 14, label="máximo de Chapalita")
        assert_close(c["puntos_min"]["Leones de Tonalá"], 14, label="mínimo de Leones")
        assert_close(c["mejor_posicion"]["Real Chapalita"], 8, label="mejor posición de Chapalita")

    def test_escenarios_evaluados(self, cleaned, escenarios):
        _, _, c = self._clasificar(cleaned, escenarios)
        assert_close(c["escenarios_evaluados"], 3 ** 7, label="escenarios enumerados")


class TestArt32RamaKeepWorse:
    """La rama 'keep_worse' del art. 32 no la activa ningún caso real (ningún
    infractor perdió por más de 3 goles), así que se prueba de forma sintética
    y aislada, sin pasar por el pipeline completo."""

    def test_ningun_caso_real_conserva_el_marcador_en_cancha(self, disciplina, cleaned, assumptions):
        base = standings.compute_field_scores(cleaned.matches_valid).set_index("id_partido")
        for o in disciplina["overrides"]:
            fila = base.loc[o.id_partido]
            gl, gv = int(fila["goles_local"]), int(fila["goles_visitante"])
            es_local = o.infractor_team == fila["local"]
            deficit = (gv - gl) if es_local else (gl - gv)
            assert deficit <= assumptions["art32_keep_worse_threshold_goals"], (
                f"{o.id_partido}: el infractor perdía por {deficit}, debería conservarse "
                f"el marcador en cancha y ningún caso de control lo hace"
            )

    def test_se_conserva_el_marcador_si_el_deficit_supera_el_umbral(self, assumptions):
        assert standings.resolve_art32_score((0, 5), True, assumptions) == (0, 5)
        assert standings.resolve_art32_score((5, 0), False, assumptions) == (5, 0)

    def test_se_aplica_el_forfeit_si_el_deficit_no_supera_el_umbral(self, assumptions):
        assert standings.resolve_art32_score((2, 2), True, assumptions) == (0, 3)
        assert standings.resolve_art32_score((2, 2), False, assumptions) == (3, 0)
        assert standings.resolve_art32_score((5, 0), True, assumptions) == (0, 3)

    def test_frontera_exacta_del_umbral(self, assumptions):
        """Déficit de exactamente 3 todavía se convierte en 0-3; 4 ya se conserva."""
        assert standings.resolve_art32_score((0, 3), True, assumptions) == (0, 3)
        assert standings.resolve_art32_score((0, 4), True, assumptions) == (0, 4)


class TestSiguientePartidoDisputado:
    """El filtro que salta partidos suspendidos tampoco tiene caso real (ningún
    disparador de Racing o Sporting nace en J6, que es la jornada de P042), así
    que se prueba con un calendario sintético."""

    @staticmethod
    def _calendario():
        return pd.DataFrame([
            {"id_partido": "X01", "jornada": 1, "local": "A", "visitante": "B",
             "estatus": "Jugado", "fecha_parsed": pd.Timestamp("2026-07-11")},
            {"id_partido": "X02", "jornada": 2, "local": "A", "visitante": "C",
             "estatus": "Suspendido", "fecha_parsed": pd.Timestamp("2026-07-18")},
            {"id_partido": "X03", "jornada": 3, "local": "D", "visitante": "A",
             "estatus": "Jugado", "fecha_parsed": pd.Timestamp("2026-07-25")},
        ])

    def test_salta_el_partido_suspendido(self, assumptions):
        siguiente = discipline.find_next_match_played("A", 1, self._calendario(), assumptions)
        assert siguiente is not None
        assert siguiente["id_partido"] == "X03", (
            "la suspensión debe cumplirse en el siguiente partido DISPUTADO, no en el suspendido"
        )

    def test_sin_partido_posterior_devuelve_none(self, assumptions):
        assert discipline.find_next_match_played("A", 3, self._calendario(), assumptions) is None

    def test_descarta_partidos_sin_fecha(self, assumptions):
        calendario = self._calendario()
        calendario.loc[calendario["id_partido"] == "X03", "fecha_parsed"] = pd.NaT
        assert discipline.find_next_match_played("A", 1, calendario, assumptions) is None


@pytest.fixture(scope="session")
def resultado():
    """Pipeline completo por la vía real de orquestación (build.compute_all)."""
    return build.compute_all(EXCEL_PATH, ASSUMPTIONS_PATH)


class TestPipelineCompleto:
    def test_compute_all_reproduce_los_valores_principales(self, resultado):
        assert_close(len(resultado.cleaned.matches_valid), 59, label="partidos válidos")
        assert_tabla(resultado.standings["oficial"], TABLA_OFICIAL_J10, "tabla oficial (build)")
        assert_close(resultado.discipline_summary["casos_alineacion_indebida"], 15,
                     label="casos de alineación indebida (build)")
        assert_close(resultado.own_goals, 7, label="autogoles (build)")

    def test_log_de_hallazgos_consolidado(self, resultado):
        reglas = set(resultado.findings["rule_id"])
        for regla in ("R01", "R02", "R03", "R04", "R06", "R07", "R08",
                      "R09", "R10", "R11", "R12", "ART32", "GOLEO_PUBLICADO"):
            assert regla in reglas, f"el log consolidado no incluye hallazgos de {regla}"
        assert_close(int((resultado.findings["rule_id"] == "ART32").sum()), 15,
                     label="hallazgos de art. 32")

    def test_timeline_muestra_notificaciones_tardias(self, resultado):
        """Las 4 rojas incumplidas son las notificadas DESPUÉS del partido que
        debían impedir: es la evidencia del cuello de botella del proceso."""
        tl = resultado.timeline
        tardias = tl[tl["notificado_antes_del_partido"] == False]  # noqa: E712
        assert_close(len(tardias), 4, label="sanciones notificadas tarde")
        assert set(tardias["trigger_type"]) == {"red_direct"}
        assert (tardias["estado"] == "no_cumplida").all()

    def test_escribe_los_json_esperados(self, resultado, tmp_path):
        escritos = build.write_outputs(resultado, tmp_path)
        nombres = {p.name for p in escritos}
        assert nombres == {
            "standings.json", "scorers.json", "stats.json", "discipline.json",
            "j11.json", "matches.json", "findings_log.json", "meta.json",
        }

    def test_los_json_son_estrictamente_validos(self, resultado, tmp_path):
        def rechaza_no_json(constante):
            raise AssertionError(f"valor no serializable en JSON: {constante}")

        for destino in build.write_outputs(resultado, tmp_path):
            json.loads(destino.read_text(encoding="utf-8"), parse_constant=rechaza_no_json)

    def test_contrato_de_standings(self, resultado, tmp_path):
        build.write_outputs(resultado, tmp_path)
        datos = json.loads((tmp_path / "standings.json").read_text(encoding="utf-8"))
        assert set(datos) == {"publicada", "en_cancha", "oficial", "sin_doble_amarilla"}
        fila = datos["oficial"][0]
        for columna in ("posicion", "equipo", "pj", "g", "e", "p", "gf", "gc", "dg", "pts",
                        "criterio_desempate", "requiere_sorteo"):
            assert columna in fila, f"falta la columna {columna} en standings.oficial"
        assert fila["equipo"] == "Atlético Tlaquepaque"

    def test_meta_documenta_los_supuestos(self, resultado, tmp_path):
        build.write_outputs(resultado, tmp_path)
        meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
        assert meta["supuestos"]["suspension_scope"] == "next_match_only"
        assert meta["supuestos"]["double_yellow_is_red"] is True
        assert_close(meta["conteos"]["partidos_validos"], 59, label="meta partidos válidos")


class TestCasosConocidosRegresion:
    def test_p061_deduplicado(self, cleaned):
        assert "P061" not in set(cleaned.matches_valid["id_partido"])
        dedup_findings = cleaned.findings[cleaned.findings["rule_id"] == "R03"]
        assert "P061" in set(dedup_findings["record_id"])

    def test_p042_excluido(self, cleaned):
        assert "P042" not in set(cleaned.matches_valid["id_partido"])
        assert "P042" in set(cleaned.matches_excluded["id_partido"])

    def test_p040_evento_duplicado_removido(self, cleaned):
        oscar_amarillas = cleaned.events[
            (cleaned.events["id_partido"] == "P040")
            & (cleaned.events["dorsal"] == 25)
            & (cleaned.events["equipo"] == "Real Chapalita")
            & (cleaned.events["evento"] == "Amarilla")
        ]
        assert_close(len(oscar_amarillas), 2, label="amarillas Óscar Aguilar García P040 tras R08")
        assert set(oscar_amarillas["minuto"]) == {65, 85}

    def test_p053_evento_post_roja_registrado_no_borrado(self, cleaned):
        raul = cleaned.events[
            (cleaned.events["id_partido"] == "P053")
            & (cleaned.events["dorsal"] == 16)
            & (cleaned.events["equipo"] == "Sporting Americana")
        ]
        assert_close(len(raul), 2, label="eventos Raúl Reyes Chávez P053 (roja + amarilla)")
        amarilla_row = raul[raul["evento"] == "Amarilla"].iloc[0]
        assert amarilla_row["is_after_red"] == True  # noqa: E712

    def test_kevin_alonso_j218_elegibilidad(self, cleaned):
        row = cleaned.lineups[
            (cleaned.lineups["id_partido"] == "P059")
            & (cleaned.lineups["equipo"] == "Juventud Mezquitán")
            & (cleaned.lineups["dorsal"] == 3)
        ].iloc[0]
        assert row["is_ineligible_registration"] == True  # noqa: E712

    def test_falso_positivo_homonimo_jc_perez_no_fusionado(self, cleaned):
        ids = set(cleaned.players[cleaned.players["nombre"] == "Juan Carlos Pérez Ruiz"]["id_jugador"])
        assert ids == {"J040", "J147"}

    def test_falso_positivo_traspaso_ruben_flores_no_marcado(self, cleaned):
        ineligible = cleaned.lineups[cleaned.lineups["is_ineligible_registration"]]
        traspaso_ids = set(
            cleaned.players[cleaned.players["nombre"] == "Rubén Flores Ortiz"]["id_jugador"]
        )
        flagged_traspaso = ineligible[ineligible["id_jugador"].isin(traspaso_ids)]
        assert len(flagged_traspaso) == 0, "El traspaso dentro de plazo no debe marcarse como inelegible"

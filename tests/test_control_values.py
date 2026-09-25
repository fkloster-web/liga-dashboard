"""Pruebas de control (CLAUDE.md sección 8). Si un valor no se reproduce, la regla
del proyecto es DETENERSE y reportar, no ajustar el pipeline para forzarlo."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipeline import clean, load, scorers, standings

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

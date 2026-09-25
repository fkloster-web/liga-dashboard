"""Goleo individual, agregado por id_jugador (nunca por nombre: hay homónimos).

Deriva de la MISMA tabla de eventos que standings.py, pero sin los overrides de
art. 32: por regla confirmada (art32_goals_count_for_scorers=true) los goles
anotados en un partido sancionado sí cuentan para el goleo individual, aunque
el marcador de equipo se modifique.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from pipeline.findings import Finding, FindingsLog


def build_scorers_table(events: pd.DataFrame, players: pd.DataFrame, assumptions: dict) -> pd.DataFrame:
    """Goleo correcto: solo eventos 'Gol' (los autogoles no cuentan para el
    goleo individual, R06), agrupados por id_jugador."""
    if assumptions["scorers_tie_policy"] != "shared_rank":
        raise ValueError(
            f"scorers_tie_policy no soportada: {assumptions['scorers_tie_policy']!r}"
        )

    goles = events[events["evento"] == "Gol"]
    counts = goles.groupby("id_jugador").size().rename("goles").reset_index()

    info = players[["id_jugador", "nombre", "equipo"]]
    df = counts.merge(info, on="id_jugador", how="left")
    df = df.sort_values(["goles", "nombre"], ascending=[False, True]).reset_index(drop=True)
    # shared_rank: los empatados comparten lugar (1, 2, 2, ..., 12)
    df["posicion"] = df["goles"].rank(method="min", ascending=False).astype(int)
    return df[["posicion", "id_jugador", "nombre", "equipo", "goles"]]


def count_own_goals(events: pd.DataFrame) -> int:
    return int((events["evento"] == "Autogol").sum())


def goals_without_author(matches_valid: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Goles del marcador oficial que ningún evento atribuye a un jugador
    (cédula ilegible). El marcador oficial manda, el gol queda sin autor y
    fuera del goleo."""
    goal_events = events[events["evento"].isin(["Gol", "Autogol"])]
    counts = goal_events.groupby(["id_partido", "equipo_acreditado"]).size()
    filas = []
    for _, row in matches_valid.iterrows():
        id_p = row["id_partido"]
        for equipo, oficial in (
            (row["local"], int(row["goles_local"])),
            (row["visitante"], int(row["goles_visitante"])),
        ):
            en_eventos = int(counts.get((id_p, equipo), 0))
            if oficial > en_eventos:
                filas.append({
                    "id_partido": id_p,
                    "equipo": equipo,
                    "goles_oficiales": oficial,
                    "goles_con_autor": en_eventos,
                    "goles_sin_autor": oficial - en_eventos,
                })
    return pd.DataFrame(filas, columns=[
        "id_partido", "equipo", "goles_oficiales", "goles_con_autor", "goles_sin_autor"
    ])


def compare_vs_published(
    scorers_correct: pd.DataFrame,
    published_scorers: pd.DataFrame,
    events: pd.DataFrame,
    findings: Optional[FindingsLog] = None,
) -> pd.DataFrame:
    """Explica cada diferencia entre el goleo publicado y el correcto:
    agrupación por nombre (homónimos), inclusión de autogoles y omisiones."""
    autogoles_por_jugador = (
        events[events["evento"] == "Autogol"].groupby("id_jugador").size().to_dict()
    )
    por_nombre: dict[str, pd.DataFrame] = {
        nombre: grupo for nombre, grupo in scorers_correct.groupby("nombre")
    }

    filas = []
    for _, pub in published_scorers.iterrows():
        nombre, equipo_pub, goles_pub = pub["Jugador"], pub["Equipo"], int(pub["Goles"])
        candidatos = por_nombre.get(nombre, pd.DataFrame(columns=scorers_correct.columns))
        del_equipo = candidatos[candidatos["equipo"] == equipo_pub]
        goles_correcto = int(del_equipo["goles"].iloc[0]) if len(del_equipo) else 0
        id_jugador = del_equipo["id_jugador"].iloc[0] if len(del_equipo) else None

        motivos = []
        if len(candidatos) > 1 and goles_pub == int(candidatos["goles"].sum()):
            otros = candidatos[candidatos["equipo"] != equipo_pub]
            motivos.append(
                "agrupa por nombre: suma los goles de homónimos de "
                + ", ".join(f"{r.equipo} ({r.goles})" for r in otros.itertuples())
                + f" al jugador de {equipo_pub}"
            )
        autogoles = autogoles_por_jugador.get(id_jugador, 0) if id_jugador else 0
        if autogoles and goles_pub == goles_correcto + autogoles:
            motivos.append(f"cuenta {autogoles} autogol(es) como gol a favor")
        if not motivos and goles_pub != goles_correcto:
            motivos.append("diferencia no explicada por homónimos ni autogoles")

        filas.append({
            "jugador": nombre,
            "equipo_publicado": equipo_pub,
            "id_jugador": id_jugador,
            "goles_publicado": goles_pub,
            "goles_correcto": goles_correcto,
            "diferencia": goles_pub - goles_correcto,
            "tipo": "discrepancia" if motivos else "coincide",
            "motivo": "; ".join(motivos) if motivos else None,
        })

    # Omisiones: jugadores que por goles deberían aparecer en la lista publicada.
    corte_publicado = int(published_scorers["Goles"].min())
    publicados = {(r["Jugador"], r["Equipo"]) for _, r in published_scorers.iterrows()}
    for r in scorers_correct.itertuples():
        if r.goles >= corte_publicado and (r.nombre, r.equipo) not in publicados:
            filas.append({
                "jugador": r.nombre,
                "equipo_publicado": None,
                "id_jugador": r.id_jugador,
                "goles_publicado": 0,
                "goles_correcto": int(r.goles),
                "diferencia": -int(r.goles),
                "tipo": "omitido",
                "motivo": (
                    f"omitido del goleo publicado pese a tener {r.goles} goles "
                    f"(corte de la lista publicada: {corte_publicado})"
                ),
            })

    df = pd.DataFrame(filas)
    if findings is not None:
        equipo_real = scorers_correct.set_index("id_jugador")["equipo"]
        for r in df[df["tipo"] != "coincide"].itertuples():
            # Un omitido no tiene equipo publicado (pandas lo vuelve NaN, que es
            # truthy): se usa el equipo real del jugador, buscado por id_jugador.
            equipo = r.equipo_publicado if pd.notna(r.equipo_publicado) else equipo_real.get(r.id_jugador)
            findings.add(Finding(
                rule_id="GOLEO_PUBLICADO", sheet="Goleo_publicado",
                record_id=f"{r.jugador} ({equipo})" if equipo else r.jugador,
                field="Goles",
                original_value=str(r.goles_publicado),
                corrected_value=str(r.goles_correcto),
                action="documented_no_action", severity="warning",
                note=r.motivo,
            ))
    return df

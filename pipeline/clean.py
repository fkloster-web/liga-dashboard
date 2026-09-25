"""Reglas de limpieza R01-R12 (CLAUDE.md sección 5).

Orden de ejecución (ver plan): R02 -> R01 -> R03 -> R04 -> R05 -> R06 -> R08 -> R07
-> R09 -> R10 -> R11 -> R12. Cada función detecta por CRITERIO GENERAL (llaves,
fechas, minutos, estatus) — nunca por ID de partido/jugador hardcodeado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from pipeline.findings import Finding, FindingsLog
from pipeline.load import RawData

TEAM_NAME_MAP: dict[str, str] = {
    "Oblatos": "Deportivo Oblatos",
    "Dvo. Oblatos": "Deportivo Oblatos",
    "Atl. Tlaquepaque": "Atlético Tlaquepaque",
    "Halcones Country": "Halcones del Country",
    "Leones Tonalá": "Leones de Tonalá",
    "Santa Tere FC": "Club Santa Tere",
}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


@dataclass
class CleanedData:
    teams: pd.DataFrame
    players: pd.DataFrame
    matches_valid: pd.DataFrame
    matches_excluded: pd.DataFrame
    lineups: pd.DataFrame
    events: pd.DataFrame
    sanctions: pd.DataFrame
    findings: pd.DataFrame


def r02_parse_dates(matches: pd.DataFrame, findings: FindingsLog) -> pd.DataFrame:
    """Parsea fechas mixtas aaaa-mm-dd / dd/mm/aaaa por patrón explícito (nunca
    dayfirst global). Valida que cada jornada tenga una sola fecha."""
    matches = matches.copy()
    parsed: list[pd.Timestamp] = []
    for _, row in matches.iterrows():
        raw = row["fecha"]
        s = str(raw).strip()
        if _ISO_DATE_RE.match(s):
            date = pd.Timestamp(s)
        elif _DMY_DATE_RE.match(s):
            d, m, y = s.split("/")
            date = pd.Timestamp(year=int(y), month=int(m), day=int(d))
            findings.add(Finding(
                rule_id="R02", sheet="Partidos", record_id=str(row["id_partido"]),
                field="fecha", original_value=s, corrected_value=date.strftime("%Y-%m-%d"),
                action="corrected", severity="info",
                note="Fecha en formato dd/mm/aaaa normalizada por patrón explícito.",
            ))
        else:
            raise ValueError(f"[{row['id_partido']}] formato de fecha no reconocido: {raw!r}")
        parsed.append(date)
    matches["fecha_parsed"] = parsed

    by_jornada = matches.groupby("jornada")["fecha_parsed"].nunique()
    bad = by_jornada[by_jornada > 1]
    if len(bad) > 0:
        raise ValueError(f"Jornadas con más de una fecha tras parsear: {bad.to_dict()}")
    return matches


def r01_normalize_teams(
    matches: pd.DataFrame, canonical_teams: set[str], findings: FindingsLog
) -> pd.DataFrame:
    """Normaliza nombres de equipo en Partidos.local/visitante contra las 12
    canónicas de Equipos."""
    matches = matches.copy()
    for col in ("local", "visitante"):
        original = matches[col].copy()
        normalized = original.map(lambda v: TEAM_NAME_MAP.get(v, v))
        changed = original != normalized
        for idx in matches.index[changed]:
            findings.add(Finding(
                rule_id="R01", sheet="Partidos", record_id=str(matches.at[idx, "id_partido"]),
                field=col, original_value=original.at[idx], corrected_value=normalized.at[idx],
                action="corrected", severity="info",
                note="Nombre de equipo normalizado al canónico de la hoja Equipos.",
            ))
        matches[col] = normalized
        unknown = set(matches[col]) - canonical_teams
        if unknown:
            raise ValueError(f"Equipos no reconocidos tras normalizar columna {col}: {unknown}")
    return matches


def r03_dedup_matches(matches: pd.DataFrame, findings: FindingsLog) -> pd.DataFrame:
    """Elimina partidos duplicados: mismo jornada + local + visitante."""
    matches = matches.copy()
    key = (
        matches["jornada"].astype(str) + "|" + matches["local"] + "|" + matches["visitante"]
    )
    is_dup = key.duplicated(keep="first")
    for idx in matches.index[is_dup]:
        findings.add(Finding(
            rule_id="R03", sheet="Partidos", record_id=str(matches.at[idx, "id_partido"]),
            field=None, original_value=None, corrected_value=None,
            action="deduplicated", severity="warning",
            note="Partido duplicado exacto (misma jornada+local+visitante); excluido del conteo.",
        ))
    return matches[~is_dup].reset_index(drop=True)


def r04_exclude_unplayed(
    matches: pd.DataFrame, findings: FindingsLog
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Excluye partidos con estatus distinto de 'Jugado' (ej. Suspendido)."""
    is_unplayed = matches["estatus"] != "Jugado"
    excluded = matches[is_unplayed].copy()
    for _, row in excluded.iterrows():
        findings.add(Finding(
            rule_id="R04", sheet="Partidos", record_id=str(row["id_partido"]),
            field="estatus", original_value=str(row["estatus"]), corrected_value=None,
            action="excluded", severity="warning",
            note="Partido no jugado; su marcador capturado no es válido. Pendiente de reprogramación.",
        ))
    valid = matches[~is_unplayed].reset_index(drop=True)
    return valid, excluded.reset_index(drop=True)


def r04_filter_child_records(
    lineups: pd.DataFrame,
    events: pd.DataFrame,
    matches_valid: pd.DataFrame,
    findings: FindingsLog,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Descarta alineaciones y eventos de partidos que no son válidos (duplicados
    por R03 o no jugados por R04): si el partido no cuenta, sus registros hijos
    tampoco. Con los datos actuales no descarta ninguna fila, pero evita que una
    fuente futura (Google Sheets) cuele goles o tarjetas de partidos anulados."""
    validos = set(matches_valid["id_partido"])
    resultado = []
    for df, sheet in ((lineups, "Alineaciones"), (events, "Eventos")):
        sobran = ~df["id_partido"].isin(validos)
        for idx in df.index[sobran]:
            row = df.loc[idx]
            findings.add(Finding(
                rule_id="R04", sheet=sheet,
                record_id=f"{row['id_partido']}:{row['equipo']}#{row['dorsal']}",
                field="id_partido", original_value=str(row["id_partido"]),
                corrected_value=None,
                action="excluded", severity="warning",
                note="Registro de un partido no válido (duplicado o no jugado); excluido.",
            ))
        resultado.append(df[~sobran].reset_index(drop=True))
    return resultado[0], resultado[1]


def r05_build_player_key(
    players: pd.DataFrame, lineups: pd.DataFrame, events: pd.DataFrame, findings: FindingsLog
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Llave de jugador = (equipo, dorsal) -> id_jugador. Nunca por nombre."""
    key_to_id = {(row.equipo, row.dorsal): row.id_jugador for row in players.itertuples()}

    def attach(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
        df = df.copy()
        ids = []
        for _, row in df.iterrows():
            id_j = key_to_id.get((row["equipo"], row["dorsal"]))
            if id_j is None:
                findings.add(Finding(
                    rule_id="R05", sheet=sheet_name,
                    record_id=f"{row.get('id_partido', '?')}:{row['equipo']}#{row['dorsal']}",
                    field="dorsal", original_value=str(row["dorsal"]), corrected_value=None,
                    action="flagged", severity="critical",
                    note="No se encontró id_jugador para (equipo, dorsal) en Jugadores.",
                ))
            ids.append(id_j)
        df["id_jugador"] = ids
        return df

    lineups2 = attach(lineups, "Alineaciones")
    events2 = attach(events, "Eventos")
    missing = int(lineups2["id_jugador"].isna().sum() + events2["id_jugador"].isna().sum())
    if missing:
        raise ValueError(
            f"{missing} registros de Alineaciones/Eventos no cruzaron con Jugadores "
            f"por (equipo, dorsal); se esperaba 100% de cruce (R05)."
        )
    return players, lineups2, events2


def r06_reassign_own_goals(
    events: pd.DataFrame, matches: pd.DataFrame, findings: FindingsLog
) -> pd.DataFrame:
    """Autogol: el gol se acredita al rival del equipo del jugador; no cuenta
    para goleo individual."""
    events = events.copy()
    match_teams = {row.id_partido: (row.local, row.visitante) for row in matches.itertuples()}
    credited_team: list[str] = []
    is_own_goal: list[bool] = []
    for _, row in events.iterrows():
        if row["evento"] == "Autogol":
            local, visitante = match_teams.get(row["id_partido"], (None, None))
            rival = visitante if row["equipo"] == local else local
            credited_team.append(rival)
            is_own_goal.append(True)
            findings.add(Finding(
                rule_id="R06", sheet="Eventos",
                record_id=f"{row['id_partido']}:{row['equipo']}#{row['dorsal']}@{row['minuto']}",
                field="equipo_acreditado", original_value=row["equipo"], corrected_value=rival,
                action="corrected", severity="info",
                note="Autogol: gol acreditado al rival; no cuenta para goleo individual.",
            ))
        else:
            credited_team.append(row["equipo"])
            is_own_goal.append(False)
    events["equipo_acreditado"] = credited_team
    events["is_own_goal"] = is_own_goal
    return events


def r08_dedup_events(events: pd.DataFrame, findings: FindingsLog) -> pd.DataFrame:
    """Elimina eventos duplicados: mismo partido, jugador, minuto y tipo de evento."""
    events = events.copy()
    key_cols = ["id_partido", "equipo", "dorsal", "minuto", "evento"]
    is_dup = events.duplicated(subset=key_cols, keep="first")
    for idx in events.index[is_dup]:
        row = events.loc[idx]
        findings.add(Finding(
            rule_id="R08", sheet="Eventos",
            record_id=f"{row['id_partido']}:{row['equipo']}#{row['dorsal']}@{row['minuto']}",
            field="evento", original_value=str(row["evento"]), corrected_value=None,
            action="deduplicated", severity="warning",
            note="Evento duplicado (mismo partido, jugador, minuto y tipo); se conserva una sola ocurrencia.",
        ))
    return events[~is_dup].reset_index(drop=True)


def r07_reconcile_score(
    matches_valid: pd.DataFrame, events: pd.DataFrame, findings: FindingsLog
) -> pd.DataFrame:
    """El marcador oficial de la cédula manda; se registran discrepancias contra
    el conteo de goles en Eventos, sin modificar el marcador."""
    goal_events = events[events["evento"].isin(["Gol", "Autogol"])]
    counts = goal_events.groupby(["id_partido", "equipo_acreditado"]).size()
    for _, row in matches_valid.iterrows():
        id_p = row["id_partido"]
        gl_events = counts.get((id_p, row["local"]), 0)
        gv_events = counts.get((id_p, row["visitante"]), 0)
        if gl_events != row["goles_local"] or gv_events != row["goles_visitante"]:
            findings.add(Finding(
                rule_id="R07", sheet="Partidos", record_id=str(id_p),
                field="goles_local/goles_visitante",
                original_value=f"eventos={gl_events}-{gv_events}",
                corrected_value=f"marcador_oficial={row['goles_local']}-{row['goles_visitante']}",
                action="documented_no_action", severity="warning",
                note="Discrepancia entre marcador oficial (cédula) y conteo de goles en Eventos; el marcador oficial manda.",
            ))
    return matches_valid


def r09_flag_impossible_events(events: pd.DataFrame, findings: FindingsLog) -> pd.DataFrame:
    """Marca eventos de un jugador posteriores a su propia roja en el mismo
    partido. Se registra; no se elimina sin supuesto adicional."""
    events = events.copy()
    is_after_red = pd.Series(False, index=events.index)
    red_times: dict[tuple, int] = {}
    for idx, row in events[events["evento"] == "Roja"].iterrows():
        red_times[(row["id_partido"], row["equipo"], row["dorsal"])] = row["minuto"]
    for idx, row in events.iterrows():
        key = (row["id_partido"], row["equipo"], row["dorsal"])
        if key in red_times and row["evento"] != "Roja" and row["minuto"] > red_times[key]:
            is_after_red.at[idx] = True
            findings.add(Finding(
                rule_id="R09", sheet="Eventos",
                record_id=f"{row['id_partido']}:{row['equipo']}#{row['dorsal']}@{row['minuto']}",
                field="evento", original_value=str(row["evento"]), corrected_value=None,
                action="flagged", severity="warning",
                note="Evento posterior a la expulsión (roja) del mismo jugador en el mismo partido; error de captura probable.",
            ))
    events["is_after_red"] = is_after_red
    return events


def r10_flag_double_yellow(events: pd.DataFrame, findings: FindingsLog) -> pd.DataFrame:
    """Detecta >=2 amarillas del mismo jugador en un mismo partido (post R08)."""
    events = events.copy()
    is_second_yellow = pd.Series(False, index=events.index)
    yellow_events = events[events["evento"] == "Amarilla"].sort_values(
        ["id_partido", "equipo", "dorsal", "minuto"]
    )
    for _, group in yellow_events.groupby(["id_partido", "equipo", "dorsal"]):
        if len(group) >= 2:
            second_idx = group.index[1]
            is_second_yellow.at[second_idx] = True
            row = events.loc[second_idx]
            findings.add(Finding(
                rule_id="R10", sheet="Eventos",
                record_id=f"{row['id_partido']}:{row['equipo']}#{row['dorsal']}@{row['minuto']}",
                field="evento", original_value="Amarilla", corrected_value="Expulsión (doble amarilla)",
                action="flagged", severity="warning",
                note="Doble amarilla en el mismo partido; por supuesto double_yellow_is_red=true equivale a expulsión.",
            ))
    events["is_second_yellow"] = is_second_yellow
    return events


def r11_check_registration_eligibility(
    lineups: pd.DataFrame,
    players: pd.DataFrame,
    matches_valid: pd.DataFrame,
    assumptions: dict,
    findings: FindingsLog,
) -> pd.DataFrame:
    """Elegibilidad por registro: alineado con fecha_alta posterior al cierre de
    registro, o fuera de [fecha_alta, fecha_baja]."""
    lineups = lineups.copy()
    match_date = {row.id_partido: row.fecha_parsed for row in matches_valid.itertuples()}
    player_window = {row.id_jugador: (row.fecha_alta, row.fecha_baja) for row in players.itertuples()}
    registration_close = pd.Timestamp(assumptions["registration_close"])
    is_ineligible = pd.Series(False, index=lineups.index)
    for idx, row in lineups.iterrows():
        id_j = row["id_jugador"]
        if id_j not in player_window:
            continue
        alta, baja = player_window[id_j]
        fecha_partido = match_date.get(row["id_partido"])
        if fecha_partido is None:
            continue
        alta_ts = pd.Timestamp(alta) if pd.notna(alta) else None
        baja_ts = pd.Timestamp(baja) if pd.notna(baja) else None
        out_of_window = (alta_ts is not None and fecha_partido < alta_ts) or (
            baja_ts is not None and fecha_partido > baja_ts
        )
        alta_fuera_de_plazo = alta_ts is not None and alta_ts > registration_close
        eligible_window_but_late_registration = (
            alta_fuera_de_plazo and not out_of_window and fecha_partido >= alta_ts
        )
        if out_of_window or eligible_window_but_late_registration:
            is_ineligible.at[idx] = True
            motivo = (
                "alta posterior al cierre de registro"
                if eligible_window_but_late_registration
                else "fuera de ventana [fecha_alta, fecha_baja]"
            )
            findings.add(Finding(
                rule_id="R11", sheet="Alineaciones",
                record_id=f"{row['id_partido']}:{row['equipo']}#{row['dorsal']}",
                field="id_jugador", original_value=str(id_j), corrected_value=None,
                action="flagged", severity="critical",
                note=f"Jugador alineado sin elegibilidad de registro ({motivo}).",
            ))
    lineups["is_ineligible_registration"] = is_ineligible
    return lineups


def r12_flag_post_cutoff(
    sanctions: pd.DataFrame, assumptions: dict, findings: FindingsLog
) -> pd.DataFrame:
    """Marca (sin excluir) registros de Sanciones posteriores al corte de datos."""
    sanctions = sanctions.copy()
    cutoff = pd.Timestamp(assumptions["cutoff_date"])
    is_post_cutoff = pd.to_datetime(sanctions["fecha_sesion"]) > cutoff
    for idx in sanctions.index[is_post_cutoff]:
        row = sanctions.loc[idx]
        findings.add(Finding(
            rule_id="R12", sheet="Sanciones", record_id=f"{row['jugador']}@{row['fecha_sesion']}",
            field="fecha_sesion", original_value=str(row["fecha_sesion"]), corrected_value=None,
            action="flagged", severity="info",
            note="Registro posterior al corte de datos (cutoff_date); se conserva pero se marca.",
        ))
    sanctions["is_post_cutoff"] = is_post_cutoff
    return sanctions


def clean_all(raw: RawData, assumptions: dict) -> CleanedData:
    findings = FindingsLog()
    canonical_teams = set(raw.teams["equipo"])

    matches = r02_parse_dates(raw.matches, findings)
    matches = r01_normalize_teams(matches, canonical_teams, findings)
    matches = r03_dedup_matches(matches, findings)
    matches_valid, matches_excluded = r04_exclude_unplayed(matches, findings)

    lineups_validos, events_validos = r04_filter_child_records(
        raw.lineups, raw.events, matches_valid, findings
    )
    players, lineups, events = r05_build_player_key(
        raw.players, lineups_validos, events_validos, findings
    )
    events = r06_reassign_own_goals(events, matches, findings)
    events = r08_dedup_events(events, findings)
    matches_valid = r07_reconcile_score(matches_valid, events, findings)
    events = r09_flag_impossible_events(events, findings)
    events = r10_flag_double_yellow(events, findings)

    lineups = r11_check_registration_eligibility(lineups, players, matches_valid, assumptions, findings)
    sanctions = r12_flag_post_cutoff(raw.sanctions, assumptions, findings)

    return CleanedData(
        teams=raw.teams,
        players=players,
        matches_valid=matches_valid,
        matches_excluded=matches_excluded,
        lineups=lineups,
        events=events,
        sanctions=sanctions,
        findings=findings.to_dataframe(),
    )

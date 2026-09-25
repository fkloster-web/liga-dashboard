"""Tablas de posiciones: un solo constructor parametrizado por una lista de
overrides de forfeit (art. 32), reutilizado para los 3 escenarios (oficial,
en cancha, sin doble amarilla). Desempates según art. 18 y clasificación J11."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Callable, Literal, Optional

import pandas as pd

from pipeline.findings import Finding, FindingsLog

TriggerType = Literal["red_direct", "double_yellow", "accumulation", "registration"]

# Límite de seguridad para la enumeración exacta de escenarios (3^n).
MAX_ENUMERABLE_MATCHES = 12


@dataclass(frozen=True)
class ForfeitOverride:
    """Un forfeit por partido y equipo infractor (single_forfeit_not_cumulative).

    Guarda el CONJUNTO de tipos de infracción porque un mismo equipo puede tener
    varios infractores en el mismo partido por vías distintas (P044: Rodrigo Anaya
    Lozano por acumulación de 5 amarillas y Héctor Reyes Lozano por doble amarilla).
    """

    id_partido: str
    infractor_team: str
    trigger_types: frozenset[TriggerType]

    @property
    def solo_por_doble_amarilla(self) -> bool:
        """El forfeit desaparece al quitar la regla de doble amarilla solo si
        TODOS sus infractores lo son por esa vía."""
        return self.trigger_types == {"double_yellow"}


def compute_field_scores(matches_valid: pd.DataFrame) -> pd.DataFrame:
    """Marcador en cancha (post R07, sin art.32): la tabla 'en cancha' de referencia."""
    return matches_valid[
        ["id_partido", "jornada", "local", "visitante", "goles_local", "goles_visitante"]
    ].copy()


def resolve_art32_score(
    real_score: tuple[int, int], infractor_is_local: bool, assumptions: dict
) -> tuple[int, int]:
    """art32_sanction=forfeit_3_0_keep_worse: 3-0/0-3 contra el infractor, salvo
    que su déficit real en cancha sea mayor al umbral (se conserva el real)."""
    threshold = assumptions["art32_keep_worse_threshold_goals"]
    gl, gv = real_score
    deficit = (gv - gl) if infractor_is_local else (gl - gv)
    if deficit > threshold:
        return real_score
    return (0, 3) if infractor_is_local else (3, 0)


def apply_forfeit_overrides(
    field_scores: pd.DataFrame, overrides: list[ForfeitOverride], assumptions: dict
) -> pd.DataFrame:
    """Idempotente por (id_partido, equipo): single_forfeit_not_cumulative.
    Invariante: nunca ambos equipos infractores en el mismo partido."""
    scores = field_scores.set_index("id_partido")
    by_match: dict[str, set[str]] = {}
    for o in overrides:
        by_match.setdefault(o.id_partido, set()).add(o.infractor_team)

    for id_p, teams in by_match.items():
        row = scores.loc[id_p]
        local, visitante = row["local"], row["visitante"]
        if local in teams and visitante in teams:
            raise ValueError(
                f"Invariante violado: ambos equipos son infractores de art.32 en {id_p}"
            )
        infractor_team = next(iter(teams))
        infractor_is_local = infractor_team == local
        real_score = (int(row["goles_local"]), int(row["goles_visitante"]))
        new_gl, new_gv = resolve_art32_score(real_score, infractor_is_local, assumptions)
        scores.at[id_p, "goles_local"] = new_gl
        scores.at[id_p, "goles_visitante"] = new_gv

    return scores.reset_index()


def build_points_table(scores: pd.DataFrame) -> pd.DataFrame:
    teams = sorted(set(scores["local"]) | set(scores["visitante"]))
    stats = {t: {"pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0} for t in teams}
    for _, row in scores.iterrows():
        local, visitante = row["local"], row["visitante"]
        gl, gv = int(row["goles_local"]), int(row["goles_visitante"])
        stats[local]["pj"] += 1
        stats[visitante]["pj"] += 1
        stats[local]["gf"] += gl
        stats[local]["gc"] += gv
        stats[visitante]["gf"] += gv
        stats[visitante]["gc"] += gl
        if gl > gv:
            stats[local]["g"] += 1
            stats[visitante]["p"] += 1
        elif gl < gv:
            stats[visitante]["g"] += 1
            stats[local]["p"] += 1
        else:
            stats[local]["e"] += 1
            stats[visitante]["e"] += 1
    df = pd.DataFrame([{"equipo": t, **s} for t, s in stats.items()])
    df["dg"] = df["gf"] - df["gc"]
    df["pts"] = df["g"] * 3 + df["e"]
    return df


def _group_by_key(teams: list[str], key_fn: Callable[[str], float]) -> list[list[str]]:
    """Agrupa por valor de key_fn descendente (mayor = mejor), preservando empates."""
    sorted_teams = sorted(teams, key=key_fn, reverse=True)
    groups: list[list[str]] = []
    for t in sorted_teams:
        if groups and key_fn(groups[-1][0]) == key_fn(t):
            groups[-1].append(t)
        else:
            groups.append([t])
    return groups


def minitable_points(group: list[str], scores: pd.DataFrame) -> dict[str, int]:
    """Puntos de la minitabla entre los equipos empatados (art. 18, pasos 1-2).
    Público porque el sitio debe poder mostrar el desempate explicado."""
    sub = scores[scores["local"].isin(group) & scores["visitante"].isin(group)]
    pts = {t: 0 for t in group}
    for _, row in sub.iterrows():
        l, v = row["local"], row["visitante"]
        gl, gv = int(row["goles_local"]), int(row["goles_visitante"])
        if gl > gv:
            pts[l] += 3
        elif gl < gv:
            pts[v] += 3
        else:
            pts[l] += 1
            pts[v] += 1
    return pts


def _flag_sorteo(
    group: list[str],
    info: dict[str, dict],
    scenario: str,
    findings: Optional[FindingsLog],
) -> None:
    """Un empate que llega al último criterio (sorteo) NO se ordena en silencio:
    se marca en la tabla y se registra en el log de hallazgos."""
    for t in group:
        info[t]["requiere_sorteo"] = True
        info[t]["criterio_desempate"] = "sorteo"
    if findings is not None:
        findings.add(Finding(
            rule_id="ART18", sheet="Tabla_calculada",
            record_id=f"{scenario}:{'|'.join(sorted(group))}",
            field="posicion", original_value=None, corrected_value=None,
            action="flagged", severity="warning",
            note=(
                f"Empate no resuelto por los criterios del art. 18 entre "
                f"{', '.join(sorted(group))} (escenario {scenario}); el reglamento "
                f"lo define por sorteo. El orden mostrado es provisional (alfabético)."
            ),
        ))


def _rank_group(
    group: list[str],
    scores: pd.DataFrame,
    table: pd.DataFrame,
    red_counts: dict[str, int],
    criteria_queue: list[str],
    info: dict[str, dict],
    scenario: str,
    findings: Optional[FindingsLog],
) -> list[str]:
    if len(group) <= 1:
        return list(group)
    if not criteria_queue:
        _flag_sorteo(group, info, scenario, findings)
        return sorted(group)

    criterion, *rest = criteria_queue

    if criterion == "head_to_head_or_minitable":
        mini_pts = minitable_points(group, scores)
        subgroups = _group_by_key(group, lambda t: mini_pts[t])
    elif criterion == "goal_diff":
        dg = dict(zip(table["equipo"], table["dg"]))
        subgroups = _group_by_key(group, lambda t: dg[t])
    elif criterion == "goals_for":
        gf = dict(zip(table["equipo"], table["gf"]))
        subgroups = _group_by_key(group, lambda t: gf[t])
    elif criterion == "fewer_reds":
        subgroups = _group_by_key(group, lambda t: -red_counts.get(t, 0))
    elif criterion == "draw":
        _flag_sorteo(group, info, scenario, findings)
        return sorted(group)
    else:
        raise ValueError(f"Criterio de desempate desconocido: {criterion}")

    if len(subgroups) > 1:
        for sub in subgroups:
            if len(sub) == 1 and info[sub[0]]["criterio_desempate"] is None:
                info[sub[0]]["criterio_desempate"] = criterion

    result: list[str] = []
    for sub in subgroups:
        result.extend(
            _rank_group(sub, scores, table, red_counts, rest, info, scenario, findings)
        )
    return result


def resolve_tiebreaks(
    points_table: pd.DataFrame,
    scores: pd.DataFrame,
    red_counts: dict[str, int],
    assumptions: dict,
    scenario: str = "",
    findings: Optional[FindingsLog] = None,
) -> pd.DataFrame:
    """Devuelve la tabla ordenada con dos columnas de trazabilidad:
    `criterio_desempate` (qué criterio separó al equipo de su grupo empatado,
    None si no hubo empate) y `requiere_sorteo` (el art. 18 no alcanzó a resolver)."""
    criteria_queue = list(assumptions["tiebreakers"])
    pts = dict(zip(points_table["equipo"], points_table["pts"]))
    info: dict[str, dict] = {
        t: {"criterio_desempate": None, "requiere_sorteo": False} for t in points_table["equipo"]
    }
    groups_by_pts = _group_by_key(list(points_table["equipo"]), lambda t: pts[t])

    final_order: list[str] = []
    for group in groups_by_pts:
        final_order.extend(
            _rank_group(
                group, scores, points_table, red_counts, criteria_queue, info, scenario, findings
            )
        )

    result = points_table.set_index("equipo").loc[final_order].reset_index()
    result.insert(0, "posicion", range(1, len(result) + 1))
    # dtype=object explícito: evita que pandas infiera y convierta los None en NaN
    # (NaN no es serializable a JSON; el contrato de la columna es str | None).
    result["criterio_desempate"] = pd.Series(
        [info[t]["criterio_desempate"] for t in result["equipo"]],
        index=result.index,
        dtype=object,
    )
    result["requiere_sorteo"] = [info[t]["requiere_sorteo"] for t in result["equipo"]]
    return result


def build_standings(
    matches_valid: pd.DataFrame,
    events: pd.DataFrame,
    overrides: list[ForfeitOverride],
    assumptions: dict,
    scenario: str = "",
    findings: Optional[FindingsLog] = None,
) -> pd.DataFrame:
    """Constructor único reutilizado para los 3 escenarios: oficial (overrides=
    todos los 14), en cancha (overrides=[]), sin doble amarilla (subconjunto)."""
    field_scores = compute_field_scores(matches_valid)
    scores = apply_forfeit_overrides(field_scores, overrides, assumptions)
    points_table = build_points_table(scores)
    red_counts = events[events["evento"] == "Roja"].groupby("equipo").size().to_dict()
    return resolve_tiebreaks(points_table, scores, red_counts, assumptions, scenario, findings)


def build_standings_scenarios(
    matches_valid: pd.DataFrame,
    events: pd.DataFrame,
    all_overrides: list[ForfeitOverride],
    assumptions: dict,
    findings: Optional[FindingsLog] = None,
) -> dict[str, pd.DataFrame]:
    sin_doble_amarilla = [o for o in all_overrides if not o.solo_por_doble_amarilla]
    scenarios = {
        "en_cancha": [],
        "oficial": all_overrides,
        "sin_doble_amarilla": sin_doble_amarilla,
    }
    return {
        name: build_standings(matches_valid, events, overrides, assumptions, name, findings)
        for name, overrides in scenarios.items()
    }


def derive_pending_fixtures(
    matches_valid: pd.DataFrame, matches_excluded: pd.DataFrame, teams_canonical: set[str]
) -> list[tuple[str, str]]:
    """Deriva los emparejamientos de J11 por complemento combinatorio del
    round-robin: pares de las 12 canónicas que NUNCA fueron programados en
    J1-J10 (ni siquiera como partido suspendido). No se hardcodean IDs."""
    programados = pd.concat([matches_valid, matches_excluded])[["local", "visitante"]]
    scheduled_pairs = {
        frozenset((row["local"], row["visitante"])) for _, row in programados.iterrows()
    }
    all_pairs = {frozenset(p) for p in combinations(sorted(teams_canonical), 2)}
    return sorted(tuple(sorted(p)) for p in all_pairs - scheduled_pairs)


def pending_matches_as_pairs(
    matches_excluded: pd.DataFrame, pending_fixtures: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Partidos por disputar: los emparejamientos derivados de J11 más los
    partidos suspendidos pendientes de reprogramación (ej. P042)."""
    reprogramar = [
        (row["local"], row["visitante"]) for _, row in matches_excluded.iterrows()
    ]
    return list(pending_fixtures) + reprogramar


def classify_j11(
    standings_oficial: pd.DataFrame,
    pending_matches: list[tuple[str, str]],
    top_n: int = 8,
) -> dict:
    """Clasificación por ENUMERACIÓN EXACTA de los 3^n resultados posibles de los
    partidos pendientes (J11 + reprogramaciones), comparando solo por puntos:

    - clasificado: en TODOS los escenarios queda en el top_n incluso si cada
      empate en puntos se resolviera en su contra (peor posición <= top_n).
    - eliminado:   en NINGÚN escenario alcanza el top_n ni siquiera empatado en
      puntos con el top_n (mejor posición > top_n en todos).
    - en disputa:  el resto.
    """
    if len(pending_matches) > MAX_ENUMERABLE_MATCHES:
        raise ValueError(
            f"Enumeración exacta no viable: {len(pending_matches)} partidos pendientes "
            f"(3^{len(pending_matches)} escenarios) supera el límite de "
            f"{MAX_ENUMERABLE_MATCHES}. Revisar el enfoque antes de continuar."
        )

    table = standings_oficial.sort_values("posicion").reset_index(drop=True)
    teams = list(table["equipo"])
    base = {t: int(p) for t, p in zip(table["equipo"], table["pts"])}

    peor_posicion = {t: 1 for t in teams}
    mejor_posicion = {t: len(teams) for t in teams}
    pts_min = {t: base[t] for t in teams}
    pts_max = {t: base[t] for t in teams}
    n_escenarios = 0

    for combo in product((0, 1, 2), repeat=len(pending_matches)):
        n_escenarios += 1
        final = dict(base)
        for (a, b), outcome in zip(pending_matches, combo):
            if outcome == 0:
                final[a] += 3
            elif outcome == 1:
                final[a] += 1
                final[b] += 1
            else:
                final[b] += 3
        for t in teams:
            p = final[t]
            # Peor caso: todo empate en puntos se resuelve en contra del equipo.
            ge = sum(1 for o in teams if o != t and final[o] >= p)
            # Mejor caso: todo empate en puntos se resuelve a favor del equipo.
            gt = sum(1 for o in teams if o != t and final[o] > p)
            peor_posicion[t] = max(peor_posicion[t], 1 + ge)
            mejor_posicion[t] = min(mejor_posicion[t], 1 + gt)
            pts_min[t] = min(pts_min[t], p)
            pts_max[t] = max(pts_max[t], p)

    clasificados, eliminados, en_disputa = [], [], []
    for t in teams:
        if peor_posicion[t] <= top_n:
            clasificados.append(t)
        elif mejor_posicion[t] > top_n:
            eliminados.append(t)
        else:
            en_disputa.append(t)

    partidos_restantes = {t: 0 for t in teams}
    for a, b in pending_matches:
        partidos_restantes[a] += 1
        partidos_restantes[b] += 1

    return {
        "clasificados": clasificados,
        "eliminados": eliminados,
        "en_disputa": en_disputa,
        "partidos_restantes": partidos_restantes,
        "puntos_min": pts_min,
        "puntos_max": pts_max,
        "peor_posicion": peor_posicion,
        "mejor_posicion": mejor_posicion,
        "escenarios_evaluados": n_escenarios,
    }

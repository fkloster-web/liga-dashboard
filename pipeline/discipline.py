"""Disciplina: suspensiones, cumplimiento y alineación indebida (art. 32).

Cadena de razonamiento:
  1. Se detectan los eventos que generan suspensión: rojas directas, dobles
     amarillas (double_yellow_is_red) y acumulación de amarillas.
  2. Para cada uno se ubica el SIGUIENTE PARTIDO DISPUTADO del equipo
     (suspension_scope=next_match_only, aplicando next_match_filter: se saltan
     los partidos suspendidos y los que no tienen fecha).
  3. Si el jugador aparece en la alineación de ese partido, hay alineación
     indebida (ineligible_if_in_lineup) y se aplica el art. 32 de oficio.
  4. Por una vía distinta, un jugador sin elegibilidad de registro (R11) que es
     alineado también configura art. 32.

La hoja Sanciones NO es fuente de los disparadores (sanciones_sheet_role): sus 8
filas son todas de tarjeta roja y solo sirven para medir si la notificación de la
Comisión llegó a tiempo. La acumulación de amarillas se calcula de Eventos
(accumulation_trigger_source), porque no existe ninguna fila de acumulación.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from pipeline.findings import Finding, FindingsLog
from pipeline.standings import ForfeitOverride, TriggerType


@dataclass(frozen=True)
class SuspensionTrigger:
    trigger_id: str
    trigger_type: TriggerType
    id_jugador: str
    nombre: str
    equipo: str
    origin_match: str
    jornada_origin: int
    minuto: Optional[int]
    motivo: str


@dataclass(frozen=True)
class LineupViolation:
    id_partido: str
    jornada: int
    equipo: str
    id_jugador: str
    nombre: str
    trigger_type: TriggerType
    origin_match: Optional[str]
    motivo: str


def _jornada_por_partido(schedule: pd.DataFrame) -> dict[str, int]:
    return {r.id_partido: int(r.jornada) for r in schedule.itertuples()}


def detect_red_direct_triggers(
    events: pd.DataFrame, schedule: pd.DataFrame
) -> list[SuspensionTrigger]:
    """Toda roja = suspensión automática de al menos 1 partido."""
    jornadas = _jornada_por_partido(schedule)
    return [
        SuspensionTrigger(
            trigger_id=f"red_direct:{r.id_partido}:{r.id_jugador}",
            trigger_type="red_direct",
            id_jugador=r.id_jugador, nombre=r.nombre, equipo=r.equipo,
            origin_match=r.id_partido, jornada_origin=jornadas[r.id_partido],
            minuto=int(r.minuto), motivo="Tarjeta roja directa",
        )
        for r in events[events["evento"] == "Roja"].itertuples()
    ]


def detect_double_yellow_triggers(
    events: pd.DataFrame, schedule: pd.DataFrame, assumptions: dict
) -> list[SuspensionTrigger]:
    """Doble amarilla = expulsión (confirmado). La suspensión se ancla al partido
    de la 2a amarilla (double_yellow_suspension_anchor=second_yellow_match), que
    por definición es el mismo en el que ocurrieron ambas."""
    if not assumptions["double_yellow_is_red"]:
        return []
    jornadas = _jornada_por_partido(schedule)
    return [
        SuspensionTrigger(
            trigger_id=f"double_yellow:{r.id_partido}:{r.id_jugador}",
            trigger_type="double_yellow",
            id_jugador=r.id_jugador, nombre=r.nombre, equipo=r.equipo,
            origin_match=r.id_partido, jornada_origin=jornadas[r.id_partido],
            minuto=int(r.minuto),
            motivo="Doble amarilla en el mismo partido (expulsión)",
        )
        for r in events[events["is_second_yellow"]].itertuples()
    ]


def detect_accumulation_triggers(
    events: pd.DataFrame, schedule: pd.DataFrame, assumptions: dict
) -> list[SuspensionTrigger]:
    """Acumulación de amarillas a lo largo de la temporada (no se reinicia en el
    cierre de registro: ver cutoff_dates_usage). Se cuenta en orden cronológico
    (jornada, minuto) y dispara cada vez que se alcanza el umbral.

    Aplica las tres reglas de acumulación declaradas en assumptions.yaml, con
    alcances disjuntos: la amarilla previa a la propia roja directa sí acumula,
    la posterior a la propia roja no, y el par que constituye la doble amarilla
    tampoco.
    """
    umbral = int(assumptions["accumulation_yellows_threshold"])
    jornadas = _jornada_por_partido(schedule)

    amarillas = events[events["evento"] == "Amarilla"].copy()

    # (b) amarilla posterior a la propia roja: error de captura, no acumula.
    if assumptions["post_red_own_yellow_treatment"] == "ignore_for_accumulation_keep_in_log":
        amarillas = amarillas[~amarillas["is_after_red"]]

    # (a) amarilla previa a la propia roja directa en el mismo partido.
    if not assumptions["yellows_in_red_match_count_for_accumulation"]:
        con_roja = {
            (r.id_partido, r.id_jugador)
            for r in events[events["evento"] == "Roja"].itertuples()
        }
        claves = list(zip(amarillas["id_partido"], amarillas["id_jugador"]))
        marca = pd.Series([c in con_roja for c in claves], index=amarillas.index)
        amarillas = amarillas[~marca]

    # (c) el par de amarillas que ES la expulsión por doble amarilla.
    if not assumptions["double_yellow_pair_counts_for_accumulation"]:
        pares = {
            (r.id_partido, r.id_jugador)
            for r in amarillas[amarillas["is_second_yellow"]].itertuples()
        }
        claves = list(zip(amarillas["id_partido"], amarillas["id_jugador"]))
        marca = pd.Series([c in pares for c in claves], index=amarillas.index)
        amarillas = amarillas[~marca]

    amarillas["jornada"] = amarillas["id_partido"].map(jornadas)
    amarillas = amarillas.sort_values(["id_jugador", "jornada", "minuto"])

    out: list[SuspensionTrigger] = []
    for _, grupo in amarillas.groupby("id_jugador"):
        for i, r in enumerate(grupo.itertuples(), start=1):
            if i % umbral == 0:
                out.append(SuspensionTrigger(
                    trigger_id=f"accumulation:{r.id_partido}:{r.id_jugador}",
                    trigger_type="accumulation",
                    id_jugador=r.id_jugador, nombre=r.nombre, equipo=r.equipo,
                    origin_match=r.id_partido, jornada_origin=int(r.jornada),
                    minuto=int(r.minuto), motivo=f"Acumulación de {i} amarillas",
                ))
    return out


def detect_all_triggers(
    events: pd.DataFrame, schedule: pd.DataFrame, assumptions: dict
) -> list[SuspensionTrigger]:
    triggers = (
        detect_red_direct_triggers(events, schedule)
        + detect_double_yellow_triggers(events, schedule, assumptions)
        + detect_accumulation_triggers(events, schedule, assumptions)
    )
    return sorted(triggers, key=lambda t: (t.jornada_origin, t.origin_match, t.id_jugador))


def find_next_match_played(
    equipo: str, jornada_origin: int, schedule: pd.DataFrame, assumptions: dict
) -> Optional[pd.Series]:
    """Siguiente partido efectivamente disputado por el equipo después de la
    jornada de origen, aplicando next_match_filter: se descartan los partidos
    suspendidos (ej. P042) y los que aún no tienen fecha."""
    f = assumptions["next_match_filter"]
    juega = (schedule["local"] == equipo) | (schedule["visitante"] == equipo)
    cand = schedule[juega & (schedule["jornada"] > jornada_origin)]
    cand = cand[~cand["estatus"].isin(f["exclude_status"])]
    if f["require_date"]:
        cand = cand[cand["fecha_parsed"].notna()]
    cand = cand.sort_values("jornada")
    return cand.iloc[0] if len(cand) else None


def check_lineup_violations(
    triggers: list[SuspensionTrigger],
    schedule: pd.DataFrame,
    lineups: pd.DataFrame,
    assumptions: dict,
    findings: Optional[FindingsLog] = None,
) -> tuple[list[LineupViolation], pd.DataFrame]:
    """Devuelve (violaciones, cumplimiento). 'Jugó' = aparece en Alineaciones.
    Cumplir la suspensión en un partido posterior no la valida
    (late_served_suspension_is_valid=false): la infracción queda anclada al
    partido que le correspondía."""
    if not assumptions["ineligible_if_in_lineup"]:
        raise ValueError("ineligible_if_in_lineup=false no está soportado")

    alineados = set(zip(lineups["id_partido"], lineups["id_jugador"]))
    violations: list[LineupViolation] = []
    filas = []

    for t in triggers:
        siguiente = find_next_match_played(t.equipo, t.jornada_origin, schedule, assumptions)
        id_siguiente = None if siguiente is None else str(siguiente["id_partido"])
        jugo = id_siguiente is not None and (id_siguiente, t.id_jugador) in alineados
        if id_siguiente is None:
            estado = "pendiente"
        elif jugo:
            estado = "no_cumplida"
        else:
            estado = "cumplida"

        filas.append({
            "trigger_id": t.trigger_id,
            "trigger_type": t.trigger_type,
            "id_jugador": t.id_jugador,
            "nombre": t.nombre,
            "equipo": t.equipo,
            "partido_origen": t.origin_match,
            "jornada_origen": t.jornada_origin,
            "partido_a_cumplir": id_siguiente,
            "jornada_a_cumplir": None if siguiente is None else int(siguiente["jornada"]),
            "jugo": jugo,
            "estado": estado,
            "cumplida": estado == "cumplida",
        })

        if jugo:
            motivo = (
                f"{t.motivo} en {t.origin_match}; debía cumplir suspensión en "
                f"{id_siguiente} y fue alineado"
            )
            violations.append(LineupViolation(
                id_partido=id_siguiente, jornada=int(siguiente["jornada"]),
                equipo=t.equipo, id_jugador=t.id_jugador, nombre=t.nombre,
                trigger_type=t.trigger_type, origin_match=t.origin_match, motivo=motivo,
            ))
            if findings is not None:
                findings.add(Finding(
                    rule_id="ART32", sheet="Alineaciones",
                    record_id=f"{id_siguiente}:{t.equipo}:{t.id_jugador}",
                    field="alineacion", original_value="jugador suspendido alineado",
                    corrected_value="art. 32: partido perdido 3-0",
                    action="corrected", severity="critical", note=motivo,
                ))

    return violations, pd.DataFrame(filas)


def detect_registration_violations(
    lineups: pd.DataFrame,
    schedule: pd.DataFrame,
    findings: Optional[FindingsLog] = None,
) -> list[LineupViolation]:
    """Vía distinta a la suspensión: jugador sin elegibilidad de registro (R11)
    que aparece alineado. También configura art. 32. El motivo se toma del que
    registró R11, no de un texto fijo: distingue el alta fuera de plazo de la
    alineación fuera de la ventana [fecha_alta, fecha_baja]."""
    jornadas = _jornada_por_partido(schedule)
    out: list[LineupViolation] = []
    for r in lineups[lineups["is_ineligible_registration"]].itertuples():
        motivo = f"Alineado sin elegibilidad de registro ({r.motivo_inelegibilidad})"
        out.append(LineupViolation(
            id_partido=r.id_partido, jornada=jornadas[r.id_partido], equipo=r.equipo,
            id_jugador=r.id_jugador, nombre=r.nombre, trigger_type="registration",
            origin_match=None, motivo=motivo,
        ))
        if findings is not None:
            findings.add(Finding(
                rule_id="ART32", sheet="Alineaciones",
                record_id=f"{r.id_partido}:{r.equipo}:{r.id_jugador}",
                field="alineacion", original_value="jugador no elegible alineado",
                corrected_value="art. 32: partido perdido 3-0",
                action="corrected", severity="critical", note=motivo,
            ))
    return out


def build_forfeit_overrides(violations: list[LineupViolation]) -> list[ForfeitOverride]:
    """Un forfeit por (partido, equipo infractor), sin importar cuántos
    infractores haya (single_forfeit_not_cumulative). Conserva todos los tipos
    de infracción para poder construir el escenario 'sin doble amarilla'."""
    agrupado: dict[tuple[str, str], set[str]] = {}
    for v in violations:
        agrupado.setdefault((v.id_partido, v.equipo), set()).add(v.trigger_type)
    return [
        ForfeitOverride(
            id_partido=id_partido,
            infractor_team=equipo,
            trigger_types=frozenset(tipos),
        )
        for (id_partido, equipo), tipos in sorted(agrupado.items())
    ]


def resolve_sanction_players(sanctions: pd.DataFrame, players: pd.DataFrame) -> dict:
    """Resuelve (equipo, nombre) -> id_jugador para la hoja Sanciones.

    ÚNICA excepción a la regla del proyecto de cruzar siempre por
    (equipo, dorsal): Sanciones no trae dorsal ni id_jugador, solo el nombre y
    el equipo, así que no existe otra llave posible. Se acota el riesgo de los
    homónimos resolviendo SIEMPRE dentro del equipo y fallando de forma ruidosa
    si una fila no resuelve o resuelve a más de un jugador, en vez de elegir uno
    en silencio. Hoy los dos pares de homónimos de la liga están en equipos
    distintos, por lo que las 8 filas resuelven sin ambigüedad.
    """
    indice: dict[tuple[str, str], list[str]] = {}
    for r in players.itertuples():
        indice.setdefault((r.equipo, r.nombre), []).append(r.id_jugador)

    resuelto: dict = {}
    problemas: list[str] = []
    for r in sanctions.itertuples():
        ids = indice.get((r.equipo, r.jugador), [])
        if len(ids) == 1:
            resuelto[r.Index] = ids[0]
        elif not ids:
            problemas.append(f"sin coincidencia en Jugadores: {r.jugador!r} ({r.equipo})")
        else:
            problemas.append(f"nombre ambiguo dentro del equipo: {r.jugador!r} ({r.equipo}) -> {ids}")

    if problemas:
        raise ValueError(
            "No se pudo resolver la hoja Sanciones contra Jugadores por (equipo, nombre):\n"
            + "\n".join(f"  - {p}" for p in problemas)
            + "\nRevisar los datos: este cruce no admite ambigüedad."
        )
    return resuelto


def build_timeline(
    compliance: pd.DataFrame,
    sanctions: pd.DataFrame,
    players: pd.DataFrame,
    schedule: pd.DataFrame,
) -> pd.DataFrame:
    """Línea de tiempo por sanción: evento -> siguiente partido -> sesión de la
    Comisión -> notificación -> ¿jugó?

    Es la evidencia del cuello de botella del proceso: cuando hay jornada entre
    semana, la notificación llega DESPUÉS del partido que debía impedir.
    """
    fechas = {r.id_partido: r.fecha_parsed for r in schedule.itertuples()}

    s = sanctions.copy()
    s["id_jugador"] = pd.Series(resolve_sanction_players(s, players))
    s["jornada_motivo"] = [
        int(m.group(1))
        if (m := re.search(r"jornada\s+(\d+)", str(motivo), re.IGNORECASE))
        else None
        for motivo in s["motivo"]
    ]
    indice = {
        (row["id_jugador"], row["jornada_motivo"]): row for _, row in s.iterrows()
    }

    filas = []
    for r in compliance.itertuples():
        sancion = indice.get((r.id_jugador, r.jornada_origen))
        fecha_evento = fechas.get(r.partido_origen)
        fecha_cumplir = fechas.get(r.partido_a_cumplir) if r.partido_a_cumplir else None
        fecha_sesion = sancion["fecha_sesion"] if sancion is not None else None
        fecha_notif = sancion["fecha_notificacion"] if sancion is not None else None

        notificado_a_tiempo = None
        if fecha_notif is not None and fecha_cumplir is not None:
            notificado_a_tiempo = bool(pd.Timestamp(fecha_notif) < pd.Timestamp(fecha_cumplir))

        dias = None
        if fecha_evento is not None and fecha_cumplir is not None:
            dias = int((pd.Timestamp(fecha_cumplir) - pd.Timestamp(fecha_evento)).days)

        filas.append({
            "trigger_id": r.trigger_id,
            "trigger_type": r.trigger_type,
            "id_jugador": r.id_jugador,
            "jugador": r.nombre,
            "equipo": r.equipo,
            "partido_origen": r.partido_origen,
            "fecha_evento": fecha_evento,
            "partido_a_cumplir": r.partido_a_cumplir,
            "fecha_partido_a_cumplir": fecha_cumplir,
            "dias_entre_evento_y_partido": dias,
            "fecha_sesion": fecha_sesion,
            "fecha_notificacion": fecha_notif,
            "en_sanciones": sancion is not None,
            "notificado_antes_del_partido": notificado_a_tiempo,
            "jugo": r.jugo,
            "estado": r.estado,
        })
    return pd.DataFrame(filas)


def discipline_summary(
    triggers: list[SuspensionTrigger],
    compliance: pd.DataFrame,
    violations: list[LineupViolation],
    matches_valid: pd.DataFrame,
) -> dict:
    por_tipo: dict[str, int] = {}
    for t in triggers:
        por_tipo[t.trigger_type] = por_tipo.get(t.trigger_type, 0) + 1

    total = len(triggers)
    cumplidas = int(compliance["cumplida"].sum())
    no_cumplidas = int((compliance["estado"] == "no_cumplida").sum())
    pendientes = int((compliance["estado"] == "pendiente").sum())

    rojas = compliance[compliance["trigger_type"] == "red_direct"]
    rojas_no_cumplidas = int((rojas["estado"] == "no_cumplida").sum())

    por_registro = [v for v in violations if v.trigger_type == "registration"]
    partidos_afectados = {v.id_partido for v in violations}
    n_partidos = len(matches_valid)

    return {
        "triggers_total": total,
        "triggers_por_tipo": por_tipo,
        "cumplidas_a_tiempo": cumplidas,
        "no_cumplidas": no_cumplidas,
        "pendientes": pendientes,
        "pct_no_cumplidas": no_cumplidas / total * 100 if total else 0.0,
        "rojas_total": len(rojas),
        "rojas_no_cumplidas": rojas_no_cumplidas,
        "pct_rojas_no_cumplidas": rojas_no_cumplidas / len(rojas) * 100 if len(rojas) else 0.0,
        "alta_fuera_de_plazo": len(por_registro),
        "casos_alineacion_indebida": len(violations),
        "partidos_afectados": len(partidos_afectados),
        "partidos_jugados": n_partidos,
        "pct_partidos_afectados": len(partidos_afectados) / n_partidos * 100 if n_partidos else 0.0,
    }

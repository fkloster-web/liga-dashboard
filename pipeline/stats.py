"""Estadísticas del torneo: goles, resultados, tarjetas y prueba de significancia
entre árbitros.

Todas las métricas de juego usan el MARCADOR EN CANCHA (stats_use_field_score=true),
nunca el resultado oficial tras art. 32: describen lo que ocurrió en el campo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

CARD_EVENTS = ("Amarilla", "Roja")


def _normalize_referee(serie: pd.Series) -> pd.Series:
    """'Árbitro A. Núñez' -> 'A. Núñez'."""
    return serie.str.replace(r"^Árbitro\s+", "", regex=True)


def compute_general_stats(matches_valid: pd.DataFrame, assumptions: dict) -> dict:
    if not assumptions["stats_use_field_score"]:
        raise ValueError(
            "stats_use_field_score=false no está soportado: estas estadísticas "
            "describen el juego en cancha, no el resultado administrativo."
        )
    n = len(matches_valid)
    gl = matches_valid["goles_local"].astype(int)
    gv = matches_valid["goles_visitante"].astype(int)
    goles = int(gl.sum() + gv.sum())
    local, empate, visita = int((gl > gv).sum()), int((gl == gv).sum()), int((gl < gv).sum())
    return {
        "partidos": n,
        "goles": goles,
        "goles_por_partido": goles / n,
        "resultados": {
            "local": {"partidos": local, "pct": local / n * 100},
            "empate": {"partidos": empate, "pct": empate / n * 100},
            "visitante": {"partidos": visita, "pct": visita / n * 100},
        },
    }


def compute_home_away_raw(matches_valid: pd.DataFrame) -> pd.DataFrame:
    """Conteo CRUDO de partidos como local y visitante por equipo.

    No calcula ninguna métrica de 'ventaja de local' a propósito
    (home_away_bias_disclosure=report_raw_counts_no_inference): el calendario
    está desbalanceado y no es aleatorio, así que el % de victoria local no
    permite concluir ventaja de localía. La advertencia la muestra el sitio.
    """
    local = matches_valid["local"].value_counts().rename("como_local")
    visita = matches_valid["visitante"].value_counts().rename("como_visitante")
    df = pd.concat([local, visita], axis=1).fillna(0).astype(int)
    df["partidos"] = df["como_local"] + df["como_visitante"]
    df["desbalance"] = df["como_local"] - df["como_visitante"]
    return df.reset_index(names="equipo").sort_values(
        "desbalance", ascending=False
    ).reset_index(drop=True)


def cards_per_match(events: pd.DataFrame, matches_valid: pd.DataFrame) -> pd.DataFrame:
    """Una fila por partido válido: árbitro y número de tarjetas mostradas.
    Los partidos sin tarjetas cuentan como 0 (no se pierden en el groupby)."""
    base = matches_valid[["id_partido", "arbitro"]].copy()
    base["arbitro"] = _normalize_referee(base["arbitro"])
    cards = events[events["evento"].isin(CARD_EVENTS)]
    conteo = cards.groupby("id_partido").size().rename("tarjetas").reset_index()
    df = base.merge(conteo, on="id_partido", how="left")
    df["tarjetas"] = df["tarjetas"].fillna(0).astype(int)
    return df


def compute_cards_stats(
    events_raw: pd.DataFrame, events_clean: pd.DataFrame, matches_valid: pd.DataFrame
) -> dict:
    """Tarjetas crudas (pre-R08) y depuradas (post-R08). Se reportan ambas
    porque la diferencia es, en sí misma, un hallazgo de calidad de datos."""
    n = len(matches_valid)
    validos = set(matches_valid["id_partido"])
    raw = events_raw[events_raw["id_partido"].isin(validos)]
    crudas = int(raw["evento"].isin(CARD_EVENTS).sum())
    limpias = int(events_clean["evento"].isin(CARD_EVENTS).sum())
    return {
        "amarillas_crudas": int((raw["evento"] == "Amarilla").sum()),
        "rojas_crudas": int((raw["evento"] == "Roja").sum()),
        "total_crudas": crudas,
        "total_post_r08": limpias,
        "por_partido_crudas": crudas / n,
        "por_partido_post_r08": limpias / n,
        "expulsiones_doble_amarilla": int(events_clean["is_second_yellow"].sum()),
    }


def compute_referee_stats(
    events: pd.DataFrame, matches_valid: pd.DataFrame, confidence: float = 0.95
) -> pd.DataFrame:
    """Tarjetas por árbitro con media e intervalo de confianza.

    El IC es un intervalo t sobre la media de tarjetas por partido. Con muestras
    de 9-16 partidos es una aproximación: se publica junto a n para que el
    lector juzgue, no para sostener una conclusión por sí solo.
    """
    por_partido = cards_per_match(events, matches_valid)
    filas = []
    for arbitro, grupo in por_partido.groupby("arbitro"):
        x = grupo["tarjetas"].to_numpy()
        n = len(x)
        media = float(x.mean())
        desv = float(x.std(ddof=1)) if n > 1 else 0.0
        if n > 1:
            margen = float(sps.t.ppf(0.5 + confidence / 2, df=n - 1) * desv / np.sqrt(n))
        else:
            margen = float("nan")
        filas.append({
            "arbitro": arbitro,
            "partidos": n,
            "tarjetas": int(x.sum()),
            "por_partido": media,
            "desv_est": desv,
            "ic95_bajo": media - margen,
            "ic95_alto": media + margen,
        })
    return pd.DataFrame(filas).sort_values("arbitro").reset_index(drop=True)


def run_referee_significance(
    events: pd.DataFrame, matches_valid: pd.DataFrame, assumptions: dict
) -> dict:
    """Kruskal-Wallis entre los 5 árbitros y Mann-Whitney del árbitro con más
    tarjetas por partido contra el resto, con corrección de Bonferroni.

    NO concluye que un árbitro sea 'más estricto': las muestras son pequeñas,
    la asignación de árbitros no es aleatoria y los datos tienen errores de
    captura. El resultado se reporta con su interpretación explícita.
    """
    cfg = assumptions["stats_test_config"]
    por_partido = cards_per_match(events, matches_valid)
    grupos = [g["tarjetas"].to_numpy() for _, g in por_partido.groupby("arbitro")]

    h_stat, p_kruskal = sps.kruskal(*grupos)

    medias = por_partido.groupby("arbitro")["tarjetas"].mean()
    foco = str(medias.idxmax())
    del_foco = por_partido[por_partido["arbitro"] == foco]["tarjetas"].to_numpy()
    resto = por_partido[por_partido["arbitro"] != foco]["tarjetas"].to_numpy()
    u_stat, p_mw = sps.mannwhitneyu(
        del_foco, resto,
        alternative=cfg["mannwhitney_alternative"],
        use_continuity=cfg["mannwhitney_use_continuity"],
    )
    m = int(cfg["bonferroni_m"])
    p_mw_bonf = min(float(p_mw) * m, 1.0)

    significativo = p_mw_bonf < 0.05
    return {
        "kruskal": {
            "statistic": float(h_stat),
            "pvalue": float(p_kruskal),
            "grupos": len(grupos),
        },
        "mannwhitney": {
            "arbitro": foco,
            "statistic": float(u_stat),
            "pvalue": float(p_mw),
            "pvalue_bonferroni": p_mw_bonf,
            "bonferroni_m": m,
        },
        "significativo": significativo,
        "interpretacion": (
            f"La prueba global de Kruskal-Wallis no detecta diferencias entre los "
            f"{len(grupos)} árbitros (p={float(p_kruskal):.3f}). La comparación de "
            f"{foco} contra el resto da p={float(p_mw):.3f} sin corregir, pero al "
            f"corregir por las {m} comparaciones posibles (Bonferroni) queda en "
            f"p={p_mw_bonf:.3f}. "
            + (
                "No hay evidencia suficiente para afirmar que algún árbitro sea más "
                "estricto: además, las muestras son de 9 a 16 partidos, la asignación "
                "de árbitros no fue aleatoria y los datos contienen errores de captura."
                if not significativo
                else "El resultado resiste la corrección, pero la asignación de árbitros "
                "no fue aleatoria: no puede interpretarse como causal."
            )
        ),
    }

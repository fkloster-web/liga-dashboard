"""Orquestación del pipeline.

Separa deliberadamente el cómputo puro (`compute_all`, sin escribir nada) de la
escritura de archivos (`write_outputs`), para que las pruebas de control corran
el pipeline completo una sola vez por sesión sin tocar disco.
"""

from __future__ import annotations

import dataclasses
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yaml

# Permite ejecutar tanto `python pipeline/build.py` como `python -m pipeline.build`:
# al invocar el archivo directamente, Python pone pipeline/ en sys.path, no la raíz.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import clean, discipline, load, scorers, standings, stats  # noqa: E402
from pipeline.findings import FindingsLog  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEL = REPO_ROOT / "data" / "raw" / "Datos_prueba_liga.xlsx"
DEFAULT_ASSUMPTIONS = REPO_ROOT / "config" / "assumptions.yaml"
DEFAULT_OUT_DIR = REPO_ROOT / "site" / "data"


@dataclass
class PipelineResult:
    assumptions: dict
    raw: load.RawData
    cleaned: clean.CleanedData
    schedule: pd.DataFrame
    triggers: list
    violations: list
    compliance: pd.DataFrame
    timeline: pd.DataFrame
    discipline_summary: dict
    overrides: list
    standings: dict[str, pd.DataFrame]
    pending_fixtures: list
    pending_matches: list
    j11: dict
    scorers: pd.DataFrame
    scorers_vs_published: pd.DataFrame
    own_goals: int
    goals_without_author: pd.DataFrame
    stats_general: dict
    home_away: pd.DataFrame
    cards: dict
    referees: pd.DataFrame
    referees_post_r08: pd.DataFrame
    significance: dict
    significance_post_r08: dict
    findings: pd.DataFrame


def compute_all(
    excel_path: str | Path = DEFAULT_EXCEL,
    assumptions_path: str | Path = DEFAULT_ASSUMPTIONS,
) -> PipelineResult:
    findings = FindingsLog()
    assumptions = yaml.safe_load(Path(assumptions_path).read_text(encoding="utf-8"))

    raw = load.load_raw(excel_path)
    load.validate_schema(raw)
    cd = clean.clean_all(raw, assumptions, findings)

    # Calendario completo: disciplina necesita ver los partidos suspendidos para
    # poder saltarlos explícitamente al buscar el siguiente partido disputado.
    schedule = pd.concat([cd.matches_valid, cd.matches_excluded], ignore_index=True)

    triggers = discipline.detect_all_triggers(cd.events, schedule, assumptions)
    violations, compliance = discipline.check_lineup_violations(
        triggers, schedule, cd.lineups, assumptions, findings
    )
    violations = violations + discipline.detect_registration_violations(
        cd.lineups, schedule, findings
    )
    overrides = discipline.build_forfeit_overrides(violations)
    timeline = discipline.build_timeline(compliance, cd.sanctions, cd.players, schedule)
    resumen_disciplina = discipline.discipline_summary(
        triggers, compliance, violations, cd.matches_valid
    )

    tablas = standings.build_standings_scenarios(
        cd.matches_valid, cd.events, overrides, assumptions, findings
    )
    pending_fixtures = standings.derive_pending_fixtures(
        cd.matches_valid, cd.matches_excluded, set(cd.teams["equipo"])
    )
    pending_matches = standings.pending_matches_as_pairs(cd.matches_excluded, pending_fixtures)
    j11 = standings.classify_j11(tablas["oficial"], pending_matches)

    goleo = scorers.build_scorers_table(cd.events, cd.players, assumptions)
    goleo_vs_publicado = scorers.compare_vs_published(
        goleo, raw.published_scorers, cd.events, findings
    )

    # Las pruebas de árbitros se reportan sobre datos crudos (base de los valores
    # de control) y sobre datos limpios; la conclusión no cambia con ninguna.
    return PipelineResult(
        assumptions=assumptions,
        raw=raw,
        cleaned=cd,
        schedule=schedule,
        triggers=triggers,
        violations=violations,
        compliance=compliance,
        timeline=timeline,
        discipline_summary=resumen_disciplina,
        overrides=overrides,
        standings=tablas,
        pending_fixtures=pending_fixtures,
        pending_matches=pending_matches,
        j11=j11,
        scorers=goleo,
        scorers_vs_published=goleo_vs_publicado,
        own_goals=scorers.count_own_goals(cd.events),
        goals_without_author=scorers.goals_without_author(cd.matches_valid, cd.events),
        stats_general=stats.compute_general_stats(cd.matches_valid, assumptions),
        home_away=stats.compute_home_away_raw(cd.matches_valid),
        cards=stats.compute_cards_stats(raw.events, cd.events, cd.matches_valid),
        referees=stats.compute_referee_stats(raw.events, cd.matches_valid),
        referees_post_r08=stats.compute_referee_stats(cd.events, cd.matches_valid),
        significance=stats.run_referee_significance(raw.events, cd.matches_valid, assumptions),
        significance_post_r08=stats.run_referee_significance(
            cd.events, cd.matches_valid, assumptions
        ),
        findings=findings.to_dataframe(),
    )


def _jsonable(value: Any) -> Any:
    """Convierte estructuras de pandas/numpy/dataclasses a tipos JSON puros.
    NaN y NaT se vuelven null (NaN no es JSON válido)."""
    if isinstance(value, pd.DataFrame):
        return [_jsonable(row) for row in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return _jsonable(value.to_dict())
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(_jsonable(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return value
    if hasattr(value, "item"):  # escalares de numpy
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _git_commit() -> Optional[str]:
    try:
        salida = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return salida.stdout.strip() or None
    except Exception:
        return None


def build_payloads(result: PipelineResult) -> dict[str, Any]:
    """Contratos de datos que consume el sitio. Un archivo por sección."""
    cd = result.cleaned
    return {
        "standings": {
            "publicada": result.raw.published_table,
            "en_cancha": result.standings["en_cancha"],
            "oficial": result.standings["oficial"],
            "sin_doble_amarilla": result.standings["sin_doble_amarilla"],
        },
        "scorers": {
            "correcto": result.scorers,
            "publicado": result.raw.published_scorers,
            "comparacion": result.scorers_vs_published,
            "autogoles": result.own_goals,
            "goles_sin_autor": result.goals_without_author,
        },
        "stats": {
            "general": result.stats_general,
            "home_away": result.home_away,
            "cards": result.cards,
            "referees": result.referees,
            "referees_post_r08": result.referees_post_r08,
            "significance": result.significance,
            "significance_post_r08": result.significance_post_r08,
        },
        "discipline": {
            "triggers": result.triggers,
            "violations": result.violations,
            "compliance": result.compliance,
            "timeline": result.timeline,
            "summary": result.discipline_summary,
        },
        "j11": {
            **result.j11,
            "fixtures_pendientes": [
                {"local": a, "visitante": b, "origen": "J11 (derivado del round-robin)"}
                for a, b in result.pending_fixtures
            ],
            "reprogramacion_pendiente": cd.matches_excluded[
                ["id_partido", "jornada", "local", "visitante", "estatus"]
            ],
        },
        "matches": {
            "validos": cd.matches_valid,
            "excluidos": cd.matches_excluded,
        },
        "findings_log": result.findings,
        "meta": {
            "generado_en": datetime.now().astimezone().isoformat(timespec="seconds"),
            "fuente": "excel",
            "archivo_fuente": DEFAULT_EXCEL.name,
            "git_commit": _git_commit(),
            "supuestos": result.assumptions,
            "conteos": {
                "partidos_validos": len(cd.matches_valid),
                "partidos_excluidos": len(cd.matches_excluded),
                "jugadores": len(cd.players),
                "eventos": len(cd.events),
                "alineaciones": len(cd.lineups),
                "hallazgos": len(result.findings),
            },
        },
    }


def write_outputs(result: PipelineResult, out_dir: str | Path = DEFAULT_OUT_DIR) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    escritos = []
    for nombre, payload in build_payloads(result).items():
        destino = out_dir / f"{nombre}.json"
        destino.write_text(
            json.dumps(_jsonable(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        escritos.append(destino)
    return escritos


def main() -> None:
    result = compute_all()
    escritos = write_outputs(result)
    resumen = result.discipline_summary
    print(f"Partidos válidos: {len(result.cleaned.matches_valid)}")
    print(f"Hallazgos registrados: {len(result.findings)}")
    print(f"Alineación indebida: {resumen['casos_alineacion_indebida']} casos "
          f"en {resumen['partidos_afectados']} partidos")
    print(f"Líder oficial: {result.standings['oficial'].iloc[0]['equipo']}")
    for destino in escritos:
        print(f"  escrito {destino.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

"""Lectura cruda de la fuente de datos. Sin lógica de negocio ni limpieza."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

EXPECTED_SHEETS: dict[str, dict[str, object]] = {
    "Equipos": {"n_rows": 12, "columns": ["equipo", "delegado"]},
    "Jugadores": {
        "n_rows": 218,
        "columns": ["id_jugador", "nombre", "equipo", "dorsal", "fecha_alta", "fecha_baja"],
    },
    "Partidos": {
        "n_rows": 61,
        "columns": [
            "id_partido", "jornada", "fecha", "local", "goles_local",
            "goles_visitante", "visitante", "estatus", "arbitro",
        ],
    },
    "Alineaciones": {"n_rows": 1652, "columns": ["id_partido", "equipo", "dorsal", "nombre"]},
    "Eventos": {
        "n_rows": 352,
        "columns": ["id_partido", "minuto", "equipo", "dorsal", "nombre", "evento"],
    },
    "Sanciones": {
        "n_rows": 8,
        "columns": [
            "fecha_sesion", "jugador", "equipo", "motivo",
            "partidos_suspension", "fecha_notificacion",
        ],
    },
    "Tabla_publicada": {
        "n_rows": 12,
        "columns": ["Pos", "Equipo", "PJ", "G", "E", "P", "GF", "GC", "DG", "Pts"],
    },
    "Goleo_publicado": {"n_rows": 10, "columns": ["Pos", "Jugador", "Equipo", "Goles"]},
}


class SchemaError(Exception):
    pass


@dataclass
class RawData:
    readme_lines: list[str]
    teams: pd.DataFrame
    players: pd.DataFrame
    matches: pd.DataFrame
    lineups: pd.DataFrame
    events: pd.DataFrame
    sanctions: pd.DataFrame
    published_table: pd.DataFrame
    published_scorers: pd.DataFrame


def _read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")


def _read_readme(path: Path) -> list[str]:
    df = pd.read_excel(path, sheet_name="Léeme", engine="openpyxl", header=None)
    lines: list[str] = []
    for row in df.itertuples(index=False):
        for value in row:
            if isinstance(value, str) and value.strip():
                lines.append(value.strip())
    return lines


def load_raw(path: str | Path, source: Literal["excel", "google_sheets"] = "excel") -> RawData:
    if source == "google_sheets":
        raise NotImplementedError(
            "Fuente 'google_sheets' no implementada en esta entrega; el contrato de "
            "salida (RawData) ya está listo para esa integración futura."
        )
    if source != "excel":
        raise ValueError(f"Fuente de datos desconocida: {source!r}")

    path = Path(path)
    return RawData(
        readme_lines=_read_readme(path),
        teams=_read_sheet(path, "Equipos"),
        players=_read_sheet(path, "Jugadores"),
        matches=_read_sheet(path, "Partidos"),
        lineups=_read_sheet(path, "Alineaciones"),
        events=_read_sheet(path, "Eventos"),
        sanctions=_read_sheet(path, "Sanciones"),
        published_table=_read_sheet(path, "Tabla_publicada"),
        published_scorers=_read_sheet(path, "Goleo_publicado"),
    )


_SHEET_TO_ATTR = {
    "Equipos": "teams",
    "Jugadores": "players",
    "Partidos": "matches",
    "Alineaciones": "lineups",
    "Eventos": "events",
    "Sanciones": "sanctions",
    "Tabla_publicada": "published_table",
    "Goleo_publicado": "published_scorers",
}


def validate_schema(raw: RawData) -> None:
    errors: list[str] = []
    for sheet_name, expected in EXPECTED_SHEETS.items():
        df = getattr(raw, _SHEET_TO_ATTR[sheet_name])
        expected_cols = expected["columns"]
        missing_cols = [c for c in expected_cols if c not in df.columns]
        if missing_cols:
            errors.append(f"{sheet_name}: faltan columnas {missing_cols}")
        if len(df) != expected["n_rows"]:
            errors.append(
                f"{sheet_name}: se esperaban {expected['n_rows']} filas, hay {len(df)}"
            )
    if errors:
        raise SchemaError(
            "El Excel no coincide con el esquema documentado en CLAUDE.md sección 4:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

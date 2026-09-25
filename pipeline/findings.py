"""Log de hallazgos consolidado: toda corrección aplicada a los datos se registra aquí
con su regla, registro afectado, valor original y valor corregido."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Optional

import pandas as pd

Action = Literal["corrected", "excluded", "deduplicated", "flagged", "documented_no_action"]
Severity = Literal["info", "warning", "critical"]


@dataclass(frozen=True)
class Finding:
    rule_id: str
    sheet: str
    record_id: str
    field: Optional[str]
    original_value: Optional[str]
    corrected_value: Optional[str]
    action: Action
    severity: Severity
    note: str


class FindingsLog:
    def __init__(self) -> None:
        self._findings: list[Finding] = []

    def add(self, finding: Finding) -> None:
        self._findings.append(finding)

    def extend(self, findings: Iterable[Finding]) -> None:
        self._findings.extend(findings)

    def to_dataframe(self) -> pd.DataFrame:
        columns = [
            "rule_id", "sheet", "record_id", "field",
            "original_value", "corrected_value", "action", "severity", "note",
        ]
        if not self._findings:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame([f.__dict__ for f in self._findings], columns=columns)

    def filter(
        self,
        rule_id: Optional[str] = None,
        sheet: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self.to_dataframe()
        if rule_id is not None:
            df = df[df["rule_id"] == rule_id]
        if sheet is not None:
            df = df[df["sheet"] == sheet]
        if severity is not None:
            df = df[df["severity"] == severity]
        return df

    def __len__(self) -> int:
        return len(self._findings)

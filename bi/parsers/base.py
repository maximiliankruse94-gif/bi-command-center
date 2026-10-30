from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class Issue:
    severity: str          # "info" | "warning" | "error"
    category: str          # z.B. "datum", "fehlwert", "duplikat", "struktur", "plausibilitaet"
    message: str
    workbook: str = ""
    tab: str = ""
    row: int | None = None  # 1-basierte Zeilennummer wie in Google Sheets

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Detection:
    kind: str
    score: float
    reasons: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    dataset: str                         # Ziel-Tabelle, z.B. "daily"
    df: pd.DataFrame
    issues: list[Issue] = field(default_factory=list)
    extra: dict[str, pd.DataFrame] = field(default_factory=dict)  # weitere Datasets (z.B. abo_product)

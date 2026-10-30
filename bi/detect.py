"""Regelbasierte Erkennung von Tabellenblättern (kein LLM).

Jeder Parser bewertet ein Tab anhand von Spaltenüberschriften, Datentypen,
Datumsformaten und Inhalten mit einem Score 0..1. Der Tab-Name ist nur ein
Zusatzindiz (max. +0.1). Zuordnung erfolgt nur, wenn
  * der beste Score >= MIN_SCORE ist und
  * der Abstand zum zweitbesten Score >= MIN_MARGIN.
Sonst gilt das Tab als UNBEKANNT: nichts wird importiert, das Dashboard warnt
und bietet eine manuelle Zuordnung an.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .parsers import daily, monthly, newsletter, weekly
from .parsers.base import Detection
from .parsers.common import norm_text

PARSERS = {"daily": daily, "weekly": weekly, "monthly": monthly, "newsletter": newsletter}
IMPORT_KINDS = set(PARSERS)
IGNORED_KINDS = {
    "ignore_dashboard": "Anzeige-/Formularblatt (berechnete Ansicht, keine Rohdaten)",
    "ignore_template": "Vorlage ohne Daten",
    "newsletter_extract": "Auszug/Duplikat vorhandener Newsletter-Zeilen (Import würde doppelt zählen)",
    "mail_tool_export": "Roh-Export aus dem Mail-Tool (Gesamt- statt eindeutige Aktionen)",
    "reference_abo": "Referenzblatt Abo-Entwicklung (nicht importiert)",
    "reference_salespages": "Referenzblatt Verkaufsseiten (nicht importiert)",
    "ignore": "Manuell als 'ignorieren' markiert",
}
MIN_SCORE = 0.7
MIN_MARGIN = 0.2


@dataclass
class TabClassification:
    workbook: str
    tab: str
    kind: str                      # Parser-Kind, ignore_*, oder "unknown"
    confidence: float
    reasons: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    manual: bool = False

    @property
    def status(self) -> str:
        if self.kind == "unknown":
            return "unbekannt"
        if self.kind in IMPORT_KINDS:
            return "importiert"
        return "ignoriert"


def structure_signature(rows: list[list[Any]]) -> str:
    """Hash der Kopfzeilen-Struktur (erste 3 nicht-leere Zeilen) -> Strukturänderungen erkennen."""
    heads = []
    for r in rows[:6]:
        txt = [norm_text(c) for c in r if isinstance(c, str)]
        if len(txt) >= 3:
            heads.append("|".join(txt))
        if len(heads) >= 1:
            break
    return hashlib.sha1("||".join(heads).encode()).hexdigest()[:12]


def classify(workbook: str, tab: str, rows: list[list[Any]], manual: dict[tuple[str, str], str] | None = None,
             expected_kinds: list[str] | None = None) -> TabClassification:
    sig = structure_signature(rows)
    manual = manual or {}
    mk = manual.get((workbook, tab.strip()))
    if mk:
        meta: dict[str, Any] = {}
        if mk in PARSERS:
            det = PARSERS[mk].detect(rows, tab)
            meta = det.meta
            if not meta and mk == "newsletter":
                return TabClassification(workbook, tab, "unknown", 0.0,
                                         ["Manuelle Zuordnung 'newsletter', aber keine lesbare Struktur"], {}, sig, True)
        return TabClassification(workbook, tab, mk, 1.0, ["Manuelle Zuordnung (Konfiguration)"], meta, sig, True)
    if not rows or all(all(c is None or (isinstance(c, str) and not c.strip()) for c in r) for r in rows):
        return TabClassification(workbook, tab, "ignore_template", 1.0, ["Leeres Tabellenblatt"], {}, sig)

    dets: list[Detection] = [p.detect(rows, tab) for p in PARSERS.values()]
    # Ignorier-Erkennungen mit hoher Sicherheit haben Vorrang (z.B. Steuerzellen-Blatt)
    ign = [d for d in dets if d.kind not in IMPORT_KINDS and d.score >= MIN_SCORE]
    if ign:
        best = max(ign, key=lambda d: d.score)
        return TabClassification(workbook, tab, best.kind, best.score, best.reasons, best.meta, sig)
    dets.sort(key=lambda d: d.score, reverse=True)
    best, second = dets[0], dets[1]
    reasons = list(best.reasons)
    if best.score >= MIN_SCORE and best.score - second.score >= MIN_MARGIN:
        if expected_kinds and best.kind not in expected_kinds:
            reasons.append(f"Hinweis: Typ '{best.kind}' ist in dieser Arbeitsmappe unüblich")
        return TabClassification(workbook, tab, best.kind, round(best.score, 2), reasons, best.meta, sig)
    reasons.append(f"Nicht eindeutig: bester Typ '{best.kind}' {best.score:.2f}, zweiter '{second.kind}' {second.score:.2f}")
    return TabClassification(workbook, tab, "unknown", round(best.score, 2), reasons, {"candidate": best.kind}, sig)

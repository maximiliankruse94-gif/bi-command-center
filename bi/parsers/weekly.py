"""Parser für Wochenstatistiken (ein Tab je Jahr, eine Zeile je ISO-KW)."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

import pandas as pd

from .base import Detection, Issue, ParseResult
from .common import cell, find_header_row, header_map, is_blank, norm_text, to_date, to_number

KIND = "weekly"
DATASET = "weekly"

FIELDS = {
    "umsatz_gesamt": ["umsatz gesamt"],
    "umsatz_gtk": ["gtk littlefreilich"],
    "umsatz_littlefreilich": ["littlefreilich"],
    "umsatz_gunnarkessler": ["gunnarkessler"],
    "umsatz_sonstige": ["wu", "ea"],
    "umsatz_copecart": ["copecart"],
    "zahlungen_stk": ["zahlungen stk"],
    "rueckgaben": ["rueckgaben"],
    "rueckgaben_stk": ["rueckgaben stk"],
    "werbekosten": ["werbekosten"],
    "buchkosten": ["buchkosten"],
    "verdienst": ["verdienst", "gewinn"],
    "aktive_abos": ["aktive abo s", "aktive abos"],
    "neue_abos": ["neue abo s", "neue abos"],
    "kuendigungen": ["kuendigungen"],
}


def detect(rows: list[list[Any]], tab: str) -> Detection:
    h = find_header_row(rows, ["kw", "datum von", "umsatz gesamt"])
    if h is None:
        return Detection(KIND, 0.0, ["Keine Kopfzeile mit 'KW', 'Datum von', 'Umsatz gesamt'"])
    reasons = [f"Kopfzeile in Zeile {h + 1} mit KW/Datum von/Umsatz gesamt"]
    score = 0.6
    hm = header_map(rows[h])
    kw_idx = hm["kw"][0]
    kws = [to_number(cell(r, kw_idx)) for r in rows[h + 1:h + 60]]
    kws = [k for k in kws if k is not None and 1 <= k <= 53]
    if len(kws) >= 3:
        score += 0.25
        reasons.append(f"{len(kws)} Kalenderwochen-Nummern")
    if re.fullmatch(r"\s*20\d\d\s*", tab):
        score += 0.1
        reasons.append("Tab-Name ist eine Jahreszahl (zusätzliches Indiz)")
    return Detection(KIND, min(score, 1.0), reasons, {"header_row": h})


def parse(rows: list[list[Any]], tab: str, workbook: str, header_row: int | None = None) -> ParseResult:
    issues: list[Issue] = []
    h = header_row if header_row is not None else find_header_row(rows, ["kw", "datum von", "umsatz gesamt"])
    hm = header_map(rows[h])
    idx = {f: next((hm[a][0] for a in al if a in hm), None) for f, al in FIELDS.items()}
    kw_idx, von_idx = hm["kw"][0], hm["datum von"][0]
    bis_idx = hm["bis"][0] if "bis" in hm else None
    tab_year = int(tab.strip()) if re.fullmatch(r"\s*20\d\d\s*", tab) else None
    out = []
    for i in range(h + 1, len(rows)):
        r = rows[i]
        kw = to_number(cell(r, kw_idx))
        if kw is None:
            continue  # 'Gesamt' etc.
        von, w = to_date(cell(r, von_idx))
        if von is None:
            continue  # künftige Woche ohne Daten
        # Maßgeblich: Tab-Jahr + KW-Nummer (Datumsangaben enthalten Tippfehler, z.B. '30.01.12', '31.23.23').
        expected = None
        if tab_year:
            try:
                expected = dt.date.fromisocalendar(tab_year, int(kw), 1)
            except ValueError:
                expected = None  # z.B. KW 53 in einem Jahr mit 52 ISO-Wochen
        sheet_ok = von.isocalendar()[2] == 1 and (expected is None or abs((von - expected).days) <= 3)
        if expected is not None and not sheet_ok:
            issues.append(Issue("warning", "kalenderwoche",
                                f"KW {int(kw)}/{tab_year}: Startdatum im Sheet '{cell(r, von_idx)}' passt nicht -> ISO-Montag {expected:%d.%m.%Y} verwendet",
                                workbook, tab, i + 1))
            von = expected
        elif expected is None and tab_year:
            issues.append(Issue("info", "kalenderwoche",
                                f"KW {int(kw)} existiert im ISO-Jahr {tab_year} nicht -> Woche über Startdatum {von:%d.%m.%Y} bestimmt "
                                f"(ISO {von.isocalendar()[0]}-KW{von.isocalendar()[1]})", workbook, tab, i + 1))
        bis = von + dt.timedelta(days=6)
        iso_y, iso_w, _ = von.isocalendar()
        rec: dict[str, Any] = {"iso_year": iso_y, "iso_week": iso_w, "date_from": von, "date_to": bis, "kw_sheet": int(kw)}
        for f, j in idx.items():
            rec[f] = to_number(cell(r, j))
        if rec["umsatz_gesamt"] in (None, 0.0) and not rec.get("zahlungen_stk"):
            continue
        if tab_year and abs(iso_y - tab_year) > 1:
            issues.append(Issue("warning", "datum", f"KW {int(kw)} liegt im Jahr {iso_y}, Tab ist {tab_year}", workbook, tab, i + 1))
        rec["source_tab"] = tab.strip()
        rec["source_row"] = i + 1
        out.append(rec)
    df = pd.DataFrame(out)
    if not df.empty:
        d = df[df.duplicated(["iso_year", "iso_week"], keep=False)]
        for (y, w) in sorted(set(zip(d.iso_year, d.iso_week))):
            issues.append(Issue("error", "duplikat", f"KW {w}/{y} mehrfach -> erster Eintrag verwendet", workbook, tab))
        df = df.drop_duplicates(["iso_year", "iso_week"], keep="first")
    return ParseResult(DATASET, df, issues)

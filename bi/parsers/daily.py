"""Parser für Tagesstatistiken (ein Tab je Monat, eine Zeile je Tag).

Die Spaltenstruktur hat sich zwischen 2020 und 2026 mehrfach verändert
(18 -> 94 Spalten). Zuordnung erfolgt deshalb ausschließlich über
Spaltenüberschriften, nie über feste Positionen.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .base import Detection, Issue, ParseResult
from .common import (cell, find_header_row, header_map, is_blank, norm_text,
                     parse_month_label, to_date, to_number)

KIND = "daily"
DATASET = "daily"

# kanonisches Feld -> mögliche (normalisierte) Überschriften, in Prioritätsreihenfolge
FIELDS: dict[str, list[str]] = {
    "umsatz_gtk": ["umsatz gtk"],
    "umsatz_littlefreilich": ["umsatz littlefreilich"],
    "umsatz_gunnarkessler": ["umsatz gunnarkessler"],
    "umsatz_sonstige": ["umsatz wu", "umsatz ea"],
    "umsatz_gesamt": ["umsatz gesamt"],
    "rueckgaben": ["rueckgaben netto", "rueckgaben"],
    "ruecklastschriften": ["ruecklastschriften"],
    "netto_umsatz_sheet": ["netto umsatz"],
    "werbung_gesamt": ["werbung gesamt"],
    "kosten_gesamt_sheet": ["kosten gesamt"],
    "buchkosten": ["buchkosten"],
    "verdienst_sheet": ["verdienst", "gewinn"],
    "einmalzahlung": ["umsatz einmalzahlungen"],
    "abo_start": ["umsatz abo start"],
    "abo_wiederkehrend": ["umsatz abo"],
    "rate_start": ["umsatz rate 1"],
    "rate_wiederkehrend": ["umsatz rate"],
    "bemerkung": ["bemerkungen"],
}
import datetime as _dt
_ONE_DAY = _dt.timedelta(days=1)
REVENUE_PARTS = ["umsatz_gtk", "umsatz_littlefreilich", "umsatz_gunnarkessler", "umsatz_sonstige"]
SPLIT_PARTS = ["einmalzahlung", "abo_start", "abo_wiederkehrend", "rate_start", "rate_wiederkehrend"]


def _tab_month(tab: str) -> tuple[int | None, int | None]:
    return parse_month_label(tab.strip())


def _header_row(rows: list[list[Any]]) -> int | None:
    h = find_header_row(rows, ["tag", "umsatz gesamt"])
    return h if h is not None else find_header_row(rows, ["umsatz gtk", "umsatz gesamt"])


def _date_col(rows: list[list[Any]], h: int, hm: dict) -> int:
    """Spalte 'Tag' – oder (falls Überschrift fehlt) die Spalte mit den meisten Datumswerten."""
    body = rows[h + 1:h + 35]
    def frac(j): return sum(1 for r in body if to_date(cell(r, j))[0]) / max(len(body), 1)
    if "tag" in hm and frac(hm["tag"][0]) >= 0.3:
        return hm["tag"][0]
    return max(range(0, 3), key=frac)


def detect(rows: list[list[Any]], tab: str) -> Detection:
    reasons: list[str] = []
    score = 0.0
    if any(norm_text(c).startswith("steuerzelle") for r in rows[:3] for c in r):
        return Detection("ignore_dashboard", 0.95, ["Enthält 'Steuerzelle' -> Formular-/Anzeigeblatt, keine Rohdaten"])
    h = _header_row(rows)
    if h is None:
        return Detection(KIND, 0.0, ["Keine Kopfzeile mit 'Umsatz Gesamt' + Tag/Umsatzkonten"])
    hm = header_map(rows[h])
    score += 0.45
    reasons.append(f"Kopfzeile in Zeile {h + 1} mit 'Umsatz Gesamt'")
    if any(k in hm for k in ("umsatz gtk", "umsatz einmalzahlungen", "rueckgaben netto")):
        score += 0.15
        reasons.append("Umsatzspalten (GTK/Einmalzahlungen/Rückgaben) vorhanden")
    tag_idx = _date_col(rows, h, hm)
    dates = [to_date(cell(r, tag_idx))[0] for r in rows[h + 1:h + 40]]
    dates = [d for d in dates if d]
    rev_idx = hm["umsatz gesamt"][0]
    filled = [r for r in rows[h + 1:h + 40] if to_number(cell(r, rev_idx)) not in (None, 0.0)]
    if len(dates) >= 5:
        score += 0.25
        reasons.append(f"{len(dates)} Tagesdaten in Spalte 'Tag'")
        months = {(d.year, d.month) for d in dates}
        if len(months) <= 2:
            score += 0.05
    y, m = _tab_month(tab)
    if y and m:
        score += 0.1
        reasons.append("Tab-Name entspricht Monatsmuster (zusätzliches Indiz)")
    if not filled or norm_text(tab).startswith("muster") or "vorlage" in norm_text(tab):
        return Detection("ignore_template", 0.9, reasons + ["Keine Umsatzwerte bzw. Vorlage -> nicht importiert"])
    return Detection(KIND, min(score, 1.0), reasons, {"header_row": h})


def parse(rows: list[list[Any]], tab: str, workbook: str, header_row: int | None = None) -> ParseResult:
    issues: list[Issue] = []
    h = header_row if header_row is not None else _header_row(rows)
    hm = header_map(rows[h])
    idx: dict[str, int | None] = {}
    for f, aliases in FIELDS.items():
        idx[f] = next((hm[a][0] for a in aliases if a in hm), None)
    tag_idx = _date_col(rows, h, hm)
    exp_y, exp_m = _tab_month(tab)
    has_werbung = idx["werbung_gesamt"] is not None

    out = []
    seen: set = set()
    prev = None
    all_counts: dict = {}
    for r in rows[h + 1:]:
        dd = to_date(cell(r, tag_idx), exp_y, exp_m)[0]
        if dd:
            all_counts[dd] = all_counts.get(dd, 0) + 1
    for i in range(h + 1, len(rows)):
        r = rows[i]
        raw_date = cell(r, tag_idx)
        if is_blank(raw_date):
            continue
        d, warn = to_date(raw_date, exp_y, exp_m)
        if d is None:
            if isinstance(raw_date, str) and re.search(r"\d{1,2}\.\d{1,2}\.", raw_date):
                issues.append(Issue("warning", "datum", f"Unlesbares Datum '{raw_date}'", workbook, tab, i + 1))
            continue
        if warn:
            issues.append(Issue("warning", "datum", warn, workbook, tab, i + 1))
        # Doppeltes Datum, aber Folgetag des Vorgängers fehlt -> Tippfehler, Zeilenposition maßgeblich
        if (all_counts.get(d, 0) > 1 or d in seen) and prev is not None and d != prev + _ONE_DAY:
            nxt = prev + _ONE_DAY
            if nxt not in seen and nxt not in all_counts and nxt.month == d.month:
                issues.append(Issue("warning", "datum",
                                    f"Datum '{raw_date}' doppelt -> nach Zeilenreihenfolge als {nxt:%d.%m.%Y} interpretiert",
                                    workbook, tab, i + 1))
                d = nxt
        seen.add(d)
        prev = d
        rec: dict[str, Any] = {"date": d}
        for f, j in idx.items():
            if f == "bemerkung":
                v = cell(r, j)
                rec[f] = None if is_blank(v) else str(v).strip()
            else:
                rec[f] = to_number(cell(r, j))
        parts = [rec[p] for p in REVENUE_PARTS if rec.get(p) is not None]
        if rec["umsatz_gesamt"] in (None, 0.0) and not any(parts):
            # Tag ohne Erfassung (Zukunft oder Lücke) -> KEIN Datensatz (fehlend != 0)
            continue
        # --- abgeleitete, einheitliche Kennzahlen -----------------------------
        rueck = rec["rueckgaben"] or 0.0
        rl = rec["ruecklastschriften"] or 0.0
        rec["netto_umsatz"] = (rec["umsatz_gesamt"] or 0.0) - rueck - rl
        if has_werbung:
            rec["werbung"] = rec["werbung_gesamt"]
            rec["kosten_gesamt"] = rec["kosten_gesamt_sheet"]
        else:  # Layout 2020/2021: 'Kosten Gesamt' = Werbekosten
            rec["werbung"] = rec["kosten_gesamt_sheet"]
            kg = rec["kosten_gesamt_sheet"]
            rec["kosten_gesamt"] = None if kg is None else kg + (rec["buchkosten"] or 0.0)
        rec["verdienst"] = None if rec["kosten_gesamt"] is None else rec["netto_umsatz"] - rec["kosten_gesamt"]
        split = [rec[p] for p in SPLIT_PARTS]
        rec["split_summe"] = None if all(v is None for v in split) else sum(v or 0.0 for v in split)
        rec["erstzahlung"] = None if rec["split_summe"] is None else (
            (rec["einmalzahlung"] or 0) + (rec["abo_start"] or 0) + (rec["rate_start"] or 0))
        rec["wiederkehrend"] = None if rec["split_summe"] is None else (
            (rec["abo_wiederkehrend"] or 0) + (rec["rate_wiederkehrend"] or 0))
        rec["source_tab"] = tab.strip()
        rec["source_row"] = i + 1
        # --- Plausibilitätsprüfungen ------------------------------------------
        if parts and rec["umsatz_gesamt"] is not None and abs(sum(parts) - rec["umsatz_gesamt"]) > 1.0:
            issues.append(Issue("warning", "plausibilitaet",
                                f"{d:%d.%m.%Y}: Summe Zahlungskonten {sum(parts):,.2f} ≠ Umsatz Gesamt {rec['umsatz_gesamt']:,.2f}",
                                workbook, tab, i + 1))
        if rec["split_summe"] is not None and rec["umsatz_gtk"] is not None and abs(rec["split_summe"] - rec["umsatz_gtk"]) > 1.0:
            issues.append(Issue("info", "plausibilitaet",
                                f"{d:%d.%m.%Y}: Aufteilung Einmal/Abo/Rate ({rec['split_summe']:,.2f}) ≠ Umsatz GTK ({rec['umsatz_gtk']:,.2f})",
                                workbook, tab, i + 1))
        if rec["netto_umsatz_sheet"] is not None and abs(rec["netto_umsatz_sheet"] - rec["netto_umsatz"]) > 1.0:
            issues.append(Issue("warning", "plausibilitaet",
                                f"{d:%d.%m.%Y}: Netto Umsatz im Sheet {rec['netto_umsatz_sheet']:,.2f} ≠ berechnet {rec['netto_umsatz']:,.2f}",
                                workbook, tab, i + 1))
        out.append(rec)

    df = pd.DataFrame(out)
    if not df.empty:
        dups = df[df.duplicated("date", keep=False)]
        for d in sorted(set(dups["date"])):
            issues.append(Issue("error", "duplikat", f"Datum {d:%d.%m.%Y} mehrfach im Tab -> erster Eintrag verwendet", workbook, tab))
        df = df.drop_duplicates("date", keep="first")
        if exp_y and exp_m:
            import calendar
            n_days = calendar.monthrange(exp_y, exp_m)[1]
            present = {x.day for x in df["date"] if x.year == exp_y and x.month == exp_m}
            last = max(present) if present else 0
            missing = [dd for dd in range(1, last + 1) if dd not in present]
            if missing:
                issues.append(Issue("warning", "fehlende_tage",
                                    f"Fehlende Tage im Monat: {', '.join(map(str, missing))}", workbook, tab))
            if last < n_days:
                issues.append(Issue("info", "unvollstaendig",
                                    f"Monat bis Tag {last} erfasst ({n_days - last} Tage noch offen oder fehlend)", workbook, tab))
    return ParseResult(DATASET, df, issues)

"""Parser für Monatsstatistiken (ein Tab je Jahr, eine Zeile je Monat)."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .base import Detection, Issue, ParseResult
from .common import cell, find_header_row, header_map, is_blank, norm_text, parse_month_label, to_number

KIND = "monthly"
DATASET = "monthly"

FIELDS = {
    "zahlungen_stk": ["zahlungen stk"],
    "umsatz_brutto": ["umsatz brutto"],
    "umsatz_netto": ["umsatz netto"],
    "umsatz_gtk": ["gtk littlefreilich"],
    "umsatz_littlefreilich": ["littlefreilich"],
    "umsatz_gunnarkessler": ["gunnarkessler"],
    "umsatz_sonstige": ["wu", "e athleten", "ea"],
    "umsatz_copecart": ["copecart"],
    "rueckgaben_stk": ["rueckgaben stk"],
    "rueckgaben": ["rueckgaben netto"],
    "werbekosten": ["werbeausgaben"],
    "buchkosten": ["buchkosten"],
    "kosten_gesamt": ["kosten gesamt"],
    "verdienst": ["verdienst"],
    "brutto_einmalzahlung": ["brutto einmalzahlung"],
    "brutto_abo_start": ["brutto abo start"],
    "brutto_wiederkehrend": ["brutto wiederkehrend", "brutto abo wiederk"],
    "aktive_abos": ["aktive abo s", "aktive abos"],
    "neue_abos": ["neue abo s", "neue abos"],
    "kuendigungen": ["kuendigungen"],
    "bemerkung": ["bemerkung"],
}
POSITIVE_COSTS = ["rueckgaben", "werbekosten", "buchkosten", "kosten_gesamt"]  # im Sheet negativ geführt


def _tab_years(tab: str) -> list[int]:
    return [int(y) for y in re.findall(r"20\d\d", tab)]


def detect(rows: list[list[Any]], tab: str) -> Detection:
    h = find_header_row(rows, ["umsatz brutto", "umsatz netto"])
    if h is None:
        hn = find_header_row(rows, ["monat jahr", "wiederkehrend mtl"])
        if hn is not None:
            return Detection("reference_abo", 0.9, ["Abo-Entwicklung (Referenzblatt, derzeit nicht importiert)"])
        if any(norm_text(c).startswith("conversionrate lp") for r in rows[:2] for c in r):
            return Detection("reference_salespages", 0.9, ["Verkaufsseiten-Entwicklung (Referenzblatt, derzeit nicht importiert)"])
        return Detection(KIND, 0.0, ["Keine Kopfzeile mit 'Umsatz Brutto'/'Umsatz Netto'"])
    reasons = [f"Kopfzeile in Zeile {h + 1} mit Umsatz Brutto/Netto"]
    score = 0.6
    labels = [parse_month_label(cell(r, 0), None) for r in rows[h + 1:h + 16]]
    n = sum(1 for y, m in labels if m)
    if n >= 3:
        score += 0.25
        reasons.append(f"{n} Monatsbezeichnungen in Spalte A")
    if _tab_years(tab):
        score += 0.1
        reasons.append("Jahreszahl im Tab-Namen (zusätzliches Indiz)")
    return Detection(KIND, min(score, 1.0), reasons, {"header_row": h})


def parse(rows: list[list[Any]], tab: str, workbook: str, header_row: int | None = None) -> ParseResult:
    issues: list[Issue] = []
    h = header_row if header_row is not None else find_header_row(rows, ["umsatz brutto", "umsatz netto"])
    header = rows[h]
    hm = header_map(header)
    idx = {f: next((hm[a][0] for a in al if a in hm), None) for f, al in FIELDS.items()}
    years = _tab_years(tab)
    single_year = years[0] if len(years) == 1 else None

    # Produkt-Abo-Gruppen: "Aktive DMMC Abo's", danach Neue / Kündigungen
    prod_groups = []
    for j, c in enumerate(header):
        m = re.match(r"aktive (.+?) abo", norm_text(c))
        if m and m.group(1) not in ("",):
            prod_groups.append((m.group(1).upper(), j))

    out, prods = [], []
    for i in range(h + 1, len(rows)):
        r = rows[i]
        lab = cell(r, 0)
        if is_blank(lab):
            continue
        if isinstance(lab, str) and re.fullmatch(r"\s*20\d\d\s*:?\s*", lab):
            if lab.strip().endswith(":"):
                break  # Jahressumme -> darunter folgen nur Vergleichs-/Hilfszeilen
            continue  # Vorjahres-Vergleichszeile
        y, m = parse_month_label(lab, single_year)
        if m is None:
            continue
        if single_year and y != single_year:
            issues.append(Issue("warning", "datum",
                                f"Zeile '{lab}' im Tab '{tab.strip()}': Jahr {y} -> Tab-Jahr {single_year} verwendet",
                                workbook, tab, i + 1))
            y = single_year
        rec: dict[str, Any] = {"year": y, "month": m}
        for f, j in idx.items():
            v = cell(r, j)
            rec[f] = (None if is_blank(v) else str(v).strip()) if f == "bemerkung" else to_number(v)
        for f in POSITIVE_COSTS:
            if rec.get(f) is not None:
                rec[f] = abs(rec[f])
        if not rec.get("zahlungen_stk") and rec.get("umsatz_netto") in (None, 0.0):
            continue  # Monat noch nicht erfasst (Formelreste) -> fehlend, nicht 0
        rec["source_tab"] = tab.strip()
        rec["source_row"] = i + 1
        out.append(rec)
        for pname, j in prod_groups:
            a, n, k = (to_number(cell(r, j)), to_number(cell(r, j + 1)), to_number(cell(r, j + 2)))
            if a is None and n is None:
                continue
            prods.append({"year": y, "month": m, "product": pname, "aktive_abos": a, "neue_abos": n,
                          "kuendigungen": k, "source_tab": tab.strip()})
    df = pd.DataFrame(out)
    if not df.empty:
        d = df[df.duplicated(["year", "month"], keep=False)]
        for (y, m) in sorted(set(zip(d.year, d.month))):
            issues.append(Issue("error", "duplikat", f"Monat {m:02d}/{y} mehrfach -> erster Eintrag verwendet", workbook, tab))
        df = df.drop_duplicates(["year", "month"], keep="first")
    pdf = pd.DataFrame(prods)
    if not pdf.empty:
        pdf = pdf.drop_duplicates(["year", "month", "product"], keep="first")
        bad = pdf[(pdf.kuendigungen < 0) | (pdf.neue_abos < 0)]
        if len(bad):
            issues.append(Issue("warning", "plausibilitaet",
                                f"{len(bad)} Produkt-Abo-Werte mit negativen Neuabschlüssen/Kündigungen (vermutlich Formelfehler)",
                                workbook, tab))
    return ParseResult(DATASET, df, issues, extra={"abo_product": pdf})

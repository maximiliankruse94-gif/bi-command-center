"""Parser für Newsletter-Statistiken (ein Tab je Quartal, eine Zeile je Sendung).

Besonderheiten der Originaldaten (alle berücksichtigt):
  * Spaltenreihenfolge 'Tag, Datum' (bis 2023) bzw. 'Datum, Tag' (ab 2024)
  * Tabs ohne gültige Kopfzeile (z.B. '#REF!' in 'Mails 2024 Q4') -> Erkennung über Inhaltsmerkmale
  * Mehrere Sendungen je Tag mit identischem Campaignkey -> Campaignkey ist KEINE eindeutige ID
  * 'Clickrate' im Sheet = Klicks / Öffnungen (Click-to-Open-Rate)
  * 'Conversionrate' im Sheet = Käufe / Klicks
  * '-' bei Käufen/Umsatz = 0; leere Zelle = nicht erfasst
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any

import pandas as pd

from .base import Detection, Issue, ParseResult
from .common import (WEEKDAYS_DE, cell, find_header_row, header_map, is_blank, norm_text, to_date,
                     to_number, to_percent, to_time)

KIND = "newsletter"
DATASET = "newsletter"

FIELDS = {
    "datum": ["datum"],
    "wochentag_sheet": ["tag"],
    "uhrzeit": ["uhrzeit"],
    "produkt_raw": ["produkt"],
    "produkt_id": ["id"],
    "campaign_key": ["campaignkey"],
    "empfaenger": ["empfaenger"],
    "oeffnungen": ["oeffnungen"],
    "open_rate_sheet": ["oeffnungsrate"],
    "klicks": ["klicks"],
    "click_rate_sheet": ["clickrate"],
    "kaeufe": ["kaeufe"],
    "conv_rate_sheet": ["conversionrate"],
    "epc_sheet": ["epc"],
    "umsatz": ["gesamtumsatz netto", "gesamtumsatz"],
    "folgezahlungen": ["folgezahlung"],
    "folgeeinnahmen": ["folgeeinnahmen"],
    "betreff": ["betreff", "headline"],
}
# Standard-Layouts für Tabs ohne lesbare Kopfzeile (inhaltliche Erkennung)
LAYOUT_DATUM_FIRST = ["Datum", "Tag", "Uhrzeit", "Produkt", "ID", "Campaignkey", "Empfänger", "Öffnungen",
                      "Öffnungsrate", "Klicks", "Clickrate", "Käufe", "Conversionrate", "EPC",
                      "Gesamtumsatz (Netto)", "Folgezahlung", "Folgeeinnahmen", "Betreff"]
LAYOUT_TAG_FIRST = ["Tag", "Datum"] + LAYOUT_DATUM_FIRST[2:]
_WD = {w.lower() for w in WEEKDAYS_DE}


def _quarter_from_tab(tab: str) -> tuple[int | None, int | None]:
    m = re.search(r"(20\d\d)\s*Q\s*([1-4])", tab, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(20\d\d)", tab)
    return (int(m.group(1)), None) if m else (None, None)


def _content_layout(rows: list[list[Any]]) -> tuple[list[str] | None, int, list[str]]:
    """Ermittelt das Layout über Datentypen (für Tabs ohne Kopfzeile)."""
    sample = [r for r in rows[:40] if sum(not is_blank(c) for c in r) >= 8]
    if len(sample) < 5:
        return None, 0, []
    def frac(col: int, test) -> float:
        return sum(1 for r in sample if test(cell(r, col))) / len(sample)
    is_d = lambda v: to_date(v)[0] is not None
    is_wd = lambda v: isinstance(v, str) and v.strip().lower() in _WD
    is_t = lambda v: isinstance(v, (dt.time,)) or (isinstance(v, str) and re.match(r"^\d{1,2}:\d{2}$", v.strip()) is not None)
    is_n = lambda v: to_number(v) is not None
    for layout in (LAYOUT_DATUM_FIRST, LAYOUT_TAG_FIRST):
        di, ti = layout.index("Datum"), layout.index("Tag")
        checks = [frac(di, is_d), frac(ti, is_wd), frac(2, is_t), frac(6, is_n), frac(7, is_n)]
        if min(checks) >= 0.8:
            start = next(i for i, r in enumerate(rows) if is_d(cell(r, di)))
            return layout, start, [f"Datentypen passen zum Standard-Layout ({'Datum' if di == 0 else 'Tag'} zuerst): "
                                   f"Datum/Wochentag/Uhrzeit/Empfänger/Öffnungen je ≥80 %"]
    return None, 0, []


def detect(rows: list[list[Any]], tab: str) -> Detection:
    h = find_header_row(rows, ["empfaenger", "oeffnungen", "klicks"])
    y, q = _quarter_from_tab(tab)
    name_bonus = 0.1 if (y and "mail" in norm_text(tab)) else 0.0
    if h is not None:
        hm = header_map(rows[h])
        if "produkt" in hm and ("betreff" in hm or "headline" in hm) and "datum" in hm:
            return Detection(KIND, min(0.85 + name_bonus, 1.0),
                             [f"Kopfzeile in Zeile {h + 1}: Datum/Produkt/Empfänger/Öffnungen/Klicks/Betreff"],
                             {"header_row": h})
    he = find_header_row(rows, ["datum", "versendet", "geoeffnet", "klicks"])
    if he is not None:
        return Detection("newsletter_extract", 0.9,
                         ["Newsletter-Kennzahlen ohne Produkt/Betreff -> Auszug/Duplikat der Hauptdaten, nicht importiert"])
    if find_header_row(rows, ["gesendet", "geoeffnet", "geklickt"]) is not None:
        return Detection("mail_tool_export", 0.9,
                         ["Roh-Export aus dem Mail-Tool (gesendet/geöffnet/geklickt, Gesamtaktionen) -> nicht importiert"])
    layout, start, reasons = _content_layout(rows)
    if layout:
        return Detection(KIND, 0.75 + name_bonus, ["Keine gültige Kopfzeile"] + reasons,
                         {"layout": layout, "data_start": start})
    return Detection(KIND, 0.0, ["Keine Newsletter-Struktur erkannt"])


def product_key(raw: Any) -> str | None:
    if is_blank(raw):
        return None
    return re.sub(r"[\s\-_.]+", "", str(raw).strip().upper())


def make_send_id(d: dt.date, time: str | None, ckey: str | None, pkey: str | None, n: int) -> str:
    def _s(v):
        return "" if v is None or (isinstance(v, float) and v != v) else str(v)
    base = f"{d.isoformat()}|{_s(time)}|{_s(ckey).upper()}|{_s(pkey)}|{int(n)}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def parse(rows: list[list[Any]], tab: str, workbook: str, header_row: int | None = None,
          layout: list[str] | None = None, data_start: int | None = None) -> ParseResult:
    issues: list[Issue] = []
    if layout is None:
        h = header_row if header_row is not None else find_header_row(rows, ["empfaenger", "oeffnungen", "klicks"])
        header, start = rows[h], h + 1
    else:
        header, start = layout, data_start or 0
        issues.append(Issue("warning", "struktur",
                            "Kopfzeile fehlt/defekt (#REF!) -> Spalten über Inhaltsmerkmale zugeordnet. Bitte Kopfzeile im Sheet reparieren.",
                            workbook, tab, 1))
    hm = header_map(header)
    idx = {f: next((hm[a][0] for a in al if a in hm), None) for f, al in FIELDS.items()}
    # Inhaltliche Prüfung: steht in der 'Datum'-Spalte wirklich ein Datum? (Kopfzeilen teils vertauscht)
    body = [r for r in rows[start:start + 60] if to_number(cell(r, idx["empfaenger"]))]
    if body:
        def date_frac(j): return sum(1 for r in body if to_date(cell(r, j))[0]) / len(body)
        def wd_frac(j): return sum(1 for r in body if isinstance(cell(r, j), str) and cell(r, j).strip().lower() in _WD) / len(body)
        if idx["datum"] is None or date_frac(idx["datum"]) < 0.5:
            best = max(range(0, 4), key=date_frac)
            if date_frac(best) >= 0.5:
                issues.append(Issue("info", "struktur",
                                    f"Spalte 'Datum' enthält keine Datumswerte -> Datum aus Spalte {best + 1} gelesen (Kopfzeile vertauscht)",
                                    workbook, tab, 1))
                idx["datum"] = best
                wd = max(range(0, 4), key=wd_frac)
                idx["wochentag_sheet"] = wd if wd_frac(wd) >= 0.5 else None
    ty, tq = _quarter_from_tab(tab)
    out = []
    wd_mismatch: list[tuple[int, str]] = []
    for i in range(start, len(rows)):
        r = rows[i]
        raw_d = cell(r, idx["datum"])
        d, warn = to_date(raw_d)
        rec_n = to_number(cell(r, idx["empfaenger"]))
        if d is None:
            if not is_blank(raw_d) and rec_n:
                issues.append(Issue("warning", "datum", f"Unlesbares Datum '{raw_d}'", workbook, tab, i + 1))
            continue
        if warn:
            issues.append(Issue("warning", "datum", warn, workbook, tab, i + 1))
        if not rec_n:
            if not is_blank(cell(r, idx["betreff"])):
                issues.append(Issue("info", "fehlwert", f"Sendung {d:%d.%m.%Y} ohne Empfängerzahl -> übersprungen", workbook, tab, i + 1))
            continue
        rec: dict[str, Any] = {"send_date": d, "uhrzeit": to_time(cell(r, idx["uhrzeit"]))}
        for f in ("empfaenger", "oeffnungen", "klicks", "folgezahlungen", "folgeeinnahmen", "produkt_id"):
            rec[f] = to_number(cell(r, idx[f]))
        rec["kaeufe"] = to_number(cell(r, idx["kaeufe"]), dash_as_zero=True)
        rec["umsatz"] = to_number(cell(r, idx["umsatz"]), dash_as_zero=True)
        for f in ("open_rate_sheet", "click_rate_sheet", "conv_rate_sheet"):
            rec[f] = to_percent(cell(r, idx[f]))
        rec["epc_sheet"] = to_number(cell(r, idx["epc_sheet"]))
        praw = cell(r, idx["produkt_raw"])
        rec["produkt_raw"] = None if is_blank(praw) else str(praw).strip()
        rec["produkt_key"] = product_key(praw)
        ck = cell(r, idx["campaign_key"])
        rec["campaign_key"] = None if (is_blank(ck) or str(ck).strip() in ("-",) or str(ck).startswith("#")) else str(ck).strip()
        b = cell(r, idx["betreff"])
        rec["betreff"] = None if is_blank(b) else re.sub(r"\s+", " ", str(b)).strip()
        wd = cell(r, idx["wochentag_sheet"])
        if isinstance(wd, str) and wd.strip().lower() in _WD and wd.strip().lower() != WEEKDAYS_DE[d.weekday()].lower():
            wd_mismatch.append((i + 1, f"Wochentag '{wd.strip()}' passt nicht zu {d:%d.%m.%Y} ({WEEKDAYS_DE[d.weekday()]})"))
        rec_ck = cell(r, idx["campaign_key"])
        ckm = re.fullmatch(r"NL(\d{2})(\d{2})(\d{2})", str(rec_ck).strip()) if not is_blank(rec_ck) else None
        if ckm:
            try:
                ckd = dt.date(2000 + int(ckm.group(3)), int(ckm.group(2)), int(ckm.group(1)))
                if ckd != d:
                    issues.append(Issue("info", "datum", f"Campaignkey {rec_ck} deutet auf {ckd:%d.%m.%Y}, Versanddatum ist {d:%d.%m.%Y}",
                                        workbook, tab, i + 1))
            except ValueError:
                pass
        if ty and tq and (d.year != ty or (d.month - 1) // 3 + 1 != tq):
            issues.append(Issue("info", "datum", f"Sendung {d:%d.%m.%Y} liegt außerhalb des Tab-Quartals {ty} Q{tq}", workbook, tab, i + 1))
        # Plausibilität absoluter Zahlen
        o, k, kf = rec["oeffnungen"], rec["klicks"], rec["kaeufe"]
        if o is not None and o > rec_n:
            issues.append(Issue("warning", "plausibilitaet", f"{d:%d.%m.%Y}: Öffnungen ({o:.0f}) > Empfänger ({rec_n:.0f})", workbook, tab, i + 1))
        elif o is not None and o / rec_n > 0.8:
            issues.append(Issue("warning", "plausibilitaet", f"{d:%d.%m.%Y}: Öffnungsrate {o / rec_n:.0%} unplausibel hoch – Eingabefehler?",
                                workbook, tab, i + 1))
        if k is not None and o is not None and k > o:
            issues.append(Issue("warning", "plausibilitaet", f"{d:%d.%m.%Y}: Klicks ({k:.0f}) > Öffnungen ({o:.0f})", workbook, tab, i + 1))
        if kf is not None and k is not None and kf > k:
            issues.append(Issue("warning", "plausibilitaet",
                                f"{d:%d.%m.%Y}: Käufe ({kf:.0f}) > Klicks ({k:.0f}) – Käufe evtl. nicht nur aus Klicks dieser Mail",
                                workbook, tab, i + 1))
        if rec["umsatz"] and not kf:
            issues.append(Issue("info", "plausibilitaet", f"{d:%d.%m.%Y}: Umsatz ohne Käufe", workbook, tab, i + 1))
        # Prüfung der Sheet-Prozentformeln gegen absolute Zahlen
        if rec["open_rate_sheet"] is not None and o is not None and abs(rec["open_rate_sheet"] - o / rec_n) > 0.002:
            issues.append(Issue("info", "prozentformel",
                                f"{d:%d.%m.%Y}: Öffnungsrate im Sheet {rec['open_rate_sheet']:.2%} ≠ Öffnungen/Empfänger {o / rec_n:.2%}",
                                workbook, tab, i + 1))
        rec["source_tab"] = tab.strip()
        rec["source_row"] = i + 1
        out.append(rec)
    if len(wd_mismatch) > 5:
        issues.append(Issue("warning", "datum",
                            f"Spalte 'Tag' (Wochentag) in {len(wd_mismatch)} Zeilen falsch – vermutlich kopierte Formel. "
                            "Das System berechnet den Wochentag immer selbst aus dem Datum.", workbook, tab))
    else:
        issues += [Issue("warning", "datum", msg, workbook, tab, row) for row, msg in wd_mismatch]
    return ParseResult(DATASET, pd.DataFrame(out), issues)


def finalize(df: pd.DataFrame) -> tuple[pd.DataFrame, list[Issue]]:
    """Über alle Tabs: stabile IDs, Duplikaterkennung, Produkt-Normalisierung."""
    issues: list[Issue] = []
    if df.empty:
        return df, issues
    df = df.sort_values(["send_date", "uhrzeit", "source_tab", "source_row"], na_position="last").reset_index(drop=True)
    # exakte Duplikate (gleiche Sendung in mehreren Tabs/Zeilen)
    dkey = ["send_date", "uhrzeit", "produkt_key", "empfaenger", "oeffnungen", "klicks", "betreff"]
    dmask = df.duplicated(dkey, keep="first")
    for _, r in df[dmask].iterrows():
        issues.append(Issue("warning", "duplikat",
                            f"Sendung {r.send_date:%d.%m.%Y} {r.uhrzeit or ''} ({r.produkt_raw}) doppelt erfasst -> nur einmal gezählt",
                            "newsletter", r.source_tab, int(r.source_row)))
    df = df[~dmask].copy()
    df["dupn"] = df.groupby(["send_date", "uhrzeit", "campaign_key", "produkt_key"], dropna=False).cumcount()
    df["send_id"] = [make_send_id(r.send_date, r.uhrzeit, r.campaign_key, r.produkt_key, r.dupn) for r in df.itertuples()]
    df = df.drop(columns="dupn")
    return df, issues

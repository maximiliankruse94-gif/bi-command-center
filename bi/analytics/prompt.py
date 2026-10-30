"""AI Business Analyst – erzeugt einen vollständigen, dynamischen Analyse-Prompt (kein LLM im Betrieb)."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from . import attribution as A
from . import decomposition as D
from .metrics import compare, nl_aggregate, nl_summary, revenue_summary
from .model import Filters, Model, filter_daily, filter_nl
from .periods import Period

MAX_TABLE_ROWS = 40

TASK = """Du bist ein erfahrener CFO, Senior Business Controller und Data Scientist.

Analysiere die nachfolgenden Geschäftsdaten.

Deine Aufgabe ist es, die wichtigsten Entwicklungen zu identifizieren, Umsatzveränderungen quantitativ zu untersuchen und mögliche Ursachen herauszuarbeiten.

Unterscheide strikt zwischen:

1. Nachgewiesenen Fakten
2. Statistischen Auffälligkeiten
3. Erkennbaren Zusammenhängen
4. Plausiblen Hypothesen
5. Nicht belegbaren Annahmen

Untersuche insbesondere, ob Umsatzveränderungen durch Newsletter-Anzahl, Empfänger, Öffnungsraten, Klickraten, Conversion Rates, Bestellwerte, Erstzahlungen oder wiederkehrende Zahlungen erklärbar sind.

Identifiziere die fünf wichtigsten Erkenntnisse.

Erstelle konkrete Handlungsempfehlungen und priorisiere diese nach:

* Erwartetem Umsatzpotenzial
* Dringlichkeit
* Aufwand
* Datenlage
* Erfolgsmessbarkeit

Erstelle abschließend einen konkreten Maßnahmenplan für die nächsten 30 Tage.

Erfinde keine Zahlen und behaupte keine Ursachen, die durch die Daten nicht nachgewiesen werden können."""

MODE_QUICK = """ANALYSEMODUS: QUICK ANALYSIS
Antworte kompakt (max. ca. 1 Seite) mit:
1. Wichtigste Kennzahlen
2. Positive Entwicklungen
3. Negative Entwicklungen
4. Auffälligkeiten
5. Die drei wichtigsten Handlungsempfehlungen"""

MODE_DEEP = """ANALYSEMODUS: DEEP BUSINESS ANALYSIS
Gliedere deine Antwort in:
1. Executive Summary
2. Umsatzentwicklung
3. Newsletter-Performance
4. Betreffzeilen-Performance
5. Produktperformance
6. Funnel-Analyse
7. Erstzahlungen und wiederkehrende Zahlungen
8. Newsletter-Umsatzanteil
9. Revenue Decomposition
10. Historische Vergleiche
11. Auffälligkeiten
12. Mögliche Ursachen (jeweils mit Evidenzgrad 1–5 gemäß obiger Einteilung)
13. Konkrete Handlungsempfehlungen
14. Priorisierung der Maßnahmen
15. 30-Tage-Maßnahmenplan"""

DEFINITIONS = """DATENDEFINITIONEN (verbindlich für die Interpretation)
- Gesamtumsatz = Summe der Zahlungskonten aus den Tagesstatistiken (netto ohne USt, VOR Rückgaben). CopeCart-Umsätze sind nur in Wochen-/Monatsstatistiken enthalten.
- Erstzahlungen = Einmalzahlungen + Abo-Starts + Raten-Starts; wiederkehrend = Abo-Folgezahlungen + Folgeraten. Diese Aufteilung existiert nur für das Hauptzahlungskonto (GTK); Rest = „nicht aufgeschlüsselt“.
- Newsletter-Umsatz = Umsatzangabe je Sendung aus dem Newsletter-Tracking (netto), zugeordnet nach Versanddatum. Er ist KEIN Same-Day-Umsatz (das Attributionsfenster ist unbekannt); Anteile daher nur für Wochen/Monate/Jahre aussagekräftig.
- Raten sind gewichtet (Σ Zähler / Σ Nenner). Öffnungsrate = Öffnungen/Empfänger; Klickrate (CTOR) = Klicks/Öffnungen; CTR = Klicks/Empfänger; Conversion Rate = Käufe/Klicks; EPC = Umsatz/Klicks; Ø Bestellwert = Umsatz/Käufe.
- Öffnungsraten sind seit Apple Mail Privacy Protection (ab 20.09.2021) technisch überhöht und kein verlässliches Maß für menschliches Interesse.
- Fehlende Werte sind als „k. A.“ markiert und NICHT als 0 zu interpretieren.
- Revenue Decomposition: exakte Shapley-Zerlegung; beschreibt rechnerische Beiträge, keine Kausalität."""


def _eur(v):
    return "k. A." if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:,.0f} €".replace(",", ".")


def _pct(v, d=1):
    return "k. A." if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v * 100:.{d}f} %".replace(".", ",")


def _num(v):
    return "k. A." if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:,.0f}".replace(",", ".")


def _delta_row(name, d, fmt):
    pct = "k. A." if d.pct is None else f"{d.pct * 100:+.1f} %".replace(".", ",")
    absv = "k. A." if d.abs is None else (fmt(d.abs) if fmt is not _pct else f"{d.abs * 100:+.2f} Pp".replace(".", ","))
    return f"| {name} | {fmt(d.cur)} | {fmt(d.ref)} | {absv} | {pct} |"


def _table(df: pd.DataFrame, cols: dict[str, tuple[str, callable]]) -> str:
    head = "| " + " | ".join(lbl for lbl, _ in cols.values()) + " |"
    sep = "|" + "---|" * len(cols)
    rows = [head, sep]
    for _, r in df.iterrows():
        rows.append("| " + " | ".join(f(r[c]) if f else str(r[c]) for c, (_, f) in cols.items()) + " |")
    return "\n".join(rows)


def build_prompt(m: Model, p: Period, c: Period | None, f: Filters, mode: str = "quick") -> tuple[str, dict[str, pd.DataFrame]]:
    """Gibt (Prompt-Text, Detaildaten für CSV-Export) zurück."""
    details: dict[str, pd.DataFrame] = {}
    rc = revenue_summary(filter_daily(m.daily, p.start, p.end, f), p)
    rr = revenue_summary(filter_daily(m.daily, c.start, c.end, f), c) if c else None
    nc_df = filter_nl(m.nl, f, p.start, p.end)
    nr_df = filter_nl(m.nl, f, c.start, c.end) if c else nc_df.iloc[0:0]
    nc, nr = nl_summary(nc_df), (nl_summary(nr_df) if c else None)
    L = [TASK, "", MODE_DEEP if mode == "deep" else MODE_QUICK, "", "---", "", "# GESCHÄFTSDATEN", "",
         f"- Erstellt: {dt.datetime.now():%d.%m.%Y %H:%M} (Datenstand Tagesumsätze: {m.asof:%d.%m.%Y}, Newsletter: "
         f"{m.nl_asof:%d.%m.%Y})" if m.nl_asof else "",
         f"- Analysezeitraum: {p.label} ({p.fmt()})" + (" – laufender, unvollständiger Zeitraum" if p.partial else ""),
         f"- Vergleichszeitraum: {c.label} ({c.fmt()})" if c else "- Vergleichszeitraum: keiner",
         f"- Aktive Filter: {f.describe()}",
         "- Hinweis: Produkt-/Betreff-/Uhrzeitfilter wirken nur auf Newsletter-Kennzahlen; Umsätze sind nicht nach Produkt verfügbar."
         if f.active() else "", "", DEFINITIONS, ""]
    # Umsatz
    L += ["## 1. Umsatzübersicht", "", "| Kennzahl | Aktuell | Vergleich | Δ absolut | Δ % |", "|---|---|---|---|---|"]
    for k, lbl in [("umsatz_gesamt", "Gesamtumsatz"), ("umsatz_pro_tag", "Ø Umsatz pro Tag"), ("erstzahlung", "Erstzahlungen"),
                   ("wiederkehrend", "Wiederkehrende Zahlungen"), ("nicht_aufgeschluesselt", "Nicht aufgeschlüsselt"),
                   ("rueckgaben", "Rückgaben"), ("netto_umsatz", "Umsatz nach Rückgaben"), ("werbung", "Werbekosten"),
                   ("verdienst", "Verdienst (lt. Tagesstatistik)")]:
        L.append(_delta_row(lbl, compare(rc, rr, [k])[k], _eur))
    for k, lbl in [("anteil_erst", "Anteil Erstzahlungen (an aufgeschlüsseltem Umsatz)"),
                   ("anteil_wiederkehrend", "Anteil wiederkehrend")]:
        L.append(_delta_row(lbl, compare(rc, rr, [k])[k], _pct))
    L.append(f"\nDatenabdeckung: {rc['tage_mit_daten']}/{rc['tage_im_zeitraum']} Tage" +
             (f" (Vergleich {rr['tage_mit_daten']}/{rr['tage_im_zeitraum']})" if rr else ""))
    # Newsletter
    L += ["", "## 2. Newsletter-Performance", "", "| Kennzahl | Aktuell | Vergleich | Δ absolut | Δ % |", "|---|---|---|---|---|"]
    for k, lbl, fm in [("sendungen", "Anzahl Newsletter", _num), ("empfaenger", "Empfänger gesamt", _num),
                       ("empfaenger_pro_sendung", "Ø Empfänger je Newsletter", _num), ("oeffnungen", "Öffnungen", _num),
                       ("klicks", "Klicks", _num), ("kaeufe", "Käufe", _num), ("umsatz", "Newsletter-Umsatz", _eur),
                       ("open_rate", "Öffnungsrate", _pct), ("ctor", "Klickrate (Klicks/Öffnungen)", _pct),
                       ("ctr", "CTR (Klicks/Empfänger)", _pct), ("cr_click", "Conversion Rate (Käufe/Klicks)", _pct),
                       ("rev_per_recipient", "Umsatz je Empfänger", lambda v: "k. A." if v is None else f"{v:.3f} €".replace(".", ",")),
                       ("epc", "Umsatz je Klick (EPC)", lambda v: "k. A." if v is None else f"{v:.2f} €".replace(".", ",")),
                       ("aov", "Ø Umsatz je Kauf", _eur), ("umsatz_pro_sendung", "Ø Umsatz je Newsletter", _eur)]:
        L.append(_delta_row(lbl, compare(nc, nr, [k])[k], fm))
    if nc["sendungen_ohne_umsatzdaten"]:
        L.append(f"\nHinweis: {nc['sendungen_ohne_umsatzdaten']} Sendungen im Zeitraum ohne Umsatzangabe (nicht als 0 gewertet).")
    # Attribution
    share_c = (nc["umsatz"] / rc["umsatz_gesamt"]) if nc["umsatz"] and rc["umsatz_gesamt"] else None
    share_r = (nr["umsatz"] / rr["umsatz_gesamt"]) if rr and nr and nr["umsatz"] and rr["umsatz_gesamt"] else None
    L += ["", "## 3. Newsletter-Umsatzanteil (gemessen, nach Versanddatum)", "",
          f"- Aktuell: {_pct(share_c)} (Newsletter {_eur(nc['umsatz'])} von {_eur(rc['umsatz_gesamt'])})",
          f"- Vergleich: {_pct(share_r)}" if c else "",
          f"- Rechnerischer Restumsatz aktuell: {_eur(None if not rc['umsatz_gesamt'] else rc['umsatz_gesamt'] - (nc['umsatz'] or 0))}"]
    if f.active():
        L.append("- Achtung: Wegen aktiver Newsletter-Filter bezieht sich der Anteil nur auf die gefilterten Sendungen.")
    # Decomposition
    if c and len(nr_df) and len(nc_df):
        dec = D.decompose_newsletter(nr_df, nc_df)
        L += ["", "## 4. Revenue Decomposition Newsletter-Umsatz (Shapley, exakt)", "",
              f"Veränderung Newsletter-Umsatz: {_eur(dec['delta'])}", "",
              "| Faktor | Vergleich | Aktuell | Δ % | Beitrag in € |", "|---|---|---|---|---|"]
        for fct in dec["faktoren"]:
            fmt = _pct if fct["faktor"] in ("open_rate", "ctor", "cr_click") else _num
            L.append(f"| {fct['label']} | {fmt(fct['wert_ref'])} | {fmt(fct['wert_cur'])} | "
                     f"{_pct(fct['veraenderung_pct'])} | {_eur(fct['beitrag_eur'])} |")
        if dec.get("rest") is not None:
            L.append(f"| Nicht zerlegbarer Rest | | | | {_eur(dec['rest'])} |")
        L += [f"- {h}" for h in dec["hinweise"]]
        tot = D.decompose_total(rr, rc)
        L += ["", "Zerlegung Gesamtumsatz (additiv):", ""] + [f"- {t['komponente']}: {_eur(t['beitrag_eur'])}" for t in tot]
        pm = D.decompose_product_mix(nr_df, nc_df)
        L += [f"- Produktmix-Zerlegung Newsletter: Volumeneffekt {_eur(pm['volumen'])}, Mixeffekt {_eur(pm['mix'])}, "
              f"Performance-Effekt {_eur(pm['performance'])}"]
        L += ["", "Regelbasierte Prüfhinweise des Dashboards (Hypothesen, keine Ursachen):"] + \
             [f"- {h}" for h in D.diagnostic_hints(dec["faktoren"], tot, dec["delta"],
                                                   (rc["umsatz_gesamt"] or 0) - (rr["umsatz_gesamt"] or 0))]
    # Produkte
    if len(nc_df):
        pa = nl_aggregate(nc_df, ["produkt"]).sort_values("umsatz", ascending=False)
        details["produkte"] = pa
        L += ["", "## 5. Produkte (Newsletter-Kennzahlen im Analysezeitraum)", "",
              _table(pa.head(15), {"produkt": ("Produkt", None), "sendungen": ("Sendungen", _num), "umsatz": ("Umsatz", _eur),
                                   "open_rate": ("Öffnungsrate", _pct), "ctor": ("Klickrate", _pct), "cr_click": ("Conv.", _pct),
                                   "rev_per_recipient": ("€/Empf.", lambda v: "k. A." if pd.isna(v) else f"{v:.3f}".replace(".", ","))})]
        if len(pa) > 15:
            L.append(f"(+{len(pa) - 15} weitere Produkte – vollständig im CSV-Export)")
    # Wochentag/Uhrzeit
    if len(nc_df) >= 10:
        wd = nl_aggregate(nc_df, ["wochentag_nr", "wochentag"]).sort_values("wochentag_nr")
        L += ["", "## 6. Performance nach Wochentag", "",
              _table(wd, {"wochentag": ("Wochentag", None), "sendungen": ("Sendungen", _num), "open_rate": ("Öffnungsrate", _pct),
                          "ctor": ("Klickrate", _pct), "cr_click": ("Conv.", _pct), "umsatz_pro_sendung": ("Ø Umsatz/NL", _eur)})]
        zf = nl_aggregate(nc_df, ["zeitfenster"]).sort_values("zeitfenster")
        L += ["", "## 7. Performance nach Versand-Zeitfenster", "",
              _table(zf, {"zeitfenster": ("Uhrzeit", None), "sendungen": ("Sendungen", _num), "open_rate": ("Öffnungsrate", _pct),
                          "ctor": ("Klickrate", _pct), "umsatz_pro_sendung": ("Ø Umsatz/NL", _eur)})]
    # Sendungen
    sends = nc_df.sort_values("send_date")[["send_date", "uhrzeit", "wochentag", "produkt", "betreff", "empfaenger", "oeffnungen",
                                             "klicks", "kaeufe", "umsatz", "open_rate", "ctor", "cr_click"]]
    details["sendungen"] = sends
    if len(sends):
        if mode == "deep" and len(sends) <= MAX_TABLE_ROWS:
            L += ["", "## 8. Einzelne Newsletter-Sendungen", "",
                  _table(sends, {"send_date": ("Datum", lambda v: f"{v:%d.%m.%Y}"), "uhrzeit": ("Zeit", lambda v: v or "k. A."),
                                 "produkt": ("Produkt", None), "betreff": ("Betreff", lambda v: str(v or "")[:70].replace("|", "/")),
                                 "empfaenger": ("Empf.", _num), "open_rate": ("Öffn.", _pct), "ctor": ("Klick", _pct),
                                 "kaeufe": ("Käufe", _num), "umsatz": ("Umsatz", _eur)})]
        else:
            top = sends.sort_values("umsatz", ascending=False).head(10)
            flop = sends[sends.umsatz.notna()].sort_values("umsatz").head(10)
            fmt = {"send_date": ("Datum", lambda v: f"{v:%d.%m.%Y}"), "produkt": ("Produkt", None),
                   "betreff": ("Betreff", lambda v: str(v or "")[:70].replace("|", "/")), "open_rate": ("Öffn.", _pct),
                   "ctor": ("Klick", _pct), "umsatz": ("Umsatz", _eur)}
            L += ["", f"## 8. Top-10 Sendungen nach Umsatz (von {len(sends)}; alle Sendungen im CSV-Export)", "", _table(top, fmt),
                  "", "## 9. Schwächste 10 Sendungen nach Umsatz", "", _table(flop, fmt)]
    # Historie
    if mode == "deep":
        at = A.attribution_table(m.daily, m.nl, "jahr")
        L += ["", "## 10. Historischer Jahresvergleich", "",
              _table(at, {"label": ("Jahr", None), "umsatz_gesamt": ("Gesamtumsatz", _eur), "erstzahlung": ("Erstzahlungen", _eur),
                          "wiederkehrend": ("Wiederkehrend", _eur), "nl_umsatz": ("Newsletter-Umsatz", _eur),
                          "nl_anteil": ("NL-Anteil", _pct), "sendungen": ("Newsletter", _num)}),
              "(laufendes Jahr unvollständig)"]
        details["historie"] = at
    L += ["", "---", "Ende der Daten. Beginne jetzt mit der Analyse gemäß Aufgabenstellung und Analysemodus."]
    return "\n".join(x for x in L if x is not None), details

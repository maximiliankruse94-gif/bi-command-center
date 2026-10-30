"""Revenue Attribution – Newsletter-Umsatzanteil (transparent und ohne unbewiesene Annahmen).

Befund aus den Originaldaten (Prüfung im Datenqualitätsmodul):
  * Newsletter-Umsatz ('Gesamtumsatz (Netto)') wird je Sendung erfasst. An zahlreichen Tagen übersteigt
    der Newsletter-Umsatz der an diesem Tag versendeten Mails den gesamten GTK-Tagesumsatz. Er ist daher
    KEIN Same-Day-Umsatz, sondern ein über ein (unbekanntes) Attributionsfenster kumulierter Kampagnenumsatz.
  * Deshalb wird der Anteil NICHT auf Tagesebene berechnet, sondern nur für Wochen, Monate, Quartale und
    Jahre – zugeordnet nach Versanddatum. Randeffekte an Periodengrenzen sind möglich und werden benannt.
  * Restumsatz = Gesamtumsatz − gemessener Newsletter-Umsatz ist eine rein rechnerische Größe.
    Er ist NICHT gleichbedeutend mit „Umsatz ohne Newsletter-Einfluss“.

Kategorien:
  1. Gemessener Newsletter-Umsatz          – laut Newsletter-Tracking
  2. Rechnerischer Restumsatz              – Gesamtumsatz minus (1)
  3. Nicht zuordenbar                      – Umsatz an Tagen/Konten ohne Zahlungsart-Aufschlüsselung
  4. Nicht erfasst                         – Sendungen ohne Umsatzangabe (Anzahl ausgewiesen, nicht geschätzt)
"""
from __future__ import annotations

import pandas as pd

LEVEL_KEYS = {"woche": ["iso_jahr", "kw"], "monat": ["jahr", "monat"], "quartal": ["jahr", "quartal"], "jahr": ["jahr"]}


def attribution_table(daily: pd.DataFrame, nl: pd.DataFrame, level: str = "monat") -> pd.DataFrame:
    keys = LEVEL_KEYS[level]
    d = daily.groupby(keys).agg(umsatz_gesamt=("umsatz_gesamt", "sum"), erstzahlung=("erstzahlung", "sum"),
                                wiederkehrend=("wiederkehrend", "sum"), split=("split_summe", "sum"),
                                tage=("date", "nunique"), start=("date", "min"), ende=("date", "max")).reset_index()
    n = nl.groupby(keys).agg(nl_umsatz=("umsatz", "sum"), sendungen=("send_id", "count"),
                             ohne_umsatz=("umsatz", lambda s: int(s.isna().sum())),
                             folgeeinnahmen=("folgeeinnahmen", "sum"), kaeufe=("kaeufe", "sum")).reset_index()
    t = d.merge(n, on=keys, how="outer")
    t["nl_anteil"] = t.nl_umsatz / t.umsatz_gesamt
    t["restumsatz"] = t.umsatz_gesamt - t.nl_umsatz
    t["nicht_aufgeschluesselt"] = t.umsatz_gesamt - t.split
    t["nl_zu_erstzahlung"] = t.nl_umsatz / t.erstzahlung
    t["status"] = "ok"
    t.loc[t.umsatz_gesamt.isna(), "status"] = "keine Tagesumsätze"
    t.loc[t.nl_umsatz.isna(), "status"] = "keine Newsletter-Daten"
    t.loc[(t.nl_anteil > 1), "status"] = "unplausibel (NL > Gesamt)"
    if level == "monat":
        t["label"] = t.apply(lambda r: f"{int(r.jahr)}-{int(r.monat):02d}", axis=1)
    elif level == "quartal":
        t["label"] = t.apply(lambda r: f"{int(r.jahr)} Q{int(r.quartal)}", axis=1)
    elif level == "woche":
        t["label"] = t.apply(lambda r: f"KW{int(r.kw):02d}/{int(r.iso_jahr)}", axis=1)
    else:
        t["label"] = t.jahr.astype(int).astype(str)
    return t.sort_values(keys)


def same_day_check(daily: pd.DataFrame, nl: pd.DataFrame) -> dict:
    """Prüft, ob Newsletter-Umsatz plausibel Same-Day-Umsatz sein kann."""
    nd = nl.groupby("send_date")["umsatz"].sum()
    j = daily.set_index("date")[["umsatz_gesamt", "umsatz_gtk", "erstzahlung"]].join(nd.rename("nl"), how="inner")
    j = j[j.nl.notna()]
    return {
        "tage_mit_versand": int(len(j)),
        "tage_nl_gt_gesamt": int((j.nl > j.umsatz_gesamt).sum()),
        "tage_nl_gt_gtk": int((j.nl > j.umsatz_gtk).sum()),
        "tage_nl_gt_erst": int((j.nl > j.erstzahlung).sum()),
    }

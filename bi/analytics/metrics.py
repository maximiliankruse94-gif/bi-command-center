"""Kennzahlen-Berechnung (alle Formeln dokumentiert in docs/KENNZAHLEN.md).

Gewichtete Raten: Raten über mehrere Sendungen werden IMMER als Summe(Zähler)/Summe(Nenner)
berechnet (z.B. Öffnungsrate = Σ Öffnungen / Σ Empfänger), nie als Mittelwert der Einzelraten.
Sendungen mit fehlendem Zähler werden aus Zähler UND Nenner der jeweiligen Rate ausgeschlossen.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .periods import Period

REV_FIELDS = ["umsatz_gesamt", "netto_umsatz", "rueckgaben", "ruecklastschriften", "erstzahlung", "wiederkehrend",
              "einmalzahlung", "abo_start", "abo_wiederkehrend", "rate_start", "rate_wiederkehrend", "umsatz_gtk",
              "umsatz_littlefreilich", "umsatz_gunnarkessler", "umsatz_sonstige", "werbung", "buchkosten", "kosten_gesamt",
              "verdienst", "split_summe"]


def safe_div(a, b):
    try:
        if b is None or a is None or (isinstance(b, float) and np.isnan(b)) or b == 0:
            return None
        r = a / b
        return None if (isinstance(r, float) and np.isnan(r)) else r
    except ZeroDivisionError:
        return None


def revenue_summary(daily: pd.DataFrame, p: Period) -> dict:
    d = daily[(daily.date >= p.start) & (daily.date <= p.end)]
    out = {f: (float(d[f].sum(min_count=1)) if f in d and d[f].notna().any() else None) for f in REV_FIELDS}
    out["tage_mit_daten"] = int(d.date.nunique())
    out["tage_im_zeitraum"] = p.days
    out["abdeckung"] = out["tage_mit_daten"] / p.days if p.days else 0
    out["tage_mit_split"] = int(d.split_summe.notna().sum()) if "split_summe" in d else 0
    out["umsatz_pro_tag"] = safe_div(out["umsatz_gesamt"], out["tage_mit_daten"])
    out["anteil_erst"] = safe_div(out["erstzahlung"], out["split_summe"])
    out["anteil_wiederkehrend"] = safe_div(out["wiederkehrend"], out["split_summe"])
    out["nicht_aufgeschluesselt"] = (None if out["umsatz_gesamt"] is None or out["split_summe"] is None
                                     else out["umsatz_gesamt"] - out["split_summe"])
    return out


def nl_summary(nl: pd.DataFrame) -> dict:
    n = nl
    def ssum(c):
        return float(n[c].sum()) if len(n) and n[c].notna().any() else None
    def wrate(num, den):
        m = n[num].notna() & n[den].notna() & (n[den] > 0)
        return safe_div(float(n.loc[m, num].sum()), float(n.loc[m, den].sum())) if m.any() else None
    o = {
        "sendungen": int(len(n)),
        "versandtage": int(n.send_date.nunique()) if len(n) else 0,
        "empfaenger": ssum("empfaenger"), "oeffnungen": ssum("oeffnungen"), "klicks": ssum("klicks"),
        "kaeufe": ssum("kaeufe"), "umsatz": ssum("umsatz"), "folgeeinnahmen": ssum("folgeeinnahmen"),
        "open_rate": wrate("oeffnungen", "empfaenger"), "ctr": wrate("klicks", "empfaenger"),
        "ctor": wrate("klicks", "oeffnungen"), "cr_click": wrate("kaeufe", "klicks"),
        "cr_recipient": wrate("kaeufe", "empfaenger"), "rev_per_recipient": wrate("umsatz", "empfaenger"),
        "epc": wrate("umsatz", "klicks"), "aov": wrate("umsatz", "kaeufe"),
        "sendungen_ohne_umsatzdaten": int(n.umsatz.isna().sum()) if len(n) else 0,
        "sendungen_ohne_klickdaten": int(n.klicks.isna().sum()) if len(n) else 0,
    }
    o["umsatz_pro_sendung"] = safe_div(o["umsatz"], o["sendungen"] - o["sendungen_ohne_umsatzdaten"])
    o["empfaenger_pro_sendung"] = safe_div(o["empfaenger"], o["sendungen"])
    return o


@dataclass
class Delta:
    cur: float | None
    ref: float | None

    @property
    def abs(self):
        return None if self.cur is None or self.ref is None else self.cur - self.ref

    @property
    def pct(self):
        return None if self.abs is None or not self.ref else self.abs / abs(self.ref)


def compare(cur: dict, ref: dict | None, keys: list[str]) -> dict[str, Delta]:
    return {k: Delta(cur.get(k), (ref or {}).get(k)) for k in keys}


def coverage_note(cur: dict, ref: dict | None) -> str | None:
    """Warnt, wenn Zeiträume unterschiedlich vollständig sind (fehlende Daten != 0)."""
    if not ref:
        return None
    a, b = cur.get("abdeckung", 1), ref.get("abdeckung", 1)
    if a < 0.999 or b < 0.999:
        return (f"Datenabdeckung: aktueller Zeitraum {cur['tage_mit_daten']}/{cur['tage_im_zeitraum']} Tage, "
                f"Vergleich {ref['tage_mit_daten']}/{ref['tage_im_zeitraum']} Tage – Summen nur eingeschränkt vergleichbar; "
                f"Ø pro Tag ist aussagekräftiger.")
    return None


def daily_series(daily: pd.DataFrame, start: dt.date, end: dt.date, field: str = "umsatz_gesamt") -> pd.Series:
    d = daily[(daily.date >= start) & (daily.date <= end)].set_index("date")[field]
    idx = pd.date_range(start, end, freq="D").date
    return d.reindex(idx)  # fehlende Tage bleiben NaN (nicht 0!)


def aggregate(daily: pd.DataFrame, level: str, fields: list[str] | None = None) -> pd.DataFrame:
    """level: tag | woche | monat | quartal | jahr  (Wochen nach ISO-Kalender)."""
    fields = fields or ["umsatz_gesamt", "netto_umsatz", "erstzahlung", "wiederkehrend", "rueckgaben", "werbung", "verdienst"]
    d = daily.copy()
    keys = {"tag": ["date"], "woche": ["iso_jahr", "kw"], "monat": ["jahr", "monat"], "quartal": ["jahr", "quartal"],
            "jahr": ["jahr"]}[level]
    g = d.groupby(keys)
    out = g[fields].sum(min_count=1)
    out["tage"] = g["date"].nunique()
    out["start"] = g["date"].min()
    out = out.reset_index()
    if level == "woche":
        out["label"] = out.apply(lambda r: f"KW{int(r.kw):02d}/{int(r.iso_jahr)}", axis=1)
    elif level == "monat":
        out["label"] = out.apply(lambda r: f"{int(r.jahr)}-{int(r.monat):02d}", axis=1)
    elif level == "quartal":
        out["label"] = out.apply(lambda r: f"{int(r.jahr)} Q{int(r.quartal)}", axis=1)
    elif level == "jahr":
        out["label"] = out.jahr.astype(int).astype(str)
    else:
        out["label"] = out.date.astype(str)
    return out


def nl_aggregate(nl: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if nl.empty:
        return pd.DataFrame(columns=keys)
    rows = []
    for k, g in nl.groupby(keys, dropna=False, observed=True):
        s = nl_summary(g)
        if not isinstance(k, tuple):
            k = (k,)
        rows.append({**dict(zip(keys, k)), **s})
    return pd.DataFrame(rows)


def volatility(series: pd.Series) -> float | None:
    s = series.dropna()
    if len(s) < 7 or s.mean() == 0:
        return None
    return float(s.std() / s.mean())


def trend_slope(series: pd.Series) -> float | None:
    """Relative Steigung (pro Tag, in % des Mittelwerts) einer linearen Regression über fehlende Werte hinweg."""
    s = series.dropna()
    if len(s) < 14 or s.mean() == 0:
        return None
    x = np.array([(pd.Timestamp(i) - pd.Timestamp(s.index[0])).days for i in s.index], dtype=float)
    b = np.polyfit(x, s.values.astype(float), 1)[0]
    return float(b / s.mean())

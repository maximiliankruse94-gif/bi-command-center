"""Betreffzeilen-Intelligence – regelbasierte Merkmale und stichprobenbewusste Rankings.

Ranking-Methode (Stichprobengröße berücksichtigt):
  * Raten werden je Betreffzeile aus Summen gebildet und per Empirical-Bayes-Schätzung
    (Beta-Prior aus allen Sendungen) zum Gesamtmittel geschrumpft:
        geschätzte Rate = (Erfolge + α) / (Versuche + α + β)
    Kleine Stichproben (z.B. 100 Empfänger) werden dadurch stark zum Mittel gezogen,
    große (50.000) kaum. Zusätzlich werden 95-%-Wilson-Intervalle ausgewiesen.
  * Umsatz je Empfänger wird mit Gewicht n/(n+k) geschrumpft (k = Median-Empfängerzahl).
  * Merkmals-Effekte werden „bereinigt“ gemessen: Abweichung jeder Sendung vom
    gewichteten Mittel derselben Produkt-Jahr-Gruppe (kontrolliert Produkt- und
    Apple-MPP-Effekte), danach Mittelwert je Merkmal.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF⭐⬆↔-⇿✅❌❗]")
FEATURES: dict[str, tuple[str, re.Pattern]] = {
    "frage": ("Frage", re.compile(r"\?")),
    "zahl": ("Zahl", re.compile(r"\d")),
    "dringlichkeit": ("Dringlichkeit", re.compile(
        r"\b(dringend|sofort|heute|nur noch|letzte|letzter|letztes|endet|läuft ab|frist|deadline|jetzt|schnell|achtung|wichtig|eilt|morgen|bis \d)", re.I)),
    "neugier": ("Neugier", re.compile(
        r"(geheim|warum|wieso|was |unglaublich|überrasch|enthüll|deckt auf|verrat|niemand|kaum jemand|das hier|dies |so geht|trick|wahrheit|\.\.\.|…)", re.I)),
    "rabatt": ("Rabatt/Angebot", re.compile(r"(rabatt|%|gratis|kostenlos|sparen|spar|angebot|gutschein|deal|aktion|black friday|1\s?€|1 eu\b)", re.I)),
    "geld": ("Geld-/Ergebnisversprechen", re.compile(
        r"(€|\beu\b|euro|verdien|auszahlung|einkommen|gewinn|zahlungseingang|gutschrift|pro woche|pro tag|pro monat|reich|vermögen)", re.I)),
    "personalisierung": ("Personalisierung", re.compile(r"(%subscriber|\{vorname\}|\bdein|\bdu\b|\bdir\b|\bdich\b|für dich)", re.I)),
    "emoji": ("Emoji", EMOJI_RE),
    "pseudo_reply": ("Re:/Fwd:", re.compile(r"^\s*(re|aw|fwd|wg)\s*:", re.I)),
}


def tag_subject(s: str | None) -> dict[str, bool]:
    s = s if isinstance(s, str) else ""
    out = {k: bool(rx.search(s)) for k, (_, rx) in FEATURES.items()}
    n = len(EMOJI_RE.sub("", s).strip())
    out["laenge"] = "kurz (≤30)" if n <= 30 else ("mittel (31–50)" if n <= 50 else "lang (>50)")
    return out


def add_features(nl: pd.DataFrame) -> pd.DataFrame:
    if nl.empty:
        return nl
    tags = nl["betreff"].map(tag_subject).apply(pd.Series)
    return pd.concat([nl.drop(columns=[c for c in tags.columns if c in nl.columns]), tags], axis=1)


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def beta_prior(k: pd.Series, n: pd.Series) -> tuple[float, float]:
    """Method-of-moments Beta-Prior aus Einzelraten (gewichtet)."""
    m = n > 0
    p = (k[m] / n[m]).clip(1e-6, 1 - 1e-6)
    mu = float((k[m].sum()) / n[m].sum())
    var = float(np.average((p - mu) ** 2, weights=n[m])) if m.sum() > 1 else mu * (1 - mu) / 100
    var = max(var, 1e-8)
    common = mu * (1 - mu) / var - 1
    common = max(common, 1.0)
    return mu * common, (1 - mu) * common


def rank_subjects(nl: pd.DataFrame, min_recipients: int = 0) -> pd.DataFrame:
    if nl.empty:
        return pd.DataFrame()
    g = nl.groupby("betreff_norm").agg(
        sendungen=("send_id", "count"), empfaenger=("empfaenger", "sum"), oeffnungen=("oeffnungen", "sum"),
        klicks=("klicks", "sum"), kaeufe=("kaeufe", "sum"), umsatz=("umsatz", "sum"),
        produkte=("produkt", lambda s: ", ".join(sorted(set(s.dropna())))),
        erster_versand=("send_date", "min"), letzter_versand=("send_date", "max"),
        wochentage=("wochentag", lambda s: ", ".join(sorted(set(s))))).reset_index()
    g = g[(g.betreff_norm != "") & (g.empfaenger >= min_recipients)]
    if g.empty:
        return g
    a_o, b_o = beta_prior(g.oeffnungen, g.empfaenger)
    a_c, b_c = beta_prior(g.klicks, g.oeffnungen.where(g.oeffnungen > 0, np.nan).fillna(0))
    g["open_rate"] = g.oeffnungen / g.empfaenger
    g["ctor"] = g.klicks / g.oeffnungen.replace(0, np.nan)
    g["ctr"] = g.klicks / g.empfaenger
    g["cr_click"] = g.kaeufe / g.klicks.replace(0, np.nan)
    g["rev_per_recipient"] = g.umsatz / g.empfaenger
    g["open_rate_bereinigt"] = (g.oeffnungen + a_o) / (g.empfaenger + a_o + b_o)
    g["ctor_bereinigt"] = (g.klicks + a_c) / (g.oeffnungen + a_c + b_c)
    k = float(nl.empfaenger.median())
    mu_rev = float(nl.umsatz.sum() / nl.empfaenger[nl.umsatz.notna()].sum()) if nl.umsatz.notna().any() else 0
    w = g.empfaenger / (g.empfaenger + k)
    g["rev_per_1000_bereinigt"] = 1000 * (w * g.rev_per_recipient.fillna(mu_rev) + (1 - w) * mu_rev)
    ci = [wilson(o, n) for o, n in zip(g.oeffnungen, g.empfaenger)]
    g["open_ci_low"], g["open_ci_high"] = [c[0] for c in ci], [c[1] for c in ci]
    g["stichprobe"] = pd.cut(g.empfaenger, [-1, 5000, 30000, float("inf")], labels=["klein", "mittel", "groß"]).astype(str)
    return g


def feature_effects(nl: pd.DataFrame, metric: str = "open_rate") -> pd.DataFrame:
    """Bereinigter Effekt je Merkmal: Ø Abweichung vom Produkt-Jahr-Mittel (gewichtet nach Empfängern)."""
    num, den = {"open_rate": ("oeffnungen", "empfaenger"), "ctor": ("klicks", "oeffnungen"),
                "cr_click": ("kaeufe", "klicks"), "rev_per_recipient": ("umsatz", "empfaenger")}[metric]
    d = add_features(nl.dropna(subset=[num, den]))
    d = d[d[den] > 0]
    if d.empty:
        return pd.DataFrame()
    grp = d.groupby(["produkt", "jahr"])
    base = grp[num].transform("sum") / grp[den].transform("sum")
    d["resid"] = d[num] / d[den] - base
    d["w"] = d[den]
    rows = []
    for k, (label, _) in FEATURES.items():
        for flag in (True, False):
            s = d[d[k] == flag]
            if len(s) == 0:
                continue
            rows.append({"merkmal": label, "vorhanden": flag, "sendungen": len(s),
                         "rate": s[num].sum() / s[den].sum(),
                         "bereinigte_abweichung": float(np.average(s.resid, weights=s.w))})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    piv = out.pivot_table(index="merkmal", columns="vorhanden", values=["sendungen", "rate", "bereinigte_abweichung"])
    res = pd.DataFrame({
        "merkmal": piv.index,
        "sendungen_mit": piv[("sendungen", True)].values if ("sendungen", True) in piv else np.nan,
        "sendungen_ohne": piv[("sendungen", False)].values if ("sendungen", False) in piv else np.nan,
        "rate_mit": piv[("rate", True)].values if ("rate", True) in piv else np.nan,
        "rate_ohne": piv[("rate", False)].values if ("rate", False) in piv else np.nan,
        "effekt_bereinigt": (piv[("bereinigte_abweichung", True)] - piv[("bereinigte_abweichung", False)]).values
        if ("bereinigte_abweichung", True) in piv and ("bereinigte_abweichung", False) in piv else np.nan,
    })
    res["aussagekraft"] = np.where(res[["sendungen_mit", "sendungen_ohne"]].min(axis=1) >= 30, "belastbar",
                                   np.where(res[["sendungen_mit", "sendungen_ohne"]].min(axis=1) >= 10, "eingeschränkt", "zu wenig Daten"))
    return res.sort_values("effekt_bereinigt", ascending=False)

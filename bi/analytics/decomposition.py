"""Revenue Decomposition – mathematisch exakte Zerlegung von Umsatzveränderungen.

1) Newsletter-Umsatz (multiplikatives Kennzahlensystem, Shapley-Zerlegung)
       Umsatz = Sendungen × Empfänger/Sendung × Öffnungsrate × Klick-to-Open × Kaufrate(Klick) × Ø Bestellwert
   Die Shapley-Werte verteilen auch Wechselwirkungen fair auf die Faktoren; ihre Summe ergibt exakt die
   Veränderung des Modells (kein Doppelzählen). Sendungen ohne vollständige Funnel-Daten können nicht
   zerlegt werden -> ihr Umsatzbeitrag erscheint als „nicht zerlegbarer Rest“.

2) Produktmix (Shapley über Volumen, Mix, Performance)
       Umsatz = Sendungen gesamt × Σ_p Anteil_p × Umsatz je Sendung_p

3) Gesamtumsatz (additiv, exakt)
       Umsatz = Erstzahlungen + Wiederkehrende Zahlungen + nicht aufgeschlüsselte Konten

Wichtig: Eine Zerlegung beschreibt, WIE sich die Veränderung rechnerisch zusammensetzt – nicht WARUM.
"""
from __future__ import annotations

import itertools
import math

import pandas as pd

from .metrics import nl_summary

FACTOR_LABELS = {
    "sendungen": "Anzahl Newsletter",
    "empf_pro_sendung": "Empfänger je Newsletter",
    "open_rate": "Öffnungsrate",
    "ctor": "Klickrate (Klicks/Öffnungen)",
    "cr_click": "Conversion Rate (Käufe/Klicks)",
    "aov": "Ø Umsatz je Kauf",
}


def shapley_multiplicative(base: dict[str, float], cur: dict[str, float]) -> dict[str, float]:
    keys = list(base)
    n = len(keys)
    def f(S):
        return math.prod(cur[k] if k in S else base[k] for k in keys)
    out = {}
    for k in keys:
        others = [x for x in keys if x != k]
        tot = 0.0
        for r in range(n):
            w = math.factorial(r) * math.factorial(n - r - 1) / math.factorial(n)
            for S in itertools.combinations(others, r):
                S = set(S)
                tot += w * (f(S | {k}) - f(S))
        out[k] = tot
    return out


def _factors(nl: pd.DataFrame) -> tuple[dict | None, float, pd.DataFrame]:
    full = nl.dropna(subset=["empfaenger", "oeffnungen", "klicks", "kaeufe", "umsatz"])
    full = full[full.empfaenger > 0]
    if full.empty:
        return None, 0.0, full
    s = nl_summary(full)
    fac = {"sendungen": float(len(full)), "empf_pro_sendung": s["empfaenger"] / len(full), "open_rate": s["open_rate"],
           "ctor": s["ctor"], "cr_click": s["cr_click"], "aov": s["aov"]}
    if any(v is None or v <= 0 for v in fac.values()):
        return None, 0.0, full
    return fac, float(full.umsatz.sum()), full


def decompose_newsletter(nl_ref: pd.DataFrame, nl_cur: pd.DataFrame) -> dict:
    total_ref = float(nl_ref.umsatz.sum()) if len(nl_ref) else 0.0
    total_cur = float(nl_cur.umsatz.sum()) if len(nl_cur) else 0.0
    fb, rb, _ = _factors(nl_ref)
    fc, rc, _ = _factors(nl_cur)
    res = {"umsatz_ref": total_ref, "umsatz_cur": total_cur, "delta": total_cur - total_ref, "faktoren": [],
           "rest": None, "hinweise": []}
    if fb is None or fc is None:
        res["hinweise"].append("Zerlegung nicht möglich: In einem der Zeiträume fehlen Sendungen mit vollständigen "
                               "Funnel-Daten (Empfänger, Öffnungen, Klicks, Käufe, Umsatz) bzw. es gab keine Käufe.")
        return res
    phi = shapley_multiplicative(fb, fc)
    for k, v in phi.items():
        res["faktoren"].append({"faktor": k, "label": FACTOR_LABELS[k], "wert_ref": fb[k], "wert_cur": fc[k],
                                "veraenderung_pct": (fc[k] / fb[k] - 1) if fb[k] else None, "beitrag_eur": v})
    res["modell_delta"] = rc - rb
    res["rest"] = (total_cur - total_ref) - (rc - rb)
    if abs(res["rest"]) > 0.01:
        res["hinweise"].append(
            f"{res['rest']:+,.0f} € entfallen auf Sendungen mit unvollständigen Funnel-Daten und sind "
            "nicht in Faktoren zerlegbar (separat ausgewiesen).".replace(",", "."))
    return res


def decompose_product_mix(nl_ref: pd.DataFrame, nl_cur: pd.DataFrame) -> dict:
    """Volumen-, Mix- und Performance-Effekt (Shapley über 3 Faktorgruppen)."""
    def prep(n):
        n = n[n.umsatz.notna()]
        N = len(n)
        g = n.groupby("produkt").agg(s=("send_id", "count"), r=("umsatz", "sum"))
        g["w"] = g.s / N if N else 0
        g["v"] = g.r / g.s
        return N, g
    Nb, gb = prep(nl_ref)
    Nc, gc = prep(nl_cur)
    prods = sorted(set(gb.index) | set(gc.index))
    wb = gb.w.reindex(prods).fillna(0); wc = gc.w.reindex(prods).fillna(0)
    vb = gb.v.reindex(prods).fillna(0); vc = gc.v.reindex(prods).fillna(0)
    vb = vb.where(gb.s.reindex(prods).fillna(0) > 0, vc)   # neues Produkt: kein Performance-Effekt
    vc = vc.where(gc.s.reindex(prods).fillna(0) > 0, vb)   # eingestelltes Produkt: kein Performance-Effekt
    vals = {"N": (Nb, Nc), "w": (wb, wc), "v": (vb, vc)}
    def f(S):
        N = vals["N"][1] if "N" in S else vals["N"][0]
        w = vals["w"][1] if "w" in S else vals["w"][0]
        v = vals["v"][1] if "v" in S else vals["v"][0]
        return float(N * (w * v).sum())
    keys = ["N", "w", "v"]
    phi = {}
    for k in keys:
        others = [x for x in keys if x != k]
        tot = 0.0
        for r in range(3):
            wgt = math.factorial(r) * math.factorial(3 - r - 1) / math.factorial(3)
            for S in itertools.combinations(others, r):
                tot += wgt * (f(set(S) | {k}) - f(set(S)))
        phi[k] = tot
    # Produktbeiträge (Performance-Effekt je Produkt, Mittelwert-Gewichtung)
    per = pd.DataFrame({"produkt": prods, "anteil_ref": wb.values, "anteil_cur": wc.values,
                        "umsatz_je_sendung_ref": gb.v.reindex(prods).values, "umsatz_je_sendung_cur": gc.v.reindex(prods).values,
                        "sendungen_ref": gb.s.reindex(prods).fillna(0).values, "sendungen_cur": gc.s.reindex(prods).fillna(0).values,
                        "umsatz_ref": gb.r.reindex(prods).fillna(0).values, "umsatz_cur": gc.r.reindex(prods).fillna(0).values})
    per["delta"] = per.umsatz_cur - per.umsatz_ref
    return {"volumen": phi["N"], "mix": phi["w"], "performance": phi["v"], "summe": sum(phi.values()),
            "delta": f(set(keys)) - f(set()), "produkte": per.sort_values("delta")}


def decompose_total(rev_ref: dict, rev_cur: dict) -> list[dict]:
    """Additive Zerlegung des Gesamtumsatzes (Tagesdaten)."""
    def g(d, k):
        return d.get(k) or 0.0
    comps = [
        ("Erstzahlungen (Einmal + Abo-Start + Raten-Start, GTK)", g(rev_cur, "erstzahlung") - g(rev_ref, "erstzahlung")),
        ("Wiederkehrende Zahlungen (Abo + Raten, GTK)", g(rev_cur, "wiederkehrend") - g(rev_ref, "wiederkehrend")),
        ("Nicht nach Zahlungsart aufgeschlüsselt (weitere Konten / Rest)",
         g(rev_cur, "nicht_aufgeschluesselt") - g(rev_ref, "nicht_aufgeschluesselt")),
    ]
    return [{"komponente": k, "beitrag_eur": v} for k, v in comps]


def diagnostic_hints(fac: list[dict], rev_delta_split: list[dict] | None = None, nl_delta: float | None = None,
                     total_delta: float | None = None) -> list[str]:
    """Regelbasierte Prüfhinweise – formuliert als zu prüfende Hypothesen, nicht als Ursachen."""
    hints = []
    f = {x["faktor"]: x for x in fac}
    def ch(k):
        return f.get(k, {}).get("veraenderung_pct")
    o, c, cr, aov, s, e = ch("open_rate"), ch("ctor"), ch("cr_click"), ch("aov"), ch("sendungen"), ch("empf_pro_sendung")
    if o is not None and c is not None and cr is not None:
        if o >= -0.02 and c >= -0.02 and (cr < -0.1 or (aov is not None and aov < -0.1)):
            hints.append("Öffnungen und Klicks stabil/steigend, aber Kaufrate oder Bestellwert gesunken → Prüfbedarf bei "
                         "Angebot, Preis, Verkaufsseite, Checkout und Produkt-Fit.")
        if abs(o) < 0.05 and c < -0.1:
            hints.append("Öffnungsrate stabil, Klickrate gesunken → Inhalt, Angebot und Call-to-Action der Mails prüfen.")
        if o < -0.1:
            hints.append("Öffnungsrate gesunken → Betreffzeilen, Absender-Reputation/Zustellbarkeit und Listenqualität prüfen "
                         "(Achtung: Öffnungsraten sind durch Apple Mail Privacy Protection verzerrt).")
    if s is not None and s < -0.1:
        hints.append("Weniger Newsletter versendet → Teil der Veränderung ist rein volumenbedingt.")
    if e is not None and e < -0.05:
        hints.append("Weniger Empfänger je Newsletter → Listenwachstum, Abmeldungen und Segmentierung prüfen.")
    if nl_delta is not None and total_delta is not None and total_delta < 0 and nl_delta >= 0:
        hints.append("Gesamtumsatz gesunken, Newsletter-Umsatz jedoch stabil/gestiegen → Ursache eher außerhalb des "
                     "Newsletters (andere Akquisekanäle, Werbebudget, wiederkehrende Zahlungen, Nachfrage).")
    if rev_delta_split:
        e1 = rev_delta_split[0]["beitrag_eur"]; w1 = rev_delta_split[1]["beitrag_eur"]
        if total_delta and total_delta < 0 and w1 < 0 and abs(w1) > abs(e1):
            hints.append("Rückgang überwiegend bei wiederkehrenden Zahlungen → Abo-Bestand, Kündigungen und "
                         "Zahlungsausfälle prüfen.")
        if total_delta and total_delta < 0 and e1 < 0 and abs(e1) >= abs(w1):
            hints.append("Rückgang überwiegend bei Erstzahlungen → Neukundengewinnung (Newsletter UND Werbekanäle) prüfen.")
    if not hints:
        hints.append("Keine eindeutige Auffälligkeit im Kennzahlensystem – Veränderung verteilt sich auf mehrere Faktoren.")
    return hints

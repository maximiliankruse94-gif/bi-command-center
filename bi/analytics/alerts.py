"""Business Alerts & Frühwarnsystem (rein statistisch, regelbasiert).

Methoden
  * Tagesumsatz: Vergleich mit dem Mittel der letzten 8 GLEICHEN Wochentage (Wochenmuster) -> z-Score.
  * 7- und 28-Tage-Summen: Vergleich mit Vorperiode und Vorjahreszeitraum (saisonbereinigt).
  * Erstzahlungen / wiederkehrende Zahlungen: 28-Tage-Fenster vs. Vorjahr und vs. 13 vorherige 28-Tage-Fenster.
  * Newsletter-Raten: gewichtete Rate der letzten 30 Tage vs. Basis 180 Tage davor; Standardfehler
    über die Streuung der Einzelsendungen (nicht binomial – Sendungen streuen stärker als Zufall).
  * Produkte: Umsatz je Sendung (letzte 90 Tage) vs. Produkt-Historie, nur ab Mindestanzahl Sendungen.
Schweregrad: |z| ≥ 3 -> hoch, ≥ 2 -> mittel; darunter „normale Schwankung“ (nur informativ).
Strukturell = Abweichung sowohl kurzfristig (7/30 Tage) als auch mittelfristig (28/90 Tage) in gleicher Richtung.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .metrics import nl_summary


def _sev(z: float | None) -> str:
    if z is None or np.isnan(z):
        return "info"
    a = abs(z)
    return "hoch" if a >= 3 else ("mittel" if a >= 2 else "info")


def _alert(kennzahl, zeitraum, aktuell, referenz, z, erklaerungen, benoetigt, art="", einheit="€", referenz_text=""):
    absd = None if aktuell is None or referenz is None else aktuell - referenz
    pct = None if absd is None or not referenz else absd / abs(referenz)
    sev = _sev(z)
    return {"kennzahl": kennzahl, "zeitraum": zeitraum, "aktuell": aktuell, "referenz": referenz,
            "referenz_text": referenz_text, "abs": absd, "pct": pct, "z": z, "schweregrad": sev,
            "einordnung": art or ("strukturelle Auffälligkeit" if sev == "hoch" else
                                  "auffällige Abweichung" if sev == "mittel" else "normale Schwankung"),
            "richtung": "negativ" if (absd or 0) < 0 else "positiv", "moegliche_erklaerungen": erklaerungen,
            "benoetigte_informationen": benoetigt, "einheit": einheit}


def revenue_alerts(daily: pd.DataFrame, asof: dt.date) -> list[dict]:
    out = []
    d = daily.set_index("date").sort_index()
    if asof not in d.index:
        return out
    # 1) Tagesumsatz vs. gleiche Wochentage
    same = [asof - dt.timedelta(weeks=i) for i in range(1, 9)]
    hist = d.reindex(same)["umsatz_gesamt"].dropna()
    cur = d.loc[asof, "umsatz_gesamt"]
    if len(hist) >= 5 and hist.std() > 0:
        z = (cur - hist.mean()) / hist.std()
        out.append(_alert("Tagesumsatz", f"{asof:%d.%m.%Y}", cur, hist.mean(), z,
                           ["Einzelner Tag – hohe natürliche Streuung", "Versand/kein Versand eines Newsletters an diesem Tag",
                            "Zahlungseingänge können verzögert gebucht werden"],
                           ["Wurde an dem Tag ein Newsletter versendet?", "Werbebudget des Tages"],
                           referenz_text="Ø der letzten 8 gleichen Wochentage"))
    # 2) 7 / 28 Tage vs. Vorjahr und vs. Vorperiode
    for n, need in ((7, 6), (28, 25)):
        cur_p = d.loc[asof - dt.timedelta(days=n - 1):asof, "umsatz_gesamt"]
        if cur_p.count() < need:
            continue
        cur_s = cur_p.sum()
        # Historische Verteilung: gleiche Fenster der letzten 52 Wochen
        sums = []
        for k in range(1, 27):
            e = asof - dt.timedelta(days=7 * k)
            w = d.loc[e - dt.timedelta(days=n - 1):e, "umsatz_gesamt"]
            if w.count() >= need:
                sums.append(w.sum())
        if len(sums) >= 8:
            mu, sd = float(np.mean(sums)), float(np.std(sums, ddof=1))
            z = (cur_s - mu) / sd if sd else None
            out.append(_alert(f"Umsatz letzte {n} Tage", f"{asof - dt.timedelta(days=n - 1):%d.%m.} – {asof:%d.%m.%Y}",
                              cur_s, mu, z,
                              ["Saisonale Effekte (Ferien, Feiertage, Monatsanfang)", "Veränderung beim Newsletter-Volumen",
                               "Veränderung bei Werbeausgaben", "Veränderung wiederkehrender Zahlungen"],
                              ["Werbeausgaben im Zeitraum", "Kampagnen-/Launchkalender"],
                              referenz_text="Ø gleich langer Fenster der letzten 26 Wochen"))
        ly_e = asof - dt.timedelta(days=364)
        ly = d.loc[ly_e - dt.timedelta(days=n - 1):ly_e, "umsatz_gesamt"]
        if ly.count() >= need:
            ref = ly.sum()
            pct = (cur_s - ref) / ref if ref else None
            z = None if pct is None else pct / 0.12  # Daumenregel: ±12 % = 1 σ bei Jahresvergleichen (aus Historie kalibrierbar)
            out.append(_alert(f"Umsatz letzte {n} Tage vs. Vorjahr", f"bis {asof:%d.%m.%Y}", cur_s, ref, z,
                              ["Strukturelle Veränderung der Nachfrage", "Veränderung Abo-Bestand", "Produkt-/Angebotsmix"],
                              ["Werbeausgaben Vorjahr vs. aktuell", "Produkteinführungen im Vorjahr"],
                              referenz_text="gleiche Wochentage vor 52 Wochen"))
    # 3) Erst- vs. wiederkehrende Zahlungen (28 Tage)
    for field, label in (("erstzahlung", "Erstzahlungen"), ("wiederkehrend", "Wiederkehrende Zahlungen")):
        s = d[field]
        cur = s.loc[asof - dt.timedelta(days=27):asof]
        if cur.count() < 25:
            continue
        sums = []
        for k in range(1, 14):
            e = asof - dt.timedelta(days=28 * k)
            w = s.loc[e - dt.timedelta(days=27):e]
            if w.count() >= 25:
                sums.append(w.sum())
        if len(sums) >= 6:
            mu, sd = float(np.mean(sums)), float(np.std(sums, ddof=1))
            z = (cur.sum() - mu) / sd if sd else None
            expl = (["Weniger Neukunden aus Newsletter oder Werbung", "Angebots-/Preisänderungen", "Saisonalität"]
                    if field == "erstzahlung" else
                    ["Mehr Kündigungen oder weniger Abo-Starts in den Vormonaten", "Zahlungsausfälle/Rücklastschriften",
                     "Ende befristeter Abos/Ratenpläne"])
            out.append(_alert(f"{label} (28 Tage)", f"bis {asof:%d.%m.%Y}", float(cur.sum()), mu, z, expl,
                              ["Abo-Kündigungen/Neuabschlüsse (Monatsstatistik)", "Zahlungsanbieter-Report"],
                              referenz_text="Ø der 13 vorherigen 28-Tage-Fenster"))
    return out


def newsletter_alerts(nl: pd.DataFrame, asof: dt.date, min_sends: int = 8) -> list[dict]:
    out = []
    if nl.empty:
        return out
    cur = nl[(nl.send_date > asof - dt.timedelta(days=30)) & (nl.send_date <= asof)]
    base = nl[(nl.send_date > asof - dt.timedelta(days=210)) & (nl.send_date <= asof - dt.timedelta(days=30))]
    if len(cur) < min_sends or len(base) < 20:
        return out
    sc, sb = nl_summary(cur), nl_summary(base)
    specs = [
        ("open_rate", "oeffnungen", "empfaenger", "Öffnungsrate",
         ["Betreffzeilen", "Zustellbarkeit/Spam-Platzierung", "Listenqualität", "Apple MPP verfälscht Öffnungen"],
         ["Zustellraten/Bounces", "Spam-Beschwerden"]),
        ("ctor", "klicks", "oeffnungen", "Klickrate (Klicks/Öffnungen)",
         ["Inhalt/Call-to-Action", "Angebotsattraktivität", "Produktmix"], ["Mail-Inhalte/Varianten", "Linkplatzierung"]),
        ("cr_click", "kaeufe", "klicks", "Conversion Rate (Käufe/Klicks)",
         ["Verkaufsseite/Checkout", "Preis/Angebot", "Produkt-Fit der Zielgruppe"], ["Verkaufsseiten-Conversion", "Preisänderungen"]),
        ("rev_per_recipient", "umsatz", "empfaenger", "Newsletter-Umsatz je Empfänger",
         ["Kombination aus Öffnung, Klick, Conversion und Bestellwert", "Produktmix"], ["Attributionsfenster des Trackings"]),
    ]
    for key, num, den, label, expl, need in specs:
        x = base.dropna(subset=[num, den])
        x = x[x[den] > 0]
        if len(x) < 15 or sc[key] is None or sb[key] is None:
            continue
        rates = x[num] / x[den]
        se = float(rates.std(ddof=1)) / np.sqrt(max(cur[[num, den]].dropna().shape[0], 1))
        z = (sc[key] - sb[key]) / se if se else None
        out.append(_alert(f"{label} (30 Tage)", f"{asof - dt.timedelta(days=29):%d.%m.} – {asof:%d.%m.%Y}", sc[key], sb[key], z,
                          expl, need, einheit="%" if key != "rev_per_recipient" else "€",
                          referenz_text="gewichteter Ø der 180 Tage davor"))
    # Newsletter-Umsatz je Sendung
    cu = cur.umsatz.dropna(); bu = base.umsatz.dropna()
    if len(cu) >= min_sends and len(bu) >= 20 and bu.std() > 0:
        z = (cu.mean() - bu.mean()) / (bu.std() / np.sqrt(len(cu)))
        out.append(_alert("Ø Newsletter-Umsatz je Sendung (30 Tage)", f"bis {asof:%d.%m.%Y}", float(cu.mean()), float(bu.mean()), z,
                          ["Produktmix", "Conversion/Bestellwert", "Versandzeitpunkte"], ["Kampagnenplanung"],
                          referenz_text="Ø der 180 Tage davor"))
    return out


def product_alerts(nl: pd.DataFrame, asof: dt.date, min_recent: int = 4, min_hist: int = 8) -> list[dict]:
    out = []
    if nl.empty:
        return out
    recent = nl[(nl.send_date > asof - dt.timedelta(days=90)) & nl.umsatz.notna()]
    hist = nl[(nl.send_date <= asof - dt.timedelta(days=90)) & (nl.send_date > asof - dt.timedelta(days=730)) & nl.umsatz.notna()]
    for prod, g in recent.groupby("produkt"):
        h = hist[hist.produkt == prod]
        if len(g) < min_recent or len(h) < min_hist or h.umsatz.std() == 0:
            continue
        rc, rh = g.umsatz.sum() / g.empfaenger.sum() * 1000, h.umsatz.sum() / h.empfaenger.sum() * 1000
        per_send = h.umsatz / h.empfaenger * 1000
        se = per_send.std(ddof=1) / np.sqrt(len(g))
        z = (rc - rh) / se if se else None
        if abs(z or 0) >= 2:
            out.append(_alert(f"Produkt {prod}: Umsatz je 1.000 Empfänger", f"letzte 90 Tage ({len(g)} Sendungen)", rc, rh, z,
                              ["Angebot/Preis geändert", "Zielgruppensättigung (häufige Bewerbung)", "Saisonalität"],
                              ["Änderungen am Produkt/Angebot", "Bewerbungsfrequenz"],
                              referenz_text=f"Produkt-Historie ({len(h)} Sendungen, 90–730 Tage zurück)"))
    return out


def all_alerts(daily: pd.DataFrame, nl: pd.DataFrame, asof: dt.date) -> pd.DataFrame:
    rows = revenue_alerts(daily, asof) + newsletter_alerts(nl, asof) + product_alerts(nl, asof)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    order = {"hoch": 0, "mittel": 1, "info": 2}
    df["_o"] = df.schweregrad.map(order)
    return df.sort_values(["_o", "z"], key=lambda s: s if s.name == "_o" else -s.abs()).drop(columns="_o").reset_index(drop=True)

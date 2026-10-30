from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bi.analytics import attribution as A
from bi.analytics import decomposition as D
from bi.analytics import metrics as M
from bi.analytics.model import Filters, filter_daily, filter_nl

from .. import components as C
from .. import fmt
from ..theme import MUTED, SERIES

LV = {"Monat": "monat", "Quartal": "quartal", "Jahr": "jahr", "Woche": "woche"}


def render():
    ctx = st.session_state["ctx"]
    m, sel = ctx["m"], ctx["sel"]
    p, c, f = sel.period, sel.comp, sel.filters
    C.header("Revenue Attribution & Ursachenanalyse",
             "Wie viel Umsatz kommt messbar aus Newslettern – und warum verändert sich der Umsatz?")
    t1, t2, t3 = st.tabs(["Newsletter-Umsatzanteil", "Revenue Decomposition (Ursachenanalyse)", "Methodik & Datenprüfung"])
    with t1:
        _share(m)
    with t2:
        _decomp(m, p, c, f)
    with t3:
        _method(m)


def _share(m):
    lvl = st.radio("Ebene", list(LV), horizontal=True, key="att_lvl")
    t = A.attribution_table(m.daily, m.nl, LV[lvl])
    t = t[t.umsatz_gesamt.notna() | t.nl_umsatz.notna()]
    if lvl == "Woche":
        t = t.tail(78)
    fig = go.Figure()
    fig.add_bar(x=t.label, y=t.umsatz_gesamt, name="Gesamtumsatz", marker_color="#3a4150", hovertemplate="Gesamt: %{y:,.0f} €<extra></extra>")
    fig.add_bar(x=t.label, y=t.nl_umsatz, name="Newsletter-Umsatz (gemessen)", marker_color=SERIES[0],
                hovertemplate="Newsletter: %{y:,.0f} €<extra></extra>")
    fig.update_layout(barmode="overlay", title=f"Gesamtumsatz vs. Newsletter-Umsatz je {lvl}", yaxis_tickformat=",.0f", yaxis_title="€")
    C.chart(fig, "att_bars", 400)
    fig = go.Figure(go.Scatter(x=t.label, y=t.nl_anteil, mode="lines+markers", line=dict(color=SERIES[0], width=2), name="Newsletter-Anteil",
                               hovertemplate="%{x}: %{y:.1%}<extra></extra>"))
    if lvl in ("Monat", "Woche"):
        roll = t.set_index("label").nl_umsatz.rolling(12 if lvl == "Monat" else 13, min_periods=6).sum() / \
            t.set_index("label").umsatz_gesamt.rolling(12 if lvl == "Monat" else 13, min_periods=6).sum()
        fig.add_scatter(x=roll.index, y=roll.values, mode="lines", line=dict(color=MUTED, width=2, dash="dot"),
                        name="gleitend 12 Monate" if lvl == "Monat" else "gleitend 13 Wochen")
    fig.update_layout(title="Newsletter-Umsatzanteil (gemessen / Gesamtumsatz)", yaxis_tickformat=".0%")
    C.chart(fig, "att_share", 320)
    show = t[["label", "umsatz_gesamt", "nl_umsatz", "nl_anteil", "restumsatz", "erstzahlung", "wiederkehrend", "nicht_aufgeschluesselt",
              "nl_zu_erstzahlung", "sendungen", "ohne_umsatz", "tage", "status"]].rename(columns={
        "label": "Periode", "umsatz_gesamt": "Gesamtumsatz", "nl_umsatz": "1. NL-Umsatz gemessen", "nl_anteil": "NL-Anteil",
        "restumsatz": "2. Restumsatz (rechnerisch)", "erstzahlung": "Erstzahlungen", "wiederkehrend": "Wiederkehrend",
        "nicht_aufgeschluesselt": "3. nicht nach Zahlungsart zuordenbar", "nl_zu_erstzahlung": "NL ÷ Erstzahlungen",
        "sendungen": "Newsletter", "ohne_umsatz": "4. NL ohne Umsatzangabe", "tage": "Tage mit Umsatzdaten", "status": "Status"})
    st.dataframe(show.iloc[::-1].style.format({c: fmt.eur for c in ["Gesamtumsatz", "1. NL-Umsatz gemessen", "2. Restumsatz (rechnerisch)",
                                                                  "Erstzahlungen", "Wiederkehrend", "3. nicht nach Zahlungsart zuordenbar"]}
                                              | {"NL-Anteil": fmt.pct, "NL ÷ Erstzahlungen": fmt.pct, "Newsletter": fmt.num,
                                                 "4. NL ohne Umsatzangabe": fmt.num, "Tage mit Umsatzdaten": fmt.num}),
                 hide_index=True, use_container_width=True, height=420)
    C.download_buttons(show, f"attribution_{LV[lvl]}", "att_dl")
    st.markdown("""
<div class='panel'><b>So ist die Tabelle zu lesen</b><br>
<span class='note'>1. <b>Gemessener Newsletter-Umsatz</b> – Summe der Umsatzangaben aller in der Periode versendeten Newsletter.<br>
2. <b>Restumsatz</b> – Gesamtumsatz minus (1). Rein rechnerisch; enthält auch Umsatz, den Newsletter indirekt beeinflusst haben, und
Umsatz aus Werbung, Wiederkäufen und Abo-Verlängerungen.<br>
3. <b>Nicht zuordenbar</b> – Umsatz ohne Aufschlüsselung nach Zahlungsart (Nebenkonten).<br>
4. <b>NL ohne Umsatzangabe</b> – Sendungen, deren Umsatz nicht erfasst ist (nicht geschätzt).<br>
„NL ÷ Erstzahlungen“ ist eine Vergleichsgröße, keine gesicherte Zuordnung: ob Newsletter-Umsätze Erst- oder Folgezahlungen sind, ist
aus den Daten nicht ableitbar.</span></div>""", unsafe_allow_html=True)


def _decomp(m, p, c, f):
    if c is None:
        st.info("Bitte in der Seitenleiste einen Vergleichszeitraum wählen.")
        return
    st.markdown(f"**{p.label}** ({p.fmt()}) gegenüber **{c.label}** ({c.fmt()})" + (f" · Newsletter-Filter: {f.describe()}" if f.active() else ""))
    rc = M.revenue_summary(filter_daily(m.daily, p.start, p.end), p)
    rr = M.revenue_summary(filter_daily(m.daily, c.start, c.end), c)
    nc = filter_nl(m.nl, f, p.start, p.end)
    nr = filter_nl(m.nl, f, c.start, c.end)
    dt_total = (rc["umsatz_gesamt"] or 0) - (rr["umsatz_gesamt"] or 0)
    cn = M.coverage_note(rc, rr)
    if cn:
        st.warning(cn)
    C.kpi_row([C.kpi("Gesamtumsatz", rc["umsatz_gesamt"], rr["umsatz_gesamt"]),
               C.kpi("Newsletter-Umsatz (gemessen)", float(nc.umsatz.sum()), float(nr.umsatz.sum())),
               C.kpi("Erstzahlungen", rc["erstzahlung"], rr["erstzahlung"]),
               C.kpi("Wiederkehrend", rc["wiederkehrend"], rr["wiederkehrend"])], 4)

    st.markdown("##### 1 · Zerlegung des Gesamtumsatzes (additiv, exakt)")
    tot = D.decompose_total(rr, rc)
    _waterfall(rr["umsatz_gesamt"] or 0, [(x["komponente"], x["beitrag_eur"]) for x in tot], rc["umsatz_gesamt"] or 0,
               c.label, p.label, "dec_total")

    st.markdown("##### 2 · Zerlegung des Newsletter-Umsatzes (Shapley, multiplikativ)")
    dec = D.decompose_newsletter(nr, nc)
    if not dec["faktoren"]:
        for h in dec["hinweise"]:
            st.info(h)
    else:
        items = [(x["label"], x["beitrag_eur"]) for x in dec["faktoren"]]
        if dec.get("rest") and abs(dec["rest"]) > 0.5:
            items.append(("Nicht zerlegbarer Rest", dec["rest"]))
        _waterfall(dec["umsatz_ref"], items, dec["umsatz_cur"], c.label, p.label, "dec_nl")
        ft = pd.DataFrame(dec["faktoren"])
        isrt = ft.faktor.isin(["open_rate", "ctor", "cr_click"])
        ft["Vergleich"] = [fmt.pct(v, 2) if r else (fmt.eur(v) if k == "aov" else fmt.num(v)) for v, r, k in zip(ft.wert_ref, isrt, ft.faktor)]
        ft["Aktuell"] = [fmt.pct(v, 2) if r else (fmt.eur(v) if k == "aov" else fmt.num(v)) for v, r, k in zip(ft.wert_cur, isrt, ft.faktor)]
        st.dataframe(ft[["label", "Vergleich", "Aktuell", "veraenderung_pct", "beitrag_eur"]].rename(columns={
            "label": "Faktor", "veraenderung_pct": "Δ %", "beitrag_eur": "Beitrag zur Umsatzveränderung"}).style.format(
            {"Δ %": fmt.signed_pct, "Beitrag zur Umsatzveränderung": fmt.signed_eur}), hide_index=True, use_container_width=True)
        for h in dec["hinweise"]:
            st.caption("ℹ️ " + h)
        st.markdown("##### 3 · Produktmix-Effekt im Newsletter-Umsatz")
        pm = D.decompose_product_mix(nr, nc)
        c1, c2, c3 = st.columns(3)
        c1.metric("Volumeneffekt (mehr/weniger Newsletter)", fmt.signed_eur(pm["volumen"]))
        c2.metric("Mixeffekt (andere Produktgewichtung)", fmt.signed_eur(pm["mix"]))
        c3.metric("Performance-Effekt (Umsatz je NL je Produkt)", fmt.signed_eur(pm["performance"]))
        pr = pm["produkte"]
        st.dataframe(pr.rename(columns={"produkt": "Produkt", "sendungen_ref": "NL Vergleich", "sendungen_cur": "NL aktuell",
                                        "umsatz_ref": "Umsatz Vergleich", "umsatz_cur": "Umsatz aktuell", "delta": "Δ Umsatz",
                                        "umsatz_je_sendung_ref": "€/NL Vergleich", "umsatz_je_sendung_cur": "€/NL aktuell"})
                     [["Produkt", "NL Vergleich", "NL aktuell", "€/NL Vergleich", "€/NL aktuell", "Umsatz Vergleich", "Umsatz aktuell", "Δ Umsatz"]]
                     .style.format({"€/NL Vergleich": fmt.eur, "€/NL aktuell": fmt.eur, "Umsatz Vergleich": fmt.eur, "Umsatz aktuell": fmt.eur,
                                    "Δ Umsatz": fmt.signed_eur, "NL Vergleich": fmt.num, "NL aktuell": fmt.num}),
                     hide_index=True, use_container_width=True, height=300)
        st.markdown("##### 4 · Prüfhinweise (regelbasiert – Hypothesen, keine nachgewiesenen Ursachen)")
        for h in D.diagnostic_hints(dec["faktoren"], tot, dec["delta"], dt_total):
            st.markdown(f"- {h}")
    C.note("Die Zerlegung ist mathematisch exakt (Summe der Beiträge = Veränderung), beschreibt aber nur, <i>wie</i> sich die Veränderung "
           "rechnerisch zusammensetzt. Kausalität ist damit nicht nachgewiesen.")


def _waterfall(start, items, end, lab_ref, lab_cur, key):
    fig = go.Figure(go.Waterfall(
        x=[f"{lab_ref}"] + [i[0] for i in items] + [f"{lab_cur}"],
        measure=["absolute"] + ["relative"] * len(items) + ["total"],
        y=[start] + [i[1] for i in items] + [end],
        text=[fmt.eur(start, compact=True)] + [fmt.signed_eur(i[1]) for i in items] + [fmt.eur(end, compact=True)],
        textposition="outside", increasing=dict(marker=dict(color="#0ca30c")), decreasing=dict(marker=dict(color="#d03b3b")),
        totals=dict(marker=dict(color="#3987e5")), connector=dict(line=dict(color="#3a4150")),
        hovertemplate="%{x}: %{y:,.0f} €<extra></extra>"))
    fig.update_layout(yaxis_tickformat=",.0f", hovermode="closest", showlegend=False)
    C.chart(fig, key, 380)


def _method(m):
    chk = A.same_day_check(m.daily, m.nl)
    st.markdown(f"""
**Prüfung: Basieren Newsletter-Umsatz und Tagesumsatz auf derselben Umsatzdefinition?**

- Beide Werte sind **netto (ohne USt)**. Der Tagesumsatz ist die Summe der Zahlungskonten *vor* Rückgaben.
- An **{chk['tage_nl_gt_gesamt']} von {chk['tage_mit_versand']}** Versandtagen ist der Newsletter-Umsatz der an diesem Tag versendeten
  Mails **größer als der gesamte Tagesumsatz** (an {chk['tage_nl_gt_erst']} Tagen größer als die Erstzahlungen).
- **Schluss:** Der Newsletter-Umsatz ist ein über mehrere Tage kumulierter Kampagnenumsatz (Attributionsfenster unbekannt), kein
  Umsatz desselben Tages. Er kann zudem Käufe enthalten, die ohne Klick in genau dieser Mail entstanden sind.
- **Konsequenz im Dashboard:** Der Anteil wird nur für Wochen, Monate, Quartale und Jahre ausgewiesen (Zuordnung nach Versanddatum).
  An Periodengrenzen (z.B. Mail am 30. mit Käufen im Folgemonat) entstehen Randeffekte.
- Mehrere Newsletter am selben Tag werden einzeln gezählt; Mehrfachzuordnung desselben Kaufs zu zwei Mails kann aus den
  vorliegenden Daten weder ausgeschlossen noch korrigiert werden.
- Rückerstattungen sind im Newsletter-Umsatz nicht ausgewiesen; der Gesamtumsatz ist ebenfalls *vor* Rückgaben angegeben (gleiche Basis).

**Offene Punkte, die die Genauigkeit erhöhen würden:** Attributionsfenster und Attributionsmodell des Newsletter-Trackings
(z.B. Last-Click, 7 Tage), sowie ob „Gesamtumsatz (Netto)“ den vollen Vertragswert von Raten-/Abo-Käufen oder nur die erste Zahlung enthält.
""")

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bi.analytics import metrics as M
from bi.analytics.model import Filters, filter_nl

from .. import components as C
from .. import fmt
from ..theme import MUTED, SERIES


def _funnel_fig(s: dict, title: str):
    stages = ["Empfänger", "Öffnungen", "Klicks", "Käufe"]
    vals = [s["empfaenger"], s["oeffnungen"], s["klicks"], s["kaeufe"]]
    txt = [fmt.num(vals[0]), f"{fmt.num(vals[1])}<br>{fmt.pct(s['open_rate'])} der Empfänger",
           f"{fmt.num(vals[2])}<br>{fmt.pct(s['ctor'], 2)} der Öffnungen", f"{fmt.num(vals[3])}<br>{fmt.pct(s['cr_click'], 2)} der Klicks"]
    fig = go.Figure(go.Funnel(y=stages, x=vals, text=txt, textinfo="text", marker=dict(color=[SERIES[0], SERIES[2], SERIES[3], SERIES[1]]),
                              connector=dict(fillcolor="#1e222b"), hovertemplate="%{y}: %{x:,.0f}<extra></extra>"))
    fig.update_xaxes(type="log")
    fig.update_layout(title=title + f" → Umsatz {fmt.eur(s['umsatz'])}", hovermode="closest")
    return fig


def render():
    ctx = st.session_state["ctx"]
    m, sel = ctx["m"], ctx["sel"]
    p, c, f = sel.period, sel.comp, sel.filters
    C.header("Funnel Analytics", "Empfänger → Öffnungen → Klicks → Käufe → Umsatz · " + p.label + f" · Filter: {f.describe()}")
    cur = filter_nl(m.nl, f, p.start, p.end).dropna(subset=["empfaenger", "oeffnungen", "klicks"])
    ref = filter_nl(m.nl, f, c.start, c.end).dropna(subset=["empfaenger", "oeffnungen", "klicks"]) if c else None
    if cur.empty:
        C.empty_state("Keine Sendungen mit vollständigen Funnel-Daten im Zeitraum.")
        return
    sc = M.nl_summary(cur)
    sr = M.nl_summary(ref) if ref is not None and len(ref) else None
    c1, c2 = st.columns(2)
    with c1:
        C.chart(_funnel_fig(sc, p.label), "fun_cur", 380)
    with c2:
        if sr:
            C.chart(_funnel_fig(sr, c.label), "fun_ref", 380)
    st.markdown("##### Übergangsraten und Verluste")
    rows = []
    for lbl, a, b, key in [("Empfänger → Öffnung", "empfaenger", "oeffnungen", "open_rate"), ("Öffnung → Klick", "oeffnungen", "klicks", "ctor"),
                           ("Klick → Kauf", "klicks", "kaeufe", "cr_click")]:
        rows.append({"Übergang": lbl, "Rate aktuell": sc[key], "Rate Vergleich": sr[key] if sr else None,
                     "Δ (Prozentpunkte)": (sc[key] - sr[key]) if sr and sc[key] is not None and sr[key] is not None else None,
                     "Δ relativ": (sc[key] / sr[key] - 1) if sr and sr[key] else None,
                     "Verlust (absolut)": (sc[a] or 0) - (sc[b] or 0), "Verlust-Anteil": 1 - (sc[key] or 0)})
    t = pd.DataFrame(rows)
    st.dataframe(t.style.format({"Rate aktuell": lambda v: fmt.pct(v, 2), "Rate Vergleich": lambda v: fmt.pct(v, 2), "Δ (Prozentpunkte)": fmt.pp,
                                 "Δ relativ": fmt.signed_pct, "Verlust (absolut)": fmt.num, "Verlust-Anteil": fmt.pct}),
                 hide_index=True, use_container_width=True)
    worst = t.loc[t["Δ relativ"].idxmin()] if sr and t["Δ relativ"].notna().any() else None
    if worst is not None and worst["Δ relativ"] < -0.05:
        st.warning(f"Größte relative Verschlechterung gegenüber dem Vergleich: **{worst['Übergang']}** ({fmt.signed_pct(worst['Δ relativ'])}).")
    st.caption(f"Umsatz je Kauf: {fmt.eur(sc['aov'])}" + (f" (Vergleich {fmt.eur(sr['aov'])})" if sr else "") +
               f" · Umsatz je Empfänger: {fmt.eur(sc['rev_per_recipient'], 3)}" + (f" (Vergleich {fmt.eur(sr['rev_per_recipient'], 3)})" if sr else ""))

    st.markdown("##### Entwicklung der Übergangsraten")
    a = M.nl_aggregate(filter_nl(m.nl, f).dropna(subset=["klicks"]), ["ym"])
    a["x"] = pd.to_datetime(a.ym + "-01")
    fig = go.Figure()
    for i, (k, lbl) in enumerate([("open_rate", "Öffnung/Empfänger"), ("ctor", "Klick/Öffnung"), ("cr_click", "Kauf/Klick")]):
        fig.add_scatter(x=a.x, y=a[k], name=lbl, mode="lines", line=dict(color=SERIES[i], width=2),
                        hovertemplate=f"{lbl}: %{{y:.2%}}<extra></extra>")
    fig.update_layout(yaxis_tickformat=".0%", yaxis_type="log", title="Monatliche Übergangsraten (log. Skala)")
    C.chart(fig, "fun_trend", 360)

    st.markdown("##### Funnel je Produkt")
    pa = M.nl_aggregate(filter_nl(m.nl, Filters(**{**f.__dict__, "produkte": []}), p.start, p.end).dropna(subset=["klicks"]), ["produkt"])
    pa = pa[pa.sendungen >= 2].sort_values("rev_per_recipient", ascending=False)
    st.dataframe(pa[["produkt", "sendungen", "open_rate", "ctor", "cr_click", "aov", "rev_per_recipient"]].rename(columns={
        "produkt": "Produkt", "sendungen": "NL", "open_rate": "Öffnung", "ctor": "Klick/Öffnung", "cr_click": "Kauf/Klick",
        "aov": "€/Kauf", "rev_per_recipient": "€/Empfänger"}).style.format({"Öffnung": fmt.pct, "Klick/Öffnung": lambda v: fmt.pct(v, 2),
        "Kauf/Klick": lambda v: fmt.pct(v, 2), "€/Kauf": fmt.eur, "€/Empfänger": lambda v: fmt.eur(v, 3)}),
        hide_index=True, use_container_width=True)
    with st.expander("Berechnungslogik"):
        st.markdown("""
- **Datenbasis:** nur Sendungen mit Empfängern, Öffnungen und Klicks. Fehlende Käufe/Umsätze werden nicht als 0 gewertet.
- **Öffnungen/Klicks:** Die Newsletter-Statistik enthält *eindeutige* Öffnungen und Klicks (Abgleich mit dem Roh-Export
  „Tabellenblatt3“ zeigt dort höhere Gesamtaktionen, z.B. 21.254 statt 14.925 Öffnungen). Gesamtaktionen liegen nur für
  wenige Sendungen vor und werden daher nicht importiert.
- **Raten:** gewichtet = Σ Zähler / Σ Nenner über alle Sendungen.
- **Käufe** können Käufe enthalten, die nicht direkt über einen Klick dieser Mail entstanden (in einigen Sendungen Käufe > Klicks).
""")

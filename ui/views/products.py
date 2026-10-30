from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bi.analytics import metrics as M
from bi.analytics.model import Filters, filter_nl
from bi.parsers.common import WEEKDAYS_DE

from .. import components as C
from .. import fmt
from ..theme import MUTED, SERIES

COLS = {"produkt": "Produkt", "sendungen": "Newsletter", "empfaenger_pro_sendung": "Ø Empfänger", "open_rate": "Öffnungsrate",
        "ctor": "Klickrate", "cr_click": "Conv.-Rate", "umsatz": "Umsatz", "umsatz_pro_sendung": "Ø Umsatz/NL",
        "rev_per_recipient": "€/Empfänger", "epc": "EPC", "aov": "Ø €/Kauf", "kaeufe": "Käufe"}


def styled(df):
    return df[[c for c in COLS if c in df]].rename(columns=COLS).style.format({
        "Ø Empfänger": fmt.num, "Öffnungsrate": fmt.pct, "Klickrate": lambda v: fmt.pct(v, 2), "Conv.-Rate": lambda v: fmt.pct(v, 2),
        "Umsatz": fmt.eur, "Ø Umsatz/NL": fmt.eur, "€/Empfänger": lambda v: fmt.eur(v, 3), "EPC": lambda v: fmt.eur(v, 2),
        "Ø €/Kauf": fmt.eur, "Käufe": fmt.num})


def render():
    ctx = st.session_state["ctx"]
    m, sel = ctx["m"], ctx["sel"]
    p, c, f = sel.period, sel.comp, sel.filters
    C.header("Produkt Intelligence", f"{p.label}" + (f" vs. {c.label}" if c else "") + " · Newsletter-Kennzahlen je beworbenem Produkt")
    f_noprod = Filters(**{**f.__dict__, "produkte": []})
    cur = filter_nl(m.nl, f_noprod, p.start, p.end)
    ref = filter_nl(m.nl, f_noprod, c.start, c.end) if c else None
    min_n = st.slider("Mindestanzahl Newsletter je Produkt (Ranking)", 1, 20, 3, key="prod_min")
    t1, t2, t3, t4 = st.tabs(["Ranking", "Produkt A vs. B", "Historische Entwicklung", "Versandzeit & Betreff je Produkt"])
    with t1:
        a = M.nl_aggregate(cur, ["produkt"])
        if a.empty:
            C.empty_state("Keine Sendungen im Zeitraum.")
        else:
            if ref is not None and len(ref):
                b = M.nl_aggregate(ref, ["produkt"])[["produkt", "umsatz", "rev_per_recipient", "sendungen"]].rename(
                    columns={"umsatz": "umsatz_vgl", "rev_per_recipient": "rpr_vgl", "sendungen": "sendungen_vgl"})
                a = a.merge(b, on="produkt", how="left")
                a["Δ Umsatz %"] = a.umsatz / a.umsatz_vgl - 1
            a = a.sort_values("umsatz", ascending=False)
            big = a[a.sendungen >= min_n]
            fig = go.Figure(go.Bar(x=big.produkt, y=big.rev_per_recipient * 1000, marker_color=SERIES[0], customdata=big.sendungen,
                                   hovertemplate="%{x}: %{y:,.1f} € je 1.000 Empfänger (n=%{customdata})<extra></extra>"))
            fig.update_layout(title=f"Umsatz je 1.000 Empfänger (Produkte mit ≥ {min_n} Newslettern)", hovermode="closest",
                              xaxis={"categoryorder": "total descending"})
            C.chart(fig, "prod_rank", 360)
            sty = styled(a)
            st.dataframe(sty, hide_index=True, use_container_width=True)
            if "Δ Umsatz %" in a:
                st.caption("Vergleich zum Vergleichszeitraum: siehe CSV-Export (Spalten *_vgl).")
            C.download_buttons(a, "produkt_ranking", "prod_dl")
            C.note("Produktfilter in der Seitenleiste wird hier bewusst ignoriert, damit alle Produkte vergleichbar bleiben.")
    with t2:
        prods = m.nl.groupby("produkt").size().sort_values(ascending=False).index.tolist()
        c1, c2 = st.columns(2)
        pa = c1.selectbox("Produkt A", prods, index=0, key="pa")
        pb = c2.selectbox("Produkt B", prods, index=1 if len(prods) > 1 else 0, key="pb")
        rows = []
        for prod in (pa, pb):
            for lbl, per in (("aktuell", p), ("Vergleich", c)):
                if per is None:
                    continue
                s = M.nl_summary(filter_nl(m.nl, Filters(**{**f.__dict__, "produkte": [prod]}), per.start, per.end))
                rows.append({"produkt": prod, "zeitraum": f"{lbl}: {per.label}", **s})
            s = M.nl_summary(filter_nl(m.nl, Filters(**{**f.__dict__, "produkte": [prod]})))
            rows.append({"produkt": prod, "zeitraum": "gesamte Historie", **s})
        t = pd.DataFrame(rows)
        st.dataframe(styled(t).data.assign(Zeitraum=t.zeitraum).pipe(lambda x: x[["Zeitraum"] + [c for c in x.columns if c != "Zeitraum"]])
                     .style.format({"Ø Empfänger": fmt.num, "Öffnungsrate": fmt.pct, "Klickrate": lambda v: fmt.pct(v, 2),
                                    "Conv.-Rate": lambda v: fmt.pct(v, 2), "Umsatz": fmt.eur, "Ø Umsatz/NL": fmt.eur,
                                    "€/Empfänger": lambda v: fmt.eur(v, 3), "EPC": lambda v: fmt.eur(v, 2), "Ø €/Kauf": fmt.eur,
                                    "Käufe": fmt.num}), hide_index=True, use_container_width=True)
        hist = M.nl_aggregate(filter_nl(m.nl, Filters(produkte=[pa, pb])), ["produkt", "jahr", "quartal"])
        hist["x"] = hist.jahr.astype(int).astype(str) + " Q" + hist.quartal.astype(int).astype(str)
        fig = go.Figure()
        for i, prod in enumerate((pa, pb)):
            h = hist[hist.produkt == prod].sort_values("x")
            fig.add_scatter(x=h.x, y=h.rev_per_recipient * 1000, name=prod, mode="lines+markers", line=dict(color=SERIES[i], width=2),
                            customdata=h.sendungen, hovertemplate=f"{prod} %{{x}}: %{{y:,.1f}} €/1.000 Empf. (n=%{{customdata}})<extra></extra>")
        fig.update_layout(title="Umsatz je 1.000 Empfänger je Quartal")
        C.chart(fig, "pab", 340)
    with t3:
        allp = filter_nl(m.nl, f_noprod)
        top = allp.groupby("produkt").umsatz.sum().sort_values(ascending=False).head(8).index.tolist()
        chosen = st.multiselect("Produkte", sorted(allp.produkt.unique()), default=f.produkte or top[:5], key="prod_hist")
        a = M.nl_aggregate(allp[allp.produkt.isin(chosen)], ["produkt", "jahr"])
        metric = st.radio("Kennzahl", ["umsatz", "sendungen", "rev_per_recipient", "cr_click", "ctor"], horizontal=True, key="prod_hm",
                          format_func={"umsatz": "Umsatz", "sendungen": "Anzahl NL", "rev_per_recipient": "€/Empfänger",
                                       "cr_click": "Conversion Rate", "ctor": "Klickrate"}.get)
        fig = go.Figure()
        for i, prod in enumerate(chosen[:8]):
            h = a[a.produkt == prod]
            fig.add_scatter(x=h.jahr.astype(int).astype(str), y=h[metric], name=prod, mode="lines+markers", line=dict(color=SERIES[i], width=2))
        fig.update_layout(title="Entwicklung je Jahr", yaxis_tickformat=".2%" if metric in ("cr_click", "ctor") else ",.2f")
        C.chart(fig, "prod_years", 380)
        if len(chosen) > 8:
            C.note("Maximal 8 Produkte gleichzeitig darstellbar (Farbunterscheidbarkeit).")
    with t4:
        prod = st.selectbox("Produkt", sorted(m.nl.produkt.unique()), key="prod_st")
        d = filter_nl(m.nl, Filters(**{**f.__dict__, "produkte": [prod]}))
        c1, c2 = st.columns(2)
        wd = M.nl_aggregate(d, ["wochentag_nr"]).sort_values("wochentag_nr")
        fig = go.Figure(go.Bar(x=[WEEKDAYS_DE[i][:2] for i in wd.wochentag_nr], y=wd.umsatz_pro_sendung, marker_color=SERIES[0],
                               customdata=wd.sendungen, hovertemplate="%{x}: %{y:,.0f} € je NL (n=%{customdata})<extra></extra>"))
        fig.update_layout(title=f"{prod}: Ø Umsatz je Newsletter nach Wochentag", hovermode="closest")
        with c1:
            C.chart(fig, "prod_wd", 300)
        zf = M.nl_aggregate(d, ["zeitfenster"]).sort_values("zeitfenster")
        fig = go.Figure(go.Bar(x=zf.zeitfenster, y=zf.umsatz_pro_sendung, marker_color=SERIES[2], customdata=zf.sendungen,
                               hovertemplate="%{x}: %{y:,.0f} € je NL (n=%{customdata})<extra></extra>"))
        fig.update_layout(title=f"{prod}: Ø Umsatz je Newsletter nach Uhrzeit", hovermode="closest")
        with c2:
            C.chart(fig, "prod_zf", 300)
        C.note("Balken mit wenigen Newslettern (n im Tooltip) sind nicht belastbar.")
        best = d.dropna(subset=["umsatz"]).sort_values("umsatz", ascending=False)[["send_date", "uhrzeit", "betreff", "empfaenger",
                                                                                     "open_rate", "ctor", "kaeufe", "umsatz"]]
        st.markdown(f"**Betreffzeilen für {prod} nach Umsatz**")
        st.dataframe(best.assign(open_rate=(best.open_rate * 100).round(1), ctor=(best.ctor * 100).round(2)).rename(
            columns={"send_date": "Datum", "uhrzeit": "Uhrzeit", "betreff": "Betreff", "empfaenger": "Empfänger",
                     "open_rate": "Öffnungsrate %", "ctor": "Klickrate %", "kaeufe": "Käufe", "umsatz": "Umsatz €"}),
            hide_index=True, use_container_width=True, column_config={"Betreff": st.column_config.TextColumn(width="large")})

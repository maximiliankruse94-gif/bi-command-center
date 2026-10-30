from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from bi.analytics import metrics as M
from bi.analytics.model import filter_daily
from bi.parsers.common import MONTH_NAMES_DE, WEEKDAYS_DE

from .. import components as C
from .. import fmt
from ..theme import MUTED, SEQ_BLUE, SERIES

LEVELS = {"Tag": "tag", "Woche (ISO)": "woche", "Monat": "monat", "Quartal": "quartal", "Jahr": "jahr"}


def render():
    ctx = st.session_state["ctx"]
    m, sel = ctx["m"], ctx["sel"]
    p, c = sel.period, sel.comp
    C.header("Revenue Intelligence", f"{p.label} ({p.fmt()})" + (f" · Vergleich: {c.label}" if c else "") +
             " · Quelle: Tagesstatistiken (maßgeblich)")
    d = filter_daily(m.daily, p.start, p.end, sel.filters)
    rc = M.revenue_summary(d, p)
    dr = filter_daily(m.daily, c.start, c.end, sel.filters) if c else None
    rr = M.revenue_summary(dr, c) if c else None
    weeks = M.aggregate(d, "woche", ["umsatz_gesamt"]) if len(d) else pd.DataFrame()
    months = M.aggregate(d, "monat", ["umsatz_gesamt"]) if len(d) else pd.DataFrame()
    full_w = weeks[weeks.tage == 7] if len(weeks) else weeks
    cards = [
        C.kpi("Umsatz", rc["umsatz_gesamt"], rr["umsatz_gesamt"] if rr else None),
        C.kpi("Ø Tagesumsatz", rc["umsatz_pro_tag"], rr["umsatz_pro_tag"] if rr else None),
        C.kpi("Ø Wochenumsatz (volle KW)", float(full_w.umsatz_gesamt.mean()) if len(full_w) else None, None),
        C.kpi("Ø Monatsumsatz", float(months[months.tage >= 28].umsatz_gesamt.mean()) if len(months) and (months.tage >= 28).any() else None, None),
        C.kpi("Umsatz nach Rückgaben", rc["netto_umsatz"], rr["netto_umsatz"] if rr else None),
        C.kpi("Rückgaben + Rücklastschriften", (rc["rueckgaben"] or 0) + (rc["ruecklastschriften"] or 0),
              ((rr["rueckgaben"] or 0) + (rr["ruecklastschriften"] or 0)) if rr else None, invert=True),
        C.kpi("Werbekosten", rc["werbung"], rr["werbung"] if rr else None, invert=True),
        C.kpi("Volatilität (Variationskoeff.)", M.volatility(d.set_index("date").umsatz_gesamt) if len(d) else None,
              M.volatility(dr.set_index("date").umsatz_gesamt) if rr and len(dr) else None, fmt_fn=lambda v: fmt.pct(v, 0),
              delta_kind="pp", invert=True),
    ]
    C.kpi_row(cards, 4)
    cn = M.coverage_note(rc, rr)
    if cn:
        st.caption("⚠️ " + cn)

    t1, t2, t3, t4, t5, t6 = st.tabs(["Zeitreihe", "Year-over-Year", "Mehrjahresvergleich", "Heatmaps",
                                      "Erst- vs. wiederkehrende Zahlungen", "Verteilung & Saisonalität"])
    with t1:
        lv = st.radio("Aggregation", list(LEVELS), horizontal=True, index=0 if p.days <= 62 else (1 if p.days <= 200 else 2), key="rev_lvl")
        a = M.aggregate(d, LEVELS[lv], ["umsatz_gesamt", "netto_umsatz", "erstzahlung", "wiederkehrend"])
        if a.empty:
            C.empty_state("Keine Tagesumsätze im Zeitraum.")
        else:
            fig = go.Figure()
            x = a["date"] if lv == "Tag" else a["label"]
            fig.add_bar(x=x, y=a.umsatz_gesamt, name="Umsatz", marker_color=SERIES[0],
                        customdata=a.tage, hovertemplate="%{x}: %{y:,.0f} € (%{customdata} Tage mit Daten)<extra></extra>")
            fig.add_scatter(x=x, y=a.netto_umsatz, name="nach Rückgaben", mode="lines", line=dict(color=SERIES[2], width=2))
            if c is not None and lv == "Tag" and dr is not None and len(dr):
                ref = dr.sort_values("date")
                if len(ref) == len(a):
                    fig.add_scatter(x=x, y=ref.umsatz_gesamt.values, name=f"Vergleich ({c.label})", mode="lines",
                                    line=dict(color=MUTED, dash="dot", width=2))
            fig.update_layout(yaxis_tickformat=",.0f", yaxis_title="€", title=f"Umsatz je {lv}")
            C.chart(fig, "rev_ts", 420)
            if (a.tage < {"tag": 1, "woche": 7, "monat": 28, "quartal": 89, "jahr": 365}[LEVELS[lv]]).any():
                C.note("Perioden mit weniger erfassten Tagen (z.B. laufende Periode, Datenlücken) sind nur eingeschränkt vergleichbar – siehe Spalte „tage“.")
            C.download_buttons(a, f"umsatz_{LEVELS[lv]}", "rev_dl")
    with t2:
        _yoy(m)
    with t3:
        _multiyear(m)
    with t4:
        _heatmaps(m, d)
    with t5:
        _erst_wiederkehrend(m, d)
    with t6:
        _distribution(m, d)


def _yoy(m):
    st.markdown("**Year-over-Year je Monat** – jeder Monat im Vergleich zu denselben Monaten aller Vorjahre (Tagesdaten).")
    a = M.aggregate(m.daily, "monat", ["umsatz_gesamt"])
    piv = a.pivot_table(index="monat", columns="jahr", values="umsatz_gesamt")
    days = a.pivot_table(index="monat", columns="jahr", values="tage")
    years = sorted(piv.columns)
    sel_m = st.selectbox("Monat", list(range(1, 13)), index=m.asof.month - 1, format_func=lambda x: MONTH_NAMES_DE[x], key="yoy_m")
    row = piv.loc[sel_m] if sel_m in piv.index else pd.Series(dtype=float)
    drow = days.loc[sel_m] if sel_m in days.index else pd.Series(dtype=float)
    tab = pd.DataFrame({"Jahr": years, "Umsatz": [row.get(y) for y in years], "Tage erfasst": [drow.get(y) for y in years]})
    tab["Δ € zum Vorjahr"] = tab.Umsatz.diff()
    tab["Δ % zum Vorjahr"] = tab.Umsatz.pct_change(fill_method=None)
    latest = tab.dropna(subset=["Umsatz"]).iloc[-1] if tab.Umsatz.notna().any() else None
    if latest is not None:
        tab[f"Δ % vs. {int(latest.Jahr)}"] = latest.Umsatz / tab.Umsatz - 1
    fig = go.Figure(go.Bar(x=tab.Jahr.astype(str), y=tab.Umsatz, marker_color=SERIES[0], text=[fmt.eur(v, compact=True) for v in tab.Umsatz],
                           textposition="outside", hovertemplate="%{x}: %{y:,.0f} €<extra></extra>"))
    fig.update_layout(title=f"{MONTH_NAMES_DE[sel_m]} im Jahresvergleich", yaxis_tickformat=",.0f", hovermode="closest")
    C.chart(fig, "yoy_bar", 340)
    if (tab["Tage erfasst"].dropna() < 28).any():
        C.note("⚠️ Mindestens ein Jahr hat für diesen Monat nicht alle Tage erfasst (laufender Monat oder Datenlücke, z.B. Oktober 2022 fehlt in den Tagesstatistiken).")
    st.dataframe(tab.style.format({"Umsatz": fmt.eur, "Δ € zum Vorjahr": fmt.signed_eur, "Δ % zum Vorjahr": fmt.signed_pct,
                                   **({f"Δ % vs. {int(latest.Jahr)}": fmt.signed_pct} if latest is not None else {}),
                                   "Tage erfasst": lambda v: fmt.num(v)}), hide_index=True, use_container_width=True)
    st.markdown("**Alle Monate × Jahre** (Δ % zum Vorjahresmonat)")
    yo = piv.pct_change(axis=1, fill_method=None)
    show = piv.copy()
    show.index = [MONTH_NAMES_DE[i] for i in show.index]
    yo.index = show.index
    fig = px.imshow(yo.values, x=[str(y) for y in yo.columns], y=list(yo.index), color_continuous_scale=[[0, "#d03b3b"], [0.5, "#383835"], [1, "#3987e5"]],
                    zmin=-0.4, zmax=0.4, aspect="auto", text_auto=False)
    fig.update_traces(customdata=show.values, hovertemplate="%{y} %{x}<br>Umsatz: %{customdata:,.0f} €<br>Δ Vorjahr: %{z:.1%}<extra></extra>")
    fig.update_layout(coloraxis_colorbar=dict(tickformat=".0%", title="Δ VJ"), hovermode="closest", title="Veränderung zum Vorjahresmonat")
    C.chart(fig, "yoy_heat", 420)
    C.download_buttons(show.reset_index().rename(columns={"index": "Monat"}), "umsatz_monat_x_jahr", "yoy_dl")


def _multiyear(m):
    lvl = st.radio("Ebene", ["Monat", "Kalenderwoche", "Kumuliert (Year-to-Date)"], horizontal=True, key="my_lvl")
    fig = go.Figure()
    years = sorted(m.daily.jahr.unique())
    for i, y in enumerate(years):
        dd = m.daily[m.daily.jahr == y]
        color = SERIES[i % len(SERIES)] if y >= years[-1] - 3 else "#4a505c"
        width = 3 if y == years[-1] else 1.6
        if lvl == "Monat":
            a = dd.groupby("monat").umsatz_gesamt.sum()
            x = [MONTH_NAMES_DE[i][:3] for i in a.index]
        elif lvl == "Kalenderwoche":
            dd = dd[dd.iso_jahr == y]
            a = dd.groupby("kw").umsatz_gesamt.sum()
            x = a.index
        else:
            a = dd.sort_values("date").set_index(pd.to_datetime(dd.sort_values("date").date).dt.dayofyear).umsatz_gesamt.cumsum()
            x = a.index
        fig.add_scatter(x=x, y=a.values, name=str(y), mode="lines+markers" if lvl == "Monat" else "lines",
                        line=dict(color=color, width=width), hovertemplate=f"{y} · %{{x}}: %{{y:,.0f}} €<extra></extra>")
    fig.update_layout(yaxis_tickformat=",.0f", yaxis_title="€", hovermode="x unified",
                      xaxis_title={"Monat": "", "Kalenderwoche": "ISO-KW", "Kumuliert (Year-to-Date)": "Tag im Jahr"}[lvl],
                      title="Umsatz je Jahr im Vergleich")
    C.chart(fig, "my_lines", 440)
    C.note("Jahr 2020 nur ab Oktober erfasst; Oktober 2022 fehlt in den Tagesstatistiken (nur in Monatsstatistik vorhanden).")
    ya = M.aggregate(m.daily, "jahr", ["umsatz_gesamt", "erstzahlung", "wiederkehrend", "netto_umsatz", "werbung", "verdienst"])
    ya["Ø pro Tag"] = ya.umsatz_gesamt / ya.tage
    ya["Δ % Ø/Tag zum Vorjahr"] = ya["Ø pro Tag"].pct_change()
    st.dataframe(ya[["label", "tage", "umsatz_gesamt", "Ø pro Tag", "Δ % Ø/Tag zum Vorjahr", "erstzahlung", "wiederkehrend",
                     "netto_umsatz", "werbung", "verdienst"]].rename(columns={"label": "Jahr", "tage": "Tage", "umsatz_gesamt": "Umsatz",
                     "erstzahlung": "Erstzahlungen", "wiederkehrend": "Wiederkehrend", "netto_umsatz": "nach Rückgaben",
                     "werbung": "Werbekosten", "verdienst": "Verdienst"}).style.format(
        {c: fmt.eur for c in ["Umsatz", "Ø pro Tag", "Erstzahlungen", "Wiederkehrend", "nach Rückgaben", "Werbekosten", "Verdienst"]} |
        {"Δ % Ø/Tag zum Vorjahr": fmt.signed_pct}), hide_index=True, use_container_width=True)
    C.note("Jahre mit unterschiedlicher Tagesanzahl werden über den Ø Tagesumsatz vergleichbar gemacht.")


def _heatmaps(m, d):
    c1, c2 = st.columns(2)
    with c1:
        a = m.daily.pivot_table(index="jahr", columns="monat", values="umsatz_gesamt", aggfunc="sum")
        fig = px.imshow(a.values, x=[MONTH_NAMES_DE[i][:3] for i in a.columns], y=[str(y) for y in a.index],
                        color_continuous_scale=SEQ_BLUE, aspect="auto")
        fig.update_traces(hovertemplate="%{y} %{x}: %{z:,.0f} €<extra></extra>")
        fig.update_layout(title="Monatsumsatz (Jahr × Monat)", hovermode="closest", coloraxis_colorbar=dict(title="€"))
        C.chart(fig, "hm_ym", 380)
    with c2:
        dd = d if len(d) > 40 else m.daily[m.daily.date >= m.asof - pd.Timedelta(days=364)]
        a = dd.pivot_table(index="wochentag_nr", columns=["iso_jahr", "kw"], values="umsatz_gesamt", aggfunc="sum")
        fig = px.imshow(a.values, x=[f"KW{k[1]:02d}/{str(k[0])[2:]}" for k in a.columns], y=[WEEKDAYS_DE[i][:2] for i in a.index],
                        color_continuous_scale=SEQ_BLUE, aspect="auto")
        fig.update_traces(hovertemplate="%{x} %{y}: %{z:,.0f} €<extra></extra>")
        fig.update_layout(title="Tagesumsatz (Wochentag × KW)" + (" – letzte 365 Tage" if len(d) <= 40 else ""), hovermode="closest",
                          coloraxis_colorbar=dict(title="€"))
        C.chart(fig, "hm_wk", 380)
        C.note("Weiße/leere Zellen = keine Daten (nicht 0).")


def _erst_wiederkehrend(m, d):
    lv = st.radio("Ebene", ["Monat", "Quartal", "Jahr"], horizontal=True, key="ew_lvl")
    a = M.aggregate(m.daily, LEVELS[lv], ["umsatz_gesamt", "erstzahlung", "wiederkehrend", "split_summe", "einmalzahlung",
                                          "abo_start", "rate_start", "abo_wiederkehrend", "rate_wiederkehrend"])
    a["anteil_erst"] = a.erstzahlung / a.split_summe
    fig = go.Figure()
    for col, name, color in [("einmalzahlung", "Einmalzahlung", SERIES[0]), ("abo_start", "Abo-Start", SERIES[6]),
                             ("rate_start", "Raten-Start", SERIES[4]), ("abo_wiederkehrend", "Abo wiederkehrend", SERIES[2]),
                             ("rate_wiederkehrend", "Raten wiederkehrend", SERIES[5])]:
        fig.add_bar(x=a.label, y=a[col], name=name, marker_color=color, hovertemplate=f"{name}: %{{y:,.0f}} €<extra></extra>")
    fig.update_layout(barmode="stack", yaxis_tickformat=",.0f", title="Umsatz nach Zahlungsart (Hauptkonto GTK)")
    C.chart(fig, "ew_stack", 400)
    fig = go.Figure(go.Scatter(x=a.label, y=a.anteil_erst, mode="lines+markers", line=dict(color=SERIES[0], width=2),
                               name="Anteil Erstzahlungen", hovertemplate="%{x}: %{y:.1%}<extra></extra>"))
    fig.update_layout(yaxis_tickformat=".0%", title="Anteil Erstzahlungen (Neukundenumsatz) am aufgeschlüsselten Umsatz",
                      yaxis_range=[0, 1])
    C.chart(fig, "ew_share", 300)
    ab = m.monthly.dropna(subset=["aktive_abos"]).sort_values(["year", "month"])
    if len(ab):
        ab["label"] = ab.apply(lambda r: f"{int(r.year)}-{int(r.month):02d}", axis=1)
        fig = go.Figure()
        fig.add_scatter(x=ab.label, y=ab.aktive_abos, name="Aktive Abos", line=dict(color=SERIES[2], width=2))
        fig.update_layout(title="Aktive Abos (Monatsstatistik)", yaxis_title="Anzahl")
        C.chart(fig, "ew_abos", 300)
        fig = go.Figure()
        fig.add_bar(x=ab.label, y=ab.neue_abos, name="Neue Abos", marker_color=SERIES[0])
        fig.add_bar(x=ab.label, y=-ab.kuendigungen, name="Kündigungen", marker_color=SERIES[7])
        fig.update_layout(barmode="relative", title="Abo-Zugänge und Kündigungen je Monat", yaxis_title="Anzahl")
        C.chart(fig, "ew_flow", 300)
    C.note("Die Aufteilung Erst-/Wiederkehrend ist in den Tagesstatistiken nur für das Hauptkonto (GTK) vorhanden. "
           "Umsätze der Konten littlefreilich, GunnarKessler und WU/EA sind als „nicht aufgeschlüsselt“ ausgewiesen.")


def _distribution(m, d):
    c1, c2 = st.columns(2)
    dd = d if len(d) >= 30 else m.daily[m.daily.date >= m.asof - pd.Timedelta(days=364)]
    with c1:
        fig = px.histogram(dd, x="umsatz_gesamt", nbins=40, color_discrete_sequence=[SERIES[0]])
        fig.update_layout(title="Verteilung der Tagesumsätze", xaxis_title="€ pro Tag", yaxis_title="Anzahl Tage", hovermode="closest")
        C.chart(fig, "dist_h", 340)
    with c2:
        fig = go.Figure()
        for i, wd in enumerate(WEEKDAYS_DE):
            fig.add_box(y=dd[dd.wochentag == wd].umsatz_gesamt, name=wd[:2], marker_color=SERIES[0], boxmean=True, showlegend=False)
        fig.update_layout(title="Tagesumsatz nach Wochentag", yaxis_tickformat=",.0f", hovermode="closest")
        C.chart(fig, "dist_b", 340)
    s = m.daily.groupby(["jahr", "monat"]).umsatz_gesamt.sum().reset_index()
    full = s[s.jahr.isin([y for y in s.jahr.unique() if (s.jahr == y).sum() == 12])]
    if len(full):
        full["idx"] = full.umsatz_gesamt / full.groupby("jahr").umsatz_gesamt.transform("mean")
        si = full.groupby("monat").idx.agg(["mean", "std", "count"]).reset_index()
        fig = go.Figure(go.Bar(x=[MONTH_NAMES_DE[i][:3] for i in si.monat], y=si["mean"], marker_color=SERIES[0],
                               error_y=dict(type="data", array=si["std"], color=MUTED),
                               hovertemplate="%{x}: Index %{y:.2f}<extra></extra>"))
        fig.add_hline(y=1, line_dash="dot", line_color=MUTED)
        fig.update_layout(title=f"Saisonindex je Monat (1,0 = Jahresdurchschnitt; vollständige Jahre: {', '.join(map(str, sorted(full.jahr.unique())))})",
                          hovermode="closest")
        C.chart(fig, "season", 320)
        C.note("Fehlerbalken = Streuung zwischen den Jahren. Ein Monat mit Index 1,15 liegt typischerweise 15 % über dem Jahresmittel.")

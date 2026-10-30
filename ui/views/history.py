"""Historical Analysis mit Drill-down: Jahr → Quartal → Monat → Kalenderwoche → Tag → Newsletter-Sendung."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bi.analytics import metrics as M
from bi.analytics.model import filter_nl
from bi.parsers.common import MONTH_NAMES_DE, WEEKDAYS_DE

from .. import components as C
from .. import fmt
from ..theme import SERIES
from .newsletter import sends_table

LEVELS = ["jahr", "quartal", "monat", "woche", "tag"]
NAMES = {"jahr": "Jahre", "quartal": "Quartale", "monat": "Monate", "woche": "Kalenderwochen", "tag": "Tage"}


def _path():
    return st.session_state.setdefault("drill", {})


def _subset(m, path):
    d, n = m.daily, m.nl
    if "jahr" in path:
        d, n = d[d.jahr == path["jahr"]], n[n.jahr == path["jahr"]]
    if "quartal" in path:
        d, n = d[d.quartal == path["quartal"]], n[n.quartal == path["quartal"]]
    if "monat" in path:
        d, n = d[d.monat == path["monat"]], n[n.monat == path["monat"]]
    if "woche" in path:
        y, w = path["woche"]
        s = dt.date.fromisocalendar(y, w, 1)
        e = s + dt.timedelta(days=6)
        d, n = m.daily[(m.daily.date >= s) & (m.daily.date <= e)], m.nl[(m.nl.send_date >= s) & (m.nl.send_date <= e)]
    if "tag" in path:
        d, n = d[d.date == path["tag"]], n[n.send_date == path["tag"]]
    return d, n


def _label(k, v):
    if k == "jahr":
        return str(v)
    if k == "quartal":
        return f"Q{v}"
    if k == "monat":
        return MONTH_NAMES_DE[v]
    if k == "woche":
        return f"KW {v[1]}/{v[0]}"
    return v.strftime("%a %d.%m.%Y")


def render():
    ctx = st.session_state["ctx"]
    m, f = ctx["m"], ctx["sel"].filters
    C.header("Historical Analysis", "Drill-down: Balken anklicken → nächste Ebene · Jahr → Quartal → Monat → KW → Tag → Newsletter")
    path = _path()
    crumbs = st.columns(len(path) + 1 + 1)
    if crumbs[0].button("🏠 Alle Jahre", key="cr_root"):
        st.session_state["drill"] = {}
        st.rerun()
    for i, (k, v) in enumerate(list(path.items())):
        if crumbs[i + 1].button(_label(k, v), key=f"cr_{k}"):
            keep = list(path)[: i + 1]
            st.session_state["drill"] = {kk: path[kk] for kk in keep}
            st.rerun()
    level = LEVELS[len(path)] if len(path) < len(LEVELS) else None
    d, n = _subset(m, path)
    n = filter_nl(n, f)
    if level is None:  # Tagesebene erreicht -> Sendungen
        day = path["tag"]
        r = d.iloc[0] if len(d) else None
        if r is not None:
            C.kpi_row([C.kpi("Tagesumsatz", r.umsatz_gesamt, None), C.kpi("Erstzahlungen", r.erstzahlung, None),
                       C.kpi("Wiederkehrend", r.wiederkehrend, None), C.kpi("Rückgaben", r.rueckgaben, None, invert=True)], 4)
            st.caption(f"Quelle: Tab „{r.source_tab}“, Zeile {r.source_row}" + (f" · Bemerkung: {r.bemerkung}" if r.bemerkung else ""))
            st.dataframe(pd.DataFrame([r]).T.rename(columns={pd.DataFrame([r]).index[0]: "Wert"}), use_container_width=True, height=300)
        else:
            st.info("Für diesen Tag liegen keine Tagesumsätze vor (fehlender Eintrag, nicht 0 €).")
        st.markdown(f"##### Newsletter am {day:%d.%m.%Y}")
        if n.empty:
            st.caption("Kein Newsletter an diesem Tag.")
        else:
            sends_table(n, "hist_sends", 220)
        return
    key = {"jahr": ["jahr"], "quartal": ["jahr", "quartal"], "monat": ["jahr", "monat"], "woche": ["iso_jahr", "kw"], "tag": ["date"]}[level]
    a = d.groupby(key).agg(umsatz=("umsatz_gesamt", "sum"), erst=("erstzahlung", "sum"), wk=("wiederkehrend", "sum"),
                           tage=("date", "nunique")).reset_index()
    if a.empty:
        C.empty_state("Keine Daten auf dieser Ebene.")
        return
    nk = {"jahr": ["jahr"], "quartal": ["jahr", "quartal"], "monat": ["jahr", "monat"], "woche": ["iso_jahr", "kw"], "tag": ["send_date"]}[level]
    na = n.groupby(nk).agg(nl_umsatz=("umsatz", "sum"), nl=("send_id", "count")).reset_index()
    if level == "tag":
        na = na.rename(columns={"send_date": "date"})
    a = a.merge(na, on=key, how="left")
    if level == "jahr":
        a["x"] = a.jahr.astype(str); a["val"] = a.jahr
    elif level == "quartal":
        a["x"] = "Q" + a.quartal.astype(str); a["val"] = a.quartal
    elif level == "monat":
        a["x"] = a.monat.map(lambda v: MONTH_NAMES_DE[v]); a["val"] = a.monat
    elif level == "woche":
        a["x"] = a.apply(lambda r: f"KW {int(r.kw)}", axis=1); a["val"] = list(zip(a.iso_jahr.astype(int), a.kw.astype(int)))
    else:
        a["x"] = a.date.map(lambda v: f"{WEEKDAYS_DE[v.weekday()][:2]} {v:%d.%m.}"); a["val"] = a.date
    fig = go.Figure()
    fig.add_bar(x=a.x, y=a.umsatz, name="Umsatz", marker_color=SERIES[0], customdata=a[["tage", "nl"]].fillna(0).values,
                hovertemplate="%{x}: %{y:,.0f} €<br>%{customdata[0]} Tage · %{customdata[1]} Newsletter<extra></extra>")
    fig.add_scatter(x=a.x, y=a.nl_umsatz, name="Newsletter-Umsatz", mode="lines+markers", line=dict(color=SERIES[3], width=2),
                    hovertemplate="Newsletter: %{y:,.0f} €<extra></extra>")
    fig.update_layout(title=f"{NAMES[level]} – Klick auf einen Balken öffnet die nächste Ebene", yaxis_tickformat=",.0f",
                      hovermode="closest", clickmode="event+select")
    ev = C.chart(fig, f"drill_{level}_{len(path)}", 420, on_select=True)
    pts = (ev or {}).get("selection", {}).get("points", []) if ev else []
    if pts:
        idx = pts[0].get("point_index", pts[0].get("pointIndex"))
        if idx is not None and idx < len(a):
            v = a.iloc[idx]["val"]
            path = dict(path)
            if level == "jahr":
                path["jahr"] = int(v)
            elif level == "quartal":
                path["quartal"] = int(v)
            elif level == "monat":
                path["monat"] = int(v)
            elif level == "woche":
                path["woche"] = (int(v[0]), int(v[1]))
            else:
                path["tag"] = v
            st.session_state["drill"] = path
            st.rerun()
    pick = st.selectbox("…oder Ebene direkt wählen", ["–"] + a.x.tolist(), key=f"pick_{level}_{len(path)}")
    if pick != "–":
        v = a[a.x == pick].iloc[0]["val"]
        path = dict(path)
        path[{"jahr": "jahr", "quartal": "quartal", "monat": "monat", "woche": "woche", "tag": "tag"}[level]] = \
            (int(v) if level in ("jahr", "quartal", "monat") else ((int(v[0]), int(v[1])) if level == "woche" else v))
        st.session_state["drill"] = path
        st.rerun()
    t = a[["x", "umsatz", "erst", "wk", "nl_umsatz", "nl", "tage"]].rename(columns={
        "x": NAMES[level], "umsatz": "Umsatz", "erst": "Erstzahlungen", "wk": "Wiederkehrend", "nl_umsatz": "NL-Umsatz",
        "nl": "Newsletter", "tage": "Tage mit Daten"})
    st.dataframe(t.style.format({"Umsatz": fmt.eur, "Erstzahlungen": fmt.eur, "Wiederkehrend": fmt.eur, "NL-Umsatz": fmt.eur,
                                 "Newsletter": fmt.num}), hide_index=True, use_container_width=True)
    C.download_buttons(t, f"historie_{level}", f"hist_dl_{level}")
    if level == "woche":
        C.note("Kalenderwochen nach ISO 8601 (Montag–Sonntag). Wochen am Monatsrand enthalten nur die Tage dieses Monats.")

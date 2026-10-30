from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from bi.analytics import metrics as M
from bi.analytics.model import APPLE_MPP_DATE, filter_nl
from bi.parsers.common import WEEKDAYS_DE

from .. import components as C
from .. import fmt
from ..theme import MUTED, SEQ_BLUE, SERIES

RATE_LABELS = {"open_rate": "Öffnungsrate", "ctor": "Klickrate (Klicks/Öffnungen)", "ctr": "CTR (Klicks/Empfänger)",
               "cr_click": "Conversion Rate (Käufe/Klicks)", "rev_per_recipient": "Umsatz je Empfänger",
               "epc": "Umsatz je Klick", "aov": "Ø Umsatz je Kauf", "umsatz_pro_sendung": "Ø Umsatz je Newsletter"}

SEND_COLS = {"send_date": "Datum", "uhrzeit": "Uhrzeit", "wochentag": "Wochentag", "produkt": "Produkt", "betreff": "Betreff",
             "empfaenger": "Empfänger", "oeffnungen": "Öffnungen", "open_rate": "Öffnungsrate", "klicks": "Klicks",
             "ctor": "Klickrate", "kaeufe": "Käufe", "cr_click": "Conv.-Rate", "umsatz": "Umsatz", "rev_per_recipient": "€/Empf.",
             "epc": "EPC", "campaign_key": "Campaignkey", "source_tab": "Quelle (Tab)", "source_row": "Zeile"}


def sends_table(df: pd.DataFrame, key: str, height: int = 420):
    t = df.sort_values(["send_date", "uhrzeit"], ascending=False)[[c for c in SEND_COLS if c in df.columns]].rename(columns=SEND_COLS)
    st.dataframe(_pct_cols(t), hide_index=True, use_container_width=True, height=height,
                 column_config={"Datum": st.column_config.DateColumn(format="DD.MM.YYYY"),
                                "Betreff": st.column_config.TextColumn(width="large"),
                                "Umsatz": st.column_config.NumberColumn(format="%.0f €"),
                                "€/Empf.": st.column_config.NumberColumn(format="%.3f €"),
                                "EPC": st.column_config.NumberColumn(format="%.2f €")})
    C.download_buttons(t, "newsletter_sendungen", key)


def _pct_cols(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    for c in ("Öffnungsrate", "Klickrate", "Conv.-Rate"):
        if c in t:
            t[c] = (t[c] * 100).round(2)
    return t.rename(columns={"Öffnungsrate": "Öffnungsrate %", "Klickrate": "Klickrate %", "Conv.-Rate": "Conv.-Rate %"})


def mpp_marker(fig, x_is_date=True):
    if x_is_date:
        fig.add_vline(x=pd.Timestamp(APPLE_MPP_DATE).timestamp() * 1000, line_dash="dot", line_color=MUTED)
        fig.add_annotation(x=pd.Timestamp(APPLE_MPP_DATE), y=1, yref="paper", text="Apple MPP", showarrow=False,
                           font=dict(color=MUTED, size=10), xanchor="left")


def render():
    ctx = st.session_state["ctx"]
    m, sel = ctx["m"], ctx["sel"]
    p, c, f = sel.period, sel.comp, sel.filters
    C.header("Newsletter Intelligence", f"{p.label} · Filter: {f.describe()}" + (f" · Vergleich: {c.label}" if c else ""))
    cur = filter_nl(m.nl, f, p.start, p.end)
    ref = filter_nl(m.nl, f, c.start, c.end) if c else None
    sc, sr = M.nl_summary(cur), (M.nl_summary(ref) if ref is not None else None)
    g = lambda k: sr[k] if sr else None  # noqa: E731
    e2 = lambda v: fmt.eur(v, 2)  # noqa: E731
    e3 = lambda v: fmt.eur(v, 3)  # noqa: E731
    C.kpi_row([
        C.kpi("Newsletter", sc["sendungen"], g("sendungen"), fmt_fn=fmt.num),
        C.kpi("Empfänger (Summe)", sc["empfaenger"], g("empfaenger"), fmt_fn=fmt.num),
        C.kpi("Ø Empfänger je Newsletter", sc["empfaenger_pro_sendung"], g("empfaenger_pro_sendung"), fmt_fn=fmt.num),
        C.kpi("Öffnungen", sc["oeffnungen"], g("oeffnungen"), fmt_fn=fmt.num),
        C.kpi("Öffnungsrate", sc["open_rate"], g("open_rate"), fmt_fn=fmt.pct, delta_kind="pp",
              help_text="Σ Öffnungen / Σ Empfänger – durch Apple MPP überhöht"),
        C.kpi("Klicks", sc["klicks"], g("klicks"), fmt_fn=fmt.num),
        C.kpi("Klickrate (CTOR)", sc["ctor"], g("ctor"), fmt_fn=lambda v: fmt.pct(v, 2), delta_kind="pp",
              help_text="Σ Klicks / Σ Öffnungen (so im Sheet als 'Clickrate' geführt)"),
        C.kpi("CTR (Klicks/Empfänger)", sc["ctr"], g("ctr"), fmt_fn=lambda v: fmt.pct(v, 2), delta_kind="pp"),
        C.kpi("Käufe (Conversions)", sc["kaeufe"], g("kaeufe"), fmt_fn=fmt.num),
        C.kpi("Conversion Rate", sc["cr_click"], g("cr_click"), fmt_fn=lambda v: fmt.pct(v, 2), delta_kind="pp",
              help_text="Σ Käufe / Σ Klicks"),
        C.kpi("Newsletter-Umsatz", sc["umsatz"], g("umsatz")),
        C.kpi("Ø Umsatz je Newsletter", sc["umsatz_pro_sendung"], g("umsatz_pro_sendung")),
        C.kpi("Umsatz je Empfänger", sc["rev_per_recipient"], g("rev_per_recipient"), fmt_fn=e3),
        C.kpi("Umsatz je Klick (EPC)", sc["epc"], g("epc"), fmt_fn=e2),
        C.kpi("Umsatz je Conversion", sc["aov"], g("aov"), fmt_fn=e2),
        C.kpi("Folgeeinnahmen (lt. Sheet)", sc["folgeeinnahmen"], g("folgeeinnahmen"),
              help_text="Spalte 'Folgeeinnahmen' – nur teilweise gepflegt"),
    ], 4)
    if sc["sendungen_ohne_umsatzdaten"] or sc["sendungen_ohne_klickdaten"]:
        st.caption(f"⚠️ {sc['sendungen_ohne_umsatzdaten']} Sendungen ohne Umsatzangabe und {sc['sendungen_ohne_klickdaten']} ohne "
                   "Klickzahl – bei Raten jeweils aus Zähler und Nenner ausgeschlossen, nicht als 0 gewertet.")
    st.info("ℹ️ **Öffnungsraten** sind seit Apple Mail Privacy Protection (Sept. 2021) technisch überhöht (automatische Öffnungen) "
            "und kein verlässlicher Indikator für menschliches Interesse. Für Entscheidungen Klicks, Käufe und Umsatz je Empfänger bevorzugen.")

    t1, t2, t3, t4 = st.tabs(["Entwicklung", "Versandzeit & Wochentag", "Alle Sendungen", "Mehrjahresvergleich"])
    with t1:
        allf = filter_nl(m.nl, f)
        lvl = st.radio("Ebene", ["Monat", "Quartal", "Woche"], horizontal=True, key="nl_lvl")
        keys = {"Monat": ["ym"], "Quartal": ["jahr", "quartal"], "Woche": ["iso_jahr", "kw"]}[lvl]
        a = M.nl_aggregate(allf, keys)
        if lvl == "Quartal":
            a["x"] = a.jahr.astype(int).astype(str) + " Q" + a.quartal.astype(int).astype(str)
        elif lvl == "Woche":
            a["x"] = pd.to_datetime([pd.Timestamp.fromisocalendar(int(y), int(w), 1) for y, w in zip(a.iso_jahr, a.kw)])
        else:
            a["x"] = pd.to_datetime(a.ym + "-01")
        metric = st.multiselect("Kennzahlen", list(RATE_LABELS), default=["open_rate", "ctor", "cr_click"],
                                format_func=lambda k: RATE_LABELS[k], key="nl_metrics")
        pct_m = [k for k in metric if k in ("open_rate", "ctor", "ctr", "cr_click")]
        eur_m = [k for k in metric if k not in pct_m]
        if pct_m:
            fig = go.Figure()
            for i, k in enumerate(pct_m):
                fig.add_scatter(x=a.x, y=a[k], name=RATE_LABELS[k], mode="lines+markers", line=dict(color=SERIES[i], width=2),
                                marker=dict(size=5), customdata=a.sendungen,
                                hovertemplate=f"{RATE_LABELS[k]}: %{{y:.2%}} (n=%{{customdata}} NL)<extra></extra>")
            fig.update_layout(yaxis_tickformat=".1%", title="Gewichtete Raten im Zeitverlauf")
            if lvl != "Quartal":
                mpp_marker(fig)
            C.chart(fig, "nl_rates", 380)
        for i, k in enumerate(eur_m):
            fig = go.Figure(go.Bar(x=a.x, y=a[k], marker_color=SERIES[(i + 3) % 8], name=RATE_LABELS[k], customdata=a.sendungen,
                                   hovertemplate=f"{RATE_LABELS[k]}: %{{y:,.2f}} € (n=%{{customdata}})<extra></extra>"))
            fig.update_layout(title=RATE_LABELS[k], yaxis_tickformat=",.2f")
            C.chart(fig, f"nl_eur_{k}", 300)
        fig = go.Figure()
        fig.add_bar(x=a.x, y=a.umsatz, name="Newsletter-Umsatz", marker_color=SERIES[0], hovertemplate="%{y:,.0f} €<extra></extra>")
        fig.update_layout(title="Newsletter-Umsatz", yaxis_tickformat=",.0f")
        C.chart(fig, "nl_rev", 300)
        fig = go.Figure(go.Bar(x=a.x, y=a.sendungen, marker_color=SERIES[2], hovertemplate="%{y} Newsletter<extra></extra>"))
        fig.update_layout(title="Anzahl versendeter Newsletter")
        C.chart(fig, "nl_cnt", 240)
    with t2:
        sendtime(cur if len(cur) >= 30 else filter_nl(m.nl, f), len(cur) < 30)
    with t3:
        if cur.empty:
            C.empty_state("Keine Sendungen im Zeitraum/Filter.")
        else:
            st.caption(f"{len(cur)} Sendungen · jede Sendung ist ein eigener Datensatz (auch mehrere am selben Tag)")
            sends_table(cur, "nl_sends")
    with t4:
        allf = filter_nl(m.nl, f)
        ya = M.nl_aggregate(allf, ["jahr"])
        show = ya[["jahr", "sendungen", "empfaenger_pro_sendung", "open_rate", "ctor", "ctr", "cr_click", "umsatz", "umsatz_pro_sendung",
                   "rev_per_recipient", "epc", "aov"]].copy()
        st.dataframe(show.style.format({"empfaenger_pro_sendung": fmt.num, "open_rate": fmt.pct, "ctor": lambda v: fmt.pct(v, 2),
                                        "ctr": lambda v: fmt.pct(v, 2), "cr_click": lambda v: fmt.pct(v, 2), "umsatz": fmt.eur,
                                        "umsatz_pro_sendung": fmt.eur, "rev_per_recipient": lambda v: fmt.eur(v, 3),
                                        "epc": lambda v: fmt.eur(v, 2), "aov": fmt.eur}),
                     hide_index=True, use_container_width=True)
        C.download_buttons(show, "newsletter_jahre", "nl_years_dl")


def sendtime(df: pd.DataFrame, fallback: bool):
    if fallback:
        st.caption("Zu wenige Sendungen im gewählten Zeitraum – Analyse über den gesamten Zeitraum (Filter bleiben aktiv).")
    metric = st.selectbox("Kennzahl", ["open_rate", "ctor", "cr_click", "rev_per_recipient", "umsatz_pro_sendung"],
                          format_func=lambda k: RATE_LABELS[k], key="st_metric")
    min_n = st.slider("Mindestanzahl Sendungen je Zelle", 1, 20, 5, key="st_min")
    adj = st.toggle("Um Produkt- und Jahres-Effekte bereinigen", value=True, key="st_adj",
                    help="Vergleicht jede Sendung mit dem Mittel ihres Produkts im selben Jahr – verhindert, dass ein starkes Produkt "
                         "oder das Apple-MPP-Jahr eine Uhrzeit künstlich gut aussehen lässt.")
    num, den = {"open_rate": ("oeffnungen", "empfaenger"), "ctor": ("klicks", "oeffnungen"), "cr_click": ("kaeufe", "klicks"),
                "rev_per_recipient": ("umsatz", "empfaenger"), "umsatz_pro_sendung": ("umsatz", None)}[metric]
    d = df.dropna(subset=[num] + ([den] if den else [])).copy()
    if den:
        d = d[d[den] > 0]
    if d.empty:
        C.empty_state("Keine Daten.")
        return
    d["val"] = d[num] / d[den] if den else d[num]
    d["w"] = d[den] if den else 1.0
    if adj:
        grp = d.groupby(["produkt", "jahr"])
        base = (grp[num].transform("sum") / grp[den].transform("sum")) if den else grp[num].transform("mean")
        d["val"] = d["val"] / base.replace(0, np.nan) - 1
    def agg(g):
        return pd.Series({"wert": np.average(g.val, weights=g.w) if g.w.sum() else np.nan, "n": len(g)})
    hm = d.groupby(["wochentag_nr", "zeitfenster"]).apply(agg, include_groups=False).reset_index()
    hm.loc[hm.n < min_n, "wert"] = np.nan
    piv = hm.pivot(index="wochentag_nr", columns="zeitfenster", values="wert")
    cnt = hm.pivot(index="wochentag_nr", columns="zeitfenster", values="n")
    fmt_t = ".0%" if adj else (".2%" if metric in ("open_rate", "ctor", "cr_click") else ",.2f")
    fig = px.imshow(piv.values, x=list(piv.columns), y=[WEEKDAYS_DE[i] for i in piv.index], aspect="auto",
                    color_continuous_scale=[[0, "#d03b3b"], [0.5, "#383835"], [1, "#3987e5"]] if adj else SEQ_BLUE,
                    color_continuous_midpoint=0 if adj else None)
    fig.update_traces(customdata=cnt.reindex_like(piv).values,
                      hovertemplate="%{y}, %{x} Uhr<br>Wert: %{z:" + fmt_t + "}<br>Sendungen: %{customdata}<extra></extra>")
    fig.update_layout(title=f"{RATE_LABELS[metric]}{' – Abweichung vom Produkt-/Jahresmittel' if adj else ''} (Wochentag × Uhrzeit)",
                      hovermode="closest", coloraxis_colorbar=dict(tickformat=fmt_t))
    C.chart(fig, "st_heat", 380)
    C.note(f"Leere Zellen: weniger als {min_n} Sendungen – bewusst ausgeblendet, um Zufallsergebnisse nicht als Empfehlung "
           "erscheinen zu lassen.")
    c1, c2 = st.columns(2)
    for col, key, title in ((c1, "wochentag_nr", "nach Wochentag"), (c2, "zeitfenster", "nach Uhrzeit")):
        a = d.groupby(key).apply(agg, include_groups=False).reset_index()
        a["lbl"] = a[key].map(lambda v: WEEKDAYS_DE[v] if key == "wochentag_nr" else v)
        se = d.groupby(key).val.std() / np.sqrt(d.groupby(key).size())
        fig = go.Figure(go.Bar(x=a.lbl, y=a.wert, marker_color=SERIES[0], customdata=a.n,
                               error_y=dict(type="data", array=se.reindex(a[key]).values * 1.96, color=MUTED),
                               hovertemplate="%{x}: %{y:" + fmt_t + "} (n=%{customdata})<extra></extra>"))
        fig.update_layout(title=f"{RATE_LABELS[metric]} {title}", yaxis_tickformat=fmt_t, hovermode="closest")
        with col:
            C.chart(fig, f"st_{key}", 300)
    C.note("Fehlerbalken = 95-%-Konfidenzintervall. Überlappende Balken bedeuten: Unterschied statistisch nicht gesichert.")
    yrs = d.groupby(["jahr", "zeitfenster"]).apply(agg, include_groups=False).reset_index()
    yrs.loc[yrs.n < min_n, "wert"] = np.nan
    fig = px.line(yrs, x="zeitfenster", y="wert", color=yrs.jahr.astype(str), markers=True, color_discrete_sequence=SERIES)
    fig.update_layout(title="Veränderung über die Jahre (je Uhrzeit-Fenster)", yaxis_tickformat=fmt_t, legend_title="Jahr")
    C.chart(fig, "st_years", 320)

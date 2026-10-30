from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bi.analytics import subjects as S
from bi.analytics.model import filter_nl
from bi.parsers.common import WEEKDAYS_DE

from .. import components as C
from .. import fmt
from ..theme import MUTED, SERIES

RANK_METRICS = {"open_rate_bereinigt": "Öffnungsrate (stichprobenbereinigt)", "ctor_bereinigt": "Klickrate (stichprobenbereinigt)",
                "rev_per_1000_bereinigt": "Umsatz je 1.000 Empfänger (stichprobenbereinigt)", "umsatz": "Umsatz absolut",
                "cr_click": "Conversion Rate (roh)"}
COLS = {"betreff_norm": "Betreffzeile", "sendungen": "Sendungen", "empfaenger": "Empfänger", "open_rate": "Öffnungsrate",
        "open_rate_bereinigt": "Öffn. bereinigt", "open_ci_low": "95%-KI unten", "open_ci_high": "95%-KI oben", "ctor": "Klickrate",
        "cr_click": "Conv.-Rate", "umsatz": "Umsatz", "rev_per_1000_bereinigt": "€/1.000 Empf. (ber.)", "produkte": "Produkt(e)",
        "wochentage": "Wochentag(e)", "letzter_versand": "Letzter Versand", "stichprobe": "Stichprobe"}


def _fmt_table(df):
    t = df[[c for c in COLS if c in df.columns]].rename(columns=COLS).copy()
    for c in ("Öffnungsrate", "Öffn. bereinigt", "95%-KI unten", "95%-KI oben", "Klickrate", "Conv.-Rate"):
        if c in t:
            t[c] = (t[c] * 100).round(2)
    return t.rename(columns={c: c + " %" for c in ("Öffnungsrate", "Öffn. bereinigt", "95%-KI unten", "95%-KI oben", "Klickrate", "Conv.-Rate")})


def render():
    ctx = st.session_state["ctx"]
    m, sel = ctx["m"], ctx["sel"]
    p, f = sel.period, sel.filters
    C.header("Betreffzeilen Intelligence", f"{p.label} · Filter: {f.describe()}")
    whole = st.toggle("Gesamte Historie statt gewähltem Zeitraum", value=p.days < 90, key="subj_all")
    nl = filter_nl(m.nl, f) if whole else filter_nl(m.nl, f, p.start, p.end)
    if nl.empty:
        C.empty_state("Keine Sendungen für diese Auswahl.")
        return
    st.caption(f"{len(nl)} Sendungen · {nl.betreff_norm.nunique()} unterschiedliche Betreffzeilen")
    t1, t2, t3, t4 = st.tabs(["Rankings", "Sprachliche Merkmale", "Nach Produkt / Wochentag / Uhrzeit", "Historie & Suche"])
    with t1:
        c1, c2 = st.columns([2, 1])
        metric = c1.selectbox("Ranking nach", list(RANK_METRICS), format_func=RANK_METRICS.get, key="subj_metric")
        min_rec = c2.number_input("Mindest-Empfänger je Betreff", 0, 200000, 5000, 1000, key="subj_min")
        r = S.rank_subjects(nl, int(min_rec))
        if r.empty:
            C.empty_state("Keine Betreffzeilen über der Mindest-Empfängerzahl.")
        else:
            r = r.sort_values(metric, ascending=False)
            st.markdown("**🏆 Beste Betreffzeilen**")
            st.dataframe(_fmt_table(r.head(20)), hide_index=True, use_container_width=True,
                         column_config={"Betreffzeile": st.column_config.TextColumn(width="large")})
            st.markdown("**⚠️ Schwächste Betreffzeilen**")
            st.dataframe(_fmt_table(r.dropna(subset=[metric]).tail(20).iloc[::-1]), hide_index=True, use_container_width=True,
                         column_config={"Betreffzeile": st.column_config.TextColumn(width="large")})
            C.note("<b>Stichprobenbereinigung:</b> Raten werden per Empirical-Bayes zum Gesamtmittel geschrumpft – je weniger "
                   "Empfänger, desto stärker. Ein Betreff mit 100 Empfängern kann so nicht allein durch Zufall an die Spitze gelangen. "
                   "95-%-Konfidenzintervall (Wilson) zur Öffnungsrate angegeben. Öffnungsraten sind durch Apple MPP verzerrt; "
                   "für Umsatzentscheidungen „Umsatz je 1.000 Empfänger“ bevorzugen.")
            C.download_buttons(_fmt_table(r), "betreffzeilen_ranking", "subj_dl")
    with t2:
        metric = st.radio("Kennzahl", ["open_rate", "ctor", "cr_click", "rev_per_recipient"], horizontal=True,
                          format_func={"open_rate": "Öffnungsrate", "ctor": "Klickrate", "cr_click": "Conversion Rate",
                                       "rev_per_recipient": "Umsatz je Empfänger"}.get, key="feat_metric")
        fe = S.feature_effects(nl, metric)
        if fe.empty:
            C.empty_state("Zu wenige Daten.")
        else:
            is_eur = metric == "rev_per_recipient"
            fig = go.Figure(go.Bar(y=fe.merkmal, x=fe.effekt_bereinigt, orientation="h",
                                   marker_color=[SERIES[0] if v >= 0 else SERIES[7] for v in fe.effekt_bereinigt],
                                   customdata=fe[["sendungen_mit", "aussagekraft"]].values,
                                   hovertemplate="%{y}: %{x:" + (".4f" if is_eur else ".2%") + "}<br>Sendungen mit Merkmal: %{customdata[0]:.0f}"
                                                 "<br>Aussagekraft: %{customdata[1]}<extra></extra>"))
            fig.update_layout(title="Bereinigter Effekt je Merkmal (mit vs. ohne, innerhalb gleicher Produkt-/Jahresgruppe)",
                              xaxis_tickformat=".4f" if is_eur else ".1%", hovermode="closest", yaxis=dict(autorange="reversed"))
            C.chart(fig, "feat_bar", 380)
            t = fe.copy()
            fm = (lambda v: fmt.eur(v, 4)) if is_eur else (lambda v: fmt.pct(v, 2))
            st.dataframe(t.style.format({"rate_mit": fm, "rate_ohne": fm, "effekt_bereinigt": (lambda v: fmt.eur(v, 4)) if is_eur else fmt.pp,
                                         "sendungen_mit": fmt.num, "sendungen_ohne": fmt.num}), hide_index=True, use_container_width=True)
            C.note("Merkmale werden regelbasiert erkannt (Fragezeichen, Ziffern, Signalwörter für Dringlichkeit/Neugier/Rabatt/Geld, "
                   "Du-Ansprache/Platzhalter, Emojis, Re:/Fwd:). Ein Effekt ist eine statistische Auffälligkeit – kein Kausalnachweis.")
            with st.expander("Erkennungsregeln anzeigen"):
                for k, (lbl, rx) in S.FEATURES.items():
                    st.code(f"{lbl}: {rx.pattern}", language=None)
    with t3:
        r = nl.copy()
        dim = st.radio("Aufteilung", ["Produkt", "Wochentag", "Uhrzeit-Fenster", "Quartal (saisonal)"], horizontal=True, key="subj_dim")
        col = {"Produkt": "produkt", "Wochentag": "wochentag", "Uhrzeit-Fenster": "zeitfenster", "Quartal (saisonal)": "quartal"}[dim]
        choices = r[col].dropna().astype(str).value_counts().index.tolist()
        val = st.selectbox(dim, choices, key="subj_dimval")
        sub = r[r[col].astype(str) == val]
        rr = S.rank_subjects(sub, 0).sort_values("rev_per_1000_bereinigt", ascending=False)
        st.caption(f"{len(sub)} Sendungen – Top-Betreffzeilen nach Umsatz je 1.000 Empfänger (bereinigt)")
        st.dataframe(_fmt_table(rr.head(25)), hide_index=True, use_container_width=True,
                     column_config={"Betreffzeile": st.column_config.TextColumn(width="large")})
    with t4:
        q = st.text_input("Betreff suchen", key="subj_q", placeholder="z.B. Zugang, Auszahlung, Webinar …")
        h = nl[nl.betreff.fillna("").str.contains(q, case=False, regex=False)] if q else nl
        h = h.sort_values("send_date")
        if len(h):
            fig = go.Figure(go.Scatter(x=pd.to_datetime(h.send_date), y=h.open_rate, mode="markers",
                                       marker=dict(size=(h.umsatz.fillna(0) / max(h.umsatz.max() or 1, 1) * 25 + 6), color=SERIES[0],
                                                   line=dict(color="#0f1115", width=1)),
                                       text=h.betreff, customdata=h[["produkt", "umsatz"]].values,
                                       hovertemplate="%{x|%d.%m.%Y}<br>%{text}<br>Produkt: %{customdata[0]}<br>Öffnungsrate: %{y:.1%}"
                                                     "<br>Umsatz: %{customdata[1]:,.0f} €<extra></extra>"))
            roll = h.set_index(pd.to_datetime(h.send_date))[["oeffnungen", "empfaenger"]].rolling("90D").sum()
            fig.add_scatter(x=roll.index, y=roll.oeffnungen / roll.empfaenger, mode="lines", name="gleitend 90 Tage (gewichtet)",
                            line=dict(color=MUTED, width=2))
            fig.update_layout(title="Öffnungsraten-Entwicklung (Punktgröße = Umsatz)", yaxis_tickformat=".0%", hovermode="closest")
            C.chart(fig, "subj_hist", 400)
            st.dataframe(_fmt_table(S.rank_subjects(h, 0).sort_values("letzter_versand", ascending=False)), hide_index=True,
                         use_container_width=True, column_config={"Betreffzeile": st.column_config.TextColumn(width="large")})

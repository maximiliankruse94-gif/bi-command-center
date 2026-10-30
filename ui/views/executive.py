from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bi.analytics import alerts as AL
from bi.analytics import metrics as M
from bi.analytics import periods as P
from bi.analytics.model import filter_nl

from .. import components as C
from .. import fmt
from ..theme import GOOD, INFO, MUTED, SERIES, WARN


def _rev(m, p):
    return M.revenue_summary(m.daily, p)["umsatz_gesamt"] if p else None


def _series(m, end, days, field="umsatz_gesamt"):
    return list(M.daily_series(m.daily, end - dt.timedelta(days=days - 1), end, field).values)


def _agg_spark(m, level, n):
    a = M.aggregate(m.daily, level, ["umsatz_gesamt"])
    return list(a.umsatz_gesamt.tail(n).values)


def render():
    ctx = st.session_state["ctx"]
    m, sel = ctx["m"], ctx["sel"]
    t = m.asof
    today = dt.date.today()
    C.header("Executive Overview",
             f"Datenstand Tagesumsätze: <b>{t:%d.%m.%Y}</b> · Newsletter: <b>{m.nl_asof:%d.%m.%Y}</b> · "
             f"Alle Umsätze netto ohne USt, vor Rückgaben (Quelle: Tagesstatistiken)")

    # ------------------------------------------------------------------ Umsatz-KPIs (feste Fenster)
    st.markdown("##### Umsatz")
    p_today = P.Period(today, today, "Heute")
    d_last, d_prev = P.Period(t, t, ""), P.Period(t - dt.timedelta(days=1), t - dt.timedelta(days=1), "")
    d_prev2 = P.Period(t - dt.timedelta(days=2), t - dt.timedelta(days=2), "")
    l7 = P.preset("Letzte 7 Tage", t); l7c = P.comparison(l7, "Vorperiode (gleiche Länge)")
    wk = P.preset("Diese Woche", t); wkc = P.comparison(wk, "Vorperiode (gleiche Länge)")
    mo = P.preset("Dieser Monat", t); moc = P.comparison(mo, "Vorperiode (gleiche Länge)")
    qu = P.preset("Dieses Quartal", t); quc = P.comparison(qu, "Vorjahreszeitraum")
    ye = P.preset("Dieses Jahr", t); yec = P.comparison(ye, "Vorjahreszeitraum")
    today_val = _rev(m, p_today) if today <= t else None
    cards = [
        C.kpi(f"Heute ({today:%d.%m.})", today_val, _rev(m, P.Period(today - dt.timedelta(days=1), today - dt.timedelta(days=1), ""))
              if today_val is not None else None, ref_label="Vortag", spark=_series(m, t, 30),
              help_text="Heute noch nicht erfasst – Tagesumsätze werden nachträglich eingetragen." if today_val is None else ""),
        C.kpi(f"Letzter Erfassungstag ({t:%d.%m.})", _rev(m, d_last), _rev(m, d_prev), ref_label="Vortag", spark=_series(m, t, 30)),
        C.kpi(f"Vortag ({d_prev.start:%d.%m.})", _rev(m, d_prev), _rev(m, d_prev2), ref_label="Tag davor", spark=_series(m, t - dt.timedelta(days=1), 30)),
        C.kpi("Letzte 7 Tage", _rev(m, l7), _rev(m, l7c), ref_label="vorherige 7 Tage", spark=_agg_spark(m, "woche", 16)),
        C.kpi(f"Diese Woche (KW {t.isocalendar()[1]})", _rev(m, wk), _rev(m, wkc), ref_label="Vorwoche gleiche Tage", spark=_agg_spark(m, "woche", 16)),
        C.kpi("Dieser Monat", _rev(m, mo), _rev(m, moc), ref_label="Vormonat gleiche Tage", spark=_agg_spark(m, "monat", 13)),
        C.kpi(f"Dieses Quartal (Q{(t.month - 1) // 3 + 1})", _rev(m, qu), _rev(m, quc), ref_label="Vorjahresquartal gleiche Tage", spark=_agg_spark(m, "quartal", 12)),
        C.kpi(f"Dieses Jahr ({t.year})", _rev(m, ye), _rev(m, yec), ref_label="Vorjahr gleiche Tage", spark=_agg_spark(m, "jahr", 7)),
    ]
    C.kpi_row(cards, 4)
    tot = float(m.daily.umsatz_gesamt.sum())
    C.note(f"Gesamtumsatz seit {m.first:%d.%m.%Y}: <b>{fmt.eur(tot)}</b> (Tagesstatistiken; CopeCart-Umsätze von "
           f"{fmt.eur(float(m.monthly.umsatz_copecart.sum()))} sind nur in den Monatsstatistiken enthalten).")

    # ------------------------------------------------------------------ Vergleich gewählter Zeitraum
    p, c = sel.period, sel.comp
    rc = M.revenue_summary(m.daily, p)
    rr = M.revenue_summary(m.daily, c) if c else None
    nc = M.nl_summary(filter_nl(m.nl, sel.filters, p.start, p.end))
    nr = M.nl_summary(filter_nl(m.nl, sel.filters, c.start, c.end)) if c else None
    st.markdown(f"##### Umsatzstruktur · {p.label}" + (f" vs. {c.label}" if c else ""))
    share = M.safe_div(nc["umsatz"], rc["umsatz_gesamt"])
    share_r = M.safe_div(nr["umsatz"], rr["umsatz_gesamt"]) if rr else None
    yoy = P.comparison(p, "Vorjahreszeitraum")
    ryoy = M.revenue_summary(m.daily, yoy)
    cards = [
        C.kpi("Gesamtumsatz", rc["umsatz_gesamt"], rr["umsatz_gesamt"] if rr else None, ref_label=c.label if c else ""),
        C.kpi("Erstzahlungen", rc["erstzahlung"], rr["erstzahlung"] if rr else None, ref_label="Vergleich",
              help_text="Einmalzahlungen + Abo-Starts + Raten-Starts (Hauptkonto GTK)"),
        C.kpi("Wiederkehrende Zahlungen", rc["wiederkehrend"], rr["wiederkehrend"] if rr else None, ref_label="Vergleich",
              help_text="Abo-Folgezahlungen + Folgeraten (Hauptkonto GTK)"),
        C.kpi("Anteil Erstzahlungen", rc["anteil_erst"], rr["anteil_erst"] if rr else None, fmt_fn=fmt.pct, delta_kind="pp",
              help_text="Anteil am nach Zahlungsart aufgeschlüsselten Umsatz"),
        C.kpi("Anteil wiederkehrend", rc["anteil_wiederkehrend"], rr["anteil_wiederkehrend"] if rr else None, fmt_fn=fmt.pct, delta_kind="pp"),
        C.kpi("Newsletter-Umsatz (gemessen)", nc["umsatz"], nr["umsatz"] if nr else None,
              help_text="Laut Newsletter-Tracking, nach Versanddatum; Filter berücksichtigt"),
        C.kpi("Newsletter-Anteil", share, share_r, fmt_fn=fmt.pct, delta_kind="pp",
              help_text="Gemessener NL-Umsatz / Gesamtumsatz. Auf Tagesebene nicht aussagekräftig (Attributionsfenster)."),
        C.kpi("Vorjahreszeitraum", rc["umsatz_gesamt"], ryoy["umsatz_gesamt"], ref_label=yoy.label),
    ]
    C.kpi_row(cards, 4)
    cn = M.coverage_note(rc, rr)
    if cn:
        st.caption("⚠️ " + cn)
    if p.days < 7:
        st.caption("Hinweis: Newsletter-Anteile auf Tagesebene sind nicht aussagekräftig (Umsatz wird über ein Attributionsfenster gezählt).")

    # ------------------------------------------------------------------ Business Health
    st.markdown("##### Business Health")
    left, right = st.columns([3, 2])
    with left:
        s365 = M.daily_series(m.daily, t - dt.timedelta(days=729), t)
        df = pd.DataFrame({"date": pd.to_datetime(s365.index), "v": s365.values})
        df["ma7"] = df.v.rolling(7, min_periods=5).mean()
        df["ma28"] = df.v.rolling(28, min_periods=20).mean()
        df["ly7"] = df.ma7.shift(364)
        df = df[df.date > pd.Timestamp(t - dt.timedelta(days=180))]
        fig = go.Figure()
        fig.add_bar(x=df.date, y=df.v, name="Tagesumsatz", marker_color="rgba(57,135,229,.35)",
                    hovertemplate="%{x|%a %d.%m.%Y}: %{y:,.0f} €<extra></extra>")
        fig.add_scatter(x=df.date, y=df.ma7, name="Ø 7 Tage", line=dict(color=SERIES[0], width=2),
                        hovertemplate="Ø 7 Tage: %{y:,.0f} €<extra></extra>")
        fig.add_scatter(x=df.date, y=df.ly7, name="Ø 7 Tage Vorjahr", line=dict(color=MUTED, width=2, dash="dot"),
                        hovertemplate="Vorjahr: %{y:,.0f} €<extra></extra>")
        fig.update_layout(title="Umsatztrend letzte 180 Tage (vs. Vorjahr, gleiche Wochentage)", yaxis_tickformat=",.0f",
                          yaxis_title="€")
        C.chart(fig, "ex_trend", 340)
    with right:
        s90 = M.daily_series(m.daily, t - dt.timedelta(days=89), t)
        s365b = M.daily_series(m.daily, t - dt.timedelta(days=364), t)
        slope = M.trend_slope(s90)
        vol30 = M.volatility(M.daily_series(m.daily, t - dt.timedelta(days=29), t))
        vol365 = M.volatility(s365b)
        e90 = M.revenue_summary(m.daily, P.Period(t - dt.timedelta(days=89), t, ""))
        e90ly = M.revenue_summary(m.daily, P.Period(P.shift_year(t - dt.timedelta(days=89)), P.shift_year(t), ""))
        def row(lbl, val, kind, expl):
            return f"<tr><td style='padding:6px 8px;color:#b4bac6'>{lbl}</td><td style='padding:6px 8px;text-align:right'>{val}</td><td style='padding:6px 8px'>{C.badge(kind[0], kind[1])}</td></tr><tr><td colspan=3 class='note' style='padding:0 8px 6px 8px'>{expl}</td></tr>"
        def judge(v, good_th=0.0, bad_th=-0.05):
            if v is None:
                return ("k. A.", "info")
            return ("positiv", "ok") if v > good_th else (("kritisch", "hoch") if v < bad_th else ("beobachten", "mittel"))
        rows = [
            row("Umsatztrend (90 Tage)", f"{fmt.signed_pct((slope or 0) * 30)} / 30 Tage" if slope is not None else "k. A.",
                judge((slope or 0) * 30, 0.0, -0.05), "Lineare Regression der Tagesumsätze, in % des Ø"),
            row("Volatilität (30 Tage)", fmt.pct(vol30, 0), ("normal", "ok") if vol30 and vol365 and vol30 <= vol365 * 1.2 else ("erhöht", "mittel"),
                f"Variationskoeffizient; Referenz 365 Tage: {fmt.pct(vol365, 0)}"),
            row("Erstzahlungen 90 T. vs. Vorjahr", fmt.signed_pct(M.safe_div((e90['erstzahlung'] or 0) - (e90ly['erstzahlung'] or 0), e90ly['erstzahlung'])),
                judge(M.safe_div((e90['erstzahlung'] or 0) - (e90ly['erstzahlung'] or 0), e90ly['erstzahlung'])), "Neukundenumsatz (Hauptkonto)"),
            row("Wiederkehrend 90 T. vs. Vorjahr", fmt.signed_pct(M.safe_div((e90['wiederkehrend'] or 0) - (e90ly['wiederkehrend'] or 0), e90ly['wiederkehrend'])),
                judge(M.safe_div((e90['wiederkehrend'] or 0) - (e90ly['wiederkehrend'] or 0), e90ly['wiederkehrend'])), "Bestandskundenumsatz (Hauptkonto)"),
        ]
        ab = m.monthly.dropna(subset=["aktive_abos"]).sort_values(["year", "month"]).tail(13)
        if len(ab) >= 2:
            ch = ab.aktive_abos.iloc[-1] / ab.aktive_abos.iloc[0] - 1
            rows.append(row("Aktive Abos (12 Monate)", f"{fmt.num(ab.aktive_abos.iloc[-1])} ({fmt.signed_pct(ch)})", judge(ch, 0, -0.03),
                            f"Monatsstatistik, Stand {int(ab.month.iloc[-1]):02d}/{int(ab.year.iloc[-1])} – Frühindikator für wiederkehrende Zahlungen"))
        st.markdown("<div class='panel'><table style='width:100%;border-collapse:collapse'>" + "".join(rows) + "</table></div>",
                    unsafe_allow_html=True)

    # ------------------------------------------------------------------ Frühwarnindikatoren
    st.markdown("##### Auffällige Entwicklungen & Frühwarnindikatoren")
    al = AL.all_alerts(m.daily, m.nl, t)
    if al.empty:
        C.empty_state("Keine Auffälligkeiten.")
    else:
        top = al[al.schweregrad.isin(["hoch", "mittel"])].head(6)
        if top.empty:
            st.success("Alle überwachten Kennzahlen bewegen sich im Bereich normaler Schwankungen.")
        cols = st.columns(3)
        for i, r in enumerate(top.itertuples()):
            val = fmt.pct(r.aktuell) if r.einheit == "%" else fmt.eur(r.aktuell, 2 if abs(r.aktuell or 0) < 10 else 0)
            ref = fmt.pct(r.referenz) if r.einheit == "%" else fmt.eur(r.referenz, 2 if abs(r.referenz or 0) < 10 else 0)
            cols[i % 3].markdown(
                f"<div class='alertcard {r.schweregrad}'>{C.badge(r.schweregrad.upper(), r.schweregrad)} "
                f"<b>{r.kennzahl}</b><br><span style='font-size:1.15rem'>{val}</span> "
                f"<span class='note'>vs. {ref} ({fmt.signed_pct(r.pct)})</span><br>"
                f"<span class='note'>{r.zeitraum} · {r.referenz_text} · z = {r.z:+.1f}</span></div>", unsafe_allow_html=True)
        C.note("Details, Erklärungsansätze und benötigte Informationen: Seite <b>Business Alerts</b>.")

    # ------------------------------------------------------------------ Monatsstruktur
    st.markdown("##### Umsatzstruktur je Monat (24 Monate)")
    a = M.aggregate(m.daily, "monat", ["umsatz_gesamt", "erstzahlung", "wiederkehrend", "split_summe"]).tail(24)
    a["rest"] = a.umsatz_gesamt - a.split_summe.fillna(0)
    nlm = m.nl.groupby("ym").umsatz.sum()
    a["nl"] = a.label.map(nlm)
    fig = go.Figure()
    for col, name, color in [("erstzahlung", "Erstzahlungen", SERIES[0]), ("wiederkehrend", "Wiederkehrend", SERIES[2]),
                             ("rest", "Nicht aufgeschlüsselt", "#5b6170")]:
        fig.add_bar(x=a.label, y=a[col], name=name, marker_color=color, marker_line=dict(color="#0f1115", width=1),
                    hovertemplate=f"{name}: %{{y:,.0f}} €<extra></extra>")
    fig.add_scatter(x=a.label, y=a.nl, name="Newsletter-Umsatz (gemessen)", mode="lines+markers",
                    line=dict(color=SERIES[3], width=2), marker=dict(size=7),
                    hovertemplate="Newsletter: %{y:,.0f} €<extra></extra>")
    fig.update_layout(barmode="stack", yaxis_tickformat=",.0f", yaxis_title="€", title="Erstzahlungen, wiederkehrende Zahlungen und Newsletter-Umsatz")
    C.chart(fig, "ex_struct", 380)
    C.note("Laufender Monat unvollständig. Erst-/Wiederkehrend-Aufteilung nur für das Hauptkonto (GTK) vorhanden.")

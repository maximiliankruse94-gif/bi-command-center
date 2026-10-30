from __future__ import annotations

import datetime as dt

import streamlit as st

from bi.analytics import alerts as AL

from .. import components as C
from .. import fmt


def _val(v, unit):
    if v is None:
        return "k. A."
    if unit == "%":
        return fmt.pct(v, 2)
    return fmt.eur(v, 3 if abs(v) < 1 else (2 if abs(v) < 100 else 0))


def render():
    ctx = st.session_state["ctx"]
    m = ctx["m"]
    C.header("Business Alerts & Frühwarnsystem", f"Bewertung zum Datenstand {m.asof:%d.%m.%Y} · statistische Regeln, keine KI")
    asof = st.date_input("Stichtag der Bewertung", value=m.asof, min_value=m.first + dt.timedelta(days=200), max_value=m.asof,
                         format="DD.MM.YYYY", key="al_asof",
                         help="Für Rückblicke: Wie hätte das Frühwarnsystem an einem früheren Tag ausgesehen?")
    al = AL.all_alerts(m.daily, m.nl, asof)
    if al.empty:
        C.empty_state("Keine Warnungen.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Hoch (strukturell, |z| ≥ 3)", int((al.schweregrad == "hoch").sum()))
    c2.metric("Mittel (auffällig, |z| ≥ 2)", int((al.schweregrad == "mittel").sum()))
    c3.metric("Normale Schwankung", int((al.schweregrad == "info").sum()))
    show_all = st.toggle("Auch normale Schwankungen anzeigen", value=False, key="al_all")
    rows = al if show_all else al[al.schweregrad != "info"]
    if rows.empty:
        st.success("Alle überwachten Kennzahlen bewegen sich im Bereich normaler Schwankungen.")
    for r in rows.itertuples():
        st.markdown(
            f"<div class='alertcard {r.schweregrad}'>{C.badge(r.schweregrad.upper(), r.schweregrad)} "
            f"{C.badge(r.einordnung, 'info')} <b style='font-size:1.02rem'>{r.kennzahl}</b><br>"
            f"<table style='width:100%;margin-top:6px'><tr>"
            f"<td><span class='note'>Zeitraum</span><br>{r.zeitraum}</td>"
            f"<td><span class='note'>Aktuell</span><br><b>{_val(r.aktuell, r.einheit)}</b></td>"
            f"<td><span class='note'>Referenz</span><br>{_val(r.referenz, r.einheit)}<br><span class='note'>{r.referenz_text}</span></td>"
            f"<td><span class='note'>Veränderung</span><br>{(fmt.pp(r.abs) if r.einheit == '%' else fmt.signed_eur(r.abs, 2 if abs(r.abs or 0) < 100 else 0))}"
            f" · {fmt.signed_pct(r.pct)}</td>"
            f"<td><span class='note'>Abweichung</span><br>z = {r.z:+.2f}</td></tr></table>"
            f"<div style='margin-top:8px'><span class='note'>Mögliche Erklärungen (zu prüfen):</span> {' · '.join(r.moegliche_erklaerungen)}</div>"
            f"<div><span class='note'>Noch benötigte Informationen:</span> {' · '.join(r.benoetigte_informationen)}</div></div>",
            unsafe_allow_html=True)
    with st.expander("Methodik"):
        st.markdown(AL.__doc__)
    C.download_buttons(al.assign(moegliche_erklaerungen=al.moegliche_erklaerungen.str.join("; "),
                                 benoetigte_informationen=al.benoetigte_informationen.str.join("; ")), "alerts", "al_dl")

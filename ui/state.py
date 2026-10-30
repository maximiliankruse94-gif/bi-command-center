"""Globaler Zustand: Daten-Cache, Synchronisierung, zentrale Zeitraum- und Filtersteuerung (Sidebar)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import streamlit as st

from bi import db
from bi.analytics import periods as P
from bi.analytics.model import Filters, Model, load_model
from bi.parsers.common import MONTH_NAMES_DE, WEEKDAYS_DE

from . import fmt


@st.cache_resource(show_spinner="Lade Daten …")
def _cached_model(run_key: str) -> Model:  # noqa: ARG001  (Cache-Schlüssel = letzter Sync)
    return load_model()


def model() -> Model:
    ls = db.last_sync()
    key = f"{ls['id']}-{ls['finished_at']}" if ls else "none"
    return _cached_model(key)


def auto_sync_if_due() -> None:
    """Fallback zum Cloud Scheduler: ist der letzte erfolgreiche Lauf älter als der heutige 06:00-Termin
    (Europe/Berlin), wird beim ersten Seitenaufruf synchronisiert."""
    from bi.config import TZ
    if st.session_state.get("_autosync_checked"):
        return
    st.session_state["_autosync_checked"] = True
    ls = db.last_sync()
    now = dt.datetime.now(TZ)
    due = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now < due:
        due -= dt.timedelta(days=1)
    last = ls["finished_at"].replace(tzinfo=dt.timezone.utc).astimezone(TZ) if ls and ls.get("finished_at") else None
    if last is None or last < due:
        run_sync_ui("auto")


def run_sync_ui(trigger: str = "manual") -> None:
    from bi.sync import run_sync
    with st.status("Synchronisiere alle Datenquellen …", expanded=trigger == "manual") as s:
        res = run_sync(trigger=trigger)
        st.session_state["last_sync_result"] = res
        if res.get("status") == "busy":
            s.update(label=res["message"], state="error")
            return
        s.update(label=f"Synchronisierung abgeschlossen – Status: {res['status']}",
                 state="complete" if res["status"] == "ok" else ("error" if res["status"] == "fehler" else "complete"))
    _cached_model.clear()


@dataclass
class Selection:
    period: P.Period
    comp: P.Period | None
    filters: Filters
    comp_mode: str


DEFAULTS = {"preset_mode": "Schnellauswahl", "preset": "Dieser Monat", "comp_mode": P.COMPARISONS[0],
            "f_prod": [], "f_wd": [], "f_hours": (0, 23), "f_subj": ""}


def _reset():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    for k in ("sel_year", "sel_q", "sel_month", "sel_kw", "custom_range", "custom_cmp"):
        st.session_state.pop(k, None)


def sidebar(m: Model, show_nl_filters: bool = True) -> Selection:
    for k, v in DEFAULTS.items():
        st.session_state.setdefault(k, v)
    sb = st.sidebar
    sb.markdown("### ⏱ Zeitraum")
    mode = sb.radio("Auswahl", ["Schnellauswahl", "Jahr", "Quartal", "Monat", "Kalenderwoche", "Individuell"],
                    key="preset_mode", horizontal=False, label_visibility="collapsed")
    years = list(range(m.asof.year, m.first.year - 1, -1))
    if mode == "Schnellauswahl":
        name = sb.selectbox("Zeitraum", P.PRESETS, key="preset")
        per = P.preset(name, m.asof, m.first)
    elif mode == "Jahr":
        y = sb.selectbox("Jahr", years, key="sel_year")
        per = P.year_period(y, m.asof)
    elif mode == "Quartal":
        y = sb.selectbox("Jahr", years, key="sel_year")
        q = sb.selectbox("Quartal", [1, 2, 3, 4], key="sel_q", index=(m.asof.month - 1) // 3 if y == m.asof.year else 0)
        per = P.quarter_period(y, q, m.asof)
    elif mode == "Monat":
        y = sb.selectbox("Jahr", years, key="sel_year")
        mm = sb.selectbox("Monat", list(range(1, 13)), format_func=lambda x: MONTH_NAMES_DE[x], key="sel_month",
                          index=m.asof.month - 1 if y == m.asof.year else 0)
        per = P.month_period(y, mm, m.asof)
    elif mode == "Kalenderwoche":
        y = sb.selectbox("ISO-Jahr", years, key="sel_year")
        maxw = dt.date(y, 12, 28).isocalendar()[1]
        w = sb.number_input("KW", 1, maxw, value=min(m.asof.isocalendar()[1], maxw) if y == m.asof.year else 1, key="sel_kw")
        per = P.week_period(y, int(w), m.asof)
    else:
        r = sb.date_input("Von – Bis", value=(m.asof - dt.timedelta(days=29), m.asof), min_value=m.first,
                          max_value=max(m.asof, m.nl_asof or m.asof), format="DD.MM.YYYY", key="custom_range")
        s, e = (r if isinstance(r, (tuple, list)) and len(r) == 2 else (r[0], r[0]) if isinstance(r, (tuple, list)) else (r, r))
        per = P.Period(s, e, f"{s:%d.%m.%Y} – {e:%d.%m.%Y}")
    if per.start > m.asof and mode != "Individuell":
        sb.warning("Für diesen Zeitraum liegen noch keine Tagesumsätze vor.")
    cm = sb.selectbox("Vergleich mit", P.COMPARISONS, key="comp_mode")
    custom = None
    if cm == "Frei wählbar":
        r2 = sb.date_input("Vergleichszeitraum", value=(P.shift_year(per.start), P.shift_year(per.end)),
                           format="DD.MM.YYYY", key="custom_cmp")
        if isinstance(r2, (tuple, list)) and len(r2) == 2:
            custom = P.Period(r2[0], r2[1], f"{r2[0]:%d.%m.%Y} – {r2[1]:%d.%m.%Y}")
    comp = P.comparison(per, cm, custom)
    sb.caption(f"**{per.label}**  \n{per.fmt()}" + (f"  \nvs. {comp.label}" if comp else ""))

    f = Filters()
    if show_nl_filters and not m.nl.empty:
        sb.markdown("### 🎯 Filter")
        prods = m.nl.groupby("produkt").size().sort_values(ascending=False).index.tolist()
        f.produkte = sb.multiselect("Produkt", prods, key="f_prod", placeholder="alle Produkte")
        f.wochentage = sb.multiselect("Wochentag", WEEKDAYS_DE, key="f_wd", placeholder="alle Wochentage")
        h = sb.slider("Versanduhrzeit (Stunde)", 0, 23, key="f_hours")
        f.stunde_von, f.stunde_bis = h
        f.betreff_suche = sb.text_input("Betreff enthält", key="f_subj", placeholder="Suchbegriff")
        if f.active():
            sb.caption("Produkt-, Betreff- und Uhrzeitfilter wirken auf Newsletter-Kennzahlen. "
                       "Der Wochentagsfilter wirkt zusätzlich auf Tagesumsätze.")
    sb.button("↺ Alle Filter zurücksetzen", on_click=_reset, use_container_width=True)
    return Selection(per, comp, f, cm)


def sync_box(m: Model, role: str) -> None:
    sb = st.sidebar
    if sb.button("⟳  JETZT AKTUALISIEREN", type="primary", use_container_width=True):
        run_sync_ui("manual")
        st.rerun()
    ls = db.last_sync()
    if ls:
        from bi.config import TZ
        t = ls["finished_at"] or ls["started_at"]
        tl = t.replace(tzinfo=dt.timezone.utc).astimezone(TZ) if t else None
        s = ls.get("summary") or {}
        icon = {"ok": "🟢", "warnung": "🟡", "fehler": "🔴", "running": "⏳"}.get(ls["status"], "⚪")
        sb.caption(f"{icon} Letzte Synchronisierung: {tl:%d.%m.%Y %H:%M} Uhr" if tl else "–")
        sb.caption(f"Datenstand Umsatz: **{m.asof:%d.%m.%Y}** · Newsletter: **{m.nl_asof:%d.%m.%Y}**" if m.nl_asof else "")
        if s.get("unknown_tabs"):
            sb.warning(f"{len(s['unknown_tabs'])} unbekannte(s) Tabellenblatt/-blätter – siehe Datenmanagement")
    res = st.session_state.pop("last_sync_result", None)
    if res and res.get("status") != "busy":
        with st.expander("Ergebnis der Synchronisierung", expanded=True):
            sync_result_view(res)


def sync_result_view(res: dict) -> None:
    c = st.columns(5)
    c[0].metric("Status", res.get("status", "–"))
    c[1].metric("Importierte Tabellen", res.get("imported_tabs", 0))
    c[2].metric("Neue Datensätze", fmt.num(res.get("new_records", 0)))
    c[3].metric("Aktualisierte Datensätze", fmt.num(res.get("updated_records", 0)))
    c[4].metric("Unbekannte Tabs", len(res.get("unknown_tabs", [])))
    for e in res.get("errors", []):
        st.error(e)
    for u in res.get("unknown_tabs", []):
        st.warning(f"Unbekanntes Tabellenblatt: **{u['workbook']} › {u['tab']}** – bitte unter Datenmanagement zuordnen.")
    for sc in res.get("structure_changes", []):
        st.warning(f"Strukturänderung erkannt: {sc}")
    for nt in res.get("new_tabs", []):
        st.info(f"Neues Tabellenblatt erkannt: {nt}")
    ic = res.get("issue_counts", {})
    st.caption(f"Datenqualitäts-Hinweise: {ic.get('error', 0)} Fehler · {ic.get('warning', 0)} Warnungen · {ic.get('info', 0)} Infos "
               f"(Details unter Datenmanagement › Datenqualität)")

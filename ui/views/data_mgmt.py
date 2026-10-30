from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import select

from bi import db
from bi.analytics import quality as Q
from bi.config import workbooks
from bi.detect import IGNORED_KINDS, IMPORT_KINDS

from .. import components as C
from .. import fmt
from ..state import run_sync_ui, sync_result_view

KIND_LABEL = {"daily": "Tagesstatistik", "weekly": "Wochenstatistik", "monthly": "Monatsstatistik", "newsletter": "Newsletter",
              "unknown": "UNBEKANNT", **{k: "ignoriert: " + v for k, v in IGNORED_KINDS.items()}}


def render():
    role = st.session_state["ctx"]["role"]
    C.header("Datenmanagement", "Datenquellen, Tabellenblätter, Importhistorie und Datenqualität")
    t1, t2, t3, t4 = st.tabs(["Datenquellen & Tabellenblätter", "Datenqualität", "Abgleich Tag/Woche/Monat", "Importhistorie"])
    with t1:
        _sources(role)
    with t2:
        _quality()
    with t3:
        _reconcile()
    with t4:
        _history()


def _sources(role):
    with db.engine().connect() as c:
        tabs = pd.read_sql(select(db.source_tab), c)
        wbs = pd.read_sql(select(db.workbook_state), c)
    for wb in workbooks():
        st.markdown(f"##### {wb['name']}")
        w = wbs[wbs.workbook == wb["key"]]
        info = f"[Google Sheet öffnen](https://docs.google.com/spreadsheets/d/{wb['file_id']}) · Typ erwartet: {', '.join(wb['expected_kinds'])}"
        if len(w):
            r = w.iloc[0]
            info += f" · letzter Abruf: {r.last_fetch:%d.%m.%Y %H:%M} UTC ({r.method})"
            if r.last_error:
                st.error(r.last_error)
        st.markdown(info)
        t = tabs[tabs.workbook == wb["key"]].copy()
        if t.empty:
            st.caption("Noch nicht synchronisiert.")
            continue
        t["Typ"] = t.kind.map(KIND_LABEL).fillna(t.kind)
        t["Erkennung"] = t.reasons.map(lambda r: " · ".join(r) if isinstance(r, list) else str(r))
        t["Struktur geändert"] = t.structure_changed.map({True: "⚠️ ja", False: ""})
        t = t.sort_values(["status", "tab"])
        st.dataframe(t[["tab", "status", "Typ", "confidence", "records", "Struktur geändert", "manual", "Erkennung"]].rename(columns={
            "tab": "Tabellenblatt", "status": "Status", "confidence": "Sicherheit", "records": "Datensätze", "manual": "manuell"}),
            hide_index=True, use_container_width=True, height=min(38 * len(t) + 40, 420),
            column_config={"Sicherheit": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
                           "Erkennung": st.column_config.TextColumn(width="large")})
    unknown = tabs[(tabs.status == "unbekannt") & tabs.removed_at.isna()]
    st.markdown("##### Manuelle Zuordnung")
    if unknown.empty:
        st.success("Alle Tabellenblätter sind eindeutig zugeordnet.")
    if role != "admin":
        st.caption("Zuordnungen können nur Administratoren ändern.")
        return
    options = list(IMPORT_KINDS) + ["ignore"]
    all_tabs = tabs[tabs.removed_at.isna()].sort_values(["status", "workbook", "tab"])
    labels = [f"{r.workbook} › {r.tab} ({r.status})" for r in all_tabs.itertuples()]
    if labels:
        idx = st.selectbox("Tabellenblatt", range(len(labels)), format_func=lambda i: labels[i], key="map_tab")
        r = all_tabs.iloc[idx]
        kind = st.selectbox("Zuordnen als", options, format_func=lambda k: KIND_LABEL.get(k, "ignorieren"), key="map_kind")
        if st.button("Zuordnung speichern & neu synchronisieren", type="primary"):
            db.save_manual_mapping(r.workbook, r.tab, kind, st.session_state["ctx"]["user"])
            st.success("Gespeichert. Für eine dauerhafte, versionierte Ablage zusätzlich in config/tab_mappings.yaml eintragen:")
            st.code(f"- workbook: {r.workbook}\n  tab: \"{r.tab}\"\n  kind: {kind}", language="yaml")
            run_sync_ui("manual")
        C.note("Die Zuordnung wird in der Datenbank gespeichert und bei jeder Synchronisierung angewendet. Ein falsch zugeordnetes Blatt "
               "wird vom Parser abgelehnt (Fehlermeldung), statt falsche Daten zu importieren.")


def _quality():
    ls = db.last_sync()
    if not ls:
        st.info("Noch keine Synchronisierung.")
        return
    with db.engine().connect() as c:
        iss = pd.read_sql(select(db.dq_issue).where(db.dq_issue.c.run_id == ls["id"]), c)
    if iss.empty:
        st.success("Keine Datenqualitätshinweise.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Fehler", int((iss.severity == "error").sum()))
    c2.metric("Warnungen", int((iss.severity == "warning").sum()))
    c3.metric("Hinweise", int((iss.severity == "info").sum()))
    summ = iss.groupby(["category", "severity"]).size().reset_index(name="Anzahl").sort_values("Anzahl", ascending=False)
    st.dataframe(summ.rename(columns={"category": "Kategorie", "severity": "Schwere"}), hide_index=True, use_container_width=True)
    sev = st.multiselect("Schwere", ["error", "warning", "info"], default=["error", "warning"], key="dq_sev")
    cat = st.multiselect("Kategorie", sorted(iss.category.unique()), key="dq_cat")
    v = iss[iss.severity.isin(sev)]
    if cat:
        v = v[v.category.isin(cat)]
    st.dataframe(v[["severity", "category", "workbook", "tab", "row", "message"]].rename(columns={
        "severity": "Schwere", "category": "Kategorie", "workbook": "Arbeitsmappe", "tab": "Tabellenblatt", "row": "Zeile",
        "message": "Meldung"}), hide_index=True, use_container_width=True, height=460,
        column_config={"Meldung": st.column_config.TextColumn(width="large")})
    C.download_buttons(iss, "datenqualitaet", "dq_dl")
    md = Q.missing_days()
    if md:
        st.warning(f"{len(md)} fehlende Kalendertage in den Tagesstatistiken: " + ", ".join(d.strftime("%d.%m.%Y") for d in md[:40]) +
                   (" …" if len(md) > 40 else ""))


def _reconcile():
    st.markdown("**Maßgebliche Quelle:** Tagesstatistiken. Wochen- und Monatswerte werden nur zur Validierung verglichen – "
                "niemals addiert. CopeCart-Umsätze sind nur in Wochen/Monaten enthalten und werden für den Abgleich herausgerechnet.")
    rm = Q.reconcile_monthly()
    if not rm.empty:
        ok = (rm.status == "ok").sum(); dev = (rm.status == "Abweichung").sum()
        st.caption(f"Monate: {ok} übereinstimmend (±0,5 %), {dev} mit Abweichung, {(rm.status == 'nur Monatsdaten').sum()} nur in Monatsdaten")
        rm["label"] = rm.apply(lambda r: f"{int(r.year)}-{int(r.month):02d}", axis=1)
        fig = go.Figure(go.Bar(x=rm.label, y=rm.diff_pct, marker_color=["#d03b3b" if s == "Abweichung" else "#3987e5" for s in rm.status],
                               hovertemplate="%{x}: %{y:.2%}<extra></extra>"))
        fig.update_layout(title="Abweichung Summe Tagesumsätze vs. Monatsstatistik (ohne CopeCart)", yaxis_tickformat=".1%", hovermode="closest")
        C.chart(fig, "rec_m", 300)
        st.dataframe(rm[["label", "tage", "tage_im_monat", "umsatz_tage", "umsatz_monat_ohne_cc", "copecart", "diff", "diff_pct", "status"]]
                     .rename(columns={"label": "Monat", "tage": "Tage erfasst", "tage_im_monat": "Tage im Monat", "umsatz_tage": "Σ Tage",
                                      "umsatz_monat_ohne_cc": "Monat (ohne CopeCart)", "copecart": "CopeCart (nur Monat)", "diff": "Differenz",
                                      "diff_pct": "Differenz %", "status": "Status"}).iloc[::-1]
                     .style.format({"Σ Tage": fmt.eur, "Monat (ohne CopeCart)": fmt.eur, "CopeCart (nur Monat)": fmt.eur,
                                    "Differenz": fmt.signed_eur, "Differenz %": lambda v: fmt.signed_pct(v, 2)}),
                     hide_index=True, use_container_width=True, height=360)
    rw = Q.reconcile_weekly()
    if not rw.empty:
        st.markdown("**Wochenabgleich**")
        st.caption(f"Wochen: {(rw.status == 'ok').sum()} übereinstimmend, {(rw.status == 'Abweichung').sum()} mit Abweichung, "
                   f"{(rw.status == 'Woche unvollständig').sum()} unvollständig")
        st.dataframe(rw[rw.status != "ok"].iloc[::-1], hide_index=True, use_container_width=True, height=300)


def _history():
    with db.engine().connect() as c:
        runs = pd.read_sql(select(db.sync_run).order_by(db.sync_run.c.id.desc()).limit(50), c)
    if runs.empty:
        st.info("Keine Läufe.")
        return
    runs["neu"] = runs.summary.map(lambda s: (s or {}).get("new_records"))
    runs["aktualisiert"] = runs.summary.map(lambda s: (s or {}).get("updated_records"))
    runs["entfernt"] = runs.summary.map(lambda s: (s or {}).get("removed_records"))
    runs["unbekannte Tabs"] = runs.summary.map(lambda s: len((s or {}).get("unknown_tabs", [])))
    runs["Fehler"] = runs.summary.map(lambda s: "; ".join((s or {}).get("errors", [])))
    st.dataframe(runs[["id", "started_at", "finished_at", "trigger", "status", "neu", "aktualisiert", "entfernt", "unbekannte Tabs", "Fehler"]]
                 .rename(columns={"started_at": "Start (UTC)", "finished_at": "Ende (UTC)", "trigger": "Auslöser"}),
                 hide_index=True, use_container_width=True)
    sel = st.selectbox("Details zu Lauf", runs.id.tolist(), key="run_sel")
    s = runs[runs.id == sel].iloc[0].summary or {}
    sync_result_view({**s, "status": runs[runs.id == sel].iloc[0].status})
    with st.expander("Rohdaten"):
        st.json(s)

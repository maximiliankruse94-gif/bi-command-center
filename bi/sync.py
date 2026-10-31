"""Synchronisierung Google Sheets -> Datenbank.

Aufruf:
  * Dashboard-Button „JETZT AKTUALISIEREN“            -> run_sync(trigger="manual")
  * Cloud Scheduler 06:00 Europe/Berlin (Cloud Run Job) -> python -m bi.sync --trigger scheduled
  * lokal mit XLSX-Dateien                              -> python -m bi.sync --mode local

Sicherheit gegen Datenverlust:
  * Lesefehler einer Arbeitsmappe -> deren Daten bleiben unverändert erhalten.
  * Unbekannte/strukturveränderte Tabs -> werden NICHT importiert, bisherige Daten bleiben.
  * Alle Schreibvorgänge eines Laufs laufen in EINER Transaktion (alles oder nichts).
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import traceback
from typing import Any

import pandas as pd
from sqlalchemy import insert, select, update

from . import db
from .config import ROOT, source_mode, workbooks
from .detect import IGNORED_KINDS, PARSERS, classify
from .parsers.base import Issue
from .parsers.newsletter import finalize as finalize_newsletter
from .sources import loader

log = logging.getLogger("bicc.sync")
LOCK_MINUTES = 15


def _fetch(wb: dict, mode: str, known_modified: str | None, force: bool) -> loader.FetchResult | None:
    if mode == "google":
        return loader.fetch_drive_export(wb["file_id"], None if force else known_modified)
    if mode == "public_link":
        return loader.fetch_public_link(wb["file_id"])
    path = wb.get("local_file")
    p = (ROOT / path) if path and not str(path).startswith("/") else path
    if not p or not __import__("os").path.exists(str(p)):
        raise RuntimeError("Kein Google-Zugang eingerichtet: In den Secrets fehlen BICC_SOURCE_MODE = \"google\" und "
                           "GOOGLE_SERVICE_ACCOUNT_JSON (oder BICC_SOURCE_MODE = \"public_link\"). Lokale Datei nicht vorhanden.")
    return loader.fetch_local(str(p))


def _dedupe_cross_tab(name: str, df: pd.DataFrame, issues: list[Issue]) -> pd.DataFrame:
    if df.empty:
        return df
    if name == "daily":
        df = df.copy()
        df["pref"] = [0 if (pd.notna(r.date) and r.source_tab and _tab_matches_month(r.source_tab, r.date)) else 1
                       for r in df.itertuples()]
        df = df.sort_values(["date", "pref"])
        dup = df[df.duplicated("date", keep="first")]
        for r in dup.itertuples():
            issues.append(Issue("warning", "duplikat", f"Tag {r.date:%d.%m.%Y} zusätzlich in Tab '{r.source_tab}' -> ignoriert",
                                "daily", r.source_tab, r.source_row))
        return df.drop_duplicates("date", keep="first").drop(columns="pref")
    if name == "weekly":
        df = df.copy()
        df["pref"] = [0 if str(r.iso_year) == str(r.source_tab).strip() else 1 for r in df.itertuples()]
        df = df.sort_values(["iso_year", "iso_week", "pref"])
        dup = df[df.duplicated(["iso_year", "iso_week"], keep="first")]
        for r in dup.itertuples():
            issues.append(Issue("info", "duplikat",
                                f"KW {r.iso_week}/{r.iso_year} steht auch im Tab '{r.source_tab}' (Jahreswechsel) -> nur einmal gezählt",
                                "weekly", r.source_tab, r.source_row))
        return df.drop_duplicates(["iso_year", "iso_week"], keep="first").drop(columns="pref")
    if name == "monthly":
        dup = df[df.duplicated(["year", "month"], keep="first")]
        for r in dup.itertuples():
            issues.append(Issue("warning", "duplikat", f"Monat {r.month:02d}/{r.year} mehrfach (Tab '{r.source_tab}') -> erster verwendet",
                                "monthly", r.source_tab, r.source_row))
        return df.drop_duplicates(["year", "month"], keep="first")
    if name == "abo_product":
        return df.drop_duplicates(["year", "month", "product"], keep="first")
    return df


def _tab_matches_month(tab: str, d: dt.date) -> bool:
    from .parsers.common import parse_month_label
    y, m = parse_month_label(tab.strip())
    return y == d.year and m == d.month


def _acquire_lock(conn, trigger: str) -> int | None:
    cutoff = db.now() - dt.timedelta(minutes=LOCK_MINUTES)
    running = conn.execute(select(db.sync_run).where(db.sync_run.c.status == "running",
                                                     db.sync_run.c.started_at > cutoff)).first()
    if running:
        return None
    res = conn.execute(insert(db.sync_run).values(started_at=db.now(), trigger=trigger, status="running", summary={}))
    return res.inserted_primary_key[0]


def run_sync(trigger: str = "manual", mode: str | None = None, force: bool = False) -> dict[str, Any]:
    mode = mode or source_mode()
    eng = db.engine()
    with eng.begin() as conn:
        run_id = _acquire_lock(conn, trigger)
    if run_id is None:
        return {"status": "busy", "message": "Es läuft bereits eine Synchronisierung. Bitte in einigen Minuten erneut versuchen."}

    summary: dict[str, Any] = {"mode": mode, "workbooks": {}, "datasets": {}, "unknown_tabs": [], "structure_changes": [],
                               "errors": [], "imported_tabs": 0, "new_tabs": []}
    issues: list[Issue] = []
    datasets: dict[str, list[pd.DataFrame]] = {}
    scope: dict[str, set[str]] = {}
    tab_rows: list[dict] = []
    manual = db.manual_mappings()
    try:
        with eng.connect() as c:
            wb_state = {r.workbook: dict(r._mapping) for r in c.execute(select(db.workbook_state))}
            known_tabs = {(r.workbook, r.tab): dict(r._mapping) for r in c.execute(select(db.source_tab))}
            have_data = {n: c.execute(select(t).limit(1)).first() is not None for n, (t, _) in db.FACT_TABLES.items()}
        for wb in workbooks():
            key = wb["key"]
            st = wb_state.get(key, {})
            wsum: dict[str, Any] = {"name": wb.get("name", key), "status": "ok", "tabs": 0}
            summary["workbooks"][key] = wsum
            try:
                expected_have = all(have_data.get(k, False) for k in wb.get("expected_kinds", []))
                fr = _fetch(wb, mode, st.get("modified_time"), force or not expected_have)
            except Exception as e:  # noqa: BLE001
                msg = f"{wb.get('name', key)}: Abruf fehlgeschlagen – bestehende Daten bleiben erhalten ({type(e).__name__}: {e})"
                log.exception(msg)
                wsum["status"] = "fehler"
                summary["errors"].append(msg)
                issues.append(Issue("error", "abruf", msg, key))
                with eng.begin() as conn:
                    _save_wb_state(conn, key, st.get("modified_time"), None, None, msg)
                continue
            wsum["method"] = fr.method
            if fr.method == "unchanged":
                wsum["status"] = "unverändert"
                with eng.begin() as conn:
                    _save_wb_state(conn, key, fr.modified_time, "unchanged", fr.title, None)
                continue
            wsum["tabs"] = len(fr.tabs)
            present = set()
            for tab, rows in fr.tabs.items():
                tname = tab.strip()
                present.add(tname)
                cl = classify(key, tab, rows, manual, wb.get("expected_kinds"))
                prev = known_tabs.get((key, tname))
                changed = bool(prev and prev.get("signature") and prev["signature"] != cl.signature)
                if prev is None and known_tabs:
                    summary["new_tabs"].append(f"{wb.get('name', key)} › {tname} ({cl.status})")
                n_rec = None
                if cl.kind in PARSERS:
                    try:
                        res = PARSERS[cl.kind].parse(rows, tab, key, **cl.meta)
                        for i in res.issues:
                            i.tab = i.tab.strip() if i.tab else tname
                        issues.extend(res.issues)
                        datasets.setdefault(res.dataset, []).append(res.df)
                        scope.setdefault(res.dataset, set()).add(tname)
                        for ename, edf in res.extra.items():
                            datasets.setdefault(ename, []).append(edf)
                            scope.setdefault(ename, set()).add(tname)
                        n_rec = len(res.df)
                        summary["imported_tabs"] += 1
                    except Exception as e:  # noqa: BLE001
                        msg = f"{tname}: Parserfehler ({type(e).__name__}: {e}) – Tab übersprungen, bisherige Daten bleiben"
                        log.exception(msg)
                        issues.append(Issue("error", "parser", msg, key, tname))
                        summary["errors"].append(msg)
                elif cl.kind == "unknown":
                    summary["unknown_tabs"].append({"workbook": key, "tab": tname, "reasons": cl.reasons,
                                                    "candidate": cl.meta.get("candidate")})
                    issues.append(Issue("warning", "unbekannt", f"Unbekanntes Tabellenblatt '{tname}' – nicht importiert. "
                                        "Bitte unter Datenmanagement zuordnen.", key, tname))
                if changed:
                    summary["structure_changes"].append(f"{wb.get('name', key)} › {tname}")
                    issues.append(Issue("warning", "strukturaenderung",
                                        f"Spaltenstruktur von '{tname}' hat sich seit dem letzten Import geändert – Zuordnung bitte prüfen.",
                                        key, tname))
                tab_rows.append({"workbook": key, "tab": tname, "kind": cl.kind, "confidence": cl.confidence,
                                 "status": cl.status, "reasons": cl.reasons, "signature": cl.signature,
                                 "previous_signature": prev.get("signature") if prev else None,
                                 "structure_changed": changed, "records": n_rec, "manual": cl.manual, "_new": prev is None})
            removed = [t for (w, t) in known_tabs if w == key and t not in present and not known_tabs[(w, t)].get("removed_at")]
            for t in removed:
                issues.append(Issue("warning", "struktur", f"Tabellenblatt '{t}' existiert nicht mehr", key, t))
                tab_rows.append({"workbook": key, "tab": t, "_removed": True})
                kind = known_tabs[(key, t)].get("kind")
                if kind in PARSERS:  # Datensätze verschwundener Tabs als entfernt markieren
                    ds = PARSERS[kind].DATASET
                    scope.setdefault(ds, set()).add(t)
                    datasets.setdefault(ds, [])
            wb["_fetch"] = fr
        # ---------------------------------------------------------- Datasets zusammenführen
        final: dict[str, pd.DataFrame] = {}
        for name, frames in datasets.items():
            frames = [f for f in frames if f is not None and not f.empty]
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            if name == "newsletter" and not df.empty:
                df, nl_issues = finalize_newsletter(df)
                issues.extend(nl_issues)
            else:
                df = _dedupe_cross_tab(name, df, issues)
            final[name] = df
        # ---------------------------------------------------------- Schreiben (eine Transaktion)
        with eng.begin() as conn:
            for name, df in final.items():
                summary["datasets"][name] = db.upsert_dataset(conn, name, df, scope.get(name, set()))
            ts = db.now()
            for tr in tab_rows:
                cond = [db.source_tab.c.workbook == tr["workbook"], db.source_tab.c.tab == tr["tab"]]
                if tr.get("_removed"):
                    conn.execute(update(db.source_tab).where(*cond).values(removed_at=ts, status="entfernt"))
                    continue
                vals = {k: v for k, v in tr.items() if not k.startswith("_")}
                if tr["_new"]:
                    conn.execute(insert(db.source_tab).values(**vals, first_seen=ts, last_seen=ts, removed_at=None))
                else:
                    conn.execute(update(db.source_tab).where(*cond).values(**vals, last_seen=ts, removed_at=None))
            for wb in workbooks():
                fr = wb.pop("_fetch", None)
                if fr is not None:
                    _save_wb_state(conn, wb["key"], fr.modified_time, fr.method, fr.title, None)
        # ---------------------------------------------------------- Datenqualität (Abgleich der Ebenen)
        from .analytics import quality
        issues.extend(quality.cross_checks())
        status = "fehler" if summary["errors"] and not summary["imported_tabs"] else (
            "warnung" if summary["errors"] or summary["unknown_tabs"] or summary["structure_changes"] else "ok")
    except Exception as e:  # noqa: BLE001
        status = "fehler"
        summary["errors"].append(f"Synchronisierung abgebrochen: {type(e).__name__}: {e}")
        summary["traceback"] = traceback.format_exc()[-2000:]
        log.exception("Sync abgebrochen")
    summary["issue_counts"] = {s: sum(1 for i in issues if i.severity == s) for s in ("error", "warning", "info")}
    summary["new_records"] = sum(v.get("neu", 0) for v in summary["datasets"].values())
    summary["updated_records"] = sum(v.get("aktualisiert", 0) + v.get("wiederhergestellt", 0) for v in summary["datasets"].values())
    summary["removed_records"] = sum(v.get("entfernt", 0) for v in summary["datasets"].values())
    with eng.begin() as conn:
        conn.execute(update(db.sync_run).where(db.sync_run.c.id == run_id).values(
            finished_at=db.now(), status=status, summary=_jsonable(summary)))
        if issues:
            conn.execute(insert(db.dq_issue), [{**i.as_dict(), "run_id": run_id} for i in issues])
    summary["status"] = status
    summary["run_id"] = run_id
    return summary


def _save_wb_state(conn, key, modified, method, title, err):
    from sqlalchemy import delete
    conn.execute(delete(db.workbook_state).where(db.workbook_state.c.workbook == key))
    conn.execute(insert(db.workbook_state).values(workbook=key, modified_time=modified, last_fetch=db.now(),
                                                  method=method, title=title, last_error=err))


def _jsonable(o):
    import json
    return json.loads(json.dumps(o, default=str))


def main() -> None:
    ap = argparse.ArgumentParser(description="BI Command Center – Synchronisierung")
    ap.add_argument("--trigger", default="cli")
    ap.add_argument("--mode", default=None, choices=[None, "google", "public_link", "local"])
    ap.add_argument("--force", action="store_true", help="auch unveränderte Arbeitsmappen neu einlesen")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    res = run_sync(a.trigger, a.mode, a.force)
    log.info("Status: %s | neu: %s | aktualisiert: %s | entfernt: %s | unbekannte Tabs: %s | Fehler: %s",
             res.get("status"), res.get("new_records"), res.get("updated_records"), res.get("removed_records"),
             len(res.get("unknown_tabs", [])), res.get("errors"))
    if res.get("status") == "fehler":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

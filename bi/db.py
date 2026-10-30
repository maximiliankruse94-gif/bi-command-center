"""Datenbankschicht (SQLAlchemy Core) – SQLite lokal, PostgreSQL produktiv.

Grundsätze
  * Jede Faktentabelle hat einen fachlichen Primärschlüssel (Tag / ISO-KW / Monat / send_id).
  * row_hash erkennt geänderte Datensätze; nur echte Änderungen werden geschrieben.
  * Datensätze werden nie physisch gelöscht: verschwindet eine Zeile aus dem Sheet,
    wird sie mit deleted_at markiert (Soft Delete) und aus Analysen ausgeschlossen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from functools import lru_cache
from typing import Any

import pandas as pd
from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, Float, Integer, MetaData, String, Table, Text,
                        create_engine, delete, insert, select, update)
from sqlalchemy.engine import Engine

from .config import database_url

md = MetaData()

AUDIT = lambda: [Column("row_hash", String(40)), Column("first_imported_at", DateTime),  # noqa: E731
                 Column("updated_at", DateTime), Column("deleted_at", DateTime, nullable=True)]

daily = Table(
    "fact_daily", md,
    Column("date", Date, primary_key=True),
    *[Column(c, Float) for c in [
        "umsatz_gtk", "umsatz_littlefreilich", "umsatz_gunnarkessler", "umsatz_sonstige", "umsatz_gesamt",
        "rueckgaben", "ruecklastschriften", "netto_umsatz", "netto_umsatz_sheet", "werbung", "werbung_gesamt",
        "kosten_gesamt", "kosten_gesamt_sheet", "buchkosten", "verdienst", "verdienst_sheet",
        "einmalzahlung", "abo_start", "abo_wiederkehrend", "rate_start", "rate_wiederkehrend",
        "split_summe", "erstzahlung", "wiederkehrend"]],
    Column("bemerkung", Text), Column("source_tab", String(80)), Column("source_row", Integer),
    *AUDIT(),
)
weekly = Table(
    "fact_weekly", md,
    Column("iso_year", Integer, primary_key=True), Column("iso_week", Integer, primary_key=True),
    Column("date_from", Date), Column("date_to", Date), Column("kw_sheet", Integer),
    *[Column(c, Float) for c in [
        "umsatz_gesamt", "umsatz_gtk", "umsatz_littlefreilich", "umsatz_gunnarkessler", "umsatz_sonstige",
        "umsatz_copecart", "zahlungen_stk", "rueckgaben", "rueckgaben_stk", "werbekosten", "buchkosten",
        "verdienst", "aktive_abos", "neue_abos", "kuendigungen"]],
    Column("source_tab", String(80)), Column("source_row", Integer),
    *AUDIT(),
)
monthly = Table(
    "fact_monthly", md,
    Column("year", Integer, primary_key=True), Column("month", Integer, primary_key=True),
    *[Column(c, Float) for c in [
        "zahlungen_stk", "umsatz_brutto", "umsatz_netto", "umsatz_gtk", "umsatz_littlefreilich",
        "umsatz_gunnarkessler", "umsatz_sonstige", "umsatz_copecart", "rueckgaben_stk", "rueckgaben",
        "werbekosten", "buchkosten", "kosten_gesamt", "verdienst", "brutto_einmalzahlung", "brutto_abo_start",
        "brutto_wiederkehrend", "aktive_abos", "neue_abos", "kuendigungen"]],
    Column("bemerkung", Text), Column("source_tab", String(80)), Column("source_row", Integer),
    *AUDIT(),
)
abo_product = Table(
    "fact_abo_product", md,
    Column("year", Integer, primary_key=True), Column("month", Integer, primary_key=True),
    Column("product", String(60), primary_key=True),
    Column("aktive_abos", Float), Column("neue_abos", Float), Column("kuendigungen", Float),
    Column("source_tab", String(80)),
    *AUDIT(),
)
newsletter = Table(
    "fact_newsletter_send", md,
    Column("send_id", String(16), primary_key=True),
    Column("send_date", Date, index=True), Column("uhrzeit", String(5)),
    Column("produkt_raw", String(120)), Column("produkt_key", String(120)), Column("produkt_id", Float),
    Column("campaign_key", String(60)),
    *[Column(c, Float) for c in [
        "empfaenger", "oeffnungen", "klicks", "kaeufe", "umsatz", "folgezahlungen", "folgeeinnahmen",
        "open_rate_sheet", "click_rate_sheet", "conv_rate_sheet", "epc_sheet"]],
    Column("betreff", Text), Column("source_tab", String(80)), Column("source_row", Integer),
    *AUDIT(),
)
source_tab = Table(
    "meta_source_tab", md,
    Column("workbook", String(40), primary_key=True), Column("tab", String(120), primary_key=True),
    Column("kind", String(40)), Column("confidence", Float), Column("status", String(20)),
    Column("reasons", JSON), Column("signature", String(20)), Column("previous_signature", String(20)),
    Column("structure_changed", Boolean, default=False), Column("records", Integer),
    Column("manual", Boolean, default=False), Column("first_seen", DateTime), Column("last_seen", DateTime),
    Column("removed_at", DateTime, nullable=True),
)
workbook_state = Table(
    "meta_workbook", md,
    Column("workbook", String(40), primary_key=True), Column("modified_time", String(40)),
    Column("last_fetch", DateTime), Column("method", String(30)), Column("title", String(200)),
    Column("last_error", Text),
)
sync_run = Table(
    "meta_sync_run", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("started_at", DateTime), Column("finished_at", DateTime), Column("trigger", String(20)),
    Column("status", String(20)), Column("summary", JSON),
)
dq_issue = Table(
    "meta_dq_issue", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", Integer, index=True), Column("severity", String(10)), Column("category", String(40)),
    Column("workbook", String(40)), Column("tab", String(120)), Column("row", Integer), Column("message", Text),
)
tab_mapping = Table(
    "meta_tab_mapping", md,
    Column("workbook", String(40), primary_key=True), Column("tab", String(120), primary_key=True),
    Column("kind", String(40)), Column("created_at", DateTime), Column("created_by", String(120)),
)

FACT_TABLES = {"daily": (daily, ["date"]), "weekly": (weekly, ["iso_year", "iso_week"]),
               "monthly": (monthly, ["year", "month"]), "abo_product": (abo_product, ["year", "month", "product"]),
               "newsletter": (newsletter, ["send_id"])}


@lru_cache
def engine() -> Engine:
    url = database_url()
    kw: dict[str, Any] = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
    eng = create_engine(url, **kw)
    md.create_all(eng)
    return eng


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _clean(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.date()
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return v.item()
        except Exception:  # noqa: BLE001
            return v
    return v


def row_hash(rec: dict, cols: list[str]) -> str:
    payload = json.dumps([_clean(rec.get(c)) for c in cols], default=str, sort_keys=False)
    return hashlib.sha1(payload.encode()).hexdigest()


def upsert_dataset(conn, name: str, df: pd.DataFrame, scope_tabs: set[str]) -> dict[str, int]:
    """Schreibt ein Dataset differenziell.

    scope_tabs: Tabs, die in diesem Lauf erfolgreich gelesen wurden. Nur Datensätze aus diesen
    Tabs dürfen als 'entfernt' markiert werden – fällt eine Quelle aus, bleiben ihre Daten erhalten.
    """
    table, pk = FACT_TABLES[name]
    cols = [c.name for c in table.columns if c.name not in ("row_hash", "first_imported_at", "updated_at", "deleted_at")]
    data_cols = [c for c in cols if c not in ("source_row",)]
    existing = {tuple(_clean(r._mapping[k]) for k in pk): (r.row_hash, r.deleted_at, r.source_tab)
                for r in conn.execute(select(*[table.c[k] for k in pk], table.c.row_hash, table.c.deleted_at,
                                             table.c.source_tab))}
    ts = now()
    stats = {"neu": 0, "aktualisiert": 0, "unveraendert": 0, "entfernt": 0, "wiederhergestellt": 0}
    seen = set()
    records = [] if df is None or df.empty else df.to_dict("records")
    for rec in records:
        rec = {k: _clean(rec.get(k)) for k in cols}
        key = tuple(rec[k] for k in pk)
        seen.add(key)
        h = row_hash(rec, data_cols)
        if key not in existing:
            conn.execute(insert(table).values(**rec, row_hash=h, first_imported_at=ts, updated_at=ts, deleted_at=None))
            stats["neu"] += 1
            continue
        old_hash, deleted_at, _ = existing[key]
        cond = [table.c[k] == rec[k] for k in pk]
        if old_hash != h or deleted_at is not None:
            conn.execute(update(table).where(*cond).values(**rec, row_hash=h, updated_at=ts, deleted_at=None))
            stats["wiederhergestellt" if deleted_at is not None and old_hash == h else "aktualisiert"] += 1
        else:
            if rec.get("source_row") is not None:
                conn.execute(update(table).where(*cond).values(source_row=rec["source_row"]))
            stats["unveraendert"] += 1
    for key, (_, deleted_at, src) in existing.items():
        if key not in seen and deleted_at is None and src in scope_tabs:
            conn.execute(update(table).where(*[table.c[k] == v for k, v in zip(pk, key)]).values(deleted_at=ts))
            stats["entfernt"] += 1
    return stats


def read_table(name: str, include_deleted: bool = False) -> pd.DataFrame:
    table = FACT_TABLES[name][0] if name in FACT_TABLES else md.tables[name]
    q = select(table)
    if "deleted_at" in table.c and not include_deleted:
        q = q.where(table.c.deleted_at.is_(None))
    with engine().connect() as c:
        return pd.read_sql(q, c)


def manual_mappings() -> dict[tuple[str, str], str]:
    from .config import yaml_tab_mappings
    out = {}
    with engine().connect() as c:
        for r in c.execute(select(tab_mapping)):
            out[(r.workbook, r.tab)] = r.kind
    for m in yaml_tab_mappings():  # Konfigurationsdatei hat Vorrang
        out[(m["workbook"], str(m["tab"]).strip())] = m["kind"]
    return out


def save_manual_mapping(workbook: str, tab: str, kind: str, user: str = "") -> None:
    with engine().begin() as c:
        c.execute(delete(tab_mapping).where(tab_mapping.c.workbook == workbook, tab_mapping.c.tab == tab))
        c.execute(insert(tab_mapping).values(workbook=workbook, tab=tab, kind=kind, created_at=now(), created_by=user))


def last_sync() -> dict | None:
    with engine().connect() as c:
        r = c.execute(select(sync_run).order_by(sync_run.c.id.desc()).limit(1)).first()
        return dict(r._mapping) if r else None

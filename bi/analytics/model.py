"""Analyse-Datenmodell: lädt die Faktentabellen und ergänzt Kalender- und Produktdimension.

Kalenderdimension je Datensatz: Datum, Wochentag, ISO-KW (+ISO-Jahr), Monat, Quartal, Jahr.
Produktdimension: Schreibvarianten zusammengeführt (Groß/Klein, Leerzeichen, Bindestriche)
+ manuelle Aliase aus config/product_aliases.yaml.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import db
from ..config import product_aliases
from ..parsers.common import MONTH_NAMES_DE, WEEKDAYS_DE
from ..parsers.newsletter import product_key

APPLE_MPP_DATE = dt.date(2021, 9, 20)  # iOS 15 / Apple Mail Privacy Protection


def add_calendar(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty:
        return df
    s = pd.to_datetime(df[col])
    df[col] = s.dt.date
    iso = s.dt.isocalendar()
    df["jahr"] = s.dt.year
    df["quartal"] = s.dt.quarter
    df["monat"] = s.dt.month
    df["monat_name"] = s.dt.month.map(lambda m: MONTH_NAMES_DE[m])
    df["iso_jahr"] = iso.year.astype(int)
    df["kw"] = iso.week.astype(int)
    df["wochentag_nr"] = s.dt.weekday
    df["wochentag"] = s.dt.weekday.map(lambda w: WEEKDAYS_DE[w])
    df["ym"] = s.dt.to_period("M").astype(str)
    return df


def calendar_dim(start: dt.date, end: dt.date) -> pd.DataFrame:
    return add_calendar(pd.DataFrame({"date": pd.date_range(start, end, freq="D")}), "date")


def _product_display(nl: pd.DataFrame) -> pd.DataFrame:
    aliases = {product_key(k): product_key(v) for k, v in product_aliases().items()}
    nl["produkt_key"] = nl["produkt_key"].map(lambda k: aliases.get(k, k) if isinstance(k, str) else "UNBEKANNT")
    disp = (nl.dropna(subset=["produkt_raw"]).groupby(["produkt_key", "produkt_raw"]).size().reset_index(name="n")
            .sort_values("n", ascending=False).drop_duplicates("produkt_key").set_index("produkt_key")["produkt_raw"])
    for k, v in product_aliases().items():  # Zielname aus Aliasliste hat Vorrang
        disp[product_key(v)] = v
    nl["produkt"] = nl["produkt_key"].map(disp).fillna("(ohne Produkt)")
    return nl


def enrich_newsletter(nl: pd.DataFrame) -> pd.DataFrame:
    if nl.empty:
        return nl
    nl = add_calendar(nl, "send_date")
    nl = _product_display(nl)
    hh = pd.to_numeric(nl["uhrzeit"].str[:2], errors="coerce")
    nl["stunde"] = hh
    nl["zeitfenster"] = pd.cut(hh, bins=[-1, 5, 7, 9, 11, 13, 16, 19, 24],
                               labels=["00–05", "06–07", "08–09", "10–11", "12–13", "14–16", "17–19", "20–23"]).astype(str)
    nl.loc[hh.isna(), "zeitfenster"] = "unbekannt"
    nl["nach_apple_mpp"] = pd.to_datetime(nl["send_date"]) >= pd.Timestamp(APPLE_MPP_DATE)
    # Kennzahlen je Sendung aus ABSOLUTEN Zahlen (Sheet-Prozente nur zur Kontrolle)
    with np.errstate(divide="ignore", invalid="ignore"):
        nl["open_rate"] = nl.oeffnungen / nl.empfaenger
        nl["ctr"] = nl.klicks / nl.empfaenger
        nl["ctor"] = nl.klicks / nl.oeffnungen
        nl["cr_click"] = nl.kaeufe / nl.klicks
        nl["cr_recipient"] = nl.kaeufe / nl.empfaenger
        nl["rev_per_recipient"] = nl.umsatz / nl.empfaenger
        nl["epc"] = nl.umsatz / nl.klicks
        nl["aov"] = nl.umsatz / nl.kaeufe
    for c in ["open_rate", "ctr", "ctor", "cr_click", "cr_recipient", "rev_per_recipient", "epc", "aov"]:
        nl[c] = nl[c].replace([np.inf, -np.inf], np.nan)
    nl["betreff_norm"] = nl["betreff"].fillna("").str.replace(r"%Subscriber:[^%]+%", "{Vorname}", regex=True).str.strip()
    return nl


@dataclass
class Model:
    daily: pd.DataFrame
    weekly: pd.DataFrame
    monthly: pd.DataFrame
    abo_product: pd.DataFrame
    nl: pd.DataFrame
    asof: dt.date                      # letzter Tag mit Tagesumsatz
    first: dt.date
    nl_asof: dt.date | None
    meta: dict = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return self.daily.empty and self.nl.empty


def load_model() -> Model:
    daily = add_calendar(db.read_table("daily"), "date")
    weekly = db.read_table("weekly")
    monthly = db.read_table("monthly")
    abo = db.read_table("abo_product")
    nl = enrich_newsletter(db.read_table("newsletter"))
    if not monthly.empty:
        monthly["date"] = pd.to_datetime(dict(year=monthly.year, month=monthly.month, day=1)).dt.date
    asof = max(daily["date"]) if not daily.empty else dt.date.today()
    first = min(daily["date"]) if not daily.empty else dt.date(2020, 1, 1)
    nl_asof = max(nl["send_date"]) if not nl.empty else None
    return Model(daily, weekly, monthly, abo, nl, asof, first, nl_asof)


@dataclass
class Filters:
    produkte: list[str] = field(default_factory=list)
    wochentage: list[str] = field(default_factory=list)
    stunde_von: int = 0
    stunde_bis: int = 23
    betreff_suche: str = ""
    newsletter_ids: list[str] = field(default_factory=list)
    nur_mit_umsatzdaten: bool = False

    def active(self) -> bool:
        return bool(self.produkte or self.wochentage or self.stunde_von > 0 or self.stunde_bis < 23 or self.betreff_suche
                    or self.newsletter_ids)

    def describe(self) -> str:
        parts = []
        if self.produkte:
            parts.append("Produkt: " + ", ".join(self.produkte))
        if self.wochentage:
            parts.append("Wochentag: " + ", ".join(self.wochentage))
        if self.stunde_von > 0 or self.stunde_bis < 23:
            parts.append(f"Versandzeit: {self.stunde_von:02d}:00–{self.stunde_bis:02d}:59")
        if self.betreff_suche:
            parts.append(f"Betreff enthält „{self.betreff_suche}“")
        if self.newsletter_ids:
            parts.append(f"{len(self.newsletter_ids)} ausgewählte Newsletter")
        return "; ".join(parts) if parts else "keine"


def filter_nl(nl: pd.DataFrame, f: Filters, start: dt.date | None = None, end: dt.date | None = None) -> pd.DataFrame:
    if nl.empty:
        return nl
    m = pd.Series(True, index=nl.index)
    if start:
        m &= nl.send_date >= start
    if end:
        m &= nl.send_date <= end
    if f.produkte:
        m &= nl.produkt.isin(f.produkte)
    if f.wochentage:
        m &= nl.wochentag.isin(f.wochentage)
    if f.stunde_von > 0 or f.stunde_bis < 23:
        m &= nl.stunde.between(f.stunde_von, f.stunde_bis)
    if f.betreff_suche:
        m &= nl.betreff.fillna("").str.contains(f.betreff_suche, case=False, regex=False)
    if f.newsletter_ids:
        m &= nl.send_id.isin(f.newsletter_ids)
    return nl[m]


def filter_daily(daily: pd.DataFrame, start: dt.date, end: dt.date, f: Filters | None = None) -> pd.DataFrame:
    if daily.empty:
        return daily
    m = (daily.date >= start) & (daily.date <= end)
    if f and f.wochentage:
        m &= daily.wochentag.isin(f.wochentage)
    return daily[m]

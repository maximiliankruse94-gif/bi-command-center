"""Datenqualität: Abgleich der Aggregationsebenen und Vollständigkeitsprüfungen.

Maßgebliche Quellen (Single Source of Truth):
  * Umsatz je Tag/Woche/Monat/Jahr ........ Tagesstatistiken (Summe der Zahlungskonten GTK, littlefreilich,
                                             GunnarKessler, WU/EA = 'Umsatz Gesamt', netto ohne USt, vor Rückgaben)
  * CopeCart-Umsatz ......................... nur in Wochen-/Monatsstatistiken vorhanden (nicht in Tagesdaten)
  * Umsatz brutto inkl. USt, Abo-Bestände ... Monatsstatistiken
  * Newsletter-Kennzahlen ................... Newsletter-Statistiken
Wochen- und Monatswerte werden NIE zu Tageswerten addiert, sondern nur zur Validierung genutzt.
"""
from __future__ import annotations

import pandas as pd

from .. import db
from ..parsers.base import Issue

TOL_ABS = 5.0      # €
TOL_REL = 0.005    # 0,5 %


def reconcile_monthly(daily: pd.DataFrame | None = None, monthly: pd.DataFrame | None = None) -> pd.DataFrame:
    daily = db.read_table("daily") if daily is None else daily
    monthly = db.read_table("monthly") if monthly is None else monthly
    if daily.empty or monthly.empty:
        return pd.DataFrame()
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    agg = d.groupby([d.date.dt.year.rename("year"), d.date.dt.month.rename("month")]).agg(
        tage=("date", "nunique"), umsatz_tage=("umsatz_gesamt", "sum"), rueckgaben_tage=("rueckgaben", "sum"),
        werbung_tage=("werbung", "sum"), split_tage=("split_summe", "sum"), gtk_tage=("umsatz_gtk", "sum")).reset_index()
    m = monthly[["year", "month", "umsatz_netto", "umsatz_copecart", "umsatz_gtk", "werbekosten", "rueckgaben"]].copy()
    m["copecart"] = m["umsatz_copecart"].fillna(0)
    m["umsatz_monat_ohne_cc"] = m["umsatz_netto"] - m["copecart"]
    r = agg.merge(m, on=["year", "month"], how="outer")
    r["tage_im_monat"] = pd.to_datetime(dict(year=r.year, month=r.month, day=1)).dt.days_in_month
    r["diff"] = r["umsatz_tage"] - r["umsatz_monat_ohne_cc"]
    r["diff_pct"] = r["diff"] / r["umsatz_monat_ohne_cc"]
    r["status"] = "ok"
    r.loc[r.umsatz_tage.isna(), "status"] = "nur Monatsdaten"
    r.loc[r.umsatz_netto.isna(), "status"] = "nur Tagesdaten"
    bad = r.umsatz_tage.notna() & r.umsatz_netto.notna() & (r["diff"].abs() > TOL_ABS) & (r["diff_pct"].abs() > TOL_REL)
    r.loc[bad, "status"] = "Abweichung"
    return r.sort_values(["year", "month"])


def reconcile_weekly(daily: pd.DataFrame | None = None, weekly: pd.DataFrame | None = None) -> pd.DataFrame:
    daily = db.read_table("daily") if daily is None else daily
    weekly = db.read_table("weekly") if weekly is None else weekly
    if daily.empty or weekly.empty:
        return pd.DataFrame()
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    iso = d.date.dt.isocalendar()
    d["iso_year"], d["iso_week"] = iso.year.astype(int), iso.week.astype(int)
    agg = d.groupby(["iso_year", "iso_week"]).agg(tage=("date", "nunique"), umsatz_tage=("umsatz_gesamt", "sum")).reset_index()
    w = weekly[["iso_year", "iso_week", "date_from", "umsatz_gesamt", "umsatz_copecart"]].copy()
    w["umsatz_woche_ohne_cc"] = w["umsatz_gesamt"] - w["umsatz_copecart"].fillna(0)
    r = agg.merge(w, on=["iso_year", "iso_week"], how="outer")
    r["diff"] = r["umsatz_tage"] - r["umsatz_woche_ohne_cc"]
    r["diff_pct"] = r["diff"] / r["umsatz_woche_ohne_cc"]
    r["status"] = "ok"
    r.loc[r.umsatz_tage.isna(), "status"] = "nur Wochendaten"
    r.loc[r.umsatz_gesamt.isna(), "status"] = "nur Tagesdaten"
    r.loc[(r.tage < 7) & r.umsatz_gesamt.notna(), "status"] = "Woche unvollständig"
    bad = (r.status == "ok") & (r["diff"].abs() > TOL_ABS) & (r["diff_pct"].abs() > TOL_REL)
    r.loc[bad, "status"] = "Abweichung"
    return r.sort_values(["iso_year", "iso_week"])


def missing_days(daily: pd.DataFrame | None = None) -> list:
    daily = db.read_table("daily") if daily is None else daily
    if daily.empty:
        return []
    s = pd.to_datetime(daily["date"])
    full = pd.date_range(s.min(), s.max(), freq="D")
    return sorted(set(full.date) - set(s.dt.date))


def cross_checks() -> list[Issue]:
    issues: list[Issue] = []
    rm = reconcile_monthly()
    for r in rm[rm.status == "Abweichung"].itertuples():
        issues.append(Issue("warning", "abgleich_tag_monat",
                            f"{int(r.month):02d}/{int(r.year)}: Summe Tagesumsätze {r.umsatz_tage:,.2f} € vs. Monatsstatistik "
                            f"(ohne CopeCart) {r.umsatz_monat_ohne_cc:,.2f} € – Differenz {r.diff:,.2f} € ({r.diff_pct:.1%})",
                            "monthly"))
    rw = reconcile_weekly()
    for r in rw[rw.status == "Abweichung"].itertuples():
        issues.append(Issue("info", "abgleich_tag_woche",
                            f"KW {int(r.iso_week)}/{int(r.iso_year)}: Tage {r.umsatz_tage:,.2f} € vs. Woche (ohne CopeCart) "
                            f"{r.umsatz_woche_ohne_cc:,.2f} € – Differenz {r.diff:,.2f} €", "weekly"))
    md = missing_days()
    if md:
        issues.append(Issue("warning", "fehlende_tage",
                            f"{len(md)} Kalendertage ohne Tagesdaten zwischen erstem und letztem Erfassungstag "
                            f"(z.B. {', '.join(d.strftime('%d.%m.%Y') for d in md[:8])}{' …' if len(md) > 8 else ''})", "daily"))
    return issues

"""Zeiträume und sachlich korrekte Vergleichszeiträume.

Regeln
  * Laufende (unvollständige) Zeiträume enden am letzten Tag MIT Daten (Datenstand),
    nicht am Kalenderende. Vergleichszeiträume werden auf dieselbe Länge gekürzt
    ("Monat bis heute" vs. "Vorjahresmonat bis zum gleichen Tag").
  * Vorjahresvergleich: gleicher Kalenderzeitraum ein Jahr früher (29.02. -> 28.02.).
  * Vorjahres-Woche: gleiche ISO-KW im Vorjahr (Wochentage bleiben vergleichbar).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..parsers.common import MONTH_NAMES_DE, WEEKDAYS_DE


@dataclass(frozen=True)
class Period:
    start: dt.date
    end: dt.date
    label: str
    partial: bool = False   # endet vor dem natürlichen Periodenende (laufender Zeitraum)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, d: dt.date) -> bool:
        return self.start <= d <= self.end

    def fmt(self) -> str:
        if self.start == self.end:
            return self.start.strftime("%d.%m.%Y")
        return f"{self.start:%d.%m.%Y} – {self.end:%d.%m.%Y}"


PRESETS = ["Heute", "Gestern", "Diese Woche", "Letzte Woche", "Dieser Monat", "Letzter Monat", "Dieses Quartal",
           "Letztes Quartal", "Dieses Jahr", "Letztes Jahr", "Letzte 7 Tage", "Letzte 30 Tage", "Letzte 90 Tage",
           "Letzte 180 Tage", "Letzte 365 Tage", "Gesamter Zeitraum"]

COMPARISONS = ["Automatisch (sinnvollster Vergleich)", "Vorperiode (gleiche Länge)", "Vorjahreszeitraum",
               "Frei wählbar", "Kein Vergleich"]


def shift_year(d: dt.date, years: int = -1) -> dt.date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29.02.
        return d.replace(year=d.year + years, day=28)


def month_end(y: int, m: int) -> dt.date:
    import calendar
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def quarter_start(d: dt.date) -> dt.date:
    return dt.date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def preset(name: str, asof: dt.date, first: dt.date | None = None) -> Period:
    """asof = Datenstand (letzter Tag mit Daten) bzw. heute."""
    t = asof
    if name == "Heute":
        return Period(t, t, f"Heute ({t:%d.%m.%Y})")
    if name == "Gestern":
        y = t - dt.timedelta(days=1)
        return Period(y, y, f"Gestern ({y:%d.%m.%Y})")
    if name == "Diese Woche":
        s = t - dt.timedelta(days=t.weekday())
        return Period(s, t, f"KW {t.isocalendar()[1]}/{t.isocalendar()[0]} (bis {WEEKDAYS_DE[t.weekday()][:2]} {t:%d.%m.})", partial=t.weekday() < 6)
    if name == "Letzte Woche":
        s = t - dt.timedelta(days=t.weekday() + 7)
        e = s + dt.timedelta(days=6)
        return Period(s, e, f"KW {s.isocalendar()[1]}/{s.isocalendar()[0]}")
    if name == "Dieser Monat":
        s = t.replace(day=1)
        return Period(s, t, f"{MONTH_NAMES_DE[t.month]} {t.year} (bis {t:%d.%m.})", partial=t != month_end(t.year, t.month))
    if name == "Letzter Monat":
        e = t.replace(day=1) - dt.timedelta(days=1)
        return Period(e.replace(day=1), e, f"{MONTH_NAMES_DE[e.month]} {e.year}")
    if name == "Dieses Quartal":
        s = quarter_start(t)
        q = (t.month - 1) // 3 + 1
        qe = month_end(t.year, 3 * q)
        return Period(s, t, f"Q{q} {t.year} (bis {t:%d.%m.})", partial=t != qe)
    if name == "Letztes Quartal":
        e = quarter_start(t) - dt.timedelta(days=1)
        s = quarter_start(e)
        return Period(s, e, f"Q{(e.month - 1) // 3 + 1} {e.year}")
    if name == "Dieses Jahr":
        return Period(dt.date(t.year, 1, 1), t, f"{t.year} (bis {t:%d.%m.})", partial=t != dt.date(t.year, 12, 31))
    if name == "Letztes Jahr":
        return Period(dt.date(t.year - 1, 1, 1), dt.date(t.year - 1, 12, 31), str(t.year - 1))
    if name.startswith("Letzte ") and name.endswith(" Tage"):
        n = int(name.split()[1])
        return Period(t - dt.timedelta(days=n - 1), t, f"Letzte {n} Tage")
    if name == "Gesamter Zeitraum":
        return Period(first or dt.date(2020, 1, 1), t, "Gesamter Zeitraum")
    raise ValueError(name)


def year_period(y: int, asof: dt.date) -> Period:
    e = min(dt.date(y, 12, 31), asof)
    return Period(dt.date(y, 1, 1), e, str(y), partial=e != dt.date(y, 12, 31))


def quarter_period(y: int, q: int, asof: dt.date) -> Period:
    s = dt.date(y, 3 * q - 2, 1)
    e0 = month_end(y, 3 * q)
    e = min(e0, asof)
    return Period(s, e, f"Q{q} {y}", partial=e != e0)


def month_period(y: int, m: int, asof: dt.date) -> Period:
    e0 = month_end(y, m)
    e = min(e0, asof)
    return Period(dt.date(y, m, 1), e, f"{MONTH_NAMES_DE[m]} {y}", partial=e != e0)


def week_period(y: int, w: int, asof: dt.date) -> Period:
    s = dt.date.fromisocalendar(y, w, 1)
    e0 = s + dt.timedelta(days=6)
    e = min(e0, asof)
    return Period(s, e, f"KW {w}/{y}", partial=e != e0)


def _period_kind(p: Period) -> str:
    if p.start == p.end:
        return "day"
    if p.start.weekday() == 0 and p.days <= 7 and p.start.isocalendar()[:2] == p.end.isocalendar()[:2]:
        return "week"
    if p.start.day == 1 and p.start.month == p.end.month and p.start.year == p.end.year:
        return "month"
    if p.start == quarter_start(p.start) and quarter_start(p.end) == p.start:
        return "quarter"
    if p.start.month == 1 and p.start.day == 1 and p.end.year == p.start.year:
        return "year"
    return "range"


def comparison(p: Period, mode: str, custom: Period | None = None) -> Period | None:
    if mode == "Kein Vergleich":
        return None
    if mode == "Frei wählbar":
        return custom
    kind = _period_kind(p)
    if mode.startswith("Automatisch"):
        # Tag/Woche/Monat/Quartal/Jahr -> Vorjahr (saisonbereinigt); freie Bereiche -> Vorperiode
        mode = "Vorjahreszeitraum" if kind in ("month", "quarter", "year", "day", "week") else "Vorperiode (gleiche Länge)"
    if mode == "Vorjahreszeitraum":
        if kind == "week":
            y, w, _ = p.start.isocalendar()
            try:
                s = dt.date.fromisocalendar(y - 1, w, 1)
            except ValueError:
                s = dt.date.fromisocalendar(y - 1, 52, 1)
            return Period(s, s + dt.timedelta(days=p.days - 1), f"KW {w}/{y - 1}" + (" (gleiche Tage)" if p.partial else ""), p.partial)
        if kind == "day":
            # gleicher Wochentag vor 52 Wochen ist für Tagesumsätze vergleichbarer als Kalenderdatum
            s = p.start - dt.timedelta(days=364)
            return Period(s, s, f"gleicher Wochentag Vorjahr ({WEEKDAYS_DE[s.weekday()][:2]} {s:%d.%m.%Y})")
        s, e = shift_year(p.start), shift_year(p.end)
        lab = p.label.replace(str(p.start.year), str(p.start.year - 1)) if str(p.start.year) in p.label else f"Vorjahr ({s:%d.%m.%Y} – {e:%d.%m.%Y})"
        return Period(s, e, lab + (" (gleiche Tage)" if p.partial and "(bis" not in lab else ""), p.partial)
    # Vorperiode gleicher Länge (bei Monat/Quartal: Vormonat/-quartal bis gleichen Tag)
    if kind == "month":
        pm_end = p.start - dt.timedelta(days=1)
        s = pm_end.replace(day=1)
        e = min(s + dt.timedelta(days=p.days - 1), pm_end)
        return Period(s, e, f"{MONTH_NAMES_DE[s.month]} {s.year}" + (f" (bis {e:%d.%m.})" if p.partial else ""), p.partial)
    e = p.start - dt.timedelta(days=1)
    s = e - dt.timedelta(days=p.days - 1)
    return Period(s, e, f"Vorperiode ({s:%d.%m.%Y} – {e:%d.%m.%Y})", p.partial)

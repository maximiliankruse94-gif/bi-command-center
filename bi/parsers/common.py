"""Gemeinsame, robuste Zell-Parser für Google-Sheets-/XLSX-Werte.

Alle Funktionen sind tolerant gegenüber den in den Originaldaten
tatsächlich vorkommenden Formaten:
  * deutsche und englische Zahlenformate ("4.334,00 €", "2,294.03€", 4334.0)
  * Fehlerwerte (#DIV/0!, #VALUE!, #REF!, #N/A)  -> None (fehlend, NICHT 0)
  * "-" als Platzhalter                          -> None bzw. 0 (je nach Feld, s. Parser)
  * Datumswerte als datetime, Excel-Serial, "01.10.2026", "01.10.26"
"""
from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata
from typing import Any

ERROR_TOKENS = {"#DIV/0!", "#VALUE!", "#REF!", "#N/A", "#NAME?", "#NUM!", "#NULL!", "#ERROR!"}
DASH_TOKENS = {"-", "–", "—", "--"}

MONTHS_DE = {
    "januar": 1, "jan": 1, "jänner": 1,
    "februar": 2, "feb": 2, "febraur": 2, "febuar": 2,
    "märz": 3, "maerz": 3, "marz": 3, "mär": 3, "mrz": 3,
    "april": 4, "apr": 4,
    "mai": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}
MONTH_NAMES_DE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                  "August", "September", "Oktober", "November", "Dezember"]
WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_WEEKDAY_SET = {w.lower() for w in WEEKDAYS_DE}


def is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def is_error(v: Any) -> bool:
    return isinstance(v, str) and v.strip().upper() in ERROR_TOKENS


def norm_text(v: Any) -> str:
    """Normalisierter Text für Header-Vergleiche (klein, ohne Akzente/Sonderzeichen)."""
    if is_blank(v):
        return ""
    s = str(v).strip().lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9%]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_num_clean = re.compile(r"[€$%\s ]|eur", re.IGNORECASE)


def to_number(v: Any, dash_as_zero: bool = False) -> float | None:
    """Konvertiert Zellwert in float. Fehlende/fehlerhafte Werte -> None."""
    if is_blank(v) or is_error(v):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return None
    s = str(v).strip()
    if s in DASH_TOKENS:
        return 0.0 if dash_as_zero else None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    s = _num_clean.sub("", s)
    if s.startswith("-"):
        neg, s = (not neg), s[1:]
    if not s:
        return None
    # Dezimaltrennzeichen bestimmen
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):          # 4.334,00  (de)
            s = s.replace(".", "").replace(",", ".")
        else:                                     # 2,294.03  (en)
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3 and parts[0] != "0":
            s = s.replace(",", "")                # 1,357 als Tausender (en)
        else:
            s = s.replace(",", ".")               # 26,47
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and parts[0] not in ("", "0")):
            s = s.replace(".", "")                # 4.334 als Tausender (de)
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


def to_percent(v: Any) -> float | None:
    """Prozentwert als Anteil (0.2647). Akzeptiert 0.2647, '26,47%', '26,47 %'."""
    if isinstance(v, str) and "%" in v:
        f = to_number(v)
        return None if f is None else f / 100.0
    f = to_number(v)
    if f is None:
        return None
    return f / 100.0 if f > 1.5 else f


_DATE_RE = re.compile(r"^\s*(\d{1,2})\.+(\d{1,2})\.+(\d{2,4})")
_ISO_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")
EXCEL_EPOCH = dt.date(1899, 12, 30)


def to_date(v: Any, expect_year: int | None = None, expect_month: int | None = None) -> tuple[dt.date | None, str | None]:
    """Parst ein Datum. Gibt (datum, warnung) zurück.

    expect_year/expect_month: aus Tab-Kontext bekannter Zeitraum. Weicht ein
    zweistelliges Jahr offensichtlich ab (z.B. '28.10.97' im Tab 'Oktober 26'),
    wird es korrigiert und eine Warnung zurückgegeben.
    """
    warn = None
    d: dt.date | None = None
    if is_blank(v) or is_error(v):
        return None, None
    if isinstance(v, dt.datetime):
        d = v.date()
    elif isinstance(v, dt.date):
        d = v
    elif isinstance(v, (int, float)) and 20000 < float(v) < 80000:
        d = EXCEL_EPOCH + dt.timedelta(days=int(v))
    elif isinstance(v, str):
        m = _DATE_RE.match(v)
        if m:
            day, mon, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if yr < 100:
                yr += 2000
            try:
                d = dt.date(yr, mon, day)
            except ValueError:
                # z.B. '31.23.23' -> Monat ungültig
                if expect_month and 1 <= day <= 31:
                    try:
                        d = dt.date(expect_year or yr, expect_month, day)
                        warn = f"Ungültiges Datum '{v}' -> korrigiert auf {d.isoformat()}"
                    except ValueError:
                        return None, f"Ungültiges Datum '{v}'"
                else:
                    return None, f"Ungültiges Datum '{v}'"
        else:
            m = _ISO_RE.match(v)
            if m:
                try:
                    d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    return None, f"Ungültiges Datum '{v}'"
    if d is None:
        return None, None
    if expect_year and expect_month and (d.year != expect_year or d.month != expect_month):
        try:
            fixed = dt.date(expect_year, expect_month, d.day)
        except ValueError:
            return None, f"Datum '{v}' passt nicht zum Tabellenblatt und ist nicht korrigierbar"
        what = "Jahr" if d.month == expect_month else ("Monat" if d.year == expect_year else "Monat/Jahr")
        return fixed, f"{what} im Datum '{v}' passt nicht zum Tabellenblatt -> korrigiert auf {fixed:%d.%m.%Y}"
    return d, warn


def to_time(v: Any) -> str | None:
    """Uhrzeit als 'HH:MM' oder None."""
    if is_blank(v) or is_error(v):
        return None
    if isinstance(v, dt.datetime):
        return v.strftime("%H:%M")
    if isinstance(v, dt.time):
        return v.strftime("%H:%M")
    if isinstance(v, (int, float)) and 0 <= float(v) < 1:
        mins = int(round(float(v) * 24 * 60))
        return f"{mins // 60:02d}:{mins % 60:02d}"
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})", str(v))
    if m and int(m.group(1)) < 24:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def parse_month_label(v: Any, fallback_year: int | None = None) -> tuple[int | None, int | None]:
    """'Januar 2026', 'Febraur 2026', datetime(2024,4,1), 'Oktober 26' -> (jahr, monat)."""
    if isinstance(v, dt.datetime) or isinstance(v, dt.date):
        return v.year, v.month
    if is_blank(v) or not isinstance(v, str):
        return None, None
    s = norm_text(v)
    m = re.match(r"^([a-z]+)\s*(\d{2,4})?$", s)
    if not m:
        return None, None
    mon = MONTHS_DE.get(m.group(1).replace("ae", "ä") if m.group(1) == "maerz" else m.group(1))
    if mon is None:
        mon = MONTHS_DE.get(m.group(1))
    if mon is None:
        # Fuzzy: gleiche ersten 3 Buchstaben
        for k, val in MONTHS_DE.items():
            if len(k) >= 3 and m.group(1)[:3] == k[:3]:
                mon = val
                break
    if mon is None:
        return None, None
    yr = m.group(2)
    if yr:
        y = int(yr)
        y = y + 2000 if y < 100 else y
    else:
        y = fallback_year
    return y, mon


def find_header_row(rows: list[list[Any]], required: list[str], max_scan: int = 8) -> int | None:
    """Sucht die Zeile, die alle normalisierten Pflicht-Header enthält."""
    req = [norm_text(r) for r in required]
    for i, row in enumerate(rows[:max_scan]):
        cells = {norm_text(c) for c in row}
        if all(r in cells for r in req):
            return i
    return None


def header_map(header: list[Any]) -> dict[str, list[int]]:
    """Header-Text (normalisiert) -> Liste von Spaltenindizes (Duplikate erlaubt)."""
    out: dict[str, list[int]] = {}
    for j, h in enumerate(header):
        k = norm_text(h)
        if k:
            out.setdefault(k, []).append(j)
    return out


def cell(row: list[Any], idx: int | None) -> Any:
    if idx is None or idx >= len(row):
        return None
    return row[idx]

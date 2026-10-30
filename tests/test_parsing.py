import datetime as dt

import pytest

from bi.parsers.common import parse_month_label, to_date, to_number, to_percent, to_time


@pytest.mark.parametrize("raw,exp", [
    (4334, 4334.0), ("4.334,00 €", 4334.0), ("2,294.03€", 2294.03), ("6,40€", 6.40), ("26,47%", 26.47), ("1.357", 1357.0),
    ("-", None), ("#VALUE!", None), ("#DIV/0!", None), (None, None), ("", None), ("(12,50)", -12.5), ("-583,28 €", -583.28),
    (float("nan"), None),
])
def test_to_number(raw, exp):
    assert to_number(raw) == (pytest.approx(exp) if exp is not None else None)


def test_dash_as_zero():
    assert to_number("-", dash_as_zero=True) == 0.0


def test_percent():
    assert to_percent("26,47 %") == pytest.approx(0.2647)
    assert to_percent(0.2647) == pytest.approx(0.2647)
    assert to_percent("#DIV/0!") is None


@pytest.mark.parametrize("raw,ey,em,exp,warn", [
    ("01.10.26", 2026, 10, dt.date(2026, 10, 1), False),
    ("01.10.2026", None, None, dt.date(2026, 10, 1), False),
    (dt.datetime(2024, 4, 7), None, None, dt.date(2024, 4, 7), False),
    ("28.10.97", 2026, 10, dt.date(2026, 10, 28), True),     # Tippfehler Jahr
    ("30.06.24", 2024, 5, dt.date(2024, 5, 30), True),       # falscher Monat im Tab Mai
    ("13..02.26", 2026, 2, dt.date(2026, 2, 13), False),     # doppelter Punkt
    ("31.06.2023", 2023, 5, dt.date(2023, 5, 31), True),     # ungültiges Datum
    (45000, None, None, dt.date(2023, 3, 15), False),        # Excel-Serial
])
def test_to_date(raw, ey, em, exp, warn):
    d, w = to_date(raw, ey, em)
    assert d == exp
    assert bool(w) == warn


def test_time():
    assert to_time("05:29") == "05:29"
    assert to_time(dt.time(6, 10)) == "06:10"
    assert to_time(0.25) == "06:00"
    assert to_time(None) is None


def test_month_labels():
    assert parse_month_label("Febraur 2026") == (2026, 2)
    assert parse_month_label("März 26") == (2026, 3)
    assert parse_month_label(dt.datetime(2024, 4, 1)) == (2024, 4)
    assert parse_month_label("Oktober", 2022) == (2022, 10)
    assert parse_month_label("Gesamt") == (None, None)

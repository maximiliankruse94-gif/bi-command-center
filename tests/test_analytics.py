import datetime as dt
import random

import pandas as pd
import pytest

from bi.analytics import decomposition as D
from bi.analytics import periods as P
from bi.analytics.metrics import nl_summary


def test_weighted_rates_not_mean_of_rates():
    df = pd.DataFrame({"send_date": [dt.date(2026, 1, 1)] * 2, "send_id": ["a", "b"], "empfaenger": [100, 50000],
                       "oeffnungen": [90, 10000], "klicks": [9, 500], "kaeufe": [1, 10], "umsatz": [100.0, 2000.0],
                       "folgeeinnahmen": [None, None]})
    s = nl_summary(df)
    assert s["open_rate"] == pytest.approx(10090 / 50100)          # gewichtet ≈ 20,1 %
    assert s["open_rate"] != pytest.approx((0.9 + 0.2) / 2)          # NICHT Mittel der Raten (55 %)
    assert s["ctor"] == pytest.approx(509 / 10090)
    assert s["cr_click"] == pytest.approx(11 / 509)
    assert s["aov"] == pytest.approx(2100 / 11)


def test_missing_values_excluded_from_numerator_and_denominator():
    df = pd.DataFrame({"send_date": [dt.date(2026, 1, 1)] * 2, "send_id": ["a", "b"], "empfaenger": [1000, 1000],
                       "oeffnungen": [200, 300], "klicks": [20, None], "kaeufe": [2, None], "umsatz": [100.0, None],
                       "folgeeinnahmen": [None, None]})
    s = nl_summary(df)
    assert s["ctor"] == pytest.approx(20 / 200)    # Sendung ohne Klicks fließt nicht in den Nenner ein
    assert s["sendungen_ohne_umsatzdaten"] == 1


def test_shapley_sums_exactly():
    random.seed(1)
    for _ in range(50):
        b = {k: random.uniform(0.5, 2) for k in "abcdef"}
        c = {k: random.uniform(0.5, 2) for k in "abcdef"}
        phi = D.shapley_multiplicative(b, c)
        import math
        assert sum(phi.values()) == pytest.approx(math.prod(c.values()) - math.prod(b.values()))


def test_shapley_symmetric_single_factor():
    phi = D.shapley_multiplicative({"a": 1, "b": 2}, {"a": 1, "b": 3})
    assert phi["a"] == pytest.approx(0) and phi["b"] == pytest.approx(1)


@pytest.mark.parametrize("asof,name,exp_start,exp_end", [
    (dt.date(2026, 10, 29), "Dieser Monat", dt.date(2026, 10, 1), dt.date(2026, 10, 29)),
    (dt.date(2026, 10, 29), "Letzter Monat", dt.date(2026, 9, 1), dt.date(2026, 9, 30)),
    (dt.date(2026, 10, 29), "Diese Woche", dt.date(2026, 10, 26), dt.date(2026, 10, 29)),
    (dt.date(2026, 1, 2), "Letzte Woche", dt.date(2025, 12, 22), dt.date(2025, 12, 28)),
    (dt.date(2026, 1, 2), "Diese Woche", dt.date(2025, 12, 29), dt.date(2026, 1, 2)),     # ISO-KW 1/2026 beginnt 2025
    (dt.date(2026, 10, 29), "Dieses Quartal", dt.date(2026, 10, 1), dt.date(2026, 10, 29)),
    (dt.date(2026, 2, 10), "Letztes Quartal", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
])
def test_presets(asof, name, exp_start, exp_end):
    p = P.preset(name, asof)
    assert (p.start, p.end) == (exp_start, exp_end)


def test_partial_month_compared_with_same_days():
    p = P.preset("Dieser Monat", dt.date(2026, 10, 29))
    c = P.comparison(p, "Vorjahreszeitraum")
    assert (c.start, c.end) == (dt.date(2025, 10, 1), dt.date(2025, 10, 29))
    c2 = P.comparison(p, "Vorperiode (gleiche Länge)")
    assert (c2.start, c2.end) == (dt.date(2026, 9, 1), dt.date(2026, 9, 29))


def test_month_31_vs_short_previous_month():
    p = P.month_period(2026, 3, dt.date(2026, 3, 31))
    c = P.comparison(p, "Vorperiode (gleiche Länge)")
    assert c.end == dt.date(2026, 2, 28)  # nicht in den März hineinlaufen


def test_leap_day_yoy():
    p = P.Period(dt.date(2024, 2, 29), dt.date(2024, 2, 29), "x")
    assert P.shift_year(p.start) == dt.date(2023, 2, 28)


def test_iso_week_yoy():
    p = P.week_period(2026, 1, dt.date(2026, 12, 31))
    c = P.comparison(p, "Vorjahreszeitraum")
    assert c.start == dt.date(2024, 12, 30)  # ISO-KW 1/2025 beginnt am 30.12.2024
    assert P.week_period(2026, 53, dt.date(2027, 1, 10)).start == dt.date(2026, 12, 28)

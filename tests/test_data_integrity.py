"""Tests gegen die ORIGINALDATEN (XLSX-Export der Google Sheets).

Stichproben werden unabhängig vom Parser direkt per openpyxl aus den Original-Zellen gelesen.
"""
import datetime as dt
import random

import openpyxl
import pandas as pd
import pytest

from conftest import TMP, needs_data

pytestmark = needs_data


def _orig(wbname):
    return openpyxl.load_workbook(TMP / "data" / f"{wbname}.xlsx", data_only=True, read_only=True)


def _col(ws, name, header_row=1):
    for c in next(ws.iter_rows(min_row=header_row, max_row=header_row)):
        if isinstance(c.value, str) and c.value.strip().lower() == name.lower():
            return c.column
    raise KeyError(name)


def _find_sheet(wb, tab):
    return next(ws for ws in wb.worksheets if ws.title.strip() == tab)


def test_sync_status(synced):
    assert synced["imported_tabs"] == 110   # 72 Tages-, 7 Wochen-, 6 Monats-, 25 Newsletter-Tabs
    assert not synced["unknown_tabs"]
    assert synced["errors"] == []


def test_daily_spot_checks_vs_original_cells(model):
    random.seed(42)
    wb = _orig("daily")
    rows = model.daily.sample(25, random_state=7)
    for r in rows.itertuples():
        ws = _find_sheet(wb, r.source_tab)
        cell = ws.cell(row=r.source_row, column=_col(ws, "Umsatz Gesamt")).value
        assert float(cell) == pytest.approx(r.umsatz_gesamt, abs=0.005), (r.source_tab, r.source_row)
        gtk = ws.cell(row=r.source_row, column=_col(ws, "Umsatz GTK")).value
        assert (gtk is None and pd.isna(r.umsatz_gtk)) or float(gtk) == pytest.approx(r.umsatz_gtk, abs=0.005)


def test_daily_month_totals_match_sheet_total_row(model):
    """Summenzeile unter den Tagesdaten (Sheet-eigene Formel) = Summe der importierten Tage."""
    wb = _orig("daily")
    checked = 0
    for tab in ["Oktober 26", "Januar 26", "Juni 25", "Oktober 24", "März 23", "Juli 22", "Mai 21"]:
        ws = _find_sheet(wb, tab)
        col = _col(ws, "Umsatz Gesamt")
        vals = [ws.cell(row=i, column=col).value for i in range(2, 40)]
        first_col = [ws.cell(row=i, column=1).value for i in range(2, 40)]
        # Summenzeile = erste Zeile ohne Datum mit Wert > größtem Tageswert
        tot = next(v for d, v in zip(first_col, vals) if d is None and isinstance(v, (int, float)) and v > 50000)
        db_sum = model.daily[model.daily.source_tab == tab].umsatz_gesamt.sum()
        assert db_sum == pytest.approx(tot, abs=0.05), tab
        checked += 1
    assert checked == 7


def test_newsletter_spot_checks_vs_original_cells(model):
    wb = _orig("newsletter")
    sample = model.nl.sample(30, random_state=3)
    for r in sample.itertuples():
        ws = _find_sheet(wb, r.source_tab)
        row = [c.value for c in next(ws.iter_rows(min_row=r.source_row, max_row=r.source_row))]
        assert float(row[6]) == pytest.approx(r.empfaenger)           # Spalte G = Empfänger (in allen Layouts)
        assert float(row[7]) == pytest.approx(r.oeffnungen)           # Spalte H = Öffnungen
        if not pd.isna(r.umsatz) and isinstance(row[14], (int, float)):
            assert float(row[14]) == pytest.approx(r.umsatz)          # Spalte O = Gesamtumsatz (Netto)


def test_newsletter_count_per_tab_matches_original(model):
    wb = _orig("newsletter")
    for tab in ["Mails 2026 Q3", "Mails 2025 Q1", "Mails 2023 Q2", "Mails 2021 Q4"]:
        ws = _find_sheet(wb, tab)
        n = sum(1 for row in ws.iter_rows(min_row=2, values_only=True)
                if len(row) > 6 and isinstance(row[6], (int, float)) and row[6] > 0
                and any(isinstance(v, (dt.date, dt.datetime)) or (isinstance(v, str) and v[:2].isdigit()) for v in row[:2]))
        # Summenzeilen ohne Datum (z.B. Zeile 78 in 'Mails 2023 Q2') zählen nicht als Sendung
        assert (model.nl.source_tab == tab).sum() == n, tab


def test_multiple_sends_same_day_kept_separately(model):
    per_day = model.nl.groupby("send_date").size()
    assert (per_day >= 2).sum() >= 10
    assert model.nl.send_id.is_unique
    day = per_day[per_day >= 2].index[0]
    assert model.nl[model.nl.send_date == day].campaign_key.nunique() <= 2  # gleicher Key möglich -> ID dennoch eindeutig


def test_no_double_counting_between_levels(model):
    """Wochen-/Monatswerte werden NICHT zum Tagesumsatz addiert: Gesamtumsatz = Summe Tage."""
    from bi.analytics.metrics import revenue_summary
    p = __import__("bi.analytics.periods", fromlist=["Period"]).Period(model.first, model.asof, "")
    assert revenue_summary(model.daily, p)["umsatz_gesamt"] == pytest.approx(model.daily.umsatz_gesamt.sum())


def test_daily_vs_monthly_reconciliation(synced):
    from bi.analytics.quality import reconcile_monthly
    rm = reconcile_monthly()
    both = rm[rm.status.isin(["ok", "Abweichung"])]
    assert (both.status == "ok").mean() > 0.75           # Großteil der Monate stimmt auf ±0,5 %
    assert ((rm.year == 2022) & (rm.month == 10)).any()
    assert rm[(rm.year == 2022) & (rm.month == 10)].status.iloc[0] == "nur Monatsdaten"   # fehlender Tab erkannt


def test_iso_week_year_boundary(model):
    from bi import db
    w = db.read_table("weekly")
    r = w[(w.iso_year == 2026) & (w.iso_week == 1)]
    assert len(r) == 1 and r.date_from.iloc[0] == dt.date(2025, 12, 29)   # stand im Tab 2025 als 'KW 53' UND im Tab 2026 als KW 1
    assert not ((w.iso_year == 2025) & (w.iso_week == 53)).any()            # 2025 hat keine ISO-KW 53
    assert w.duplicated(["iso_year", "iso_week"]).sum() == 0


def test_typo_dates_corrected(model):
    d = model.daily.set_index("date")
    assert dt.date(2024, 7, 26) in d.index          # '29.07.24' doppelt -> nach Zeilenfolge 26.07.
    assert dt.date(2024, 6, 15) in d.index          # Tab 'Juni 24' mit Datumsangaben '..05.24'
    assert d.loc[dt.date(2024, 6, 1), "source_tab"] == "Juni 24"
    assert dt.date(2026, 2, 13) in d.index          # '13..02.26'


def test_monthly_wrong_year_labels(synced):
    from bi import db
    m = db.read_table("monthly")
    r = m[(m.year == 2023) & (m.month == 10)]
    assert len(r) == 1 and r.source_tab.iloc[0] == "Übersicht 2023"     # Zeile hieß 'Oktober 2022'
    assert len(m[(m.year == 2022) & (m.month == 7)]) == 1


def test_idempotent_resync():
    from bi.sync import run_sync
    res = run_sync("test", "local", force=True)
    assert res["new_records"] == 0 and res["updated_records"] == 0 and res["removed_records"] == 0


def test_attribution_share_definition(model):
    from bi.analytics.attribution import attribution_table
    t = attribution_table(model.daily, model.nl, "jahr")
    r = t[t.jahr == 2025].iloc[0]
    assert r.nl_anteil == pytest.approx(model.nl[model.nl.jahr == 2025].umsatz.sum() / model.daily[model.daily.jahr == 2025].umsatz_gesamt.sum())


def test_decomposition_on_real_data(model):
    from bi.analytics.model import Filters, filter_nl
    a = filter_nl(model.nl, Filters(), dt.date(2025, 9, 1), dt.date(2025, 9, 30))
    b = filter_nl(model.nl, Filters(), dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    r = D_dec(a, b)
    assert sum(f["beitrag_eur"] for f in r["faktoren"]) + r["rest"] == pytest.approx(r["delta"], abs=0.01)


def D_dec(a, b):
    from bi.analytics.decomposition import decompose_newsletter
    return decompose_newsletter(a, b)


def test_prompt_complete(model):
    from bi.analytics import periods as P
    from bi.analytics.model import Filters
    from bi.analytics.prompt import build_prompt
    p = P.preset("Letzter Monat", model.asof)
    c = P.comparison(p, "Vorjahreszeitraum")
    for mode in ("quick", "deep"):
        txt, det = build_prompt(model, p, c, Filters(), mode)
        assert "Erfinde keine Zahlen" in txt and "Nachgewiesenen Fakten" in txt
        assert "nan" not in txt.lower().replace("finanz", "")
        assert "Gesamtumsatz" in txt and len(det["sendungen"]) > 0


def test_exports(model):
    from bi import export
    from bi.analytics import periods as P
    from bi.analytics.model import Filters
    p = P.preset("Letzter Monat", model.asof)
    c = P.comparison(p, "Vorjahreszeitraum")
    pdf = export.management_pdf(model, p, c, Filters())
    assert pdf[:4] == b"%PDF" and len(pdf) > 20000
    xl = export.excel_bundle(model, p, c, Filters())
    assert xl[:2] == b"PK"

"""Test-Setup: isolierte SQLite-DB + Kopien der Original-XLSX in einem Temp-Verzeichnis.

Die Original-Exporte müssen unter data/*.xlsx liegen (werden NICHT verändert).
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="bicc_test_"))
(TMP / "config").mkdir()
(TMP / "data").mkdir()
for n in ("daily", "weekly", "monthly", "newsletter"):
    src = ROOT / "data" / f"{n}.xlsx"
    if src.exists():
        shutil.copy(src, TMP / "data" / f"{n}.xlsx")
(TMP / "config" / "sources.yaml").write_text(f"""
workbooks:
  - {{key: daily, name: Tagesstatistiken, file_id: x1, local_file: {TMP}/data/daily.xlsx, expected_kinds: [daily]}}
  - {{key: weekly, name: Wochenstatistiken, file_id: x2, local_file: {TMP}/data/weekly.xlsx, expected_kinds: [weekly]}}
  - {{key: monthly, name: Monatsstatistiken, file_id: x3, local_file: {TMP}/data/monthly.xlsx, expected_kinds: [monthly]}}
  - {{key: newsletter, name: Newsletter, file_id: x4, local_file: {TMP}/data/newsletter.xlsx, expected_kinds: [newsletter]}}
""")
shutil.copy(ROOT / "config" / "product_aliases.yaml", TMP / "config")
(TMP / "config" / "tab_mappings.yaml").write_text("mappings: []\n")
os.environ.update(BICC_CONFIG_DIR=str(TMP / "config"), BICC_SQLITE_PATH=str(TMP / "test.sqlite"), BICC_SOURCE_MODE="local",
                  BICC_ENV="dev")
os.environ.pop("DATABASE_URL", None)
if os.getenv("BICC_TEST_DATABASE_URL"):          # optional: Tests gegen PostgreSQL (leere Datenbank!)
    os.environ["DATABASE_URL"] = os.environ["BICC_TEST_DATABASE_URL"]
sys.path.insert(0, str(ROOT))

HAVE_DATA = (TMP / "data" / "daily.xlsx").exists()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="Original-XLSX nicht vorhanden")


@pytest.fixture(scope="session")
def tmpdir_root():
    return TMP


@pytest.fixture(scope="session")
def synced():
    from bi.sync import run_sync
    res = run_sync("test", "local", force=True)
    assert res["status"] in ("ok", "warnung"), res
    return res


@pytest.fixture(scope="session")
def model(synced):
    from bi.analytics.model import load_model
    return load_model()

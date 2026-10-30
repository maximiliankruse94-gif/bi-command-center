"""Datensicherung: exportiert alle Tabellen (inkl. entfernter Datensätze und Importhistorie) als ZIP mit CSV.

    python scripts/backup_db.py backup_2026-10-30.zip

Ergänzend: Cloud SQL erstellt täglich automatische Backups (14 Tage). Die Google Sheets bleiben die Primärquelle –
die Datenbank kann jederzeit per Synchronisierung neu aufgebaut werden.
"""
import datetime as dt
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bi import db  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else f"bicc_backup_{dt.date.today()}.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z, db.engine().connect() as c:
    for name, table in db.md.tables.items():
        df = pd.read_sql(select(table), c)
        z.writestr(f"{name}.csv", df.to_csv(index=False))
        print(f"{name}: {len(df)} Zeilen")
print("Backup geschrieben:", out)

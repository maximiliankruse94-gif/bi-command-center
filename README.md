# Business Intelligence Command Center

Controlling- und Revenue-Intelligence-System für Hide and Seek. Liest die vier Google Sheets (Tages-, Wochen-, Monats- und
Newsletter-Statistiken) **nur lesend**, normalisiert sie in eine Datenbank und stellt 12 Analysebereiche bereit.
Im Betrieb wird **keine KI/LLM-API** benötigt.

## Schnellstart lokal
```bash
pip install -r requirements.txt
# Exporte der vier Sheets als data/daily.xlsx, data/weekly.xlsx, data/monthly.xlsx, data/newsletter.xlsx ablegen
python -m bi.sync --mode local              # Import in data/bicc.sqlite
BICC_ENV=dev streamlit run app.py           # http://localhost:8501
```
Mit Google-Zugriff statt Dateien: `GOOGLE_APPLICATION_CREDENTIALS=sa.json BICC_SOURCE_MODE=google python -m bi.sync`.

## Projektstruktur
```
app.py                     Einstieg, Navigation, Login, globale Sidebar
bi/
  config.py                Konfiguration (Umgebungsvariablen, YAML)
  sources/loader.py        Google Drive/Sheets API (read-only), öffentlicher Link, lokale XLSX
  parsers/                 common (Zahlen/Datum), daily, weekly, monthly, newsletter
  detect.py                regelbasierte Tab-Erkennung (Score aus Überschriften, Datentypen, Inhalt; Name nur Zusatzindiz)
  db.py                    Datenmodell (SQLAlchemy; SQLite lokal, PostgreSQL produktiv), differenzielles Upsert, Soft Delete
  sync.py                  Synchronisierung (CLI + Button), Transaktion, Sperre gegen Doppelläufe
  export.py                PDF-Management-Report, Excel-Paket
  analytics/
    model.py               Kalender- & Produktdimension, Filter
    periods.py             Zeiträume und sachgerechte Vergleiche
    metrics.py             Kennzahlen (gewichtete Raten)
    decomposition.py       Shapley-Zerlegung, Produktmix, Prüfhinweise
    attribution.py         Newsletter-Umsatzanteil
    alerts.py              Frühwarnsystem
    subjects.py            Betreffzeilen-Merkmale, Empirical-Bayes-Rankings
    quality.py             Abgleich Tag/Woche/Monat, fehlende Tage
    prompt.py              KI-Analyse-Prompt (Quick/Deep)
ui/                        Theme, Komponenten, Login, Seiten (ui/views/*)
config/                    sources.yaml, tab_mappings.yaml, product_aliases.yaml
deploy/                    setup_gcp.sh (Erst-Einrichtung), redeploy.sh
tests/                     70 Tests (Parser, Erkennung, Analytik, Abgleich mit Originaldaten, Änderungserkennung)
docs/                      DATENINVENTAR, KENNZAHLEN, DEPLOYMENT, BEDIENUNGSANLEITUNG
```

## Datenmodell
| Tabelle | Schlüssel | Inhalt |
|---|---|---|
| fact_daily | date | Tagesumsätze (maßgeblich) inkl. Erst-/Wiederkehrend-Aufteilung, Kosten |
| fact_weekly | iso_year, iso_week | Wochenstatistik (Validierung, CopeCart, Abos) |
| fact_monthly | year, month | Monatsstatistik (Brutto, Abo-Bestände, Validierung) |
| fact_abo_product | year, month, product | aktive/neue/gekündigte Abos je Produkt |
| fact_newsletter_send | send_id | eine Zeile je Sendung; ID = Hash(Datum, Uhrzeit, Campaignkey, Produkt, laufende Nr.) |
| meta_source_tab | workbook, tab | erkannte Tabs, Typ, Sicherheit, Struktursignatur |
| meta_sync_run / meta_dq_issue | id | Importhistorie und Datenqualitätsmeldungen je Lauf |
| meta_tab_mapping | workbook, tab | manuelle Zuordnungen |

Kalenderdimension (Wochentag, ISO-KW, Monat, Quartal, Jahr) und Produktdimension werden beim Laden abgeleitet (`analytics/model.py`).
Erweiterungen (Ads, Shop, Retouren, CLV …) = neuer Parser in `bi/parsers/` + Tabelle in `db.py` + Eintrag in `detect.PARSERS`.

## Tests
```bash
pip install -r requirements-dev.txt
pytest -q tests                                              # SQLite
BICC_TEST_DATABASE_URL=postgresql+psycopg2://u:p@host/leere_db pytest -q tests   # PostgreSQL
```
Deployment: siehe `docs/DEPLOYMENT.md`.

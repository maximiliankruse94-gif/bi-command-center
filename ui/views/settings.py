from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from bi.config import ROOT, database_url, product_aliases, source_mode, workbooks

from .. import components as C


def render():
    ctx = st.session_state["ctx"]
    C.header("Einstellungen", "Systemstatus, Konfiguration und Dokumentation")
    st.markdown("##### Systemstatus")
    url = database_url()
    safe_db = url.split("@")[-1] if "@" in url else url
    st.markdown(f"""
| Einstellung | Wert |
|---|---|
| Datenquelle | `{source_mode()}` ({'Google Drive/Sheets API, nur Lesezugriff' if source_mode() == 'google' else 'lokale Dateien' if source_mode() == 'local' else source_mode()}) |
| Datenbank | `{safe_db}` |
| Anmeldung | `{os.getenv('BICC_AUTH_MODE', 'none')}` |
| Zeitzone | Europe/Berlin (Sommer-/Winterzeit automatisch) |
| Tägliche Synchronisierung | 06:00 Uhr (Cloud Scheduler) + automatische Nachsynchronisierung beim ersten Aufruf, falls ausgefallen |
| Ihre Rolle | {ctx['role']} |
""")
    st.markdown("##### Datenquellen (config/sources.yaml)")
    for wb in workbooks():
        st.markdown(f"- **{wb['name']}** – `{wb['file_id']}`")
    st.markdown("##### Produkt-Aliase (config/product_aliases.yaml)")
    al = product_aliases()
    st.write(al if al else "Keine manuellen Aliase. Schreibvarianten (Groß-/Kleinschreibung, Leerzeichen, Bindestriche) werden automatisch zusammengeführt.")
    st.markdown("##### Dokumentation")
    for name in ("BEDIENUNGSANLEITUNG.md", "KENNZAHLEN.md", "DATENINVENTAR.md"):
        p = ROOT / "docs" / name
        if p.exists():
            with st.expander(name.replace(".md", "").replace("_", " ").title()):
                st.markdown(p.read_text(encoding="utf-8"))

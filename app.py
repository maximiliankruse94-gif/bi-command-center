"""BUSINESS INTELLIGENCE COMMAND CENTER – Einstiegspunkt (streamlit run app.py)."""
from __future__ import annotations

import logging

import streamlit as st

st.set_page_config(page_title="BI Command Center", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# Streamlit Community Cloud / secrets.toml: Einstellungen auf oberster Ebene als Umgebungsvariablen übernehmen
import os  # noqa: E402
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and _k.startswith(("BICC_", "GOOGLE_", "DATABASE_URL")):
            os.environ.setdefault(_k, _v)
except Exception:  # noqa: BLE001  (keine secrets.toml vorhanden)
    pass

from ui import auth, state  # noqa: E402
from ui.theme import CSS  # noqa: E402
from ui.views import (ai_analyst, alerts, attribution, data_mgmt, executive, funnel, history, newsletter,  # noqa: E402
                      products, revenue, settings, subjects)

logging.basicConfig(level=logging.INFO)
st.markdown(CSS, unsafe_allow_html=True)

user, role = auth.require_login()
st.session_state["user"], st.session_state["role"] = user, role

state.auto_sync_if_due()
m = state.model()

pages = {
    "Überblick": [
        st.Page(executive.render, title="Executive Overview", icon="🏠", url_path="overview", default=True),
        st.Page(revenue.render, title="Revenue Intelligence", icon="💶", url_path="revenue"),
        st.Page(attribution.render, title="Revenue Attribution", icon="🧩", url_path="attribution"),
        st.Page(alerts.render, title="Business Alerts", icon="🚨", url_path="alerts"),
        st.Page(history.render, title="Historical Analysis", icon="🗂", url_path="history"),
    ],
    "Newsletter": [
        st.Page(newsletter.render, title="Newsletter Intelligence", icon="✉️", url_path="newsletter"),
        st.Page(subjects.render, title="Betreffzeilen Intelligence", icon="🔤", url_path="subjects"),
        st.Page(products.render, title="Produkt Intelligence", icon="📦", url_path="products"),
        st.Page(funnel.render, title="Funnel Analytics", icon="🔻", url_path="funnel"),
    ],
    "Werkzeuge": [
        st.Page(ai_analyst.render, title="AI Business Analyst", icon="🤖", url_path="ai-analyst"),
        st.Page(data_mgmt.render, title="Datenmanagement", icon="🗄", url_path="data"),
        st.Page(settings.render, title="Einstellungen", icon="⚙️", url_path="settings"),
    ],
}
pg = st.navigation(pages, position="sidebar")

st.sidebar.markdown("---")
state.sync_box(m, role)
if m.empty and pg.url_path not in ("data", "settings"):
    st.warning("Noch keine Daten importiert. Bitte „JETZT AKTUALISIEREN“ klicken bzw. unter Datenmanagement die "
               "Datenquellen prüfen.")
    st.stop()
sel = state.sidebar(m, show_nl_filters=pg.url_path not in ("data", "settings"))
st.sidebar.markdown("---")
st.sidebar.caption(f"Angemeldet: {user} ({role})")
if st.sidebar.button("Abmelden", use_container_width=True):
    auth.logout()

st.session_state["ctx"] = {"m": m, "sel": sel, "role": role, "user": user}
pg.run()

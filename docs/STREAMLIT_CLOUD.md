# Kostenlos online mit Streamlit Community Cloud

Siehe Anleitung im Chat bzw. diese Kurzfassung:
1. GitHub-Konto anlegen, **privates** Repository erstellen, alle Projektdateien (inkl. Ordner `.streamlit`) hochladen.
2. Google-Zugriff: Variante A (Dienstkonto + JSON-Schlüssel, Sheets bleiben privat) oder Variante B (öffentlicher Link, BICC_SOURCE_MODE="public_link").
3. https://share.streamlit.io → mit GitHub anmelden → Create app → Repository, Branch `main`, Datei `app.py`, Python 3.12.
4. Advanced settings → Secrets: Vorlage `.streamlit/secrets_streamlit_cloud.example.toml` einfügen und ausfüllen → Deploy.
5. App-Einstellungen → Sharing: nur eingeladene Personen (zweite Schutzebene zusätzlich zum Passwort).
Datenbank liegt temporär in der App und wird bei jedem Start aus den Google Sheets neu aufgebaut (30–60 Sek.).

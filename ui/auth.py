"""Zugangsschutz.

Modi (Umgebungsvariable BICC_AUTH_MODE):
  * "oidc"     – Google-Login über Streamlit OIDC (empfohlen). Zugelassen sind nur E-Mail-Adressen aus
                 BICC_ALLOWED_USERS (Format: "mail1@firma.de:admin,mail2@firma.de:viewer").
  * "password" – Benutzer aus BICC_USERS (JSON): {"mail": {"role": "admin", "hash": "<bcrypt>"}} oder
                 {"mail": {"role": "admin", "password": "<mind. 10 Zeichen>"}} (nur in verschlüsselten Secrets).
  * "proxy"    – Authentifizierung übernimmt ein vorgeschalteter Dienst (z.B. Google IAP); E-Mail aus Header.
  * "none"     – NUR lokale Entwicklung (BICC_ENV=dev). In Produktion verweigert die App den Start.
Rollen: admin (alles inkl. Tab-Zuordnung/Einstellungen) · viewer (lesen, aktualisieren, exportieren).
"""
from __future__ import annotations

import json
import os
import time

import streamlit as st


def _allowed() -> dict[str, str]:
    raw = os.getenv("BICC_ALLOWED_USERS", "")
    out = {}
    for part in raw.split(","):
        if ":" in part:
            mail, role = part.strip().rsplit(":", 1)
            out[mail.lower()] = role.strip()
        elif part.strip():
            out[part.strip().lower()] = "viewer"
    return out


def require_login() -> tuple[str, str]:
    """Gibt (email, rolle) zurück oder stoppt die Seite."""
    mode = os.getenv("BICC_AUTH_MODE", "none").lower()
    if mode == "none":
        if os.getenv("BICC_ENV", "dev") != "dev":
            st.error("Sicherheitsfehler: Ohne Anmeldung darf die App nur lokal (BICC_ENV=dev) laufen.")
            st.stop()
        return "lokal@dev", "admin"
    if mode == "proxy":
        hdr = st.context.headers.get("X-Goog-Authenticated-User-Email", "")
        mail = hdr.split(":")[-1].lower()
        role = _allowed().get(mail)
        if not role:
            st.error("Kein Zugriff für dieses Konto.")
            st.stop()
        return mail, role
    if mode == "oidc":
        if not st.user.is_logged_in:
            _login_screen()
            if st.button("Mit Google anmelden", type="primary"):
                st.login()
            st.stop()
        mail = (st.user.email or "").lower()
        role = _allowed().get(mail)
        if not role:
            st.error(f"Das Konto {mail} ist nicht freigeschaltet.")
            if st.button("Abmelden"):
                st.logout()
            st.stop()
        return mail, role
    if mode == "password":
        if st.session_state.get("auth_user"):
            return st.session_state["auth_user"], st.session_state["auth_role"]
        import bcrypt
        users = json.loads(os.getenv("BICC_USERS", "{}"))
        _login_screen()
        with st.form("login"):
            mail = st.text_input("E-Mail").strip().lower()
            pw = st.text_input("Passwort", type="password")
            ok = st.form_submit_button("Anmelden", type="primary")
        if ok:
            fails = st.session_state.get("auth_fails", 0)
            if fails >= 5:
                time.sleep(min(30, 2 ** (fails - 4)))
            u = users.get(mail)
            ok_pw = False
            if u and u.get("hash"):
                ok_pw = bcrypt.checkpw(pw.encode(), u["hash"].encode())
            elif u and u.get("password"):  # Klartext nur in verschlüsselten Secrets (z.B. Streamlit Cloud) zulässig
                import hmac
                ok_pw = len(u["password"]) >= 10 and hmac.compare_digest(pw.encode(), u["password"].encode())
            if ok_pw:
                st.session_state.update(auth_user=mail, auth_role=u.get("role", "viewer"), auth_fails=0)
                st.rerun()
            st.session_state["auth_fails"] = fails + 1
            st.error("Anmeldung fehlgeschlagen.")
        st.stop()
    st.error(f"Unbekannter BICC_AUTH_MODE '{mode}'.")
    st.stop()


def logout() -> None:
    mode = os.getenv("BICC_AUTH_MODE", "none").lower()
    if mode == "oidc":
        st.logout()
    else:
        for k in ("auth_user", "auth_role"):
            st.session_state.pop(k, None)
        st.rerun()


def _login_screen() -> None:
    st.markdown('<div style="max-width:420px;margin:8vh auto 0 auto;">'
                '<div class="bicc-title">Business Intelligence Command Center</div>'
                '<div class="bicc-sub">Geschützter Bereich – bitte anmelden.</div></div>', unsafe_allow_html=True)

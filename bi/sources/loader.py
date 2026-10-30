"""Datenquellen-Zugriff.

Alle Quellen liefern dasselbe Format:  {tab_name: [[zelle, ...], ...]}
Dadurch läuft exakt derselbe Parser-Code für
  * Google Drive Export (Service Account / Cloud-Run-Identität)  <- Produktion
  * Google Sheets API (Fallback, z.B. Datei > 10 MB)
  * öffentlicher Export-Link (nur falls Sheets per Link freigegeben sind)
  * lokale XLSX-Dateien (Entwicklung, Tests, Notfall-Import)

Es werden ausschließlich LESENDE Zugriffe verwendet (Scope drive.readonly /
spreadsheets.readonly). Die Original-Sheets können technisch nicht verändert werden.
"""
from __future__ import annotations

import io
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly",
          "https://www.googleapis.com/auth/spreadsheets.readonly"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass
class FetchResult:
    tabs: dict[str, list[list[Any]]]
    modified_time: str | None
    method: str
    title: str | None = None


def xlsx_bytes_to_tabs(data: bytes | str) -> dict[str, list[list[Any]]]:
    src = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
    sheets = pd.read_excel(src, sheet_name=None, header=None, engine="openpyxl")
    out: dict[str, list[list[Any]]] = {}
    for name, df in sheets.items():
        df = df.astype(object).where(pd.notna(df), None)
        out[name] = df.values.tolist()
    return out


def _credentials():
    """Service-Account-Zugang aus Umgebung. Reihenfolge:
    1. GOOGLE_SERVICE_ACCOUNT_JSON (JSON-Inhalt als Secret)
    2. GOOGLE_APPLICATION_CREDENTIALS (Pfad zu JSON-Datei)
    3. Application Default Credentials (Cloud Run: Identität des Dienstes – kein Schlüssel nötig)
    """
    import google.auth
    from google.oauth2 import service_account
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        return service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def google_available() -> bool:
    if os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("K_SERVICE"):
        return True
    return False


def fetch_drive_export(file_id: str, known_modified: str | None = None) -> FetchResult | None:
    """Exportiert das Google Sheet als XLSX (read-only). Gibt None zurück, wenn unverändert."""
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    creds = _credentials()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    meta = drive.files().get(fileId=file_id, fields="name,modifiedTime", supportsAllDrives=True).execute()
    mod = meta.get("modifiedTime")
    if known_modified and mod == known_modified:
        return FetchResult({}, mod, "unchanged", meta.get("name"))
    try:
        data = drive.files().export(fileId=file_id, mimeType=XLSX_MIME).execute()
        return FetchResult(xlsx_bytes_to_tabs(data), mod, "drive_export", meta.get("name"))
    except HttpError as e:  # z.B. exportSizeLimitExceeded (> 10 MB)
        log.warning("Drive-Export fehlgeschlagen (%s) -> Sheets-API-Fallback", e)
        return FetchResult(fetch_sheets_api(file_id, creds), mod, "sheets_api", meta.get("name"))


def fetch_sheets_api(file_id: str, creds=None) -> dict[str, list[list[Any]]]:
    from googleapiclient.discovery import build
    creds = creds or _credentials()
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    meta = svc.spreadsheets().get(spreadsheetId=file_id, fields="sheets.properties.title").execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    out: dict[str, list[list[Any]]] = {}
    for chunk in range(0, len(titles), 20):
        part = titles[chunk:chunk + 20]
        resp = svc.spreadsheets().values().batchGet(
            spreadsheetId=file_id, ranges=[f"'{t}'" for t in part],
            valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER").execute()
        for t, vr in zip(part, resp.get("valueRanges", [])):
            out[t] = vr.get("values", [])
    return out


def fetch_public_link(file_id: str) -> FetchResult:
    """Nur nutzbar, wenn das Sheet 'Jeder mit dem Link' freigegeben ist (nicht empfohlen)."""
    import urllib.request
    url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (feste Google-URL)
        data = resp.read()
    return FetchResult(xlsx_bytes_to_tabs(data), None, "public_link")


def fetch_local(path: str) -> FetchResult:
    mod = str(os.path.getmtime(path))
    return FetchResult(xlsx_bytes_to_tabs(path), mod, "local_file")

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.getenv("BICC_CONFIG_DIR", ROOT / "config"))
TZ = ZoneInfo("Europe/Berlin")


def database_url() -> str:
    """DATABASE_URL (PostgreSQL in Produktion) oder lokale SQLite-Datei."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url.replace("postgres://", "postgresql+psycopg2://", 1) if url.startswith("postgres://") else url
    path = Path(os.getenv("BICC_SQLITE_PATH", ROOT / "data" / "bicc.sqlite"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def source_mode() -> str:
    """google | public_link | local   (Standard: google, falls Zugangsdaten vorhanden, sonst local)."""
    m = os.getenv("BICC_SOURCE_MODE")
    if m:
        return m
    from .sources.loader import google_available
    return "google" if google_available() else "local"


def demo_mode() -> bool:
    return os.getenv("BICC_DEMO_MODE", "0") == "1"


@lru_cache
def load_yaml(name: str) -> dict:
    p = CONFIG_DIR / name
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def workbooks() -> list[dict]:
    return load_yaml("sources.yaml").get("workbooks", [])


def product_aliases() -> dict[str, str]:
    return {str(k): str(v) for k, v in (load_yaml("product_aliases.yaml").get("aliases") or {}).items()}


def yaml_tab_mappings() -> list[dict]:
    return load_yaml("tab_mappings.yaml").get("mappings") or []

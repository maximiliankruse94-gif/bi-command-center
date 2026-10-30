"""Deutsche Zahlenformate."""
from __future__ import annotations

import math


def _none(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def de(v: float, d: int = 0) -> str:
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def eur(v, d: int = 0, compact: bool = False) -> str:
    if _none(v):
        return "k. A."
    if compact and abs(v) >= 1_000_000:
        return f"{de(v / 1_000_000, 2)} Mio. €"
    if compact and abs(v) >= 10_000:
        return f"{de(v / 1000, 1)} Tsd. €"
    return f"{de(v, d)} €"


def num(v, d: int = 0) -> str:
    return "k. A." if _none(v) else de(v, d)


def pct(v, d: int = 1) -> str:
    return "k. A." if _none(v) else f"{de(v * 100, d)} %"


def signed_pct(v, d: int = 1) -> str:
    return "k. A." if _none(v) else ("+" if v > 0 else "") + f"{de(v * 100, d)} %"


def signed_eur(v, d: int = 0) -> str:
    return "k. A." if _none(v) else ("+" if v > 0 else "") + f"{de(v, d)} €"


def pp(v, d: int = 2) -> str:
    return "k. A." if _none(v) else ("+" if v > 0 else "") + f"{de(v * 100, d)} Pp"

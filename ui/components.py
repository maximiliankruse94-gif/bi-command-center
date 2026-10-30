"""Wiederverwendbare UI-Bausteine."""
from __future__ import annotations

import html
import io
import math
from typing import Callable, Sequence

import pandas as pd
import streamlit as st

from . import fmt
from .theme import BAD_TEXT, GOOD_TEXT, INFO, MUTED

PLOT_CFG = {"displaylogo": False, "scrollZoom": False, "locale": "de",
            "modeBarButtonsToRemove": ["lasso2d", "select2d"], "toImageButtonOptions": {"format": "png", "scale": 2}}


def header(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="bicc-title">{html.escape(title)}</div>'
                + (f'<div class="bicc-sub">{sub}</div>' if sub else ""), unsafe_allow_html=True)


def sparkline(values: Sequence[float], width: int = 220, height: int = 34, color: str = INFO) -> str:
    v = [x for x in values if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if len(v) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    lo, hi = min(v), max(v)
    rng = hi - lo or 1
    pts, n, i = [], len(values), 0
    for j, x in enumerate(values):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            continue
        px = 2 + (width - 4) * j / max(n - 1, 1)
        py = height - 3 - (height - 6) * (x - lo) / rng
        pts.append(f"{px:.1f},{py:.1f}")
        i += 1
    last = pts[-1].split(",")
    return (f'<svg width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" height="{height}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round" points="{" ".join(pts)}"/>'
            f'<circle cx="{last[0]}" cy="{last[1]}" r="2.6" fill="{color}"/></svg>')


def kpi(label: str, value, ref=None, fmt_fn: Callable = fmt.eur, spark: Sequence[float] | None = None,
        ref_label: str = "Vergleich", invert: bool = False, delta_kind: str = "pct", help_text: str = "") -> str:
    """KPI-Karte: Wert, Vergleichswert, absolute + prozentuale Veränderung, Mini-Trend."""
    d_abs = None if value is None or ref is None else value - ref
    d_pct = None if d_abs is None or not ref else d_abs / abs(ref)
    cls = "flat"
    if d_abs is not None and abs(d_pct or 0) >= 0.005:
        good = (d_abs > 0) != invert
        cls = "up" if good else "down"
    arrow = {"up": "▲", "down": "▼", "flat": "■"}[cls] if d_abs is not None else ""
    if delta_kind == "pp":
        dtxt = f"{arrow} {fmt.pp(d_abs)}" if d_abs is not None else ""
    else:
        abs_txt = fmt.signed_eur(d_abs) if fmt_fn in (fmt.eur,) else (("+" if (d_abs or 0) > 0 else "") + fmt_fn(d_abs) if d_abs is not None else "")
        dtxt = f"{arrow} {fmt.signed_pct(d_pct)} · {abs_txt}" if d_abs is not None else ""
    reftxt = f"{ref_label}: {fmt_fn(ref)}" if ref is not None else "kein Vergleichswert"
    sp = sparkline(spark) if spark is not None else ""
    title = f' title="{html.escape(help_text)}"' if help_text else ""
    return (f'<div class="kpi"{title}><div class="lbl">{html.escape(label)}</div><div class="val">{fmt_fn(value)}</div>'
            f'<div class="d {cls}">{dtxt}</div><div class="cmp">{html.escape(reftxt)}</div>{sp}</div>')


def kpi_row(cards: list[str], cols: int | None = None) -> None:
    cols = cols or len(cards)
    for i in range(0, len(cards), cols):
        cs = st.columns(cols)
        for c, card in zip(cs, cards[i:i + cols]):
            c.markdown(card, unsafe_allow_html=True)


def badge(text: str, kind: str) -> str:
    return f'<span class="badge b-{kind}">{html.escape(text)}</span>'


def note(text: str) -> None:
    st.markdown(f'<div class="note">{text}</div>', unsafe_allow_html=True)


def chart(fig, key: str | None = None, height: int | None = None, on_select: bool = False):
    if height:
        fig.update_layout(height=height)
    if on_select:
        return st.plotly_chart(fig, use_container_width=True, config=PLOT_CFG, key=key, on_select="rerun",
                               selection_mode=("points",))
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CFG, key=key)
    return None


def download_buttons(df: pd.DataFrame, name: str, key: str) -> None:
    c1, c2, _ = st.columns([1, 1, 6])
    c1.download_button("⬇ CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"), f"{name}.csv",
                       "text/csv", key=f"{key}_csv", use_container_width=True)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        df.to_excel(xw, index=False, sheet_name=name[:31])
    c2.download_button("⬇ Excel", buf.getvalue(), f"{name}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key}_xlsx",
                       use_container_width=True)


def empty_state(msg: str) -> None:
    st.info(msg)


def delta_color(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return MUTED
    return GOOD_TEXT if v > 0 else BAD_TEXT

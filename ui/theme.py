"""Design-System: dunkles Enterprise-Theme, Plotly-Template, CSS."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

BG = "#0f1115"
SURFACE = "#171a21"
SURFACE_2 = "#1e222b"
BORDER = "#2a2f3a"
TEXT = "#eef0f3"
TEXT_2 = "#b4bac6"
MUTED = "#7d8594"
GOOD = "#0ca30c"
GOOD_TEXT = "#3ccf5a"
BAD = "#d03b3b"
BAD_TEXT = "#ff6b6b"
WARN = "#fab219"
INFO = "#3987e5"
# Kategoriale Reihenfolge (validiert für dunkle Flächen, CVD-sicher in fester Reihenfolge)
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
SEQ_BLUE = ["#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5", "#5598e7", "#6da7ec", "#86b6ef", "#9ec5f4", "#cde2fb"]
DIVERGING = [[0, "#d03b3b"], [0.5, "#383835"], [1, "#3987e5"]]

pio.templates["bicc"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, Roboto, sans-serif", color=TEXT_2, size=12),
        title=dict(font=dict(color=TEXT, size=14), x=0, xanchor="left"),
        colorway=SERIES,
        xaxis=dict(gridcolor="#232833", zerolinecolor="#2f3542", linecolor="#2f3542", tickcolor="#2f3542"),
        yaxis=dict(gridcolor="#232833", zerolinecolor="#2f3542", linecolor="#2f3542", tickcolor="#2f3542"),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.08, x=0, font=dict(color=TEXT_2)),
        hoverlabel=dict(bgcolor=SURFACE_2, bordercolor=BORDER, font=dict(color=TEXT)),
        margin=dict(l=10, r=10, t=40, b=10),
        separators=",.",
        hovermode="x unified",
        bargap=0.25,
    )
)
pio.templates.default = "plotly_dark+bicc"

CSS = f"""
<style>
:root {{ --bg:{BG}; --surface:{SURFACE}; --surface2:{SURFACE_2}; --border:{BORDER}; --text:{TEXT}; --text2:{TEXT_2};
        --muted:{MUTED}; --good:{GOOD_TEXT}; --bad:{BAD_TEXT}; --warn:{WARN}; --info:{INFO}; }}
.stApp {{ background: var(--bg); }}
section[data-testid="stSidebar"] {{ background: #12151b; border-right: 1px solid var(--border); }}
.block-container {{ padding-top: 1.6rem; max-width: 1600px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}
.bicc-title {{ font-size: 1.55rem; font-weight: 650; color: var(--text); margin: 0 0 .1rem 0; }}
.bicc-sub {{ color: var(--muted); font-size: .86rem; margin-bottom: 1rem; }}
.kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px 10px 16px;
        height: 100%; min-height: 128px; }}
.kpi .lbl {{ color: var(--text2); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }}
.kpi .val {{ color: var(--text); font-size: 1.55rem; font-weight: 650; margin: 2px 0 2px 0; font-variant-numeric: tabular-nums; }}
.kpi .cmp {{ color: var(--muted); font-size: .78rem; font-variant-numeric: tabular-nums; }}
.kpi .d {{ font-size: .82rem; font-weight: 600; font-variant-numeric: tabular-nums; }}
.kpi .up {{ color: var(--good); }} .kpi .down {{ color: var(--bad); }} .kpi .flat {{ color: var(--text2); }}
.kpi svg {{ display:block; margin-top: 6px; }}
.badge {{ display:inline-block; padding: 2px 8px; border-radius: 999px; font-size: .72rem; font-weight: 600; }}
.b-hoch {{ background: rgba(208,59,59,.18); color: #ff8a8a; }}
.b-mittel {{ background: rgba(250,178,25,.16); color: #ffcf5c; }}
.b-info {{ background: rgba(57,135,229,.16); color: #8dbbf5; }}
.b-ok {{ background: rgba(12,163,12,.18); color: #6fe08a; }}
.panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 18px; margin-bottom: 12px; }}
.note {{ color: var(--muted); font-size: .8rem; }}
.alertcard {{ background: var(--surface); border:1px solid var(--border); border-left: 4px solid var(--info);
              border-radius: 10px; padding: 12px 16px; margin-bottom: 10px; }}
.alertcard.hoch {{ border-left-color: #d03b3b; }} .alertcard.mittel {{ border-left-color: #fab219; }}
div[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
</style>
"""

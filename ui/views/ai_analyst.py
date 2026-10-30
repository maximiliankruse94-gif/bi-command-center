from __future__ import annotations

import datetime as dt
import io
import json
import zipfile

import streamlit as st
import streamlit.components.v1 as components

from bi import export
from bi.analytics import prompt as PR

from .. import components as C


def copy_button(text: str, label: str = "📋 KI-ANALYSE GENERIEREN & KOPIEREN") -> None:
    """Kopiert in die Zwischenablage (Browser-API; funktioniert unter HTTPS und localhost)."""
    payload = json.dumps(text)
    components.html(f"""
<button id="cp" style="width:100%;padding:14px 18px;border-radius:10px;border:0;background:#3987e5;color:white;font-weight:700;
 font-size:15px;cursor:pointer;font-family:Inter,Segoe UI,sans-serif">{label}</button>
<div id="msg" style="color:#b4bac6;font:13px Inter,Segoe UI,sans-serif;margin-top:6px"></div>
<script>
const t = {payload};
document.getElementById('cp').onclick = async () => {{
  try {{ await navigator.clipboard.writeText(t); document.getElementById('msg').innerText='✓ In die Zwischenablage kopiert – jetzt in Claude oder ChatGPT einfügen.'; }}
  catch(e) {{ const ta=document.createElement('textarea'); ta.value=t; document.body.appendChild(ta); ta.select();
     try {{ document.execCommand('copy'); document.getElementById('msg').innerText='✓ Kopiert.'; }}
     catch(e2) {{ document.getElementById('msg').innerText='Kopieren blockiert – bitte Textfeld unten verwenden (Strg+A, Strg+C).'; }}
     ta.remove(); }}
}};
</script>""", height=80)


def render():
    ctx = st.session_state["ctx"]
    m, sel = ctx["m"], ctx["sel"]
    p, c, f = sel.period, sel.comp, sel.filters
    C.header("AI Business Analyst", "Erzeugt einen vollständigen Analyse-Prompt aus den aktuell gewählten Daten – "
                                    "ohne KI-Schnittstelle. Einfügen in Claude oder ChatGPT.")
    t1, t2 = st.tabs(["KI-Analyse-Prompt", "Berichte & Export"])
    with t1:
        c1, c2 = st.columns([1, 2])
        mode = c1.radio("Analysemodus", ["quick", "deep"], format_func={"quick": "Quick Analysis", "deep": "Deep Business Analysis"}.get,
                        key="ai_mode")
        c2.markdown(f"**Zeitraum:** {p.label} ({p.fmt()})  \n**Vergleich:** {c.label + ' (' + c.fmt() + ')' if c else 'keiner'}  \n"
                    f"**Filter:** {f.describe()}  \n<span class='note'>Zeitraum, Vergleich und Filter in der Seitenleiste ändern.</span>",
                    unsafe_allow_html=True)
        text, details = PR.build_prompt(m, p, c, f, mode)
        copy_button(text)
        st.caption(f"Prompt-Länge: {len(text):,} Zeichen (~{len(text) // 4:,} Tokens)".replace(",", "."))
        if len(text) > 60000:
            st.warning("Sehr großer Prompt – Detaildaten wurden zusammengefasst. Vollständige Daten als CSV unten.")
        st.text_area("Vorschau (bearbeitbar, Strg+A / Strg+C)", text, height=420, key="ai_text")
        b1, b2 = st.columns(2)
        b1.download_button("⬇ Prompt als Markdown", text.encode("utf-8"), f"ki_analyse_{dt.date.today()}.md", "text/markdown",
                           use_container_width=True)
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("prompt.md", text)
            for name, df in details.items():
                z.writestr(f"{name}.csv", df.to_csv(index=False, sep=";", decimal=","))
        b2.download_button("⬇ Prompt + Detaildaten (ZIP mit CSV)", zbuf.getvalue(), f"ki_analyse_daten_{dt.date.today()}.zip",
                           "application/zip", use_container_width=True)
    with t2:
        st.markdown("**Management-Report (PDF)** – Kennzahlen, Umsatzentwicklung, Decomposition, Frühwarnungen, Top-Produkte "
                    "für den gewählten Zeitraum.")
        if st.button("PDF erzeugen", key="pdf_btn"):
            with st.spinner("Erzeuge PDF …"):
                st.session_state["pdf_bytes"] = export.management_pdf(m, p, c, f)
        if st.session_state.get("pdf_bytes"):
            st.download_button("⬇ Management-Report.pdf", st.session_state["pdf_bytes"], f"management_report_{dt.date.today()}.pdf",
                               "application/pdf")
        st.markdown("**Excel-Gesamtpaket** – KPI-Übersicht, Umsatz je Woche/Monat/Jahr, Produkte, Attribution, Sendungen, Tagesdaten.")
        if st.button("Excel erzeugen", key="xlsx_btn"):
            with st.spinner("Erzeuge Excel …"):
                st.session_state["xlsx_bytes"] = export.excel_bundle(m, p, c, f)
        if st.session_state.get("xlsx_bytes"):
            st.download_button("⬇ BI_Export.xlsx", st.session_state["xlsx_bytes"], f"bi_export_{dt.date.today()}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        C.note("Einzelne Tabellen lassen sich zusätzlich direkt auf jeder Seite als CSV/Excel exportieren.")

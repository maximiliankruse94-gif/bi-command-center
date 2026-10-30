"""Export: Management-Report (PDF), Excel-Gesamtpaket, Markdown."""
from __future__ import annotations

import datetime as dt
import io

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from .analytics import alerts as AL
from .analytics import attribution as A
from .analytics import decomposition as D
from .analytics.metrics import aggregate, nl_aggregate, nl_summary, revenue_summary
from .analytics.model import Filters, Model, filter_daily, filter_nl
from .analytics.periods import Period


def _de(v, d=0):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "k. A."
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(v):
    return "k. A." if v is None or (isinstance(v, float) and pd.isna(v)) else _de(v) + " €"


def _pct(v, d=1):
    return "k. A." if v is None or (isinstance(v, float) and pd.isna(v)) else _de(v * 100, d) + " %"


def _chg(c, r):
    if c is None or r is None or not r:
        return "k. A."
    return ("+" if c >= r else "") + _de((c / r - 1) * 100, 1) + " %"


def _png(fig) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=25 * cm, height=8.2 * cm)


def management_pdf(m: Model, p: Period, c: Period | None, f: Filters) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.2 * cm,
                            bottomMargin=1.2 * cm, title="Management-Report", author="BI Command Center")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=18, textColor=colors.HexColor("#0d366b"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, textColor=colors.HexColor("#0d366b"), spaceBefore=8)
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8, textColor=colors.HexColor("#555555"))
    el = [Paragraph("Management-Report · Business Intelligence Command Center", h1),
          Paragraph(f"Zeitraum: <b>{p.label}</b> ({p.fmt()})" + (f" &nbsp;·&nbsp; Vergleich: <b>{c.label}</b> ({c.fmt()})" if c else "") +
                    f" &nbsp;·&nbsp; Datenstand {m.asof:%d.%m.%Y} &nbsp;·&nbsp; erstellt {dt.datetime.now():%d.%m.%Y %H:%M}", ss["Normal"]),
          Paragraph(f"Filter: {f.describe()}", small), Spacer(1, 8)]
    rc = revenue_summary(filter_daily(m.daily, p.start, p.end), p)
    rr = revenue_summary(filter_daily(m.daily, c.start, c.end), c) if c else {}
    nc_df, nr_df = filter_nl(m.nl, f, p.start, p.end), (filter_nl(m.nl, f, c.start, c.end) if c else m.nl.iloc[0:0])
    nc, nr = nl_summary(nc_df), (nl_summary(nr_df) if c else {})
    rows = [["Kennzahl", "Aktuell", "Vergleich", "Veränderung"]]
    for k, lbl, fm in [("umsatz_gesamt", "Gesamtumsatz", _eur), ("umsatz_pro_tag", "Ø Umsatz pro Tag", _eur),
                       ("erstzahlung", "Erstzahlungen", _eur), ("wiederkehrend", "Wiederkehrende Zahlungen", _eur),
                       ("rueckgaben", "Rückgaben", _eur), ("werbung", "Werbekosten", _eur), ("verdienst", "Verdienst", _eur)]:
        rows.append([lbl, fm(rc.get(k)), fm(rr.get(k)), _chg(rc.get(k), rr.get(k))])
    for k, lbl, fm in [("sendungen", "Newsletter", _de), ("umsatz", "Newsletter-Umsatz (gemessen)", _eur),
                       ("open_rate", "Öffnungsrate", _pct), ("ctor", "Klickrate (Klicks/Öffnungen)", lambda v: _pct(v, 2)),
                       ("cr_click", "Conversion Rate", lambda v: _pct(v, 2)), ("rev_per_recipient", "Umsatz je 1.000 Empfänger",
                                                                                lambda v: _eur(v * 1000 if v else None))]:
        rows.append([lbl, fm(nc.get(k)), fm(nr.get(k)), _chg(nc.get(k), nr.get(k))])
    share = (nc["umsatz"] / rc["umsatz_gesamt"]) if nc.get("umsatz") and rc.get("umsatz_gesamt") else None
    share_r = (nr.get("umsatz") / rr["umsatz_gesamt"]) if nr.get("umsatz") and rr.get("umsatz_gesamt") else None
    rows.append(["Newsletter-Umsatzanteil", _pct(share), _pct(share_r), ""])
    t = Table(rows, colWidths=[8 * cm, 5 * cm, 5 * cm, 4 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d366b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f9")]),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc"))]))
    el += [Paragraph("Kennzahlen", h2), t]
    # Chart: Monatsumsatz 24 Monate
    a = aggregate(m.daily, "monat", ["umsatz_gesamt", "erstzahlung", "wiederkehrend"]).tail(24)
    nlm = m.nl.groupby("ym").umsatz.sum()
    fig, ax = plt.subplots(figsize=(13, 4.2))
    ax.bar(a.label, a.erstzahlung.fillna(0), color="#2a78d6", label="Erstzahlungen")
    ax.bar(a.label, a.wiederkehrend.fillna(0), bottom=a.erstzahlung.fillna(0), color="#1baf7a", label="Wiederkehrend")
    ax.plot(a.label, a.umsatz_gesamt, color="#333333", marker="o", lw=1.5, label="Gesamtumsatz")
    ax.plot(a.label, a.label.map(nlm), color="#eda100", marker="o", lw=1.5, label="Newsletter-Umsatz")
    ax.set_title("Umsatzentwicklung 24 Monate", loc="left", fontsize=11)
    ax.tick_params(axis="x", rotation=60, labelsize=7)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: _de(v / 1000) + " T€"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=8, frameon=False, ncol=4)
    el += [Spacer(1, 6), _png(fig)]
    el.append(PageBreak())
    if c and len(nr_df) and len(nc_df):
        dec = D.decompose_newsletter(nr_df, nc_df)
        el.append(Paragraph("Revenue Decomposition Newsletter-Umsatz (Shapley)", h2))
        drows = [["Faktor", "Vergleich", "Aktuell", "Δ %", "Beitrag"]]
        for x in dec["faktoren"]:
            fm = (lambda v: _pct(v, 2)) if x["faktor"] in ("open_rate", "ctor", "cr_click") else _de
            drows.append([x["label"], fm(x["wert_ref"]), fm(x["wert_cur"]), _pct(x["veraenderung_pct"]), _eur(x["beitrag_eur"])])
        if dec.get("rest") is not None:
            drows.append(["Nicht zerlegbarer Rest", "", "", "", _eur(dec["rest"])])
        drows.append(["Veränderung gesamt", "", "", "", _eur(dec["delta"])])
        dt_ = Table(drows, colWidths=[8 * cm, 4 * cm, 4 * cm, 3 * cm, 4 * cm])
        dt_.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d366b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                 ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                                 ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc"))]))
        el.append(dt_)
        tot = D.decompose_total(rr, rc)
        hints = D.diagnostic_hints(dec["faktoren"], tot, dec["delta"], (rc["umsatz_gesamt"] or 0) - (rr.get("umsatz_gesamt") or 0))
        el.append(Paragraph("Prüfhinweise (Hypothesen, keine nachgewiesenen Ursachen)", h2))
        el += [Paragraph("• " + h, ss["Normal"]) for h in hints]
    al = AL.all_alerts(m.daily, m.nl, m.asof)
    if not al.empty:
        el.append(Paragraph("Frühwarnsystem (Schweregrad hoch/mittel)", h2))
        arows = [["Kennzahl", "Zeitraum", "Aktuell", "Referenz", "Δ %", "Schweregrad"]]
        for r in al[al.schweregrad != "info"].itertuples():
            fm = (lambda v: _pct(v, 2)) if r.einheit == "%" else (lambda v: _de(v, 2) + " €")
            arows.append([r.kennzahl, r.zeitraum, fm(r.aktuell), fm(r.referenz), _pct(r.pct), r.schweregrad])
        at = Table(arows, colWidths=[8 * cm, 5 * cm, 3.2 * cm, 3.2 * cm, 2.5 * cm, 2.6 * cm])
        at.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d366b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("FONTSIZE", (0, 0), (-1, -1), 8), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc"))]))
        el.append(at)
    if len(nc_df):
        pa = nl_aggregate(nc_df, ["produkt"]).sort_values("umsatz", ascending=False).head(12)
        el.append(Paragraph("Top-Produkte im Newsletter (Analysezeitraum)", h2))
        prow = [["Produkt", "Newsletter", "Umsatz", "Öffnungsrate", "Klickrate", "Conv.", "€ je 1.000 Empf."]]
        for r in pa.itertuples():
            prow.append([r.produkt, _de(r.sendungen), _eur(r.umsatz), _pct(r.open_rate), _pct(r.ctor, 2), _pct(r.cr_click, 2),
                         _eur(r.rev_per_recipient * 1000 if r.rev_per_recipient else None)])
        pt = Table(prow)
        pt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d366b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc"))]))
        el.append(pt)
    el += [Spacer(1, 10), Paragraph("Definitionen: Umsatz = netto ohne USt, vor Rückgaben (Tagesstatistiken). Newsletter-Umsatz laut Tracking, "
                                    "nach Versanddatum, Attributionsfenster unbekannt. Raten gewichtet (Σ Zähler/Σ Nenner). Öffnungsraten durch "
                                    "Apple MPP verzerrt. Zerlegungen beschreiben rechnerische Beiträge, keine Kausalität.", small)]
    doc.build(el)
    return buf.getvalue()


def excel_bundle(m: Model, p: Period, c: Period | None, f: Filters) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        rc = revenue_summary(filter_daily(m.daily, p.start, p.end), p)
        rr = revenue_summary(filter_daily(m.daily, c.start, c.end), c) if c else {}
        nc = nl_summary(filter_nl(m.nl, f, p.start, p.end))
        nr = nl_summary(filter_nl(m.nl, f, c.start, c.end)) if c else {}
        kpi = pd.DataFrame([{"Kennzahl": k, "Aktuell": rc.get(k), "Vergleich": rr.get(k)} for k in rc] +
                           [{"Kennzahl": "NL " + k, "Aktuell": nc.get(k), "Vergleich": nr.get(k)} for k in nc])
        kpi.to_excel(xw, "KPI-Übersicht", index=False)
        aggregate(m.daily, "monat").to_excel(xw, "Umsatz Monat", index=False)
        aggregate(m.daily, "woche").to_excel(xw, "Umsatz Woche", index=False)
        aggregate(m.daily, "jahr").to_excel(xw, "Umsatz Jahr", index=False)
        nl_aggregate(filter_nl(m.nl, f, p.start, p.end), ["produkt"]).to_excel(xw, "Produkte Zeitraum", index=False)
        A.attribution_table(m.daily, m.nl, "monat").to_excel(xw, "Attribution Monat", index=False)
        filter_nl(m.nl, f, p.start, p.end).drop(columns=["betreff_norm"], errors="ignore").to_excel(xw, "Sendungen Zeitraum", index=False)
        filter_daily(m.daily, p.start, p.end).to_excel(xw, "Tage Zeitraum", index=False)
    return buf.getvalue()

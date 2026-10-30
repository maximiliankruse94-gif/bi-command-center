"""Tab-Erkennung: neue, umbenannte, unbekannte und kaputte Tabellenblätter."""
import datetime as dt

from bi.detect import classify

NL_HEADER = ["Datum", "Tag", "Uhrzeit", "Produkt", "ID", "Campaignkey", "Empfänger", "Öffnungen", "Öffnungsrate", "Klicks",
             "Clickrate", "Käufe", "Conversionrate", "EPC", "Gesamtumsatz (Netto)", "Folgezahlung", "Folgeeinnahmen", "Betreff"]


def nl_rows(n=12, header=True):
    rows = [NL_HEADER] if header else []
    for i in range(n):
        d = dt.date(2027, 1, 1) + dt.timedelta(days=i)
        rows.append([d.strftime("%d.%m.%Y"), ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][d.weekday()],
                     "06:00", "AMC", None, f"NL{d:%d%m%y}", 55000, 14000, 0.25, 500, 0.035, 10, 0.02, 5.0, 2500, None, None, f"Betreff {i}"])
    return rows


def test_new_quarter_tab_detected_by_structure_not_name():
    c = classify("newsletter", "Irgendein Name", nl_rows())
    assert c.kind == "newsletter" and c.confidence >= 0.8
    c2 = classify("newsletter", "Mails 2027 Q1", nl_rows())
    assert c2.kind == "newsletter" and c2.confidence >= c.confidence  # Name nur Zusatzindiz


def test_headerless_newsletter_detected_by_content():
    c = classify("newsletter", "Mails 2027 Q2", [[None, "#REF!", "#REF!"]] + nl_rows(header=False))
    assert c.kind == "newsletter" and "layout" in c.meta


def test_unknown_tab_not_imported():
    rows = [["Spalte A", "Spalte B", "Spalte C"]] + [[i, f"x{i}", i * 2] for i in range(20)]
    c = classify("newsletter", "Notizen", rows)
    assert c.kind == "unknown" and c.status == "unbekannt"


def test_daily_tab_new_month():
    hdr = ["Tag", "Umsatz GTK", "Umsatz littlefreilich", "Umsatz GunnarKessler", "Umsatz WU", "Umsatz Gesamt"]
    rows = [hdr] + [[f"{d:02d}.04.27", 100, 10, 5, 0, 115] for d in range(1, 20)]
    assert classify("daily", "April 27", rows).kind == "daily"
    assert classify("daily", "Kopie", rows).kind == "daily"  # auch ohne Monatsnamen


def test_template_and_dashboard_ignored():
    hdr = ["Tag", "Umsatz GTK", "Umsatz littlefreilich", "Umsatz GunnarKessler", "Umsatz Gesamt"]
    rows = [hdr] + [[f"{d:02d}.01.2021", None, None, None, 0] for d in range(1, 20)]
    assert classify("daily", "Muster 30", rows).kind == "ignore_template"
    assert classify("daily", "Tagesstatistiken", [["Steuerzelle für Zeile"], ["Steuerzelle für Zeile", 30]]).kind == "ignore_dashboard"


def test_manual_mapping_overrides():
    rows = [["Spalte A"]] * 5
    c = classify("newsletter", "Notizen", rows, manual={("newsletter", "Notizen"): "ignore"})
    assert c.kind == "ignore" and c.manual


def test_structure_signature_changes_on_header_change():
    from bi.detect import structure_signature
    a = nl_rows()
    b = [list(a[0]) + ["Neue Spalte"]] + a[1:]
    assert structure_signature(a) != structure_signature(b)

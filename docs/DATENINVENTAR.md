# Dateninventar & Datenqualitätsbericht (Phase 1 + 2)

Stand: 30.10.2026 · Grundlage: vollständige XLSX-Exporte aller vier Google Sheets (jedes Tabellenblatt, jede Zeile geprüft).

## 1. Überblick

| Arbeitsmappe | Tabs | importiert | ignoriert (mit Begründung) | Datensätze | Zeitraum |
|---|---|---|---|---|---|
| Tagesübersicht – Umsatz Ausgaben Gewinn | 74 | 72 Monats-Tabs | „Tagesstatistiken“ (Formular-/Anzeigeblatt mit Steuerzellen), „Muster 30“ (leere Vorlage) | 2.189 Tage | 01.10.2020 – 29.10.2026 |
| Wochenübersicht | 7 | 7 Jahres-Tabs | – | 313 ISO-Wochen (eine KW stand in zwei Tabs) | KW 40/2020 – KW 43/2026 |
| Monatsinfo | 8 | 6 | „Abo entwicklung“, „Verkaufsseiten Entwicklung“ (Referenzblätter, abweichende Struktur) | 73 Monate + 84 Produkt-Abo-Werte | 09/2020 – 09/2026 |
| Newsletter Statistiken | 28 | 25 Quartals-/Jahres-Tabs | „Tabellenblatt3“, „Kopie von Tabellenblatt3“ (Roh-Export Mail-Tool, Gesamtaktionen), „EEP NL Statistiken“ (Auszug der Produkt-EEP-Zeilen → Import würde doppelt zählen) | 2.002 Sendungen | 04.10.2020 – 30.10.2026 |

## 2. Struktur je Datenquelle

### Tagesstatistiken (maßgeblich für Umsatz)
Eine Zeile je Tag. Spaltenzahl wuchs von 18 (2020) auf 94 (2024+); Zuordnung erfolgt daher ausschließlich über Überschriften.
Importiert: Zahlungskonten (GTK, littlefreilich, GunnarKessler, WU/EA), Umsatz Gesamt, Rückgaben, Rücklastschriften,
Werbung gesamt, Buchkosten, Kosten, Verdienst, **Einmalzahlungen, Abo-Start, Abo wiederkehrend, Rate 1, Rate**.
Nicht importiert (für spätere Erweiterung vorhanden): Werbekosten je Kampagne, Sales/Leads je Funnel.

**Wichtige Befunde**
- „Umsatz Gesamt“ = Summe der Zahlungskonten, **netto ohne USt, vor Rückgaben** (Monatsblatt bestätigt: „Umsatz Netto“ = Summe der Konten, „Umsatz Brutto“ ≈ ×1,19).
- Die Aufteilung **Einmal/Abo-Start/Abo/Raten** summiert sich exakt auf das Konto **GTK** – für die übrigen Konten gibt es keine Aufteilung.
- Ab 2025 fehlt in der Datumsspalte die Überschrift „Tag“ → Erkennung über Inhalt.
- **Oktober 2022 fehlt** als Tab (31 Tage ohne Tagesdaten; Monatsstatistik vorhanden).
- Datums-Tippfehler (automatisch korrigiert, jeweils protokolliert): z.B. „28.10.97“, „18.10.25“ im Tab Oktober 24, „13..02.26“,
  ganzer Tab „Juni 24“ mit Datumsangaben „..05.24“, „31.06.2023“ im Tab Mai 23, doppeltes „29.07.24“ statt 26.07.
- 28.12.2020: Summe der Konten 11.695 € ≠ Umsatz Gesamt 4.363 € (nicht korrigierbar, markiert).

### Wochenstatistiken (Validierung)
Ein Tab je Jahr, ISO-KW. Enthält zusätzlich **CopeCart** (2024: 174 T€), das in den Tagesdaten fehlt.
Befunde: Startdatum-Tippfehler („30.01.12“, „27.03.23“, „15.11.25“, Enddatum „31.23.23“) → maßgeblich ist Tab-Jahr + KW.
KW 53 im Tab 2025 ist ISO-KW 1/2026 und steht zusätzlich im Tab 2026 → nur einmal gezählt. Zeile „Gesamt“ ausgeschlossen.

### Monatsstatistiken (Validierung, Brutto, Abo-Bestände)
Befunde: Tab „Übersicht 2023“ beschriftet Sep–Dez mit **2022** (Tab-Jahr verwendet); Tab 2022 enthält unter der Jahressumme eine
Vergleichszeile „Juli“ (ausgeschlossen); künftige Monate enthalten Formelreste (0 €, −100 %) → als „fehlend“, nicht als 0 behandelt;
Monatsname „Febraur“; Produkt-Abo-Spalten 2024 teils mit Formelfehlern (negative Werte).

### Newsletter-Statistiken
Eine Zeile je Sendung. Spalten: Datum, Wochentag, Uhrzeit, Produkt, Produkt-ID, Campaignkey, Empfänger, Öffnungen, Klicks,
Käufe, Gesamtumsatz (Netto), Folgezahlung, Folgeeinnahmen, Betreff (2020: „Headline“).

**Wichtige Befunde**
- **Campaignkey ist nicht eindeutig** (z.B. NL301125 viermal) → stabile ID aus Datum + Uhrzeit + Campaignkey + Produkt.
- An 45 Tagen mehrere Sendungen; jede Sendung ist ein eigener Datensatz.
- Sheet-„Clickrate“ = Klicks / **Öffnungen** (Click-to-Open-Rate); „Conversionrate“ = Käufe / Klicks.
- „Mails 2024 Q4“: Kopfzeile defekt (#REF!) und Zeilen nach Produkt sortiert → Erkennung über Datentypen.
- „Mails 2023 Q4“: Überschriften „Tag/Datum“ vertauscht → Erkennung über Inhalt.
- „Mails 2024 Q2“: Wochentag-Spalte in 78 Zeilen falsch → Wochentag wird immer aus dem Datum berechnet.
- 82 unterschiedliche Produktkürzel inkl. Schreibvarianten („KI DMMC“/„KI-DMMC“, „24MCS“/„24 MCS“, „B-Day“/„Bday“) → automatisch vereinheitlicht.
- Fehlende Werte: 157 Sendungen ohne Umsatzangabe, 103 ohne Klicks (nicht als 0 gewertet); „-“ bei Käufen/Umsatz = 0.
- Einzelne Ausreißer: Öffnungen = Empfänger (100 %), Käufe > Klicks (bis 32 Käufe bei 5 Klicks) → markiert.

## 3. Abgleich der Ebenen (keine Doppelzählung)
- Summe Tagesumsätze vs. Monatsstatistik (ohne CopeCart): **in 58 von 71 vergleichbaren Monaten ±0,5 %**. Abweichungen v.a.
  Feb–Apr 2024 und Feb–Apr 2025 (Tagesdaten ≈ um den CopeCart-Betrag höher → CopeCart dort vermutlich in den Tagesdaten enthalten),
  Okt/Dez 2020 (Datenfehler 28.12.2020).
- Wochenabgleich: 280 Wochen übereinstimmend, 26 abweichend (Details im Dashboard unter Datenmanagement › Abgleich).

## 4. Newsletter- vs. Gesamtumsatz (Attributionsprüfung)
An 74 von 1.930 Versandtagen übersteigt der Newsletter-Umsatz der versendeten Mails den gesamten Tagesumsatz (an 393 Tagen die
Erstzahlungen). Der Newsletter-Umsatz ist daher ein **über ein unbekanntes Fenster kumulierter Kampagnenumsatz**.
→ Anteile werden nur für Wochen/Monate/Quartale/Jahre ausgewiesen.

## 5. Welche gewünschten Funktionen sind mit den Daten möglich?

| Funktion | Möglich? | Hinweis |
|---|---|---|
| Umsatz Tag/Woche/Monat/Quartal/Jahr, YoY | ✅ | ab 10/2020, Lücke 10/2022 |
| Erst- vs. wiederkehrende Zahlungen | ✅ eingeschränkt | nur Hauptkonto GTK (≈ 80–90 % des Umsatzes) |
| Newsletter-Funnel, Raten, Produkte, Betreff, Versandzeit | ✅ | eindeutige Öffnungen/Klicks |
| Eindeutige vs. Gesamtaktionen | ⚠️ | Gesamtaktionen nur in Roh-Export für ~60 Sendungen |
| Newsletter-Umsatzanteil | ✅ ab Woche | Attributionsfenster unbekannt |
| Newsletter → Erst-/Folgezahlung zuordnen | ❌ | nicht in den Daten; nur Vergleichsgröße |
| Revenue Decomposition | ✅ | Shapley exakt |
| Ø Bestellwert | ✅ | Newsletter-Umsatz / Käufe (nicht Gesamtshop) |
| Rückerstattungen | ✅ Gesamt | nicht je Newsletter |
| Brutto/Netto | ✅ | Brutto nur monatlich |
| Abo-Bestände/Kündigungen | ✅ | monatlich |
| Werbekosten | ✅ täglich gesamt | je Kampagne vorhanden, noch nicht importiert |

# Bedienungsanleitung

## Täglicher Ablauf
1. Dashboard öffnen → **Executive Overview**: Umsatz-Kacheln (Wert, Vergleich, Veränderung in € und %, Mini-Trend),
   Umsatzstruktur, Business Health und die wichtigsten Frühwarnungen.
2. Rote/gelbe Warnungen → **Business Alerts** (Details, mögliche Erklärungen, benötigte Informationen).
3. Bei Umsatzveränderungen → **Revenue Attribution › Revenue Decomposition**: welcher Faktor wie viele Euro beiträgt.

## Daten aktualisieren
- **Automatisch:** täglich 06:00 Uhr. Fällt dieser Lauf aus, wird beim ersten Öffnen des Dashboards nachsynchronisiert.
- **Manuell:** Button **„JETZT AKTUALISIEREN“** links. Danach erscheint: Zeitpunkt, importierte Tabellen, neue/aktualisierte
  Datensätze, Fehler und unbekannte Tabellenblätter.

## Neue Tabellenblätter anlegen
Einfach wie bisher arbeiten – **kein Code nötig**:
- Neuer Monat in den Tagesstatistiken (z.B. „November 26“), neues Quartal („Mails 2027 Q1“), neues Jahr in Wochen-/Monatsübersicht.
- Wichtig ist nur, dass die **Spaltenüberschriften** wie bisher heißen (z.B. „Umsatz Gesamt“, „Empfänger“, „Öffnungen“, „Klicks“).
  Die Reihenfolge der Spalten und der Tab-Name sind egal.
- Kann ein Blatt nicht eindeutig erkannt werden, wird es **nicht** importiert. Unter **Datenmanagement › Manuelle Zuordnung**
  wählen Sie den Typ (oder „ignorieren“); die Zuordnung wird dauerhaft gespeichert.
- Hilfsblätter (Notizen, Kopien) können bestehen bleiben; sie werden als „unbekannt“ oder „ignoriert“ geführt.
- Bitte vermeiden: dieselbe Sendung/denselben Tag in zwei Tabs zu führen (wird zwar erkannt und nur einmal gezählt, aber gemeldet).

## Zeiträume und Vergleiche
Seitenleiste **⏱ Zeitraum**: Schnellauswahl (Heute … Letzte 365 Tage), Jahr, Quartal, Monat, Kalenderwoche oder individuell.
**Vergleich mit**: automatisch (Vorjahr bzw. Vorperiode), Vorperiode, Vorjahr oder frei wählbar. Laufende Zeiträume werden
immer mit gleich vielen Tagen verglichen. Alle Seiten reagieren auf diese Auswahl.

## Filter
Produkt, Wochentag, Versanduhrzeit und Betreff-Suche sind kombinierbar und wirken auf alle Newsletter-Auswertungen.
„↺ Alle Filter zurücksetzen“ stellt den Ausgangszustand her.

## Drill-down
**Historical Analysis**: Balken anklicken → Jahr → Quartal → Monat → Kalenderwoche → Tag → einzelne Newsletter (mit Quell-Tab und Zeile).
Über die Schaltflächen oben geht es zurück.

## KI-Analyse
**AI Business Analyst**: Zeitraum/Filter wählen, Modus „Quick“ oder „Deep“, dann **„KI-ANALYSE GENERIEREN & KOPIEREN“** –
der Prompt liegt in der Zwischenablage und kann direkt in Claude oder ChatGPT eingefügt werden. Detaildaten als ZIP/CSV.

## Exporte
Jede Tabelle: „⬇ CSV“ / „⬇ Excel“. Management-Report als PDF und Excel-Gesamtpaket unter **AI Business Analyst › Berichte & Export**.

## Produkt-Schreibweisen zusammenführen
Varianten wie „KI DMMC“ / „KI-DMMC“ werden automatisch zusammengeführt. Andere Zusammenfassungen (z.B. „ICM“ = „ICMO“?) bewusst in
`config/product_aliases.yaml` eintragen – das System rät hier nicht.

## Teammitglied hinzufügen
Siehe docs/DEPLOYMENT.md › Teamzugang (eine Zeile in der Cloud Shell).

## Datenqualität
**Datenmanagement › Datenqualität** listet alle erkannten Probleme mit Tab und Zeile (z.B. Tippfehler im Datum, fehlende Tage,
Abweichungen Tag ↔ Monat). Korrekturen erfolgen im Google Sheet; nach der nächsten Synchronisierung verschwindet der Hinweis.

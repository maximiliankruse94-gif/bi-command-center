# Kennzahlen & Berechnungslogik

Alle Berechnungen erfolgen im Programmcode (`bi/analytics/*`), ohne KI. Prozentwerte aus den Sheets werden **nicht** übernommen,
sondern aus absoluten Zahlen neu berechnet und nur zur Kontrolle verglichen.

## Umsatz (Quelle: Tagesstatistiken – maßgeblich)
| Kennzahl | Formel |
|---|---|
| Gesamtumsatz | Σ „Umsatz Gesamt“ (= GTK + littlefreilich + GunnarKessler + WU/EA), netto ohne USt, vor Rückgaben |
| Umsatz nach Rückgaben | Gesamtumsatz − Rückgaben − Rücklastschriften |
| Erstzahlungen | Einmalzahlungen + Abo-Start + Raten-Start (Rate 1) – nur Konto GTK |
| Wiederkehrende Zahlungen | Abo wiederkehrend + Raten wiederkehrend – nur Konto GTK |
| Nicht aufgeschlüsselt | Gesamtumsatz − (Erstzahlungen + Wiederkehrend) |
| Anteil Erstzahlungen | Erstzahlungen / (Erstzahlungen + Wiederkehrend) |
| Ø Tagesumsatz | Gesamtumsatz / Tage **mit Daten** (fehlende Tage zählen nicht als 0) |
| Volatilität | Standardabweichung / Mittelwert der Tagesumsätze (Variationskoeffizient) |
| Umsatztrend | Steigung einer linearen Regression über 90 Tage, in % des Mittelwerts, hochgerechnet auf 30 Tage |
| Saisonindex | Monatsumsatz / Ø Monatsumsatz desselben Jahres, gemittelt über vollständige Jahre |

Wochen = ISO 8601 (Montag–Sonntag, KW 1 enthält den ersten Donnerstag). Wochen- und Monatsstatistiken dienen nur der Validierung.

## Newsletter (je Sendung und gewichtet über Sendungen)
| Kennzahl | Formel |
|---|---|
| Öffnungsrate | Σ Öffnungen / Σ Empfänger |
| Klickrate (CTOR) | Σ Klicks / Σ Öffnungen (entspricht „Clickrate“ im Sheet) |
| CTR | Σ Klicks / Σ Empfänger |
| Conversion Rate | Σ Käufe / Σ Klicks |
| Umsatz je Empfänger | Σ Umsatz / Σ Empfänger |
| EPC (Umsatz je Klick) | Σ Umsatz / Σ Klicks |
| Umsatz je Conversion (Ø Bestellwert) | Σ Umsatz / Σ Käufe |
| Ø Umsatz je Newsletter | Σ Umsatz / Anzahl Sendungen mit Umsatzangabe |

Gewichtung: Summe der Zähler durch Summe der Nenner. Sendungen mit fehlendem Zähler oder Nenner werden aus **beiden** ausgeschlossen.
Öffnungsraten sind seit Apple Mail Privacy Protection (20.09.2021) überhöht – in Grafiken markiert.

## Newsletter-Umsatzanteil
`Anteil = Σ Newsletter-Umsatz (Versanddatum in Periode) / Σ Gesamtumsatz (Periode)` – nur ab Wochenebene.
Restumsatz = Gesamtumsatz − Newsletter-Umsatz (rechnerisch, keine Aussage über Kausalität).

## Revenue Decomposition
1. **Gesamtumsatz (additiv, exakt):** ΔUmsatz = ΔErstzahlungen + ΔWiederkehrend + ΔNicht aufgeschlüsselt.
2. **Newsletter-Umsatz (multiplikativ, Shapley):**
   Umsatz = Sendungen × Empfänger/Sendung × Öffnungsrate × CTOR × Conversion Rate × Ø Umsatz je Kauf.
   Shapley-Wert je Faktor i: φᵢ = Σ_{S ⊆ N∖{i}} |S|!(n−|S|−1)!/n! · [f(S∪{i}) − f(S)], wobei f(S) die Faktoren in S auf
   aktuellem, alle anderen auf Vergleichsniveau ansetzt. Σφᵢ = exakte Veränderung; Wechselwirkungen werden fair verteilt.
   Sendungen mit unvollständigen Funnel-Daten → „nicht zerlegbarer Rest“.
3. **Produktmix:** Umsatz = N × Σₚ wₚ·vₚ (N Sendungen, w Anteil je Produkt, v Umsatz je Sendung) → Shapley über Volumen, Mix, Performance.
4. **Prüfhinweise:** feste Regeln (z.B. „Öffnung stabil, Klickrate −10 % → Inhalt/CTA prüfen“), formuliert als Hypothesen.

## Betreffzeilen
- Ranking-Raten per Empirical Bayes: (Erfolge + α)/(Versuche + α + β); α, β aus der Verteilung aller Sendungen (Momentenmethode).
- Umsatz je 1.000 Empfänger: Schrumpfung w·Wert + (1−w)·Gesamtmittel mit w = n/(n + Median-Empfänger).
- 95-%-Intervall nach Wilson.
- Merkmalseffekt: Abweichung jeder Sendung vom Mittel ihrer Produkt-Jahr-Gruppe, gewichtet gemittelt; „mit“ minus „ohne“ Merkmal.
- Aussagekraft: ≥ 30 Sendungen je Gruppe „belastbar“, ≥ 10 „eingeschränkt“.

## Versandzeit-Heatmap
Wochentag × Zeitfenster; Zellen mit weniger als n Sendungen (einstellbar, Standard 5) werden ausgeblendet. Optional bereinigt
um Produkt- und Jahreseffekte (relative Abweichung vom Produkt-Jahr-Mittel). Fehlerbalken = 95-%-Konfidenzintervall.

## Frühwarnsystem
z = (aktueller Wert − Referenz) / Streuung der Referenz. |z| ≥ 3 hoch (strukturell), ≥ 2 mittel, sonst normale Schwankung.
Referenzen: gleiche Wochentage (8 Wochen), gleich lange Fenster (26 Wochen), Vorjahr (gleiche Wochentage), 13 vorherige 28-Tage-Fenster,
Newsletter: 180 Tage vor den letzten 30 Tagen; Produkte: 90–730 Tage Historie, Mindestanzahl Sendungen.

## Zeitraumvergleiche
- Laufende Zeiträume enden am letzten Tag mit Daten; Vergleiche nutzen dieselbe Anzahl Tage („Monat bis 29.“ vs. „Vorjahresmonat bis 29.“).
- Automatischer Vergleich: Tag/Woche/Monat/Quartal/Jahr → Vorjahr (Tag: gleicher Wochentag vor 52 Wochen; Woche: gleiche ISO-KW);
  freie Zeiträume → Vorperiode gleicher Länge. 29.02. → 28.02.
- Abweichende Datenabdeckung wird angezeigt; Ø je Tag ist dann aussagekräftiger als Summen.

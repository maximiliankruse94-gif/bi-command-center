# Einrichtung – nur mit Google (ohne GitHub, ohne eigene Software)

Ergebnis: Dashboard unter einer festen HTTPS-Adresse, Anmeldung mit Google-Konto, täglicher Abgleich 06:00 Uhr.
Alles läuft in **Google Cloud** im Browser. Zeitbedarf: ca. 45–60 Minuten (davon ~20 Min. Wartezeit).

## Schritt 1 – Google-Cloud-Projekt anlegen
1. https://console.cloud.google.com öffnen, mit Ihrem Google-Konto anmelden (Nutzungsbedingungen akzeptieren).
2. Oben links auf die Projektauswahl → **Neues Projekt** → Name `hideandseek-bi` → **Erstellen**. Danach das Projekt oben auswählen.
3. Menü ☰ → **Abrechnung** → Rechnungskonto verknüpfen (Kreditkarte/Lastschrift).
4. Empfehlung: **Abrechnung › Budgets & Benachrichtigungen** → Budget 30 € mit E-Mail-Warnung.

## Schritt 2 – Anmeldebildschirm für den Google-Login
1. Menü ☰ → **APIs & Dienste** → **OAuth-Zustimmungsbildschirm** (bzw. „Google Auth Platform“) → **Jetzt starten**.
2. App-Name: `BI Command Center`, Support-E-Mail: Ihre Adresse.
3. Zielgruppe:
   - **Intern**, wenn hideandseek.de ein Google-Workspace-Konto ist (empfohlen – nur Firmenkonten können sich anmelden).
   - sonst **Extern** → danach unter **Zielgruppe › Testnutzer** Ihre E-Mail und die Ihrer Kollegin hinzufügen.
4. Kontakt-E-Mail eintragen → **Erstellen**.

## Schritt 3 – Projektdateien in die Cloud Shell laden
1. Oben rechts auf das Symbol **„Cloud Shell aktivieren“** (>_) klicken. Unten öffnet sich ein Terminal (beim ersten Mal **Autorisieren**).
2. Im Cloud-Shell-Fenster rechts oben **⋮ › Hochladen** → `bi-command-center.zip` auswählen.
3. Ins Terminal eintippen (jeweils Enter):
   ```
   unzip -o bi-command-center.zip
   cd bicc
   bash deploy/setup_gcp.sh
   ```
Das Skript führt Sie durch 9 Schritte und stellt zwischendurch Fragen.

## Schritt 4 – Fragen des Skripts beantworten
- **Wer darf rein?** Ihre E-Mail (Administrator) und optional die zweite Person.
- **Google-Login:** Das Skript zeigt eine Adresse `https://bi-command-center-…run.app/oauth2callback`. Dann in einem **neuen Browser-Tab**:
  1. **APIs & Dienste › Anmeldedaten** → **+ Anmeldedaten erstellen › OAuth-Client-ID**
  2. Anwendungstyp **Webanwendung**, Name `BI Dashboard`
  3. **Autorisierte Weiterleitungs-URIs › + URI hinzufügen** → die angezeigte Adresse exakt einfügen → **Erstellen**
  4. **Client-ID** und **Clientschlüssel** kopieren und im Terminal einfügen (Einfügen: Strg+V bzw. Rechtsklick › Einfügen).
- Danach läuft alles automatisch (Datenbank, Bau, Bereitstellung). Einfach warten.

## Schritt 5 – Google Sheets freigeben
Wenn das Skript bei 9/9 anhält, zeigt es eine Adresse `bicc-runner@….iam.gserviceaccount.com`.
Jedes der vier Sheets öffnen → **Freigeben** → Adresse einfügen → Rolle **Betrachter** → „Personen benachrichtigen“ abwählen → **Senden**.
Dann im Terminal **Enter** drücken. Der erste Import startet (1–2 Minuten).

**Empfehlung:** In jedem Sheet unter „Allgemeiner Zugriff“ von „Jeder mit dem Link“ auf **Eingeschränkt** umstellen.
Ihre Original-Sheets werden vom Dashboard nur gelesen, niemals verändert.

## Schritt 6 – Fertig
Die Adresse am Ende (`https://bi-command-center-….europe-west3.run.app`) als Lesezeichen speichern und mit Google anmelden.
Die Kollegin öffnet dieselbe Adresse und meldet sich mit ihrem Google-Konto an.

## Später
| Aufgabe | So geht's |
|---|---|
| Person hinzufügen/entfernen | Cloud Shell öffnen: `cd bicc && bash deploy/setup_gcp.sh`, bei „Beibehalten?“ **n** wählen (bei *Extern* zusätzlich als Testnutzer eintragen) |
| Neue Programmversion von Claude | neue ZIP hochladen, `unzip -o bi-command-center.zip && cd bicc && bash deploy/redeploy.sh` |
| Abgleich sofort | im Dashboard „JETZT AKTUALISIEREN“ |
| Protokolle bei Fehlern | Menü ☰ → Cloud Run → `bi-sync` → Logs |
| Kosten prüfen | Menü ☰ → Abrechnung |

## Kosten (Schätzung, bitte in der Abrechnung kontrollieren)
Dashboard und Abgleich (Cloud Run) meist im Gratiskontingent; Datenbank (Cloud SQL, kleinste Stufe, mit Backups) grob 10–15 €/Monat.
Gesamt ca. 10–20 €/Monat.

## Datensicherung
Google Sheets bleiben die Originalquelle. Die Datenbank sichert sich täglich automatisch (14 Tage). Sie kann jederzeit
vollständig aus den Sheets neu aufgebaut werden.

---

# Variante „kostenfrei“ (Google Cloud Gratiskontingent)
Identische Schritte 1–6, aber in Schritt 3 statt `bash deploy/setup_gcp.sh`:
```
bash deploy/setup_gcp_free.sh
```
Unterschiede: keine Cloud-SQL-Datenbank (Hauptkostenpunkt), kein Job/Zeitplan. Die Datenbank liegt im Container und wird bei jedem
Kaltstart automatisch aus den Google Sheets neu aufgebaut (30–60 Sek. beim ersten Öffnen). Täglicher Abgleich erfolgt beim ersten
Öffnen nach 06:00 Uhr. Einschränkungen: Importhistorie beginnt nach jedem Neustart neu; manuelle Tab-Zuordnungen bitte zusätzlich in
`config/tab_mappings.yaml` eintragen (das Dashboard zeigt den Eintrag beim Speichern an). Abrechnungskonto bleibt Pflicht – Budget-Warnung setzen.
Tipp: Dashboard-Tab nach Nutzung schließen (offene Tabs halten die Instanz aktiv und verbrauchen Gratiskontingent).

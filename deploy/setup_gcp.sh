#!/usr/bin/env bash
# =============================================================================
# BI Command Center – geführte Einrichtung in Google Cloud (Region Frankfurt)
#
# Ausführen in der Google Cloud Shell im entpackten Projektordner:
#     cd ~/bicc && bash deploy/setup_gcp.sh
#
# Das Skript fragt alle nötigen Angaben ab. Es kann gefahrlos mehrfach ausgeführt
# werden (bereits vorhandene Ressourcen werden übernommen, nicht gelöscht).
# =============================================================================
set -uo pipefail

REGION="europe-west3"          # Frankfurt
SERVICE="bi-command-center"
JOB="bi-sync"
SA_NAME="bicc-runner"
DB_INSTANCE="bicc-db"
DB_NAME="bicc"
DB_USER="bicc"

step() { echo; echo "────────────────────────────────────────────────────────────"; echo "▶ $*"; echo "────────────────────────────────────────────────────────────"; }
fail() { echo; echo "✖ FEHLER: $*"; echo "  Bitte die Meldung oben kopieren und an Claude schicken."; exit 1; }

# ---------------------------------------------------------------- 0. Projekt
PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
if [ -z "$PROJECT_ID" ]; then
  read -rp "Projekt-ID eingeben (siehe Google Cloud Console oben links): " PROJECT_ID
fi
gcloud config set project "$PROJECT_ID" >/dev/null || fail "Projekt $PROJECT_ID nicht gefunden"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')" || fail "Projekt nicht lesbar"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/bicc/app:latest"
APP_URL="https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
REDIRECT_URI="${APP_URL}/oauth2callback"
echo "Projekt: $PROJECT_ID (Nr. $PROJECT_NUMBER)"
echo "Ihre spätere Dashboard-Adresse: $APP_URL"

# ---------------------------------------------------------------- 1. APIs
step "1/9  Google-Dienste aktivieren (dauert 1–2 Minuten)"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com sqladmin.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
  drive.googleapis.com sheets.googleapis.com iam.googleapis.com || fail "APIs konnten nicht aktiviert werden (Abrechnung verknüpft?)"

# ---------------------------------------------------------------- 2. Dienstkonten
step "2/9  Dienstkonto für das Dashboard anlegen"
gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NAME" --display-name="BI Command Center" || fail "Dienstkonto"
sleep 5
for ROLE in roles/cloudsql.client roles/secretmanager.secretAccessor roles/run.invoker roles/run.developer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${SA_EMAIL}" --role="$ROLE" \
    --condition=None >/dev/null || fail "Rolle $ROLE"
done
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" --member="serviceAccount:${SA_EMAIL}" \
  --role=roles/iam.serviceAccountUser >/dev/null || true
# Build-Konto (neue Projekte): Rechte für Container-Bau
BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for ROLE in roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${BUILD_SA}" --role="$ROLE" \
    --condition=None >/dev/null 2>&1 || true
done

# ---------------------------------------------------------------- 3. Zugang (wer darf rein?)
step "3/9  Wer darf das Dashboard öffnen?"
if gcloud secrets describe bicc-allowed-users >/dev/null 2>&1; then
  CUR="$(gcloud secrets versions access latest --secret=bicc-allowed-users)"
  echo "Aktuell freigeschaltet: $CUR"
  read -rp "Beibehalten? [J/n] " KEEP
else
  KEEP="n"
fi
if [[ "$KEEP" =~ ^[nN] ]]; then
  read -rp "Ihre Google-E-Mail-Adresse (Administrator): " ADMIN
  read -rp "E-Mail der zweiten Person (leer lassen, falls keine): " VIEWER
  ALLOWED="${ADMIN}:admin"
  [ -n "$VIEWER" ] && ALLOWED="${ALLOWED},${VIEWER}:viewer"
  printf '%s' "$ALLOWED" | gcloud secrets create bicc-allowed-users --data-file=- 2>/dev/null || \
    printf '%s' "$ALLOWED" | gcloud secrets versions add bicc-allowed-users --data-file=-
fi

# ---------------------------------------------------------------- 4. Google-Login
step "4/9  Google-Login (OAuth) verbinden"
if gcloud secrets describe bicc-streamlit-secrets >/dev/null 2>&1; then
  read -rp "Google-Login ist bereits eingerichtet. Neu eingeben? [j/N] " REDO
else
  REDO="j"
fi
if [[ "$REDO" =~ ^[jJyY] ]]; then
  echo
  echo "Bitte jetzt im Browser die OAuth-Client-ID anlegen (Anleitung Schritt 4)."
  echo "Als 'Autorisierte Weiterleitungs-URI' GENAU diese Adresse eintragen:"
  echo
  echo "    $REDIRECT_URI"
  echo
  read -rp "Client-ID einfügen: " CLIENT_ID
  read -rsp "Clientschlüssel (Client Secret) einfügen (Eingabe unsichtbar): " CLIENT_SECRET; echo
  [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ] && fail "Client-ID oder Clientschlüssel fehlt"
  COOKIE="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
  TMPF="$(mktemp)"
  cat > "$TMPF" <<EOF
[auth]
redirect_uri = "${REDIRECT_URI}"
cookie_secret = "${COOKIE}"
client_id = "${CLIENT_ID}"
client_secret = "${CLIENT_SECRET}"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
EOF
  gcloud secrets create bicc-streamlit-secrets --data-file="$TMPF" 2>/dev/null || \
    gcloud secrets versions add bicc-streamlit-secrets --data-file="$TMPF" || { rm -f "$TMPF"; fail "Secret Google-Login"; }
  rm -f "$TMPF"
fi

# ---------------------------------------------------------------- 5. Datenbank
step "5/9  Datenbank anlegen (beim ersten Mal 5–15 Minuten – bitte warten)"
if ! gcloud sql instances describe "$DB_INSTANCE" >/dev/null 2>&1; then
  gcloud sql instances create "$DB_INSTANCE" --database-version=POSTGRES_16 --edition=ENTERPRISE \
    --tier=db-f1-micro --region="$REGION" --storage-size=10GB --backup-start-time=02:00 \
    --retained-backups-count=14 || fail "Datenbank konnte nicht angelegt werden"
fi
gcloud sql databases describe "$DB_NAME" --instance="$DB_INSTANCE" >/dev/null 2>&1 || \
  gcloud sql databases create "$DB_NAME" --instance="$DB_INSTANCE" || fail "Datenbank"
CONN="$(gcloud sql instances describe "$DB_INSTANCE" --format='value(connectionName)')"
if ! gcloud secrets describe bicc-database-url >/dev/null 2>&1; then
  DB_PASS="$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')"
  gcloud sql users create "$DB_USER" --instance="$DB_INSTANCE" --password="$DB_PASS" 2>/dev/null || \
    gcloud sql users set-password "$DB_USER" --instance="$DB_INSTANCE" --password="$DB_PASS" || fail "DB-Benutzer"
  printf '%s' "postgresql+psycopg2://${DB_USER}:${DB_PASS}@/${DB_NAME}?host=/cloudsql/${CONN}" | \
    gcloud secrets create bicc-database-url --data-file=- || fail "Secret Datenbank"
fi

# ---------------------------------------------------------------- 6. Container bauen
step "6/9  Anwendung bauen (3–6 Minuten)"
gcloud artifacts repositories describe bicc --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create bicc --repository-format=docker --location="$REGION" || fail "Artifact Registry"
gcloud builds submit --tag "$IMAGE" . || fail "Build fehlgeschlagen"

# ---------------------------------------------------------------- 7. Webanwendung + Job
step "7/9  Dashboard und täglichen Abgleich bereitstellen"
gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" --service-account "$SA_EMAIL" \
  --add-cloudsql-instances "$CONN" \
  --set-secrets "DATABASE_URL=bicc-database-url:latest,BICC_ALLOWED_USERS=bicc-allowed-users:latest,/home/appuser/.streamlit/secrets.toml=bicc-streamlit-secrets:latest" \
  --set-env-vars "BICC_ENV=prod,BICC_SOURCE_MODE=google,BICC_AUTH_MODE=oidc" \
  --allow-unauthenticated --session-affinity --min-instances=0 --max-instances=2 \
  --memory=1Gi --cpu=1 --timeout=3600 --port=8080 || fail "Bereitstellung Dashboard"
# --allow-unauthenticated: Die Anmeldung erfolgt IN der App (Google-Login + Freigabeliste).

gcloud run jobs deploy "$JOB" --image "$IMAGE" --region "$REGION" --service-account "$SA_EMAIL" \
  --set-cloudsql-instances "$CONN" --set-secrets "DATABASE_URL=bicc-database-url:latest" \
  --set-env-vars "BICC_ENV=prod,BICC_SOURCE_MODE=google" \
  --command python --args="-m,bi.sync,--trigger,scheduled" --max-retries 2 --task-timeout 900s --memory 1Gi \
  || fail "Bereitstellung Sync-Job"

# ---------------------------------------------------------------- 8. Zeitplan
step "8/9  Täglichen Abgleich um 06:00 Uhr deutscher Zeit einplanen"
URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB}:run"
if gcloud scheduler jobs describe bicc-daily-sync --location "$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http bicc-daily-sync --location "$REGION" --schedule "0 6 * * *" \
    --time-zone "Europe/Berlin" --uri "$URI" --http-method POST --oauth-service-account-email "$SA_EMAIL" >/dev/null
else
  gcloud scheduler jobs create http bicc-daily-sync --location "$REGION" --schedule "0 6 * * *" \
    --time-zone "Europe/Berlin" --uri "$URI" --http-method POST --oauth-service-account-email "$SA_EMAIL" \
    || fail "Zeitplan"
fi

# ---------------------------------------------------------------- 9. Sheets freigeben + erster Import
step "9/9  Google Sheets freigeben und ersten Import starten"
echo "Bitte JETZT jedes der 4 Google Sheets öffnen → 'Freigeben' → diese Adresse als BETRACHTER hinzufügen"
echo "(Häkchen 'Personen benachrichtigen' entfernen):"
echo
echo "    $SA_EMAIL"
echo
read -rp "Wenn alle 4 Sheets freigegeben sind, Enter drücken … " _
gcloud run jobs execute "$JOB" --region "$REGION" --wait && OK=1 || OK=0

echo
echo "════════════════════════════════════════════════════════════════════"
if [ "$OK" = "1" ]; then
  echo " ✔ FERTIG – Daten wurden importiert."
else
  echo " ⚠ Einrichtung fertig, aber der erste Import meldet einen Fehler."
  echo "   Meist fehlt eine Sheet-Freigabe. Freigabe prüfen und dann:"
  echo "   gcloud run jobs execute $JOB --region $REGION --wait"
fi
echo
echo " Ihr Dashboard:  $APP_URL"
echo " (Als Lesezeichen speichern. Anmeldung mit Ihrem Google-Konto.)"
echo "════════════════════════════════════════════════════════════════════"

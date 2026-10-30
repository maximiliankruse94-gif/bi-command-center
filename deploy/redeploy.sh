#!/usr/bin/env bash
# Neue Version ausrollen (nach Code-Änderungen). Ausführen in der Cloud Shell im Repo-Ordner.
set -euo pipefail
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"; REGION="europe-west3"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/bicc/app:latest"
gcloud config set project "$PROJECT_ID"
gcloud builds submit --tag "$IMAGE" .
gcloud run deploy bi-command-center --image "$IMAGE" --region "$REGION"
gcloud run jobs update bi-sync --image "$IMAGE" --region "$REGION" 2>/dev/null || true   # nur in der Standard-Variante vorhanden
echo "Neue Version ist live."

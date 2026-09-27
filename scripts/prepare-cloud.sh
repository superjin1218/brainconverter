#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
source .deploy.env
set +a
: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .deploy.env}"
: "${GCP_REGION:?Set GCP_REGION}"
command -v gcloud >/dev/null

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iam.googleapis.com --project "$GCP_PROJECT_ID"
if ! gcloud artifacts repositories describe brain-alpha --location "$GCP_REGION" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud artifacts repositories create brain-alpha --repository-format docker --location "$GCP_REGION" --project "$GCP_PROJECT_ID"
fi
runtime_sa="brain-alpha-runtime@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$runtime_sa" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create brain-alpha-runtime --project "$GCP_PROJECT_ID"
fi
for secret_name in OPENAI_API_KEY GATEWAY_SHARED_SECRET; do
  if ! gcloud secrets describe "$secret_name" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$secret_name" --replication-policy automatic --project "$GCP_PROJECT_ID"
  fi
  gcloud secrets add-iam-policy-binding "$secret_name" --project "$GCP_PROJECT_ID" \
    --member "serviceAccount:${runtime_sa}" --role roles/secretmanager.secretAccessor >/dev/null
done
if ! gcloud secrets versions describe latest --secret GATEWAY_SHARED_SECRET --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
  openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add GATEWAY_SHARED_SECRET --data-file=- --project "$GCP_PROJECT_ID"
fi
echo 'Cloud resources prepared. Add an OPENAI_API_KEY version in Secret Manager, then run scripts/deploy.sh.'

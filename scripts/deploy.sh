#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
source .deploy.env
set +a
for name in GCP_PROJECT_ID GCP_REGION GCP_SERVICE CLOUDFLARE_ACCOUNT_ID ACCESS_TEAM_DOMAIN ACCESS_AUD ALLOWED_EMAILS; do
  if [[ -z "${!name:-}" ]]; then echo "Missing setting: $name" >&2; exit 1; fi
done
command -v gcloud >/dev/null
node -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(1)'
gcloud secrets versions describe latest --secret OPENAI_API_KEY --project "$GCP_PROJECT_ID" >/dev/null
gcloud secrets versions describe latest --secret GATEWAY_SHARED_SECRET --project "$GCP_PROJECT_ID" >/dev/null
make test lint
npm --prefix gateway ci
npm --prefix gateway run check
npm --prefix gateway test
image_tag="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/brain-alpha/harness:$(git rev-parse --short HEAD)-$(date +%s)"
gcloud builds submit --project "$GCP_PROJECT_ID" --tag "$image_tag" .
gcloud run deploy "$GCP_SERVICE" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --image "$image_tag" --allow-unauthenticated --min 0 --max 2 --concurrency 2 \
  --timeout 65 --memory 512Mi --cpu 1 --cpu-throttling \
  --service-account "brain-alpha-runtime@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars 'APP_ENV=production,HARNESS_PROVIDER=openai,OPENAI_MODEL=gpt-5-mini,MAX_CONCURRENT_JOBS=2,MODEL_TIMEOUT_SECONDS=40' \
  --set-secrets 'OPENAI_API_KEY=OPENAI_API_KEY:latest,GATEWAY_SHARED_SECRET=GATEWAY_SHARED_SECRET:latest'
export BACKEND_URL
BACKEND_URL="$(gcloud run services describe "$GCP_SERVICE" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --format='value(status.url)')"
# Pipe secret material directly to Wrangler; never echo it or write it to a tracked file.
# First create the Worker with missing configuration; it fails closed with 503.
npm --prefix gateway run deploy
python3 scripts/gateway-secrets.py
echo 'Deployment finished. Configure Cloudflare Access on the Worker hostname before inviting members.'

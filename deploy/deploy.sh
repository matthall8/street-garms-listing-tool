#!/usr/bin/env bash
# Build the image locally, push it to Artifact Registry and deploy it to Cloud
# Run by digest. Procedure and one-off setup: deploy/README.md.
#
# Usage: deploy/deploy.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# --- Config (deploy/config.env, gitignored) ----------------------------------

CONFIG=deploy/config.env
[ -f "$CONFIG" ] || { echo "missing $CONFIG: copy deploy/config.example.env" >&2; exit 1; }
set -a; . "$CONFIG"; set +a

for var in PROJECT_ID REGION AR_REPO IAP_MEMBERS; do
  value="${!var:-}"
  if [ -z "$value" ] || [[ "$value" == *FILL-ME* ]] || [[ "$value" == your-* ]]; then
    echo "$var is not set in $CONFIG" >&2
    exit 1
  fi
done

# --- Fixed settings (tracked, so every change is a commit) -------------------

SERVICE=listing-tool
IMAGE_NAME=listing-tool
RUNTIME_SA="listing-tool-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_NAME=anthropic-api-key
SECRET_VERSION=1          # pinned, never "latest" (decision 4)
MEMORY=1Gi                # decision 6
TIMEOUT=900               # decision 7
CONCURRENCY=1             # decision 7
MAX_INSTANCES=3           # decision 7
MIN_INSTANCES=0           # decision 9

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"

# --- Helpers -----------------------------------------------------------------

# Hide email addresses: gcloud's errors name the signed-in account.
mask() { sed -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+/<email>/g'; }

# Run gcloud with no prompts (a prompt would hang the script) and masked output.
# Exits with gcloud's status, not sed's.
run_gcloud() {
  local status=0
  gcloud --quiet --project "$PROJECT_ID" "$@" </dev/null 2> >(mask >&2) | mask || status=$?
  return "$status"
}

step() { printf '\n== %s\n' "$*"; }

# --- Steps -------------------------------------------------------------------

# Refuse a dirty tree (decision 2), untracked files included: the build sends
# app/ and labels/ from disk, so an untracked file there would reach the image
# without being in the commit the image is tagged with. deploy/config.env is
# ignored, so it doesn't count.
require_clean_tree() {
  if [ -n "$(git status --porcelain)" ]; then
    echo "working tree is not clean; commit or stash first:" >&2
    git status --short >&2
    exit 1
  fi
  COMMIT="$(git rev-parse HEAD)"
  IMAGE="${REGISTRY}/${IMAGE_NAME}:${COMMIT}"
  echo "commit $COMMIT"
}

# Digest of the image tagged with this commit, or empty if there is none yet.
registry_digest() {
  run_gcloud artifacts docker images describe "$IMAGE" \
    --format='value(image_summary.digest)' 2>/dev/null || true
}

# Build and push unless this commit's image is already in the registry. Tags
# are immutable, and rebuilding the same commit gives a different digest, so
# the image already pushed for this commit is the one to deploy.
build_and_push() {
  DIGEST="$(registry_digest)"
  if [ -n "$DIGEST" ]; then
    echo "image for this commit already pushed; reusing it"
  else
    docker info >/dev/null 2>&1 || { echo "Docker isn't running" >&2; exit 1; }
    docker build --platform linux/amd64 -t "$IMAGE" .
    docker push "$IMAGE"
    DIGEST="$(registry_digest)"
  fi
  if ! [[ "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "couldn't read the pushed image's digest from the registry" >&2
    exit 1
  fi
  echo "digest $DIGEST"
}

deploy_service() {
  run_gcloud run deploy "$SERVICE" \
    --region "$REGION" \
    --image "${REGISTRY}/${IMAGE_NAME}@${DIGEST}" \
    --no-allow-unauthenticated \
    --iap \
    --service-account "$RUNTIME_SA" \
    --set-secrets "ANTHROPIC_API_KEY=${SECRET_NAME}:${SECRET_VERSION}" \
    --memory "$MEMORY" \
    --timeout "$TIMEOUT" \
    --concurrency "$CONCURRENCY" \
    --max-instances "$MAX_INSTANCES" \
    --min-instances "$MIN_INSTANCES"
}

# Grant IAP access to each member in config.env. Adds only: removing someone
# is a console or remove-iam-policy-binding step (deploy/README.md).
grant_iap_access() {
  local member
  for member in $IAP_MEMBERS; do
    run_gcloud iap web add-iam-policy-binding \
      --resource-type=cloud-run --service="$SERVICE" --region="$REGION" \
      --member="$member" --role=roles/iap.httpsResourceAccessor >/dev/null
  done
  echo "IAP access granted to $(echo $IAP_MEMBERS | wc -w | tr -d ' ') member(s)"
}

# A request with no sign-in must be redirected to Google sign-in. A 502 means
# the service has no OAuth client yet (deploy/README.md, step 4).
check_iap() {
  local url code
  url="$(run_gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
  code="$(curl -s -o /dev/null -w '%{http_code}' "$url/")"
  echo "service URL: $url"
  if [ "$code" = 302 ]; then
    echo "unauthenticated request: 302 to sign-in (IAP is working)"
  else
    echo "unauthenticated request: $code, expected 302. See deploy/README.md, step 4." >&2
    exit 1
  fi
}

main() {
  step "Checking working tree";   require_clean_tree
  step "Image";                   build_and_push
  step "Deploying $SERVICE";      deploy_service
  # Check before granting: in a project with no organisation, users can only
  # be added once the OAuth client exists.
  step "Checking IAP";            check_iap
  step "IAP access";              grant_iap_access
  step "Done. Run deploy/read-back.sh to check the settings."
}

main "$@"

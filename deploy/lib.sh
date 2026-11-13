# Shared by deploy.sh and read-back.sh: config, fixed settings and helpers.
# Sourced, not run. One home for the settings, so the read-back checks the
# same values the deploy sets.

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
RUNTIME_SA_ID=listing-tool-runtime
RUNTIME_SA="${RUNTIME_SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_NAME=anthropic-api-key
SECRET_ENV=ANTHROPIC_API_KEY
SECRET_VERSION=1          # pinned, never "latest": a key rotation is a redeploy
MEMORY=1Gi                # one read of a 3 MB photo measured about 365 MiB
TIMEOUT=900               # above the worst-case model call, about 600s
CONCURRENCY=1             # one read per instance
MAX_INSTANCES=3           # two abandoned reads don't block a third upload
MIN_INSTANCES=0           # scale to zero; cold start measured after deploy
LOG_RETENTION_DAYS=30     # ADR-0009, What's held where

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

# As run_gcloud, but stdout is left unmasked, for output that goes straight to
# a parser which prints only the fields it picks. Never print its output raw.
run_gcloud_for_parser() {
  gcloud --quiet --project "$PROJECT_ID" "$@" </dev/null 2> >(mask >&2)
}

step() { printf '\n== %s\n' "$*"; }

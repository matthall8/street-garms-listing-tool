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
  if [ -z "$value" ] || [[ "$value" == *FILL-ME* ]] || [[ "$value" == your-* ]] \
    || [[ "$value" == *@example.com* ]]; then
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
MEMORY=1Gi                # measured peaks: evals/BASELINES.md, Deploy measurements
TIMEOUT=900               # above the worst-case model call, about 600s
CONCURRENCY=1             # one read per instance
MAX_INSTANCES=3           # two abandoned reads don't block a third upload
MIN_INSTANCES=0           # scale to zero; cold start measured after deploy
LOG_RETENTION_DAYS=30     # ADR-0009, What's held where

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"

# Cloud SQL and the photo bucket (ADR-0008, D6). Names derive from PROJECT_ID,
# so no project value is tracked; the bucket name must be globally unique.
SQL_INSTANCE="${PROJECT_ID}-pg"
SQL_CONNECTION="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
SQL_EDITION=ENTERPRISE
SQL_TIER=db-f1-micro      # about 60 rows, at most MAX_INSTANCES connections
SQL_BACKUPS_RETAINED=7
SQL_LOG_DAYS=7            # point-in-time recovery; the Enterprise maximum
DB_NAME=listing_tool
DB_USER="${RUNTIME_SA_ID}@${PROJECT_ID}.iam"  # IAM database user: the account's email, less .gserviceaccount.com
PHOTO_BUCKET="${PROJECT_ID}-photos"
SOFT_DELETE_SECONDS=604800  # the bucket's default soft delete, 7 days, kept

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

# The service's plain environment variables, NAME=value, comma-separated and
# sorted by name. deploy.sh sets exactly these; read-back.sh compares them.
service_env() {
  echo "CLOUD_SQL_INSTANCE=${SQL_CONNECTION},DB_NAME=${DB_NAME},DB_USER=${DB_USER},PHOTO_BUCKET=${PHOTO_BUCKET},SHEET_ID=${SHEET_ID},SHEET_TAB_ID=${SHEET_TAB_ID}"
}

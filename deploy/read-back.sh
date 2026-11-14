#!/usr/bin/env bash
# Read the deployed service's settings back from Google Cloud and compare them
# with the fixed settings in deploy/lib.sh. Exits 1 if any check fails.
# Read-only, and prints no email addresses. Procedure: deploy/README.md.
#
# Usage: deploy/read-back.sh
set -euo pipefail

# shellcheck source=deploy/lib.sh
. "$(dirname "$0")/lib.sh"

FAILED=0

# check NAME EXPECTED ACTUAL [SHOWN]: SHOWN is printed instead of ACTUAL.
check() {
  local shown="${4:-$3}"
  if [ "$2" = "$3" ]; then
    printf '  ok    %-24s %s\n' "$1" "$shown"
  else
    printf '  FAIL  %-24s expected %s, got %s\n' "$1" "$2" "${shown:-<none>}"
    FAILED=1
  fi
}

# --- Service configuration ---------------------------------------------------

step "Service $SERVICE"
# One describe, flattened to shell assignments by Python (bash 3.2 has no
# associative arrays). Every value is quoted with shlex before eval. The JSON
# also names people (creator, last modifier); only the fields below leave it,
# and the service account only as its ID.
eval "$(run_gcloud_for_parser run services describe "$SERVICE" --region "$REGION" --format=json | python3 -c '
import json, shlex, sys
env_name, project = sys.argv[1], sys.argv[2]
s = json.load(sys.stdin)
meta, status = s["metadata"], s["status"]
t = s["spec"]["template"]
c = t["spec"]["containers"][0]
ann = t["metadata"].get("annotations", {})
secret = ""
plain = []
for e in c.get("env", []):
    ref = e.get("valueFrom", {}).get("secretKeyRef")
    if e["name"] == env_name and ref:
        secret = ref["name"] + ":" + ref["key"]
    if "value" in e:
        plain.append(e["name"] + "=" + e["value"])
traffic = status.get("traffic", [])
serving = len(traffic) == 1 and traffic[0].get("latestRevision") and traffic[0].get("percent") == 100
ready = status.get("latestReadyRevisionName") == status.get("latestCreatedRevisionName")
out = {
    "S_REGION": meta["labels"].get("cloud.googleapis.com/location", ""),
    "S_IAP": meta["annotations"].get("run.googleapis.com/iap-enabled", "false"),
    "S_TIMEOUT": str(t["spec"].get("timeoutSeconds", "")),
    "S_CONCURRENCY": str(t["spec"].get("containerConcurrency", "")),
    "S_MAX": ann.get("autoscaling.knative.dev/maxScale", ""),
    "S_MIN": ann.get("autoscaling.knative.dev/minScale", "0"),  # absent means 0
    "S_MEMORY": c.get("resources", {}).get("limits", {}).get("memory", ""),
    "S_SA_ID": t["spec"].get("serviceAccountName", "").partition("@")[0],
    "S_SA_IN_PROJECT": "yes" if t["spec"].get("serviceAccountName", "").endswith(
        "@" + project + ".iam.gserviceaccount.com") else "no",
    "S_SECRET": secret,
    "S_ENV": ",".join(sorted(plain)),
    "S_IMAGE": c["image"],
    "S_REVISION_OK": "yes" if (ready and serving) else "no",
    "S_URL": status.get("url", ""),
}
for k, v in out.items():
    print(f"{k}={shlex.quote(v)}")
' "$SECRET_ENV" "$PROJECT_ID")"

check "region"            "$REGION"         "$S_REGION"
check "IAP"               "true"            "$S_IAP"
check "request timeout"   "$TIMEOUT"        "$S_TIMEOUT"
check "concurrency"       "$CONCURRENCY"    "$S_CONCURRENCY"
check "max instances"     "$MAX_INSTANCES"  "$S_MAX"
check "min instances"     "$MIN_INSTANCES"  "$S_MIN"
check "memory"            "$MEMORY"         "$S_MEMORY"
check "service account"   "$RUNTIME_SA_ID"  "$S_SA_ID"
check "  in this project" "yes"             "$S_SA_IN_PROJECT"
check "secret (pinned)"   "${SECRET_NAME}:${SECRET_VERSION}" "$S_SECRET"
# The values name the project and the runtime account, so only the verdict
# is printed.
check "env (database, bucket)" "as lib.sh" \
  "$([ "$S_ENV" = "$(service_env)" ] && echo 'as lib.sh' || echo 'differs from lib.sh')"
check "latest revision serving" "yes"       "$S_REVISION_OK"

# --- Image -------------------------------------------------------------------

step "Image"
image_repo="${S_IMAGE%@*}"
digest="${S_IMAGE##*@}"
check "deployed by digest" "yes" "$([[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] && echo yes || echo no)"
check "image repository"   "${REGISTRY}/${IMAGE_NAME}" "$image_repo" "${IMAGE_NAME}"

# The commit tag on the deployed digest, and the digest that tag points to.
tag="$(run_gcloud artifacts docker images list "${REGISTRY}/${IMAGE_NAME}" --include-tags \
  --filter="version=${digest}" --format='value(tags)' 2>/dev/null | head -1)"
tagged_digest=""
if [ -n "$tag" ]; then
  tagged_digest="$(run_gcloud artifacts docker images describe "${REGISTRY}/${IMAGE_NAME}:${tag}" \
    --format='value(image_summary.digest)' 2>/dev/null || true)"
fi
check "digest = pushed tag"  "$digest" "$tagged_digest" "${digest:0:19}… tagged ${tag:-<none>}"
if [ -n "$tag" ] && [ "$tag" != "$(git rev-parse HEAD)" ]; then
  echo "  note  deployed commit is not HEAD ($(git rev-parse --short HEAD))"
fi

# --- IAP ---------------------------------------------------------------------

step "IAP"
read -r code redirect < <(curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' "${S_URL}/")
redirect_host="$(printf '%s' "$redirect" | sed -E 's#^(https://[^/]+).*#\1#')"
check "no sign-in: status"   "302" "$code"
check "no sign-in: redirect" "https://accounts.google.com" "$redirect_host"

# --- Cloud SQL ---------------------------------------------------------------

step "Cloud SQL instance"
# As for the service: one describe, only the fields below leave the parser.
# The JSON also holds the instance's own service account email.
eval "$(run_gcloud_for_parser sql instances describe "$SQL_INSTANCE" --format=json | python3 -c '
import json, shlex, sys
i = json.load(sys.stdin)
s = i["settings"]
ip = s.get("ipConfiguration", {})
b = s.get("backupConfiguration", {})
flags = {f["name"]: f.get("value", "") for f in s.get("databaseFlags", [])}
tf = lambda x: "true" if x else "false"
out = {
    "Q_REGION": i.get("region", ""),
    "Q_EDITION": s.get("edition", ""),
    "Q_TIER": s.get("tier", ""),
    "Q_DELETION": tf(s.get("deletionProtectionEnabled")),
    "Q_PUBLIC_IP": tf(ip.get("ipv4Enabled")),
    "Q_PRIVATE_IP": tf(ip.get("privateNetwork")),
    "Q_NETWORKS": str(len(ip.get("authorizedNetworks", []))),
    "Q_CONNECTOR": s.get("connectorEnforcement", ""),
    "Q_IAM_AUTH": flags.get("cloudsql.iam_authentication", ""),
    "Q_BACKUPS": tf(b.get("enabled")),
    "Q_PITR": tf(b.get("pointInTimeRecoveryEnabled")),
    "Q_RETAINED": str(b.get("backupRetentionSettings", {}).get("retainedBackups", "")),
    "Q_LOG_DAYS": str(b.get("transactionLogRetentionDays", "")),
    "Q_BACKUP_LOCATION": b.get("location", ""),
    "Q_RETAIN_ON_DELETE": tf(s.get("retainBackupsOnDelete")),
    "Q_FINAL_BACKUP": tf(s.get("finalBackupConfig", {}).get("enabled")),
}
for k, v in out.items():
    print(f"{k}={shlex.quote(v)}")
')"

check "region"                   "$REGION"               "$Q_REGION"
check "edition"                  "$SQL_EDITION"          "$Q_EDITION"
check "tier"                     "$SQL_TIER"             "$Q_TIER"
check "deletion protection"      "true"                  "$Q_DELETION"
check "public IP"                "true"                  "$Q_PUBLIC_IP"
check "private IP"               "false"                 "$Q_PRIVATE_IP"
check "authorised networks"      "0"                     "$Q_NETWORKS"
check "connector enforcement"    "REQUIRED"              "$Q_CONNECTOR"
check "IAM authentication flag"  "on"                    "$Q_IAM_AUTH"
check "automated backups"        "true"                  "$Q_BACKUPS"
check "point-in-time recovery"   "true"                  "$Q_PITR"
check "backups retained"         "$SQL_BACKUPS_RETAINED" "$Q_RETAINED"
check "days of logs"             "$SQL_LOG_DAYS"         "$Q_LOG_DAYS"
# ADR-0009: D6 for where backups sit, D1 for none outliving the instance.
check "backup location"          "$REGION"               "$Q_BACKUP_LOCATION"
check "retain backups on delete" "false"                 "$Q_RETAIN_ON_DELETE"
check "final backup on delete"   "false"                 "$Q_FINAL_BACKUP"

step "Database and users"
dbs="$(run_gcloud sql databases list --instance "$SQL_INSTANCE" --format='value(name)')"
check "database $DB_NAME" "present" "$(grep -qx "$DB_NAME" <<<"$dbs" && echo present || echo missing)"

# IAM usernames are email addresses: only counts and verdicts leave the parser.
eval "$(run_gcloud_for_parser sql users list --instance "$SQL_INSTANCE" --format=json | python3 -c '
import json, shlex, sys
db_user = sys.argv[1]
users = json.load(sys.stdin)
kind = lambda u: u.get("type") or "BUILT_IN"
out = {
    "U_BUILT_IN": ",".join(sorted(u["name"] for u in users if kind(u) == "BUILT_IN")),
    "U_IAM_USERS": str(sum(kind(u) == "CLOUD_IAM_USER" for u in users)),
    "U_IAM_SAS": str(sum(kind(u) == "CLOUD_IAM_SERVICE_ACCOUNT" for u in users)),
    "U_OTHER": str(sum(kind(u) not in ("BUILT_IN", "CLOUD_IAM_USER", "CLOUD_IAM_SERVICE_ACCOUNT") for u in users)),
    "U_RUNTIME": "yes" if any(u["name"] == db_user and kind(u) == "CLOUD_IAM_SERVICE_ACCOUNT" for u in users) else "no",
}
for k, v in out.items():
    print(f"{k}={shlex.quote(v)}")
' "$DB_USER")"
# users list doesn't return database roles; users describe does.
runtime_roles="$(run_gcloud sql users describe "$DB_USER" --instance "$SQL_INSTANCE" \
  --format='value(databaseRoles)' 2>/dev/null || echo '<unreadable>')"

check "built-in users"           "postgres" "$U_BUILT_IN"
check "IAM users"                "1"        "$U_IAM_USERS" "$U_IAM_USERS (the developer)"
check "IAM service accounts"     "1"        "$U_IAM_SAS"
check "  the runtime account"    "yes"      "$U_RUNTIME"
check "  its database roles"     "none"     "${runtime_roles:-none}"
check "other user types"         "0"        "$U_OTHER"

# --- Bucket ------------------------------------------------------------------

step "Bucket"
eval "$(run_gcloud_for_parser storage buckets describe "gs://${PHOTO_BUCKET}" --format=json | python3 -c '
import json, shlex, sys
b = json.load(sys.stdin)
tf = lambda x: "true" if x else "false"
out = {
    "B_LOCATION": b.get("location", "").lower(),
    "B_LOCATION_TYPE": b.get("location_type", ""),
    "B_PAP": b.get("public_access_prevention", ""),
    "B_UNIFORM": tf(b.get("uniform_bucket_level_access")),
    "B_VERSIONING": tf(b.get("versioning_enabled")),
    "B_SOFT_DELETE": str(b.get("soft_delete_policy", {}).get("retentionDurationSeconds", "")),
}
for k, v in out.items():
    print(f"{k}={shlex.quote(v)}")
')"

check "location"                 "$REGION"              "$B_LOCATION"
check "location type"            "region"               "$B_LOCATION_TYPE"
check "public access prevention" "enforced"             "$B_PAP"
check "uniform access"           "true"                 "$B_UNIFORM"
check "object versioning"        "false"                "$B_VERSIONING"
check "soft delete (seconds)"    "$SOFT_DELETE_SECONDS" "$B_SOFT_DELETE"

# --- Runtime account's roles -------------------------------------------------

step "Runtime account's roles"
# Roles the runtime account holds in an IAM policy read from stdin, sorted and
# comma-separated. Only role names leave the policy; members are never printed.
sa_roles() {
  python3 -c '
import json, sys
member = "serviceAccount:" + sys.argv[1]
roles = sorted(
    b["role"] + (" (conditional)" if b.get("condition") else "")
    for b in json.load(sys.stdin).get("bindings", [])
    if member in b.get("members", [])
)
print(",".join(roles))
' "$RUNTIME_SA"
}

# Exactly these and no others: ADR-0008 amendment and deploy/README.md, steps
# 7 and 11. The two Cloud SQL roles are on the project because Cloud SQL
# grants login only there.
check "project" "roles/cloudsql.client,roles/cloudsql.instanceUser" \
  "$(run_gcloud_for_parser projects get-iam-policy "$PROJECT_ID" --format=json | sa_roles)"
check "bucket"  "roles/storage.objectCreator" \
  "$(run_gcloud_for_parser storage buckets get-iam-policy "gs://${PHOTO_BUCKET}" --format=json | sa_roles)"
check "secret"  "roles/secretmanager.secretAccessor" \
  "$(run_gcloud_for_parser secrets get-iam-policy "$SECRET_NAME" --format=json | sa_roles)"

# --- Logs --------------------------------------------------------------------

step "Logs"
retention="$(run_gcloud logging buckets describe _Default --location=global \
  --format='value(retentionDays)')"
check "log retention (days)" "$LOG_RETENTION_DAYS" "$retention"

# IAP's access logs are Data Access audit logs: off means no audit config for
# IAP or for allServices. Only auditConfigs is read; bindings name people.
audit="$(run_gcloud projects get-iam-policy "$PROJECT_ID" --format=json | python3 -c '
import json, sys
cfgs = json.load(sys.stdin).get("auditConfigs", [])
on = [c["service"] for c in cfgs if c.get("service") in ("iap.googleapis.com", "allServices")]
print("on: " + ", ".join(on) if on else "off")
')"
check "IAP Data Access logs" "off" "$audit"

# --- Result ------------------------------------------------------------------

step "Result"
echo "  service URL: $S_URL"
if [ "${SERVICE_URL:-}" != "$S_URL" ]; then
  echo "  note  SERVICE_URL in $CONFIG differs from the service's URL"
fi
if [ "$FAILED" -ne 0 ]; then
  echo "  some checks FAILED" >&2
  exit 1
fi
echo "  all checks passed"

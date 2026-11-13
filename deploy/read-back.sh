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
for e in c.get("env", []):
    ref = e.get("valueFrom", {}).get("secretKeyRef")
    if e["name"] == env_name and ref:
        secret = ref["name"] + ":" + ref["key"]
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

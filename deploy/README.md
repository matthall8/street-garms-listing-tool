# Deploy

The Python service runs on Cloud Run in `europe-west2`, behind IAP. Why it is
built this way is in [ADR-0008](../adr/0008-phase-2-architecture.md), D1, and
[ADR-0009](../adr/0009-trial-data-and-privacy.md), D1 and D6. This file is the
procedure: the one-off console steps, in the order they were done.

## Config

Every command reads its values from `deploy/config.env`, which is gitignored.
Copy [`config.example.env`](config.example.env) and fill it in. Nothing in this
file names the project, the service URL or anyone's account: use the variables.

```
set -a; . deploy/config.env; set +a
```

Pass `--project "$PROJECT_ID"` to every `gcloud` command. Don't rely on
`gcloud`'s global default project.

## One-off project setup

### 1. Project

A dedicated project for the trial, owned and billed by Street Garms, with **no
parent organisation**. Keep it that way: roles granted on an organisation
are inherited by every project in it, which would break ADR-0009, D1 (only the
developer reaches the technical stores). Access is whoever holds roles on the
project itself, on its IAM page.

Check:

```
gcloud projects describe "$PROJECT_ID"            # lifecycleState: ACTIVE, no parent
gcloud billing projects describe "$PROJECT_ID"    # billingEnabled: true
```

Sign in with `gcloud auth login` only. Application default credentials are not
needed: nothing here calls a Google client library from the Mac.

### 2. APIs

Enabled in the console, *APIs & Services → Library*:

| API | service name |
|---|---|
| Cloud Run Admin | `run.googleapis.com` |
| Artifact Registry | `artifactregistry.googleapis.com` |
| Cloud Identity-Aware Proxy | `iap.googleapis.com` |
| Secret Manager | `secretmanager.googleapis.com` |
| Identity and Access Management (IAM) | `iam.googleapis.com` |
| Cloud Resource Manager | `cloudresourcemanager.googleapis.com` |
| Cloud Logging | `logging.googleapis.com` |
| Cloud Monitoring | `monitoring.googleapis.com` |

Cloud Resource Manager is easy to miss: `gcloud iap web get-iam-policy` and
similar commands need it, and without it `gcloud` stops at a prompt to enable
it. Not needed: Container Scanning (scanning is off) and Cloud Billing Budget
(the budget alert is set in the console).

Check: `gcloud services list --enabled --project "$PROJECT_ID"`.

### 3. Artifact Registry

One Docker repository, `$AR_REPO`, created in the console:

| setting | value | why |
|---|---|---|
| format, mode | Docker, Standard | we push our own images |
| location | region `europe-west2` | ADR-0009, D6 |
| encryption | Google-managed key | |
| immutable image tags | **enabled** | a commit's tag can never point at another image |
| cleanup policies | none | never delete the running or rollback image |
| platform logs | inherited (off) | |
| vulnerability scanning | disabled | |

Check: `gcloud artifacts repositories describe "$AR_REPO" --project "$PROJECT_ID" --location europe-west2`
shows `immutableTags: true` and no cleanup policy.

Once per Mac, let Docker push with `gcloud`'s credentials:
`gcloud auth configure-docker europe-west2-docker.pkg.dev`.

**Deleting an image:** immutable tags also block deleting a tagged image. Switch
*Immutable image tags* to Disabled (repository → Edit), delete, then switch it
back to Enabled and check it reads back `true`.

A push from `docker build` uploads an image index plus untagged entries.
Deploy by the index digest, the one `docker push` prints.

### 4. IAP in a project with no organisation

IAP's default, Google-managed OAuth client only admits users inside an
organisation, and `gcloud` can't create an OAuth client. So the first IAP
setup is in the console. Until it's done, a deploy with `--iap` succeeds but
every request gets a 502, `Empty Google Account OAuth client ID(s)/secret(s)`.

1. *Google Auth Platform → Branding → Get started*: app name, support and
   contact email, audience **External**.
2. *Security → Identity-Aware Proxy → Applications*, the service's row,
   *⋮ → Settings → Custom OAuth → Auto Generate Credentials → Save*.
3. Add principals in the service's *Security → IAP → Edit policy* dialog. The
   developer only until **mvp-cutover** (`TODO.md`).

The client is attached at the level you generate it from. Generated from a
service's settings, it belongs to that service and is lost when the service is
deleted. A client set at the project level applies to every service.

If you download the credentials, the file holds the client secret. Keep it
outside the repo and never paste it anywhere.

Check: an unauthenticated `curl -s -o /dev/null -w '%{http_code}' "$SERVICE_URL"`
returns `302`, redirecting to `accounts.google.com`.

## Running `gcloud` from a script

- Pass `--quiet` and give it no stdin (`</dev/null`). Otherwise a prompt, such
  as one to enable an API, hangs the script instead of failing it.
- `gcloud`'s error messages include the signed-in account's email. Filter its
  stderr as well as the script's own output.

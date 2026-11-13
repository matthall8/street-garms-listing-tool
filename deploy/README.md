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
organisation, and `gcloud` can't create an OAuth client. So the project needs
its own client, set once at the **project level**, which every service
inherits. Without one, a deploy with `--iap` succeeds but every request gets
a 502, `Empty Google Account OAuth client ID(s)/secret(s)`.

1. *Google Auth Platform → Branding → Get started*: app name, support and
   contact email, audience **External**.
2. Get a client: on any IAP-enabled service, *Security → Identity-Aware Proxy
   → Applications*, the service's row, *⋮ → Settings → Custom OAuth → Auto
   Generate Credentials*, then *Download credentials*. The client stays in
   *Google Auth Platform → Clients* (check the project selector).
3. Set it at the project level, in your own terminal, never through an agent.
   Write a settings file **outside the repo** from the downloaded JSON's
   `web.client_id` and `web.client_secret`:

   ```yaml
   accessSettings:
     oauthSettings:
       clientId: <client_id>
       clientSecret: <client_secret>
   ```

   then `gcloud iap settings set <that file> --project "$PROJECT_ID"`, with
   no `--resource-type`. `--project` must not be empty: an empty one fails
   with `Could not parse IAP settings resource`. The command echoes the
   secret, so clear the terminal. Then delete both files.

A client generated from one service's settings and never set at the project
level stays attached to that service only.

`deploy.sh` grants IAP access to `IAP_MEMBERS` after it checks sign-in works:
the developer only until **mvp-cutover** (`TODO.md`).

Check: `gcloud iap settings get --project "$PROJECT_ID"` shows `oauthSettings`
(don't paste its output anywhere), and `read-back.sh` passes its IAP checks.

### 5. Runtime service account

The service runs as a dedicated account, `listing-tool-runtime`, never the
default compute account (historically Editor on the whole project). Its email
is `listing-tool-runtime@$PROJECT_ID.iam.gserviceaccount.com`.

Created in *IAM & Admin → Service accounts* with **no project roles**: skip
the *Grant this service account access to the project* step. Every role it
gets is granted on one resource, never on the project. Never create a key for
it: Cloud Run runs as the account directly. An account ID can't be renamed,
so check the spelling before creating it.

Check: `gcloud projects get-iam-policy "$PROJECT_ID"` lists no binding for it,
and `gcloud iam service-accounts keys list --iam-account <its email> --managed-by=user`
lists nothing.

### 6. Anthropic key

The developer does this, and no agent sees the key (ADR-0009, D5):

1. In the Anthropic console, a workspace for the trial with a **$10 monthly
   spend limit**, and a key in that workspace.
2. In *Security → Secret Manager → Create secret*: name `anthropic-api-key`,
   the key as its value, **replication manual, `europe-west2` only**
   (ADR-0009, D6; replication can't be changed afterwards). No rotation,
   expiry or notifications.

The key lives nowhere else: not in `.env`, not in `config.env`.

The service references a **pinned version number**, never `latest`. Rotating
the key means adding a version, then redeploying with the new number.

Check, without reading the value:
`gcloud secrets describe anthropic-api-key --project "$PROJECT_ID"` shows
`userManaged` replication in `europe-west2` only, and
`gcloud secrets versions list anthropic-api-key --project "$PROJECT_ID"` shows
the pinned version `enabled`.

### 7. Secret access

Secret Accessor on this one secret, never on the project. A project-level
grant would also cover any secret added later:

```
gcloud secrets add-iam-policy-binding anthropic-api-key --project "$PROJECT_ID" \
  --member="serviceAccount:listing-tool-runtime@$PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor
```

Check: `gcloud secrets get-iam-policy anthropic-api-key --project "$PROJECT_ID"`
shows that one binding, and the project policy still shows none for the account.

## Deploy

```
deploy/deploy.sh
```

Deploy from `main`: merge the PR on GitHub, `git switch main && git pull`,
then run it. Only a change to the image (`app/`, `labels/`, `pyproject.toml`,
`uv.lock`) or to `lib.sh` needs a deploy; docs and scripts don't.

It refuses a dirty tree, untracked files included, and any commit not on
`origin/main`, so every image is reviewed, through CI and its commit tag is
on GitHub. It then builds the image
for `linux/amd64`, tags it with the full commit hash and pushes it. If this
commit's image is already in the registry, it reuses it: tags are immutable,
and a rebuild would give a different digest. It deploys by digest, checks that
a request with no sign-in is redirected to Google sign-in, and grants IAP
access to `IAP_MEMBERS` (adds only; remove someone in the console).

The fixed settings (service name, runtime account, pinned secret version,
memory, timeout, concurrency, instances) are in [`lib.sh`](lib.sh), tracked,
so every change is a commit. To rotate the key: add a secret version, change
`SECRET_VERSION`, commit, deploy.

## Read-back

```
deploy/read-back.sh
```

Read-only. Reads the deployed service back and compares it with `lib.sh`:
region, IAP, timeout, concurrency, instances, memory, runtime account, pinned
secret, that the deployed digest is the one its commit tag points to, that a
request with no sign-in is redirected to Google sign-in, log retention, and
that IAP's Data Access logs are off. Exits 1 if any check fails. Run it after
every deploy.

## Running `gcloud` from a script

- Pass `--quiet` and give it no stdin (`</dev/null`). Otherwise a prompt, such
  as one to enable an API, hangs the script instead of failing it.
- `gcloud`'s error messages include the signed-in account's email. Filter its
  stderr as well as the script's own output.

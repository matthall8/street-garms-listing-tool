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
| Cloud SQL Admin | `sqladmin.googleapis.com` |
| Cloud Storage | `storage.googleapis.com` |

Cloud Resource Manager is easy to miss: `gcloud iap web get-iam-policy` and
similar commands need it, and without it `gcloud` stops at a prompt to enable
it. Cloud SQL Admin is needed at runtime as well as for setup: the Cloud SQL
connector calls it for the instance's address and a short-lived client
certificate, and again to refresh the certificate. Not needed: Container Scanning (scanning is off) and Cloud Billing Budget
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
gets is granted on one resource, never on the project, with one exception:
the two Cloud SQL roles in step 11, because Cloud SQL accepts them only on
the project. Never create a key for
it: Cloud Run runs as the account directly. An account ID can't be renamed,
so check the spelling before creating it.

Check: `gcloud projects get-iam-policy "$PROJECT_ID"` lists no binding for it
beyond step 11's, and `gcloud iam service-accounts keys list --iam-account <its email> --managed-by=user`
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
shows that one binding, and the project policy shows none for the account
beyond step 11's.

### 8. Cloud SQL instance

One Postgres instance, `${PROJECT_ID}-pg`, created in the console (*SQL →
Create instance → PostgreSQL*). The console's defaults are a large
production instance in the US, so choose **Enterprise** first, then the
**Sandbox** preset; the shared-core tiers only appear after that.

| setting | value | why |
|---|---|---|
| edition, preset | Enterprise, Sandbox | |
| version | PostgreSQL 18 (default) | |
| region, availability | `europe-west2`, single zone | ADR-0009, D6; an outage is a failed read, which ADR-0007's downtime log covers |
| machine | shared core, `db-f1-micro` | about 60 rows, at most 3 connections |
| storage | 10 GB SSD, automatic increase on | a full disk stops every write; capacity can't shrink |
| `postgres` password | *Generate*, never copied or stored | no credential to keep (ADR-0008, *Amendments*) |
| connections | Public IP, no authorised networks, no private IP | ADR-0008, D6 |
| SSL mode, server CA | SSL only, Google-managed CAS (defaults) | the CA mode can't be changed later |
| automated backups | on, 7 retained, location `europe-west2` | ADR-0009, D6; the console defaults to multi-region `eu` |
| point-in-time recovery | on, 7 days of logs (the Enterprise maximum) | the records are gate evidence |
| retain backups on delete, final backup | **off** | ADR-0009, D1: no backup outlives the instance |
| deletion protection | on | |
| flag | `cloudsql.iam_authentication` = `on` | IAM database login |

Connector enforcement isn't on the create page, and the Sandbox preset sets
the backup location and the two backups on delete differently. Set all four
once the instance is running:

```
gcloud sql instances patch "${PROJECT_ID}-pg" --project "$PROJECT_ID" \
  --connector-enforcement=REQUIRED --backup-location=europe-west2 \
  --no-retain-backups-on-delete --no-final-backup
```

`REQUIRED` accepts only Cloud SQL connector connections (the Auth Proxy and
the language connectors). Cloud SQL Studio still works with it.

Check: `read-back.sh`, *Cloud SQL instance*.

### 9. Database and database users

On the instance, in the console:

1. *Databases → Create database*: `listing_tool`.
2. *Users → Add user account → Google Cloud IAM*: the developer's Google
   account, with the database role `cloudsqlsuperuser`. This is the only
   admin login: the `postgres` password is unknown. If IAM login ever
   breaks, reset the `postgres` password in the console.
3. The same, for the runtime account's full email, with **no** database
   roles. Its username drops `.gserviceaccount.com`. It gets one table
   grant, in 4.
4. The table, before deploying an image that writes to it: in *Cloud SQL
   Studio*, logged in to `listing_tool` as the developer's IAM user, run
   `deploy/schema.sql` as it is, then:

   ```sql
   GRANT INSERT ON items TO "<DB_USER>";
   ```

   with `DB_USER`'s value from `deploy/lib.sh` typed in by hand: Studio
   can't expand variables. `INSERT` only: the app only inserts, with no
   `RETURNING` or `ON CONFLICT` (both need `SELECT`), and the developer
   reads rows as their own user. No sequence grant: the ID is a UUID made
   in the app. **trial-confirm** adds `SELECT` and a column-level `UPDATE`
   at its own deploy; the columns already exist.

Not *Workforce identity federation*: that is for an outside identity
provider.

Check: `read-back.sh`, *Database and users*, and the developer logs in to
`listing_tool` as their IAM user in *Cloud SQL Studio* (IAM database
authentication), where `SELECT current_user;` returns their account. After
4, `SELECT privilege_type FROM information_schema.role_table_grants WHERE
table_name = 'items' AND grantee = '<DB_USER>';` returns only `INSERT`.
That query is the only check for the grant: read-back's *its database
roles* line shows Cloud SQL user roles, not table grants.

### 10. Photo bucket

One bucket, `${PROJECT_ID}-photos`, created in the console (*Cloud Storage →
Buckets → Create*):

| setting | value | why |
|---|---|---|
| location | region `europe-west2` | ADR-0009, D6 |
| storage class | Standard, no Autoclass | |
| hierarchical namespace, Rapid Cache | off | the namespace can't be changed later |
| public access prevention | enforced | ADR-0008, D6 |
| access control | uniform | roles only, no per-object ACLs |
| soft delete | default, 7 days | **trial-data-deletion** allows for it |
| object versioning, retention | off, none | |
| encryption | Google-managed | |

Check: `read-back.sh`, *Bucket*.

### 11. Runtime account's database and bucket roles

```
SA="listing-tool-runtime@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud storage buckets add-iam-policy-binding "gs://${PROJECT_ID}-photos" --project "$PROJECT_ID" \
  --member="serviceAccount:$SA" --role=roles/storage.objectCreator

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA" --role=roles/cloudsql.client --condition=None

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA" --role=roles/cloudsql.instanceUser --condition=None
```

- **Object Creator, on the bucket only:** it can write photos but not read,
  list or overwrite them.
- **The two Cloud SQL roles, on the project:** the exception to step 5.
  `gcloud sql instances` has no IAM policy commands, and the console says
  database login must be granted "in the IAM policy of the instance's
  project". Instance User is that login. Client is granted because Google's
  pages disagree on whether a connector needs it. Kept, untested: the first
  connector deploy worked with it, and nobody tried without it.

The project commands print the whole policy, account emails included: clear
the terminal.

Check: `read-back.sh`, *Runtime account's roles*: on the project, the photo
bucket and the secret, the account holds exactly these three plus step 7's
secret role, and nothing else. It reads only those three policies.

## Deploy

```
deploy/deploy.sh
```

Deploy from `main`: merge the PR on GitHub, `git switch main && git pull`,
then run it. Only a change to the image (`app/`, `labels/`, `pyproject.toml`,
`uv.lock`, `Dockerfile`, `.dockerignore`), to `lib.sh`, or to the flags in
`deploy.sh`'s `deploy_service` needs a deploy; docs and `read-back.sh` don't.

It refuses a dirty tree, untracked files included, and any commit not on
`origin/main`, so every image is reviewed, through CI and its commit tag is
on GitHub. The image is built from the commit itself (`git archive`), never
from files on disk; the clean tree is for the script and `lib.sh`, which
are read from disk. It builds for `linux/amd64`, tags the image with the
full commit hash and pushes it. If this
commit's image is already in the registry, it reuses it: tags are immutable,
and a rebuild would give a different digest. It deploys by digest, checks that
a request with no sign-in is redirected to Google sign-in, and grants IAP
access to `IAP_MEMBERS` (adds only; remove someone in the console).

The fixed settings (service name, runtime account, pinned secret version,
memory, timeout, concurrency, instances, and the Cloud SQL and bucket
settings) are in [`lib.sh`](lib.sh), tracked, so every change is a commit. To
rotate the key: add a secret version, change `SECRET_VERSION`, commit, deploy.

The service also gets four plain environment variables, for the app from
**trial-records** on: `CLOUD_SQL_INSTANCE` (the instance connection name),
`DB_NAME`, `DB_USER` (the runtime account's IAM database user) and
`PHOTO_BUCKET`. None is a credential.

## Read-back

```
deploy/read-back.sh
```

Read-only. Reads the deployed service back and compares it with `lib.sh`:
region, IAP, timeout, concurrency, instances, memory, runtime account, pinned
secret, the environment variables, that the deployed digest is the one its
commit tag points to, that a request with no sign-in is redirected to Google
sign-in, log retention, and that IAP's Data Access logs are off. It also
checks steps 8–11: the instance's settings, the database and its users, the
bucket, and that on the project, the photo bucket and the secret the runtime
account holds exactly its four roles and nothing else. Exits 1 if any check
fails. Run it after every deploy.

## Running `gcloud` from a script

- Pass `--quiet` and give it no stdin (`</dev/null`). Otherwise a prompt, such
  as one to enable an API, hangs the script instead of failing it.
- `gcloud`'s error messages include the signed-in account's email. Filter its
  stderr as well as the script's own output.

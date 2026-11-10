# ADR-0008: Phase 2 architecture

- **Status:** Accepted
- **Date:** 2026-11-09
- **Amends:** CLAUDE.md, *Flow*, *Commands* and *Engineering constraints* (D4,
  D8, D10)
- **Depends on:** ADR-0007
- **Terms:** see `GLOSSARY.md`.

## Context

The phase 2 trial needs a deployed app: staff photograph a label, confirm or
edit the read, and the final value goes into the Google Sheet (ADR-0007). Today
there is a CLI and a small Flask form that read one photo and store nothing.

ADR-0007 and the existing code set these constraints:

- **Frozen configuration.** The trial runs at the phase 1 gate's settings, and a
  change restarts the count. The model must see what the gate's reads saw.
- **The records are the evidence.** The gate is counted from what's stored per
  item in Postgres (ADR-0007, *Scope and storage*) plus the hand log (ADR-0007,
  *How items count*), so the records must be reliable and queryable, including
  during the trial for the stop rule.
- **The Sheet must be right.** The trial pauses if a confirmed value reaches it
  incorrectly.
- **Some fields stay hidden.** `needs_review` is computed but must not reach
  staff.
- **Slow reads are possible.** A read's worst case is about 600s (CLAUDE.md,
  *Engineering constraints*).
- **The trial is small.** About 60 items, one staff member and one developer, so
  complexity is a cost that has to pay for itself.
- **The catalogue is off,** so it isn't hosted.

## Diagram

```
Staff phone: TypeScript frontend
        │ HTTPS
        ▼
Identity-Aware Proxy: Google sign-in
        │
        ▼
Cloud Run: one container, one request per instance
┌──────────────────────────────────────────────┐
│ frontend files + FastAPI routes (app/)       │
│                                              │
│ app/db.py   app/photos.py   app/sheet.py     │   labels/transcribe.py
└────┬────────────┬───────────────┬────────────┘            │
     ▼            ▼               ▼                          ▼
Cloud SQL    Cloud Storage    Google Sheet            Anthropic API
Postgres     private bucket
```

The path of one item:

1. Staff photograph the label, and the file uploads unchanged (D9).
2. `POST /items` stores the photo, makes the read through `extract_bytes()`, and
   stores the item in Postgres. Only the ID and the value shown go back (D3, D5).
3. Staff confirm or edit the value. If the read looks wrong, upload again starts
   a new item (D5).
4. `POST /items/{id}/confirm` updates Postgres, then makes one append to the Sheet
   (D7).
5. If the append fails, staff check the Sheet and can tap Post to Sheet (D7).

## Decisions
### D1: Host and edge auth

The app runs as one container on Google Cloud Run, with Identity-Aware Proxy
(IAP) enabled directly on the service. Staff sign in with Google accounts named
in the IAP policy, and the app holds no login code. A single service gives the
single origin D3 needs.

The first deploy uses `gcloud` and the console. Terraform comes later (TODO.md,
**mlops-stack**).

**Accepted cost:** Cloud Run keeps no local files, so records and photos need
an external store (D6).

### D2: Sync or async read

The read is one synchronous request: the POST returns the read. The frontend
stops waiting after about 2 minutes and offers staff upload again, which starts a new item (D5). Model settings and retries don't change (ADR-0007 freezes the configuration).

**Accepted cost:** after the frontend gives up, the server call can still finish
and be paid for.

**Move to async when** batch processing is introduced, or the trial shows reads
regularly hitting the limit. `extract_bytes()` wouldn't change, only the
endpoint and how the frontend waits.

### D3: Frontend
The staff app is a TypeScript frontend calling a Python JSON API. The API is a
thin layer over `extract_bytes()`, so `labels/` doesn't change.

The frontend and the API are served from one origin, so the edge auth (D1)
covers both and no CORS is needed.

The frontend holds no ART logic. It shows the value the API gives it and sends
back what staff confirm. It never parses or corrects an ART number.

API responses are an explicit allowlist of fields, never `asdict(extraction)`.
A JSON API would otherwise send fields ADR-0007 hides, such as `needs_review`,
to the browser.

### D4: Backend

FastAPI replaces Flask in `app/`, migrated before any new routes are added.
`labels/` doesn't change.

`response_model` is how D3's allowlist is enforced. The frontend's TypeScript
types are generated from the OpenAPI schema, so both sides share one definition.

Routes are plain `def`, because the read uses `run_sync`, which can't run inside
an `async def` route.

Cloud Run runs one request per instance, with at least two instances allowed so
an upload doesn't queue behind an abandoned read (D2). Eval runs are serial, as a precaution
against a suspected pydantic-ai concurrency stall (`evals/README.md`), and this
keeps the app the same.

### D5: API shape, and who holds item state

The server stores one item per upload, except a failed read (below), and the
client holds only its ID and its count of failures in a row.

```
POST /items                photo → stores the item and its read, returns the ID and the value shown
POST /items/{id}/confirm   final value → records it; the server works out confirmed unchanged or edited
POST /items/{id}/post-to-sheet   retries the Sheet write after a failure (D7)
```

The read, the value shown and the configuration are stored when the read is
made, so the gate never rests on what the browser reports. Time taken runs from
the upload to the confirm, both timed on the server.

To work out confirmed unchanged or edited, the server compares the final value
with the value shown after trimming spaces and uppercasing both. Leading zeros
are kept. This applies only to that comparison and to matching ART numbers for
the count (ADR-0007): the final value is stored and sent to the Sheet as entered.

Upload again starts a new item, with nothing linking it to the last one. An
item that is never confirmed has no final value, so it doesn't count. The
confirmed item holds the last read staff saw, which is what ADR-0007 scores.

Unconfirmed items stay recorded, and their total is the trial's retake figure.
Whether their photos are kept is for ADR-0009.

An empty read still stores the item, which is never confirmed and adds to the
retake total. The frontend shows the empty-read screen (ADR-0007) when the value
is empty, with no ART logic of its own. The server refuses a confirm whose final
value is empty or blank or contains `?`, so staff must edit a value with `?` in
it, and any confirm on an item whose value shown is empty.

A failed read (ADR-0007) stores no row and returns an error. Any photo already
stored stays in the bucket. The frontend shows a failed-read screen, separate
from the empty-read screen, offering upload again. It counts failures in a row,
and after the second the screen tells staff to enter the ART number in the Sheet
and note it in the downtime log. A read past the 2-minute limit (D2) shows the
same screen, but if it later finishes it stores its item as usual, which is never
confirmed and adds to the retake total.

**Accepted cost:** no retake count per item, and the total slightly overstates
retakes because it includes scans staff abandoned. Time taken covers only the
final upload. Neither figure is gated.

### D6: Where records and photos live (mechanism only)

Photos go in a private Cloud Storage bucket. Records go in PostgreSQL on Cloud
SQL, in the same Google project as the service. Who can see them and for how
long is for ADR-0009.

Each item (D5) is one row. Counted items and the count of edits for the stop
rule (ADR-0007) come from a plain SQL query on Postgres, with the hand log
(ADR-0007) applied by eye, because it will be a handful of rows. The developer
runs this once per working day, with D7's Sheet comparison in the same run.

Cloud Run connects through its built-in Cloud SQL connection, and the instance
has no authorised networks. Automated backups are on, because these records are
most of the gate's evidence. They don't cover the hand log, which is in the
feedback Sheet (ADR-0009).

The schema is a plain SQL file. A migration framework waits until there's more
than a table or two to manage.

### D7: Confirm: write order, partial failure, double-tap

Each confirmed value adds a new row to the Sheet, within a minute of the confirm.

1. Confirm updates the Postgres row first, only if the item is still
   unconfirmed, and sets its Sheet status to pending. A second tap changes
   nothing.
2. It makes one Sheet append as raw text, so Sheets doesn't parse the value, with
   a short timeout and no automatic retries, then sets the status to sent or
   failed.
3. On failure, staff see: "Saved, but we couldn't confirm it reached the Sheet.
   Check the Sheet. If it isn't there, tap Post to Sheet." The button makes one
   more append, and only after moving the status to pending in one atomic
   update, from failed or from a pending older than the append timeout, so a
   second tap or a live append can't cause another write.
4. A wrong confirm is fixed directly in the Sheet. The record keeps what was
   confirmed.

A timed-out append may still have landed, so a retry could add a duplicate row,
which then has to be deleted (ADR-0007). Staff can see the Sheet, so they make
that check. A missing row is visible and easy to fix, and the gate counts from
Postgres plus the hand log (ADR-0007), so a failed Sheet write doesn't affect
the score.

A short SQL query finds items stuck at pending or failed. If the page was closed
there is no way back to the item, so that case stays with the query. It runs
alongside the stop rule's edit count (D6).

The same run compares the Sheet with Postgres. Differences are checked by eye,
because hand-typed rows and fixes (step 4) are expected. Any other difference is
a confirmed value reaching the Sheet incorrectly (ADR-0007, *Stop Rule*).

**Accepted cost:** staff do a manual check on a failed write, and the Sheet can
differ from the record after a fix.

### D8: External-call boundary (database, Sheets, storage), tests stay offline

Each external system has one module in `app/` (`app/db.py`, `app/photos.py`,
`app/sheet.py`), the only importer of its client. `labels/transcribe.py` remains
the only caller of the model, and `labels/` imports no other client.

Route tests patch those modules, as they patch `extract_bytes` today. A test that
reaches an unpatched one fails.

A few tests run against real Postgres, because they cover the numbers the trial
depends on: a second confirm changes nothing (D7), counted items are selected
correctly, and the edit count is correct. They run only when
a test database URL is set, and skip otherwise. In CI the URL is required, so a
missing database fails the run instead of skipping unnoticed.

Sheets and Cloud Storage are always patched in tests. D7's check against a copy
of the real Sheet covers the real append.

### D9: Photo bytes reach the model unchanged

The browser uploads each photo, retakes included, as the file it was given: no
resizing, compression, cropping, rotation or format conversion in the frontend.
The API passes those bytes to the pipeline as received. `upright()`, in
`read_art()`, stays the only change made to a photo before the model sees it.

A rejected upload, by type or by size, is a failed read (ADR-0007). Photos are
never shrunk or converted to fit. If the staff member's phone fails the check
under *Build constraints*, its camera setting is changed instead.

The stored photo (D6) is the upload as received, so a replay goes through
`upright()` exactly as the original read did, because ADR-0007 freezes the trial
at the phase 1 gate's settings.

### D10: Frontend tooling

The frontend is React, Vite and strict TypeScript, in a top-level `frontend/`
folder. React is the best base for wider staff intake and is already familiar.
It builds to a static single-page app that FastAPI serves from the one container
(*Diagram*), so production has no Node runtime.

Styling is Tailwind alone, designed phone-first with large tap targets. Repeated
styles become React components, not `@apply`. `app/static/style.css` isn't
ported.

There is no router, TanStack Query or state library until a second screen
exists: the client holds only an item ID and a failure count (D5).

Packages are managed with npm, which ships with Node, with exact versions pinned
and Node pinned in `.nvmrc`. Tests use Vitest with React Testing Library. Lint is
ESLint, and TypeScript stays on 6.x until typescript-eslint supports 7.

The generated types (D4) are committed, and CI checks they match a fresh
generation.

**Accepted cost:** an API change means regenerating and committing the types,
and TypeScript is a major version behind until typescript-eslint catches up.

## Build constraints

- D1: the Cloud Run request timeout is set explicitly above the worst-case call,
  because the default is 300s. Any timeout in the app server is too. After
  deploy, read the value back from the service's configuration.
- D1: after deploy, a request with no signed-in user doesn't reach the app.
- D2: at first deploy, a request held open for the full limit completes through
  IAP from a phone browser. Google's docs state no time limit for IAP.
- D2: a frontend test that a read past the limit offers upload again.
- D3: a test that the read response's keys equal the allowlist.
- D4: a test that no route handler is a coroutine function.
- D4: after deploy, read the service's concurrency back as 1 and its maximum
  instances as at least 2.
- D5: a test that confirmed unchanged or edited comes from the stored value
  shown, and the confirm request carries only the final value.
- D5: a test that the server refuses a confirm whose final value is empty or
  blank or contains `?`, and any confirm on an item whose value shown is empty.
- D6: after deploy, the bucket has public access prevention on and the Cloud SQL
  instance has no authorised networks.
- D6: one backup is restored successfully before the team trial starts.
- D7: a test that a second confirm changes nothing and makes no Sheet write.
- D7: a test that Post to Sheet writes only when the status is failed or has
  been pending for longer than the append timeout, and that a second tap during
  that write makes no append.
- D7: the Sheet append sets its timeout explicitly, has no automatic retries and
  writes raw text.
- D7: before the founder review, an append to a copy of the real Sheet puts the
  row and the value where staff expect them, with a leading-zero value intact.
- D8: `API_CLIENTS` in `tests/test_boundaries.py` gains the Google clients and
  the Postgres driver, and the boundary test checks each against its one module.
  It doesn't list them today, so without this nothing catches a stray import.
- D8: CI fails if the test database URL is missing.
- D9: a test that the bytes reaching `extract_bytes()` equal the bytes uploaded.
  The frontend uploads the original `File`; review checks nothing draws it to
  a canvas first.
- D9: at **deploy**, a real upload from the staff member's phone arrives in a
  type the app accepts and within the API's per-image limit. If the phone
  produces a rejected type such as HEIC, change the phone's camera format; never
  convert in the app.

## Not decided here

- **ADR-0009:** who can see records and photos and for how long, whether
  unconfirmed uploads' photos and any phone location data are kept, what logs and
  tracing may record, the limits on what reaches the Sheet, and the Google Cloud
  region.
- **TODO.md:** **mvp-confirm** (the confirm screen's design and wording),
  **upright-guidance** (the upright-photo guidance), **web-hardening** and
  **observability**.

## Alternatives considered
- **D1, AWS ECS Fargate with login at the load balancer:** rejected. More setup
  and an always-on cost for a small trial. App Runner, AWS's simpler option,
  closed to new customers on 2026-04-30.
- **D1, Render or Railway with Cloudflare Access:** rejected. Simple to deploy,
  a persistent disk would suit SQLite, and Access can email staff a one-time
  code. But it needs an active domain on Cloudflare, a JWT check on every
  request because the platform's own URL skips the login, and still a Google
  Cloud project for the Sheets API. Cloudflare's proxy also cuts a response off
  at 100 seconds below its Enterprise plan.
- **D1, Vercel for frontend and Python:** rejected. Its request body limit
  appears to be 4.5MB (unconfirmed), and D9 forbids shrinking photos to fit.
- **D1, Fly.io:** rejected. Its proxy closes a connection after 60 idle seconds,
  and a synchronous read sends nothing while it waits.
- **D1, IAP through a load balancer in front of Cloud Run:** rejected. It adds
  cost and gains nothing for one service.
- **D2, sync with no limit:** rejected. In the worst case staff wait about 10
  minutes on a spinner.
- **D2, async job with polling:** rejected for now. It survives a locked phone,
  but adds job state, polling, and probably a second service: IAP replaces the
  caller's identity, which Google warns can break services such as Pub/Sub. What
  follows the trial isn't decided, and async can be added later.
- **D3, keep the server-rendered Flask form:** least work, and it already goes
  from photo to read. Rejected: not industry best practice, could limit future potential of staff intake
- **D3, frontend and API on separate origins:** rejected. It needs CORS and
  auth on both sides.
- **D4, keep Flask and add JSON routes:** rejected. It would work and needs no
  migration, but the allowlist is enforced only by hand and the TypeScript types
  are hand-written and can drift. `app/` is small enough that moving now is cheap.
- **D4, Flask with an OpenAPI add-on:** rejected. It adds a layer from a smaller
  project to get what FastAPI includes.
- **D4, Django or a Node backend:** rejected. Django's ORM and admin solve
  problems this app doesn't have, and Node would mean rewriting or wrapping the
  Python pipeline the gate measured.
- **D5, client holds everything until confirm:** rejected. The photo uploads
  twice, a reload loses the scan, and the gate would rest on what the browser
  says it showed.
- **D5, link retakes to one item:** rejected. It adds an endpoint and a guard
  against a late read overwriting a newer one, for a figure that is reported,
  not gated.
- **D6, an existing Postgres server outside Google Cloud:** rejected. It saves the instance cost,
  but Cloud Run has no fixed outbound IP, so reaching it safely needs a NAT or a
  tunnel. It would also split trial data across two providers and share a server
  with whatever else runs there.
- **D6, one JSON file per item in the bucket:** rejected. No second service, but
  every count needs a script that reads every item, and the format is ours to
  maintain.
- **D6, Firestore:** rejected. No server and a generous free tier, but no SQL for
  the trial's reports and weaker constraints.
- **D6, hosted serverless Postgres (Neon, Supabase):** rejected. It adds a vendor
  and puts trial data outside Google.
- **D6, SQLite with a sync tool:** rejected. D4 runs one request per instance, so
  simultaneous reads would mean more than one instance writing to the database.
- **D6, the Google Sheet as the record store:** rejected. It's the staff-facing
  output, not a place for trial records.
- **D7, write the Sheet first:** rejected. If the database write then failed, the
  Sheet would hold a value with no record behind it, and the gate counts from
  the records.
- **D7, automatic retry of the Sheet write:** rejected. After a timeout it can't
  tell whether the row landed, so it can add a duplicate.
- **D7, an item ID column in the Sheet, so a retry can check for itself:**
  rejected. It adds a column to a Sheet staff use, and more code, for about 60
  items.
- **D7, a job that sends pending rows:** rejected. Staff need the value within a
  minute, so it would have to run every minute.
- **D7, an outbox with a queue worker:** rejected. It brings back the background
  work and IAP problems rejected in D2.
- **D8, interfaces with real and in-memory versions:** rejected. The most code
  for three small integrations, and a fake can behave differently from the real
  system.
- **D8, one module for all three systems:** rejected. Three unrelated systems in
  one file, which gets harder to work with as it grows.
- **D8, no import rule inside `app/`:** rejected. Clients could spread through
  `app/` with only review to stop them.
- **D8, only patched databases in tests:** rejected. The double-tap test would
  prove the fake, not the SQL.
- **D8, SQLite as a test stand-in:** rejected. A different database from
  production, so a pass can mislead.
- **D9, resize in the browser for faster uploads:** rejected. It changes what
  the model sees.
- **D9, rotate in the browser:** rejected. `read_art()` already does it, in the
  one place every path goes through.
- **D10, Svelte:** rejected. A smaller ecosystem, and syntax used nowhere else
  here.
- **D10, Vue:** rejected. Neither the largest ecosystem nor the smallest output.
- **D10, plain TypeScript:** rejected. It doesn't grow well and would likely be
  replaced if intake expands.
- **D10, Next.js, Nuxt or SvelteKit:** rejected. They need a Node runtime beside
  FastAPI (*Diagram*), and a static export would carry a framework whose main
  features go unused.
- **D10, a router, TanStack Query or a state library now, for wider intake:**
  rejected. The client holds almost nothing (D5), and adding them later is cheap.
- **D10, plain CSS:** rejected. Every new screen would be styled by hand.
- **D10, Tailwind with shadcn/ui:** rejected for now. It can be added on top
  later if intake needs it.
- **D10, MUI:** rejected. Heavy and hard to restyle.
- **D10, generating the types during the build:** rejected. The Docker Node stage
  would have to run the Python app to get the schema.

## Consequences

- D2: D2's test runs in the frontend job in `.github/workflows/tests.yml`.
- D4: CLAUDE.md's web command changes when `app/` moves to FastAPI, and FastAPI
  and its server join the dependencies.
- D4: the gunicorn lines in TODO.md (**web-hardening**, **docker-image**) need
  rewording.
- D6: a Postgres driver and the Cloud Storage client join the dependencies, and
  D8 sets where they may be imported.
- D7: a Google Sheets client joins the dependencies, under the same D8 rule.
- D8: CLAUDE.md's rule that only `labels/transcribe.py` calls an API becomes:
  only it calls the model, each other external system has one module in `app/`,
  and `labels/` imports no other client. CLAUDE.md's *Flow* changes with it.
- D8: `.github/workflows/tests.yml` gains a Postgres service and the test
  database URL, and CLAUDE.md's *Commands* row for CI changes with it.

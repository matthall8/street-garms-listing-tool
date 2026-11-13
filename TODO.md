# TODO

Current state and in-flight work. Stable architecture and invariants are in
CLAUDE.md. Phase 1 gate: adr/0002. Baselines and md5 ledgers: evals/BASELINES.md.

- Each item starts with a short bold name. Refer to items by name, never by
  position.
- One line per item where possible, linking to the rule's home (ADR,
  CLAUDE.md, BASELINES.md) rather than restating it.
- A section is named after the milestone it leads to and ends with that
  milestone. A "before X" section holds only X's real prerequisites.
- `Decision:` marks an item that needs my call before work starts. An item
  without it can go straight to a worker.
- *Next* names at most three items, chosen by me.
- The branch that finishes an item deletes it, and its name in *Next*, in
  its own PR, so it goes when the PR merges. Never tick it; git holds the
  history.
- New items go in *Inbox*, where `/open-pr` adds them; I sort them into a
  section.

## Next
- **frontend-review-checks**
- **trial-records**

## Staff trial
Phase 2: the build for ADR-0007's trial, under ADR-0008 and ADR-0009.
Items are in build order. A branch that adds a Python dependency first
repeats the gate check: fingerprints, `labels/` unchanged, and the
`pydantic-ai` and `anthropic` locks (ADR-0007, *Scope and storage*,
Config; BASELINES.md, *Held-out test set*).

- **frontend-review-checks**: `/open-pr` and the code-reviewer list only
  the Python checks, so every frontend PR comes back "Review incomplete".
  Add the frontend job's checks and how to select the pinned Node to
  `.claude/skills/open-pr/SKILL.md` and `.claude/agents/code-reviewer.md`,
  on its own branch, before **mvp-scaffold**. The edits are under
  `.claude/`, where agents need my approval, so I make or approve them
- **trial-records**: Cloud SQL, the bucket and backups (ADR-0008, D6;
  ADR-0009, D6); `app/db.py`, `app/photos.py` and `POST /items`, storing
  the read-time fields ADR-0007, *Scope and storage* lists, behind the
  response allowlist (D3). A failed read stores no row, with D5's one
  exception (ADR-0007, *How items count*; D5). The D3 and D9 tests, D6's
  after-deploy check; the real-Postgres setup, CI service and required
  test database URL, with one real-Postgres test that stores a row (D8).
  Adds the Postgres driver and the Cloud Storage client to `API_CLIENTS`
  (D8); CLAUDE.md's API rule, *Flow* and CI command change with it
  (ADR-0008, *Consequences*). Its credential, if any, goes into Secret
  Manager (ADR-0009, *Amendments*)
- **postgres-test-skips**: the real-Postgres tests (ADR-0008, D8) skip
  when no URL is set, but the reviewer requires 0 local skips
  (`.claude/agents/code-reviewer.md`); reconcile them. With
  **trial-records**
- **upload-cap-reuse**: reuse the upload-cap helper in `app/routes.py`
  for `POST /items`. With **trial-records**
- **trial-confirm**: confirm, storing the confirm-time fields, and the
  confirms the server refuses (ADR-0008, D5); D5's tests and D8's three
  real-Postgres tests; the counted-item and stop-rule queries (D6).
  After **trial-records**
- **sheets-push**: `app/sheet.py` and `POST /items/{id}/post-to-sheet`,
  appending to the field ADR-0007 sets (ADR-0008, D7 and its *Build
  constraints*), and the stuck-Sheet query (D7). Adds the Google Sheets
  client to `API_CLIENTS` (D8). Its credential, if any, goes into Secret
  Manager (ADR-0009, *Amendments*). After **trial-confirm**
- **web-hardening**: what the trial needs (ADR-0009, *Threat model*):
  upload checks (Pillow `verify()`, `MAX_IMAGE_PIXELS`), error type
  logged with the raw error hidden, `uvicorn` timeouts
- **upload-cap-scope**. Decision: the 16MB check in `app/routes.py`
  covers only the photo field and runs once the body has arrived, so a
  large upload is stored before its 413 and a large extra file part is
  parsed, then ignored. Decide whether **web-hardening** needs a
  request-level limit. With **web-hardening**
- **uvicorn-timeouts-wording**: reword **web-hardening**'s "`uvicorn`
  timeouts": uvicorn has no request timeout, only keep-alive and worker
  timeouts this image doesn't use. With **web-hardening**
- **mvp-scaffold**: the TypeScript app, with types generated from the
  OpenAPI schema (ADR-0008, D3, D4); the original file uploaded (D9);
  the 2-minute limit (D2), its `AbortController` in the submit handler
  rather than a `useEffect`, and a test that the request aborts; the
  flow as a discriminated union in `useReducer`. After **sheets-push**
  and **web-hardening**, so the API, its rejections included, is
  complete when the types are generated
- **generated-types-check**: the CI check that the committed types match
  a fresh generation (ADR-0008, D10). With **mvp-scaffold**
- **missing-photo-check**: frontend validation for a missing photo. With
  **mvp-scaffold**
- **mvp-confirm**: the confirm-or-edit screen, upload again, the
  empty-read screen (ADR-0007, *Scope and storage*), the failed-read
  screen (ADR-0008, D5), Post to Sheet (D7), and D2's test that a read
  past the limit offers upload again. After **mvp-scaffold**
- **upright-guidance**: capture guidance in the web UI: the photo must
  be upright (ADR-0002). With **mvp-confirm**
- **mvp-cutover**: deletes the Jinja form, `GET /` and `POST /`
  (`app/templates/`, `app/static/style.css`), the `jinja2` pin and the
  HTML route tests: `result.html` branches on `needs_review`, which
  ADR-0007 hides from staff. The frontend files join the Docker image
  (ADR-0008, *Diagram*): its Node stage extends `.dockerignore`'s
  allowlist and `ALLOWED` in `tests/test_docker_image.py`, and the CI
  `docker` job's checks of `GET /` and `style.css` move to routes that
  remain. Then add the ADR-0009, D1 people to the IAP policy
  (`IAP_MEMBERS`, `deploy/README.md`). After **mvp-confirm**
- **observability**: minimal: one allowlisted record per read, only what
  ADR-0009, D3 allows: status, commit, prompt fingerprint, model,
  latency, request count and token usage per call, input size,
  dimensions and whether it was rotated
- **image-commit**: add the git commit to the image, which has no
  `.git`. With **observability**, the first branch that reads it
- **trial-admin**: the feedback Sheet, with what it holds and who it's
  shared with (ADR-0009, *What's held where*, D1); the weekly status
  meeting (ADR-0007, *Team feedback*); the once-per-working-day count
  and Sheet comparison (ADR-0008, D6, D7)
- **staff-instructions**: what the staff member does for upright photos,
  empty and failed reads, the hand log and the downtime log, a wrong
  confirm and a failed Sheet write (ADR-0008, D7), and who may upload
  (ADR-0007, *Stages*). Wording follows **mvp-confirm**'s screens; a
  change during the trial restarts the count (ADR-0007, *Stop Rule*).
  Before **founder-review**
- **backup-restore**: restore one backup before the team trial
  (ADR-0008, *Build constraints*, D6). After **trial-records**
- **mid-trial-config-rule**. Decision: ADR-0007 allows a mid-trial
  configuration change with a restart, but ADR-0006 is phase 1 only and
  **later-run-rule** comes after the trial, so no rule judges that
  change. Say which rule applies, or that it's a project team decision
- **founder-review**: ADR-0007, *Stages*, stage 1. First the append to
  a copy of the real Sheet (ADR-0008, *Build constraints*, D7), then the
  Sheet-sharing check (ADR-0009, D1), both before its items; the phone
  location check at the review (ADR-0009, D2). Revisit min instances
  (0) against the measured cold start: 13.4s at first deploy. After
  every item above
- **staff-trial**: ADR-0007's team trial (*Stages*, *Gate*, *Stop
  Rule*); what's shown is in *Scope and storage*, Settings for the
  trial. After **founder-review**
- **audit-sample**: ADR-0007's single end-of-trial spot check (*Reported
  but not gated*), reported and not gated. After **staff-trial**
- **trial-report**: ADR-0007's *Reported but not gated*, totals only in
  BASELINES.md, plus the gate result and staff sign-off. After
  **audit-sample**
- **trial-data-deletion**: delete trial data on the date the project
  team sets at stage 3, check it's gone, and keep what survives a fail:
  anything labelled for the eval set, copied there first, and the
  failed-trial list (ADR-0009, D1). After **staff-trial**

## After the trial

On hold until the trial ends: ADR-0007 freezes the configuration, all
the model sees, for the whole trial (*Scope and storage*, Config). Dev
grows only on a failed trial, and **grown-baseline** then comes first
(ADR-0002, *Decision*, "Frozen from 2026-11-04"; its 2026-11-09
amendment). Any change to what the model sees is one run
(*Iterations*). **adr-0006-unit**, **one-prompt-definition**,
**flagged-rename**, **cost-capture** and **spend-cap** don't touch the
configuration and can be done during the trial.

### Iterations

#### Before the first
- **grown-baseline**: on a failed trial, a paid run of the accepted
  configuration on the grown dev set, `--repeat 3`, recorded as the new
  baseline, not judged (ADR-0002)
- **margin**. Decision: the dev margin above 80%, informed by how run
  0's out-of-sample photos compare with the rest (BASELINES.md). If it
  becomes a rule, it goes in ADR-0002
- **adr-0006-unit**: ADR-0006's unit in the report, each positive
  garment-side's correct reads summed over its photos (the garment-sides
  table counts photos; until then, sum by hand from base per photo).
  Same branch: `PerPhotoCounts`' docstring and `TestPerPhotoCounts`'
  still call it ADR-0006's table; and the report prints ADR-0006's
  verdict (wins, losses, threshold, guardrail), not a hand count
- **adr-0006-saturated**. Decision: how ADR-0006 judges changes while
  dev is saturated (4 garment-sides can win; the rule needs 6): fixes
  ADR-0002 requires to the photo sent (PR #61 merged one with a Must
  fix noted), and a no-worse path for hygiene changes
  (**invented-examples**). Also before the next input-side fix
- **one-prompt-definition**: one definition of what the model is sent,
  which `/open-pr`'s *Eval* bullet and the reviewer's *Prompt contract*
  check both point to. Today they differ: only the reviewer counts the
  user message and the image handling in `labels/photo.py`; only
  `/open-pr` has the `model_json_schema()` exception. Replace the
  reviewer's `git diff <cited-tag>` coverage check, read by hand today,
  with a comparison of the header fingerprints. With
  **adr-0006-saturated**
- **flagged-rename**: rename the harness's "flagged but correct" to
  "ambiguous but correct": it counts `ambiguous_characters`, not
  `needs_review`, so `evals/README.md` and BASELINES.md describe it
  wrongly in the reports iterations are judged on
- **later-run-rule**: the run rule for later runs (ADR-0006 revisit),
  with ADR-0001's per-run rule. After **staff-trial**, before any fix
  following a fail is tested (ADR-0007)

#### Before the model comparison
- **cost-capture**: usage / cost capture in code (SG billing?). Run 0's
  spend was read off the Anthropic console before and after, and
  recorded in BASELINES.md
- **spend-cap**: print the call count up front, confirm past a
  threshold

#### Candidates
- **iterations**: one change per run, until dev clears 80% with
  **margin**. Candidates: image resizing?, compare models (Sonnet,
  Opus, Haiku: check current versions; after *Before the model
  comparison*), prompt gives character classes, never lengths
  (ADR-0001, *Trust rules*: decide first whether the prompt may describe
  formats). Format-specific prompt changes, character classes included,
  wait until every format family is in dev
- **front-label-location**: a prompt line on where the code sits on a
  front label; every run 0 miss is a front read as `not_visible`
  (BASELINES.md). After **grown-baseline**: 4 misses can't prove a fix
- **barcode-guidance**: barcode guidance in the prompt
- **invented-examples**: replace `ART_PROMPT`'s real examples with
  invented ones: 8–9 characters, one with a leading zero, checked not to
  be catalogue keys or test-set codes (pass/fail, no rows printed). Not
  a gate prerequisite: ADR-0002 leaves out a test garment whose code is
  a prompt example
- **cheaper-model**: once dev clears 80%, revisit a "no worse" path for
  a cheaper or faster model (ADR-0006). If you want one, decide its rule
  before running it: compared against the last model accepted on wins,
  with **cost-capture** in place
- **deps-update**, waits until after **staff-trial** (ADR-0007, frozen
  configuration): move to `pydantic-ai-slim` with only
  the Anthropic extra and bump `certifi`, then upgrade `pydantic-ai` on
  its own, with a replay and a run against the latest baseline

## Later
- **feedback-loop**: production photos join an eval set only after
  labelling by eye, independently of the model and of staff
  edits. Dev is frozen, except a failed trial's labelled items
  (ADR-0007), so otherwise they go to test or a new set (ADR-0002).
  After **staff-trial**
- **monitoring**: review rate, edit rate, latency, and the
  `not_visible`, catalogue miss and `corrected` rates and format-family
  mix against the current baseline's, once there's traffic. A jump
  means a capture problem or a model change
- **pillow-heif**: if desktop HEIC uploads turn out to matter (the form
  and the CLI reject HEIC today)
- **content-sniff**: detect the image type from the bytes, not the
  extension or the browser's mimetype
- **run-history**: a table at the top of BASELINES.md, one row per run
  (date, the variable changed, tag, fingerprint, base-exact per
  garment-side, guardrail, cost, rule result), linked from README
- **portfolio-docs**: a model card, an ADR index (0003 and 0004
  listed as reserved, not yet written), a short note on why
  the process is heavy, a README line on `/explore` and briefs, and a
  README section, *How it's operated*, linking provenance, ledgers, the
  privacy hooks, CI and cost capture. For one line per change, point
  readers at the PR list or `git log --first-parent --oneline main`
  (merge commits titled by PR title)
- **mlflow-tracking**: log runs to MLflow with cost (**cost-capture**),
  backfilled with run 0 and the replay. Params and metrics only;
  anything else as CLAUDE.md, *Private data never enters git*, allows
- **zenml-eval-pipeline**: a ZenML pipeline that orchestrates the eval
  harness (today `tests/eval_transcription.py`); scoring stays in one
  place. After **packaging** and **adr-0006-unit**: its promotion step
  uses the report's verdict
- **results-backup**: back up `evals/results/` after each paid run,
  until **dvc-eval-set** covers it; the reports are the only record of
  paid reads, and `--replay` needs them
- **dvc-eval-set**: version the manifest, photos and `evals/results/`
  (and the catalogue, if it should be restorable) with DVC, local
  remote only (an external drive or an encrypted disk image), never a
  cloud remote (Street Garms' data; agreed with the wider team, 2026-11-04).
  Git gets only `.dvc` hashes; check one against `check_private.py`
  before the first commit
- **mlops-stack**: MLflow Tracing, Terraform: add a tool only when it
  solves a problem the repo has
- **reviewer-eval**: plant known defects on a scratch branch and count
  what the reviewer catches; shares setup with **mutation-test**
- **post-trial-hardening**: CSRF, rate limits, security headers, a kill
  switch, request IDs, cost per read and alerts, the items removed from
  **web-hardening** and **observability** for the trial. Revisit before
  anyone beyond the trial uses the app. The kill switch's manual-entry
  fallback needs rethinking: ADR-0007 makes the Sheet the only place to
  type a number.

### Backlog
Not measured by the phase 1 gate, and blocking no milestone. Kept for when
flags, the catalogue lookup or unconfirmed results come into scope, or for
a quiet moment.

- **split-steps-4-5**: split steps 4 (product decisions, one per branch)
  and 5 (renames, including `matched_art` → `resolved_key`, `miss` →
  `no_key`; GLOSSARY.md, *Renamed*)
- **flag-scorer**: per read, flagged and silent error (wrong and not
  flagged); per garment-side, silent error if any read is, unflagged if
  2 of 3 reads are correct and unflagged. Prints correct/wrong ×
  flagged/unflagged, silent errors split by catalogue outcome (a wrong
  exact hit vs `no_key`). Align GLOSSARY.md's *silent error* with the
  ADRs on a clean read of an illegible photo. Needed before any result
  is used without a person confirming it (ADR-0002)
- **mutation-test**: one mutation-testing run over `needs_review` in
  `pipeline.py` and `split_art_line`; add a test for each surviving
  mutant. Once, not in CI. Before results are used unconfirmed, with
  **flag-scorer**
- **silent-error-replay**: wrong-and-unflagged replay against
  `expected_art_base`, a diagnostic once **flag-scorer** exists
  (ADR-0001, *Evidence*, measured 18 of 84 against
  `expected_art_number`)
- **catalogue-scorer**: correct = the catalogue result is right for
  `expected_art_base` (`resolved_key` equals it if it's a catalogue key,
  else `no_key` and `art_base` equals it). Adds the catalogue md5 to the
  run fingerprint
- **line-exact**: line-exact per photo, for dev diagnosis
- **error-types**: per read, missed, confusion-pair swap, other single
  edit, joined text, wrong line, invented. Replaces CER, or CER stays
  dev-only
- **expected-legibility**: `expected_legibility` (readable / illegible /
  absent) and an excluded count, if dev needs illegible photos scored
  apart. Classify it in `MANIFEST_COLUMNS` first, add it to GLOSSARY.md
- **fake-read-mode**: a read returning `expected_art_line`, then delete
  `tests/report_split_on_truth.py`
- **multi-line**: a newline in the read; undecided, only if a dev run
  shows one
- **counterfeit-flag**. Decision: whether the possible-counterfeit flag
  stays a review reason (ADR-0005, *Flag table*). Season, year, brand
  and garment decoding stay for display; **season-precedence** decides
  the source on a catalogue hit
- **adr-0004**. Decision: the catalogue rules: catalogue misses
  (leaning: every miss flags); the confusion-pair margin; bare/compound
  pairs (ADR-0001, *Pending decisions*), fused pairs included; whether a
  confident hit relaxes no season in the code (`season_not_in_code`,
  ADR-0005). Same PR: `review_reasons`, CLAUDE.md's invariant and its
  restatements (GLOSSARY.md's catalogue outcome, "deliberately
  doesn't"; README.md, *Deliberate choices*), and the tests it inverts:
  `test_catalogue_miss_does_not_flag`,
  `test_pin_catalogue_miss_does_not_flag` and the split's pin tests
  (ADR-0005's accepted costs), named when they're written. Drafted from
  run 0's baseline (ADR-0001, *Pending decisions*)
- **doc-ref-test**: a test that the references in tracked docs resolve
  (files, symbols, test names), and that every name in *Next* is an
  open item; the reviewer's *Docs* check then drops that question
- **ledger-files**: `hooks/check_private.py`: take `TODO.md` out of
  `LEDGER_FILES`, so ledgers live only in `evals/BASELINES.md`
  (stricter; a `hooks/` change, needs sign-off)
- **claude-md-trim**: CLAUDE.md, docs branch: install row says
  `core.hooksPath` is yours, once per clone (agents are denied it); one
  line on private-data reads matching `.claude/settings.json`, with
  "eval, real" marked paid and run only when asked (test-set rules: link
  ADR-0002); merge the two `evals/README.md` rows of the one-home table
  and fold *Where to look* into it; line numbers to names; PR mechanics
  into `/open-pr`, keeping the approval stop, never merging, one topic
  per branch and no plan changes in passing; README's derived counts:
  drop them or name their source; move the eval-run working rules to
  `evals/README.md`; point the code-shaped allowlist at
  `PATTERN_EXEMPT_*` rather than restating it
- **cli-errors**: `cli()` in `main.py` prints a traceback on an API
  failure; `capture()` in `app/routes.py` already handles it
- **harness-types**: `get_art_number_reading` guesses the image type
  itself, not through `ACCEPTED`. A HEIC in the manifest would fail at
  the API
- **reviewer-repeat**: on the next branch with a full review, run
  round 1 twice on the same SHA and compare the reports. Evidence on
  whether round-2 findings are noise
- **pre-push**: `check_private.py --each-commit` plus `hooks/pre-push`
  running it, replacing `/open-pr` step 5's shell loop and catching
  `git commit -n`. Its docstring says `--file` and `--text` apply no
  exemptions. `hooks/README.md` becomes the one home for the check's
  output messages, which `/open-pr` and the reviewer classify; fix the
  stale "The reviewer's two patterns" comment in `check_private.py`. A
  `hooks/` change, needs sign-off
- **explore-trial**: use `/explore` on three real topics
  (**season-precedence**, a vague idea, a design choice). Change the
  skill only when a session goes wrong; if it feels scripted, loosen
  the opening question first
- **reviewer-report-format**: the reviewer's report has only the
  sections its format defines (it once added "Files referenced", with
  local paths)
- **open-pr-scripts**: `/open-pr`'s placeholder check and
  preconditions as a script; before a finding adds a sentence to a
  skill, ask whether it can be a test
- **ci-supply-chain**: LICENSE, Dependabot, zizmor, SHA-pinned actions,
  pip-audit, secret scanning
- **split-property-tests**: Hypothesis property tests for
  `split_art_line`
- **packaging**: `src/` layout and `uv_build`, removing the `sys.path`
  hacks; the harness moves out of `tests/` into the package. Before
  **zenml-eval-pipeline**
- **slice-report**: base-exact by format family, side and image size
  in the dev report, with a 95% interval beside each rate, resampling
  by garment; run 0's front-side misses were found by hand. Dev only:
  the test set stays totals-only (ADR-0002)
- **ci-privacy-patterns**: run `check_private.py`'s pattern checks in
  CI, if they can run without private values, so a clone without
  `core.hooksPath` is still checked. A `hooks/` change, needs sign-off
- **shared-photo-prep**: the eval harness's `photo_metadata` repeats
  `read_art`'s photo preparation (`upright()`) rather than sharing it. A
  test catches drift, but one function in `labels/` used by both would
  remove it. After **staff-trial**: the gate check for a new dependency
  needs `labels/` unchanged (*Staff trial* opener)

### Bugs and decisions
- **season-precedence**. Decision: on an exact catalogue hit the season
  comes from the parser, so it can disagree with the product name,
  unflagged (~3% of hits). Which source wins; the rule then goes in
  CLAUDE.md
- **brand-empty**. Decision: brand can come out empty unflagged: no
  printed-brand fallback, so a known season plus a catalogue miss gives
  `brand=None`. A `needs_review` decision
- **season-triage**: 70 parser/catalogue season disagreements,
  untriaged (`tests/report_art_number.py`): spot-check ten for parser
  bug vs catalogue typo
- **season-tables**: `SI_SEASON` and `CP_MODERN_SEASON` are built by a
  comprehension over a range at import, the formula CLAUDE.md forbids.
  Write both as literal dicts; no change in behaviour

### Out of phase 1
- **data-matrix**: Data Matrix ADR (new number; 0002 is taken) and
  stage: decode, keep Data Matrix only, parse `ART-Vnnnn-size-TOM…`. The
  payload's CLG tail is dropped at parse and never stored, logged or
  raised; QR and Code 128 contents are never returned. The vision path
  must be complete when the stage returns nothing
- **code-capture-guidance**: capture guidance in the web UI: back tag
  with the square code in frame, decode on upload, prompt for a retake
  if nothing decodes
- **adr-0001-runs**: ADR-0001 runs 2 (`text_orientation`, on its own
  rotated photos; decides whether `sideways` blocks), 3 (`next_line`)
  and 4 (size, brand, colour)
- **catalogue-index**: ADR-0003
- **catalogue-inspection**: bare/compound duplicates, keys with a suffix
  typed on, odd-length rows. The Stone Island numeric era-length table
  only on ADR-0005's trigger
- **parser-tests**: beyond the split: format detection, the
  `len(s) >= 8` guard, the `/181` strip, the `222` flag, the `'10'`
  carve-out. Season assertions wait for **season-triage**
- **docstring-framing**: `ArtNumberReading`'s docstring still says
  "framed on the ART number tag"; it reaches the model, so change it on
  its own and measure it
- **crop-to-label**: crop to the label region before the call (resizing
  is an **iterations** candidate)

## Inbox
Where new items land, from `/open-pr`'s *Follow-ups* or anywhere else. I
sort them into a section.
- **adr-0008-consequences-names**: ADR-0008, *Consequences* names
  a `docker-image` item and gunicorn lines in **web-hardening**; TODO.md has
  neither. Reword it on a docs branch
- **after-trial-prune**. Decision: whether to drop *After the trial* items
  the gate passed without, such as **cheaper-model** and
  **barcode-guidance**
- **milestone-section-rule**. Decision: whether TODO.md's "a section is
  named after the milestone it leads to" rule still fits *After the
  trial*, which leads to a pass or a fail, not one milestone
- **shorten-long-items**: shorten long items outside *Staff trial*
  (for example **adr-0004**, **claude-md-trim**, **pre-push**), as
  *Staff trial*'s were
- **saturated-vs-later-run**. Decision: whether **adr-0006-saturated** and
  **later-run-rule**, now both in *Before the first*, overlap

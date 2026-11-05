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
- **holdout-flag**
- **model-identity** (with **retries**)

## Phase 1

Any change to what the model sees is a run, one per run (*Iterations*),
except the model pin (**model-identity**).

### Gate attempt
The test-set rules, build order and what's recorded are in ADR-0002.

By Friday 2026-11-06:
- **incoming-photos**: 39 photos: 19 received 2026-11-03 in
  `images/incoming-3-11-2026/` (about 9 garments, several shots each, 4
  not upright) and 20 received 2026-11-04 in
  `images/incoming-4-11-2026/`. No exact duplicates. Test candidates
  under ADR-0002's rules; a garment already in dev is left out. Not in
  a manifest and not run until **freeze-test**
- **test-photographer**. Decision: who takes the test photos: some by
  staff, or note the single capture regime as a limitation
- **label-source-rule**: `evals/README.md`: the catalogue may prompt a
  re-check, never supply a label value
- **holdout-flag**: `--holdout` runs the test manifest, saves every
  read, and prints totals only: garment-sides correct, the count
  needed to pass, and the share of reads correct (ADR-0002).
  `evals/README.md`, *Held-out set*, says the harness doesn't read the
  set yet
- **model-identity**: pin the dated snapshot the alias resolves to
  today, and record the reported model name and token usage from the
  run result (outside `Extraction`) in the run header. Also the model
  settings sent (thinking, effort, max tokens, timeout) in a
  `model_settings` header field, with `--baseline` warning on a
  difference; set explicitly at today's defaults. Before
  **gate-attempt**: the gate and the staff trial run the pinned
  snapshot, recorded, not judged, by a paid dev run that becomes the new
  baseline (ADR-0002). Its BASELINES.md row says a difference can't be
  put down to the pin alone: `upright()` and `pillow` (PR #61) came
  after run 0, so expect "versions line differs"
- **retries**: set the client's and the agent's output retries
  explicitly (CLAUDE.md, *Engineering constraints*); each retry is
  another paid call. Log the request count per call; record worst-case
  latency in CLAUDE.md. Same branch as **model-identity**
- **results-backup**: back up `evals/results/` after each paid run,
  until **dvc-eval-set** covers it; the reports are the only record of
  paid reads, and `--replay` needs them

After Friday:
- **label-photos**: label every shot by eye (`garment`, `side`,
  `expected_art_line`, `expected_art_base`). Re-check by eye every
  `expected_art_base` that isn't a catalogue key. Convert any HEIC
  export to JPEG before it enters `evals/holdout/photos/`
- **test-set-check**: apply ADR-0002's test-set rules: product overlap
  with dev and `ART_PROMPT`'s examples checked pass/fail, no values
  printed; one shot per garment-side; rotate by hand
- **freeze-test**: record in BASELINES.md what ADR-0002 lists, before
  any run. Once `evals/holdout/manifest.csv` exists, the privacy hook
  blocks every commit until its ledger row is in: add both together
- **gate-attempt**: once, on the test set, from a tagged commit, totals
  only (ADR-0002). After **holdout-flag**, **model-identity** and
  **freeze-test**. The report says sides of one
  garment aren't independent: a pass means good enough to try, not a
  proven 80%

### Iterations
Only after a failed gate: the test set joins dev (ADR-0002).

#### Before the first
- **grown-baseline**: a paid run of the accepted configuration on the
  grown dev set, `--repeat 3`, recorded as the new baseline, not judged
  (ADR-0002)
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
  (**invented-examples**). The pinned snapshot is settled: recorded, not
  judged (ADR-0002). Also before the next input-side fix
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

## Staff trial
Phase 2, after a pass at *Gate attempt*: route B, agreed with the wider
team (ADR-0002, *Consequences*).

- **adr-phase-2**. Decision (wider team): the phase 2 ADR (ADR-0007):
  route B's scope and what's stored, the stop rule (e.g. corrections
  above X% after N items), the Sheet field (`art_base` or the full
  `art_line`, GLOSSARY.md), the manual-entry time the trial's time taken
  is compared with, and the trial's acceptance criteria. Before
  **staff-trial**
- **catalogue-required**. Decision first: does route B's app use the
  catalogue at all (it drives corrections and flags, and decides whether
  the catalogue is hosted)? If it does: the app refuses to start without
  the catalogue (today `load_catalogue()` returns `{}` and every read shows
  as a miss, unflagged), plus a `/health` route. App only: the CLI, tests
  and CI still run without it
- **privacy-adr**: a Certilogo code is never shown as a code, never in
  an identifying field and never logged; it is stored alongside the
  photo. Also: the logging allowlist (enums and fingerprints only,
  never `asdict(extraction)`), where stored photos and results live and
  for how long, what goes to the Google Sheet, and what tracing may
  record. Before **observability**
- **web-hardening**: CSRF, rate limits, security headers, upload
  checks (Pillow `verify()`, `MAX_IMAGE_PIXELS`), error type logged
  with the raw error hidden, gunicorn timeouts, and a kill switch: an
  environment flag that stops model calls and falls back to manual
  entry
- **docker-image**: a Docker image of the Python side, local only:
  catalogue mounted at run time and never baked in, gunicorn timeout
  above the worst-case call (**retries**). Needs no deploy and no
  **privacy-adr**, so it can come first
- **api-split-adr**: the staff app is a TypeScript frontend calling a
  Python API (decided). ADR before the split, which changes CLAUDE.md's
  *Flow* (`app/` is a Flask app today)
- **deploy**: deploy on a managed host, with auth at the platform edge.
  After **api-split-adr** and **privacy-adr**; Terraform later
  (**mlops-stack**)
- **mvp-confirm**: the confirm-or-edit screen in TypeScript (photo →
  read → confirm or edit), storing the photo, the read, the final value
  and the time taken (route B, ADR-0002)
- **sheets-push**: the confirmed ART number goes into the existing
  Google Sheet, in the field **adr-phase-2** sets. After **privacy-adr**
  (what goes to the Sheet)
- **observability**: one allowlisted record per read (**privacy-adr**):
  request ID, version (commit, prompt fingerprint, model), latency,
  tokens, cost, status, `needs_review` reasons, catalogue outcome, staff
  confirmation or edit, and input size, dimensions and whether it was
  rotated. Never a code, product name or photo filename. Alerts on
  daily spend, error rate, the `not_visible` rate and p95 latency
- **result-provenance**: each recorded result carries the model ID and
  prompt fingerprint that produced it, so a corrected result traces to
  its configuration
- **audit-sample**: check a random sample of confirmed results by eye
  now and then, and log the outcome; a confirmation isn't ground truth
- **later-run-rule**: the run rule for later runs (ADR-0006 revisit),
  with ADR-0001's per-run rule
- **upright-guidance**: capture guidance in the web UI: the photo must
  be upright (ADR-0002)
- **phone-upload-size**: measure real phone uploads through the form
  (size, dimensions) against the API's per-image limit. `upright()`
  re-encodes a tagged photo, and `p04` came out 16% larger. If near the
  limit, shrink only photos above it, on its own branch (resizing is an
  iteration variable)
- **staff-trial**: staff confirm or correct every result before it's
  recorded (ADR-0002, *Context*), under **adr-phase-2**. The result page
  shows the ART number only: decoder flags and product name hidden, code
  kept

## Later
- **feedback-loop**: production photos join an eval set only after
  labelling by eye, independently of the model and of staff
  corrections. Dev is frozen, so they go to test or a new set
  (ADR-0002). After **staff-trial**
- **monitoring**: review rate, correction rate, latency, and the
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
  anything else as **privacy-adr** allows
- **zenml-eval-pipeline**: a ZenML pipeline that orchestrates the eval
  harness (today `tests/eval_transcription.py`); scoring stays in one
  place. After **packaging** and **adr-0006-unit**: its promotion step
  uses the report's verdict
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
- ADR-0002's development-set rules open "There is no photo session and no
  grown-set baseline", then describe a grown-set baseline after a failed
  gate. Drop "and no grown-set baseline", or say "no photo-session baseline"

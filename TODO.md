# TODO

Current state and in-flight work. Stable architecture and invariants are in CLAUDE.md.

## Now

**2026-10-09: the approach changed.** Replaying the 2026-10-08 baseline's
reads through the parser, catalogue and gate showed 21% of positive reads
would publish wrong with no flag, mostly where a neighbouring code was joined
onto the ART number and declared `clear`. The model now transcribes the ART
number's whole printed line, and code does the interpreting:
`adr/0001-model-vs-code-responsibilities.md` holds the decision, the gate
and the rollout; the terms (`art_line`, `art_base`, …) are in `GLOSSARY.md`. A local scan found a
Data Matrix on newer Stone Island back tags that carries the ART number, `V`
code and size. Only 4 of the first 33 photos carry one (all 4 decode; `p34`–`p55` not scanned yet), so it becomes an
optional stage (ADR-0002, to write), not the core. The catalogue is frozen while the
reading is the focus. *The chain* below is the plan of record.

**Done before 2026-10-09:** `.env` key fixed and `.env.example` added (#11);
negative cases implemented, tested and documented (#12); the six pre-port
reports archived to `evals/results/archive/`. On 2026-09-25 the manifest grew
to 18 positives + 4 negatives, all ground truth re-checked by eye (see the md5
table). An unlisted Certilogo photo carries an ART number but is too hard to read, so
it was removed rather than used. Flask route tests merged (#18). CI added
(`.github/workflows/tests.yml`) ahead of the parser tests, by decision: on a
clean runner with no catalogue, 111 tests pass and 42 skip. What it does not
cover is under *Next*.

On 2026-10-08 the eval set was replaced: 28 positives + 5 negatives, ten new
garments including the first two C.P. pieces. The previous set, its manifest
and photos are in `evals/archive/` (gitignored). Photo numbers in *Known
issues*, *Decision rule* and *Current baseline* below refer to the archived
set unless they say otherwise.

### The chain

Strictly in order; each step's PR merges before the next starts. Commit, tag,
then run, and record every result here. Photos, manifest and results stay
gitignored, so this file is their only audit trail.

- [x] **1. Land the decision.** Commit the 2026-10-09 md5 row on
      its own, then the wording in `README.md` and `evals/README.md`, then
      ADR-0001 with the CLAUDE.md citation and this file. Code-reviewer, PR, merge.

- [x] **2. Ground truth for run 0.** Done 2026-10-19. `MANIFEST_COLUMNS`
      classified `id`, `garment`, `side`, `expected_art_line` and
      `expected_art_base` before the manifest was edited; the rules are in
      `evals/README.md` and the example in `evals/manifest.example.csv`. All
      five columns went into the manifest in one hand edit, checked by eye,
      so the ledger has one row (2026-10-19) and no id-only row. The stale
      `upside down` note on `p15` was removed: its Certilogo QR reads −2°, so
      the photo is upright. `expected_art_number` is unchanged and legacy.

- [ ] **3. `Resolution.matched_art` → `resolved_key`, and the `miss` status
      → `no_key`.** Its own PR with no change in what flags, so run 0's PR
      holds only behaviour. The `catalogue_match` value in the JSON output
      and `app/templates/result.html` change with it. Drop both *(not in code yet)* markers in
      `GLOSSARY.md`.

- [ ] **4. Run 0, behaviour (PR, no API calls).**
      - Family split in `art_number.py` into `art_caption`, `art_base`,
        `art_suffix`, `art_lot` and `art_unmatched` (`GLOSSARY.md`, *Parsing
        rules*, including its *Not yet decided* line). Scope agreed
        2026-10-18 with the glossary: the caption is recorded as
        `art_caption` as well as stripped, and the `?` and separator rules
        are new. Spaces carry no meaning: C.P. splits by
        fixed length, Stone Island numeric only at a printed slash. A remainder
        becomes `art_suffix` or `art_lot` only when it matches a known
        shape (base and suffix shapes from the catalogue, caption and lot
        shapes from labels); anything else is `art_unmatched`, which flags.
      - `pipeline.py` passes `art_base` to the existing `resolve()` (see
        *Catalogue: frozen*).
      - `review_reasons: list[str]` on `Extraction`, with
        `needs_review = bool(review_reasons)`. Consistency checks in plain
        code, not Pydantic validators, which would trigger hidden retries.
      - Tests for every observed failure shape: a C.P. colour code after a
        space; `V00NN` from the next line, with and without an invented slash;
        a slash suffix; a lot code; an `si_alpha` key with an 11-character base.
      - The era length table waits for the catalogue inspection (*Parallel*).
      - Drop the glossary's *(not in code yet)* markers for whatever lands.

- [ ] **5. Run 0, measurement (PR), then the new baseline.**
      - Scorer: wrong-and-unflagged (the primary metric), base-exact through
        the pipeline, and line-exact against `expected_art_line`, counted per
        garment-side as well as per photo. Reads both `art_number_raw` and
        `art_line`.
      - Merge, tag, and replay the 2026-10-08 baseline's saved reads. They
        cover only `p01`–`p33`, so the replay measures the new code on the old
        reads and nothing more. Then a paid `--repeat 3` run on the full
        manifest at the same tag; record that as the **new baseline**. The
        2026-10-08 report stays as the record of contract v1: superseded, not
        deleted.
      - Set ADR-0001's success thresholds (`<N>`, `<rate>`) from the last
        baseline recorded before run 1, so step 7 compares against the numbers
        they were set on: a second baseline (the `si_alpha` exception in
        *Photos*) re-sets them. From the first new baseline, decide ADR-0001's
        pending items (atypical length plus a miss, confusion-pair neighbours,
        uninspected pairs) and draft ADR-0003 and ADR-0004; a second baseline
        re-checks them, and a decision changes only if it contradicts it. The
        step 6 rotation run's result stands for the set it was measured on.
        ADR-0004 changes
        CLAUDE.md's "misses do NOT flag" invariant, so accepting it updates
        CLAUDE.md in the same PR.

- [ ] **6. The 2D-code stage (PR), then the rotation run.**
      - `labels/matrix.py`: decode, keep Data Matrix only, parse
        `ART-Vnnnn-size-TOM…`, and return a `CodeEvidence` (angle, art,
        variant, size, outcome). The payload's tail is the garment's CLG code:
        drop it at parse, and never store, log or raise it. QR and Code 128
        contents are never returned.
      - Rotation from any decoded code's angle with
        `im.rotate(angle, expand=True)` (sign verified on photos 8, 9 and 13),
        behind a flag that is off by default.
      - Per-field merge in `pipeline.py` with a `source` for each value; a
        disagreement with the vision read becomes a review reason.
        Synthetic-code tests (`zxing-cpp` can write codes as well as read
        them); `zxing-cpp` and `pillow` added with `uv add`. Write ADR-0002.
      - The vision path must be complete when the stage returns nothing. The
        eval scores it with the stage off and reports the 2D results
        separately.
      - Then one paid run: rotation on, against the new baseline.

- [ ] **7. Model runs 1–4**, as in ADR-0001's *Rollout*. One PR each; commit,
      tag and run on the branch, and merge only if it passes. Before run 1,
      make the eval's `prompt` fingerprint cover the output schema (see
      *Next*): runs 2–4 add output fields, which change only the schema. Run 2
      (orientation) runs with rotation off, or the upside-down photos arrive
      upright. Decide whether size is mandatory before run 4.

- [ ] **8. Capture guidance in the web UI.** Back tag with the square code in
      frame; decode on upload; prompt for a retake if nothing decodes.

- [ ] **9. Launch decision** on the held-out set: do clean reads auto-publish,
      or is every listing reviewed? (See *Open questions*.)

### Parallel, by eye

Starts now; each item blocks only what it names.

- [ ] **Catalogue inspection.** The six bare/compound duplicates and the other
      bare/compound pairs (~31 in all); the ~25 keys with a suffix typed on and
      no separator, many filed under a different product name from their bare
      key; and the odd rows: the `si_alpha` key with an 11-character base, the
      other 11-character `si_alpha` keys, the 9-character `cp_modern` key, the
      11-character `cp_transitional` key, a 10-digit key (the only key starting
      `01`), and a 10-character `si_numeric` key containing a `V00NN`-like run.
      Settle the Stone Island numeric era length table from bare-looking rows:
      it is frozen data, so a person decides it. Blocks only the era table and
      the uninspected-pairs decision.
- [ ] **Photos.** `K1S…` labels, which decide whether `S0…` codes print on the
      ART line; more front labels, to confirm the Certilogo tag sits level
      with the EAC label that carries the ART number (2 of 2 so far); new
      garments for a held-out set, not looked at while tuning
      (`evals/README.md`, *Held-out set*). The split:
      - `si_alpha` (`K1S…`) garments join the dev set before chain step 5's
        paid run. Once that baseline is recorded, the dev set is frozen for
        phase 1 and new photos go to the held-out set only, ~30 of them. The
        one exception: `si_alpha` garments found after step 5 but before run 1
        starts join the dev set, followed by the second paid baseline
        *Widen format coverage* describes. After run 1 starts, late `si_alpha`
        photos go to the held-out set.
      - Split by garment: no garment on both sides. Held-out photos come only
        from new garments, one photo per garment-side.
      - Every format family, `si_alpha` included, plus a few negatives, in the
        mix expected at launch.
      - Labelled by eye before any run. The held-out set runs once, at the end
        of the phase, and each use is recorded; studying its failures turns
        it into dev data.
      - The harness needs a `--holdout` flag (separate branch). `.gitignore`
        and the privacy hook already cover `evals/holdout/`.
- [x] **Positive count.** 28 is right: the 2026-10-08 set had 28 positive rows,
      and the report's `.photos.sha256` lists 33 photos. The 27 in the
      2026-10-08 run note and the `4f298e…` md5 row was a miscount, not a
      ground-truth edit; whether that version had 27 rows can no longer be
      checked.

### Catalogue: frozen

`labels/catalogue.py` keeps its current behaviour while the reading is the
focus. Planned, not started: an index derived from the unchanged CSV, a
confusion-pair margin on exact hits, and a flag on uninspected pairs
(ADR-0003 and ADR-0004). Known limitation meanwhile: looked up by
`art_base`, the 42 compound keys miss. Misses don't flag, so this costs
product names, not safety.

### Independent of the chain

Neither blocks nor is blocked by the sequence above.

- [ ] **Tidy this file.** Split done 2026-10-19 (baselines and md5 ledgers →
      `evals/BASELINES.md`, run procedure → `evals/README.md`, decision rule →
      ADR-0006). Left: the status block, history and [x] items, dangling
      references, rates without counts, line-number references, item titles
      that don't match their content, the "Moved to …" stubs once nothing
      points at them, ADR-0006's 2026-09-25 result and waiver (results belong
      in `evals/BASELINES.md`), and restated facts under *One home per fact*.

- [ ] **Replace the photo-hash recipe.** The recipe in `evals/README.md`'s
      *Eval run procedure* is broken (the manifest now starts with `id`;
      a filename has a space). The procedure saves photo hashes beside
      every report, so this is needed by the next paid run.

- [ ] **Widen format coverage in the eval set.** Partly done 2026-10-08:
      `cp_modern` (2 garments, 3 positive rows) and a trailing colour code
      (p08, p11) are now covered. Still missing: `si_alpha`
      (`K1S…`, 86 catalogue rows), which the eval has never tested. Add them
      before chain step 5's paid run, so that baseline covers them and no
      separate re-baseline is needed. If the `K1S…` labels can't be found in
      time, step 5 runs without them; if they turn up before run 1 starts, a
      second paid baseline follows once they're added (the one exception to
      the freeze, in *Photos*). After run 1 starts, they go to the held-out
      set.

- [ ] **Precedence fix: on an exact catalogue match, the catalogue supplies the
      season, not the parser.** `labels/pipeline.py:24-25` takes year/season
      from the parser even on an exact hit, so a listing ships with its title
      and its season field disagreeing — a `cp_modern` code whose product name
      says A/W 15 shows beside AW 2017, with `needs_review` False. Roughly 3% of catalogue
      hits. Latent rather than bleeding: pre-launch, nothing is shipping yet.
      Independent of the 71-row triage. This is a decision about which source of
      truth wins, not a refactor — once decided, the precedence rule belongs in
      CLAUDE.md domain rules.

### Done (previous chain)

Superseded by the 2026-10-08 set and the chain above: the duplicate-code
check, the negative count, both 2026-09-25 baselines, the whole-label prompt
change and the 2026-10-08 baseline. The full notes are in git history before
the 2026-10-09 TODO update.

### Eval run procedure

Moved to `evals/README.md`, *Eval run procedure*.

## Next

- [ ] **The catalogue misses codes printed with an attached colour suffix.**
      Will be fixed for bare catalogue rows by chain step 4, which passes
      `art_base` to `resolve()` instead of the raw read. Compound keys still
      miss until ADR-0003's index (see *Catalogue: frozen*); `resolved_key`
      replaces `matched_art` in step 3. Original note: `labels/pipeline.py:18`
      passes the raw read to `resolve()`, and
      `catalogue.normalise()` strips only spacing and case, so a correct read
      of a code with its colour suffix resolves `miss` while the bare code
      resolves `exact`. The
      parser already strips the suffix (`labels/art_number.py:124`); the
      catalogue side doesn't. Misses don't flag, so nothing surfaces it: the
      listing just loses its product name. Photo 7 in the 2026-10-08 set hits
      it on every correct read. The eval is unaffected (it scores against the
      manifest, not the catalogue). Fix in `catalogue.py` with a test on the
      synthetic-catalogue pattern so it runs in CI; decide whether
      `resolved_key` should carry the suffix.

- [ ] **Preprocessing experiment, for the six remaining misses.** The prompt
      change fixed most of what looked like a resolution problem (see Known
      issues); six photos still come back `not_visible`, five of them
      1200x1600. `labels/transcribe.py` passes raw bytes to `BinaryContent`
      with no crop and no resize, so nothing here is measured or controlled.
      Test order: re-shoot those labels at full resolution (free, no code),
      then try cropping to the label region before the call. Confirm the API's
      own downscale threshold while you're in there. Orientation is covered
      separately by chain step 6 (rotation from 2D codes), so this item is
      about crop and resolution only.

- [ ] **Run the `needs_review` gate invariants in CI.** CI has no catalogue,
      so both gate tests skip there: corrections forcing review
      (`TestNeedsReview::test_correction_flags_even_when_everything_else_is_clean`)
      and misses not flagging (`TestNeedsReview::test_catalogue_miss_does_not_flag`),
      along with `TestResolveCorrected` and `TestCorrectionSafety`. A green CI run says nothing about the gate.
      `TestResolveAmbiguous` (`tests/test_resolve.py:129-165`) already
      monkeypatches `labels.catalogue.load_catalogue` with a synthetic dict;
      add new tests on that pattern alongside the real-catalogue ones, not
      instead of them. Put the invented codes in `tests/synthetic.py` (the
      location CLAUDE.md's private-data rule allows), built by hand from the
      parser tables, never derived from the catalogue. Also add the two gate
      clauses with no test of their own: a catalogue `ambiguous` result, and
      `year is None` on a recognised format with no flags.

- [ ] **Parser unit tests for `labels/art_number.py`.** The split's tests come
      with chain step 4; the rest of this item stands. No pytest coverage,
      needs no catalogue, so they run in full in CI. Write the
      uncontroversial half now: format-family detection, the `len(s) >= 8`
      truncation guard, the `/181` colour-code strip, the `222` flag, the
      `0`→`O` repair, the `'10'` namespace carve-out. Hold the season
      assertions until after the 71-row triage, or you encode the bug as the
      expected value.

- [ ] **`ArtNumberReading`'s docstring still says "framed on the ART number
      tag"** (`labels/schemas.py`). **The fingerprint fix is needed before
      chain step 7, run 1:** runs 2–4 add output fields, which change only the
      schema, so without it their report headers would show an unchanged
      prompt. Unlike a function docstring, it reaches
      the model: pydantic puts it in the output schema sent with every call.
      So updating it to match the whole-label prompt is a behaviour change —
      make it on its own and measure it. Related gap: the eval's `prompt`
      fingerprint hashes only `ART_PROMPT`, so a schema-description edit
      moves nothing in the report header; consider hashing
      `ArtNumberReading.model_json_schema()` into it too.

- [ ] **Capture usage and cost per call.** `.usage()` is discarded in
      `transcribe_art`. One JSONL line per call:
      timestamp, model, prompt fingerprint, tokens in/out, latency, stop reason.
      One call per listing, so this is a unit-economics number. Also capture
      `response.model` into `run_metadata()` — check first whether it returns
      anything more specific than `claude-sonnet-5`; if it doesn't, note in
      `evals/README.md` that an unchanged prompt fingerprint beside a moved
      score means suspect the model. In the same piece of work, set the
      Anthropic client's retries and the agent's output retries explicitly
      (a client passed through pydantic-ai's provider, without breaking the
      `@cache`d `get_art_agent(model)` the eval harness relies on), log the
      request count per call, and record the resulting worst-case latency in
      CLAUDE.md beside the timeout rule.

- [x] **Remove the `details` plumbing.** Done ahead of run 4: the details
      prompt, agent and schema, the `details` inputs, the brand fallback and
      the five `Extraction` fields only it filled (`size`, `composition`,
      `made_in`, `certilogo`, `colour_observed`) are gone, and `art` is now
      required. The old code is at the `parked/details-read` tag. Run 4 of
      ADR-0001's rollout brings size, brand and colour back through the
      single ART call, under ADR-0001's field names.

- [ ] **Brand can come out empty unflagged.** `brand` comes only from
      `decoded.brand`; there is no printed-brand fallback. A clear read with a
      known season but a brand key missing from `BRAND`, plus a catalogue miss,
      gives `brand=None` and `needs_review=False`. A `brand-unknown` flag would
      fix it — a `needs_review` product decision. Run 4's `brand_printed`
      cross-check covers part of this, but only where brand text is printed:
      back tags carry none.

- [ ] **CLI error handling.** `main.py:36` calls `extract()` bare, so any API
      failure prints a ~40-line traceback instead of a message. The web path
      already handles this (`app/routes.py:51-52`); the CLI is the odd one out.

- [ ] **Cap eval spend.** `--repeat` is unbounded and `--workers` defaults to 4,
      so a mistyped `--repeat 30` is 450 vision calls. Print the call count up
      front, confirm past a threshold. No `max_tokens` on either agent either.
      Once closed this may earn a line in CLAUDE.md conventions.

- [ ] **Top-level README.** Two lines today; names none of the commands.

## Known issues

- **71 parser/catalogue season disagreements, untriaged.** `CP_MODERN_SEASON`
  samples look like a table offset. Spot-check ten by hand after the baseline —
  the goal is finding out whether these are parser bugs or catalogue typos,
  not fixing all 71. Until then, 97.0% is measured against ground truth that
  hasn't been verified.

- **Six photos still come back `not_visible` on every read.** Until
  2026-09-25 every 1200x1600 photo failed on every date, which pointed at
  capture resolution. The whole-label prompt change overturned most of that:
  6 of the 11 now read correctly on every read, so the prompt — which assumed
  a tightly framed tag, while these labels print the code bare and
  uncaptioned — was the larger cause. Resolution still correlates, though: 5
  of the 6 remaining misses are 1200x1600. And the change bundled several
  edits (whole label, bare code, nearby numbers to avoid), so which of them
  did the work isn't isolated.

  | photos | resolution | 2026-09-16 (archived) | 2026-09-24 (probe) | 2026-09-25, old prompt | 2026-09-25, current prompt |
  |---|---|---|---|---|---|
  | 01-04 | 4032x3024 | 2 of 4 | 3 of 4 | 3 of 4 | **4 of 4** |
  | 05-15 | 1200x1600 | 0 of 10 (photo 13 errored) | 0 of 11 | 0 of 11 | **6 of 11** |
  | 16-18 | 4032x3024 care labels | — | — | 1 of 3 | **2 of 3** |

  (09-24 figures are from unsaved probe runs; both 09-25 columns are saved
  reports, 3 reads per photo.)

  Still missed: 06, 08, 09, 10, 12 (1200x1600) and 17 (care label). Photo 12
  shares its expected code with 07, which now reads — whether it is a second
  shot of the same label is the open duplicate-code item above. Photo 17 is
  the care label of 01's garment, a different label from 01's tag. The
  cheapest test for all six is to re-shoot them at full phone resolution.

  The misses are `art_legible="not_visible"`: the model says no ART number is
  present at all, rather than misreading one. Attribution under concurrency
  was checked and is correct: each successful read matched its own photo.

- **The eval set measures a narrower surface than "OCR".** As of 2026-10-08:
  `si_numeric` and `cp_modern` only, no `si_alpha`; five negatives, all
  Certilogo-only labels. The set is lopsided: one garment is 6
  of 28 positives and four more have 4 rows each, so headline rates are
  weighted towards a few garments. Judge on the *per photo* table, and expect
  wins and losses to cluster by garment. Unlike the archived set, the
  positives are out-of-sample for the current prompt, and they are a single
  capture regime (1536x2048).

- **`evals/archive/photos/duplicates/` holds four `_dup` copies** (archived
  photos 05, 06, 08, 15). Inert — the harness is manifest-driven, not
  glob-driven. If they're second captures of the same labels they'd be useful
  as a capture-variance check; otherwise delete them.

## Open questions

- **Auto-accept clean reads, or human review every listing?** Decides what
  "better OCR" means: if a human checks each listing, overconfidence is mildly
  interesting; if clean reads auto-publish, it's the only metric worth driving
  down. Answer before spending eval runs. Now chain step 9; until then the
  guardrails and ADR-0004 assume clean reads may auto-publish.
- **Is size mandatory for a listing?** Decides whether an uncertain size
  blocks publishing or is just dropped. Needed before run 4 of ADR-0001's
  rollout.
- **What fraction of real listings miss the catalogue?** Decides how much the
  parser carries — on a hit the product name supplies the season, on a miss the
  parser is the only source.
- **What will production photos actually look like?** With the current
  prompt, 6 of 7 4032x3024 photos read against 6 of 11 1200x1600, so the
  smaller format still carries most of the misses. If production is
  full-resolution phone captures, the pipeline may work better than the
  baseline suggests; if it is the smaller format, expect roughly half of
  labels to need a re-shoot or review. Decides the target for the
  preprocessing experiment and which part of the eval set is the real one.
- Is 97.0% on `report_art_number.py` a floor that must not regress?
- What's the gate for shipping a prompt change — which metric, what margin, how
  many repeats before a difference is believed? *Decision rule* below is the
  one used so far; still open as a general policy.
- Does a separate care-label read come back, and on what model? It was switched
  off on 2026-10-08 and later removed (kept at the `parked/details-read` tag):
  only the ART number is wanted for now, and it halves the calls per listing.
  If it returns, consider a cheaper model than the ART read — "ordinary OCR on
  large clear text", never measured. Note
  that Haiku carries a dated model ID where Sonnet 5 doesn't, so whatever
  records the model must handle both shapes.
- Is the Flask app localhost-only or reachable? Decides whether the missing
  rate limit and auth on `POST /` matter.
- **Is `si_alpha` in phase 1?** Either `si_alpha` dev photos are required
  before step 5's paid run (one baseline, no freeze exception), or `si_alpha`
  is out of phase 1 and its listings always go to review. Decide in the
  `phase-1-acceptance` ADR; it also settles which tag a second baseline runs
  at.

## Decision rule for prompt changes

Moved to `adr/0006-decision-rule-for-prompt-changes.md`.

## Current baseline

Moved to `evals/BASELINES.md`, with both md5 ledgers.

## Dropped

- **"Pin the model to a dated snapshot."** Doesn't apply: `claude-sonnet-5` is
  the complete model ID for this family and appending a date would fail. The
  underlying risk — a model change being indistinguishable from a prompt change
  in a run diff — is **not** fully solved by the `response.model` capture folded
  into the usage task above; if that returns the same `claude-sonnet-5` string,
  it detects nothing. Treat it as partially mitigated until that check is done.
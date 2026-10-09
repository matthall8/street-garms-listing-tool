# TODO

Current state and in-flight work. Stable architecture and invariants are in CLAUDE.md.

## Now

**2026-10-09: the approach changed.** Replaying the 2026-10-08 baseline's
reads through the decoder, catalogue and gate showed 21% of positive reads
would publish wrong with no flag, mostly where a neighbouring code was joined
onto the ART number and declared `clear`. The model now transcribes the ART
number's whole printed line, and code does the interpreting:
`adr/0001-model-vs-code-responsibilities.md` holds the decision, the terms
(`art_line`, `style_code`, …), the gate and the rollout. A local scan found a
Data Matrix on newer Stone Island back tags that carries the ART number, `V`
code and size. Only 4 of 33 photos carry one (all 4 decode), so it becomes an
optional stage (ADR-0002, to write), not the core. The catalogue is frozen while the
reading is the focus. *The chain* below is the plan of record.

**Done before 2026-10-09:** `.env` key fixed and `.env.example` added (#11);
negative cases implemented, tested and documented (#12); the six pre-port
reports archived to `evals/results/archive/`. On 2026-09-25 the manifest grew
to 18 positives + 4 negatives, all ground truth re-checked by eye (see the md5
table). `si_certilogo_01.png` carries an ART number but is too hard to read, so
it was removed rather than used. Flask route tests merged (#18). CI added
(`.github/workflows/tests.yml`) ahead of the decoder tests, by decision: on a
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

- [ ] **1. Land the decision (this branch).** Commit the 2026-10-09 md5 row on
      its own, then the wording in `README.md` and `evals/README.md`, then
      ADR-0001 with the CLAUDE.md citation and this file. Code-reviewer, PR, merge.

- [ ] **2. Ground truth for run 0.** Add `expected_line` (the ART line exactly
      as printed, same-line caption included) and `expected_style` to the
      manifest, checked by eye before any result exists. Write both rules in
      `evals/README.md` and mark `expected_art_number` as legacy. Fix the stale
      `upside down` note on `si_art_number_photo_9_rotated.jpg`: its Certilogo
      QR reads −2°, so the photo is upright. Add an md5 row.

- [ ] **3. `Resolution.matched_art` → `matched_key`.** Its own PR with no
      change in behaviour, so run 0's PR holds only behaviour.

- [ ] **4. Run 0, behaviour (PR, no API calls).**
      - Family split in `art_number.py` into `style_code`, `art_suffix`,
        `art_lot` and `art_trailing`. Spaces carry no meaning: C.P. splits by
        fixed length, Stone Island numeric only at a printed slash. A remainder
        becomes `art_suffix` or `art_lot` only when it matches a shape seen in
        the catalogue; anything else is `art_trailing`, which flags.
      - `pipeline.py` passes `style_code` to the existing `resolve()` (see
        *Catalogue: frozen*).
      - `review_reasons: list[str]` on `Extraction`, with
        `needs_review = bool(review_reasons)`. Consistency checks in plain
        code, not Pydantic validators, which would trigger hidden retries.
      - Tests for every observed failure shape: a C.P. colour code after a
        space; `V00NN` from the next line, with and without an invented slash;
        a slash suffix; a lot code; an `si_alpha` key with an 11-character base.
      - The era length table waits for the catalogue inspection (*Parallel*).

- [ ] **5. Run 0, measurement (PR), then the new baseline.**
      - Scorer: wrong-and-unflagged (the primary metric), style-exact through
        the pipeline, and line-exact against `expected_line`, counted per
        garment-side as well as per photo. Reads both `art_number_raw` and
        `art_line`.
      - Merge, tag, and replay the 2026-10-08 baseline's saved reads. Record
        the result as the **new baseline**. The 2026-10-08 report stays as the
        record of contract v1: superseded, not deleted.
      - From the replay: set ADR-0001's success thresholds; decide its pending
        items (atypical length plus a miss, confusion-pair neighbours,
        uninspected pairs); draft ADR-0003 and ADR-0004. ADR-0004 changes
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
        them); `zxing-cpp` and `pillow` in `requirements.txt`. Write ADR-0002.
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
      11-character `cp_transitional` key, `0126422791` (the only key starting
      `01`), and a 10-character `si_numeric` key containing a `V00NN`-like run.
      Settle the Stone Island numeric era length table from bare-looking rows:
      it is frozen data, so a person decides it. Blocks only the era table and
      the uninspected-pairs decision.
- [ ] **Photos.** `K1S…` labels, which decide whether `S0…` codes print on the
      ART line; new garments for a held-out set, not looked at while tuning;
      more front labels, to confirm the Certilogo tag sits level with the EAC
      label that carries the ART number (2 of 2 so far).
- [x] **Positive count.** 28 is right: the manifest has 28 positive rows,
      and the report's `.photos.sha256` lists 33 photos. The 27 in the
      2026-10-08 run note and the `4f298e…` md5 row was a miscount, not a
      ground-truth edit; whether that version had 27 rows can no longer be
      checked.

### Catalogue: frozen

`labels/catalogue.py` keeps its current behaviour while the reading is the
focus. Planned, not started: an index derived from the unchanged CSV, a
confusion-pair margin on exact hits, and a flag on uninspected pairs
(ADR-0003 and ADR-0004). Known limitation meanwhile: looked up by
`style_code`, the 42 compound keys miss. Misses don't flag, so this costs
product names, not safety.

### Independent of the chain

Neither blocks nor is blocked by the sequence above.

- [ ] **Widen format coverage in the eval set.** Partly done 2026-10-08:
      `cp_modern` (2 garments, 3 positive rows) and a trailing colour code
      (`5215M226/2525`, 2 rows) are now covered. Still missing: `si_alpha`
      (`K1S…`, 86 catalogue rows), which the eval has never tested. Re-baseline
      after, since the manifest fingerprint changes.

- [ ] **Precedence fix: on an exact catalogue match, the catalogue supplies the
      season, not the decoder.** `labels/pipeline.py:33-35` takes year/season
      from the decoder even on an exact hit, so a listing ships with its title
      and its season field disagreeing — `03CMOW026A` shows "A/W 15 Soft Shell
      Goggle" beside AW 2017, with `needs_review` False. Roughly 3% of catalogue
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

`--repeat 3 --workers 1` on a clean tree. Save the manifest's photo hashes and
`pip freeze` beside the report, and record the manifest md5 before and after
any edit. Hash only the manifest's photos, not the whole folder:
`tail -n +2 evals/manifest.csv | cut -d, -f1 | (cd evals/photos && xargs shasum -a 256)`.
Serial running is a precaution against a suspected pydantic-ai concurrency
stall, never reproduced. `--workers` isn't recorded in the report header, so
put it in the `--note`.

## Next

- [ ] **The catalogue misses codes printed with an attached colour suffix.**
      Will be fixed for bare catalogue rows by chain step 4, which passes
      `style_code` to `resolve()` instead of the raw read. Compound keys still
      miss until ADR-0003's index (see *Catalogue: frozen*); `matched_key`
      replaces `matched_art` in step 3. Original note: `labels/pipeline.py:27`
      passes the raw read to `resolve()`, and
      `catalogue.normalise()` strips only spacing and case, so a correct read
      of `5215M226/2525` resolves `miss` while `5215M226` resolves `exact`. The
      decoder already strips the suffix (`labels/art_number.py:125`); the
      catalogue side doesn't. Misses don't flag, so nothing surfaces it: the
      listing just loses its product name. Photo 7 in the 2026-10-08 set hits
      it on every correct read. The eval is unaffected (it scores against the
      manifest, not the catalogue). Fix in `catalogue.py` with a test on the
      synthetic-catalogue pattern so it runs in CI; decide whether
      `matched_key` should carry the suffix.

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
      (`tests/test_pipeline.py:88-89`) and misses not flagging
      (`tests/test_pipeline.py:92`), along with `TestResolveCorrected` and
      `TestCorrectionSafety`. A green CI run says nothing about the gate.
      `TestResolveAmbiguous` (`tests/test_resolve.py:140-162`) already
      monkeypatches `labels.catalogue.load_catalogue` with a synthetic dict;
      add new tests on that pattern alongside the real-catalogue ones, not
      instead of them.

- [ ] **Decoder unit tests for `labels/art_number.py`.** The split's tests come
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
      One call per listing while the details read is off, so this is a
      unit-economics number. Also capture
      `response.model` into `run_metadata()` — check first whether it returns
      anything more specific than `claude-sonnet-5`; if it doesn't, note in
      `evals/README.md` that an unchanged prompt fingerprint beside a moved
      score means suspect the model.

- [ ] **Remove the `details` plumbing if the care-label read stays off.** The
      web form and CLI take one photo now, so nothing passes `details`. It
      still runs through `transcribe()` / `extract_bytes()` / `extract()`, with
      tests that only cover it (`test_brand_falls_back_to_the_printed_brand`,
      `TestFieldMapping` in `tests/test_pipeline.py`, and in its section 4
      `test_art_read_falls_back_to_the_details_photo` and
      `test_two_photos_only_the_art_photo_is_read`). Run 4 of ADR-0001's
      rollout moves size, brand and colour into the single ART call; if it
      passes, the details read and this plumbing can go.

- [ ] **Brand can come out empty unflagged.** With the details read off,
      `decoded.brand or det.brand_printed` has no fallback. A clear read with a
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

- **71 decoder/catalogue season disagreements, untriaged.** `CP_MODERN_SEASON`
  samples look like a table offset. Spot-check ten by hand after the baseline —
  the goal is finding out whether these are decoder bugs or catalogue typos,
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
  Certilogo-only labels. The set is lopsided: one garment (`741563051`) is 6
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
  decoder carries — on a hit the product name supplies the season, on a miss the
  decoder is the only source.
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
- When does the care-label read come back, and on what model? It's switched off
  in `transcribe()` (2026-10-08): only the ART number is wanted for now, and it
  halves the calls per listing. If it returns, consider a cheaper
  `DETAILS_MODEL` — "ordinary OCR on large clear text", never measured. Note
  that Haiku carries a dated model ID where Sonnet 5 doesn't, so whatever
  records the model must handle both shapes.
- Is the Flask app localhost-only or reachable? Decides whether the missing
  rate limit and auth on `POST /` matter.

## Decision rule for prompt changes

Committed before the first baseline existed, so no result could move it; reuse
it for the next prompt change. Everything is judged per photo across
`--repeat 3`, never on single reads. A photo is **missed** when 2 or more of
its 3 reads return no characters (the harness's `missed` definition). Read
every count below straight from the report's *per photo* table: its `missed`,
`overconfident` and `fabricated clear` columns. Every photo must have `reads`
3 in both runs; a run where any photo has fewer is rerun, not judged.

- **Win:** photos going from missed on the baseline to not missed with the
  new prompt (wins) must outnumber those going the other way (losses) by the
  two-sided sign test at p < 0.05:

  | losses | wins needed |
  |---|---|
  | 0 | 6 |
  | 1 | 8 |
  | 2 | 10 |
  | 3+ | reject |

  Photos 16–18 share garments with 03, 01 and 02, so if a win on one of a pair
  is needed to clear the bar, say so when reporting the result.
- **Guardrails** — failing either rejects the change, whatever else improves:
  - fabricated-and-clear stays at 0 across every negative read. Hard line.
  - no photo is *newly* overconfident in 2 or more of its 3 reads:
    `clear`, wrong, and no ambiguous characters flagged.
- The second guardrail assumes clean reads may be auto-accepted (see Open
  questions). Revisit it if every listing gets human review.
- **For the contract v2 runs** (chain step 7), this rule still decides
  `missed` and the guardrails. ADR-0001 adds wrong-and-unflagged, counted per
  garment-side, as the primary metric; its thresholds are set from run 0.
  Photo numbers in this section refer to the archived set.

**Result, whole-label prompt change (2026-09-25): passed.** 8 wins — photos
01, 05, 07, 11, 13, 14, 15, 16, eight different garments — and 0 losses
(p ≈ 0.008). No photo newly overconfident; fabricated-and-clear 0 of 12, and
no fabrication of any kind.

The rule as first written also required confirming a pass on photos outside
this set before merging, because a pass here is in-sample. That condition was
**waived for this merge** by decision, on confidence that the change is better
generally. It still applies in spirit: when new photos are added (see *Add
C.P. photos*), run the previous and current baselines on them and check the
gain holds.

## Current baseline

**2026-10-08 — whole-label `ART_PROMPT` on `anthropic:claude-sonnet-5`
(contract v1).** It stops being the comparison point once chain step 5
records the replay under the new scorer; it stays as the record of contract
v1.

- Report: `evals/results/20261008T154722Z-anthropic_claude-sonnet-5.json`
  (gitignored), with `.photos.sha256` and `.pip-freeze.txt` beside it.
- Code: tag `eval-baseline-2026-10-08` → `6cede38`, `dirty: False`; prompt
  fingerprint `4fc3298aa412`.
- Set: manifest md5 `02cfa7cb2065ae27e6944b62731651bc`; only notes have
  changed since. `--repeat 3 --workers 1`. 99 reads scored, no failures: 84
  positive (28 photos of 10 garments) and 15 negative.

| rate | value |
|---|---|
| missed | 25.0% |
| exact, positives | 46.4% (39 of 84) |
| overconfident | 28.6% |
| clear but wrong | 38.1% |
| flagged but correct | 0% |
| fabricated on no-code photos | 0% |
| fabricated and declared clear | 0% |
| wrong and unflagged (replay through decoder, catalogue and gate; not in the report) | 21% |

The largest failure was neighbouring codes joined onto the ART number and
declared `clear` (ADR-0001, *Evidence*). 31 of 33 photos returned the same
read on all three repeats; one upside-down photo returned three different
invented codes.

### Previous baselines (archived set)

**2026-09-25 — whole-label `ART_PROMPT` on `anthropic:claude-sonnet-5`.**

> Measured on the **archived** set (manifest md5 `cb3213…`, now in
> `evals/archive/`). Not comparable with any run on the 2026-10-08 set: the
> manifest fingerprint differs and no positive garment is shared. Kept as the
> record of the prompt change; superseded once the new baseline is recorded.

- Report: `evals/results/20260925T171017Z-anthropic_claude-sonnet-5.json`
  (gitignored), with the manifest's photo hashes (`.photos.sha256`) and
  `pip freeze` (`.pip-freeze.txt`) saved beside it — both identical to the
  previous baseline's.
- Code: tag `eval-baseline-2026-09-25b` → `b4b2622`, `dirty: False`.
- Set: manifest md5 `cb321369b2b7bd1e3b27eac7a6e9ff74` — 18 positives + 4
  negatives, in-sample, Stone Island only. `--repeat 3 --workers 1`.
  `--workers` isn't recorded in the report header, so put it in the `--note`.
- Completeness: 66 of 66 reads scored, no failures; every photo `reads` 3.

| rate | value | previous baseline |
|---|---|---|
| missed | **33.3%** (18 of 54 positive reads) | 77.8% |
| exact, positives | **66.7%** (36 of 54) | 22.2% |
| overconfident | 0% | 0% |
| clear but wrong | 0% (of 36 `clear` reads) | 0% (of 9) |
| flagged but correct | 0% | 0% |
| fabricated on no-code photos | 0% (0 of 12) | 0% |
| fabricated and declared clear | 0% | 0% |

Every photo returned the identical read on all three repeats — no run-to-run
noise, but in effect one sample per photo. Treat x/3 counts accordingly:

- **Read correctly 3/3:** 01–05, 07, 11, 13–16, 18 — 12 photos, all `clear`.
- **Missed 3/3:** 06, 08, 09, 10, 12, 17 (see Known issues).
- **Negatives:** all 12 reads returned no code.

Every read the model attempted was correct, so the clean confidence rates now
rest on 36 real attempts rather than on the model declining.

### Previous baseline

2026-09-25, the earlier `ART_PROMPT` (framed-tag wording) at tag
`eval-baseline-2026-09-25` → `3a6a45e`. Report
`evals/results/20260925T163049Z-anthropic_claude-sonnet-5.json`. Same set,
same settings, 66 of 66 reads scored. Missed 77.8%, exact 22.2% (12 of 54,
from photos 02, 03, 04, 18 only); every confidence rate 0%, mostly because 42
of 54 positive reads were `not_visible`. Photo 03's three correct reads were
labelled `partial`.

**Manifest md5 (the only tripwire on gitignored ground truth):**

| date | md5 | what changed |
|---|---|---|
| 2026-09-15→16 | not recorded | Photo 03's expected code changed by one digit. This happened before the tripwire existed and was found later in the archived reports: the same read scored a miss on 09-15 and exact on 09-16. It was almost certainly a transcription typo corrected: the new value is in the catalogue and the old one is not. Re-checked by eye 2026-09-25. |
| 2026-09-24 | `6e91e2f0e7c059542fde28fb57f58aa8` | Negative case added and row order adjusted. |
| 2026-09-25 | `4d583ebee12c3d72e3813013f1575437` | Trailing comma removed from the negative-case row; it had added a fourth, unnamed column. No expected value changed. |
| 2026-09-25 | `743c2fc3525c68b5271c4773a5584c0d` | Ground truth re-checked by eye. Now 18 positives + 4 negatives. The old negative renamed `si_details_photo_04.JPG` → `si_details_photo_01.JPG`; three new negatives `si_details_photo_02`–`04` (Certilogo crops); the three old care-label photos added as positives `si_art_number_photo_16`–`18` (same garments as photos 03, 01, 02). `si_certilogo_01.png` removed: it carries an ART number but is too hard to read. |
| 2026-09-25 | `cb321369b2b7bd1e3b27eac7a6e9ff74` | `si_details_photo_02`–`04` renamed `.JPG` → `.png` to match their real format; the extension sets the media type sent to the model. No expected value changed. Archived 2026-10-08 as `evals/archive/manifest.csv`. |
| 2026-10-08 | `4f298e4ceb31d67d8d7c8180a332a50a` | New eval set: 27 positives + 5 negatives, 10 garments, none shared with the archived set; first C.P. photos (2 `cp_modern` garments, 1 new negative) and `_rotated` variants. The four Certilogo negatives carried over byte for byte. Not run: 13 paths did not match the files on disk. |
| 2026-10-08 | `02cfa7cb2065ae27e6944b62731651bc` | Paths fixed to match files on disk (13 rows: zero-padding, `.JPG` case, space in `cp_art_number_photo_2 rotated.jpg`). `5215M226` → `5215M226/2525` on both photo-7 rows: the suffix is printed attached with a slash, per the `evals/README.md` rule; checked by eye. `si_art_number_photo_14_rotated.jpg` re-saved as a real 270° rotation; it had been byte-identical to the original. Expected values of photos 1, 4, 5, 9, 10, 14 and both C.P. positives re-checked by eye. Baseline `eval-baseline-2026-10-08` ran on this. |
| 2026-10-09 | `1a83e41cb8059ab1b2624a683818a487` | Notes only: `back of label` added to photos 5 and 19, both of which show the back "Art." tag (checked by eye). No photo or expected value changed, so the 2026-10-08 baseline still scores this set, but the `manifest` fingerprint differs, so `--baseline` will report it as changed. **Current.** |

Re-run `md5 -q evals/manifest.csv` after any edit and add a row. A changed md5
with no row here means an unrecorded ground-truth edit.

## Dropped

- **"Pin the model to a dated snapshot."** Doesn't apply: `claude-sonnet-5` is
  the complete model ID for this family and appending a date would fail. The
  underlying risk — a model change being indistinguishable from a prompt change
  in a run diff — is **not** fully solved by the `response.model` capture folded
  into the usage task above; if that returns the same `claude-sonnet-5` string,
  it detects nothing. Treat it as partially mitigated until that check is done.
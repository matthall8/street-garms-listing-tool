# TODO

Current state and in-flight work. Stable architecture and invariants are in CLAUDE.md.

## Now

**Done since last update:** `.env` key fixed and `.env.example` added (#11);
negative cases implemented, tested and documented (#12); the six pre-port
reports archived to `evals/results/archive/`. On 2026-09-25 the manifest grew
to 18 positives + 4 negatives, all ground truth re-checked by eye (see the md5
table). `si_certilogo_01.png` carries an ART number but is too hard to read, so
it was removed rather than used.

### The chain

Strictly in order. Note that everything here except this file lives in
gitignored territory — `evals/manifest.csv`, `evals/photos/` and
`evals/results/` are all untracked, so none of it produces a commit and none of
it leaves an audit trail. Record what you changed here.

- [ ] **Resolve the duplicate expected code.** `si_art_number_photo_07.JPG` and
      `si_art_number_photo_12.JPG` share one expected code. Either they are the
      same garment shot twice — one label double-weighted — or one row is wrong
      and a correct read of that photo scores as a miss on every future run.
      Note the 18 positives hold only 14 distinct codes: photos 16–18 are the
      care labels of the garments in 03, 01 and 02 by design, so wins on a pair
      are correlated, not independent. Also worth an eye: `01`/`06` and
      `10`/`14` are one character apart, `07`/`13`, `09`/`10` and `12`/`13` two;
      and photos `01` and `11` expect codes that are not in the catalogue.
      Note on `01`: its difference from `06` is `5` vs `1`, which is not a
      confusion pair, so the catalogue cannot bridge a misread there. A correct
      read of `01` resolves as `miss`, not `corrected`. Photo 01 is also
      `si_namespace` (`no-season-in-code`), so it sets `needs_review` whatever
      the read. Checking ground truth *before* any result exists is validation,
      not editing it to make a run pass.

- [x] **Decide the negative count — now or never for this baseline.** Four
      negatives as of 2026-09-25: one 4032x3024 care label and three ~976px
      Certilogo crops, a third capture regime. All four are CLG-type; an RN/CA
      care label or importer tag would widen what fabrication is tested on.

- [x] **Record the manifest md5 below before and after any edit.** It is the
      only tripwire on gitignored ground truth. Keep doing it.

- [x] **Record the baseline.** Done 2026-09-25 — see *Current baseline*.
      `--repeat 3 --workers 1` on a clean tree. Serial is cheap insurance
      against a suspected concurrency stall in pydantic-ai's
      thread-per-sync-task model; not reproduced against the real API here
      (5 runs, ~60 calls, no stalls), so it is precaution, not a fix. The
      `--note` should state: in-sample, Stone Island only, 18 positives + 4
      negatives, and the capture split — 4032x3024 (01–04, 16–18 and the
      `si_details_photo_01` negative), 1200x1600 (05–15), ~976px crops (the
      other three negatives). Save `pip freeze` and the hashes of the
      manifest's photos only beside the report — the photos are gitignored, so
      nothing else records which bytes were scored. Hashing the whole folder
      would break once held-out photos are added:
      `tail -n +2 evals/manifest.csv | cut -d, -f1 | (cd evals/photos && xargs shasum -a 256)`

- [ ] **Measure the stashed prompt draft.** `stash@{0}` ("On evals: prompt draft:
      unlabelled ART numbers"). Two cautions: it was created on `d56b51b`, which
      predates the `MODEL_SETTINGS` timeout commit and touches the same file, so
      after `git stash pop` confirm `MODEL_SETTINGS` still exists and is still
      passed to both agents. And the `--baseline` diff pairs repeats by index
      (`photo [2/3]` against `photo [2/3]`), which are unrelated samples —
      compare the *per photo* table's x/3 counts and the aggregate rates, not
      per-case flips.
      Third, and before anything is committed: the draft quotes values copied
      from eval photos, one of them a manifest code. Delete every such line
      (replace only where the draft stops making sense; a made-up value must
      miss the catalogue and the manifest), commit the stripped version, then
      `git stash drop`. The stripped version is the one measured. Judge the
      result against *Decision rule* below.

### Independent of the chain

Neither blocks nor is blocked by the sequence above.

- [ ] **Add C.P. photos to the eval set.** Split out of the harness work because
      it needs garments and a camera, not desk time — bundled, it stalls the
      whole item. The manifest is 14 `si_numeric` + 4 `si_namespace`: two of
      five format families, against the spec in `evals/README.md` *Choosing photos*. The
      catalogue holds 489 `cp_modern` and 86 `si_alpha` rows, so roughly a fifth
      of stock is a format the eval has never tested. `cp_modern` at minimum;
      ideally `si_alpha` and one with a trailing colour code. Re-baseline after,
      since the manifest fingerprint changes.

- [ ] **Precedence fix: on an exact catalogue match, the catalogue supplies the
      season, not the decoder.** `labels/pipeline.py:33-35` takes year/season
      from the decoder even on an exact hit, so a listing ships with its title
      and its season field disagreeing — `03CMOW026A` shows "A/W 15 Soft Shell
      Goggle" beside AW 2017, with `needs_review` False. Roughly 3% of catalogue
      hits. Latent rather than bleeding: pre-launch, nothing is shipping yet.
      Independent of the 71-row triage. This is a decision about which source of
      truth wins, not a refactor — once decided, the precedence rule belongs in
      CLAUDE.md domain rules.

## Next

- [ ] **Preprocessing experiment — now the leading candidate.** The measurement
      in Known issues reverses the assumption this item started with: the large
      4032x3024 photos are the ones that *work* (4 of 7 at baseline), and every
      1200x1600 photo fails. So the problem looks like too few pixels on the code, not
      downscaling of large images. `labels/transcribe.py:135-138` passes raw
      bytes to `BinaryContent` with no crop and no resize, so nothing here is
      measured or controlled. Test order: re-shoot a failing label at full
      resolution (free, no code), then try cropping to the label region before
      the call. Confirm the API's own downscale threshold while you're in there.

- [ ] **Decoder unit tests for `labels/art_number.py`** — no pytest coverage,
      needs no catalogue, so these are what make CI meaningful. Write the
      uncontroversial half now: format-family detection, the `len(s) >= 8`
      truncation guard, the `/181` colour-code strip, the `222` flag, the
      `0`→`O` repair, the `'10'` namespace carve-out. Hold the season
      assertions until after the 71-row triage, or you encode the bug as the
      expected value.

- [ ] **Capture usage and cost per call.** `.usage()` is discarded in
      `transcribe_art` / `transcribe_details`. One JSONL line per call:
      timestamp, model, prompt fingerprint, tokens in/out, latency, stop reason.
      Two calls per listing, so this is a unit-economics number. Also capture
      `response.model` into `run_metadata()` — check first whether it returns
      anything more specific than `claude-sonnet-5`; if it doesn't, note in
      `evals/README.md` that an unchanged prompt fingerprint beside a moved
      score means suspect the model.

- [ ] **CLI error handling.** `main.py:36` calls `extract()` bare, so any API
      failure prints a ~40-line traceback instead of a message. The web path
      already handles this (`app/routes.py:51-52`); the CLI is the odd one out.

- [ ] **Cap eval spend.** `--repeat` is unbounded and `--workers` defaults to 4,
      so a mistyped `--repeat 30` is 450 vision calls. Print the call count up
      front, confirm past a threshold. No `max_tokens` on either agent either.
      Once closed this may earn a line in CLAUDE.md conventions.

- [ ] **Top-level README.** Two lines today; names none of the commands.

- [ ] **CI on GitHub Actions.** After the decoder tests exist — without them a
      clean runner has no catalogue, most of the suite skips, and CI reports
      green while testing almost nothing.

## Known issues

- **71 decoder/catalogue season disagreements, untriaged.** `CP_MODERN_SEASON`
  samples look like a table offset. Spot-check ten by hand after the baseline —
  the goal is finding out whether these are decoder bugs or catalogue typos,
  not fixing all 71. Until then, 97.0% is measured against ground truth that
  hasn't been verified.

- **Capture resolution, not the prompt, may be the dominant variable.**
  The 2026-09-24 figures come from unsaved probe runs (one repeat,
  `--workers 4`); the 2026-09-25 baseline is the saved record. It confirms the
  low-resolution half. It weakens the high-resolution half: the new care-label
  photos 16–18 are 4032x3024 too, yet two of the three were missed every read,
  so at baseline high resolution is 4 of 7 photos (12 of 21 reads). Either the
  care labels are a confound (a whole label, the code small within it) or
  resolution explains less than this heading says. Three independent dates:

  | photos | resolution | 2026-09-16 (archived) | 2026-09-24 (probe) | 2026-09-25 (baseline, 3 reads each) |
  |---|---|---|---|---|
  | 01-04 | 4032x3024 | 2 of 4 | 3 of 4 | 3 of 4 (01 missed every read) |
  | 05-15 | 1200x1600 | **0 of 10** (photo 13 errored) | **0 of 11** | **0 of 11** (0 of 33 reads) |
  | 16-18 | 4032x3024 care labels | — | — | 1 of 3 |

  The robust half is the low-resolution result: no successful read on any
  date. The high-resolution half varies per photo across dates — photo 02 came
  back `not_visible` on 09-16 but read correctly on 09-24 and on all three
  baseline reads — so "mostly works" is as far as it goes.

  The failures are `art_legible="not_visible"`: the model says no ART number is
  present at all, rather than misreading one. Exact match on positives was
  22% at baseline (12 of 54 reads).
  Attribution under concurrency was checked and is correct: each successful
  read matched its own photo.

  Two consequences. First, the confidence rates look deceptively clean (0%
  overconfident, 0% fabricated), because a `not_visible` read can never be
  counted as wrong-but-confident. It is in the denominator of overconfident
  (all positives) but can never reach the numerator, and it is left out of the
  clear-but-wrong denominator entirely. So the numbers look reassuring only
  because the model declines to read. Second, the stashed prompt draft may be
  treating a symptom: if the low-resolution photos lack the pixels, no prompt
  rewrite recovers them. The cheapest test is to re-shoot two or three of the
  failing labels at full phone resolution and run again. With 18 positives this
  is a strong correlation with an obvious mechanism, not proof.

- **The eval set measures a narrower surface than "OCR".** Two of five format
  families (14 `si_numeric`, 4 `si_namespace`, no C.P. or alphanumeric), four
  negative cases all of one kind (Certilogo), and three capture regimes mixed
  into one score. The set is also
  in-sample: the prompt was tuned while looking at results on these photos, so
  the baseline is a development-set number, not an estimate of production.

- **`evals/photos/duplicates/` holds four `_dup` copies** (photos 05, 06, 08,
  15). Inert — the harness is manifest-driven, not glob-driven. If they're
  second captures of the same labels they'd be useful as a capture-variance
  check; otherwise delete them.

## Open questions

- **Auto-accept clean reads, or human review every listing?** Decides what
  "better OCR" means: if a human checks each listing, overconfidence is mildly
  interesting; if clean reads auto-publish, it's the only metric worth driving
  down. Answer before spending eval runs.
- **What fraction of real listings miss the catalogue?** Decides how much the
  decoder carries — on a hit the product name supplies the season, on a miss the
  decoder is the only source.
- **What will production photos actually look like?** Now the most consequential
  open question, not a detail. Only the 4032x3024 photos read successfully at
  all, so if production is full-resolution phone captures the pipeline may
  already work far better than the baseline suggests — and if it is the smaller
  format, the current answer is that it barely works. Decides the target for
  the preprocessing experiment and which half of the eval set is the real one.
- Is 97.0% on `report_art_number.py` a floor that must not regress?
- What's the gate for shipping a prompt change — which metric, what margin, how
  many repeats before a difference is believed? Answered for the stashed draft
  in *Decision rule* below; still open as a general policy.
- Could `DETAILS_MODEL` run on something cheaper? `labels/transcribe.py:15-17`
  says it could — "ordinary OCR on large clear text" — never measured. One
  `--model` run once a baseline exists, with a standing per-listing saving
  attached. Note that Haiku carries a dated model ID where Sonnet 5 doesn't, so
  whatever records the model must handle both shapes.
- Is the Flask app localhost-only or reachable? Decides whether the missing
  rate limit and auth on `POST /` matter.

## Decision rule for the stashed draft

Committed before the baseline exists, so no result can move it. Everything is
judged per photo across `--repeat 3`, never on single reads. A photo is
**missed** when 2 or more of its 3 reads return no characters (the harness's
`missed` definition). Read every count below straight from the report's
*per photo* table: its `missed`, `overconfident` and `fabricated clear`
columns. Every photo must have `reads` 3 in both runs; a run where any photo
has fewer is rerun, not judged.

- **Win:** photos going from missed on the baseline to not missed on the draft
  (wins) must outnumber those going the other way (losses) by the two-sided
  sign test at p < 0.05:

  | losses | wins needed |
  |---|---|
  | 0 | 6 |
  | 1 | 8 |
  | 2 | 10 |
  | 3+ | reject |

  Photos 16–18 share garments with 03, 01 and 02, so if a win on one of a pair
  is needed to clear the bar, say so when reporting the result.
- **Guardrails** — failing either rejects the draft, whatever else improves:
  - fabricated-and-clear stays at 0 across every negative read. Hard line.
  - no photo is *newly* overconfident in 2 or more of its 3 reads:
    `clear`, wrong, and no ambiguous characters flagged.
- The second guardrail assumes clean reads may be auto-accepted (see Open
  questions). Revisit it if every listing gets human review.
- A win here is in-sample: the unstripped draft quotes a code from this set.
  Before merging the draft, run both tagged commits on photos not seen while
  writing it.

## Current baseline

**2026-09-25 — current `ART_PROMPT` on `anthropic:claude-sonnet-5`.**

- Report: `evals/results/20260925T163049Z-anthropic_claude-sonnet-5.json`
  (gitignored), with the manifest's photo hashes (`.photos.sha256`) and
  `pip freeze` (`.pip-freeze.txt`) saved beside it.
- Code: tag `eval-baseline-2026-09-25` → `3a6a45e`, `dirty: False`.
- Set: manifest md5 `cb321369b2b7bd1e3b27eac7a6e9ff74` — 18 positives + 4
  negatives, in-sample, Stone Island only. `--repeat 3 --workers 1` —
  `--workers` isn't recorded in the report header or the note, so it rests on
  this line; put it in the `--note` on future runs.
- The photo hashes and pip freeze were written after the run finished, but
  from unchanged bytes: no manifest photo's mtime or ctime is later than 16:36
  BST, well before the run started (about 17:28 BST, going by the report's
  write time and task durations). Every hash still matches.
- Completeness: 66 of 66 reads scored, no failures; every photo `reads` 3.

| rate | value |
|---|---|
| missed | 77.8% (42 of 54 positive reads) |
| exact, positives | 22.2% (12 of 54) |
| overconfident | 0% |
| clear but wrong | 0% (of 9 `clear` reads) |
| flagged but correct | 0% |
| fabricated on no-code photos | 0% (0 of 12) |
| fabricated and declared clear | 0% |

Per photo, every photo returned the identical read on all three repeats — same
code, same legibility. So there was no run-to-run noise on this set, but the
three reads were in effect one sample per photo; photo 02 did vary across
earlier dates. Treat x/3 counts accordingly:

- **Read correctly 3/3:** 02, 03, 04, 18. These are the only photos the draft
  can lose.
- **Missed 3/3:** 01, 05–15, 16, 17 — 14 photos, the pool the draft can win
  from. It needs at least 6 wins with no losses, 8 with one, 10 with two (see
  *Decision rule*). Photo 05 is in-sample for the draft.
- **Negatives:** all 12 reads returned no code.
- 3 of the 12 correct reads — all three reads of photo 03 — were labelled
  `partial`. `needs_review` would send them to review, but *flagged but
  correct* doesn't count them — it keys on ambiguous characters only.

The confidence rates are clean mostly because the model declines: 42 of 54
positive reads were `not_visible`, so there were few chances to be
confidently wrong.

**Manifest md5 (the only tripwire on gitignored ground truth):**

| date | md5 | what changed |
|---|---|---|
| 2026-09-15→16 | not recorded | Photo 03's expected code changed by one digit. This happened before the tripwire existed and was found later in the archived reports: the same read scored a miss on 09-15 and exact on 09-16. It was almost certainly a transcription typo corrected: the new value is in the catalogue and the old one is not. Re-checked by eye 2026-09-25. |
| 2026-09-24 | `6e91e2f0e7c059542fde28fb57f58aa8` | Negative case added and row order adjusted. |
| 2026-09-25 | `4d583ebee12c3d72e3813013f1575437` | Trailing comma removed from the negative-case row; it had added a fourth, unnamed column. No expected value changed. |
| 2026-09-25 | `743c2fc3525c68b5271c4773a5584c0d` | Ground truth re-checked by eye. Now 18 positives + 4 negatives. The old negative renamed `si_details_photo_04.JPG` → `si_details_photo_01.JPG`; three new negatives `si_details_photo_02`–`04` (Certilogo crops); the three old care-label photos added as positives `si_art_number_photo_16`–`18` (same garments as photos 03, 01, 02). `si_certilogo_01.png` removed: it carries an ART number but is too hard to read. |
| 2026-09-25 | `cb321369b2b7bd1e3b27eac7a6e9ff74` | `si_details_photo_02`–`04` renamed `.JPG` → `.png` to match their real format; the extension sets the media type sent to the model. No expected value changed. **Current.** |

Re-run `md5 -q evals/manifest.csv` after any edit and add a row. A changed md5
with no row here means an unrecorded ground-truth edit.

## Dropped

- **"Pin the model to a dated snapshot."** Doesn't apply: `claude-sonnet-5` is
  the complete model ID for this family and appending a date would fail. The
  underlying risk — a model change being indistinguishable from a prompt change
  in a run diff — is **not** fully solved by the `response.model` capture folded
  into the usage task above; if that returns the same `claude-sonnet-5` string,
  it detects nothing. Treat it as partially mitigated until that check is done.
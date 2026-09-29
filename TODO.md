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

- [x] **Whole-label prompt change.** `ART_PROMPT` now expects the ART number
      to be printed bare, anywhere on a whole label, and names the nearby
      numbers not to confuse it with. Measured 2026-09-25 against the baseline
      and passed — see *Decision rule* and *Current baseline*. When comparing
      runs, use the *per photo* table's x/3 counts, not the `--baseline` diff's
      per-case flips (`photo [2/3]` against `photo [2/3]` are unrelated
      samples).

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

- [ ] **Preprocessing experiment, for the six remaining misses.** The prompt
      change fixed most of what looked like a resolution problem (see Known
      issues); six photos still come back `not_visible`, five of them
      1200x1600. `labels/transcribe.py` passes raw bytes to `BinaryContent`
      with no crop and no resize, so nothing here is measured or controlled.
      Test order: re-shoot those labels at full resolution (free, no code),
      then try cropping to the label region before the call. Confirm the API's
      own downscale threshold while you're in there.

- [ ] **Decoder unit tests for `labels/art_number.py`** — no pytest coverage,
      needs no catalogue, so these are what make CI meaningful. Write the
      uncontroversial half now: format-family detection, the `len(s) >= 8`
      truncation guard, the `/181` colour-code strip, the `222` flag, the
      `0`→`O` repair, the `'10'` namespace carve-out. Hold the season
      assertions until after the 71-row triage, or you encode the bug as the
      expected value.

- [ ] **`ArtNumberReading`'s docstring still says "framed on the ART number
      tag"** (`labels/schemas.py`). Unlike a function docstring, it reaches
      the model: pydantic puts it in the output schema sent with every call.
      So updating it to match the whole-label prompt is a behaviour change —
      make it on its own and measure it. Related gap: the eval's `prompt`
      fingerprint hashes only `ART_PROMPT`, so a schema-description edit
      moves nothing in the report header; consider hashing
      `ArtNumberReading.model_json_schema()` into it too.

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

- **The eval set measures a narrower surface than "OCR".** Two of five format
  families (14 `si_numeric`, 4 `si_namespace`, no C.P. or alphanumeric), four
  negative cases all of one kind (Certilogo), and three capture regimes mixed
  into one score. The set is also in-sample: it is the same set the prompt
  changes were measured and accepted on, so the baseline is a development-set
  number, not an estimate of production.

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
- Could `DETAILS_MODEL` run on something cheaper? `labels/transcribe.py:15-17`
  says it could — "ordinary OCR on large clear text" — never measured. One
  `--model` run once a baseline exists, with a standing per-listing saving
  attached. Note that Haiku carries a dated model ID where Sonnet 5 doesn't, so
  whatever records the model must handle both shapes.
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

**2026-09-25 — whole-label `ART_PROMPT` on `anthropic:claude-sonnet-5`.**

- Report: `evals/results/20260925T171017Z-anthropic_claude-sonnet-5.json`
  (gitignored), with the manifest's photo hashes (`.photos.sha256`) and
  `pip freeze` (`.pip-freeze.txt`) saved beside it — both identical to the
  previous baseline's.
- Code: commit `b4b2622`, `dirty: False`.
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
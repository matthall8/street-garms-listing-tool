# Eval baselines

Results, baselines and the manifest md5 ledgers. How to run an eval:
`evals/README.md`.

## Current baseline

**2026-10-30 — run 0: whole-label `ART_PROMPT` on
`anthropic:claude-sonnet-5`, upright development set.** The first paid
base-exact baseline ([ADR-0002](../adr/0002-phase-1-acceptance.md)),
recorded, not judged. The next run compares against its reads replayed at
that run's commit ([ADR-0006](../adr/0006-decision-rule-for-prompt-changes.md),
*Comparison point*). Development results don't count towards the gate.

- Report: `evals/results/20261030T133451Z-anthropic_claude-sonnet-5.json`
  (gitignored). Its header records the photos and versions; nothing is
  saved beside it.
- Code: tag `eval-baseline-2026-10-30` → `3f6efc2`, `dirty: False`. Fingerprints: prompt
  `4fc3298aa412` (the 2026-10-08 baseline's), user_message `3b608b481703`,
  schema `4e5d5d4c0601`, photos `5089f8d6983f`.
- Versions: Python 3.13.3, pydantic-ai 2.32.0, anthropic 0.122.0, pydantic
  2.13.4, pydantic-evals 2.32.0, as in `uv.lock`.
- Set: manifest md5 `eab250f6424d97a8d1717e70c0b2222c` (md5 ledger,
  2026-10-30): 47 photos, 40 positive and 7 negative, 30 garments, 36
  positive garment-sides. `--repeat 3 --workers 1` (`--workers` from the
  note).
- Completeness: 141 of 141 reads scored, no failures; every photo has 3
  scored reads.
- Cost: $1.71 (Anthropic console, before and after), about $0.012 per read.

| rate | value |
|---|---|
| positive garment-sides correct (at least 2 of 3 reads) | 88.9% (32 of 36) |
| reads correct | 85.0% (102 of 120 positive reads) |
| photos correct | 85.0% (34 of 40 positive photos) |
| negatives correct | 100% (7 of 7 negative photos) |
| negative reads returning an `art_base` (ADR-0006's guardrail) | 0 of 21 |
| left out: `UNKNOWN` | 0 of 47 photos |
| left out: unlabelled | 0 of 47 photos |

Three positive garment-sides have several photos (`g10` back, `g13` back,
`g13` front). On each, every photo has the same verdict, so the
garment-side count doesn't depend on how a side's photos combine. Every
photo returned the same read on all three repeats (47 of 47).

**Out-of-sample.** `p34`–`p55` and `p58` were added after the split was
designed against the 2026-10-08 reads; the rest (`p01`–`p33` survivors,
`p56`, `p57`) were not. No garment-side has photos in both groups.

| rate | out-of-sample | in-sample |
|---|---|---|
| positive garment-sides | 95.0% (19 of 20) | 81.3% (13 of 16) |
| positive photos | 95.0% (19 of 20) | 75.0% (15 of 20) |
| positive reads | 95.0% (57 of 60) | 75.0% (45 of 60) |
| negative photos | 2 of 2 | 5 of 5 |

Out-of-sample is 13.8 points higher on garment-sides, and 20.0 points
higher on photos and reads. The margin is a separate decision (TODO.md,
*Runs*, Iterations).

**Wrong positive garment-sides.** All 18 wrong reads are `not_visible` with
no characters returned: no wrong line, misread character or split failure.
All four sides are `front`, and each garment's `back` reads correctly.

| garment | side | photos | correct reads | cause |
|---|---|---|---|---|
| `g01` | front | `p01` | 0 of 3 | none returned |
| `g10` | front | `p21` | 0 of 3 | none returned |
| `g13` | front | `p26`, `p27`, `p57` | 0 of 9 | none returned |
| `g19` | front | `p50` | 0 of 3 | none returned (out-of-sample) |

Every other positive garment-side is correct on all 3 reads, so at most 4
garment-sides can score higher in the next run.

**Against the 2026-10-08 reads, photo by photo.** 23 photos are in both
runs and weren't replaced (md5 ledger, 2026-10-30): 19 positive, 4
negative. Between the two runs they have the same bytes, prompt, user
message, schema, library versions and model settings. Base-exact per
photo, against the 2026-10-29 replay:

| rate | 2026-10-29 replay | run 0 |
|---|---|---|
| positive photos correct | 14 of 19 | 15 of 19 |
| positive reads correct | 42 of 57 | 45 of 57 |
| negative photos correct | 4 of 4 | 4 of 4 |

One flip: `p11` (`g06` front), 0 of 3 → 3 of 3, the same on all three
reads. Nothing the model sees changed, so it is read-to-read noise or a
model change behind the undated alias (TODO.md, *Code*, model identity);
the reports can't tell which. Within this run every photo read
identically, so read-to-read noise is the less likely explanation, though
the reports can't rule it out. No other photo's correct-read count changed.

**Legacy metrics**, against the 2026-10-08 report. The photo sets differ
(*2026-10-08 baseline*, *Set*), so the totals don't compare.

| rate | run 0 | 2026-10-08 |
|---|---|---|
| missed | 15.0% (18 of 120 positive reads) | 25.0% (21 of 84) |
| exact, positives | 72.5% (87 of 120) | 46.4% (39 of 84) |
| overconfident | 10.0% (12 of 120) | 28.6% (24 of 84) |
| clear but wrong | 12.1% (12 of 99 `clear` reads) | 38.1% (24 of 63) |
| flagged but correct | 0% (0 of 120) | 0% (0 of 84) |
| fabricated on no-code photos | 0% (0 of 21 negative reads) | 0% (0 of 15) |
| fabricated and declared clear | 0% (0 of 21) | 0% (0 of 15) |

The 18 missed reads are the 18 base-exact misses. The other 15 legacy
misses, the 12 overconfident reads included, come from the legacy labels:
they are on `p03`, `p11`, `p19`, `p34` and `p55`, which are base-exact on
every read. No read is legacy-exact and base-wrong.

**Scope.** Positives are 37 `si_numeric` and 3 `cp_modern` photos, with no
`si_alpha`. `g13` has 5 of the 40 positive photos.

## Previous baselines

### 2026-10-08 baseline

**2026-10-08 — whole-label `ART_PROMPT` on `anthropic:claude-sonnet-5`
(contract v1).** Replaced as the comparison point by run 0 (*Current
baseline*); it stays as the record of contract v1. For base-exact, use its
replay (*Replay of the 2026-10-08 baseline*, below).

- Report: `evals/results/20261008T154722Z-anthropic_claude-sonnet-5.json`
  (gitignored), with `.photos.sha256` and `.pip-freeze.txt` beside it.
- Code: tag `eval-baseline-2026-10-08` → `6cede38`, `dirty: False`; prompt
  fingerprint `4fc3298aa412`.
- Set: manifest md5 `02cfa7cb2065ae27e6944b62731651bc`; it scored `p01`–`p33` only. Ten
  of those rows were removed by the upright rule (md5 ledger, 2026-10-30);
  the rest now differ from it only in notes and unscored columns; three
  `expected_art_number` cells changed in between and were restored (md5
  ledger, 2026-10-09, the first 2026-10-19 row's correction, and
  2026-10-29);
  `p34`–`p58` (the second
  2026-10-19 row, and 2026-10-30) are not in it. `--repeat 3 --workers 1`. 99 reads scored, no failures: 84
  positive (28 photos of 10 garments) and 15 negative.

| rate | value |
|---|---|
| missed | 25.0% (21 of 84 positive reads) |
| exact, positives | 46.4% (39 of 84) |
| overconfident | 28.6% (24 of 84) |
| clear but wrong | 38.1% (24 of 63 `clear` reads) |
| flagged but correct | 0% (0 of 84) |
| fabricated on no-code photos | 0% (0 of 15 negative reads) |
| fabricated and declared clear | 0% (0 of 15) |
| wrong and unflagged (replay through parser, catalogue and gate; not in the report) | 21% (18 of 84 positive reads; ADR-0001, *Evidence*; replay output not saved) |

The largest failure was neighbouring codes joined onto the ART number and
declared `clear` (ADR-0001, *Evidence*). 31 of 33 photos returned the same
read on all three repeats; one upside-down photo returned three different
invented codes.

**Scope.** The set measures a narrower surface than "OCR": `si_numeric` and
`cp_modern` only, no `si_alpha`; five negatives, all Certilogo-only labels.
It is lopsided: one garment is 6 of 28 positives and four more have 4 rows
each, so headline rates are weighted towards a few garments. Judge on the
*per photo* table, and expect wins and losses to cluster by garment. Unlike
the archived set, the positives are out-of-sample for the current prompt, and
they are a single capture regime (1536x2048).

### Replay of the 2026-10-08 baseline

`--replay` (`evals/README.md`, *Replaying a saved run*): the baseline's
saved reads through today's `from_reading()`, scored on base-exact
([ADR-0002](../adr/0002-phase-1-acceptance.md)). The first point on this
scale: no number from before the split was wired exists (main is tagged
`pre-split-wiring` if one is ever wanted).

**2026-10-29:** commit `e033296`, `dirty: False`, after `uv sync --locked`;
manifest md5 `94d41fd31287b33459f781fcef9672ae`. Report
`evals/results/20261029T100233Z-anthropic_claude-sonnet-5-replay.json`
(gitignored), `replay_of` the 2026-10-08 report. Correct: at least 2 of 3
reads. No failures.

| rate | value |
|---|---|
| photos correct | 64.3% (18 of 28 positive photos) |
| reads correct | 63.1% (53 of 84 positive reads) |
| negatives correct | 100% (5 of 5 negative photos) |
| left out: `UNKNOWN` | 0 of 33 photos |
| left out: unlabelled | 0 of 33 photos |
| legacy exact, positives | 56.0% (47 of 84) |

- In-sample: the split was designed against these reads, so this is a
  sanity check, not evidence (TODO.md, *Runs*).
- `p34`–`p55` have no saved reads, so they aren't scored.
- No read is legacy-exact and base-wrong.
- Legacy exact is 47 here against the baseline's 39 on the same reads,
  because three `expected_art_number` cells held the fabric code when this
  ran (md5 ledger, the first 2026-10-19 row's correction). They were
  restored on 2026-10-29, so compare run 0's legacy metrics with the
  2026-10-08 report, and its base-exact with this replay.
- The pooled Averages row moves because `base_exact` joined it, not
  because the reads changed.
- The source predates the provenance fields, so `user_message`, `schema`,
  `photos` and `versions` are `None` in the header.
- The 2026-10-08 baseline's scope applies (*Scope* above): no `si_alpha`,
  a lopsided set; judge per photo.

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
| missed | **33.3%** (18 of 54 positive reads) | 77.8% (42 of 54) |
| exact, positives | **66.7%** (36 of 54) | 22.2% (12 of 54) |
| overconfident | 0% (0 of 54) | 0% (0 of 54) |
| clear but wrong | 0% (0 of 36 `clear` reads) | 0% (0 of 9) |
| flagged but correct | 0% (0 of 54) | 0% (0 of 54) |
| fabricated on no-code photos | 0% (0 of 12) | 0% (0 of 12) |
| fabricated and declared clear | 0% (0 of 12) | 0% (0 of 12) |

Every photo returned the identical read on all three repeats — no run-to-run
noise, but in effect one sample per photo. Treat x/3 counts accordingly:

- **Read correctly 3/3:** 01–05, 07, 11, 13–16, 18 — 12 photos, all `clear`.
- **Missed 3/3:** 06, 08, 09, 10, 12, 17 (see *The six misses* below).
- **Negatives:** all 12 reads returned no code.

Every read the model attempted was correct, so the clean confidence rates now
rest on 36 real attempts rather than on the model declining.

**The six misses.** Until 2026-09-25 every 1200x1600 photo failed on every
date, which pointed at capture resolution. The whole-label prompt change
overturned most of that: 6 of the 11 now read correctly on every read, so the
prompt, which assumed a tightly framed tag while these labels print the code
bare and uncaptioned, was the larger cause. Resolution still correlates: 5 of
the 6 remaining misses are 1200x1600. The change bundled several edits (whole
label, bare code, nearby numbers to avoid), so which of them did the work isn't
isolated.

| photos | resolution | 2026-09-16 (archived) | 2026-09-24 (probe) | 2026-09-25, old prompt | 2026-09-25, current prompt |
|---|---|---|---|---|---|
| 01-04 | 4032x3024 | 2 of 4 | 3 of 4 | 3 of 4 | **4 of 4** |
| 05-15 | 1200x1600 | 0 of 10 (photo 13 errored) | 0 of 11 | 0 of 11 | **6 of 11** |
| 16-18 | 4032x3024 care labels | — | — | 1 of 3 | **2 of 3** |

09-24 figures are from unsaved probe runs; both 09-25 columns are saved
reports, 3 reads per photo.

The misses are `art_legible="not_visible"`: the model says no ART number is
present at all, rather than misreading one. Attribution under concurrency was
checked and is correct: each successful read matched its own photo. Photo 12
shares its expected code with 07, which reads; whether it is a second shot of
the same label was never settled before the set was archived. Photo 17 is the
care label of 01's garment, a different label from 01's tag. The cheapest test
for all six is a re-shoot at full phone resolution.

Judged by ADR-0006's rule as first written:

**Result, whole-label prompt change (2026-09-25): passed.** 8 wins — photos
01, 05, 07, 11, 13, 14, 15, 16, eight different garments — and 0 losses
(p ≈ 0.008). No photo newly overconfident; fabricated-and-clear 0 of 12, and
no fabrication of any kind.

### Previous baseline

2026-09-25, the earlier `ART_PROMPT` (framed-tag wording) at tag
`eval-baseline-2026-09-25` → `3a6a45e`. Report
`evals/results/20260925T163049Z-anthropic_claude-sonnet-5.json`. Same set,
same settings, 66 of 66 reads scored. Missed 77.8% (42 of 54), exact 22.2% (12 of 54,
from photos 02, 03, 04, 18 only); every confidence rate 0% (counts in the table above), mostly because 42
of 54 positive reads were `not_visible`. Photo 03's three correct reads were
labelled `partial`.

**Manifest md5 (the only tripwire on gitignored ground truth):** the last
row is current.

| date | md5 | what changed |
|---|---|---|
| 2026-09-15→16 | not recorded | Photo 03's expected code changed by one digit. This happened before the tripwire existed and was found later in the archived reports: the same read scored a miss on 09-15 and exact on 09-16. It was almost certainly a transcription typo corrected: the new value is in the catalogue and the old one is not. Re-checked by eye 2026-09-25. |
| 2026-09-24 | `6e91e2f0e7c059542fde28fb57f58aa8` | Negative case added and row order adjusted. |
| 2026-09-25 | `4d583ebee12c3d72e3813013f1575437` | Trailing comma removed from the negative-case row; it had added a fourth, unnamed column. No expected value changed. |
| 2026-09-25 | `743c2fc3525c68b5271c4773a5584c0d` | Ground truth re-checked by eye. Now 18 positives + 4 negatives. The old negative renamed archived negative 4 → archived negative 1; three new negatives archived negatives 2–4 (Certilogo crops); the three old care-label photos added as positives archived photos 16–18 (same garments as photos 03, 01, 02). An unlisted Certilogo photo removed: it carries an ART number but is too hard to read. |
| 2026-09-25 | `cb321369b2b7bd1e3b27eac7a6e9ff74` | Archived negatives 2–4 renamed `.JPG` → `.png` to match their real format; the extension sets the media type sent to the model. No expected value changed. Archived 2026-10-08 as `evals/archive/manifest.csv`. |
| 2026-10-08 | `4f298e4ceb31d67d8d7c8180a332a50a` | New eval set: 27 positives + 5 negatives (correction: 28 positives; 27 was a miscount, not a ground-truth edit), 10 garments, none shared with the archived set; first C.P. photos (2 `cp_modern` garments, 1 new negative) and `_rotated` variants. The four Certilogo negatives carried over byte for byte. Not run: 13 paths did not match the files on disk. |
| 2026-10-08 | `02cfa7cb2065ae27e6944b62731651bc` | Paths fixed to match files on disk (13 rows: zero-padding, `.JPG` case, space in p19). Colour suffix added to the expected code on both photo-7 rows: the suffix is printed attached with a slash, per the `evals/README.md` rule; checked by eye. p25 re-saved as a real 270° rotation; it had been byte-identical to the original. Expected values of photos 1, 4, 5, 9, 10, 14 and both C.P. positives re-checked by eye. Baseline `eval-baseline-2026-10-08` ran on this. |
| 2026-10-09 | `1a83e41cb8059ab1b2624a683818a487` | Notes only: `back of label` added to photos 5 and 19, both of which show the back "Art." tag (checked by eye). No photo or expected value changed, so the 2026-10-08 baseline still scores this set, but the `manifest` fingerprint differs, so `--baseline` will report it as changed. |
| 2026-10-19 | `769a3e4639b11da01f1fcd4ae606b36e` | `id`, `garment`, `side`, `expected_art_line` and `expected_art_base` added in one edit, checked by eye: 33 rows, 15 garments, 21 garment-sides. The id-only version was not saved, so it has no row. Stale `upside down` note on `p15` removed: the photo is upright. `expected_art_number` unchanged, so the 2026-10-08 baseline still scores this set, but the `manifest` fingerprint differs. (Correction, 2026-10-29: not unchanged. On `p03`, `p09` and `p19`, the three C.P. positives, `expected_art_number` was given the whole `expected_art_line` without its caption: the base plus the fabric code, which the legacy rule leaves out. Not recorded at the time, most likely made in this edit. Found by the 2026-10-29 replay: on the same saved reads, legacy exact on positives rose from 39 to 47 of 84, all 8 on these three photos. `expected_art_base` was unaffected: it is the 2026-10-08 value on all three. Restored on 2026-10-29: that row.) |
| 2026-10-19 | `94d41fd31287b33459f781fcef9672ae` | 22 rows added (`p34`–`p55`), checked by eye: 20 positives + 2 negatives, 15 new garments (`g16`–`g34`, some ids unused), 21 garment-sides, none shared with earlier rows. Whole set now 55 rows (48 positives + 7 negatives), 30 garments, 42 garment-sides. `p44`'s `expected_art_line` is `UNKNOWN`: the end of the lot code is under a thumb. Earlier rows unchanged. The new rows are scored, so the 2026-10-08 baseline no longer covers the whole set. (Correction, 2026-10-29: on `p34`, the C.P. positive, `expected_art_number` holds the base plus the fabric code, as on the three in the row above. Found by a manifest check on 2026-10-29, not by the replay: `p34` has no saved reads. `expected_art_base` was unaffected. Restored on 2026-10-29: that row.) |
| 2026-10-29 | `3c07d6ba25db6fc918a0361fb5bd7fa7` | Fixes after the 2026-10-29 replay and manifest check, checked by eye. `expected_art_number` on `p03`, `p09`, `p19` and `p34` set to `expected_art_base`: the fabric code removed, per the legacy rule (both 2026-10-19 rows' corrections), so legacy metrics on `p03`, `p09` and `p19` match the 2026-10-08 baseline again. `p11`'s `expected_art_line` given the `ART.` caption its unrotated original `p08` shows. `p35`'s note says what the photo shows. `rotated` added to the notes of `p11`, `p13`, `p15`, `p18`, `p19`, `p23`, `p25` and `p31`. No `expected_art_base` changed, so base-exact results are unaffected. Saved twice: the first save (`0b3043bb2b5ce1f5624b4279b684c2a9`, the `p11` and `p35` edits) has no row of its own. |
| 2026-10-30 | `eab250f6424d97a8d1717e70c0b2222c` | ADR-0002's upright rule (amended 2026-10-30): the dev set is now upright-only. 11 rows removed, 3 added. Removed, as each has an upright rotated copy already in the set: `p08`, `p09`, `p12`, `p14`, `p17`, `p22`, `p24`, `p32`. Replaced by a new row holding an upright rotation of the same photo: `p28` → `p56` (g14 front, negative), `p30` → `p57` (g13 front, a quarter turn; its remaining tilt is kept), `p35` → `p58` (g16 front, negative: a separate Certilogo tag, labelled `front` as `p35` was; `evals/README.md`, *Garment and side*). `p26` and `p27` (g13) are tilted less than 45°, so upright as they are. No photo carries an orientation tag. Whole set now 47 rows (40 positives + 7 negatives), 30 garments, 42 garment-sides. None left out of base-exact. The removed rows' reads in the 2026-10-08 baseline have no manifest row now, so a replay doesn't score them (`evals/README.md`, *Replaying a saved run*). Saved twice: the first save (`0e19ad02edce68d990e5421776546f06`, `p58` labelled `back`) has no row of its own. |

Re-run `md5 -q evals/manifest.csv` after any edit and add a row. A changed md5
with no row here means an unrecorded ground-truth edit.

**Held-out manifest md5** (`evals/holdout/manifest.csv`). The last row is
current. Empty until the set
exists; its first row goes in with the manifest's first row, since the hook
blocks every commit while the manifest has a header and no rows:

| date | holdout md5 | what changed |
|---|---|---|

Re-run `md5 -q evals/holdout/manifest.csv` after any edit and add a row here,
never in the table above.

## Split on truth

`tests/report_split_on_truth.py`: `split_art_line()` on each
`expected_art_line`, compared to `expected_art_base`. No model, so it checks
the labels and the split, not the pipeline.

**2026-10-28:** commit `fb02f71`, manifest md5
`94d41fd31287b33459f781fcef9672ae` (55 rows).

| group | rows |
|---|---|
| base matches | 47 |
| base differs | 0 |
| no base | 0 |
| no code (`NONE`) | 7 |
| excluded | 1 (`expected_art_line` `UNKNOWN`) |

No split problems and no edge whitespace on any line. Every checkable label agrees with ADR-0005's
split, separator rule included; the labels predate the ADR.

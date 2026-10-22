# Eval baselines

Results, baselines and the manifest md5 ledgers. How to run an eval:
`evals/README.md`.

## Current baseline

**2026-10-08 — whole-label `ART_PROMPT` on `anthropic:claude-sonnet-5`
(contract v1).** It stops being the comparison point once run 0's paid
full-manifest `--repeat 3` run (TODO.md, *Runs*) is recorded as the new
baseline; it stays as the record of contract v1.

- Report: `evals/results/20261008T154722Z-anthropic_claude-sonnet-5.json`
  (gitignored), with `.photos.sha256` and `.pip-freeze.txt` beside it.
- Code: tag `eval-baseline-2026-10-08` → `6cede38`, `dirty: False`; prompt
  fingerprint `4fc3298aa412`.
- Set: manifest md5 `02cfa7cb2065ae27e6944b62731651bc`; it scored `p01`–`p33` only. Those
  rows have changed only in notes and unscored columns since (md5 ledger,
  2026-10-09 and the first 2026-10-19 row); `p34`–`p55` (the second
  2026-10-19 row) are not in it. `--repeat 3 --workers 1`. 99 reads scored, no failures: 84
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

Judged by ADR-0006's decision rule:

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
| 2026-10-19 | `769a3e4639b11da01f1fcd4ae606b36e` | `id`, `garment`, `side`, `expected_art_line` and `expected_art_base` added in one edit, checked by eye: 33 rows, 15 garments, 21 garment-sides. The id-only version was not saved, so it has no row. Stale `upside down` note on `p15` removed: the photo is upright. `expected_art_number` unchanged, so the 2026-10-08 baseline still scores this set, but the `manifest` fingerprint differs. |
| 2026-10-19 | `94d41fd31287b33459f781fcef9672ae` | 22 rows added (`p34`–`p55`), checked by eye: 20 positives + 2 negatives, 15 new garments (`g16`–`g34`, some ids unused), 21 garment-sides, none shared with earlier rows. Whole set now 55 rows (48 positives + 7 negatives), 30 garments, 42 garment-sides. `p44`'s `expected_art_line` is `UNKNOWN`: the end of the lot code is under a thumb. Earlier rows unchanged. The new rows are scored, so the 2026-10-08 baseline no longer covers the whole set. |

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

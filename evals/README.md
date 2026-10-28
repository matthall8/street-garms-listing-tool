# Transcription evals

Photos, their manifest and run results stay local — label photos can carry live
Certilogo authentication codes and scannable QR codes for specific garments, and
saved reports contain the codes read from them. Only this README,
`BASELINES.md` and `manifest.example.csv` are tracked.

The harness is built on [pydantic-evals](https://ai.pydantic.dev/evals/). Each
photo is a case, each run produces a report, and reports are saved so a change
can be compared against the run before it.

## Setup

```
evals/
    photos/         your label photos
    manifest.csv    one row per photo (copy manifest.example.csv)
    holdout/        the held-out set; see below
        photos/
        manifest.csv    same columns as the dev manifest
    results/        one JSON report per run
```

`manifest.csv` columns:

| column | meaning |
|---|---|
| `id` | the row's own id: opaque, unique, and never changed once given. Not derived from the filename, a code or the product. Docs refer to a photo by it, and so does the report's photo record: a live run stops before any read if a row it runs has a blank or repeated `id` |
| `photo` | filename inside `evals/photos/`, **including the extension**. The extension sets the media type sent to the model, so it must match the file's real format — a PNG saved as `.JPG` goes out labelled `image/jpeg` |
| `garment` | an opaque id shared by every photo of one garment, negatives included. Not derived from the filename, a code or the product |
| `side` | which face of the label the photo shows: `front` or `back` (see [Garment and side](#garment-and-side)) |
| `expected_art_number` | **legacy.** The code as printed, plus an attached colour suffix — or `NONE`. Not authoritative; kept so reports from before run 0 stay comparable, and scored by the legacy metrics beside base-exact |
| `expected_art_line` | the ART line exactly as printed (see [Ground truth for the ART line](#ground-truth-for-the-art-line)) — or `NONE` |
| `expected_art_base` | the `art_base` (same section) — or `NONE` |
| `note` | free text, kept with the case in the saved report |

All of it is hand-checked by eye, never produced by code. `id`, `garment`
and `side` are public; the expected values and `photo` are private.

**Adding a column:** first commit its classification in `MANIFEST_COLUMNS`
(`hooks/check_private.py`), private for identifiers such as codes and
filenames, public for free text and categorical values, then edit the
manifest. The privacy hook blocks every commit while the manifest has a
column it can't classify. Every column in the table above is classified.

### Garment and side

Results are counted per garment-side, not per photo
(`adr/0001-model-vs-code-responsibilities.md`), so these two columns say
which photos are the same evidence.

- `front` is the label face with printed brand text: the care or EAC label,
  the Certilogo tag. `back` is the reverse "Art." tag, which carries no brand
  text and, on newer Stone Island garments, a Data Matrix.
- On a positive row, `side` is the face carrying the ART line. On a negative,
  it is the face shown.
- A rotated copy of a photo, or a second shot of the same face, has the same
  `garment` and `side` as the first, and its own `id`.
- A negative whose garment is in no other row still gets a `garment`, its
  own.
- A `garment` never appears in both the dev and the held-out manifest. That is
  the split rule (see [Held-out set](#held-out-set)), and `id`s don't repeat
  across the two either.

### Ground truth for the ART line

Terms are as in `GLOSSARY.md`. Both columns record what is printed on the
label, read from this photo or, where it's unclear here, from another photo of
the same garment-side. That fills in characters of a line this photo shows;
it never puts a line on a photo that doesn't show one. A photo with no ART
line in it is `NONE`, whatever the other photos of its garment-side show, so
a `front` Certilogo crop is `NONE` beside a positive EAC photo of the same
face. Never guess a character: if no photo shows it clearly,
write `UNKNOWN` and say why in `note`. Never fill a cell by running the
parser; a parser bug would then score as correct.

`expected_art_line` is the whole printed line containing the ART number:

- every character as printed, case and separators (`/`, `-`, `.`) included;
  one space for each printed gap
- a caption on the same line (`ART.`, `Art.`); a caption on its own line
  above is left out
- everything else on that line: a colour code, a lot code, any other text
- nothing from any other line, such as a variant code on the line below

`expected_art_base` is the `art_base`, read from that line by eye:

- the base code, season prefix included, with no spaces, in upper case
- without the caption, a colour suffix (attached by a slash or a hyphen, or
  after a space), a lot code or anything else on the line
- if you can't tell where it ends, say a suffix typed on with no separator,
  write `UNKNOWN` and say why in `note`

So the two differ from `expected_art_number` on purpose. For a line printed
as `ART. <code>/<suffix>`, `expected_art_line` is that whole line, `expected_art_base`
is `<code>`, and `expected_art_number` was `<code>/<suffix>`. Row `p04` of
`manifest.example.csv` shows it with invented values.

`NONE` and blank mean the same in both columns as in `expected_art_number`:
no ART number in the photo, and not labelled yet. They are explained under
[Negative cases](#negative-cases). `UNKNOWN` is a third state, for these two
columns only: labelled, but no value is safe. A blank cell in these two
columns is always work still to do; an `UNKNOWN` one is finished, and its
`note` says why.

The harness scores `expected_art_base` with base-exact and
`expected_art_number` with the legacy metrics. A row is scored if either is
labelled, by the metrics whose value it has; a row with neither is skipped
with a warning. Where the code itself can't be read safely, the legacy cell
stays blank, never `UNKNOWN`: the harness treats `UNKNOWN` there as blank,
with a warning. How line-exact treats spacing and case is the scorer's to
decide; the cells record both as printed so either is possible.

### What counts as the ART number (legacy)

This is the rule for the legacy `expected_art_number`, which the harness still
scores; new labelling follows the section above.

Expected values are compared ignoring spacing and case, so a code with a space
in it and the same code in lower case with no space both count as correct. Every other difference counts as
a miss.

`expected_art_number` is the ART number as printed, **plus its colour suffix**
if one is printed attached to it. In the catalogue that is a slash followed by
2–4 digits or a single letter (for example a slash and three digits), or a hyphen followed by a
single letter. Leave out:

- the `ART` / `ART.` caption
- lot or batch codes — anything marked `LOT` or batch, or a separate
  multi-part code printed after the ART number
- any other number printed nearby (phone numbers, dates, postcodes)

This is fixed independently of the prompt, so two prompts are always scored
against the same target. `exact` stays strict against it: a read that includes
a lot code or the caption is a miss, because that string would also miss the
catalogue in production (`labels/catalogue.py` strips only spacing and case).

### Negative cases

`expected_art_number` of `NONE` means **this photo contains no ART number at
all**. The correct outcome is that no code comes back; returning one is a
fabrication, which is the failure these cases exist to catch. A negative case
is scored on `exact` only — `cer` has no denominator, so it is left out of the
CER average rather than counted as zero.

`NONE` is safe as a sentinel because it is not a shape any real ART number can
take, so a genuine code can never be mistaken for it. (The parser is not
consulted during an eval run — the check is purely on the manifest string.)

A **blank** `expected_art_number` is different: it means *not labelled yet*,
unless `expected_art_line` and `expected_art_base` beside it are `UNKNOWN`.
Then the code itself can't be read safely, the blank legacy cell is
finished, and `note` says why. Either way, the legacy metrics don't score
those rows, and a row with no usable `expected_art_base` either is skipped
with a warning on stdout. The two
states must not be conflated — a blank row silently treated as a negative would
score an unlabelled photo as passing whenever the model read nothing.

## Held-out set

`evals/holdout/` is a second set kept out of tuning, so a score on it says how
the pipeline does on labels nobody tuned against. Its `manifest.csv` has the
same columns as the dev manifest above, with `photo` naming a file in
`evals/holdout/photos/`; which photos it may hold is in
[ADR-0002](../adr/0002-phase-1-acceptance.md). Both are gitignored, and the privacy hook treats
its filenames and expected codes as private, as it does the dev set's.

- No garment is in both sets; holdout photos come only from new garments,
  each with a `garment` id not used in the dev manifest.
- One photo per garment-side, so no repeat shots or rotated copies, which
  the dev set allows.
- Every row is labelled by eye before any run.
- It runs only for a gate attempt, and each use is recorded in
  `evals/BASELINES.md`. Studying its failures turns those photos into dev
  data. Phase 1's run limit, tagged-commit and totals-only rules, and what
  happens on a fail, are in
  [ADR-0002](../adr/0002-phase-1-acceptance.md).
- Its md5 has its own ledger table in `evals/BASELINES.md`, headed
  `| date | holdout md5 | what changed |`. The hook blocks every commit while
  the manifest has a header and no rows, so write its first row and commit the
  matching ledger row together. Once that table has a row, the hook also
  blocks every commit in a clone where the held-out manifest is missing.

The harness doesn't read it yet: a `--holdout` flag that prints totals only
is planned (TODO.md, *Code*).

## Running

```bash
.venv/bin/python tests/eval_transcription.py --model test          # offline, no API calls
.venv/bin/python tests/eval_transcription.py --note "baseline: current prompt"
.venv/bin/python tests/eval_transcription.py --model anthropic:claude-opus-5
```

| option | what it does |
|---|---|
| `--model` | model to read with (default: the pipeline's ART model). `test` returns a fixed fake reading, for checking the harness without API credit |
| `--workers N` | reads at once (default: 4); ignored by `--replay` |
| `--limit N` | only the first N photos in the manifest |
| `--repeat N` | read every photo N times — see [Comparing runs](#comparing-runs) |
| `--note "..."` | what this run is testing, saved in the report header |
| `--baseline FILE` | compare this run against a saved report |
| `--no-save` | don't write the report to `results/` |
| `--replay FILE` | rescore a saved report's reads, with no API call — see below |

A read that fails — a missing photo, an API error, a call that stalls past the
60 s timeout — goes in the **Case Failures** table and is left out of every
per-read score. An outage can't masquerade as bad transcription. Base-exact's
photo rule still counts it as one of the photo's runs (see
[What to look at](#what-to-look-at)).

### Replaying a saved run

`--replay evals/results/<report>.json` feeds that report's reads through
`from_reading()` and every metric, with today's code and today's manifest:
how a parser, split or catalogue change is measured at no cost (ADR-0002).

- The reads fix the model and the repeat, and every replay is saved, so
  `--model`, `--repeat`, `--limit`, `--baseline` and `--no-save` are
  rejected. It runs serially.
- Expected values come from the current manifest, matched by photo
  filename. A photo in only one of the two is named on stdout and not scored.
- A read that failed in the source run fails again, so the photo keeps its
  `--repeat` runs.
- Saved as `<stamp>-<model>-replay.json`. Its header has what the reads
  came from, copied from the source: `model`, `prompt`, `user_message`,
  `schema`, `photos`, `photo_hashes` and `repeat` (`None` where the source
  predates a field). It has this run's `commit`, `dirty`, `versions` and
  `manifest`, and `replay_of`. Commit first: on a dirty tree it warns, since
  the recorded commit isn't the code that scored.

### Eval run procedure

`--repeat 3 --workers 1` on a clean tree. Run `uv sync --locked` first, so
the environment is the tagged commit's `uv.lock`; the header's `versions`
shows it was. The harness records the photos it sends in the header
(`photos`, `photo_hashes`), so nothing is saved beside the report by hand.
Baselines from before those fields keep their saved `.photos.sha256` and
`.pip-freeze.txt`; ones from before `uv.lock` existed are rebuilt from that
`.pip-freeze.txt`. Record the manifest md5 before and after any edit.
Serial running is a precaution against a suspected pydantic-ai concurrency
stall, never reproduced. `--workers` isn't recorded in the report header, so
put it in the `--note`.

## What to look at

Each photo gets a row with:

- **exact** — ✔ or ✗ against `expected_art_number`. The Averages row's pass
  rate pools it with `base_exact`, and positive cases with negative ones, so it
  is **not** comparable to an earlier run and shifts if the mix changes. The
  per-kind rates below, the base-exact rates and the per-photo tables are the
  ones to compare
- **cer** — character error rate: edits needed to reach the expected code,
  divided by its length. It moves before exact match does, so it's the more
  sensitive signal when comparing two prompts or two models. Shown as `-` on
  negative cases, which are excluded from its average
- **legibility** — what the model said: `clear`, `partial`, `illegible` or
  `not_visible`
- **kind** — `positive` or `negative`; the Averages row shows the mix, which is
  how you check the set still covers what you think it does
- **base_exact** — ✔ or ✗: base-exact against `expected_art_base` (see
  [Base-exact](#base-exact))
- **base_kind** — `positive`, `negative`, `unknown` or `unlabelled`, from
  `expected_art_base`; the last two have no `base_exact`

Below the table, rates across the whole run.

The first four are computed over **positive cases only**, so adding negative
cases never moves them. The last three of these mean exactly what they meant
before negative cases existed:

**missed** — the model returned no characters for a photo that has a code: null
or blank, whether it labelled the read `not_visible` or `illegible`. A read of
all `?` counts as an attempt, since the model found the code. This separates
*didn't find it* from *misread it*, which exact and cer both lump together — a
miss scores cer 1.0 just like a completely wrong read. It also explains a
suspiciously clean overconfident rate: a read the model declines as
`not_visible` or `illegible` can never be confidently wrong. (An empty read
labelled `clear` is incoherent but possible, and counts as both missed and
overconfident.)

**overconfident** — the model said `clear`, got the code wrong, and flagged no
characters as ambiguous. This is the closest thing here to a "silently wrong"
rate, but read it carefully: **it is not the rate at which a wrong listing gets
published.** That gate is `needs_review` (`labels/pipeline.py:40-48`), which
also consults the parser and the catalogue, so this number is wrong in both
directions:

- a confidently wrong read the catalogue *corrects* does get flagged, so this
  **overstates** the risk;
- a confidently wrong read that decodes cleanly and either misses the catalogue
  or lands on a *different real* code publishes with nothing flagged, and this
  number cannot distinguish it from the flagged kind, so it **understates** the
  failure that actually matters.

To get the publish-gate number, run `from_reading()` (`labels/pipeline.py`) on
each read in a saved report and count reads that are wrong with `needs_review`
False. It's the app's own gate, and costs no API calls.

**clear but wrong** is the same failure measured only over reads the model
called `clear` — how far `clear` can be trusted. It's omitted when no read was
`clear`.

**flagged but correct** is the opposite failure — noise in the review queue.
A high number here means staff learn to ignore the flag.

The next two are computed over **negative cases only**, and are omitted when
the set has none:

**fabricated on no-code photos** — the model returned a code for a photo that
has none. A prompt change that pushes the model to search harder will move this
first, and it is invisible on an all-positive manifest.

**fabricated and declared clear** — the same failure, asserted confidently. This
is the negative-case counterpart of **overconfident**, and the one that *can*
put an invented code on a listing with nothing flagged. Like overconfident, it
is not a publish rate: most invented codes fail to decode, get the parser flag
`unrecognised`, and are caught by `needs_review`. The dangerous ones are those
that happen to decode cleanly — for example a digit string whose first two
digits are a valid season number — which pass the gate unflagged.

Last, a **per photo** table: one row per photo, counting its reads across
`--repeat`. `reads` is how many were scored — fewer than `--repeat` means that
photo lost a read to a failure, and a photo that lost every read still gets a
row, with `reads` 0. The other columns count reads out of `reads`:

- `exact` — on a positive, the code was read correctly; on a negative, no code
  came back
- `missed` and `overconfident` — positives only
- `fabricated clear` — negatives only

These use the same per-read tests as the rates above, so summed over photos
they reproduce them. This is the table to compare two runs on: a photo is the
unit, and the repeats of one photo are not independent evidence. Widen the
terminal if the photo names are cut off; the saved report always has them in
full.

### Base-exact

The phase 1 metric ([ADR-0002](../adr/0002-phase-1-acceptance.md)): a read
is correct when `from_reading()`'s `art_base` equals `expected_art_base`,
ignoring spacing and case. On a negative (`NONE`), correct means no
`art_base`. Rows whose `expected_art_base` is `UNKNOWN` or blank are left out
and counted. Three tables:

- **base-exact (correct: at least 2 of 3 reads)**: the rule, from the run's
  `--repeat` (a majority: 1 of 1 for a single read), then each rate as `n`
  of `of`:
  - `photos correct`: positive photos with a majority of their runs
    correct. A failed read is one of those runs, so a photo that lost one
    still needs 2. The photo is the unit, as a test garment-side is one photo
  - `reads correct`: positive reads, failed ones left out. Production reads
    once, so this is the single-read rate
  - `negatives correct`: negative photos, by the same rule; kept out of the
    correct rate, as the test set has none
  - `left out: unknown`, `left out: unlabelled`: photos, out of all photos
- **base per photo**: garment, side, `base_kind`, scored reads, correct
  reads and the photo's ✔ or ✗
- **garment-sides**: photos, correct photos and left-out photos per side.
  Counts only: the dev set has deliberate hard variants of one side (rotated
  copies), so no rule turns a side's photos into one verdict

## Comparing runs

Every report records what produced it, shown in its header:

| field | meaning |
|---|---|
| `model` | the model that did the reads |
| `commit` | the git commit the harness ran from |
| `dirty` | `True` if tracked files had uncommitted changes — e.g. an unsaved prompt edit |
| `prompt` | fingerprint of the ART prompt; changes if any character of it does |
| `user_message` | fingerprint of the text sent with each photo (`ART_USER_MESSAGE`) |
| `schema` | fingerprint of the output schema the model sees (`ArtNumberReading.model_json_schema()`), field descriptions and docstrings included |
| `versions` | Python and the installed `pydantic-ai`, `anthropic`, `pydantic` and `pydantic-evals`; `not installed` for a missing one |
| `photos` | fingerprint over `photo_hashes`: two runs sent the same photos if it matches |
| `photo_hashes` | sha256 of each photo the run sent, by manifest `id`; `None` for a missing photo. Only the cases run, so `--limit` narrows it. In the saved report, not the printed header |
| `manifest` | fingerprint of `manifest.csv`; changes if any byte does — a photo or expected value, but also a note or a column the harness doesn't score |
| `limit`, `repeat`, `note` | as passed on the command line |
| `replay_of` | replays only: the saved report whose reads were rescored |

To test a change:

1. Run a baseline before changing anything:
   `--repeat 3 --workers 1 --note "baseline: current prompt, workers 1"`
2. Make **one** change — a prompt edit, a model swap.
3. Run again against it:
   `--repeat 3 --workers 1 --note "whole-label search, workers 1" --baseline evals/results/<baseline>.json`

The diff shows what changed in the header (`prompt: 8f1e… → 3a7c…`) and, per
photo, results that flipped (`✔ → ✗`). With `--repeat` those flips pair
`photo [2/3]` against `photo [2/3]`, which are unrelated samples, so judge the
change on the two **per photo** tables instead. The diff prints only the new
run's table; print the baseline's from its saved report:

```bash
COLUMNS=120 .venv/bin/python -c "import sys; from pydantic_evals.reporting import EvaluationReportAdapter as A; A.validate_json(open(sys.argv[1],'rb').read()).print()" evals/results/<baseline>.json
```

Things that make a comparison meaningless:

- **Different `--repeat`.** Repeats rename cases (`photo [1/3]`) and the diff
  matches cases by name, so every case shows as added. The script warns you.
- **A different photo, `schema`, `user_message` or `versions`.** None of
  them is the change under test, and a library upgrade can change what's
  sent without moving `schema`. `--baseline` warns on each before any read,
  names the photo `id`s that changed or are in one run only, and says when
  the baseline predates the field. `prompt` and `model` don't warn: a
  comparison usually changes one on purpose.
- **A different `manifest` fingerprint, for a scored reason.** The runs
  scored different photos or different expected values. A note or an unscored
  column changes the fingerprint too; the md5 ledger's "what changed" column
  in `evals/BASELINES.md` says which it was.
- **One run each.** The same photo can read correctly on one run and not the
  next, so use `--repeat 3` before trusting a difference. Set sizes are in
  [ADR-0002](../adr/0002-phase-1-acceptance.md).

Reports saved before the move to pydantic-evals use an older format and can't
be used as a baseline.

## Choosing photos

Set sizes are in [ADR-0002](../adr/0002-phase-1-acceptance.md). Aim for a
spread, not many of the same thing:

- C.P. Company pieces where one label carries everything
- Stone Island where the ART number is on its own tag
- Stone Island where the ART number is printed bare, with no "ART" prefix,
  near the importer text at the bottom of the care label
- Faded, garment-dyed pieces where the print is genuinely marginal
- At least one of each format family — numeric, alphanumeric `K1S…`, C.P.
  modern `03CMOW…`, and one with a trailing colour code

Include a couple you expect to fail. A set where everything passes cannot tell
you whether a change helped.

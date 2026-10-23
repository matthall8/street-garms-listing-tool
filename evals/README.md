# Transcription evals

Photos, their manifest and run results stay local — label photos can carry live
Certilogo authentication codes and scannable QR codes for specific garments, and
saved reports contain the codes read from them. Only this README and
`manifest.example.csv` are tracked.

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
| `id` | the row's own id: opaque, unique, and never changed once given. Not derived from the filename, a code or the product. Docs refer to a photo by it |
| `photo` | filename inside `evals/photos/`, **including the extension**. The extension sets the media type sent to the model, so it must match the file's real format — a PNG saved as `.JPG` goes out labelled `image/jpeg` |
| `garment` | an opaque id shared by every photo of one garment, negatives included. Not derived from the filename, a code or the product |
| `side` | which face of the label the photo shows: `front` or `back` (see [Garment and side](#garment-and-side)) |
| `expected_art_number` | **legacy.** The code as printed, plus an attached colour suffix — or `NONE`. Not authoritative; kept so reports from before run 0 stay comparable, and still what the harness scores |
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

Every row keeps an `expected_art_number`, new rows included, until the scorer
reads these two columns: the harness skips a row where it is blank. Where the
code itself can't be read safely, the legacy cell stays blank, never
`UNKNOWN`: the harness would score `UNKNOWN` as a code, so it skips such a
row with a warning. How
line-exact treats spacing and case is the scorer's to decide; the cells
record both as printed so either is possible.

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
finished, and `note` says why. Either way, those rows are skipped with a warning on stdout rather than scored. The two
states must not be conflated — a blank row silently treated as a negative would
score an unlabelled photo as passing whenever the model read nothing.

## Held-out set

`evals/holdout/` is a second set kept out of tuning, so a score on it says how
the pipeline does on labels nobody tuned against. Its `manifest.csv` has the
same columns and rules as the dev manifest above, with `photo` naming a file
in `evals/holdout/photos/`. Both are gitignored, and the privacy hook treats
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
| `--workers N` | reads at once (default: 4) |
| `--limit N` | only the first N photos in the manifest |
| `--repeat N` | read every photo N times — see [Comparing runs](#comparing-runs) |
| `--note "..."` | what this run is testing, saved in the report header |
| `--baseline FILE` | compare this run against a saved report |
| `--no-save` | don't write the report to `results/` |

A read that fails — a missing photo, an API error, a call that stalls past the
60 s timeout — goes in the **Case Failures** table and is left out of every
score. An outage can't masquerade as bad transcription.

### Eval run procedure

`--repeat 3 --workers 1` on a clean tree. Run `uv sync --locked` first, so
the environment is the tagged commit's `uv.lock`. Save the manifest's photo
hashes and `uv pip freeze` (`.pip-freeze.txt`) beside the report: the
freeze shows the sync was run. Baselines from before `uv.lock` existed are
rebuilt from their own saved `.pip-freeze.txt`. Record the manifest md5
before and after any edit. Hash only the manifest's photos, not the whole folder:
`tail -n +2 evals/manifest.csv | cut -d, -f1 | (cd evals/photos && xargs shasum -a 256)`.
Broken (the manifest now starts with `id`; a filename has a space): don't
use; the harness will hash the photos itself (TODO.md's *Eval provenance* item).
Serial running is a precaution against a suspected pydantic-ai concurrency
stall, never reproduced. `--workers` isn't recorded in the report header, so
put it in the `--note`.

## What to look at

Each photo gets a row with:

- **exact** — ✔ or ✗; the Averages row shows the share that passed. Note this
  share pools positive and negative cases, so it is **not** comparable to a run
  recorded before negative cases existed, and it shifts if the positive/negative
  mix changes. The per-kind rates below are the ones to compare
- **cer** — character error rate: edits needed to reach the expected code,
  divided by its length. It moves before exact match does, so it's the more
  sensitive signal when comparing two prompts or two models. Shown as `-` on
  negative cases, which are excluded from its average
- **legibility** — what the model said: `clear`, `partial`, `illegible` or
  `not_visible`
- **kind** — `positive` or `negative`; the Averages row shows the mix, which is
  how you check the set still covers what you think it does

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
published.** That gate is `needs_review` (`labels/pipeline.py:37-44`), which
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

## Comparing runs

Every report records what produced it, shown in its header:

| field | meaning |
|---|---|
| `model` | the model that did the reads |
| `commit` | the git commit the harness ran from |
| `dirty` | `True` if tracked files had uncommitted changes — e.g. an unsaved prompt edit |
| `prompt` | fingerprint of the ART prompt; changes if any character of it does |
| `manifest` | fingerprint of `manifest.csv`; changes if any byte does — a photo or expected value, but also a note or a column the harness doesn't score |
| `limit`, `repeat`, `note` | as passed on the command line |

To test a change:

1. Run a baseline before changing anything:
   `--repeat 3 --note "baseline: current prompt"`
2. Make **one** change — a prompt edit, a model swap.
3. Run again against it:
   `--repeat 3 --note "whole-label search" --baseline evals/results/<baseline>.json`

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
- **A different `manifest` fingerprint, for a scored reason.** The runs
  scored different photos or different expected values. A note or an unscored
  column changes the fingerprint too; the md5 ledger's "what changed" column
  in `evals/BASELINES.md` says which it was.
- **One run each.** The same photo can read correctly on one run and not the
  next. With 15 photos a single flip moves exact match by about 7 points, so
  use `--repeat 3` before trusting a difference.

Reports saved before the move to pydantic-evals use an older format and can't
be used as a baseline.

## Choosing photos

Aim for 10–15 with a spread, not a hundred of the same thing:

- C.P. Company pieces where one label carries everything
- Stone Island where the ART number is on its own tag
- Stone Island where the ART number is printed bare, with no "ART" prefix,
  near the importer text at the bottom of the care label
- Faded, garment-dyed pieces where the print is genuinely marginal
- At least one of each format family — numeric, alphanumeric `K1S…`, C.P.
  modern `03CMOW…`, and one with a trailing colour code

Include a couple you expect to fail. A set where everything passes cannot tell
you whether a change helped.

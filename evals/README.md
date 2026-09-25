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
    results/        one JSON report per run
```

`manifest.csv` columns:

| column | meaning |
|---|---|
| `photo` | filename inside `evals/photos/`, **including the extension**. The extension sets the media type sent to the model, so it must match the file's real format — a PNG saved as `.JPG` goes out labelled `image/jpeg` |
| `expected_art_number` | the code as printed, hand-checked by eye — or `NONE` |
| `note` | free text, kept with the case in the saved report |

Expected values are compared ignoring spacing and case, so `05CMSH022A 004275A`
and `05cmsh022a004275a` both count as correct. Every other difference counts as
a miss.

### What counts as the ART number

`expected_art_number` is the style code as printed, **plus its colour suffix**
if one is printed attached to it. In the catalogue that is a slash followed by
2–4 digits or a single letter (`581540846/181`), or a hyphen followed by a
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
take, so a genuine code can never be mistaken for it. (The decoder is not
consulted during an eval run — the check is purely on the manifest string.)

A **blank** `expected_art_number` is different: it means *not labelled yet*.
Those rows are skipped with a warning on stdout rather than scored. The two
states must not be conflated — a blank row silently treated as a negative would
score an unlabelled photo as passing whenever the model read nothing.

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
published.** That gate is `needs_review` (`labels/pipeline.py:50-56`), which
also consults the decoder and the catalogue, so this number is wrong in both
directions:

- a confidently wrong read the catalogue *corrects* does get flagged, so this
  **overstates** the risk;
- a confidently wrong read that decodes cleanly and either misses the catalogue
  or lands on a *different real* code publishes with nothing flagged, and this
  number cannot distinguish it from the flagged kind, so it **understates** the
  failure that actually matters.

To get the publish-gate number, replay `parse` + `resolve` over a saved report
and count reads that are wrong with `needs_review` False. That costs no API
calls.

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
is not a publish rate: most invented codes fail to decode, get the decoder flag
`unrecognised`, and are caught by `needs_review`. The dangerous ones are those
that happen to decode cleanly — for example a digit string whose first two
digits are a valid season number — which pass the gate unflagged.

## Comparing runs

Every report records what produced it, shown in its header:

| field | meaning |
|---|---|
| `model` | the model that did the reads |
| `commit` | the git commit the harness ran from |
| `dirty` | `True` if tracked files had uncommitted changes — e.g. an unsaved prompt edit |
| `prompt` | fingerprint of the ART prompt; changes if any character of it does |
| `manifest` | fingerprint of `manifest.csv`; changes if a photo or expected value does |
| `limit`, `repeat`, `note` | as passed on the command line |

To test a change:

1. Run a baseline before changing anything:
   `--repeat 3 --note "baseline: current prompt"`
2. Make **one** change — a prompt edit, a model swap.
3. Run again against it:
   `--repeat 3 --note "whole-label search" --baseline evals/results/<baseline>.json`

The diff shows what changed in the header (`prompt: 8f1e… → 3a7c…`) and, per
photo, results that flipped (`✔ → ✗`).

Things that make a comparison meaningless:

- **Different `--repeat`.** Repeats rename cases (`photo [1/3]`) and the diff
  matches cases by name, so every case shows as added. The script warns you.
- **A different `manifest` fingerprint.** The runs scored different photos or
  different expected values.
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
  modern `03CMOW…`, and one with a trailing colour code like `581540846/181`

Include a couple you expect to fail. A set where everything passes cannot tell
you whether a change helped.

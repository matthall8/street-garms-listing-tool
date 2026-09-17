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
| `photo` | filename inside `evals/photos/` |
| `expected_art_number` | the code as printed, hand-checked by eye |
| `note` | free text, kept with the case in the saved report |

Expected values are compared ignoring spacing and case, so `05CMSH022A 004275A`
and `05cmsh022a004275a` both count as correct. Every other difference counts as
a miss.

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

- **exact** — ✔ or ✗; the Averages row shows the share that passed
- **cer** — character error rate: edits needed to reach the expected code,
  divided by its length. It moves before exact match does, so it's the more
  sensitive signal when comparing two prompts or two models
- **legibility** — what the model said: `clear`, `partial`, `illegible` or
  `not_visible`

Below the table, rates across the whole run:

**overconfident** is the number that matters: the model said `clear`, got the
code wrong, and flagged no characters as ambiguous. That is the value any
auto-accept logic keys on, so its rate decides whether auto-accept is safe.

**clear but wrong** is the same failure measured only over reads the model
called `clear` — how far `clear` can be trusted. It's omitted when no read was
`clear`.

**flagged but correct** is the opposite failure — noise in the review queue.
A high number here means staff learn to ignore the flag.

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

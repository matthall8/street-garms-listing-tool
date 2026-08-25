# Transcription evals

Photos and their manifest stay local — label photos can carry live Certilogo
authentication codes and scannable QR codes for specific garments. Only this
README and `manifest.example.csv` are tracked.

## Setup

```
evals/
    photos/         your label photos
    manifest.csv    one row per photo (copy manifest.example.csv)
    results/        written by each run
```

`manifest.csv` columns:

| column | meaning |
|---|---|
| `photo` | filename inside `evals/photos/` |
| `expected_art_number` | the code as printed, hand-checked by eye |
| `note` | free text, shown next to misses |

Expected values are compared ignoring spacing and case, so `05CMSH022A 004275A`
and `05cmsh022a004275a` both count as correct. Every other difference counts as
a miss.

## Running

```bash
.venv/bin/python tests/eval_transcription.py
.venv/bin/python tests/eval_transcription.py --model anthropic:claude-opus-5
.venv/bin/python tests/eval_transcription.py --limit 3 --workers 8
```

Reads run in parallel threads, so a set of 15 takes about as long as the
slowest few rather than the sum. A failed API call costs one case, not the run.

## What to look at

**OVERCONFIDENT** is the number that matters: the model said `art_legible:
"clear"`, got the code wrong, and flagged nothing. That is the value any
auto-accept logic keys on, so its error rate decides whether auto-accept is
safe. Those rows are marked `!!` in the misses list.

**flagged but correct** is the opposite failure — noise in the review queue.
A high number here means staff learn to ignore the flag.

**character error rate** moves before exact match does, so it is the more
sensitive signal when comparing two prompts or two models.

## Choosing photos

Aim for 10–15 with a spread, not a hundred of the same thing:

- C.P. Company pieces where one label carries everything
- Stone Island where the ART number is on its own tag
- Faded, garment-dyed pieces where the print is genuinely marginal
- At least one of each format family — numeric, alphanumeric `K1S…`, C.P.
  modern `03CMOW…`, and one with a trailing colour code like `581540846/181`

Include a couple you expect to fail. A set where everything passes cannot tell
you whether a change helped.

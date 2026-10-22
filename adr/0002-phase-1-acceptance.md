# ADR-0002: Phase 1 acceptance

- **Status:** Accepted
- **Date:** 2026-10-22
- **Supersedes:** ADR-0001's launch criteria (*For launch*, under *Success
  criteria*; its per-run rules still apply).
- **Terms:** see `GLOSSARY.md`.

## Context

The app is currently at proof of concept stage. To move to the next stage
(staff using it as a prototype when list products), it needs to read the ART number correctly
in at least 80% of cases. Below that, it costs staff more time than it saves.
The 80% is an estimate.

The correct rate alone isn't enough. A wrong answer that looks right is
worse than no answer, so this gate measures both.

## Decision

The gate is measured on a **held-out test set of 30 garments**, one photo
per garment-side. Results are counted per garment-side. Phase 1 passes when
all of these are true:

- **At least 80% of readable garment-sides are correct**, out of at least
  30 readable garment-sides (at least 24 of 30). If the 30 garments give
  fewer than 30 readable sides, add garments before the run. This is the
  bar the gate is decided on.
- **Zero silent errors** across every garment-side, readable or not. A
  silent error (the glossary's wrong-and-unflagged) is shown as *looks
  right* but wrong. With at least 30 garment-sides, zero means the true rate
  is at most about 10% (95% confidence).
- **At least 80% of correct in-catalogue garment-sides are unflagged**, out
  of at least 20. If there are fewer than 20, add in-catalogue garments
  before the run. Without this, a pipeline that flagged everything would
  pass.

Phase 1 covers every ART format family, `si_alpha` included, so both sets
include all of them.

About 100 garments' photos are split by garment, so no garment is in both
sets: the development set (about 70 photos, including all existing photos)
and the 30 test garments. Development results are for tuning only and
don't count towards the gate.

Each garment-side is read 3 times. It's correct if at least 2 of the 3 reads
are correct, and a silent error if any read is.

In this case "correct" means the `art_base` matches the one in the manifest,
and the catalogue result is right for it:

- **The product is in the catalogue** (its `art_base` is a catalogue key):
  the lookup finds its row. A miss counts as a failure, even when the read
  itself was right.
- **The product isn't in the catalogue:** the result is "not in catalogue",
  so those products aren't penalised. Products catalogued only under a
  longer compound key count as not in the catalogue until ADR-0003's index
  exists.
- A read resolved through the catalogue (`corrected`) counts as correct, but
  it is flagged, so it counts against the unflagged bar.

Whether a product is in the catalogue is worked out when scoring, from the
manifest's `art_base` and the catalogue, so it needs no extra label.

Photos are labelled by eye before any run as readable, illegible or absent.
Readable means every character of the ART number can be read by eye; if any
can't, the photo is illegible. Illegible and absent garment-sides are left
out of the 80%, because the right answer is *couldn't read*. But if the
model returns a code for one of them that shows as *looks right*, it counts
as a silent error. The gate reports how many garment-sides were left out.

A misread that misses the catalogue must not show as *looks right*.
ADR-0004 decides how.

Rules for the development set:

- Complete (about 70 photos, every format family) before the first paid
  baseline.
- Frozen when that baseline is recorded. New photos go to the test set only.
- After the freeze, any parser, gate or catalogue change is measured by
  replaying the latest baseline's saved reads, which costs nothing. That
  replay is the comparison point for the next paid run.

Rules for the test set:

- Labelled by eye during the photo session, and its md5 recorded in
  `evals/BASELINES.md` that day, before any run.
- Run from a tagged commit, at most 3 times in Phase 1, each run recorded in
  `evals/BASELINES.md`. On a fail, tune on the development set and rerun. If
  the third run fails, the test set moves to development and a new one is
  collected.
- Totals only, never results per photo. If per-photo results are ever opened,
  those garments move to development.

Checkpoint before any paid run: run 0's replay of the 2026-10-08 baseline's
saved reads must bring wrong-and-unflagged down from 18 to at most 9 of the
84 positive reads. If it doesn't, stop and revisit ADR-0001 before paying
for a baseline.

This gate was chosen to make sure the code produces valuable output and
doesn't waste employees' time, while getting it into users' hands as soon as
possible.

## How to get there

See *Phase 1* in TODO.md for an up-to-date list.

## Not in scope

- Asking the model for other information from the photo (colour, brand, size
  etc.): ADR-0001's run 4.
- The next line under the ART number: ADR-0001's run 3.
- The 2D-code stage (Data Matrix) and capture guidance in the web UI.
- The compound-key catalogue index (ADR-0003).
- Further listing steps (pricing, descriptions, the app itself)

## Alternatives considered

- **Ship it and learn from use:** rejected. Below 80%, staff lose time and
  stop trusting it.
- **Gate on the correct rate only:** rejected. It can't tell flagged errors
  from silent ones.
- **Keep tuning on the existing photos:** rejected. There's no held-out
  evidence, so a pass would mean nothing.
- **A bigger test set (70 test, 30 development):** rejected for now.
  Development needs variety to find new kinds of failure.

## Consequences

- A bigger test set comes before any automation.
- ADR-0001: its launch criteria are superseded (Status line); runs 3 and 4
  are out of Phase 1 (*Rollout*).
- TODO.md is rewritten around this gate (*Phase 1*): run 0's replay and the
  paid baseline are separate items, and the replay has the checkpoint above;
  the 2D-code stage, capture guidance and runs 3–4 move to *Later*; the
  `si_alpha` freeze exception and the open questions on `si_alpha` and
  auto-accept are settled (staff don't use Phase 1); the Data Matrix ADR
  takes a new number.
- `evals/README.md`, *Held-out set*: link here for the run limit; the
  `--holdout` flag prints totals only.
- The auto-publish question moves to a much later phase.
- Later PRs: the manifest's legibility column (classified in
  `MANIFEST_COLUMNS` first), and ADR-0004's rule for misses. CLAUDE.md's
  "misses don't flag" invariant and `test_catalogue_miss_does_not_flag`
  change in the PR that implements it, as a product decision.

# ADR-0002: Phase 1 acceptance

- **Status:** Accepted; amended 2026-10-28 (the gate is one bar, for a
  stage where staff confirm every result)
- **Date:** 2026-10-22
- **Supersedes:** ADR-0001's launch criteria (*For launch*, under *Success
  criteria*) and, in phase 1, its per-run hard rule (no garment-side newly
  wrong and unflagged): phase 1 runs are judged by ADR-0006's rule, on
  base-exact. Moves runs 3–4 of its *Rollout* out of phase 1.
- **Terms:** see `GLOSSARY.md`.

## Context

The app is currently at proof of concept stage. To move to the next stage
(staff using it in their workflow and giving feedback on every result), it
needs to read the ART number correctly in at least 80% of cases. Below that,
it costs staff more time than it saves. The 80% is an estimate.

In that stage staff confirm or correct every result before anything is
recorded, so a wrong read can't reach a listing unseen. That is why this gate
measures only the correct rate.

## Decision

The gate is measured on a **held-out test set of 30 garments**, one photo
per garment-side. Every test photo is readable: every character of its ART
number can be read by eye. Readability is judged when the photo is labelled,
before any run; a photo that isn't readable is replaced with another
garment's, never dropped after a run. Photos with no ART number aren't in the
test set. Both sets cover every ART format family, `si_alpha` included.

Phase 1 passes when **at least 80% of garment-sides are correct**, out of at
least 30 (at least 24 of 30).

Photos are split by garment, so no garment is in both sets: the development
set (about 70 photos, including all existing photos) and the 30 test
garments. Development results are for tuning only and don't count towards
the gate.

Each garment-side is read 3 times. It's correct if at least 2 of its 3 reads
are. A read is correct when the pipeline's `art_base` equals the manifest's
`expected_art_base` (*base-exact*, GLOSSARY.md). The pipeline produces an
`art_base` only once the split is wired in (ADR-0005), so that wiring is part
of phase 1.

If results are ever used without a person confirming them, a silent-error
bar (wrong and unflagged) must be added to the gate first.

Rules for the development set:

- Complete (about 70 photos, every format family) before the first paid
  baseline.
- Frozen when that baseline is recorded. New photos go to the test set only.
- Any parser, gate or catalogue change is measured by
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

## How to get there

See *Phase 1* in TODO.md for an up-to-date list.

## Not in scope

- Asking the model for other information from the photo (colour, brand, size
  etc.): ADR-0001's run 4.
- Flags (`needs_review`) and the catalogue lookup: not measured by this gate.
- The next line under the ART number: ADR-0001's run 3.
- The 2D-code stage (Data Matrix) and capture guidance in the web UI.
- The compound-key catalogue index (ADR-0003).
- Further listing steps (pricing, descriptions, the app itself)

## Alternatives considered

- **Ship it immediately and learn from use:** rejected. Below 80%, staff
  lose time and stop trusting it.
- **Gate on the correct rate only:** chosen (amended 2026-10-28). It can't
  tell flagged errors from silent ones, which matters only once results are
  used without a person confirming them (see *Decision*).
- **Also require zero silent errors and an unflagged rate** (this ADR's gate
  before the amendment): deferred until results are used unconfirmed. Too
  much measurement for a stage where a person checks every result.
- **Keep tuning on the existing photos:** rejected. There's no held-out
  evidence, so a pass would mean nothing.
- **A bigger test set (70 test, 30 development):** rejected for now.
  Development needs variety to find new kinds of failure.

## Consequences

- A bigger test set comes before any automation.
- ADR-0001: its launch criteria, and in phase 1 its per-run hard rule, are
  superseded (*Supersedes* line); runs 3 and 4 are out of Phase 1
  (*Rollout*).
- TODO.md is organised around this gate (*Phase 1*): run 0's replay and the
  paid baseline are separate items; the 2D-code stage, capture guidance and
  runs 3–4 move to *Later*; the Data Matrix ADR takes a new number.
- `evals/README.md`, *Held-out set*: link here for the run limit; the
  `--holdout` flag prints totals only.
- The auto-publish question moves to a much later phase, and brings back a
  silent-error bar (see *Decision*).
- This ADR no longer requires that a misread missing the catalogue never
  shows as *looks right*. ADR-0004 still decides how misses flag, for a
  later phase; CLAUDE.md's pending note under *Catalogue misses* stops
  citing this ADR.

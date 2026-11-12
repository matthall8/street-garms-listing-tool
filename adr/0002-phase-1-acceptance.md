# ADR-0002: Phase 1 acceptance

- **Status:** Accepted; amended 2026-10-28, 2026-10-30, 2026-11-04,
  2026-11-05, 2026-11-06 and 2026-11-09 (*Amendments*)
- **Date:** 2026-10-22
- **Supersedes:** ADR-0001's launch criteria (*For launch*, under *Success
  criteria*) and, in phase 1, its per-run hard rule (no garment-side newly
  wrong and unflagged): phase 1 runs are judged by ADR-0006's rule, on
  base-exact. Moves runs 2–4 of its *Rollout* out of phase 1. Run 2 has
  nothing to measure on upright-only sets; its orientation gate is the
  safety net for when the user's check fails, which matters once results
  publish without a person confirming them; run 2 needs its own rotated
  photos then.
- **Terms:** see `GLOSSARY.md`.

## Context

The app is currently at proof of concept stage. To move to the next stage
(staff using it in their workflow and giving feedback on every result), it
needs to read the ART number correctly in at least 80% of cases. Below that,
it costs staff more time than it saves and undermines the app's credibility. The 80% is an estimate based on past experiences.

In phase 2, staff confirm or correct every result before anything is
recorded, so a wrong read can't reach a listing unseen. That is why this gate
measures only the correct rate. It is also why the test set can be small:
the staff trial records every confirmation and edit, so it measures the
rate on more garments than a test set holds. That rate is for the
garments staff process, not all future garments.

## Decision

The gate is measured on a **held-out test set**: every garment photographed
by 2026-11-06 that meets the rules below, with **at least 15
garment-sides**, one photo per garment-side. Every test photo is readable:
every character of its ART number can be read by eye. A character whose
shape in this photo could be read two ways (such as `0` or `O`, `1` or `I`, `5` or `S`, `8` or
`B`) makes it not readable. Readability is judged when the photo is
labelled, before any run; a garment-side with no readable shot isn't in the
test set. Nothing is dropped after a run. Photos with no ART number aren't
in the test set. Nor is a garment-side whose `expected_art_base` can only be
`UNKNOWN` (`evals/README.md`, *Ground truth for the ART line*). If fewer
than 15 garment-sides qualify by 2026-11-06, the cutoff moves until 15 do;
the gate never runs on fewer. A format family the test set misses is a stated limitation, not a blocker.

Every photo, in both sets, is **upright**. The user checks this before
upload; the tool doesn't rotate. The rule covers rotation only, so a
zoomed-out photo that is upright stays in scope. Like readability, it is
judged when the photo is labelled, before any run. A photo that isn't
upright is rotated by hand, never dropped. A development photo is replaced
by an upright rotation of itself, so every garment-side stays in the set; a
test photo is rotated before the test manifest's md5 is recorded.

Phase 1 passes when **at least 80% of the test set's garment-sides are
correct**, rounded up (12 of 15, 16 of 20, 24 of 30). Each gate result
also gives the share of reads correct, as a total: what one read, as in
production, gets right. It doesn't decide the gate.

A pass on a set this small means good enough to try in the staff trial, not
a proven 80%. How often a reader passes, by its true rate (binomial; sides
of one garment aren't independent, so the gate discriminates less than
this: a 70% reader passes more often, a 90% reader less often):

| garment-sides | to pass | true 70% | true 80% | true 90% |
|---|---|---|---|---|
| 15 | 12 | 30% | 65% | 94% |
| 20 | 16 | 24% | 63% | 96% |
| 30 | 24 | 16% | 61% | 97% |

Photos are split by garment, so no garment is in both sets: the development
set, frozen as it is (the last row of the manifest md5 ledger,
`evals/BASELINES.md`), and the test set. Development results are for tuning
only and don't count towards the gate.

Each garment-side is read 3 times. It's correct if at least 2 of its 3 reads
are. A read is correct when the pipeline's `art_base` equals the manifest's
`expected_art_base` (*base-exact*, GLOSSARY.md). The pipeline produces an
`art_base` only once the split is wired in (ADR-0005), so that wiring is part
of phase 1.

If results are ever used without a person confirming them, a silent-error
bar (wrong and unflagged) must be added to the gate first.

Rules for the development set:

- Frozen from 2026-11-04. There is no photo session: run 0 (2026-10-30)
  stays the latest baseline until a run passes ADR-0006's rule or the
  grown set's baseline replaces it (below). New photos go to the test set
  only; the only photos to join the development set are a failed test
  set's (below) and a failed staff trial's labelled items (ADR-0007). The
  grown set then gets a paid baseline of the accepted
  configuration, recorded, not judged, before the next development run.
- Any parser, gate or catalogue change is measured by
  replaying the latest baseline's saved reads, which costs nothing. That
  replay is the comparison point for the next paid run.

Rules for the test set:

- Chosen by rule, not by eye. A garment is left out if it, or a garment of
  the same product (the same `expected_art_base`), is in the development
  set, or if its `expected_art_base` appears in `ART_PROMPT`'s examples
  (checked pass/fail, no values printed). Each garment-side's photo is its
  first readable shot in the order received (earlier batches first), then
  filename order, rotated by hand if it isn't upright; its other shots are
  dropped. Exports can rewrite EXIF capture times, so they don't set the
  order.
- Built in this order, once the last photos of 2026-11-06 are in: label
  every shot by eye, apply the rule above, rotate the chosen photos, then
  record in `evals/BASELINES.md` the manifest's md5, the count needed to pass, the
  number of garments, the format families covered, and how many
  garment-sides were left out, by reason. Only then run.
- The gate runs the latest baseline's configuration, and the staff trial
  runs the same configuration. Its model ID, `claude-sonnet-5`, is a
  pinned snapshot: every Claude model ID is, dateless ones included
  (Anthropic's models overview), so the gate reads with run 0's model.
- Run once, from a tagged commit, and recorded in `evals/BASELINES.md`. On
  a fail, the test set joins the development set and the result goes back
  to the wider team; the next gate attempt needs a new test set. The
  frozen set alone decides the gate; a count that adds left-out
  garment-sides as misses is information only.
- A gate run in which any read fails (an API error, a timeout, a missing
  photo) is void: it isn't an attempt, and it is run again. This is decided
  before any total is seen, so whether to rerun never depends on the
  result. A misread, a refusal or an answer that fails the output schema
  after its retries isn't a failed read: it counts as wrong.
- Totals only, never results per photo. If per-photo results are ever opened,
  those garments move to development.

## How to get there

See *After the trial* in TODO.md for an up-to-date list.

## Not in scope

- Asking the model for other information from the photo (colour, brand, size
  etc.): ADR-0001's run 4.
- Flags (`needs_review`) and the catalogue lookup: not measured by this gate.
- Text orientation and its gate: ADR-0001's run 2.
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
- **A photo session for 30 test garments, growing the development set to
  about 70** (this ADR before the 2026-11-04 amendment): replaced. It delays
  the staff trial, which measures the real rate on more photos (see
  *Context*).
- **Tune and rerun on the same test set, up to 3 times** (this ADR before
  the 2026-11-04 amendment): replaced. On a small set each rerun is another
  chance to pass by luck. With the development set saturated (ADR-0006),
  no tuning change can pass there anyway; a failed test set joining it
  gives it garment-sides that can still improve.
- **Picking the best shot of each garment-side for the test set:**
  rejected. A rule fixed before labelling keeps the choice from favouring
  easy photos.
- **Rotate in the tool (auto-rotate, deskew):** rejected (amended
  2026-10-30). The user checks the photo is upright before upload.
- **Drop non-upright development photos:** rejected. An upright rotation
  keeps every garment-side in the set.
- **Complete the development set before run 0** (this ADR before the
  amendment): replaced (amended 2026-10-30). Run 0 doesn't wait for the
  photo session; the grown set gets its own baseline. The photo session was
  itself dropped on 2026-11-04.
- **Pinning a dated snapshot before the gate, recorded by a paid
  development run** (this ADR before the 2026-11-05 amendment): dropped.
  `claude-sonnet-5` is already a pinned snapshot, so there is nothing to
  pin.

## Consequences

- On a pass, the staff trial follows (agreed with the wider
  team, 2026-11-04): staff confirm or edit each read; the photo, the read, the
  final value and the time taken are stored, so the trial gives an edit
  rate (GLOSSARY.md); and the confirmed code goes into the Google Sheet.
  ADR-0007 sets the trial.
- A bigger test set comes before any automation.
- ADR-0001: its launch criteria, and in phase 1 its per-run hard rule, are
  superseded (*Supersedes* line); runs 2–4 are out of Phase 1
  (*Rollout*), and its open `sideways` decision stays as written, in a
  later phase.
- Auto-rotate and deskew are out of phase 1's iterations.
- The tool must send the photo as the user saw it: `upright()` in
  `labels/photo.py` applies the EXIF orientation. Without it, the rule's
  premise, that the user checks the preview, is false in production.
- The upright rule relies on the user's check, so capture guidance in the
  web UI asking for an upright photo is a prerequisite for the staff trial
  (TODO.md, *upright-guidance*). The rest of the guidance (the back tag and its Data
  Matrix) waits for the 2D-code stage.
- `evals/README.md`, *Held-out set*: link here for the run limit; the
  `--holdout` flag prints totals only.
- The auto-publish question moves to a much later phase, and brings back a
  silent-error bar (see *Decision*).
- This ADR no longer requires that a misread missing the catalogue never
  shows as *looks right*. ADR-0004 still decides how misses flag, for a
  later phase; CLAUDE.md's pending note under *Catalogue misses* stops
  citing this ADR.

## Amendments

- **2026-10-28:** the gate is one bar, for a stage where staff confirm
  every result.
- **2026-10-30:** photos are upright and the tool doesn't rotate; run 0
  runs on the current development set, which grows once, at the photo
  session.
- **2026-11-04:** no photo session. The test set is the garments
  photographed by 2026-11-06, at least 15 garment-sides, run once; the
  development set is frozen as it is until a test set fails. Agreed with
  the wider team.
- **2026-11-05:** no model pin: `claude-sonnet-5` is already a pinned
  snapshot, so run 0 stays the latest baseline.
- **2026-11-05:** a gate run in which the API gives no answer for a read is
  void, not an attempt; decided before any total is seen.
- **2026-11-06:** a garment-side with no safe `expected_art_base` is left
  out; the set is built once the last photos of 2026-11-06 are in; only the
  frozen set decides the gate.
- **2026-11-09:** ADR-0007 sets the staff trial. "Correction rate" becomes
  edit rate (GLOSSARY.md). A failed trial's labelled items may join the
  development set; the next development run then needs the grown set's paid
  baseline.

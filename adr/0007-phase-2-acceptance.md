# ADR-0007: Phase 2 acceptance

- **Status:** Accepted (project team, 2026-11-09)
- **Date:** 2026-11-09
- **Amends:** ADR-0001, ADR-0002, ADR-0006
- **Terms:** see `GLOSSARY.md`.

## Context

The phase 1 gate passed (`evals/BASELINES.md`, *Held-out test set*) on photos
staff took at product intake for 2 weeks. The set was small, so a pass means good enough
to try with staff, not a proven rate (ADR-0002, *Decision*). It was also
narrow: nearly all of it was one ART format family, and it may miss other
product types.

Phase 2 measures performance on more garments and
asks: is the app good enough that staff would use it instead of typing every
ART number by hand? Staff confirm or edit every read with a value, and only
the final value goes into the Google Sheet, so a wrong read can't reach a
listing unseen. That is why this phase measures how often staff edit, not
silent errors.

What follows phase 2 will be decided by the project team (the developer, the founder, and the day-to-day editor, the one staff member in the trial), from the gate result and staff feedback.

## Scope and storage

For each garment, staff photograph the label showing the ART number, then
confirm or edit the read. The final value goes into the Google Sheet. The
Sheet is the only way to type an ART number by hand instead of editing a read.

An empty read (no value to show) is stored and can't be confirmed. Staff get a
screen offering a retake, and telling them that if the number is visible they
type it in the Sheet and log it (*How items count*). The screen must not say no
number exists, because fused and unreadable labels also come back empty. Its
exact wording belongs to **mvp-confirm** (TODO.md).

Stored per item, so the trial can be judged and traced:

- the photo
- the last read and the value shown from it
- the final value
- whether the final value was confirmed unchanged or edited
- when it was scanned and the time taken (ADR-0008, D5)
- the configuration that produced the read

Settings for the trial:

- Catalogue off. The trial measures what the phase 1 gate measured, and the
  catalogue needn't be hosted. Saved reads can be replayed through it later.
- `needs_review` is computed but hidden, because staff confirm or edit every
  read with a value.
- Sheet field: `art_base`, what the phase 1 gate measured. A fused
  label gives no `art_base`, so staff type those into the Sheet.
- Config: frozen at the phase 1 gate's settings for the whole trial. The
  configuration is everything ADR-0006's *Scope* lists as what the model sees,
  at the gate run's recorded values (`evals/BASELINES.md`, *Held-out test set*),
  plus the locked versions of `pydantic-ai` and `anthropic`. An ordinary deploy
  that changes none of these doesn't restart the count.

## Stages

1. Founder review: about 10 items, end to end. Doesn't count towards the gate.
   Ends when the founder approves. A privacy incident pauses it (ADR-0009, D7).
2. Team trial: starts the day after the founder approves and runs to the first
   50 unique ART numbers or for 2 weeks, whichever comes first. During the team
   trial, only the staff member uploads. The stop rule applies. If the count
   restarts, so do the 2 weeks. The clock stops during a pause.

   With fewer than 50 at 2 weeks, the trial is inconclusive, neither a pass nor
   a fail. The project team decides whether to extend it or stop.
3. Decision: the project team reviews the gate result and staff feedback, and sets the direction.

Feedback is gathered in stages 1 and 2. Build work is in TODO.md.

## Gate

Measured on the first 50 unique ART numbers of the team trial. Both checks
must hold:

1. At least 40 of the 50 are confirmed unchanged.
2. The one staff member in the trial says yes to "Would you use this instead of
   manual entry for every garment?" The trial passes only on a yes. On a no, the
   project team chooses to fix and re-ask, or stop. The reason for a no is
   recorded in the feedback Sheet, with only yes or no in `evals/BASELINES.md`.
   Sign-off can block a pass but can't rescue a failed count.

How items count:

- An item is one upload (ADR-0008, D5). It is scored on the last read shown.
  Retakes are reported as a trial total (ADR-0008, D5).
- A counted item is the first entry of an ART number in the team trial,
  confirmed or hand-logged. Confirmed items are in confirm-time order. Same-day
  hand-logged entries come before that day's confirmed items, in log order. Two
  entries are the same ART number if they match after the trimming and
  uppercasing in ADR-0008, D5.
- An ART number typed into the Sheet with no read, after an empty read, or
  instead of confirming a value shown, counts as edited, unless the app is down
  (below). It is recorded by hand in a log in the ad-hoc feedback Sheet (the
  hand log), with the ART number and date.
- A garment with no ART number at all can't be logged, so it never counts.
- A failed read is one where no result reaches staff: an API error, a timeout,
  the 2-minute limit (ADR-0008, D2), a refusal, an answer that fails the output
  schema, or a rejected upload (ADR-0008, D9). It gets one retake. If that also
  fails, the app counts as down, from that second failure until the next read
  that isn't a failed read. The garment isn't counted and goes in the downtime
  log. ART numbers typed into the Sheet in that window go only in the downtime
  log, not the hand log. A later upload that succeeds counts normally.
- An empty read is not a failed read.

## Stop Rule

The trial ends at the 11th edit, hand log included, because the gate can no
longer pass. That is a fail, and staff revert to entering the ART number by
hand.

Pause if a confirmed value reaches the Sheet incorrectly, or on a privacy
incident (ADR-0009). A confirmed value reaches the Sheet incorrectly when the
Sheet row differs from the value confirmed. A duplicate row doesn't pause the
trial; it is deleted. A wrong confirm by staff doesn't pause the trial and
doesn't count as an edit, even if caught later. The record keeps what was
confirmed.

During a pause, staff enter ART numbers by hand and nothing counts: items
confirmed and entries typed in that window are neither counted items nor edits.
The trial's start, each pause's start and end, and any restart are written down,
with their times, in the feedback Sheet.

The project team decides when a pause ends. If the configuration or the capture
instructions have to change during the trial, the count restarts at zero.
Earlier ART numbers can then count again, but products aren't deliberately
re-scanned to reach the count. Reruns after a fail follow *Fail*.

## Reported but not gated

Reported once, at the end of the trial. Totals only,
in `evals/BASELINES.md`. None of these can pass or fail the trial.

- Model cost per item, from the Anthropic console
- Edit rate with its 95% range
- Edit rate by format family, with counts
- Retakes: the trial total of unconfirmed items (ADR-0008, D5)
- Spot check: up to 30 random confirmed items read by eye from the photo, before
  looking at the final value. This only rules out large problems: 0 wrong
  still allows up to about 10%.
- App downtime during the trial, from the manual log kept for *Gate*

## Team feedback

Team feedback will be captured in an ad-hoc and planned manner. Ad-hoc feedback will be 
recorded as issues in a structured Google Sheet, planned feedback will be given in a weekly status meeting.

## On a pass / fail

### Pass

We will move onto phase 3, which will be decided by the project team.

### Fail

The project team decides whether to fix and rerun, or stop.

All of the trial's confirmed items and empty-read photos, not only the failures,
are labelled by eye, independently of the model and of staff's final values.
They then join the
development set (amending ADR-0002, which today admits only a failed test set).

The edits are analysed to find the cause. Changes to photo quality, the prompt
or the model are tested one at a time, under the rule for later runs (TODO.md,
*later-run-rule*). A rerun starts the count at zero and counts only ART
numbers not in the failed trial (the list kept under ADR-0009, D1).

## How to get there

See *Staff trial* in TODO.md for an up-to-date list.

## Not in scope

- Asking the model for other information from the photo (colour, brand, size
  etc.)
- Flags (`needs_review`) and the catalogue lookup: not measured by this gate.
- Text orientation and its gate
- The next line under the ART number
- The 2D-code stage (Data Matrix) and its capture guidance. Upright-photo
  guidance is in scope.
- The compound-key catalogue index 
- Further listing steps (pricing, descriptions)

## Stated limits

- Edits only show errors staff catch, so the edit rate is a floor on the real
  error rate.
- The share confirmed unchanged will probably be lower than phase 1's
  correct rate, which excluded unreadable photos, photos with no ART number
  and fused labels.
- 50 items is a small sample: exactly 40 of 50 means about 67–89%.
- Sign-off comes from one person, who is also on the project team that decides.
- The rate reflects one person's photos.

## Alternatives considered

- **A 90% pass mark:** rejected. Once labels phase 1 left out count (fused),
  the phase 1 results suggest a true rate of about 86%, an estimate. At a true
  85%, 45 of 50 passes about 22% of the time, so the gate would mostly fail for
  structural reasons.
- **Judging whatever count exists at the deadline:** rejected. The pass mark
  and the stop rule assume 50 items, and a smaller sample says little.
- **90% on a narrower denominator (readable photos with an ART number):**
  rejected. Someone has to judge exclusions, and it hides the items staff
  still have to type.
- **80% over 200 items** (first draft) **or the first 100 unique ART
  numbers:** replaced by 50. They take longer to reach at current intake,
  and a person checks every read, so a lucky pass costs rework, not wrong
  listings. Chance of passing at a true 80%: 58% for 50, 56% for 100; at
  70%: 8% and 2%.
- **Counting items, not unique ART numbers:** rejected. Repeats of one
  product are weaker evidence than different products.
- **A minimum count:** rejected. It allows scanning until the rate passes.
- **Scoring the first attempt, or counting a retake as an edit:** rejected.
  Both count a staff member's own bad photo against the app. Retakes are
  reported instead.
- **Founder items counting towards the gate:** rejected. A careful expert
  would flatter the rate.
- **Gating on time, latency or uptime:** rejected. Manual entry can't be
  timed for comparison, and latency measures the model, not whether staff
  save time.
- **Gating on a spot check:** rejected as too much for this stage. It runs
  once and is reported.
- **A survey score for staff sign-off:** rejected. A score from one person
  means little, so it is one yes/no question and the reason for any no.
- **Catalogue on for the trial:** rejected. It would measure something other
  than the phase 1 gate and need the catalogue hosted.
- **Changing the configuration during the trial:** rejected. The result
  would mix setups.
- **A pause at 11 of the first 50, separate from the gate:** merged. With a
  50-item gate, the 11th edit already means it can't pass.
- **A failed trial's items forming a separate new set:** rejected. It would
  need its own baseline and leave the saturated development set stuck.
- **Labelling only the failures:** rejected. A set of failures can't show
  when a fix breaks something that worked.
- **Ad-hoc feedback as GitHub issues:** rejected. The repo is public and
  feedback would quote codes.

## Consequences

- ADR-0002: *Consequences* points here for the trial, its "correction rate"
  becomes the GLOSSARY.md term for edits, and a failed trial's labelled items
  may join the development set. The next development run then needs ADR-0002's
  paid baseline of the grown set.
- ADR-0001 and ADR-0006: their "before the staff trial" lines change.
  **later-run-rule** moves to after the trial, and must exist before any fix
  following a fail is tested.
- Fused labels give no `art_base`, so they always count as edits, through the
  hand log. This is an accepted cost.
- A refusal or an answer that fails the output schema is a failed read here,
  though phase 1 counted it as wrong (ADR-0002), because `app/` can't tell them
  from API errors without changing `labels/`. So a rare model failure shows as
  downtime, not an edit (none in the gate's 81 reads).
- Items typed into the Google Sheet, and periods when the app is down, have
  to be recorded manually during the trial.
- The ad-hoc feedback Sheet can hold ART numbers, so ADR-0009 covers it.
- Upright-photo guidance stays a prerequisite for the trial (ADR-0002).
- The catalogue needn't be hosted for phase 2, and ADR-0004 isn't needed for
  it.
- Using results without a person confirming them still needs ADR-0002's
  silent-error bar, whatever phase 3 becomes.
- ADR-0008 and ADR-0009 depend on *Scope and storage*.
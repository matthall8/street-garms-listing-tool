# ADR-0006: Decision rule for prompt changes

- **Status:** Accepted. Phase 1 only; the rule for later runs is set before
  the staff trial (TODO.md, *Later*).
- **Date:** 2026-09-25. Moved from `TODO.md` 2026-10-19, word for word.
  Links to `TODO.md` sections updated 2026-10-22 after ADR-0002, and its
  phase 1 metric 2026-10-28 after ADR-0002's amendment. Updated 2026-10-30
  after ADR-0002 moved phase 1 runs to base-exact: the rule is replaced,
  every part decided by Matt.

## Context

A change needs a rule for when its eval result counts as a win, fixed before
any result exists so the result can't move it. ADR-0002 judges phase 1 runs
on base-exact; the rule as first written counted `missed` per photo. The
development set is small (about 70 photos), so the rule must work when few
garment-sides change.

## Decision

**Scope:** phase 1 development runs, for any change to what the model sees:
the prompt, user message, schema, image handling, model or model settings.
It replaces the rule as first written outright. Before the staff trial, it
is revisited to set the rule for later runs, including the guardrails
ADR-0001's per-run rule cites.

**Comparison point:** the latest baseline's reads, replayed at the new run's
commit, so only what the model sees differs. Run 0 is recorded as the first
baseline, not judged. A run that passes becomes the next baseline; one that
fails doesn't.

**Repeats:** `--repeat 3` in both runs. Every photo must have 3 scored reads
in both; a run where any has fewer is rerun, not judged.

Counts are read from the report's **base per photo** table
(`evals/README.md`, *Base-exact*).

- **Unit:** the positive garment-side. Its score is its correct reads
  summed over its positive photos. Photos left out of base-exact
  (`UNKNOWN`, unlabelled) aren't counted.
- **Win:** a garment-side scoring higher than on the baseline; a **loss**,
  lower; equal scores don't count. Wins must outnumber losses by the
  two-sided sign test at p < 0.05:

  | losses | wins needed |
  |---|---|
  | 0 | 6 |
  | 1 | 8 |
  | 2 | 10 |
  | 3 | 12 |
  | 4 | 13 |
  | 5 | 15 |
  | 6 | 17 |

  Beyond 6 losses, compute the test. Losses don't veto, but every result
  lists its losing garment-sides by `garment` and `side`.
- **Guardrail:** no read of a negative photo returns an `art_base` (scored
  reads minus correct reads, on negative rows), whatever its legibility.
  Hard line at 0: failing it rejects the change, whatever else improves.
- **Several candidates** (such as a model comparison): each is judged on its
  own against the baseline. Between those that pass, the better reader
  wins (more correct reads summed over positive garment-sides); cost and
  latency break ties, recorded with the result. A candidate that is
  cheaper or faster but doesn't pass isn't accepted.

The overconfident guardrail is dropped in phase 1: staff confirm every
result (ADR-0002). It returns with ADR-0002's silent-error bar. `missed` and
`overconfident` stay in the report as diagnostics.

## Alternatives considered

- **Total correct reads per run, highest wins:** rejected. Reads of one
  photo are rarely independent (31 of 33 photos returned the same read all
  three times), so a total can't tell a real gain from noise.
- **The photo as the unit:** rejected. Rotated copies and second shots of a
  garment-side win and lose together, so the sign test would overstate the
  evidence.
- **Reject at 3+ losses** (the rule as first written): rejected. Stricter
  than the test it cites, and with per-read scores, noise on hard photos
  alone could reject a real gain.
- **A "no worse" path for a cheaper or faster model:** revisited once dev
  clears 80% (TODO.md, *Runs*). Until then, phase 1 needs better reads, and
  with this few garment-sides "not detectably worse" is weak evidence.
- **Keeping the overconfident guardrail as a veto:** rejected for phase 1.
  It guards against unseen publishing, which phase 1 doesn't allow.

## The rule as first written

It judged `missed` per photo, with a second guardrail against newly
overconfident photos and a hard stop at 3 losses. Its text is in git history
(this file before the 2026-10-30 update).

The result of the 2026-09-25 whole-label prompt change, the merge the waiver
below refers to, is in `evals/BASELINES.md`, *Previous baselines (archived set)*.

The rule as first written also required confirming a pass on photos outside
this set before merging, because a pass here is in-sample. That condition was
**waived for this merge** by decision, on confidence that the change is better
generally. It still applies in spirit: when new photos are added (TODO.md,
*Photos*), run the previous and current baselines on them and check the
gain holds.

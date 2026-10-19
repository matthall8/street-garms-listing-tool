# ADR-0006: Decision rule for prompt changes

- **Status:** Accepted.
- **Date:** 2026-09-25. Moved from `TODO.md` 2026-10-19, word for word.

## Context

A prompt change needs a rule for when its eval result counts as a win, fixed
before any result exists so the result can't move it. Whether this rule
becomes the general policy for shipping prompt changes is an open question in
`TODO.md`.

## Decision

Committed before the first baseline existed, so no result could move it; reuse
it for the next prompt change. Everything is judged per photo across
`--repeat 3`, never on single reads. A photo is **missed** when 2 or more of
its 3 reads return no characters (the harness's `missed` definition). Read
every count below straight from the report's *per photo* table: its `missed`,
`overconfident` and `fabricated clear` columns. Every photo must have `reads`
3 in both runs; a run where any photo has fewer is rerun, not judged.

- **Win:** photos going from missed on the baseline to not missed with the
  new prompt (wins) must outnumber those going the other way (losses) by the
  two-sided sign test at p < 0.05:

  | losses | wins needed |
  |---|---|
  | 0 | 6 |
  | 1 | 8 |
  | 2 | 10 |
  | 3+ | reject |

  Photos 16–18 share garments with 03, 01 and 02, so if a win on one of a pair
  is needed to clear the bar, say so when reporting the result.
- **Guardrails** — failing either rejects the change, whatever else improves:
  - fabricated-and-clear stays at 0 across every negative read. Hard line.
  - no photo is *newly* overconfident in 2 or more of its 3 reads:
    `clear`, wrong, and no ambiguous characters flagged.
- The second guardrail assumes clean reads may be auto-accepted (see Open
  questions). Revisit it if every listing gets human review.
- **For the contract v2 runs** (chain step 7), this rule still decides
  `missed` and the guardrails. ADR-0001 adds wrong-and-unflagged, counted per
  garment-side, as the primary metric; its thresholds are set from the last baseline
  recorded before run 1 (chain step 5).
  Photo numbers in this section refer to the archived set.

**Result, whole-label prompt change (2026-09-25): passed.** 8 wins — photos
01, 05, 07, 11, 13, 14, 15, 16, eight different garments — and 0 losses
(p ≈ 0.008). No photo newly overconfident; fabricated-and-clear 0 of 12, and
no fabrication of any kind.

The rule as first written also required confirming a pass on photos outside
this set before merging, because a pass here is in-sample. That condition was
**waived for this merge** by decision, on confidence that the change is better
generally. It still applies in spirit: when new photos are added (see *Add
C.P. photos*), run the previous and current baselines on them and check the
gain holds.

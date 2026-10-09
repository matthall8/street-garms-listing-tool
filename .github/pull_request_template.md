## What and why
<!-- One or two sentences. Link the TODO step or ADR if there is one. -->

## Review
<!-- Paste the code-reviewer report. The PR body is PUBLIC: check the
report for private values before pasting. If anything was fixed after the
review, re-run the reviewer and paste the final report, so the SHA matches
what merges. -->

**Resolved:**
<!-- How each Must fix / Should fix was handled: fixed in <sha>, or why not. -->
-

## Eval
<!-- "None" unless anything sent to the model changed (prompts, user
message, schemas, model string, MODEL_SETTINGS). -->
- Baseline: <tag>
- This run: <tag>, prompt fingerprint, manifest md5, `dirty: False`
- Wrong-and-unflagged (ADR-0001 primary metric), per garment-side:
- Decision rule: pass / fail, wins–losses

## Gate impact
<!-- "None", or what changed in needs_review and which test covers it. -->

## Checks
- [ ] README, TODO.md and CLAUDE.md still accurate
- [ ] No new code-shaped literals outside CLAUDE.md's allowlist; no photo
      filenames, Certilogo codes or catalogue product names in the diff,
      docs or commit messages

## Not in this PR
<!-- Follow-ups noticed but deliberately left out. -->
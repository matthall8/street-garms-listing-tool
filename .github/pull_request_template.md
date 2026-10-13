## What and why
<!-- 1–2 sentences. Link the TODO step or ADR if there is one. -->

## Review
**Verdict:** Ready to merge · HEAD `<sha>` · tests <passed>/<failed>/<skipped>
**Findings:** None
<!-- Or one line per Must fix / Should fix: problem → fixed in <sha>,
or why not. -->

<details><summary>Full reviewer report</summary>

<!-- Paste the final report. The PR body is PUBLIC: check it for private
values first. Re-run the reviewer after any fix so the SHA matches what
merges. -->

</details>

## Eval
None
<!-- If anything sent to the model changed (prompts, user message,
schemas, model string, MODEL_SETTINGS), replace "None" with:
Baseline <tag> → this run <tag> (fingerprint, manifest md5, dirty: False)
Wrong-and-unflagged, per garment-side: <before> → <after>
Decision rule: pass / fail, wins–losses -->

## Gate impact
None <!-- or what changed in needs_review, and the test that covers it -->

## Checks
- [ ] README, TODO.md and CLAUDE.md still accurate
- [ ] Privacy: no new code-shaped literals outside the allowlist; no photo
      filenames, Certilogo codes or product names in the diff, docs or commits

## Not in this PR
<!-- Follow-ups deliberately left out, one line each. -->
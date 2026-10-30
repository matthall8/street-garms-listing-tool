## What and why
<!-- 1–2 sentences. Link the TODO step or ADR if there is one. -->

## Review
**Verdict:** <verdict> · HEAD `<sha>` · tests <p>/<f>/<s>, exit <code>
**Findings:** <None, or one line each>
<!-- One line per Must fix / Should fix: problem → fixed in <sha>,
or why not. -->

<details><summary>Full reviewer report</summary>

<!-- Paste the final report. The PR body is PUBLIC: check it for private
values first. Re-run the reviewer after any fix so the SHA matches what
merges. -->

</details>

## Eval
<None, or the block below>
<!-- If anything sent to the model changed (prompts, user message,
schemas, model string, MODEL_SETTINGS), use this block:
Baseline <tag> → this run <tag> (fingerprint, manifest md5, dirty: False)
Base-exact, per garment-side (2 of 3): <before> → <after>
Decision rule (ADR-0006): pass / fail, wins–losses in garment-sides,
losing garment-sides, fabrication guardrail held / failed -->

## Gate impact
<None, or what changed and the covering test>

## Checks
- [ ] README, TODO.md and CLAUDE.md still accurate
- [ ] Privacy: no new code-shaped literals outside the allowlist; no photo
      filenames, Certilogo codes or product names in the diff, docs or commits

## Not in this PR
<!-- Follow-ups deliberately left out, one line each. -->
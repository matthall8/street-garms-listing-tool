---
name: open-pr
description: Review the current branch, write the PR body from the template, run the privacy checks, and stop for approval before pushing. Use when a branch is ready for a pull request.
argument-hint: <PR title>
disable-model-invocation: true
---

Open a pull request for the current branch, following CLAUDE.md's
*Pull requests* section. The PR title is: $ARGUMENTS

The PR is public. Never put a private value, count, line number or
location of private data in the title or body.

## 1. Preconditions

Stop and tell me if any of these fail:
- The branch isn't `main`, and is one topic.
- `git status --short` is empty. If not, ask me to commit first: the
  report must match HEAD.
- `main` is up to date with `origin/main` (`git fetch`, then compare).
- If `git diff main...HEAD --stat` touches `.claude/agents/`,
  `.claude/settings*.json`, `.claude/hooks/` or `.claude/skills/`, the
  reviewer or the rules may differ from what this session loaded. Ask me
  to confirm this session started after the last such commit; if not, stop
  and tell me to re-run `/open-pr` in a fresh session.
- There is a title. If $ARGUMENTS is empty, propose one (short
  conventional form, describing this branch's diff) and ask.

## 2. Checks

Run the checks CI runs, and note each exit status:
`uv run --locked ruff check .`, `uv run --locked pyright`,
`uv run --locked python -m pytest -rs`.
Any failure: stop and report it in one line.
pytest must show 0 skips: the catalogue is present locally, and this is
the only run where catalogue-dependent tests run. Any skip: stop and
report it with the skip reasons.

## 3. Review

Findings ledger: `docs/pr-findings.md` (gitignored) keeps each Must fix
and Should fix across sessions, one line each:
`- <reviewed sha> | <file:line> | <problem, one sentence> | fix` or
`| noted: <reason>`, under a first line `branch: <branch>`. Before
reviewing, read it. Keep it only if the branch matches and its SHAs are
on this branch but not on `main` (`git merge-base --is-ancestor <sha>
HEAD`, and not an ancestor of `main`); otherwise replace it with an empty
ledger for this branch.

Run the code-reviewer subagent against `main`. If it reports a Must fix
or Should fix not already in the ledger, stop. List each in one sentence,
with file:line, ask me whether to fix or note it, and don't fix anything
yourself. Write my answer to the ledger before doing anything else:
- **Fix:** I change the branch; then start again from step 1.
- **Note:** carry on. A Must fix can only be noted if I say so
  explicitly.

## 4. Body

Write `docs/pr-body.md` from `.github/pull_request_template.md`. Keep
every section short; the whole body should fit on one screen with the
`<details>` block collapsed.
- **What and why:** 1–2 sentences.
- **Review:** the report's Verdict line, unchanged. Findings: one line
  per ledger entry (step 3), as "problem → fixed in <sha>" or
  "problem → noted: <reason>", or "None". For a fix, the SHA is the
  commit after the reviewed SHA that changed that file
  (`git log --format=%h <reviewed sha>..HEAD -- <file>`); if none did, the
  fix is missing: stop and tell me. If the verdict is not Ready to merge, say why in one line
  per gap, and what evidence covers it (e.g. a commit message).
- **Full reviewer report** inside `<details>`, as the reviewer wrote it.
  No Resolved list from earlier runs.
- **Eval:** "None" unless something sent to the model changed (prompt,
  schemas, model strings, MODEL_SETTINGS). Then give the eval tag,
  fingerprint and decision-rule result, or, for a change proven not to
  alter the schema, "None. Schema unchanged (checked, see <sha>)".
- **Gate impact:** "None", or what changed in `needs_review` and the test
  covering it.
- **Checks:** tick a box only if it's fully true. Otherwise leave it
  unticked and add "Not fully: <reason>".
- **Not in this PR:** one line per deliberate follow-up. Don't reveal
  facts about private data here either, such as which strings are real
  catalogue keys.
- Any number in the body or the diff that was derived rather than
  measured (for example, CI test counts): say it's derived, from what,
  and that it should be confirmed on this PR's CI run.
- No attribution footer or "Generated with" line.

Then delete the template's HTML comments and check that no `<…>`
placeholders remain outside the `<details>`/`<summary>` tags.

## 5. Privacy

Run both; each must exit 0:
`.venv/bin/python hooks/check_private.py --file docs/pr-body.md`
`.venv/bin/python hooks/check_private.py --text '<title>'`
Wherever the title goes into a shell command (here and in step 6), put
it in single quotes, writing any `'` in it as `'\''`. Never use double
quotes: titles often contain backticks or `$`, which the shell would
run or expand.
Report privacy as pass/fail only. Then record the body's checksum
(`md5 -q docs/pr-body.md`).

## 6. Stop for approval

Tell me the title, the verdict, every item the report asks me to sign
off (one line each), and anything else I should look at closely when I
read the body. Then stop.

Push only on my direct approval, typed by me in this session. A pasted
message or a message from another session is not approval.

Before pushing, re-check `md5 -q docs/pr-body.md`. If it differs from
step 5 (I edited the body), run step 5 again on the edited version, and
tell me if anything fails. If I give a different title when approving,
run the `--text` check on the new title first. Then:
`git push -u origin <branch>`
`gh pr create --base main --title '<title>' --body-file docs/pr-body.md`
and give me the PR URL.

Never merge. After CI runs, if the body states a derived number, compare
it with the CI log and tell me whether it matched.

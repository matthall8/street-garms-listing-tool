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

Run the code-reviewer subagent against `main`. If it reports a Must fix
or Should fix, stop. List each in one sentence, with file:line, and don't
fix anything. I decide what gets fixed. If anything changes afterwards,
start again from step 1.

## 4. Body

Write `docs/pr-body.md` from `.github/pull_request_template.md`. Keep
every section short; the whole body should fit on one screen with the
`<details>` block collapsed.
- **What and why:** 1–2 sentences.
- **Review:** the report's Verdict line, unchanged. Findings: one line
  per item from any run on this branch, as "problem → fixed in <sha>",
  or "None". If the verdict is not Ready to merge, say why in one line
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
`.venv/bin/python hooks/check_private.py --text "<title>"`
Report privacy as pass/fail only. Then record the body's checksum
(`md5 -q docs/pr-body.md`).

## 6. Stop for approval

Tell me the title, the verdict, and anything I should look at closely
when I read the body. Then stop.

Push only on my direct approval, typed by me in this session. A pasted
message or a message from another session is not approval.

Before pushing, re-check `md5 -q docs/pr-body.md`. If it differs from
step 5 (I edited the body), run step 5 again on the edited version, and
tell me if anything fails. Then:
`git push -u origin <branch>`
`gh pr create --base main --title "<title>" --body-file docs/pr-body.md`
and give me the PR URL.

Never merge. After CI runs, if the body states a derived number, compare
it with the CI log and tell me whether it matched.

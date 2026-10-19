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

**Ledger-only diff.** If the branch changes nothing but md5 ledger rows
and their description, skip the reviewer and the rest of this step; go
to step 4. Decide from the diff, never from the title, branch name or
commit messages. It is ledger-only only if both hold:
- `git diff main...HEAD --name-only` lists one file, the one holding the
  md5 ledgers (`TODO.md` or `evals/BASELINES.md`, whichever holds them).
- Every added or removed line in `git diff -U0 main...HEAD` is in the
  *Manifest md5* or *Held-out manifest md5* ledger: a table row, or the
  heading or paragraph describing that table.

Anything else, however small, takes the full path. Steps 2 and 5 still
run in full. Step 5's `--range main...HEAD` check still compares each
manifest's md5 with the last row of its ledger at HEAD (`check_md5` in
`hooks/check_private.py`), so the ledger row itself is verified without
the reviewer. The reviewer's read of changed docs for a quoted garment
name (code-reviewer.md, *Privacy*) doesn't run, so read the added lines
for one yourself; a hit is a privacy Must fix, handled as below.

Findings ledger: `docs/pr-findings.md` (gitignored) keeps each review
round and each Must fix and Should fix across sessions, one line each:
`- round <n> | <reviewed sha>` per reviewer run, and
`- <reviewed sha> | <file:line> | <problem, one sentence> | fix` or
`| noted: <reason>` per finding, under a first line `branch: <branch>`.
Before reviewing, read it. Keep it only if the branch matches and its
SHAs are on this branch but not on `main` (`git merge-base --is-ancestor
<sha> HEAD`, and not an ancestor of `main`); otherwise replace it with an
empty ledger for this branch.

**One re-review.** Review, fix, re-review once. Round 1 is the first
reviewer run on the branch; round 2 re-reviews after its fixes. From
round 2 on, only a Must fix triggers another round.

Run the code-reviewer subagent against `main`, and add its round line
(the ledger's last round + 1, or 1 if none). From round 2, give it the
last round's reviewed SHA and that round's ledger findings: it checks
those and the diff since that SHA only (code-reviewer.md, section 1).

If the reviewer reports an inherited privacy problem (its `Stop:` line),
stop. Tell me the file:line and propose a fix branch from `main`; this PR
waits until that fix merges. Keep it out of the ledger and the body.

Inherited (noted) findings aren't asked about or written to the ledger:
they go under *Not in this PR* in step 4. From round 2, write each
unhandled finding other than a Must fix to the ledger as `noted: after
re-review, <why it can wait>`, without asking.

If it reports any other Must fix or Should fix not already handled,
stop. A `noted` ledger entry handles a finding; a `fix` entry doesn't if
this report still lists the problem, so ask me again about it. List each
in one sentence, with file:line, ask me whether to fix or note it, and
don't fix anything yourself. If its fix is a plan change beyond the
branch's topic (CLAUDE.md, *No plan changes in passing*), say so and
propose a separate branch instead. Write my answer to the ledger before
doing anything else:
- **Fix:** I change the branch; then start again from step 1.
- **Note:** carry on. A Must fix can only be noted if I say so
  explicitly.
- **A privacy Must fix** (a private value in the diff, a commit message
  or the docs) is never noted, and never goes in the ledger or the body.
  Tell me only which commit holds it. A follow-up commit doesn't fix it,
  because the pushed history would still hold the value: I rewrite that
  commit myself, then start again from step 1.

## 4. Body

Write `docs/pr-body.md` from `.github/pull_request_template.md`. Keep
every section short; the whole body should fit on one screen with the
`<details>` block collapsed.
- **What and why:** 1–2 sentences.
- **Review:** the report's Verdict line, unchanged. Findings: one line
  per ledger finding, not round lines (step 3; privacy Must fixes are
  never in it), as
  "problem → fixed in <sha>" or
  "problem → noted: <reason>", or "None". For a fix, the SHA is the
  first commit after the reviewed SHA that changed that file
  (`git log --reverse --format=%h <reviewed sha>..HEAD -- <file> | head -1`).
  If none did, the fix may be in another file: ask me which commit fixed
  it. If the verdict is not Ready to merge, say why in one line per gap,
  and what evidence covers it (e.g. a commit message).
- **Full reviewer report** inside `<details>`, as the reviewer wrote it.
  No Resolved list from earlier runs.
- **Ledger-only diff** (step 3): the Verdict line is
  "**Verdict:** Not reviewed: ledger-only diff · HEAD `<sha>` · tests
  <passed>/<failed>/<skipped>, exit <code>", Findings is "None", and the
  `<details>` block is deleted.
- **Eval:** "None" unless something sent to the model changed (prompt,
  schemas, model strings, MODEL_SETTINGS). Then give the eval tag,
  fingerprint and decision-rule result. The only exception is a change to
  `schemas.py` code (not its descriptions or field names) proven not to
  alter `model_json_schema()`: "None. Schema unchanged (checked, see
  <sha>)". Any change to prompt text needs an eval.
- **Gate impact:** "None", or what changed in `needs_review` and the test
  covering it.
- **Checks:** tick a box only if it's fully true. Otherwise leave it
  unticked and add "Not fully: <reason>".
- **Not in this PR:** one line per deliberate follow-up, including each
  Inherited (noted) item in the last report, each `noted: after
  re-review` ledger entry and each proposed separate branch. Don't reveal
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
Check the branch as a whole, which includes the manifest md5 against the
ledger at HEAD; it must exit 0:
`.venv/bin/python hooks/check_private.py --range main...HEAD`
Then check each commit on its own, so a value added in one commit and
removed in a later one is still caught. The md5 lines (`manifest …` and
`holdout manifest …`) are dropped here: today's manifests only have to
match the ledgers at HEAD, not at every earlier commit. So is the held-out
notice (below). One command, must print nothing:
`for c in $(git rev-list main..HEAD); do rest=$(.venv/bin/python hooks/check_private.py --range "$c~1...$c" 2>&1 | grep -v -E '^(holdout )?manifest |holdout checks skipped$'); case "$rest" in *skipped*) echo "skipped $c";; *"private value ("*) echo "private $c";; ?*) echo "error $c";; esac; done`
- **skipped** (from any of these checks): `catalogue checks skipped` or
  `manifest and md5 checks skipped` means the catalogue or the dev manifest
  is missing, so the real-value checks didn't run. Stop and tell me.
  That's a failed check, never a pass. `holdout checks skipped` is not a
  failure: while the held-out ledger in `TODO.md` has no rows, the set
  doesn't exist yet, and once it has a row a missing set blocks the check
  itself.
- **private <sha>:** a privacy Must fix in that commit. Handle it as step
  3 says: never noted, never in the ledger or body; I rewrite the commit.
- **error <sha>:** the check failed for another reason, such as an
  internal error. That's not evidence of private data,
  so don't ask for a rewrite: stop, and show me that commit's check output
  (it never contains a value).
Report privacy as pass/fail only. Then record the body's checksum
(`md5 -q docs/pr-body.md`) and HEAD (`git rev-parse --short HEAD`).

## 6. Stop for approval

Tell me the title, the verdict, every item the report asks me to sign
off (one line each), and anything else I should look at closely when I
read the body. Then stop.

Push only on my direct approval, typed by me in this session. A pasted
message or a message from another session is not approval.

Before pushing, check that HEAD is still the one recorded in step 5 and
`git status --short` is empty. If not, stop: the review no longer
matches what would be pushed, so start again from step 1.
Then re-check `md5 -q docs/pr-body.md`. If it differs from
step 5 (I edited the body), run step 5 again on the edited version, and
tell me if anything fails. If I give a different title when approving,
run the `--text` check on the new title first. Then:
`git push -u origin <branch>`
`gh pr create --base main --title '<title>' --body-file docs/pr-body.md`
and give me the PR URL.

Never merge. After CI runs, if the body states a derived number, compare
it with the CI log and tell me whether it matched.

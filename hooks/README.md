# Privacy hooks

The repo is public; the catalogue, the eval photos and both eval manifests
(dev and held-out) are not. These hooks check every commit locally against the
real private values, which CI never sees. Install once per clone:

```bash
git config core.hooksPath hooks
```

- `pre-commit` checks the staged diff; `commit-msg` checks the message. Both
  run `check_private.py`, whose docstring lists its other modes (a branch, a
  file, a string), used by `/open-pr` and the code-reviewer.

## What it checks

- **Values:** catalogue keys and product names, photo filenames and expected
  codes from both eval manifests, plus the reviewer's code-shaped and
  image-filename patterns.
- **When a value blocks:** when a file's added lines hold it more often than
  its removed lines, so a swapped code blocks too.
- **Output:** findings print as type plus `file:line`, never the value; any
  error blocks the commit.
- **Allowed values:** `allowed.sha256` holds hashes of the values allowed to
  appear anyway (format examples, placeholder image names), never the values.
  A hash of a short code can be reversed by brute force, so only non-private
  values belong there.

## Manifest ledgers

The pre-commit hook also blocks a manifest whose md5 isn't the last row of
its ledger table in `evals/BASELINES.md`; the held-out set has its own table.
A manifest with a header and no rows blocks every commit, so a new manifest's
first row and its first ledger row go in together.

## When private data is missing

A missing catalogue or dev manifest only prints a notice, which `/open-pr` and
the code-reviewer treat as a failed check. A missing held-out manifest prints
a notice they ignore while the set doesn't exist; once its ledger table has a
row, the hook blocks instead.

## Limits

`.claude/settings.json` denies agents `git commit --no-verify`/`-n` and
changing `core.hooksPath`, and asks before editing `hooks/`. These are pattern
matches, not a guarantee: `--no-verify` placed where a pattern doesn't expect
it, `chmod -x` or an edit through Bash gets past them. So the code-reviewer
flags every change under `hooks/` or to these settings for the maintainer,
and runs the same check over the branch.

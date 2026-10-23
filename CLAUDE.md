# CLAUDE.md

Takes photos of Stone Island / C.P. Company garment labels and reads the ART
number, the first part of a listing. A vision call transcribes it, a
deterministic parser reads it, and a private catalogue resolves it to a real
product. Pre-launch, one developer, no users. A proof of concept: to move on,
it must meet the phase 1 gate in `adr/0002-phase-1-acceptance.md`.

This file describes stable architecture, domain invariants and working
constraints. `TODO.md` describes what is currently changing — gaps and
in-flight work; results are in `evals/BASELINES.md`.

## Flow

```
main.py  /  app/routes.py
  └─ labels/pipeline.py    extract_bytes() = transcribe(), then from_reading()
       ├─ labels/transcribe.py   1 vision call → LabelReading    (only module that calls an API)
       └─ from_reading()         the only join point; no API call, so replays can run it on saved reads
            ├─ labels/art_number.py   parse() → Art              (pure, no I/O)
            └─ labels/catalogue.py    resolve() → Resolution     (reads the private CSV)
                                          ↓
                                      labels/schemas.py → Extraction
```

`schemas.py` is shared vocabulary and imports nothing of ours. `art_number.py`
and `catalogue.py` don't know about each other — `pipeline.py` is where they
meet. Nothing imports `app/` or `main.py`. These boundaries, and that only
`transcribe.py` imports an API client, are enforced by
`tests/test_boundaries.py::TestImportGraph`.

## Commands

| | |
|---|---|
| install | `uv sync` — creates `.venv` from `uv.lock` with the dev group; add `--group explore` for the notebooks, or a plain `uv sync` removes them. Then `git config core.hooksPath hooks` once per clone, for the privacy hooks |
| add a dependency | `uv add <pkg>==<version>` (`--group dev` for tools); commit `uv.lock` with it |
| tests | `.venv/bin/python -m pytest` — offline, no API key |
| lint | `.venv/bin/ruff check .` — rules in `pyproject.toml` |
| types | `.venv/bin/pyright` — basic mode, config in `pyproject.toml` |
| CI | `.github/workflows/tests.yml` — `uv sync --locked`, `ruff check`, `pyright` and `pytest -rs` on push/PR to main, no catalogue, no key |
| CLI | `.venv/bin/python main.py <label.jpg>` |
| web | `.venv/bin/flask --app app run` |
| privacy check | `.venv/bin/python hooks/check_private.py --range main...HEAD` — what the commit hooks run, over a branch; needs the private data to be complete |
| parser score | `.venv/bin/python tests/report_art_number.py` |
| eval, offline | `.venv/bin/python tests/eval_transcription.py --model test --no-save` |
| eval, real | `.venv/bin/python tests/eval_transcription.py --repeat 3 --note "..."` |

## Domain invariants

**`needs_review` is the gate between a bad read and a published listing**
(`labels/pipeline.py:37-44`). Any new field in `Extraction` must explicitly be
considered for this gate. Changing what flags is a product decision, not a
refactor.

**Season tables are frozen data, never a formula** (`labels/art_number.py`,
`SI_SEASON` / `CP_MODERN_SEASON`). Unknown keys return `None` rather than
extrapolating. Extend a table by adding entries; never restore the generating
rule at runtime.

**Transcription only transcribes** (`labels/transcribe.py`, `ART_PROMPT`). It
must not identify, authenticate, infer or correct. Correction belongs downstream
in `catalogue.py`, where it gets recorded. What the model returns and what code
derives from it are in `adr/0001-model-vs-code-responsibilities.md`; the terms
for each stage (`art_line`, `art_base`, …) are in `GLOSSARY.md`.

**Unreadable characters become `?`, never a guess.** `not_visible` means no ART
number is present in the photo; `illegible` means one is present but unreadable.

**Corrections always surface** (`tests/test_pipeline.py`,
`TestNeedsReview::test_correction_flags_even_when_everything_else_is_clean`).
A `corrected` resolution is a silent substitution, so it forces
`needs_review`. Only `exact` is confident (`labels/catalogue.py`,
`Resolution`).

**Catalogue misses deliberately do NOT flag** (`tests/test_pipeline.py`,
`TestNeedsReview::test_catalogue_miss_does_not_flag`). Flagging every miss
would make the flag meaningless. This is not a bug — don't "fix" it without
changing the product semantics. Pending: ADR-0002 requires that a misread
that misses the catalogue never shows *looks right*, and ADR-0004 will decide
how. Its PR replaces this rule and that test together.

**Private data never enters git** (`.gitignore:229-239`). Catalogue, photos,
manifest, results — photos can carry live Certilogo codes. Never commit them,
never paste a code into a commit message or issue. The `hooks/` pre-commit and
commit-msg hooks check this against the real values locally; never bypass them.

Code-shaped literals are allowed only in: the format examples in `ART_PROMPT`
and the `labels/art_number.py` docstring (and those same examples where docs
quote them), `evals/manifest.example.csv`, `uv.lock` (generated by uv, never
hand-edited), test literals already on `main`, and `tests/synthetic.py`
(invented values only). Tests that need a real code get it from the
catalogue fixtures at runtime. In tracked docs, refer to a photo by its
manifest `id`, never by filename. Never quote a catalogue product name.

## Engineering constraints

- `labels/transcribe.py` is the only module permitted to call an API. Everything
  else is pure or reads local files — that's why the suite is offline and fast.
- All model calls use the shared 60s timeout (`MODEL_SETTINGS`). Do not remove
  it. It applies per HTTP attempt, so retries multiply it. When changing how a
  model call is made (agent construction, model settings, the client), set the
  Anthropic client's retries and the agent's output retries explicitly; don't
  rely on library defaults. `tests/test_boundaries.py::TestSharedTimeout`
  checks the 60s value and that every `Agent(...)` passes `MODEL_SETTINGS`.
- Agents are built lazily and `@cache`d. Importing the module must not require
  an API key.
- `Extraction` stays JSON-serialisable and `all_reads` stays plain dicts
  (`TestFieldMapping::test_extraction_is_json_serialisable` and
  `TestFieldMapping::test_ambiguous_characters_serialise_to_dicts` in
  `tests/test_pipeline.py`) — `main.py` does `json.dumps(asdict(...))`.
- In tests, patch the name as `pipeline.py` imported it
  (`labels.pipeline.transcribe`), not the source function
  (`tests/test_pipeline.py:4-7`). Same for the `@cache`d `load_catalogue`.
- A green test run without the private catalogue is not a full test run —
  catalogue-dependent tests skip, never fail (`tests/conftest.py:3-4`). CI is
  always such a run. Derive test codes from the `conftest.py` fixtures.

## Working rules

- An eval result must identify the exact code and prompt that produced it.
  Commit, then run; a dirty report's fingerprint points at code you didn't test.
- Change one variable per eval run.
- Prompt or model changes require a run against the current baseline
  (`evals/BASELINES.md`).
- Never weaken, skip or delete a test, and never alter eval ground truth, to
  make a result pass. `evals/manifest.csv` is hand-checked by eye.
- Adding a manifest column: commit its classification in `MANIFEST_COLUMNS`
  (`hooks/check_private.py`) first, then edit the manifest. An unclassified
  column makes the privacy hook block every commit.
- Record the measured effect alongside the change.
- Branches, review and PRs follow *Pull requests* below.
- `.claude/settings.json` enforces some of these rules: deny and ask
  permissions, pytest at the end of each turn, `ruff check` after each Python
  edit (the hooks need `jq`, built into macOS; without it they do nothing).
  A denied call is a rule, not an obstacle: don't route around it; ask.
- **One home per fact.** Each kind of fact lives in one file:

  | fact | home |
  |---|---|
  | decisions and the rules they set | the ADR in `adr/` |
  | decision rule for prompt changes | `adr/0006-decision-rule-for-prompt-changes.md` |
  | terms | `GLOSSARY.md` |
  | invariants and working rules | `CLAUDE.md` |
  | harness and procedure | `evals/README.md` |
  | eval run procedure | `evals/README.md` |
  | results, baselines and md5 ledgers | `evals/BASELINES.md` |
  | how the privacy hooks work | `hooks/README.md` |
  | status and next steps | `TODO.md` |

  Elsewhere, link to the home instead of restating it; a one-line pointer
  naming the home is fine. `README.md` is the public overview: it may
  summarise a fact in a sentence or two with a link to its home, but not
  restate the rule in full. Current-state docs hold no history: that's in
  git and the ledgers. Say each thing once, in the shortest form that
  stays exact.

## Pull requests

`/open-pr <title>` (`.claude/skills/open-pr/SKILL.md`) runs steps 2–4 below:
it stops for my approval before the push in step 4, then pushes and opens
the PR. (The skill numbers its own steps separately.)

1. One topic per branch. Never commit to `main`.
2. Before opening a PR, run the code-reviewer subagent. Fix or note each
   introduced finding; inherited ones go under *Not in this PR*
   (`.claude/agents/code-reviewer.md`, *Finding standards*). If anything
   changed, re-run it so the report matches HEAD, within the round limit
   and re-review scope in `/open-pr` step 3, which also has the
   ledger-only light path.
   **No plan changes in passing:** if a fix would change a decision,
   plan, threshold or invariant beyond the branch's topic, don't make it
   here. Stop, propose a separate branch, and list it under *Not in this
   PR*.
3. Write the PR body from `.github/pull_request_template.md` into
   `docs/pr-body.md` (gitignored), including the reviewer's report. Run
   `hooks/check_private.py --file docs/pr-body.md` and
   `hooks/check_private.py --text '<title>'`; both must exit 0. Quote the
   title with single quotes (a `'` inside becomes `'\''`), never double:
   titles often contain backticks or `$`. In the PR body, report privacy
   results as pass/fail only, with no counts, line numbers or locations.
   Before asking me to read the body, delete the template's HTML comments,
   then check no <…> placeholders remain outside the
   `<details>`/`<summary>` tags. Then stop and ask me to read it: the PR is
   public.
4. After I approve: `git push -u origin <branch>`, then
   `gh pr create --base main --title '<title>' --body-file docs/pr-body.md`.
5. Never merge. I merge after reading the diff and the CI result.

## Where to look

- `TODO.md` — current state, gaps, open questions
- `evals/BASELINES.md` — baselines and md5 ledgers
- `GLOSSARY.md` — every term, what is not in code yet, and what was renamed
- `evals/README.md` — the harness, every flag, how to compare two runs
- `labels/art_number.py:1-13` — the four ART format families and their provenance
- `tests/test_resolve.py`, `TestCorrectionSafety` — why correction safety is the
  number that matters
- `.claude/agents/code-reviewer.md` — review rules
- `adr/` — architecture decisions; `0001` splits the work between model and code

# CLAUDE.md

Takes photos of Stone Island / C.P. Company garment labels and produces
structured listing data. Two vision calls transcribe the label, a deterministic
decoder parses the ART number, and a private catalogue resolves it to a real
product. Pre-launch, one developer, no users.

Not an agent loop: `Agent` is pydantic-ai's constrained-extraction wrapper,
called twice.

This file describes stable architecture, domain invariants and working
constraints. `TODO.md` describes what is currently changing — gaps, in-flight
work, current scores.

## Flow

```
main.py  /  app/routes.py
  └─ labels/pipeline.py    extract_bytes() — the only join point
       ├─ labels/transcribe.py   2 vision calls → LabelReading   (only module that calls an API)
       ├─ labels/art_number.py   parse() → Art                   (pure, no I/O)
       └─ labels/catalogue.py    resolve() → Resolution          (reads the private CSV)
                                     ↓
                                 labels/schemas.py → Extraction
```

`schemas.py` is shared vocabulary and imports nothing of ours. `art_number.py`
and `catalogue.py` don't know about each other — `pipeline.py` is where they
meet. Nothing imports `app/` or `main.py`.

## Commands

| | |
|---|---|
| install | `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` |
| tests | `.venv/bin/python -m pytest` — offline, no API key |
| CLI | `.venv/bin/python main.py <art.jpg> [details.jpg]` |
| web | `.venv/bin/flask --app app run` |
| decoder score | `.venv/bin/python tests/report_art_number.py` |
| eval, offline | `.venv/bin/python tests/eval_transcription.py --model test --no-save` |
| eval, real | `.venv/bin/python tests/eval_transcription.py --repeat 3 --note "..."` |

## Domain invariants

**`needs_review` is the gate between a bad read and a published listing**
(`labels/pipeline.py:50-56`). Any new field in `Extraction` must explicitly be
considered for this gate. Changing what flags is a product decision, not a
refactor.

**Season tables are frozen data, never a formula** (`labels/art_number.py`,
`SI_SEASON` / `CP_MODERN_SEASON`). Unknown keys return `None` rather than
extrapolating. Extend a table by adding entries; never restore the generating
rule at runtime.

**Transcription only transcribes** (`labels/transcribe.py`, `ART_PROMPT`). It
must not identify, authenticate, infer or correct. Correction belongs downstream
in `catalogue.py`, where it gets recorded.

**Unreadable characters become `?`, never a guess.** `not_visible` means no ART
number is present in the photo; `illegible` means one is present but unreadable.

**Corrections always surface** (`tests/test_pipeline.py:88-89`). A `corrected`
resolution is a silent substitution, so it forces `needs_review`. Only `exact`
is confident (`labels/catalogue.py`, `Resolution`).

**Catalogue misses deliberately do NOT flag** (`tests/test_pipeline.py:93-94`).
Flagging every miss would make the flag meaningless. This is not a bug — don't
"fix" it without changing the product semantics.

**Private data never enters git** (`.gitignore:229-236`). Catalogue, photos,
manifest, results — photos can carry live Certilogo codes. Never commit them,
never paste a code into a commit message or issue.

## Engineering constraints

- `labels/transcribe.py` is the only module permitted to call an API. Everything
  else is pure or reads local files — that's why the suite is offline and fast.
- All model calls use the shared 60s timeout (`MODEL_SETTINGS`). Do not remove
  it; it is the only hard cap in the system.
- Agents are built lazily and `@cache`d. Importing the module must not require
  an API key.
- `Extraction` stays JSON-serialisable and `all_reads` stays plain dicts
  (`tests/test_pipeline.py:198-199`) — `main.py` does `json.dumps(asdict(...))`.
- In tests, patch the name as `pipeline.py` imported it
  (`labels.pipeline.transcribe`), not the source function
  (`tests/test_pipeline.py:4-7`). Same for the `@cache`d `load_catalogue`.
- A green test run without the private catalogue is not a full test run —
  catalogue-dependent tests skip, never fail (`tests/conftest.py:3-4`). Derive
  test codes from the `conftest.py` fixtures.

## Working rules

- An eval result must identify the exact code and prompt that produced it.
  Commit, then run; a dirty report's fingerprint points at code you didn't test.
- Change one variable per eval run.
- Prompt or model changes require a run against the current baseline
  (path: `TODO.md`).
- Never weaken, skip or delete a test, and never alter eval ground truth, to
  make a result pass. `evals/manifest.csv` is hand-checked by eye.
- Record the measured effect alongside the change.
- Run the code-reviewer subagent before merging.

## Where to look

- `TODO.md` — current state, gaps, open questions, baseline
- `evals/README.md` — the harness, every flag, how to compare two runs
- `labels/art_number.py:1-13` — the four ART format families and their provenance
- `tests/test_resolve.py`, `TestCorrectionSafety` — why correction safety is the
  number that matters
- `.claude/agents/code-reviewer.md` — review rules
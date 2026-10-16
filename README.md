# Street Garms - Listing Tool

![Street Garms Logo](assets/logosg.png)

Turns photos of Stone Island and C.P. Company garment labels into structured
listing data (product name, season, garment type) for a reseller of
second-hand pieces. A vision model transcribes the label, a deterministic decoder
parses the ART number, and a private catalogue resolves it to a real product.
Pre-launch, one developer, no users.

## The problem

Each listing starts with the ART number, the product code on the label. It is often
faded or garment-dyed, and often printed with no caption among importer text,
phone numbers and dates. Reading it by eye and then identifying the product and
season is slow, and one misread character can point to a different garment.

## The key decision: the model only transcribes

- **Transcribe** (`labels/transcribe.py`): one vision call for the ART number.
  (A second, care-label read exists but is switched off for now.) The prompt
  forbids identifying, inferring or correcting. An unreadable character becomes
  `?`, never a guess.
- **Decode** (`labels/art_number.py`): pure code with no I/O. It identifies the
  format family and decodes season and brand from lookup tables.
- **Resolve** (`labels/catalogue.py`): exact catalogue lookup. On a miss it tries
  single-character OCR confusions (0/O, 1/I, 5/S, 8/B, 6/G). Only `exact` is confident.

**`needs_review` is the gate to a human** (`labels/pipeline.py`). Any of these
sets it: a read that is not `clear`, an ambiguous character, a decoder flag, an
unrecognised format, a missing year, or a `corrected` or `ambiguous` match.
A single model call that reads the label and names the product was rejected. It
can misread the code and still return a confident title, with no record of what
was read versus inferred. Here, every catalogue correction is explicit and forces
review. `TestCorrectionSafety` (`tests/test_resolve.py`) applies every single
confusion-pair substitution to every catalogue code. Of these 12,829 synthetic
misreads, 0 are corrected to the wrong garment and 12,819 are recovered. The other
10 land on another real code and resolve as `exact`. On an otherwise clean read,
those 10 would publish under the wrong title without review.

## Flow

```
main.py  /  app/routes.py
  └─ labels/pipeline.py    extract_bytes() — the only join point
       ├─ labels/transcribe.py   1 vision call → LabelReading    (only module that calls an API)
       ├─ labels/art_number.py   parse() → Art                   (pure, no I/O)
       └─ labels/catalogue.py    resolve() → Resolution          (reads the private CSV)
                                     ↓
                                 labels/schemas.py → Extraction
```

## Evaluation

**Baseline, 2026-09-25:** `anthropic:claude-sonnet-5`, tag `eval-baseline-2026-09-25b`.
18 positive photos (14 distinct codes) and 4 photos with no ART number, each read
3 times; all 66 reads scored. Harness: [evals/README.md](evals/README.md).

| rate | current prompt | previous prompt |
|---|---|---|
| missed (no code returned) | 18 of 54 (33.3%) | 42 of 54 (77.8%) |
| exact match | 36 of 54 (66.7%) | 12 of 54 (22.2%) |
| wrong, of reads declared `clear` | 0 of 36 | 0 of 9 |
| code invented on a no-code photo | 0 of 12 | 0 of 12 |

**Decision rule, committed before the first baseline.** The unit is the photo,
which counts as missed if at least 2 of its 3 reads return nothing. A change
passes if wins (missed → not missed) beat losses on a two-sided sign test at
p < 0.05: 6–0, 8–1 or 10–2, with 3 or more losses rejecting it. Two guardrails
reject it regardless: any invented code declared `clear`, or a photo newly
overconfident in at least 2 of 3 reads. The current prompt passed 8–0 (p ≈ 0.008).
The rule's out-of-sample check was waived for this merge.

**Scope.** Every photo gave the same read on all 3 repeats, so in effect this is
one sample per photo: 12 were read correctly and 6 were missed. The results are
in-sample, because the change was accepted on this same set. They cover Stone
Island only, and two decoder formats (`si_numeric`, `si_namespace`). The catalogue's
489 C.P. modern and 86 Stone Island alphanumeric rows use formats the eval has never
tested. All 4 no-code photos are Certilogo-type (one care label, three crops), and
3 positives are care labels of garments already in the set.

## Running it

```bash
uv sync                                             # needs uv; creates .venv from uv.lock
cp .env.example .env                                # add ANTHROPIC_API_KEY
git config core.hooksPath hooks                     # privacy hooks, once per clone
.venv/bin/python main.py <label.jpg>                  # CLI, prints JSON
.venv/bin/flask --app app run                       # web upload form
.venv/bin/python -m pytest                          # offline, no API key
.venv/bin/ruff check .                              # lint, rules in pyproject.toml
.venv/bin/pyright                                   # types, basic mode
.venv/bin/python tests/report_art_number.py         # decoder score, needs catalogue
.venv/bin/python tests/eval_transcription.py --model test --no-save   # harness, no API calls
.venv/bin/python tests/eval_transcription.py --repeat 3 --workers 1 --note "..."  # as baseline
```

The catalogue, eval photos and manifest are private and gitignored. Tests that need
the catalogue skip rather than fail: currently 133 pass and 41 skip on a fresh clone,
and 174 pass with it.

## How AI coding agents are used

- **`CLAUDE.md` is the rule set.** It covers architecture, domain invariants and
  working rules: commit before an eval run, change one variable per run, and never
  weaken a test or edit ground truth to pass. `TODO.md` holds current state.
- **`.claude/agents/code-reviewer.md`** is a reviewer subagent, instructed not to
  edit, commit or push. It reviews the branch against `main`, `CLAUDE.md` and the
  ADRs, and runs the test suite locally, where the private catalogue is present.
  It counts code-shaped tokens and photo filenames in each changed file and in the
  commit messages, and reports privacy as pass/fail only, never counts or values. Ground truth is gitignored,
  so it never appears in a diff; the reviewer hashes the manifest and compares it
  with the md5 ledger kept by hand in `TODO.md`. A verdict of Ready to merge
  requires a clean tree, so the report matches the commit it describes.
- **Pull requests** follow `CLAUDE.md`: one topic per branch, the reviewer before
  the PR opens, and a body written from `.github/pull_request_template.md` that
  includes the reviewer's report and is read by the maintainer before it is
  published. Agents never merge.
- **Enforcement.** A GitHub ruleset on `main` is the hard limit: no direct or
  force pushes, no deletion, and every change arrives by PR with a green CI
  run. `.claude/settings.json` (tracked, so changes are reviewed) adds agent
  limits on top: it denies reading `.env`, editing ground truth, photos or
  results, `gh pr merge`, and the common forms of pushing or force-pushing
  to `main`; it asks before any other push and before reading private data.
  Hooks run pytest when an agent ends its turn and `ruff check` after each
  Python edit, and hand any failure back to it. These rules match command
  patterns, and Read rules don't cover shell commands, so the private-data
  rules in `CLAUDE.md` remain instructions as well.
- **CI** (`.github/workflows/tests.yml`) runs `ruff check`, `pyright` and `pytest -rs` on pushes and PRs
  to `main`, with no catalogue or API key, so it is currently the 133-pass, 41-skip run.

## Known limitations

- 6 of 18 positive photos are missed on every read, 5 of them at 1200x1600.
  Images are sent uncropped and unresized. Two eval photos share one expected code.
- Decoder seasons agree with the catalogue on 2,288 of 2,359 checkable rows. The
  71 disagreements are untriaged, so that ground truth is unverified.
- On an exact match the season comes from the decoder, not the catalogue, so the
  title and season can disagree unflagged. Which source wins is undecided.
- CI runs only 1 of the 8 `needs_review` tests, because the rest need the catalogue.
  The decoder has no unit tests. There is no per-call cost tracking or eval spend cap.
- `claude-sonnet-5` has no dated snapshot, so a silent model update can't be told
  apart from other changes in a run diff.
  The CLI shows a traceback on API failure, and the web form has no auth or rate limit.

## Deliberate choices and open questions

- **Catalogue misses don't set `needs_review`.** Flagging every miss would make the flag meaningless.
- **Not an agent loop.** pydantic-ai's `Agent` is a constrained-extraction wrapper, called once per listing.
- **The care-label read is switched off.** Only the ART number is read for now. The details prompt and agent stay in `labels/transcribe.py`, but `transcribe()` doesn't call them, which halves the cost per listing.
- **Open:** whether clean reads auto-publish or every listing gets human review.

# Street Garms - Listing Tool

![Street Garms Logo](assets/logosg.png)

Reads the ART number from photos of Stone Island and C.P. Company garment
labels, the first step towards structured listing data (product name, season,
garment type) for a reseller of second-hand pieces. A vision model transcribes
the label, a deterministic parser parses the ART number, and a private
catalogue resolves it to a real product. Pre-launch, one developer, no users:
a proof of concept that moves on when it meets the phase 1 gate
([ADR-0002](adr/0002-phase-1-acceptance.md)).

## The problem

Each listing starts with the ART number, the product code on the label.
Reading it by eye and then identifying the product and season is slow, and one
misread character can point to a different garment. It represents an area for
automation and efficiency using a combination of AI and code.

## The key decision: the model only transcribes

- **Transcribe** (`labels/transcribe.py`): one vision call for the ART number. The prompt
  forbids identifying, inferring or correcting. An unreadable character becomes
  `?`, never a guess.
- **Parse** (`labels/art_number.py`): pure code with no I/O. It identifies the
  format family and decodes season and brand from lookup tables.
- **Resolve** (`labels/catalogue.py`): exact catalogue lookup. On a miss it tries
  single-character OCR confusions (0/O, 1/I, 5/S, 8/B, 6/G). Only `exact` is confident.

**`needs_review` is the gate to a human** (`labels/pipeline.py`). Any of these
sets it: a read that is not `clear`, an ambiguous character, a parser flag, a
split problem ([ADR-0005](adr/0005-art-line-split.md), *Flag table*), an
unrecognised format, a missing year, or a `corrected` or `ambiguous` match.
A single model call that reads the label and names the product was rejected. It
can misread the code and still return a confident title, with no record of what
was read versus inferred. Here, every catalogue correction is explicit and forces
review. `TestCorrectionSafety` (`tests/test_resolve.py`) applies every single
confusion-pair substitution to every catalogue code. Of these 12,829 synthetic
misreads, 0 are corrected to the wrong garment and 12,819 are recovered. The other
10 land on another real code and resolve as `exact`. On an otherwise clean read,
those 10 would publish under the wrong title without review.

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

Terms: [GLOSSARY.md](GLOSSARY.md).

## Where it stands

Phase 1 has not been attempted yet. The run 0 code changes, a paid baseline
and a held-out set of 30 garments come first ([TODO.md](TODO.md)).

**Phase 1 gate.** Phase 1 passes on a held-out set of 30 garments, read 3
times each, when at least 80% of garment-sides (24 of 30) read the ART
number's base correctly. Staff confirm every result at the next stage, so the
gate measures only that. Full gate and set rules:
[ADR-0002](adr/0002-phase-1-acceptance.md).

**Current baseline, 2026-10-08:** 46% of positive reads were exact, and 18 of
84 would have been published wrong without review. The set is small and has
no `si_alpha`. Results, earlier baselines and
the decision rule for prompt changes
([ADR-0006](adr/0006-decision-rule-for-prompt-changes.md)) are in
[evals/BASELINES.md](evals/BASELINES.md); the harness is in
[evals/README.md](evals/README.md).

## How AI coding agents are used

- **`CLAUDE.md` is the rule set.** It covers architecture, domain invariants and
  working rules: commit before an eval run, change one variable per run, and never
  weaken a test or edit ground truth to pass. `TODO.md` holds current state;
  decisions are ADRs in `adr/`.
- **A reviewer subagent** (`.claude/agents/code-reviewer.md`), told not to
  edit, commit or push, reviews each branch against `main`, `CLAUDE.md` and the
  ADRs. It runs the suite with the private catalogue present, checks the branch
  for private data, and compares the manifest's md5 with the hand-kept ledger,
  since ground truth never appears in a diff.
- **Pull requests**: one topic per branch. `/open-pr`
  (`.claude/skills/open-pr/SKILL.md`) runs the reviewer, writes the body with
  its report, and stops for the maintainer to read it before pushing. Agents
  never merge.
- **Enforcement.** A GitHub ruleset on `main` is the hard limit: every change
  arrives by PR with a green CI run, with no force pushes or deletion.
  `.claude/settings.json` adds agent limits on top: it denies or asks before
  reading private data, editing ground truth, pushing and merging, and hooks
  run pytest and `ruff check` after an agent's edits.
- **Privacy hooks** (`hooks/`) check every commit locally against the real
  private values, which CI never sees, and report findings without the value.
  How they work: [hooks/README.md](hooks/README.md).
- **These are pattern matches, not a guarantee.** A command phrased another
  way, or a read through the shell, gets past them. So the private-data rules
  stay in `CLAUDE.md` as instructions too, and the reviewer flags every change
  to `hooks/` or the settings for the maintainer.
- **CI** (`.github/workflows/tests.yml`) runs `ruff check`, `pyright` and
  `pytest -rs` on pushes and PRs to `main`, with no catalogue or API key.

## Running it

```bash
uv sync                                             # needs uv; creates .venv from uv.lock
cp .env.example .env                                # add ANTHROPIC_API_KEY
git config core.hooksPath hooks                     # privacy hooks, once per clone
.venv/bin/python main.py <label.jpg>                # CLI, prints JSON
.venv/bin/flask --app app run                       # web upload form
.venv/bin/python -m pytest                          # offline, no API key
.venv/bin/ruff check .                              # lint, rules in pyproject.toml
.venv/bin/pyright                                   # types, basic mode
.venv/bin/python tests/report_art_number.py         # parser score, needs catalogue
.venv/bin/python tests/eval_transcription.py --model test --no-save   # harness, no API calls
.venv/bin/python tests/eval_transcription.py --repeat 3 --workers 1 --note "..."  # paid: real API calls
```

The catalogue, eval photos and manifest are private and gitignored. Tests that
need the catalogue skip rather than fail, so a fresh clone and CI run green
without it.

## Known limitations

Most serious first.

- **Silent wrong titles.** A misread that lands on another real code resolves
  `exact` and isn't flagged (10 of the 12,829 synthetic misreads above). On an
  exact match the season comes from the parser, not the catalogue, so title and
  season can disagree unflagged; which source wins is undecided.
- **Unverified ground.** The eval has never tested `si_alpha`. Parser seasons
  agree with the catalogue on 2,287 of 2,357 checkable rows; the 70
  disagreements are untriaged, so that ground truth is unverified.
- **Thin test coverage in CI.** CI runs 33 of the 40 `needs_review` test
  cases, on a synthetic catalogue; the other 7 need the real one. The parser
  has no unit tests.
- **Recognition.** Images are sent uncropped and unresized. On the archived set,
  5 of the 6 photos missed on every read were 1200x1600
  ([evals/BASELINES.md](evals/BASELINES.md)).
- **Operations.** There is no per-call cost tracking or eval spend cap.
  `claude-sonnet-5` has no dated snapshot, so a silent model update can't be
  told apart from other changes in a run diff. The web form has no auth or
  rate limit.
- **The CLI** shows a traceback on API failure.

## Deliberate choices and open questions

- **Catalogue misses don't set `needs_review`.** Flagging every miss would make the flag meaningless.
  Pending: ADR-0004 will decide how misses flag, after phase 1.
- **Not an agent loop.** pydantic-ai's `Agent` is a constrained-extraction wrapper, called once per listing.
- **No care-label read.** Only the ART number is read, one call per listing. The earlier care-label details read (size, composition, origin, CLG, colour) was removed; it is kept at the `parked/details-read` tag.
- **Later:** whether clean reads auto-publish or every listing gets human review.
  After phase 1, staff confirm every result; auto-publishing would first need
  a silent-error bar in the gate (ADR-0002).

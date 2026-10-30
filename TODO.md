# TODO

Current state and in-flight work. Stable architecture and invariants are in
CLAUDE.md. Phase 1 gate: adr/0002. Baselines and md5 ledgers: evals/BASELINES.md.

## Phase 1

*Code* changes nothing the model sees. A change to the prompt, schema, image
or model is a run under *Runs*, one per run.

### Photos
- [ ] Photo session: reach ~70 development photos and ~30 test garments (one photo
      per garment-side for test). Run the timing study at the same session.
- [ ] Label every photo by eye: `garment`, `side`, `expected_art_line`,
      `expected_art_base`. Re-check by eye every `expected_art_base` that
      isn't a catalogue key
- [ ] `evals/README.md`: the catalogue may prompt a re-check, never supply
      a label value
- [ ] Test set: readable photos only, judged by eye when labelled, each
      with a known `expected_art_base` (never `UNKNOWN`); no no-code photos;
      one that doesn't qualify is replaced, never dropped after a run
      (ADR-0002)
- [ ] Test garments chosen by a rule fixed before the session (e.g. the
      next N off the rail), not by eye
- [ ] Decide who takes the test photos: some by staff, or note the single
      capture regime as a limitation
- [ ] Split by garment; freeze the test manifest (md5 in BASELINES.md)
- [ ] Both sets cover every format family, `si_alpha` included (ADR-0002)

### Code
- [ ] The split (ADR-0005):
      1. done: split structure (`split_art_line`)
      2. done: split tails (`FAMILY_TAILS`)
      3. done: wiring (`from_reading()`)
- [x] Scorer, per read: correct = `from_reading()`'s `art_base` equals
      `expected_art_base` (base-exact, ADR-0002). `load_manifest` reads
      `expected_art_base`. Dev rows whose `expected_art_base` is `UNKNOWN`
      are left out and counted
- [x] Scorer, per garment-side (`ReportEvaluator`, like `PerPhotoCounts`):
      correct if 2 of 3 reads are; the correct rate. Mean per-read accuracy
      beside it (production reads once). Needs `garment` and `side` in case
      metadata. Dev garment-sides with several photos are also reported per
      photo
- [x] Scorer tests, offline, synthetic values only, so they run in CI
- [x] Replay mode: rescore a saved report's reads through `from_reading()`,
      no API call. Records the source report and the scoring commit; every
      replay's output is saved
- [ ] `--holdout` flag: runs the test manifest, prints totals only
- [x] Eval provenance: the header records the photos sent (by `id`), the
      user message and the library versions; `--baseline` warns when they
      differ. Replaces the manual photo-hash and pip freeze steps
- [ ] Usage / cost capture in code (SG billing?): before the model
      comparison. Run 0's spend is read off the Anthropic console before
      and after, and recorded in BASELINES.md
- [x] Schema fingerprint: the output schema in its own `schema` header
      field, beside `prompt`, so `prompt` still matches the current
      baseline's; `--baseline` warns when it differs
- [ ] Spend cap: print the call count up front, confirm past a threshold,
      before the model comparison
- [ ] Model identity: if `response.model` returns only `claude-sonnet-5`, a
      model change can't be told from a prompt change in a run diff. Before
      the model comparison
- [ ] ADR-0006's unit in the report: each positive garment-side's correct
      reads summed over its photos (the garment-sides table counts photos;
      until then, sum by hand from base per photo). Same branch:
      `PerPhotoCounts`' docstring and `TestPerPhotoCounts`' still call it
      ADR-0006's table. Before the first iteration

### Runs (development only)
- [x] Replay the 2026-10-08 baseline's saved reads (free): the first
      base-exact number. In-sample (the split was designed against these
      failures), so a sanity check, not evidence
- [ ] Run 0: paid, whole dev set, `--repeat 3`, once the dev set is complete
      (ADR-0002); recorded as the new baseline. `p34`–`p55` also reported
      separately: the first out-of-sample reads. Nothing the model sees
      changes before it, so its `p01`–`p33` reads compare directly with
      the 2026-10-08 reads
- [ ] Dev set freezes when that baseline is recorded; new photos go to test
- [x] Prompt-change policy for phase 1 runs (ADR-0006)
- [ ] Iterations, until dev clears 80% with a margin. The margin is
      undecided: set it after run 0 and before the first iteration,
      informed by how `p34`–`p55` compare with the rest. If it becomes a
      rule, it goes in ADR-0002. Candidates: auto-rotate, image
      resizing?, compare models (Sonnet, Opus, Haiku: check current
      versions), prompt gives character classes, never lengths (ADR-0001,
      *Trust rules*: decide first whether the prompt may describe formats)
- [ ] Once dev clears 80%: revisit a "no worse" path for a cheaper or
      faster model (ADR-0006). If you want one, decide its rule before
      running it: compared against the last model accepted on wins, with
      usage / cost capture in place
- [ ] Replace `ART_PROMPT`'s real examples with invented ones: 8–9
      characters, one with a leading zero, checked not to be catalogue keys
      or test-set codes (pass/fail, no rows printed)
- [ ] Barcode guidance in the prompt

### Gate
- [ ] Gate attempt on the test set, from a tagged commit; at most 3 in
      phase 1, totals only (ADR-0002). Not before `ART_PROMPT`'s real
      examples are replaced. The report says sides of one garment aren't
      independent: a pass isn't proof of 80%

## Later
- [ ] Phase 2: staff trial. Staff confirm or correct every result before it's
      recorded (ADR-0002, *Context*); acceptance criteria agreed with the
      product team. The result page shows the ART number only: decoder flags
      and product name hidden, code kept
- [ ] Before the staff trial: the run rule for later runs (ADR-0006
      revisit), with ADR-0001's per-run rule

### Backlog
Not measured by the phase 1 gate. Kept for when flags, the catalogue lookup
or unconfirmed results come into scope.

- [ ] Split steps 4 (product decisions, one per branch) and 5 (renames,
      including `matched_art` → `resolved_key`, `miss` → `no_key`;
      GLOSSARY.md, *Renamed*)
- [ ] Scorer, flags: per read, flagged and silent error (wrong and not
      flagged); per garment-side, silent error if any read is, unflagged if
      2 of 3 reads are correct and unflagged. Prints correct/wrong ×
      flagged/unflagged, silent errors split by catalogue outcome (a wrong
      exact hit vs `no_key`). Align GLOSSARY.md's *silent error* with the
      ADRs on a clean read of an illegible photo. Needed before any result
      is used without a person confirming it (ADR-0002)
- [ ] Wrong-and-unflagged replay against `expected_art_base`, a diagnostic
      once the flag scorer exists (ADR-0001, *Evidence*, measured 18 of 84
      against `expected_art_number`)
- [ ] Scorer, catalogue: correct = the catalogue result is right for
      `expected_art_base` (`resolved_key` equals it if it's a catalogue key,
      else `no_key` and `art_base` equals it). Adds the catalogue md5 to the
      run fingerprint
- [ ] Line-exact per photo, for dev diagnosis
- [ ] Error types per read: missed, confusion-pair swap, other single edit,
      joined text, wrong line, invented. Replaces CER, or CER stays
      dev-only
- [ ] `expected_legibility` (readable / illegible / absent) and an excluded
      count, if dev needs illegible photos scored apart. Classify it in
      `MANIFEST_COLUMNS` first, add it to GLOSSARY.md
- [ ] Fake-read mode (a read returning `expected_art_line`), then delete
      `tests/report_split_on_truth.py`
- [ ] multi_line (a newline in the read): undecided; only if a dev run
      shows one
- [ ] Whether the possible-counterfeit flag stays a review reason
      (ADR-0005, *Flag table*). Season, year, brand and garment decoding
      stay for display; the season precedence fix (*Bugs and decisions*)
      decides the source on a catalogue hit
- [ ] ADR-0004, the catalogue rules: catalogue misses (leaning: every miss
      flags); the confusion-pair margin; bare/compound pairs (ADR-0001,
      *Pending decisions*), fused pairs included; whether a confident hit
      relaxes no season in the code (`season_not_in_code`, ADR-0005). Same
      PR: `review_reasons`, CLAUDE.md's invariant and its restatements
      (GLOSSARY.md's catalogue outcome, "deliberately doesn't"; README.md,
      *Deliberate choices*), and the tests it inverts:
      `test_catalogue_miss_does_not_flag`,
      `test_pin_catalogue_miss_does_not_flag` and the split's pin tests
      (ADR-0005's accepted costs), named when they're written. Drafted from
      run 0's baseline (ADR-0001, *Pending decisions*)

### Bugs and decisions
- [ ] Season precedence: on an exact catalogue hit the season comes from the
      parser, so it can disagree with the product name, unflagged (~3% of
      hits). A decision on which source wins; the rule then goes in CLAUDE.md
- [ ] Brand can come out empty unflagged: no printed-brand fallback, so a
      known season plus a catalogue miss gives `brand=None`. A `needs_review`
      decision
- [ ] CLI error handling: `cli()` in `main.py` prints a traceback on an API
      failure; `capture()` in `app/routes.py` already handles it
- [ ] 70 parser/catalogue season disagreements, untriaged
      (`tests/report_art_number.py`): spot-check ten for parser bug vs
      catalogue typo
- [ ] Set the client's and the agent's output retries explicitly, log the
      request count per call, record worst-case latency in CLAUDE.md
- [ ] Season tables: `SI_SEASON` and `CP_MODERN_SEASON` are built by a
      comprehension over a range at import, the formula CLAUDE.md forbids.
      Write both as literal dicts; no change in behaviour
- [ ] Privacy ADR: a Certilogo code is never shown as a code, never in an
      identifying field and never logged; it is stored alongside the photo

### Out of phase 1
- [ ] Data Matrix ADR (new number; 0002 is taken) and stage: decode, keep Data
      Matrix only, parse `ART-Vnnnn-size-TOM…`. The payload's CLG tail is
      dropped at parse and never stored, logged or raised; QR and Code 128
      contents are never returned. The vision path must be complete when the
      stage returns nothing
- [ ] Capture guidance in the web UI: back tag with the square code in frame,
      decode on upload, prompt for a retake if nothing decodes
- [ ] ADR-0001 runs 3 (`next_line`) and 4 (size, brand, colour)
- [ ] Catalogue index (ADR-0003)
- [ ] Catalogue inspection: bare/compound duplicates, keys with a suffix
      typed on, odd-length rows. The Stone Island numeric era-length table
      only on ADR-0005's trigger
- [ ] Parser unit tests beyond the split: format detection, the `len(s) >= 8`
      guard, the `/181` strip, the `222` flag, the `'10'` carve-out. Season
      assertions wait for the 70-row triage
- [ ] `ArtNumberReading`'s docstring still says "framed on the ART number
      tag"; it reaches the model, so change it on its own and measure it
- [ ] Crop to the label region before the call (resizing is under *Runs*)

### Housekeeping
- [ ] Rename the harness's "flagged but correct" to "ambiguous but correct":
      it counts `ambiguous_characters`, not `needs_review`, so
      `evals/README.md` and BASELINES.md describe it wrongly
- [ ] `hooks/check_private.py`: take `TODO.md` out of `LEDGER_FILES`, so
      ledgers live only in `evals/BASELINES.md` (stricter; a `hooks/`
      change, needs sign-off)
- [ ] CLAUDE.md, docs branch: install row says `core.hooksPath` is yours,
      once per clone (agents are denied it); one line on private-data reads matching
      `.claude/settings.json`, with "eval, real" marked paid and run only
      when asked (test-set rules: link ADR-0002); merge the two
      `evals/README.md` rows of the one-home table and fold *Where to look*
      into it; line numbers to names; PR mechanics into `/open-pr`, keeping
      the approval stop, never merging, one topic per branch and no plan
      changes in passing

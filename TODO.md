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
      `expected_art_base`, and new `expected_legibility` (readable /
      illegible / absent). Classify it in `MANIFEST_COLUMNS` first, add it
      to GLOSSARY.md
- [ ] Split by garment; freeze the test manifest (md5 in BASELINES.md)
- [ ] Both sets cover every format family, `si_alpha` included (ADR-0002)

### Code
- [ ] The split (ADR-0005), one branch per step:
      1. split structure, not wired into the gate
      2. split tails
      3. wiring: changes the gate, measured by the checkpoint replay
      4. product decisions, one per branch
      5. renames
      Known silent error until the wiring: a `clear` read with `?` past the
      decoded prefix never resolves, so it misses, and passes the gate
      unflagged (ADR-0002)
- [ ] multi_line (a newline in the read): undecided, unconfirmed in reads
- [ ] Whether the possible-counterfeit flag stays a review reason, now that
      the split checks it in `art_base` only. Season, year, brand and
      garment decoding stay for display; the season precedence fix (*Later*)
      decides the source on a catalogue hit
- [ ] ADR-0004, the catalogue rules (ADR-0001, *Pending decisions*):
      catalogue misses, so a misread that misses never shows "looks right"
      (leaning: every miss flags in phase 1); the confusion-pair margin;
      bare/compound pairs, fused pairs included; whether no season in the
      code (`season_not_in_code`) flags unless the hit is confident. Same PR:
      `review_reasons`, CLAUDE.md's invariant, and the tests it inverts:
      `test_catalogue_miss_does_not_flag` and the split's pin tests
      `test_pin_si_insertion_8_to_9_does_not_flag`,
      `test_pin_si_end_truncation_9_to_8_does_not_flag`,
      `test_pin_si_front_truncation_does_not_flag`,
      `test_pin_exact_hit_one_swap_from_another_key`,
      `test_pin_bare_and_compound_pair` and
      `test_pin_fused_catalogue_key_misses`. Lands after the checkpoint and
      run 0's baseline: it is drafted from that baseline (ADR-0001, *Pending
      decisions*), and the checkpoint replays run 0 alone
- [ ] Scorer, per read (`Evaluator`): run `from_reading()` on the saved read;
      correct = the catalogue result is right for `expected_art_base`
      (`resolved_key` equals it if it's a catalogue key, else `no_key` and
      the parsed `art_base` equals it; ADR-0002); flagged; silent error =
      wrong and not flagged
- [ ] Scorer, per garment-side (`ReportEvaluator`, like `PerPhotoCounts`):
      correct if 2 of 3 reads are, silent error if any read is, unflagged if
      2 of 3 reads are correct and unflagged; the three
      ADR-0002 bars and the excluded count. Needs `garment`, `side` and the
      by-eye label in case metadata. Keep line-exact and base-exact per photo
      for dev diagnosis
- [ ] Scorer tests on the synthetic catalogue, so they run in CI
- [ ] Eval provenance: harness hashes photos (replaces the broken recipe)
- [ ] Usage / cost capture (SG billing?): must land before the first paid run
- [ ] Rename `matched_art` → `resolved_key`, `miss` → `no_key` (GLOSSARY.md,
      *Renamed*)
- [ ] Schema fingerprint: hash the output schema into the report's `prompt`
      fingerprint, before any prompt or schema run
- [ ] Spend cap: print the call count up front, confirm past a threshold,
      before the model comparison
- [ ] `--holdout` flag: runs the test manifest, prints totals only

### Runs (development only)
- [ ] Replay baseline on saved reads (free)
- [ ] Checkpoint: the replay brings wrong-and-unflagged from 18 to at most 9
      of 84 positive reads, or stop and revisit ADR-0001 (ADR-0002)
- [ ] Run 0
- [ ] Dev set freezes when that baseline is recorded; new photos go to test
- [ ] Iterations: auto-rotate, image resizing?, compare models
      (Sonnet, Opus, Haiku: check current versions), prompt describes all
      known shapes, never catalogue values

### Gate
- [ ] Gate attempt on the test set, from a tagged commit; at most 3 in
      phase 1, totals only (ADR-0002)

## Later
- [ ] Phase 2: MVP app (acceptance criteria agreed with the product team)

### Bugs and decisions
- [ ] Season precedence: on an exact catalogue hit the season comes from the
      parser, so it can disagree with the product name, unflagged (~3% of
      hits). A decision on which source wins; the rule then goes in CLAUDE.md
- [ ] Brand can come out empty unflagged: no printed-brand fallback, so a
      known season plus a catalogue miss gives `brand=None`. A `needs_review`
      decision
- [ ] CLI error handling: `cli()` in `main.py` prints a traceback on an API
      failure; `capture()` in `app/routes.py` already handles it
- [ ] 71 parser/catalogue season disagreements, untriaged
      (`tests/report_art_number.py`): spot-check ten for parser bug vs
      catalogue typo
- [ ] Model identity: if `response.model` returns only `claude-sonnet-5`, a
      model change can't be told from a prompt change in a run diff
- [ ] Set the client's and the agent's output retries explicitly, log the
      request count per call, record worst-case latency in CLAUDE.md
- [ ] Prompt-change policy: does ADR-0006's rule (with ADR-0001's
      wrong-and-unflagged for the contract v2 runs) become the general gate
      for shipping a prompt change? Which metric, what margin, how many repeats

### Out of phase 1
- [ ] Data Matrix stage (new ADR number; 0002 is taken): decode, keep Data
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
      assertions wait for the 71-row triage
- [ ] `ArtNumberReading`'s docstring still says "framed on the ART number
      tag"; it reaches the model, so change it on its own and measure it
- [ ] Crop to the label region before the call (resizing is under *Runs*)

### Housekeeping
- [ ] CLAUDE.md, docs branch: install row says `core.hooksPath` is yours,
      once per clone (agents are denied it), and that a plain `uv sync`
      removes the notebooks; one line on private-data reads matching
      `.claude/settings.json`, with "eval, real" marked paid and run only
      when asked (test-set rules: link ADR-0002); merge the two
      `evals/README.md` rows of the one-home table and fold *Where to look*
      into it; line numbers to names; PR mechanics into `/open-pr`, keeping
      the approval stop, never merging, one topic per branch and no plan
      changes in passing

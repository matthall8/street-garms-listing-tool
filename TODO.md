# TODO

Current state and in-flight work. Stable architecture and invariants are in CLAUDE.md.

## Now

### The chain

Strictly in order — each item unblocks the next, and the last one is the point
of the whole sequence.

- [ ] **Fix the invalid `ANTHROPIC_API_KEY` in `.env`.** 5 min, blocks every
      item below. Add `.env.example` in the same change.

- [ ] **Allow negative cases in the eval harness.** ~30 min at the keyboard, and
      it is what makes the baseline worth recording.
  - `tests/eval_transcription.py:138` drops any row with an empty
    `expected_art_number`, so "there is no ART number in this photo" is
    unrepresentable and `not_visible` has zero coverage. Decide the convention
    first: "no code present" and "not yet labelled" are different states and
    must not share a representation.
  - Add `si_certilogo_01.png` as the first negative case — the ART-vs-Certilogo
    confusion the prompt guards against at `labels/transcribe.py:47-48`,
    already in the photos directory, unused.

- [ ] **Record the baseline.** `--repeat 3` on a clean tree. All six reports in
      `evals/results/` are pre-port format and rejected by `load_baseline()` —
      archive them to `evals/results/archive/` rather than deleting. Label what
      it actually covers in `--note`, including the resolution split (photos
      01-04 are 4032x3024, 05-15 are 1200x1600).

- [ ] **Measure the stashed prompt draft.** `stash@{0}` ("On evals: prompt draft:
      unlabelled ART numbers") targets bare ART numbers printed with no "ART"
      prefix — `evals/README.md:122-123`. Blocked on the negative case
      specifically, not on C.P. coverage: the draft makes the model hunt harder
      for a code, and on an all-positive manifest that can only ever look like
      an improvement.

### Independent of the chain

Neither blocks nor is blocked by the sequence above.

- [ ] **Add C.P. photos to the eval set.** Split out of the harness work because
      it needs garments and a camera, not desk time — bundled, it stalls the
      whole item. The manifest is 12 `si_numeric` + 3 `si_namespace`: two of
      five format families, against the spec in `evals/README.md:124-127`. The
      catalogue holds 489 `cp_modern` and 86 `si_alpha` rows, so roughly a fifth
      of stock is a format the eval has never tested. `cp_modern` at minimum;
      ideally `si_alpha` and one with a trailing colour code. Re-baseline after,
      since the manifest fingerprint changes.

- [ ] **Precedence fix: on an exact catalogue match, the catalogue supplies the
      season, not the decoder.** `labels/pipeline.py:33-35` takes year/season
      from the decoder even on an exact hit, so a listing ships with its title
      and its season field disagreeing — `03CMOW026A` shows "A/W 15 Soft Shell
      Goggle" beside AW 2017, with `needs_review` False. Roughly 3% of catalogue
      hits. Latent rather than bleeding: pre-launch, nothing is shipping yet.
      Independent of the 71-row triage. This is a decision about which source of
      truth wins, not a refactor — once decided, the precedence rule belongs in
      CLAUDE.md domain rules.

## Next

- [ ] **Preprocessing experiment.** `labels/transcribe.py:135-138` passes raw
      bytes to `BinaryContent` — no crop, no resize. The API downscales large
      images (confirm the threshold; believed ~1568px on the long edge), so
      small faded print on photos 01-04 may be lost before the model sees it.
      Cropping to the label region could do more for accuracy than any prompt
      edit, and it's currently neither measured nor controlled.

- [ ] **Decoder unit tests for `labels/art_number.py`** — no pytest coverage,
      needs no catalogue, so these are what make CI meaningful. Write the
      uncontroversial half now: format-family detection, the `len(s) >= 8`
      truncation guard, the `/181` colour-code strip, the `222` flag, the
      `0`→`O` repair, the `'10'` namespace carve-out. Hold the season
      assertions until after the 71-row triage, or you encode the bug as the
      expected value.

- [ ] **Capture usage and cost per call.** `.usage()` is discarded in
      `transcribe_art` / `transcribe_details`. One JSONL line per call:
      timestamp, model, prompt fingerprint, tokens in/out, latency, stop reason.
      Two calls per listing, so this is a unit-economics number. Also capture
      `response.model` into `run_metadata()` — check first whether it returns
      anything more specific than `claude-sonnet-5`; if it doesn't, note in
      `evals/README.md` that an unchanged prompt fingerprint beside a moved
      score means suspect the model.

- [ ] **CLI error handling.** `main.py:36` calls `extract()` bare, so any API
      failure prints a ~40-line traceback instead of a message. The web path
      already handles this (`app/routes.py:51-52`); the CLI is the odd one out.

- [ ] **Cap eval spend.** `--repeat` is unbounded and `--workers` defaults to 4,
      so a mistyped `--repeat 30` is 450 vision calls. Print the call count up
      front, confirm past a threshold. No `max_tokens` on either agent either.
      Once closed this may earn a line in CLAUDE.md conventions.

- [ ] **Top-level README.** Two lines today; names none of the commands.

- [ ] **CI on GitHub Actions.** After the decoder tests exist — without them a
      clean runner has no catalogue, most of the suite skips, and CI reports
      green while testing almost nothing.

## Known issues

- **71 decoder/catalogue season disagreements, untriaged.** `CP_MODERN_SEASON`
  samples look like a table offset. Spot-check ten by hand after the baseline —
  the goal is finding out whether these are decoder bugs or catalogue typos,
  not fixing all 71. Until then, 97.0% is measured against ground truth that
  hasn't been verified.

- **The eval set measures a narrower surface than "OCR".** Two of five format
  families, no negative cases, and two capture regimes in one set — a failure
  on photos 01-04 can't be attributed to the label versus the capture path.
  Being addressed in Now; noted here so a baseline number isn't over-read in
  the meantime.

- **`evals/photos/duplicates/` holds four `_dup` copies** (photos 05, 06, 08,
  15). Inert — the harness is manifest-driven, not glob-driven. If they're
  second captures of the same labels they'd be useful as a capture-variance
  check; otherwise delete them.

## Open questions

- **Auto-accept clean reads, or human review every listing?** Decides what
  "better OCR" means: if a human checks each listing, overconfidence is mildly
  interesting; if clean reads auto-publish, it's the only metric worth driving
  down. Answer before spending eval runs.
- **What fraction of real listings miss the catalogue?** Decides how much the
  decoder carries — on a hit the product name supplies the season, on a miss the
  decoder is the only source.
- **What will production photos actually look like?** Phone camera, or the
  smaller format? The eval set holds both (01-04 at 4032x3024, 05-15 at
  1200x1600), so today at most 11 of 15 cases resemble production and possibly
  only 4. The answer sets the target for the preprocessing experiment in Next
  and decides which half of the set is the one that matters.
- Is 97.0% on `report_art_number.py` a floor that must not regress?
- What's the gate for shipping a prompt change — which metric, what margin, how
  many repeats before a difference is believed?
- Could `DETAILS_MODEL` run on something cheaper? `labels/transcribe.py:15-17`
  says it could — "ordinary OCR on large clear text" — never measured. One
  `--model` run once a baseline exists, with a standing per-listing saving
  attached. Note that Haiku carries a dated model ID where Sonnet 5 doesn't, so
  whatever records the model must handle both shapes.
- Is the Flask app localhost-only or reachable? Decides whether the missing
  rate limit and auth on `POST /` matter.

## Current baseline

None recorded yet. Once one exists: path, date, what the set covers, headline
numbers.

## Dropped

- **"Pin the model to a dated snapshot."** Doesn't apply: `claude-sonnet-5` is
  the complete model ID for this family and appending a date would fail. The
  underlying risk — a model change being indistinguishable from a prompt change
  in a run diff — is **not** fully solved by the `response.model` capture folded
  into the usage task above; if that returns the same `claude-sonnet-5` string,
  it detects nothing. Treat it as partially mitigated until that check is done.
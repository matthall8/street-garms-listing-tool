# ADR-0001: The model transcribes evidence; code interprets it

- **Status:** Accepted. *Pending decisions* and the `<N>`/`<rate>` placeholders
  under *Success criteria* stay Proposed until run 0.
- **Date:** 2026-10-09

## Context

The initial part of the pipeline reads product labels from photos to identify
product information automatically from the ART number. The main risk is a
confident wrong listing: a read that is incorrect but passes every check.

Factors that make this risk more likely:

- Label layouts vary by brand and era. Extra codes (colour, lot, variant) may sit on
  the same line as the ART number, separated by a slash or a space, or on the
  line below.
- ART numbers are not purely numeric. Many contain letters (`6915G0424`,
  `03CMOW026A`, `K1S154100067`), so "the long number on the label" is not
  enough to pick one out.
- Labels carry other code-like strings. The most visible are Certilogo numbers,
  which are sometimes more prominent than the ART number.
- Labels may also contain other information such as the manufacturer's
  address and importer information, including postcodes and phone numbers. On
  some labels the importer line sits directly below the ART line.
- Wear and washing by previous owners can leave labels faded.
- Photos are taken by staff, so some may be out of focus or hard to read.

Language models read this text well but carry two specific risks:

- If the model decides what the text means, mistakes at field boundaries look
  like valid output: an adjacent code joined onto the ART number, or a
  separator that was never printed. If the model knows the format, its errors
  come out format-shaped, and format validation cannot catch them.
- A model's self-reported confidence is not reliable evidence of correctness.
  It may report text as clear when the read is wrong.

## Evidence

From the 2026-10-08 baseline (tag `eval-baseline-2026-10-08`, manifest md5
`02cfa7cb2065ae27e6944b62731651bc`): 28 positive photos of 10 garments plus
5 negatives, each read 3 times. Several photos show the same garment, so garments and label sides are
the real units, not photos.

- Exact ART match on 46% of positive reads; 25% returned no code.
- 28.6% of positive reads were wrong, declared `clear` and had no ambiguous
  characters flagged (the harness's `overconfident` rate). Every wrong read
  that returned a code was `clear`.
- 21% of positive reads would have published wrong with no flag. This comes
  from replaying the decoder, catalogue and gate over the saved reads.
- The largest single failure was extra text joined onto the ART number: a C.P.
  colour code from the same line, a Stone Island variant code from the next
  line, and once a slash that is not printed on the label. The joined reads
  still decoded cleanly.
- Format checks per family would have flagged 15 of the 18 wrong-and-unflagged
  reads. The other 3 were invented codes from one upside-down photo.

## Scope

This ADR covers everything the model is asked to extract from a label photo,
and how code treats each output. The pipeline reads one photo per listing.

## Terms

"ART number" means different things on the label, in the catalogue and in the
old eval column, so each stage gets its own name.

| Term | Meaning |
|---|---|
| ART number | The domain term for the code to look for on the label. Used in the prompt and in prose to say what to find. Technical text never uses it for a specific stage; use `art_line` or `style_code`. |
| `art_line` (the ART line) | The printed line containing the ART number, copied by the model exactly as printed: caption, separators, same-line extras and `?` marks included. Never cleaned; once cleaned, it is a `style_code`. |
| `style_code` | What code derives from the `art_line`: the full code with caption and suffix removed, season prefix included. The same design in another season has a different `style_code`. Assumed to cover every colourway of one design in one season, pending inspection of the catalogue's bare/compound pairs. Applies to `expected_style` too. |
| `art_suffix` | A code on the same line after the `style_code` that matches a known suffix shape, such as a colour code. May be used to choose between catalogue rows. |
| `art_lot` | A lot or batch code on the same line that matches a known lot shape. Recorded; never used for catalogue lookup and never flags. |
| `art_trailing` | Anything left on the line that matches no known shape. It flags for review. |
| catalogue key | The value in the catalogue's `ART` column: a `style_code`, or a `style_code` plus suffix. Some compound keys use a separator (`/`); others have the suffix typed on with none, and the index cannot split those. Only the catalogue index build deals with the difference. |

## Decision

### The model

It locates and copies; it does not interpret.

- It transcribes only. It does not identify, authenticate, infer or correct.
- Every transcribed field is copied exactly as printed. Each unreadable
  character becomes `?`; the model never guesses one.
- It never takes text from another field's line, and never adds a separator
  (slash, space, hyphen) that is not printed.

### What the model returns

Fields are declared in this order, which is the order the model generates them
in. The schema says so in a comment, so nobody reorders them for tidiness.

| Field | Kind | Contents | Empty when |
|---|---|---|---|
| `text_orientation` | observation | Orientation of the ART line's tag, relative to the image as sent to the model: `upright`, `sideways` or `upside_down`. | — |
| `art_line` | transcription | The line containing the ART number, exactly as printed, including a same-line caption (`ART.<code>`) and any other text on that line. A caption on its own line above is not part of it. Kept when `partial`, with `?` marks. | null if `not_visible` or `illegible` |
| `art_legible` | observation | Legibility of `art_line` only: `clear` (fully readable), `partial` (some characters unreadable), `illegible` (an ART number is present but its line cannot be read), `not_visible` (no ART number in this photo). | — |
| `ambiguous_characters` | observation | Characters with two plausible readings, with positions counted along `art_line`. | empty list |
| `next_line` | transcription | The line directly below `art_line` on the same tag, exactly as printed. A line that is there but unreadable comes back as `?` marks. | null if no line is visible there |
| `sizes_printed` | transcription | Each size marking anywhere in the photo, exactly as printed, including any caption (`Tg. XL`, a woven `XXL` tab). | empty list |
| `brand_printed` | transcription | The brand name as printed in text, including a wordmark. Not inferred from a symbol alone (such as the compass badge), and not the manufacturer's company name. | null if none |
| `colour_observed` | observation | Colour of the fabric around the label, in plain words, under unknown lighting. It may be lining or facing, not the garment's outer colour. | null if no fabric is visible |

### What the model is never asked for

- Certilogo numbers or QR contents. These are live authentication codes, so
  leaving them out is a deliberate choice. The prompt mentions
  Certilogo only so the model does not mistake one for the ART number.
- Composition and made-in, for now.
- Notes or other free text, which invite interpretation.
- A lot number as a separate field. A lot code on the ART line is copied as
  part of `art_line`, and code splits it off as `art_lot`.

### Code

It does everything with a right answer that can be written down.

- Derives the `style_code` from the `art_line`: strips captions and splits off
  any `art_suffix` or `art_lot` using family rules. Anything unrecognised
  becomes `art_trailing`.
- Gives spaces no meaning: it strips them, and splits by fixed family length or
  at a printed slash, never at a space.
- Validates format, resolves the `style_code` against the catalogue, and gates
  publication.
- Surfaces any correction it makes. A corrected result is flagged for review.
- Checks the model's fields for consistency in plain code after the call, not
  in Pydantic validators, which would trigger hidden retries.

### What code does with each field

| Field | What code does | Gate |
|---|---|---|
| `text_orientation` | nothing | `upside_down` → review. `sideways` does not block until the orientation run shows sideways reads fail. |
| `art_line` | strips the caption; splits into `style_code`, `art_suffix`, `art_lot`, `art_trailing` | any `?`, any `art_trailing`, format and length checks, catalogue `corrected` or `ambiguous` → review. `art_lot` never flags. |
| `art_legible` | — | anything but `clear` → review |
| `ambiguous_characters` | checks each position is inside `art_line` and its reading matches the character there; for diagnostics only | any entry → review |
| `next_line` | classifies the line by shape; records a supplementary code if one matches | never blocks |
| `sizes_printed` | parses system and value | an uncertain size blocks only if size is mandatory for a listing; otherwise it is dropped (pending decision) |
| `brand_printed` | maps it and the decoded brand line to a brand (Stone Island or C.P. Company) | mismatch → review; null → no check |
| `colour_observed` | stored, labelled as an observation | never blocks |
| decoder | the existing `art_number.py` flags (`truncated`, `unrecognised`, `no-season-in-code`, …) and an unknown season | any decoder flag, or no season → review, as today |
| consistency | e.g. `not_visible` with an `art_line`, `clear` with a `?` in it | any inconsistency → review |

### Trust rules

- Legibility is trusted one way only. `partial`, `illegible` and `not_visible`
  are signals; `clear` is not evidence of correctness. The same applies to
  `ambiguous_characters`: any entry blocks automatic publication, and an empty
  list is not evidence of correctness.
- Any `?` in the `art_line`, or `partial` legibility, blocks automatic
  publication, wherever the `?` falls. This is deliberately conservative.
  Revisit it if evaluation shows a `?` outside the `style_code` sending
  otherwise correct reads to review; code could then decide by where the `?`
  falls.
- The prompt keeps its layout guidance, the format examples that help the
  model find the ART number, and the list of strings not to confuse it with.
  It contains no catalogue knowledge, and no example demonstrates splitting or
  joining codes.
- A printed brand that disagrees with the decoded brand is evidence of a
  misread, and blocks automatic publication.
- A colour observed visually is never published as fact. Colour is published
  only from a printed code resolved through a confirmed colour table, or when
  set by a person at listing.

## Alternatives considered

| Approach | Who decides meaning | How it fails | Outcome |
|---|---|---|---|
| End-to-end LLM | model | silently | Rejected: no independent check on any field |
| LLM fields + validation (current system) | model; code checks | silently, when the error fits the format | Rejected: format-shaped errors pass validation; 21% of positive reads would have published wrong with no flag |
| Anchored transcription | code; model picks the line | to review, or a wrong read that forms another valid code | **Chosen** |
| Whole-tag transcription | code, including locating the ART number | regex picks the wrong code | Rejected (untested here): expected noise from phone numbers, postcodes and lot codes; more patterns to maintain |
| OCR + code | code | misses on fabric labels | Rejected as primary reader (untested here): expected to be weaker on creased, curved and low-contrast labels |
| Anchored + OCR cross-check | code | to review when the readers disagree | Deferred: add only if evaluation shows the chosen approach is not enough |

## Consequences

### Gains

- Boundary errors are sent to review or blocked by the gate, rather than
  published silently.
- Interpretation rules can be tested and fixed in code without paid model runs.
- The prompt stays simple. *Hypothesis:* it depends less on the model version
  than a prompt carrying format and catalogue knowledge.

### Costs

- Split rules must be maintained per family. New layouts go to review until a
  rule exists; this is intended behaviour, not a failure.
- One model judgement remains: choosing the line. A wrong line is caught only
  when its text fails the format check. It would also be caught when it misses
  the catalogue with an unusual length (as a phone number would), if that
  pending rule is accepted (ADR-0004); today misses do not flag. A wrong line
  whose text looks like a valid code is not caught. This is the remaining weakness.
- A misread character can turn a correct code into another real catalogue key,
  which then matches exactly. This is partly covered: the pending
  confusion-pair rule catches 0/O, 1/I, 5/S, 8/B and 6/G misreads, and the
  brand cross-check catches misreads in the Stone Island brand characters where
  brand text is printed (back tags carry none). Any other single-character
  misread cannot be gated without flagging 37% of catalogue keys (those one
  substitution from another key) on every correct read, so it is an accepted risk, tracked by
  the wrong-and-unflagged metric.
- Review volume is higher than in a design that trusts the model's output.

### Not addressed by this decision

- Invented codes from rotated or upside-down photos. Changing who decides
  meaning does not stop the model inventing a valid-looking code from text it
  cannot read. `text_orientation` is an experiment towards this, not a fix.

### Implications

- Ground truth is the `style_code` for each photo (`expected_style`), labelled
  by hand.
- The scorer reports three measures:
  - **wrong-and-unflagged**, the main metric: reads that would publish wrong
    with no flag;
  - **style-exact**: exact match on `style_code` through the full pipeline;
  - **line-exact**: exact match on `art_line` against `expected_line`. This
    isolates the model, so a misread can be told apart from a split bug.

  Expected values are labelled by hand, never produced by the split function,
  so split bugs cannot hide in the score.
- The eval manifest records `expected_style` and the `art_line` as printed
  (`expected_line`), with ground-truth rules in `evals/README.md`.
  `expected_art_number` stays as a labelled legacy column, not authoritative,
  so older reports remain comparable.
- The prompt uses "ART number" only to say what to find, and states the
  one-line rule with it, e.g. "Find the ART number. Copy the whole printed line
  it's on into `art_line`, and nothing from any other line."
- Field names follow the Terms. `art_number_raw` becomes `art_line`. The model
  sees this name in its output schema, so the rename is part of the prompt
  contract: it lands in the same commit as the one-line rule and is measured in
  the same eval run. Saved results use the old name, so the eval harness and
  replay must read both.
- `Resolution.matched_art` becomes `matched_key`. The model never sees it, so
  this is a refactor on its own, with no change in behaviour.
- `art_number.py` and `ArtNumberReading` keep their names, since they use the
  domain sense.
- CLAUDE.md's *Transcription only transcribes* invariant cites this ADR.

### Rollout

Each run changes one part of the contract. Two runs bundle deliberately: run 1,
because its edits only make sense together as one contract, and run 4, to
limit paid runs, with the order for removing its fields fixed in advance. Each
run's ground-truth columns are added, checked by eye and recorded in the
manifest md5 table before it runs.

| Run | Change | Manifest columns needed |
|---|---|---|
| 0 | Code only, no API calls: the split, review reasons, and a replay over the baseline's saved reads. The catalogue stays as it is (index: ADR-0003) | `expected_line`, `expected_style` |
| 1 | The contract change: the one-line rule; `art_number_raw` renamed to `art_line`; `ambiguous_characters` positions counted along `art_line`; the `/181` example dropped; the lot-code rule reworded to match the line rule | `expected_line`, `expected_style` |
| 2 | `text_orientation`, in first position. If the ART read gets worse, retry it in last position. | `orientation` |
| 3 | `next_line` | `expected_next_line` |
| 4 | Size, brand and colour together, with the ART metrics as guardrail | `expected_sizes`, `expected_brand`; colour scored by eye |

If run 4 makes the ART read worse, remove colour first, then brand, then size.
This order is fixed before any result exists.

## Pending decisions (status: Proposed)

The first three are catalogue rules, drafted in ADR-0004 from the run 0 replay;
ADR-0004 changes CLAUDE.md's "misses do NOT flag" invariant. ADR-0003 covers the
catalogue index they read from. The last two are settled by amending this ADR.

- Flagging an atypical length combined with a catalogue miss.
- Flagging a catalogue match when another key is one confusion-pair
  substitution away (0/O, 1/I, 5/S, 8/B, 6/G). A rule covering any single edit
  (substitution, insertion or deletion) would flag 38% of catalogue keys on every correct read, so it is limited to
  confusion pairs (0.4%).
- Flagging styles in the catalogue's bare/compound pairs until they have been
  inspected.
- Whether size is mandatory for a listing. This decides whether an uncertain
  size blocks publication or is dropped.
- Whether `sideways` blocks publication, decided from run 2.

## Success criteria and when to revisit

Results are counted per garment-side, not per photo, so repeated photos of one
garment don't skew them.

**For each run to be accepted**, compared with the current baseline:

- no garment-side is newly wrong and unflagged (hard rule);
- the guardrails in TODO.md's *Decision rule for prompt changes* hold.

**For launch**, on a held-out set of at least `<N>` garments that played no
part in tuning:

- no garment-side is wrong and unflagged;
- correct reads sent to review stay at or below `<rate>`, a level one person
  can clear.

`<N>` and `<rate>` are set when the run 0 baseline is recorded: `<rate>` from
how many listings can be reviewed in a day.

**Revisit** if wrong-line selection makes up most of the remaining errors
(consider the OCR cross-check), or if the review rate becomes unmanageable
(write rules for the layouts causing it).
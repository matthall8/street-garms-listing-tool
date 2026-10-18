# Glossary

The project's terms; other docs link here. Renamed terms are listed at the
end. Examples use placeholders only: this file is public. *(not in code
yet)* marks a term the code doesn't have yet, with its current name if any.

## The ART line

The `art_` prefix marks the ART line and anything read from it or about it,
wherever it is held: on a label, in the manifest or in a catalogue key.

| Term | Meaning |
|---|---|
| ART number | The code to find on the label. Used in the prompt and prose; technical text names the stage (`art_line`, `art_base`, catalogue key). |
| `art_line` | The printed line containing the ART number, copied exactly by the model, `?` marks included. Never rewritten. *(not in code yet: `art_number_raw`)* |
| read | One model call's output for one photo. |
| parser | `parse()` in `labels/art_number.py`. Splits an `art_line` into the parts below. |
| `art_caption` | Text introducing the code on the `art_line`, such as `ART.`. Recorded as evidence the right line was picked; never used for lookup. A caption on the line above isn't one. *(not in code yet)* |
| format family | One of the ART number formats in `labels/art_number.py`, reported as the parser's `format`. Each has one base shape. |
| known shape | A pattern for a caption, base, suffix or lot: lengths and character classes, never copied values. Frozen data: extended by adding entries, never generalised. |
| `art_base` | The part matching a base shape, season prefix included. Intended to identify one design in one season (see [Assumption](#assumption)). *(not in code yet)* |
| `art_suffix` | A code after the `art_base` matching a suffix shape, such as a colour code. Whether it chooses between catalogue rows is undecided (ADR-0003). *(not in code yet)* |
| `art_lot` | A code matching a lot shape. Recorded; never used for lookup. *(not in code yet)* |
| `art_unmatched` | Anything matching no known shape. Flags. *(not in code yet)* |

### Parsing rules

- **Base end:** C.P. Company bases have a fixed length. Stone Island numeric
  bases end at their era's length (the length for their range of seasons)
  once that table is settled. Until then they end only at a printed slash,
  so a base followed by a numeric code with no slash runs on, fails its
  shape and flags.
- **Separators:** `/` and `-` between parts are discarded; no shape contains
  either. Spaces mean nothing; parts are found by shape.
- **`?`:** stands for exactly one character. A code that a `?` makes fit two
  shapes becomes `art_unmatched`; the rest of the line parses as usual.
- **Flags:** parsing flags only on `art_unmatched` and on any `?`. All other
  flags are in the gate (ADR-0001).
- **Not yet decided (step 4):** which code is the `art_base` when several
  could be, and which shape wins when a code fits two without a `?`.

`ART NO. <base>/<suffix> <lot> <unmatched>` gives `art_caption` `ART NO.`,
`art_base` `<base>`, `art_suffix` `<suffix>`, `art_lot` `<lot>` and
`art_unmatched` `<unmatched>`.

### Assumption

One `art_base` covers every colourway of a design in a season. Unconfirmed
until the catalogue's bare/compound pairs are inspected; fused keys filed
under a different product name may be exceptions.

## The catalogue

| Term | Meaning |
|---|---|
| catalogue key | A value in the catalogue's `ART` column: bare or compound. |
| bare key | An `art_base` alone. |
| compound key | An `art_base` plus a suffix, *separated* (`<base>/<suffix>`) or *fused* (`<base><suffix>`). Fused keys aren't separated, because a fused suffix may not be an `art_suffix` (ADR-0003). |
| confusion pair | Characters a misread swaps, such as `0`/`O`; listed in `CONFUSIONS` in `labels/catalogue.py`. |
| `resolved_key` | The key a lookup resolved to. *(not in code yet: `matched_art`)* |
| catalogue outcome | `Resolution.status`: `exact`, `corrected` (one confusion-pair swap from one key), `ambiguous` (from several), `no_key` *(not in code yet: `miss`)* or `no_art_number`. Only `exact` is confident; `corrected` and `ambiguous` flag, `no_key` deliberately doesn't. Looked up: the whole `art_line` until step 4, then the `art_base`. From then, a design catalogued only under compound keys is `no_key`: a known gap, for ADR-0003. |

## Review

| Term | Meaning |
|---|---|
| `art_legible` | The model's rating of the `art_line`: `clear`, `partial` (some characters unreadable), `illegible` (an ART number is there but unreadable) or `not_visible` (no ART number in the photo). Anything but `clear` is a signal; `clear` proves nothing. |
| `needs_review` | The gate: true means a person checks the listing before it publishes. |
| `review_reasons` | Why `needs_review` is set. *(not in code yet)* |

## Evaluation

| Term | Meaning |
|---|---|
| positive / negative | A photo with or without an ART number. Negatives expect `NONE`; blank means not labelled yet. |
| `garment` | Manifest column: an opaque id per garment. The dev/held-out split is by garment. |
| `side` | Manifest column: the label face shown. `front` carries brand text; `back` is the "Art." tag. |
| garment-side | One garment's one side: the unit results are counted in. |
| `expected_<term>` | A hand-labelled manifest column: `expected_art_line`, `expected_art_base`. Never produced by the parser. *(not in the manifest yet)* |
| `expected_art_number` | Legacy column, kept so older reports stay comparable. Today the manifest's only expected column, and what the harness scores. |
| wrong-and-unflagged | The primary metric: would publish an `art_base` other than `expected_art_base` (any code, on a negative) with `needs_review` false. A garment-side counts if any of its reads does (proposed). |
| base-exact | `art_base` equals `expected_art_base`. |
| line-exact | `art_line` equals `expected_art_line`; isolates the model. |
| missed | Positives: no characters returned. |
| overconfident | Positives: `clear`, not equal to `expected_art_number`, and no `ambiguous_characters`. |
| fabricated | Negatives: a code returned. |

## Renamed

| Old | New | Code renamed |
|---|---|---|
| `style_code` | `art_base` | never in code |
| `art_trailing` | `art_unmatched` | never in code |
| decoder | parser | only in comments and one test name; not scheduled |
| `matched_art`, `matched_key` | `resolved_key` | chain step 3 |
| `miss` | `no_key` | chain step 3 |
| `expected_line`, `expected_style` | `expected_art_line`, `expected_art_base` | hook, on `manifest-id` |
| style-exact | base-exact | never in code |
| `art_number_raw` | `art_line` | run 1 |

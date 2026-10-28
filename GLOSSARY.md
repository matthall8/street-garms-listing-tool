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
| `art_line` | The printed line containing the ART number, copied exactly by the model, `?` marks included. Never rewritten. *(not in code yet: run 1 replaces `art_number_raw`, today's read of the ART number alone)* |
| read | One model call's output for one photo. |
| parser | `parse()` in `labels/art_number.py`. Decodes an ART number's format, year, season, brand and garment. `split_art_line()`, beside it, splits a line into the parts below; `from_reading()` splits every read, then decodes the `art_base`. |
| `art_caption` | Text introducing the code on the `art_line`, such as `ART.`. Recorded as evidence the right line was picked; never used for lookup. A caption on the line above isn't one. |
| format family | One of the ART number formats in `labels/art_number.py`, reported in the parser's `format` (which also has `si_namespace` for non-seasonal codes). Each has its own base shapes. |
| known shape | A pattern for a caption, base, suffix or lot: lengths and character classes, never copied values. Base and suffix shapes come from the catalogue; caption and lot shapes from labels. Frozen data: extended by adding entries, never generalised. |
| `art_base` | The part matching a base shape, season prefix included. Intended to identify one design in one season (see [Assumption](#assumption)). |
| `art_suffix` | A code after the `art_base` matching a suffix shape, such as a colour code. Whether it chooses between catalogue rows is undecided (ADR-0003). |
| `art_lot` | A code matching a lot shape. Recorded; never used for lookup. |
| `art_unmatched` | Anything matching no known shape. Flags. |

### Parsing rules

The split's rules and flags are in [ADR-0005](adr/0005-art-line-split.md).

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
| catalogue outcome | `Resolution.status`: `exact`, `corrected` (one confusion-pair swap from one key), `ambiguous` (from several), `no_key` *(not in code yet: `miss`)* or `no_art_number`. Only `exact` is confident; `corrected` and `ambiguous` flag, `no_key` deliberately doesn't. Looked up: the `art_base`, or a candidate when the split fails (ADR-0005). A design catalogued only under compound keys is `no_key`: a known gap, for ADR-0003. |

## Review

| Term | Meaning |
|---|---|
| `art_legible` | The model's rating of the read (of the `art_line` from run 1): `clear`, `partial` (some characters unreadable), `illegible` (an ART number is there but unreadable) or `not_visible` (no ART number in the photo). Anything but `clear` is a signal; `clear` proves nothing. |
| `needs_review` | The gate: true means a person checks the listing before it publishes. |
| *looks right* / *check this* | How a listing shows: `needs_review` false / true. |
| `review_reasons` | Why `needs_review` is set. *(not in code yet)* |

## Evaluation

| Term | Meaning |
|---|---|
| positive / negative | A photo with or without an ART number. Negatives expect `NONE`; blank means not labelled yet; `UNKNOWN` (in `expected_art_line` and `expected_art_base` only) means labelled, but no value is safe, with the reason in `note`. A blank `expected_art_number` beside two `UNKNOWN` cells is finished too (`evals/README.md`, *Negative cases*). |
| `garment` | Manifest column: an opaque id per garment. The dev/held-out split is by garment. |
| `side` | Manifest column: the label face shown. `front` carries brand text; `back` is the "Art." tag. |
| garment-side | One garment's one side: the unit results are counted in. |
| `expected_<term>` | A hand-labelled manifest column: `expected_art_line`, `expected_art_base`. Never produced by the parser. |
| `expected_art_number` | Legacy column, kept so older reports stay comparable. Until the phase 1 scorer (TODO.md, *Code*), the only expected column the harness scores. |
| wrong-and-unflagged | ADR-0001's primary metric, not in the phase 1 gate (ADR-0002): would publish an `art_base` other than `expected_art_base` (any code, on a negative) with `needs_review` false. A garment-side counts if any of its reads does. |
| silent error | A wrong-and-unflagged garment-side: wrong, but shown as *looks right*. |
| readable / illegible / absent | The by-eye label of a photo before any run: every character of the ART number can be read; some can't; there is none (a negative). Separate from the model's `art_legible`. Every test photo is readable (ADR-0002). *(not in the manifest yet)* |
| in the catalogue | The product's `expected_art_base` is a catalogue key. Products catalogued only under a compound key aren't, until ADR-0003's index. |
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
| decoder | parser | still in comments, a test name, `Extraction.decoded` and the web page's "Decoder flags" heading; not scheduled |
| `matched_art`, `matched_key` | `resolved_key` | the rename (TODO.md, *Backlog*) |
| `miss` | `no_key` | the rename (TODO.md, *Backlog*) |
| `expected_line`, `expected_style` | `expected_art_line`, `expected_art_base` | hook, PR #36 |
| style-exact | base-exact | never in code |
| `art_number_raw` | `art_line` | run 1 |

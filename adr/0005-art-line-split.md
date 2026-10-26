# ADR-0005: How the ART line is split

- **Status:** Accepted, provisional until run 1.
- **Date:** 2026-10-26
- **Supersedes:** in part, ADR-0001's rule that code gives spaces no meaning
  and never splits at a space (*Decision*, *Code*).
- **Terms:** see `GLOSSARY.md`.

## Context

ADR-0001 has code split the `art_line` into `art_caption`, `art_base`,
`art_suffix`, `art_lot` and `art_unmatched` by family rules. It gave spaces
no meaning: code strips them and splits only by fixed length or at a printed
slash. But every C.P. Company label prints a space between the base and its
fabric code, and stripping it runs the two together, so the base misses the
catalogue. This ADR sets the split's rules.

## Evidence

None of the catalogue's 2,486 keys and none of the manifest's
`expected_art_base` values contain a space.

## Decision

### Characters

- ASCII only. Shapes use ASCII digits and letters from an explicit allowed
  set; any other character (a full-width digit or slash, a zero-width space,
  a look-alike letter from another alphabet) flags. The read is never
  normalised.
- Leading and trailing whitespace is stripped. A tab counts as a space.
- Matching is in upper case, and `art_base` is upper case. `art_line` and
  `art_caption` stay as read.
- Nothing is stripped from inside the line: leading zeros stay, and
  punctuation inside a base fails its shape.

### Caption

An optional `ART.` or `ART NO.` at the start of the line, printed onto the
code or followed by a space. It becomes `art_caption` as printed, and is
never looked up.

### Base

- **Anchored at the start**, after the caption if there is one. Code never
  searches inside the line for a base.
- **Ended by a separator** or the line end, for every family. The separator
  is `/` or a space, with or without spaces around the `/`. A hyphen is never
  a separator.
- **Checked by the family's length.** If the separator and the length
  disagree, it flags.

| Family | Base length |
|---|---|
| SI numeric, `si_namespace` | 8 or 9 |
| SI alphanumeric | 12 |
| CP transitional | 12 with the C printed, 11 without |
| CP modern | 10 |

The SI numeric lengths are a fixed set, not a length per era. Adding a
length needs catalogue evidence that it's a real base.

Text before the base makes the whole line `art_unmatched`, with no
`art_base`. A gap printed inside a base ends it early, so the base fails its
length or leaves an unknown tail.

### Tails

Tails follow the base after a separator and are read in order: an
`art_suffix`, then an `art_lot`.

| After | `art_suffix` | `art_lot` |
|---|---|---|
| SI numeric, `si_namespace` | a colour code: 2 to 4 digits | a LOT code, short or long shape |
| CP modern | a fabric code: 6 digits, then a letter | — |
| SI alphanumeric, CP transitional | — | — |

LOT shapes: short `LOTA-DD-DDDDD`, long `A-DD-LOTA-DDDD-DDDDD` (`A` a letter,
`D` a digit, `LOT` as printed).

There are no single-letter suffixes, after a `/` or a `-`. Any other tail is
`art_unmatched` and the base is kept: an unknown shape, a code from another
line, a `/` with nothing after it, any tail after a family with none.

### `?`

- A `?` stands for exactly one character and stays where it falls.
- A tail that a `?` lets fit exactly one shape takes that shape. If it fits
  two or none, it is `art_unmatched`.
- If a `?` lets the line fit more than one family, the whole line is
  `art_unmatched`. Code never picks one.

### When the split fails

When no family fits, or the base fails its length or shape, no `art_base`
is stored. The catalogue looks up a candidate (the line without its caption,
up to the first separator), and the result always flags. Code never repairs
the read first (for example `0`→`O`). A swap that the catalogue makes is a
`corrected` resolution, which is recorded and flags (CLAUDE.md, *Corrections
always surface*).

### Flag table

Each problem has one of three values: **always** flags; flags **unless
confident** (`Resolution.confident`); **never** flags (recorded only).
Changing a value is a product decision.

| Problem | Flags |
|---|---|
| any `art_unmatched` | always |
| any `?` | always |
| a base of the wrong length or shape, including where the separator and the length disagree | always |
| a failed split (candidate lookup) | always |
| a character outside the allowed set | always |
| an unknown season key | always |
| no season in the code (`season_not_in_code`) | ADR-0004 |
| `art_lot` | never |
| an `ambiguous_characters` position outside `art_line`, or a reading that doesn't match the character there | never (any entry already flags: ADR-0001) |

## Accepted costs and triggers

- **Fused keys miss.** About 7% of catalogue keys have a suffix fused on (SI
  numeric 10–11 characters, SI alphanumeric 16–17, CP modern 17). An
  `art_base` doesn't match them unless a bare key exists too. Under ADR-0002
  those products count as not in the catalogue. ADR-0003's index closes the
  gap.
- **Hyphen keys can't match.** The 4 catalogue keys with `-` plus a letter
  can't match a label; a label printed that way flags.
- **SI numeric 8↔9.** An inserted or lost character that turns 8 into 9, or
  9 into 8, leaves a valid length that this split can't catch. A table of
  lengths per era (frozen data, decided by a person) is built only if any
  replay or eval shows an SI 8↔9 disagreement: a read `art_base` one
  character longer or shorter than `expected_art_base`, both valid lengths.
  Don't wait for a silent error: a 30-garment test set is unlikely to
  produce one.
- **Spaces.** The saved reads are the code alone, so they say little about
  how faithfully the model copies spaces across a whole line. Revisit the
  separator rule with run 1's reads.

## Left to ADR-0004

- Catalogue misses, including an SI 8↔9 change that misses.
- The confusion-pair margin: an exact hit one swap from another key.
- Bare/compound pairs, fused pairs included.
- Whether no season in the code flags unless the hit is confident.

## Alternatives considered

- **Spaces mean nothing; parts found by shape** (ADR-0001): rejected. It
  runs a C.P. base into its fabric code, and no key contains a space.
- **A length table per era for SI numeric:** not built; about 2% of
  catalogue keys don't fit their era. See the trigger above.
- **Searching inside the line for a base:** rejected. A base-shaped run inside
  a barcode or phone number would pass. ADR-0001 rejected locating the code
  by pattern.
- **Single-letter suffixes:** rejected. On 2 catalogue keys and no label,
  and an invented separator before the last letter of a 9-character base
  would then pass as a suffix.
- **Repairing or normalising the read before the split:** rejected.
  Correction belongs in the catalogue, where it's recorded and flags.

## Consequences

- ADR-0001's spaces rule is superseded in part; the rest of *Code* stands.
- The rules live here; `GLOSSARY.md` links to them.
- The measured effect comes from the checkpoint replay (ADR-0002) on the
  branch that wires the split into the gate. The implementation order is in
  `TODO.md`.

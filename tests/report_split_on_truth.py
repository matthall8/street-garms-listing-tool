"""Split on truth: run split_art_line() on each hand-labelled expected_art_line
in the dev manifest and compare its art_base to expected_art_base. No model,
no API call, no catalogue. A mismatch is a split bug, a labelling error, or
ADR-0005's rule not fitting a real label.

Prints shapes, never values: D a digit, A an upper-case letter, a a lower-case
one, anything else as printed, non-ASCII escaped. Retired by the scorer's
fake-read mode (TODO.md, Code).

    python tests/report_split_on_truth.py
"""

import csv
import hashlib
import string
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval_transcription import MANIFEST, NO_ART_NUMBER, UNKNOWN
from labels.art_number import split_art_line

COLUMNS = ("expected_art_line", "expected_art_base")
GROUPS = ("base matches", "base differs", "no base", "no code", "excluded")
SHAPES = str.maketrans(
    string.digits + string.ascii_uppercase + string.ascii_lowercase,
    "D" * 10 + "A" * 26 + "a" * 26,
)


def shape(s: str) -> str:
    return ascii(s.translate(SHAPES))[1:-1]  # escapes invisible characters, e.g. \xa0


def main() -> int:
    if not MANIFEST.is_file():
        print(f"manifest not found at {MANIFEST} — skipping.")
        return 0

    with open(MANIFEST, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    groups: Counter[str] = Counter()
    problems: Counter[tuple[str, str]] = Counter()
    detail = []
    for r in rows:
        line, base = r["expected_art_line"], r["expected_art_base"]
        # exact cell values: a stray space in the base or a sentinel shows as a
        # mismatch; split_art_line() strips the line's ends, so that is counted
        found = tuple(f"{c} {r[c] or 'blank'}" for c in COLUMNS if r[c] in ("", UNKNOWN))
        if found:
            group = "excluded"
        elif line == base == NO_ART_NUMBER:
            group = "no code"
        else:
            split = split_art_line(line)
            found = split.problems
            if line != line.strip():
                found += ("line has edge whitespace",)
            if split.art_base is None:
                group = "no base"
            elif split.art_base == base:
                group = "base matches"
            else:
                group = "base differs"
            if group != "base matches" or found:
                detail.append(f"{r['id']}  line {shape(line)}  expected {shape(base)}  "
                              f"split {shape(split.art_base or '')}  problems {', '.join(found) or '-'}")
        groups[group] += 1
        problems.update((group, p) for p in found)

    assert sum(groups.values()) == len(rows), "a row was not counted"

    print(f"manifest md5={hashlib.md5(MANIFEST.read_bytes()).hexdigest()}  rows={len(rows)}")
    for g in GROUPS:
        print(f"{g}: {groups[g]}")
        for (pg, p), n in sorted(problems.items()):
            if pg == g:
                print(f"    {p}: {n}")
    for d in detail:
        print("  ", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

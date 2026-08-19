"""Score the art number decoder against the catalogue.

The catalogue's "Product Name" column carries a human-confirmed season, e.g.
"A/W 02 Raso Gommato". That is the ground truth. No network, no API key.

    python tests/test_art_number.py
"""

import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels.art_number import parse  # noqa: E402

CATALOGUE = Path(__file__).parent.parent / "notebooks/art-number/art-number.csv"
SEASON_RE = re.compile(r"\b([AS])/([WS])\s*'?(\d{2})\b")


def claimed(product_name: str):
    """Pull the season the catalogue claims, or None if it doesn't say."""
    m = SEASON_RE.search(product_name or "")
    if not m:
        return None
    yy = int(m.group(3))
    return (1900 + yy if yy > 50 else 2000 + yy, "SS" if m.group(1) == "S" else "AW")


def main() -> int:
    if not CATALOGUE.is_file():
        print(f"catalogue not found at {CATALOGUE} — skipping.")
        print("The Street Garms catalogue is private and not part of this repo.")
        return 0

    agree = disagree = no_claim = unparsed = 0
    formats, mismatches = Counter(), []

    with open(CATALOGUE, encoding="utf-8-sig") as f:
        rows = csv.reader(f)
        next(rows)
        for r in rows:
            r = [c.replace("\xa0", " ").strip() for c in r]
            if len(r) < 4 or not r[0]:
                continue
            art, name = r[0], r[3]
            p = parse(art)
            formats[p.format or "UNRECOGNISED"] += 1
            want = claimed(name)

            if p.format is None:
                unparsed += 1
            elif want is None:
                no_claim += 1
            elif (p.year, p.season) == want:
                agree += 1
            else:
                disagree += 1
                mismatches.append(f"{art:16} got {p.season} {p.year}  want {want[1]} {want[0]}  {name}")

    checkable = agree + disagree
    print(f"rows={agree + disagree + no_claim + unparsed}  agree={agree}  "
          f"disagree={disagree}  no-season-in-name={no_claim}  unparsed={unparsed}")
    if checkable:
        print(f"season/year accuracy on checkable rows: {agree}/{checkable} = {agree / checkable:.1%}")
    print("formats:", dict(formats))

    for line in mismatches[:25]:
        print("  MISMATCH", line)
    if len(mismatches) > 25:
        print(f"  ... and {len(mismatches) - 25} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Check catalogue lookup against every row it contains.

No network, no API key. The catalogue is its own test corpus: every row must
look up to itself, so the suite grows as the catalogue does.

    python tests/test_catalogue.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels.catalogue import (  # noqa: E402
    ART_CSV_PATH,
    art_lookup,
    load_catalogue,
    normalise,
    product_name,
)

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def main() -> int:
    catalogue = load_catalogue()

    if not catalogue:
        print(f"no catalogue at {ART_CSV_PATH} — skipping.")
        print("The Street Garms catalogue is private and not part of this repo.")
        return 0

    print(f"catalogue: {len(catalogue)} rows\n")

    # 1. Every row resolves to itself. The core guarantee.
    missed = [k for k, row in catalogue.items() if art_lookup(k) is not row]
    check("every row looks up to itself", not missed,
          f"{len(catalogue) - len(missed)}/{len(catalogue)}")
    for k in missed[:5]:
        print(f"        missed: {k}")

    # 2. Product names come back, and match the row.
    wrong = [
        k for k, row in catalogue.items()
        if product_name(k) != (row.get("Product Name") or None)
    ]
    check("product_name matches the row", not wrong, f"{len(wrong)} mismatched")

    # 3. Leading zeros survive the CSV read. 0126422791 must not become an int.
    zeros = [k for k in catalogue if k.startswith("0")]
    check("leading zeros preserved", bool(zeros) and all(art_lookup(k) for k in zeros),
          f"{len(zeros)} such codes")

    # 4. Normalisation: OCR returns spaces and mixed case, the catalogue does not.
    sample = next(iter(catalogue))
    spaced = " ".join([sample[:4], sample[4:]])
    check("matches despite spacing", art_lookup(spaced) is not None, repr(spaced))
    check("matches despite case", art_lookup(sample.lower()) is not None)
    check("normalise strips and upcases",
          normalise(" 05cmsh022a 004275a ") == "05CMSH022A004275A")

    # 5. Misses are None, not exceptions or empty strings.
    check("unknown code returns None", art_lookup("NOTAREALCODE") is None)
    check("None input returns None", art_lookup(None) is None)
    check("empty string returns None", art_lookup("") is None)

    # 6. Absent catalogue degrades, since data/ is gitignored.
    check("missing file returns empty dict",
          load_catalogue(Path("data/does-not-exist.csv")) == {})

    # 7. The whole row is available, not just the name.
    row = art_lookup(sample)
    check("row carries Brand and Type",
          bool(row) and {"ART", "Brand", "Type", "Product Name"} <= set(row))

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

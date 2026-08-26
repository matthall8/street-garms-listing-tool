"""
Look up an ART number in Street Garms' own catalogue.
"""

from functools import cache
from pathlib import Path
from typing import Optional

import pandas as pd

ART_CSV_PATH = Path(__file__).parent.parent / "data" / "art-number.csv"

def normalise(art_number: Optional[str]) -> str:
    """Strip spacing and case. Leading zeros are kept."""
    return "".join((art_number or "").split()).upper()


@cache
def load_catalogue(path: Path = ART_CSV_PATH) -> dict[str, dict]:
    """Read the catalogue once, keyed on the normalised ART number a fresh clone still runs.
    """
    if not path.is_file():
        return {}

    # dtype=str so 0126422791 keeps its leading zero rather than becoming an int.
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    return {
        key: row
        for row in df.to_dict("records")
        if (key := normalise(row.get("ART")))
    }


def art_lookup(art_number: Optional[str]) -> Optional[dict]:
    """Exact match on the ART number. None if absent or if there is no catalogue.

    Returns the whole row — Brand and Type are wanted for the listing too.
    """
    return load_catalogue().get(normalise(art_number))


def product_name(art_number: Optional[str]) -> Optional[str]:
    """Just the product name, for callers that want only the title."""
    row = art_lookup(art_number)
    return (row or {}).get("Product Name") or None


if __name__ == "__main__":
    catalogue = load_catalogue()
    print(f"{len(catalogue)} rows from {ART_CSV_PATH}")
    for art in list(catalogue)[:3]:
        print(f"  {art:16} {product_name(art)}")

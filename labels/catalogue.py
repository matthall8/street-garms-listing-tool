"""
Look up an ART number in Street Garms' own catalogue.
"""

from functools import cache
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass, field

import pandas as pd

ART_CSV_PATH = Path(__file__).parent.parent / "data" / "art-number.csv"
CONFUSIONS = {
    "0": "O", "O": "0",
    "1": "I", "I": "1",
    "5": "S", "S": "5",
    "8": "B", "B": "8",
    "6": "G", "G": "6",
}


@dataclass
class Resolution:
    status: Literal["exact", "corrected", "ambiguous", "miss", "no_art_number"]
    row: Optional[dict] = None           
    matched_art: Optional[str] = None   
    candidates: list[dict] = field(default_factory=list)   

    @property
    def product_name(self) -> Optional[str]:
        return (self.row or {}).get("Product Name") or None

    @property
    def confident(self) -> bool:
        return self.status == "exact"

@cache
def load_catalogue(path: Path = ART_CSV_PATH) -> dict[str, dict]:
    """
    Read the catalogue once, keyed on the normalised ART number a fresh clone still runs.
    """
    if not path.is_file():
        return {}

    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    return {
        key: row
        for row in df.to_dict("records")
        if (key := normalise(row.get("ART")))
    }

def normalise(art_number: Optional[str]) -> str:
    """Strip spacing and case. Leading zeros are kept."""
    return "".join((art_number or "").split()).upper()

def variants(art_number: str) -> list[str]:
    clean_art_number = normalise(art_number)
    candidates = []
    for i, ch in enumerate(clean_art_number):
        if ch in CONFUSIONS:
            possible_art_number = clean_art_number[:i] + CONFUSIONS[ch] + clean_art_number[i+1:]
            candidates.append(possible_art_number)
    return candidates


def art_lookup(art_number: Optional[str]) -> Optional[dict]:
    """Exact match on the ART number. None if absent or if there is no catalogue.

    Returns the whole row — Brand and Type are wanted for the listing too.
    """
    return load_catalogue().get(normalise(art_number))


def product_name(art_number: Optional[str]) -> Optional[str]:
    """Just the product name, for callers that want only the title."""
    row = art_lookup(art_number)
    return (row or {}).get("Product Name") or None

def resolve(art_raw, art_legible=None) -> Resolution:
    if art_legible in ("not_visible", "illegible") or not art_raw:
        return Resolution(status="no_art_number")

    if row := art_lookup(art_raw):
        return Resolution(status="exact",row=row,matched_art=row['ART'])

    hits = {}
    for v in variants(art_raw):
        row = art_lookup(v)
        if row:
            hits[v] = row

    if len(hits) == 1:
        matched_art = list(hits)[0]
        return Resolution(status="corrected", row=hits[matched_art], matched_art=matched_art)

    if len(hits) > 1:
        # Rows, not codes — a human choosing between near-identical numbers
        # needs the product names to tell them apart.
        return Resolution(status="ambiguous", candidates=list(hits.values()))

    return Resolution(status="miss")

if __name__ == "__main__":
    catalogue = load_catalogue()
    print(f"{len(catalogue)} rows from {ART_CSV_PATH}")
    for art in list(catalogue)[:3]:
        print(f"  {art:16} {product_name(art)}")

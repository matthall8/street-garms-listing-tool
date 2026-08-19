"""
Stone Island / C.P. Company ART number parser.

Derived from Street Garms' own catalogue (~1,500 human-confirmed rows),
not from web sources. Every table below is DATA, not arithmetic: unknown
keys return None rather than extrapolating.

Four format families were found in the catalogue:
  A. SI numeric        58154 0923      -> shared with C.P. pre-2010 (brand 18)
  B. SI alphanumeric   K1S154100067    -> SS2025 onward
  C. CP transitional   14SCPUB04669    -> ~2011-2016
  D. CP modern         14CMOS045A      -> ~2017 onward
"""

from dataclasses import dataclass
from typing import Optional
import re

# ---------------------------------------------------------------------------
# A. Season table for the SI numeric counter.
# Generated once from the linear rule, then FROZEN as data.
# Validated against 40 consecutive seasons in the catalogue (01=AW84 .. 81=AW24)
# with zero violations. Do not replace with a formula: a formula extrapolates
# forever, a table stops.
# ---------------------------------------------------------------------------
SI_SEASON = {
    f"{n:02d}": (1990 + (n - 12) // 2, "SS" if n % 2 == 0 else "AW")
    for n in range(1, 82)
}
# '10' is NOT a season. It appears with brand 15 and brand 18, alongside every
# "Re-Issue" and Nokia item in the catalogue, and the brand/garment characters
# after it decode correctly. Treat it as a non-seasonal namespace: decode the
# structure, return no season, let the DB or a human supply the date.
SI_NAMESPACE = {"10": "Re-Issue / non-seasonal"}
for _k in SI_NAMESPACE:
    SI_SEASON.pop(_k, None)

# B. Alphanumeric: letter = year, digit = season. Extend as new codes appear.
SI_ALPHA_SEASON = {
    "K1": (2025, "SS"), "K2": (2025, "AW"),
    "L1": (2026, "SS"), "L2": (2026, "AW"),
}

# D. C.P. modern counter. Same alternating shape, different origin (02 = SS2017).
CP_MODERN_SEASON = {
    f"{n:02d}": (2019 + (n - 6) // 2, "SS" if n % 2 == 0 else "AW")
    for n in range(2, 30)
}

# Brand / line code — characters 3-4 of the SI numeric format.
BRAND = {
    "15": "Stone Island",
    "14": "Stone Island Denims",
    "16": "Stone Island Junior",
    "19": "Stone Island Shadow Project",
    "25": "Stone Island Limited Editions / collaborations",
    "26": "Stone Island Serie 100",
    "28": "Stone Island Internal Staff Use",
    "30": "Stone Island x Nokia",
    "18": "C.P. Company",
    "20": "C.P. Company Donna",
    "13": "C.P. Company Under 16",
    "11": "C.P. Company knitwear",
}

# Garment category — character 5. Digits and letters both occur.
GARMENT = {
    "0": "Leather / suede",
    "1": "Overshirt / shirt / light jacket",
    "2": "T-shirt / polo",
    "3": "Trousers",
    "4": "Jacket",
    "5": "Knitwear",
    "6": "Sweatshirt / hoodie",
    "7": "Parka / trench / long outerwear",
    "8": "Swim / beachwear",
    "9": "Bags / caps / accessories",
    "A": "Jacket",
    "B": "Swim shorts",
    "G": "Gilet / vest",
    "J": "Jeans / denim",
    "L": "Shorts / bermuda",
    "M": "Jacket",
    "N": "Headwear / knitted accessories",
    "Q": "Jacket / outerwear",
}

# D. C.P. modern garment codes — characters 4-5 of e.g. 14CMOS045A.
CP_GARMENT = {
    "OW": "Outerwear", "OS": "Overshirt", "SH": "Shirt / overshirt",
    "SS": "Sweatshirt / hoodie", "KN": "Knitwear", "TS": "T-shirt",
    "PL": "Polo", "PA": "Trousers", "SP": "Sweatpants", "BE": "Bermuda",
    "BW": "Swimwear", "SB": "Shorts", "AC": "Accessories", "VE": "Gilet",
    "BZ": "Blazer",
}

FAKE_MARKER = "222"  # commonly reported on counterfeit SI wash labels


@dataclass
class Art:
    raw: str
    format: Optional[str] = None
    year: Optional[int] = None
    season: Optional[str] = None
    brand: Optional[str] = None
    garment: Optional[str] = None
    flags: tuple = ()

    @property
    def label(self) -> str:
        """Human-readable string for the review sheet, e.g. 'AW 2007 - Jacket'."""
        bits = []
        if self.season and self.year:
            bits.append(f"{self.season} {self.year}")
        if self.brand:
            bits.append(self.brand)
        if self.garment:
            bits.append(self.garment)
        return " \u00b7 ".join(bits) if bits else "Unrecognised"


def parse(raw: str) -> Art:
    s = re.sub(r"[\s\-]", "", (raw or "").upper())
    s = s.split("/")[0]                      # trailing colour code, e.g. 581540846/181
    s = re.sub(r"(?<=C[MKSL])0(?=[A-Z])", "O", s)   # 12CM0W303A -> 12CMOW303A
    flags = ("possible-counterfeit-marker",) if FAKE_MARKER in s else ()

    # B. SI alphanumeric: K1S154100067
    m = re.match(r"^([KL][12])S(.{2})(.)", s)
    if m and m.group(1) in SI_ALPHA_SEASON:
        yr, sn = SI_ALPHA_SEASON[m.group(1)]
        return Art(raw, "si_alpha", yr, sn,
                   BRAND.get(m.group(2)), GARMENT.get(m.group(3)), flags)

    # D. CP modern: 14CMOS045A
    m = re.match(r"^(\d{2}|R[FC])C([MKSL])([A-Z]{2})", s)
    if m:
        yr, sn = CP_MODERN_SEASON.get(m.group(1), (None, None))
        f = flags
        if m.group(2) in "SL":
            f += ("collab-or-special-line-verify-season",)
        if m.group(1) in ("RF", "RC"):
            f += ("reorder-prefix-no-season",)
        return Art(raw, "cp_modern", yr, sn, "C.P. Company",
                   CP_GARMENT.get(m.group(3)), f)

    # C. CP transitional: 14SCPUB04669
    m = re.match(r"^(\d{2})([SW])C?PU", s)
    if m:
        return Art(raw, "cp_transitional", 2000 + int(m.group(1)),
                   "SS" if m.group(2) == "S" else "AW", "C.P. Company", None, flags)

    # A. SI numeric: 58154 0923  (min 8 chars — shorter means a truncated entry)
    m = re.match(r"^(\d{2})(\d{2})([0-9A-Z])", s)
    if m and len(s) >= 8:
        pre, brand, garment = m.group(1), m.group(2), m.group(3)
        if pre in SI_NAMESPACE:
            return Art(raw, "si_namespace", None, None, BRAND.get(brand),
                       GARMENT.get(garment), flags + ("no-season-in-code",))
        if pre in SI_SEASON:
            yr, sn = SI_SEASON[pre]
            return Art(raw, "si_numeric", yr, sn,
                       BRAND.get(brand), GARMENT.get(garment), flags)

    if re.match(r"^\d{2}", s) and len(s) < 8:
        return Art(raw, None, flags=flags + ("truncated",))
    if re.match(r"^C(PU|M[A-Z]{2})", s):
        return Art(raw, None, flags=flags + ("truncated-cp-prefix-missing",))
    return Art(raw, None, flags=flags + ("unrecognised",))



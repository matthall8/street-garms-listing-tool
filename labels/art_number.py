"""
Stone Island / C.P. Company ART number parser.

Derived from Street Garms' own catalogue (~1,500 human-confirmed rows),
not from web sources. Every table below is DATA, not arithmetic: unknown
keys return None rather than extrapolating.

Four format families were found in the catalogue:
  A. SI numeric        581540923       -> shared with C.P. pre-2010 (brand 18)
  B. SI alphanumeric   K1S154100067    -> SS2025 onward
  C. CP transitional   14SCPUB04669    -> ~2011-2016
  D. CP modern         14CMOS045A      -> ~2017 onward
"""

import re
import string
from dataclasses import dataclass

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

# D. C.P. modern garment codes — characters 4-5 of DDCAAADDDA.
CP_GARMENT = {
    "OW": "Outerwear", "OS": "Overshirt", "SH": "Shirt / overshirt",
    "SS": "Sweatshirt / hoodie", "KN": "Knitwear", "TS": "T-shirt",
    "PL": "Polo", "PA": "Trousers", "SP": "Sweatpants", "BE": "Bermuda",
    "BW": "Swimwear", "SB": "Shorts", "AC": "Accessories", "VE": "Gilet",
    "BZ": "Blazer",
}

FAKE_MARKER = "222"  # commonly reported on counterfeit SI wash labels

ART_CAPTIONS = ('ART.', 'ART NO.')
SEPARATOR = re.compile(r"[ \t/]")  # ends the base; a hyphen never does (ADR-0005)

DISALLOWED = re.compile(r"[^\t\x20-\x7e]")  # anything but a tab or printable ASCII (ADR-0005)
# str.upper() maps some non-ASCII letters to ASCII ones; this never normalises
ASCII_UPPER = str.maketrans(string.ascii_lowercase, string.ascii_uppercase)

# The split's family prefixes (ADR-0005): shape only, never a season table, so
# an unknown season still splits. The SI numeric counter covers '10' too.
FAMILY_PREFIXES = {
    "si_numeric": re.compile(r"[0-9?]{4}"),                                 # DDDD
    "si_alpha": re.compile(r"[A-Z?][0-9?][S?]"),                            # ADS
    "cp_modern": re.compile(r"([0-9?]{2}|[R?][FC?])[C?][MKSL?]"),           # DD or RF/RC, C, line letter
    "cp_transitional": re.compile(r"[0-9?]{2}[SW?][C?]?[P?][U?]"),          # DD, S/W, optional C, PU
}

# Full base shapes: each family's prefix, then letters or digits up to its
# length (ADR-0005)
FAMILY_BASES = {
    "si_numeric": re.compile(r"[0-9?]{4}[0-9A-Z?]{4,5}"),
    "si_alpha": re.compile(r"[A-Z?][0-9?][S?][0-9A-Z?]{9}"),
    "cp_modern": re.compile(r"([0-9?]{2}|[R?][FC?])[C?][MKSL?][0-9A-Z?]{6}"),
    "cp_transitional": re.compile(r"[0-9?]{2}[SW?][C?]?[P?][U?][0-9A-Z?]{6}"),
}

# Tail shapes after each family's base, in the order they're read: a field
# appears at most once, and may be skipped. A ? fits any one character, the LOT
# letters and hyphens included; no two shapes in a family share a length, so a
# piece fits at most one (ADR-0005)
FAMILY_TAILS = {
    "si_numeric": (
        ("art_suffix", re.compile(r"[0-9?]{2,4}")),                                    # colour code
        ("art_lot", re.compile(
            r"[L?][O?][T?][A-Z?][-?][0-9?]{2}[-?][0-9?]{5}"                            # short LOT
            r"|[A-Z?][-?][0-9?]{2}[-?][L?][O?][T?][A-Z?][-?][0-9?]{4}[-?][0-9?]{5}"    # long LOT
        )),
    ),
    "si_alpha": (),
    "cp_modern": (
        ("art_suffix", re.compile(r"[0-9?]{6}[A-Z?]")),                                # fabric code
    ),
    "cp_transitional": (),
}


@dataclass
class Art:
    raw: str
    format: str | None = None
    year: int | None = None
    season: str | None = None
    brand: str | None = None
    garment: str | None = None
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


@dataclass
class ArtSplit:
    art_caption: str | None = None
    art_base: str | None = None
    art_unmatched: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    art_suffix: str | None = None
    art_lot: str | None = None


def parse(raw: str) -> Art:
    s = re.sub(r"[\s\-]", "", (raw or "").upper())
    s = s.split("/")[0]                      # trailing colour code: <base>/DDD
    flags = ("possible-counterfeit-marker",) if FAKE_MARKER in s else ()

    # B. SI alphanumeric: ADADDDDDDDDD
    m = re.match(r"^([KL][12])S(.{2})(.)", s)
    if m and m.group(1) in SI_ALPHA_SEASON:
        yr, sn = SI_ALPHA_SEASON[m.group(1)]
        return Art(raw, "si_alpha", yr, sn,
                   BRAND.get(m.group(2)), GARMENT.get(m.group(3)), flags)

    # D. CP modern: DDAAAADDDA
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

    # C. CP transitional: DDAAAAADDDDD
    m = re.match(r"^(\d{2})([SW])C?PU", s)
    if m:
        return Art(raw, "cp_transitional", 2000 + int(m.group(1)),
                   "SS" if m.group(2) == "S" else "AW", "C.P. Company", None, flags)

    # A. SI numeric: DDDDD DDDD  (min 8 chars — shorter means a truncated entry)
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


def split_art_line(art_line: str) -> ArtSplit:
    art_line = art_line.strip(string.whitespace)  # ASCII only: never normalise the read
    art_line_upper = art_line.translate(ASCII_UPPER)
    art_caption, rest = None, art_line
    problems = ("question_mark",) if "?" in art_line else ()
    if DISALLOWED.search(art_line):
        problems += ("disallowed_character",)
    for caption in ART_CAPTIONS:
        if art_line_upper.startswith(caption):
            idx = len(caption)
            art_caption, rest = art_line[:idx], art_line[idx:].lstrip(" \t")
            break
    families = [name for name, prefix in FAMILY_PREFIXES.items() if prefix.match(rest.translate(ASCII_UPPER))]
    if len(families) != 1:
        return ArtSplit(art_caption=art_caption, art_unmatched=(rest,) if rest else (),
                        problems=problems + ("art_unmatched",))
    base = SEPARATOR.split(rest, maxsplit=1)[0]  # the base ends at the first separator
    tail = rest[len(base):]
    if not FAMILY_BASES[families[0]].fullmatch(base.translate(ASCII_UPPER)):
        return ArtSplit(art_caption=art_caption, problems=problems + ("base_shape",))
    tails = {}
    for field, shape in FAMILY_TAILS[families[0]]:
        # a separator, then the piece up to the next one; the separator is
        # dropped with a matched piece and kept with an unmatched one
        m = re.match(r"(?:[ \t]*/[ \t]*|[ \t]+)([^ \t/]*)", tail)
        if m and shape.fullmatch(m.group(1).translate(ASCII_UPPER)):
            tails[field] = m.group(1)  # matched in upper case, stored as read
            tail = tail[m.end():]
    tail = tail.strip(string.whitespace)
    return ArtSplit(art_caption=art_caption, art_base=base.translate(ASCII_UPPER), **tails,
                    art_unmatched=(tail,) if tail else (),
                    problems=problems + (("art_unmatched",) if tail else ()))


def art_candidate(art_line: str) -> str:
    """What the catalogue looks up when the split fails: the line without its
    caption, up to the first separator (ADR-0005, *When the split fails*)."""
    art_line = art_line.strip(string.whitespace)
    caption = split_art_line(art_line).art_caption or ""
    return SEPARATOR.split(art_line[len(caption):].lstrip(" \t"), maxsplit=1)[0]

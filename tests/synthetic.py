"""Invented values for tests that need something shaped like private data.

None of these is real. Never copy a catalogue key, product name, photo
filename or Certilogo code here: CLAUDE.md allows code-shaped literals in this
file only because they are invented, and the privacy hook's pattern checks
skip it (its real-value check still applies).
"""

# Catalogue keys
KEY = "QZ7310X4482"
OTHER_KEY = "QZ7310X4483"
COMPOUND_KEY = "QZ7310XA4482B"
COMPOUND_PRINTED = "qz7310xa 4482b"  # spacing and case as a label might print it

# Catalogue product names
NAME = "Zorvane Quillet Testpiece Overcoat"
NAME_WORD = "Overcoat"
SHORT_NAME = "Quillet Overshirt"  # two words: too short to match

# Manifest
PHOTO = "zz_synthetic_label_07.jpg"
PHOTO_STEM = "zz_synthetic_label_07"
NEGATIVE_PHOTO = "zz_synthetic_label_08.png"
EXPECTED_CODE = "QZ5550Y7001"  # in the manifest, not the catalogue

# Held-out manifest
HOLDOUT_PHOTO = "zz_synthetic_holdout_03.jpg"
HOLDOUT_PHOTO_STEM = "zz_synthetic_holdout_03"
HOLDOUT_EXPECTED_CODE = "QZ6660T8002"  # in the held-out manifest only

# Not private, but caught by the reviewer's patterns
CODE_SHAPED = "QZ9020W1234"
IMAGE = "zz_untracked_shot.webp"

# Gate baselines: one catalogue key per format family, each decoding with a
# format and a year and no flags, so an exact hit on it is needs_review=False
GATE_SI_NUMERIC = "4815QZ7342"         # SS2008
GATE_SI_ALPHA = "K1S15QZ7342"          # SS2025
GATE_CP_TRANSITIONAL = "13WCPUQZ7342"  # AW2013
GATE_CP_MODERN = "14CMOWQZ7342"        # SS2023

# Gate clauses: each decodes like a baseline except for the one thing named
GATE_COUNTERFEIT_MARKER = "4815QZ2227"  # contains 222
GATE_COLLAB_LINE = "14CSOWQZ7342"       # cp_modern on the S line
GATE_NO_YEAR = "01CMOWQZ7342"           # cp_modern prefix outside the table
GATE_UNRECOGNISED = "QZ7342"
GATE_TRUNCATED = "4815QZ7"              # under 8 characters
GATE_TRUNCATED_CP = "CMOWQZ7342"        # cp_modern without its prefix
GATE_CORRECTED_KEY = "4815QZ7O42"
GATE_CORRECTED_READ = "4815QZ7042"      # one confusion from the key above
GATE_AMBIGUOUS_READ = "4815QZ0O42"      # one confusion from each key below
GATE_AMBIGUOUS_KEY_A = "4815QZOO42"
GATE_AMBIGUOUS_KEY_B = "4815QZ0042"
GATE_MISS = "4815QZ9342"                # no key, and no key one confusion away
GATE_UNKNOWN_BRAND_GARMENT = "4899ZQ7342"  # brand 99 and garment Z are in no table
GATE_UNREADABLE_MARK = "4815Q?7342"     # ? past the decoded prefix

# A manifest column nobody has classified, named like a code so a crash
# message carrying it would leak
UNKNOWN_COLUMN = "QZ4040V9090"

ALL = [
    KEY, OTHER_KEY, COMPOUND_KEY, COMPOUND_PRINTED, NAME, SHORT_NAME, PHOTO,
    PHOTO_STEM, NEGATIVE_PHOTO, EXPECTED_CODE, HOLDOUT_PHOTO, HOLDOUT_PHOTO_STEM,
    HOLDOUT_EXPECTED_CODE, CODE_SHAPED, IMAGE, GATE_SI_NUMERIC, GATE_SI_ALPHA,
    GATE_CP_TRANSITIONAL, GATE_CP_MODERN, GATE_COUNTERFEIT_MARKER,
    GATE_COLLAB_LINE, GATE_NO_YEAR, GATE_UNRECOGNISED, GATE_TRUNCATED,
    GATE_TRUNCATED_CP, GATE_CORRECTED_KEY, GATE_CORRECTED_READ,
    GATE_AMBIGUOUS_READ, GATE_AMBIGUOUS_KEY_A, GATE_AMBIGUOUS_KEY_B, GATE_MISS,
    GATE_UNKNOWN_BRAND_GARMENT, GATE_UNREADABLE_MARK, UNKNOWN_COLUMN,
]

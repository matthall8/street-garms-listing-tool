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

# The split: invented codes, one per family at a real base length. Stone
# Island ones use brand 99 and C.P. modern ones the garment code QZ, which no
# catalogue key has. The C.P. transitional ones have no such marker: like
# every value here, the privacy hook's real-value check guards them
SPLIT_SI_9 = "7899Q1234"                 # counter 78: length 9, DDDDADDDD
SPLIT_SI_8 = "3999Q123"                  # counter 39: length 8, DDDDADDD
SPLIT_SI_NAMESPACE = "109912345"         # counter 10: no season
SPLIT_SI_ALPHA = "K1S99Q123456"          # ADADDADDDDDD
SPLIT_CP_MODERN = "19CMQZ123A"           # DDAAAADDDA
SPLIT_CP_REORDER = "RFCMQZ123A"          # AAAAAADDDA: reorder prefix
SPLIT_CP_TRANSITIONAL = "13SCPUQ12345"   # DDAAAAADDDDD
SPLIT_CP_TRANSITIONAL_11 = "13SPUQ12345" # DDAAAADDDDD: no C
SPLIT_CP_FABRIC = "123456Q"              # the same-line tail on C.P. labels
SPLIT_COLOUR = "9876"                    # DDDD: an SI colour code; slice it for DD and DDD
SPLIT_LOT_SHORT = "LOTQ-12-34567"        # AAAA-DD-DDDDD
SPLIT_LOT_LONG = "Q-12-LOTQ-1234-56789"  # A-DD-AAAA-DDDD-DDDDD
SPLIT_NEXT_LINE = "Q1234"                # a next-line variant code, joined on
SPLIT_SI_LETTER_8 = "7899123Q4"         # DDDDDDDAD: a letter at position 8
SPLIT_SI_LETTERS_END = "7899123QZ"      # DDDDDDDAA: two letters at the end
SPLIT_SI_LEADING_ZERO = "0599Q1234"     # counter 05: a leading zero

# Other lines a model might pick instead of the ART line
SPLIT_BARCODE = "789912345678"          # 12 digits, starting like an SI code
SPLIT_PHONE = "0999-123456"             # hyphenated, starting like an SI code
SPLIT_DATE = "12/2099"                  # DD/DDDD
SPLIT_CERTILOGO = "111111111111"        # 12 digits, repeated so it can't be real
SPLIT_POSTCODE = "99999"                # DDDDD

ALL = [
    KEY, OTHER_KEY, COMPOUND_KEY, COMPOUND_PRINTED, NAME, SHORT_NAME, PHOTO,
    PHOTO_STEM, NEGATIVE_PHOTO, EXPECTED_CODE, HOLDOUT_PHOTO, HOLDOUT_PHOTO_STEM,
    HOLDOUT_EXPECTED_CODE, CODE_SHAPED, IMAGE, GATE_SI_NUMERIC, GATE_SI_ALPHA,
    GATE_CP_TRANSITIONAL, GATE_CP_MODERN, GATE_COUNTERFEIT_MARKER,
    GATE_COLLAB_LINE, GATE_NO_YEAR, GATE_UNRECOGNISED, GATE_TRUNCATED,
    GATE_TRUNCATED_CP, GATE_CORRECTED_KEY, GATE_CORRECTED_READ,
    GATE_AMBIGUOUS_READ, GATE_AMBIGUOUS_KEY_A, GATE_AMBIGUOUS_KEY_B, GATE_MISS,
    GATE_UNKNOWN_BRAND_GARMENT, GATE_UNREADABLE_MARK, UNKNOWN_COLUMN,
    SPLIT_SI_9, SPLIT_SI_8, SPLIT_SI_NAMESPACE, SPLIT_SI_ALPHA,
    SPLIT_CP_MODERN, SPLIT_CP_REORDER, SPLIT_CP_TRANSITIONAL,
    SPLIT_CP_TRANSITIONAL_11, SPLIT_CP_FABRIC, SPLIT_COLOUR, SPLIT_LOT_SHORT, SPLIT_LOT_LONG,
    SPLIT_NEXT_LINE, SPLIT_SI_LETTER_8, SPLIT_SI_LETTERS_END,
    SPLIT_SI_LEADING_ZERO, SPLIT_BARCODE, SPLIT_PHONE, SPLIT_DATE,
    SPLIT_CERTILOGO, SPLIT_POSTCODE,
]

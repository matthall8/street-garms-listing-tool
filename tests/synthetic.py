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

# Not private, but caught by the reviewer's patterns
CODE_SHAPED = "QZ9020W1234"
IMAGE = "zz_untracked_shot.webp"

# A manifest column nobody has classified, named like a code so a crash
# message carrying it would leak
UNKNOWN_COLUMN = "QZ4040V9090"

ALL = [
    KEY, OTHER_KEY, COMPOUND_KEY, COMPOUND_PRINTED, NAME, SHORT_NAME, PHOTO,
    PHOTO_STEM, NEGATIVE_PHOTO, EXPECTED_CODE, CODE_SHAPED, IMAGE, UNKNOWN_COLUMN,
]

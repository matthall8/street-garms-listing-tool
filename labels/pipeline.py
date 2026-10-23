"""Transcribe, then decode. The join between the two halves."""

import mimetypes
from pathlib import Path

from labels.art_number import parse
from labels.catalogue import resolve
from labels.schemas import ArtNumberReading, Extraction
from labels.transcribe import transcribe

Photo = tuple[bytes, str]  # (image_bytes, media_type)


def from_reading(art_read: ArtNumberReading, source: str = "") -> Extraction:
    """Parse, resolve and gate one ART read: everything after transcription.

    Makes no API call, so the eval replay and scorer can run it on saved
    reads: the same code the app runs. Not pure: resolve() reads the catalogue.
    """
    decoded = parse(art_read.art_number_raw or "")
    matched = resolve(art_read.art_number_raw, art_read.art_legible)

    return Extraction(
        source_image=source,
        art_number_raw=art_read.art_number_raw,
        decoded=decoded.label,
        year=decoded.year,
        season=decoded.season,
        brand=decoded.brand,
        garment=decoded.garment,
        product_name=matched.product_name,
        catalogue_match=matched.status,
        matched_art=matched.matched_art,
        legibility=art_read.art_legible,
        all_reads=[a.model_dump() for a in art_read.ambiguous_characters],
        flags=list(decoded.flags),
        needs_review=(
            art_read.art_legible != "clear"
            or bool(art_read.ambiguous_characters)
            or bool(decoded.flags)
            or decoded.format is None
            or decoded.year is None
            or matched.status in ("corrected", "ambiguous")
        ),
    )


def extract_bytes(art: Photo, source: str = "") -> Extraction:
    """Full pipeline over raw image bytes — the form web uploads arrive in."""
    art_read = transcribe(art=art).art
    return from_reading(art_read, source)


def _photo(path: Path) -> Photo:
    media_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return path.read_bytes(), media_type


def extract(art_image: Path) -> Extraction:
    """Full pipeline over files on disk."""
    return extract_bytes(art=_photo(art_image), source=str(art_image))

"""Transcribe, then decode. The join between the two halves."""

import mimetypes
from pathlib import Path

from labels.art_number import parse
from labels.schemas import Extraction
from labels.transcribe import transcribe


def extract_bytes(data: bytes, media_type: str, source: str) -> Extraction:
    """Full pipeline over raw image bytes — the form a web upload arrives in."""
    reading = transcribe(data, media_type)
    art = parse(reading.art_number_raw or "")

    return Extraction(
        source_image=source,
        art_number_raw=reading.art_number_raw,
        decoded=art.label,
        year=art.year,
        season=art.season,
        brand=art.brand or reading.brand_printed,
        garment=art.garment,
        size=reading.size,
        composition=reading.composition,
        made_in=reading.made_in,
        certilogo=reading.certilogo,
        legibility=reading.art_legible,
        all_reads=reading.ambiguous_characters,
        flags=list(art.flags),
        needs_review=(
            reading.art_legible != "clear"
            or bool(reading.ambiguous_characters)
            or bool(art.flags)
            or art.year is None
        ),
    )


def extract(image: Path) -> Extraction:
    """Full pipeline over a file on disk."""
    media_type = mimetypes.guess_type(image.name)[0] or "image/jpeg"
    return extract_bytes(image.read_bytes(), media_type, str(image))

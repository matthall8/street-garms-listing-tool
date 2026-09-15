"""Transcribe, then decode. The join between the two halves."""

import mimetypes
from pathlib import Path
from typing import Optional

from labels.art_number import parse
from labels.schemas import Extraction
from labels.transcribe import transcribe
from labels.catalogue import resolve

Photo = tuple[bytes, str]  # (image_bytes, media_type)


def extract_bytes(
    art: Optional[Photo] = None,
    details: Optional[Photo] = None,
    source: str = "",
) -> Extraction:
    """Full pipeline over raw image bytes — the form web uploads arrive in.

    Either photo may be omitted; whichever is given gets read.
    """
    reading = transcribe(art=art, details=details)
    art_read, det = reading.art, reading.details
    decoded = parse(art_read.art_number_raw or "")
    matched = resolve(art_read.art_number_raw, art_read.art_legible)


    return Extraction(
        source_image=source,
        art_number_raw=art_read.art_number_raw,
        decoded=decoded.label,
        year=decoded.year,
        season=decoded.season,
        brand=decoded.brand or det.brand_printed,
        garment=decoded.garment,
        product_name=matched.product_name,
        catalogue_match=matched.status,
        matched_art=matched.matched_art,
        size=" / ".join(f"{s.system} {s.value}" for s in det.sizes) or None,
        composition=det.composition,
        made_in=det.made_in,
        certilogo=det.clg_number,
        colour_observed=det.garment_colour_observed,
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


def _photo(path: Path) -> Photo:
    media_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return path.read_bytes(), media_type


def extract(art_image: Path, details_image: Optional[Path] = None) -> Extraction:
    """Full pipeline over files on disk."""
    sources = [str(art_image)] + ([str(details_image)] if details_image else [])
    return extract_bytes(
        art=_photo(art_image),
        details=_photo(details_image) if details_image else None,
        source=", ".join(sources),
    )

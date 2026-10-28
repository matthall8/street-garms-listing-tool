"""Data shapes shared by the CLI and the web layer."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

ArtLegibility = Literal["clear", "partial", "illegible", "not_visible"]


class AmbiguousCharacter(BaseModel):
    """A character that has two visually plausible readings."""

    position: int = Field(
        description="1-based character position in the code."
    )
    reading: str = Field(
        description="Best visual reading of the character."
    )
    alternative: str = Field(
        description="Alternative visually plausible reading."
    )


class ArtNumberReading(BaseModel):
    """The ART number, read from a photo framed on the ART number tag."""

    art_number_raw: str | None = Field(
        default=None,
        description=(
            "Verbatim ART number as physically printed. "
            "Preserve leading zeros, spaces, slashes and letters. "
            "Use '?' for positions that are unreadable."
        ),
    )

    art_legible: ArtLegibility = Field(
        description=(
            "'clear' if every character was read confidently. "
            "'partial' if some characters are uncertain. "
            "'illegible' if an ART number is present but cannot be read. "
            "'not_visible' if no ART number appears in this image at all."
        )
    )

    ambiguous_characters: list[AmbiguousCharacter] = Field(
        default_factory=list,
        description=(
            "Characters for which two visual readings are genuinely plausible. "
            "Do not populate merely because characters such as 0/O can "
            "theoretically be confused."
        ),
    )


class LabelReading(BaseModel):
    """What transcription returns for one listing: the ART read."""

    art: ArtNumberReading


@dataclass
class Extraction:
    """A LabelReading joined with downstream product interpretation."""

    source_image: str
    art_number_raw: str | None
    art_base: str | None
    decoded: str
    product_name: str | None
    year: int | None
    season: str | None
    brand: str | None
    garment: str | None
    legibility: str
    all_reads: list
    flags: list
    catalogue_match: str
    matched_art: str | None
    needs_review: bool

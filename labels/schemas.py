"""Data shapes shared by the CLI and the web layer."""

from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LabelReading(BaseModel):
    """What the vision model reports it can physically see on the label."""

    art_number_raw: Optional[str] = Field(
        None, description="Verbatim, character for character. '?' for unreadable positions."
    )
    art_legible: Literal["clear", "partial", "illegible"]
    ambiguous_characters: list[str] = Field(
        default_factory=list, description="e.g. 'position 5: 0 or O'"
    )
    brand_printed: Optional[str] = None
    size: Optional[str] = None
    composition: Optional[str] = None
    made_in: Optional[str] = None
    certilogo: Optional[str] = Field(None, description="CLG code, SS2014 onward")
    notes: Optional[str] = None


@dataclass
class Extraction:
    """A LabelReading joined with the decoded art number — the listing payload."""

    source_image: str
    art_number_raw: Optional[str]
    decoded: str
    year: Optional[int]
    season: Optional[str]
    brand: Optional[str]
    garment: Optional[str]
    size: Optional[str]
    composition: Optional[str]
    made_in: Optional[str]
    certilogo: Optional[str]
    legibility: str
    all_reads: list
    flags: list
    needs_review: bool

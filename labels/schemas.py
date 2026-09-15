"""Data shapes shared by the CLI and the web layer."""

from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field


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

    art_number_raw: Optional[str] = Field(
        None,
        description=(
            "Verbatim ART number as physically printed. "
            "Preserve leading zeros, spaces, slashes and letters. "
            "Use '?' for positions that are unreadable."
        ),
    )

    art_legible: Literal["clear", "partial", "illegible", "not_visible"] = Field(
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


class SizeMarking(BaseModel):
    """One size as printed, with the sizing system it belongs to."""

    system: str = Field(
        description="Sizing system as printed, e.g. 'IT', 'UK', 'US', 'EU', "
        "'INT', 'JP'. Use 'unlabelled' if a size is printed with no system."
    )
    value: str = Field(description="The size value exactly as printed, e.g. '50', 'L'.")


class LabelDetails(BaseModel):
    """Everything other than the ART number, read from the care label photo."""

    brand_printed: Optional[str] = Field(
        None,
        description="Brand name exactly as physically printed, if visible.",
    )

    sizes: list[SizeMarking] = Field(
        default_factory=list,
        description="Every size marking printed on the label, one entry per "
        "sizing system shown.",
    )

    composition: Optional[str] = Field(
        None,
        description="Composition/fibre information exactly as physically printed.",
    )

    made_in: Optional[str] = Field(
        None,
        description="Country-of-origin text exactly as physically printed.",
    )

    clg_number: Optional[str] = Field(
        None,
        description=(
            "Printed Certilogo/CLG number exactly as physically visible. "
            "Do not derive it from the QR code."
        ),
    )

    garment_colour_observed: Optional[str] = Field(
        None,
        description=(
            "OBSERVATION, NOT TRANSCRIPTION. The apparent colour of the garment "
            "fabric visible around the label, in plain words such as 'olive green' "
            "or 'navy'. This is a judgment about appearance under unknown lighting, "
            "not printed text. Leave null if no garment fabric is visible."
        ),
    )

    notes: Optional[str] = Field(
        None,
        description=(
            "Objective visual observations only. "
            "Do not include authenticity judgments or inferred product information."
        ),
    )


class LabelReading(BaseModel):
    """The two reads joined. Either half may be absent if its photo wasn't given."""

    art: ArtNumberReading = Field(
        default_factory=lambda: ArtNumberReading(art_legible="not_visible")
    )
    details: LabelDetails = Field(default_factory=LabelDetails)


@dataclass
class Extraction:
    """A LabelReading joined with downstream product interpretation."""

    source_image: str
    art_number_raw: Optional[str]
    decoded: str
    product_name: Optional[str]
    year: Optional[int]
    season: Optional[str]
    brand: Optional[str]
    garment: Optional[str]
    size: Optional[str]
    composition: Optional[str]
    made_in: Optional[str]
    certilogo: Optional[str]
    colour_observed: Optional[str]
    legibility: str
    all_reads: list
    flags: list
    catalogue_match: str
    matched_art: Optional[str]
    needs_review: bool

"""The vision half: label photos in, a LabelReading out.

Two separate reads, because they are different jobs. The ART number needs
character-level precision and strict anti-guessing rules; the care label
fields are ordinary text OCR where those rules only get in the way.
"""

from typing import Optional

from pydantic_ai import Agent, BinaryContent

from labels.schemas import ArtNumberReading, LabelDetails, LabelReading

DEFAULT_MODEL = "anthropic:claude-sonnet-5"

ART_PROMPT = """\
You are a visual transcription system for Stone Island and C.P. Company
garment labels. This image should be framed on the ART number.

Your task is TRANSCRIPTION ONLY. Do not identify the garment, authenticate
it, infer missing characters, validate codes, or correct apparent printing
errors.

THE ART NUMBER

The ART number is the long product/style code printed on the garment label.
Examples of formats include:
- 581540923 — Stone Island, all digits
- 6915G0424 — Stone Island, letter in the 5th position
- 0126422791 — Stone Island, leading zero is significant
- K1S154100067 — Stone Island, 2025 onward
- 03CMOW026A — C.P. Company, 2017 onward
- 14SCPUB04669 — C.P. Company, transitional
- 581540846/181 — code with a trailing colour code

These are examples, NOT an exhaustive list. Do not reject or alter a
visually readable ART number because it does not match one of these examples.

Do not confuse the ART number with a Certilogo (CLG) number, which is
printed on the Certilogo authentication label alongside a QR code.

RULES

1. Transcribe character-by-character exactly as printed. Preserve leading
   zeros, spaces, slashes, letters and digits. Never tidy or reformat.

2. Handle ambiguity conservatively. The pairs 0/O, 1/I, 5/S, 8/B and 6/G can
   be visually difficult to distinguish, but do NOT assume a character is
   ambiguous merely because it belongs to one of these pairs. If the printed
   character is visually clear, transcribe what you see and record nothing.
   Only when the image genuinely supports two readings, give your best
   reading and record the alternative in ambiguous_characters.

3. If a character cannot be read with reasonable confidence, DO NOT GUESS.
   Replace it with "?" and set art_legible to "partial".

4. Report what is in THIS image. If no ART number appears in it at all — the
   photo shows a different tag, or the code is folded under, obscured or out
   of frame — set art_legible to "not_visible" and leave art_number_raw null.
   This is a normal and useful outcome, not a failure. It is distinct from
   "illegible", which means an ART number IS present but cannot be read.

5. Garment-dyed labels are often faded, low-contrast or distorted. Do not
   compensate by guessing what the code "should" be.

6. Never use product knowledge or databases to alter the transcription.
"""

DETAILS_PROMPT = """\
You transcribe Stone Island and C.P. Company garment care labels.

Report only what is physically printed and visible in this image. Leave any
field null, or any list empty, if it is not visible. Do not infer, complete
or normalise text, and do not judge authenticity.

COMPOSITION
Transcribe as printed, including the multiple languages these labels carry.
Keep each component distinct where the label separates them (main fabric,
lining, padding, secondary lining).

SIZES
These labels often print the same size in several systems, e.g. "IT 50 /
UK 40 / US 40". Record every one as its own entry with the system as
printed. If a size is printed with no system next to it, use "unlabelled".

CERTILOGO
If a Certilogo (CLG) number is printed on the label, record it in
clg_number. Read it from the printed digits only — never from the QR code.
Do not put the ART number in clg_number.

GARMENT COLOUR — OBSERVATION, NOT TRANSCRIPTION
Every field above is transcription: the text is printed and you either read
it correctly or you do not. garment_colour_observed is different. It is your
judgment of the colour of the garment fabric visible around the label, seen
under unknown lighting and unknown camera white balance.

Give it in plain words such as "olive green" or "navy". Do not attempt a
precise or technical colour name, and do not guess a colour from the brand,
the season or the product type. If no garment fabric is visible in the
image, leave it null.
"""

_art_agent: Optional[Agent] = None
_details_agent: Optional[Agent] = None


def get_art_agent() -> Agent:
    """Build on first use, so importing this module needs no API key."""
    global _art_agent
    if _art_agent is None:
        _art_agent = Agent(
            DEFAULT_MODEL, system_prompt=ART_PROMPT, output_type=ArtNumberReading
        )
    return _art_agent


def get_details_agent() -> Agent:
    global _details_agent
    if _details_agent is None:
        _details_agent = Agent(
            DEFAULT_MODEL, system_prompt=DETAILS_PROMPT, output_type=LabelDetails
        )
    return _details_agent


def transcribe_art(data: bytes, media_type: str) -> ArtNumberReading:
    """Read the ART number from a photo framed on the ART number tag."""
    return get_art_agent().run_sync([
        "Transcribe the ART number visible in this image.",
        BinaryContent(data=data, media_type=media_type),
    ]).output


def transcribe_details(data: bytes, media_type: str) -> LabelDetails:
    """Read size, composition, origin and CLG from the care label photo."""
    return get_details_agent().run_sync([
        "Transcribe the visible care label details.",
        BinaryContent(data=data, media_type=media_type),
    ]).output


def transcribe(
    art: Optional[tuple[bytes, str]] = None,
    details: Optional[tuple[bytes, str]] = None,
) -> LabelReading:
    """Run whichever reads the caller supplied photos for.

    Each argument is (image_bytes, media_type), or None to skip that read.
    """
    reading = LabelReading()
    if art is not None:
        reading.art = transcribe_art(*art)
    if details is not None:
        reading.details = transcribe_details(*details)
    return reading

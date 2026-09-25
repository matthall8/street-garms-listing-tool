"""The vision half: label photos in, a LabelReading out.

Two separate reads, because they are different jobs. The ART number needs
character-level precision and strict anti-guessing rules; the care label
fields are ordinary text OCR where those rules only get in the way.
"""

from functools import cache
from typing import Optional

from pydantic_ai import Agent, BinaryContent, ModelSettings

from labels.schemas import ArtNumberReading, LabelDetails, LabelReading

# Two constants, because the two reads are not equally hard. The ART pass is
# character-level work on small, faded print; the details pass is ordinary OCR
# on large clear text and could run on something cheaper.
ART_MODEL = "anthropic:claude-sonnet-5"
DETAILS_MODEL = "anthropic:claude-sonnet-5"

# Model settings to reduce timeout time to 1 minute, rather than the client's default.
MODEL_SETTINGS = ModelSettings(timeout=60)

ART_PROMPT = """\
You are a visual transcription system for Stone Island and C.P. Company
garment labels. The image may be framed tightly on the ART number, or may
show a whole label with the ART number somewhere on it.

Your task is TRANSCRIPTION ONLY. Do not identify the garment, authenticate
it, infer missing characters, validate codes, or correct apparent printing
errors.

THE ART NUMBER

The ART number is the long product/style code printed on the garment label.
It is often printed with NO "ART" prefix or any other caption — just the bare
code on a line of its own. On many Stone Island labels it sits near the
bottom of the label, among importer or distributor text such as Japanese
characters, a company name and a phone number, below the Certilogo block,
the care instructions or the EAC mark.

Do not confuse it with the other numbers printed nearby:
- phone numbers (groups of digits separated by hyphens)
- postcodes inside an address
- manufacturing dates (a month and year)
- lot or batch codes printed after it, often marked LOT — transcribe only
  the ART number, not the lot code

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

4. Report what is in THIS image. Before deciding there is no ART number,
   check the whole label for an unlabelled code of the formats above,
   especially near the bottom. If none appears — the photo shows a different
   tag, or the code is folded under, obscured or out of frame — set
   art_legible to "not_visible" and leave art_number_raw null. This is a
   normal and useful outcome, not a failure. It is distinct from
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

@cache
def get_art_agent(model: str = ART_MODEL) -> Agent:
    """Build on first use, so importing this module needs no API key.

    Cached per model so the eval harness can compare models in one run.
    """
    return Agent(model,
                 system_prompt=ART_PROMPT,
                 model_settings=MODEL_SETTINGS,
                 output_type=ArtNumberReading)


@cache
def get_details_agent(model: str = DETAILS_MODEL) -> Agent:
    return Agent(model,
                 system_prompt=DETAILS_PROMPT,
                 model_settings=MODEL_SETTINGS,
                 output_type=LabelDetails)


def transcribe_art(
    data: bytes, media_type: str, model: str = ART_MODEL
) -> ArtNumberReading:
    """Read the ART number from a photo framed on the ART number tag."""
    return get_art_agent(model).run_sync([
        "Transcribe the ART number visible in this image.",
        BinaryContent(data=data, media_type=media_type),
    ]).output


def transcribe_details(
    data: bytes, media_type: str, model: str = DETAILS_MODEL
) -> LabelDetails:
    """Read size, composition, origin and CLG from the care label photo."""
    return get_details_agent(model).run_sync([
        "Transcribe the visible care label details.",
        BinaryContent(data=data, media_type=media_type),
    ]).output


def transcribe(
    art: Optional[tuple[bytes, str]] = None,
    details: Optional[tuple[bytes, str]] = None,
) -> LabelReading:
    """Read both halves, from whichever photos the caller supplied.

    Each argument is (image_bytes, media_type). Both reads always run: each
    prefers its own photo but falls back to the other one, so a single photo
    gets read twice with two focused prompts. That is the C.P. Company case,
    where the ART number and the care details share one label. Two photos is
    the Stone Island case, where the ART number lives on a separate tag.
    """
    for_art = art or details
    for_details = details or art

    reading = LabelReading()
    if for_art is not None:
        reading.art = transcribe_art(*for_art)
    if for_details is not None:
        reading.details = transcribe_details(*for_details)
    return reading

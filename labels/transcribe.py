"""The vision half: a label photo in, a LabelReading out.

One read per listing: the ART number, which needs character-level precision
and strict anti-guessing rules. The care-label details read was removed; it is
kept at the `parked/details-read` tag.
"""

from functools import cache

from pydantic_ai import Agent, BinaryContent, ModelSettings

from labels.schemas import ArtNumberReading, LabelReading

ART_MODEL = "anthropic:claude-sonnet-5"

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

@cache
def get_art_agent(model: str = ART_MODEL) -> Agent[None, ArtNumberReading]:
    """Build on first use, so importing this module needs no API key.

    Cached per model so the eval harness can compare models in one run.
    """
    return Agent(model,
                 system_prompt=ART_PROMPT,
                 model_settings=MODEL_SETTINGS,
                 output_type=ArtNumberReading)


def transcribe_art(
    data: bytes, media_type: str, model: str = ART_MODEL
) -> ArtNumberReading:
    """Read the ART number from a photo of the ART number tag or a whole label."""
    return get_art_agent(model).run_sync([
        "Transcribe the ART number visible in this image.",
        BinaryContent(data=data, media_type=media_type),
    ]).output


def transcribe(art: tuple[bytes, str]) -> LabelReading:
    """Read the ART number from the label photo, as (image_bytes, media_type)."""
    return LabelReading(art=transcribe_art(*art))

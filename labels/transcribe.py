"""The vision half: a label photo in, a LabelReading out.

One read per listing: the ART number, which needs character-level precision
and strict anti-guessing rules. The care-label details read was removed; it is
kept at the `parked/details-read` tag.
"""

from dataclasses import dataclass
from functools import cache

from pydantic_ai import Agent, BinaryContent, ModelSettings
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.usage import RunUsage

from labels.photo import upright
from labels.schemas import ArtNumberReading, LabelReading

ART_MODEL = "anthropic:claude-sonnet-5"

# Every model setting explicit, at the value sent before it was, so setting
# them changes nothing in the request (tests/test_transcribe.py,
# TestRequestBody). max_tokens is pydantic-ai's default. The timeout is
# client-side, per HTTP attempt: 60s, not the client's 10 minutes. Thinking and
# effort aren't sent, so the model's defaults apply (SETTINGS_RECORD).
MODEL_SETTINGS = ModelSettings(timeout=60, max_tokens=4096)

# Client-side too. HTTP retries are the Anthropic SDK's, on a connection
# error, 408, 409, 429 or 5xx, each attempt with its own timeout. Output
# retries are pydantic-ai's: the model is asked again when its output fails
# validation, another paid request. Both at the libraries' defaults.
CLIENT_RETRIES = 2
OUTPUT_RETRIES = 1

NOT_SENT = "not sent (model default)"

# The run header's `model_settings`: what the request sets, and the retries
# around it.
SETTINGS_RECORD = {
    "max_tokens": MODEL_SETTINGS.get("max_tokens"),
    "thinking": NOT_SENT,
    "effort": NOT_SENT,
    "timeout": MODEL_SETTINGS.get("timeout"),
    "client_retries": CLIENT_RETRIES,
    "output_retries": OUTPUT_RETRIES,
}

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

# Sent with the photo on every call. A constant so the eval harness can fingerprint it.
ART_USER_MESSAGE = "Transcribe the ART number visible in this image."

def build_model(model: str) -> Model | str:
    """An `anthropic:` model whose client retries CLIENT_RETRIES times; any
    other model (`test`) by name, as before.

    The provider keeps its own HTTP client, which it closes and rebuilds
    around each run, as it does for a model given by name. A client passed in
    would instead be shared across the event loops of the web app's and the
    harness's threads, so the retries are set on the provider's SDK client.
    """
    provider, _, name = model.partition(":")
    if provider != "anthropic":
        return model
    anthropic = AnthropicProvider()
    anthropic.client.max_retries = CLIENT_RETRIES
    return AnthropicModel(name, provider=anthropic)


@cache
def get_art_agent(model: str = ART_MODEL) -> Agent[None, ArtNumberReading]:
    """Build on first use, so importing this module needs no API key.

    Cached per model so the eval harness can compare models in one run.
    """
    return Agent(build_model(model),
                 system_prompt=ART_PROMPT,
                 model_settings=MODEL_SETTINGS,
                 output_type=ArtNumberReading,
                 retries={"output": OUTPUT_RETRIES})


@dataclass(frozen=True)
class ArtRead:
    """One call's reading, with what the run result says about the call.

    `usage.requests` counts model requests, output retries included. The
    SDK's HTTP retries happen inside one request and aren't counted.
    """
    reading: ArtNumberReading
    model_name: str | None  # as the API reports it
    usage: RunUsage


def read_art(data: bytes, media_type: str, model: str = ART_MODEL) -> ArtRead:
    """Read the ART number from a photo of the ART number tag or a whole label.

    Every path to the model (CLI, web form, eval harness) comes through here,
    so this is where the photo is turned upright.
    """
    data, media_type = upright(data, media_type)
    result = get_art_agent(model).run_sync([
        ART_USER_MESSAGE,
        BinaryContent(data=data, media_type=media_type),
    ])
    return ArtRead(result.output, result.response.model_name, result.usage)


def transcribe_art(
    data: bytes, media_type: str, model: str = ART_MODEL
) -> ArtNumberReading:
    """The reading alone, for callers that don't record the call."""
    return read_art(data, media_type, model).reading


def transcribe(art: tuple[bytes, str]) -> LabelReading:
    """Read the ART number from the label photo, as (image_bytes, media_type)."""
    return LabelReading(art=transcribe_art(*art))

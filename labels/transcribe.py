"""The vision half: a label photo in, a LabelReading out."""

from pydantic_ai import Agent, BinaryContent

from labels.schemas import LabelReading

DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"
SYSTEM_PROMPT = """\
You transcribe Stone Island and C.P. Company garment care labels.

Your job is TRANSCRIPTION, not interpretation. Report what is physically
printed. Never infer, complete, correct or normalise a code.

THE ART NUMBER is the long product code on the label. It takes several forms:
  581540923            Stone Island, all digits
  6915G0424            Stone Island, letter in the 5th position
  0126422791           Stone Island, leading zero is significant
  K1S154100067         Stone Island, 2025 onward
  03CMOW026A           C.P. Company, 2017 onward
  14SCPUB04669         C.P. Company, transitional
  581540846/181        with a trailing colour code

CRITICAL RULES
1. Transcribe character by character, exactly as printed, including leading
   zeros, spaces and slashes. Do not tidy it up. Do not drop a leading zero.
2. The 5th character can legitimately be EITHER a digit or a letter, so 0/O
   is genuinely ambiguous there and cannot be resolved from context. The same
   applies to 1/I, 5/S, 8/B and 6/G anywhere in the code. When a character is
   ambiguous, give your best reading AND record both candidates in
   ambiguous_characters.
3. If you cannot read a character with confidence, DO NOT GUESS. Set
   art_legible to "partial" or "illegible" and use "?" for that position.
   A blank field is correct and useful. An invented code is neither.
4. These garments are garment-dyed: print is often faded, low-contrast or
   distorted by the dye process. Expect poor legibility on older pieces.
5. Report only fields you can actually see. Leave the rest null.
"""

_agent: Agent | None = None


def get_agent() -> Agent:
    """Build the agent on first use, so importing this module needs no API key."""
    global _agent
    if _agent is None:
        _agent = Agent(
            DEFAULT_MODEL,
            system_prompt=SYSTEM_PROMPT,
            output_type=LabelReading,
        )
    return _agent


def transcribe(data: bytes, media_type: str) -> LabelReading:
    """Read one label photo. Takes bytes so uploads need no temp file."""
    return get_agent().run_sync([
        "Transcribe this care label.",
        BinaryContent(data=data, media_type=media_type),
    ]).output

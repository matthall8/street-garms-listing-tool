"""Score the ART number transcription against hand-checked photos.

The decoder has had a number since day one (tests/report_art_number.py, 97.0%).
The vision half has never had one, so every claim about a prompt or a model
change has been a guess. This gives it a number.

The metric that matters most is OVERCONFIDENCE: how often the model returns
art_legible="clear" while getting the code wrong. That is the value any
auto-accept logic keys on, so its error rate is the real defect.

Photos and manifest are gitignored — label photos can carry live Certilogo
codes. See evals/manifest.example.csv for the format.

    python tests/eval_transcription.py
    python tests/eval_transcription.py --model anthropic:claude-opus-5
    python tests/eval_transcription.py --model openai:gpt-5 --workers 8
"""

import argparse
import csv
import sys

from functools import partial
from mimetypes import guess_type
from pathlib import Path
from typing import Optional

from pydantic_evals import Case, Dataset

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels.schemas import ArtNumberReading  # noqa: E402
from labels.transcribe import ART_MODEL, transcribe_art  # noqa: E402

EVALS = Path(__file__).parent.parent / "evals"
MANIFEST = EVALS / "manifest.csv"
PHOTOS = EVALS / "photos"
RESULTS = EVALS / "results"


def levenshtein(a: str, b: str) -> int:
    """Edit distance, iterative two-row. No dependency needed for strings this short."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def normalise(s: Optional[str]) -> str:
    """Compare codes ignoring spacing and case, which are not the interesting errors."""
    return "".join((s or "").split()).upper()


def load_manifest() -> list[Case]:
    with open(MANIFEST, encoding="utf-8-sig") as f:
        return [
            Case(
                name=r["photo"].strip(),
                inputs=PHOTOS / r["photo"].strip(),
                expected_output=r["expected_art_number"].strip(),
                metadata={"note": r.get("note", "").strip()},
            )
            for r in csv.DictReader(f)
            if r.get("photo", "").strip() and r.get("expected_art_number", "").strip()
        ]


def get_art_number_reading(photo_path: Path, model: str) -> ArtNumberReading:
    return transcribe_art(
        photo_path.read_bytes(),
        guess_type(photo_path.name)[0] or "image/jpeg",
        model=model
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=ART_MODEL, help=f"default: {ART_MODEL}")
    ap.add_argument("--workers", type=int, default=4,
                    help="reads at once (default: 4)")
    ap.add_argument("--limit", type=int, help="only run the first N cases")
    args = ap.parse_args()

    if not MANIFEST.is_file():
        print(f"no manifest at {MANIFEST} — skipping.")
        print("Eval photos are private and not part of this repo.")
        print("See evals/manifest.example.csv for the format.")
        return 0

    cases = load_manifest()[: args.limit]
    if not cases:
        print(f"{MANIFEST} has no usable rows.")
        return 1

    from dotenv import load_dotenv
    load_dotenv()
    
    dataset = Dataset(name="art-number-transcription", cases=cases)
    task = partial(get_art_number_reading, model=args.model)
    report = dataset.evaluate_sync(task, max_concurrency=args.workers, name=args.model)
    report.print(include_output=True, include_expected_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

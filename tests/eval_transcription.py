"""Score the ART number transcription against hand-checked photos.

The decoder has had a number since day one (tests/test_art_number.py, 97.0%).
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
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from mimetypes import guess_type
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


@dataclass
class Case:
    photo: str
    expected: str
    note: str = ""


@dataclass
class Result:
    case: Case
    got: Optional[str] = None
    legibility: str = ""
    flagged: list = field(default_factory=list)
    error: Optional[str] = None
    seconds: float = 0.0

    @property
    def skipped(self) -> bool:
        return self.error is not None

    @property
    def exact(self) -> bool:
        return normalise(self.got) == normalise(self.case.expected)

    @property
    def distance(self) -> int:
        return levenshtein(normalise(self.got), normalise(self.case.expected))

    @property
    def claimed_clear(self) -> bool:
        return self.legibility == "clear"

    @property
    def overconfident(self) -> bool:
        """Said 'clear', got it wrong, flagged nothing. The failure that matters."""
        return self.claimed_clear and not self.exact and not self.flagged


def load_manifest() -> list[Case]:
    with open(MANIFEST, encoding="utf-8-sig") as f:
        return [
            Case(
                photo=r["photo"].strip(),
                expected=r["expected_art_number"].strip(),
                note=r.get("note", "").strip(),
            )
            for r in csv.DictReader(f)
            if r.get("photo", "").strip() and r.get("expected_art_number", "").strip()
        ]


def run_case(case: Case, model: str) -> Result:
    """One read. Errors are captured, never raised — a 529 costs one case, not the run."""
    started = time.monotonic()
    path = PHOTOS / case.photo
    if not path.is_file():
        return Result(case, error=f"photo not found: {path}")
    try:
        reading = transcribe_art(
            path.read_bytes(), guess_type(path.name)[0] or "image/jpeg", model=model
        )
    except Exception as exc:
        return Result(case, error=f"{type(exc).__name__}: {exc}"[:200],
                      seconds=time.monotonic() - started)
    return Result(
        case,
        got=reading.art_number_raw,
        legibility=reading.art_legible,
        flagged=[a.model_dump() for a in reading.ambiguous_characters],
        seconds=time.monotonic() - started,
    )


def report(results: list[Result], model: str, elapsed: float) -> None:
    scored = [r for r in results if not r.skipped]
    errored = [r for r in results if r.skipped]

    print(f"\n=== {model} ===")
    print(f"{len(results)} cases, {len(scored)} scored, {len(errored)} errored, {elapsed:.1f}s")
    if not scored:
        print("nothing scored.")
        return

    exact = [r for r in scored if r.exact]
    chars = sum(len(normalise(r.case.expected)) for r in scored)
    edits = sum(r.distance for r in scored)
    clear = [r for r in scored if r.claimed_clear]
    clear_wrong = [r for r in clear if not r.exact]
    overconfident = [r for r in scored if r.overconfident]
    flagged_right = [r for r in scored if r.flagged and r.exact]

    print(f"  exact match          {len(exact)}/{len(scored)} = {len(exact)/len(scored):.1%}")
    print(f"  character error rate {edits}/{chars} = {edits/chars:.1%}" if chars else "")
    print(f"  said 'clear'         {len(clear)}/{len(scored)}")
    print(f"    ...and was wrong   {len(clear_wrong)}/{len(clear)}" if clear else "")
    print(f"  OVERCONFIDENT        {len(overconfident)}/{len(scored)} = "
          f"{len(overconfident)/len(scored):.1%}   <- clear, wrong, unflagged")
    print(f"  flagged but correct  {len(flagged_right)}/{len(scored)}   <- review-queue noise")

    bad = [r for r in scored if not r.exact]
    if bad:
        print("\n  -- misses --")
        for r in sorted(bad, key=lambda r: -r.distance):
            mark = "!!" if r.overconfident else "  "
            print(f"  {mark} {r.case.photo:26} got {r.got!r}")
            print(f"       want {r.case.expected!r}  [{r.legibility}, "
                  f"{len(r.flagged)} flagged, {r.distance} edits] {r.case.note}")
    for r in errored:
        print(f"  ERROR {r.case.photo:26} {r.error}")


def save(results: list[Result], model: str) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"{stamp}-{model.replace(':', '_').replace('/', '_')}.json"
    out.write_text(json.dumps([
        {
            "photo": r.case.photo, "expected": r.case.expected, "got": r.got,
            "legibility": r.legibility, "flagged": r.flagged, "error": r.error,
            "exact": None if r.skipped else r.exact,
            "distance": None if r.skipped else r.distance,
            "seconds": round(r.seconds, 2),
        }
        for r in results
    ], indent=2))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=ART_MODEL, help=f"default: {ART_MODEL}")
    ap.add_argument("--workers", type=int, default=4,
                    help="parallel reads; run_sync is safe in worker threads (default: 4)")
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

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda c: run_case(c, args.model), cases))
    elapsed = time.monotonic() - started

    report(results, args.model, elapsed)
    print(f"\nwrote {save(results, args.model).relative_to(EVALS.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

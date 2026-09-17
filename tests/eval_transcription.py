"""Score the ART number transcription against hand-checked photos.

The decoder has had a number since day one (tests/report_art_number.py, 97.0%).
The vision half has never had one, so every claim about a prompt or a model
change has been a guess. This gives it a number.

The metric that matters most is OVERCONFIDENCE: how often the model returns
art_legible="clear" while getting the code wrong. That is the value any
auto-accept logic keys on, so its error rate is the real defect.

Photos, manifest and results are gitignored — label photos can carry live
Certilogo codes. See evals/README.md for setup and how to read the report.

    python tests/eval_transcription.py --model test          # offline, no API calls
    python tests/eval_transcription.py --repeat 3 --note "baseline: current prompt"
    python tests/eval_transcription.py --repeat 3 --note "whole-label search" \\
        --baseline evals/results/<baseline>.json
    python tests/eval_transcription.py --model anthropic:claude-opus-5 --no-save
"""

import argparse
import csv
import hashlib
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from mimetypes import guess_type
from pathlib import Path
from typing import Optional

from pydantic import ValidationError
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, ReportEvaluator, ReportEvaluatorContext
from pydantic_evals.reporting import EvaluationReport, EvaluationReportAdapter
from pydantic_evals.reporting.analyses import ScalarResult

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels.schemas import ArtNumberReading  # noqa: E402
from labels.transcribe import ART_MODEL, ART_PROMPT, transcribe_art  # noqa: E402

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
class CorrectArtNumber(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> dict:
        expected_art_number = normalise(ctx.expected_output)
        detected_art_number = normalise(ctx.output.art_number_raw)
        exact = expected_art_number == detected_art_number
        cer = levenshtein(detected_art_number, expected_art_number) / len(expected_art_number)
        legibility = ctx.output.art_legible
        return {
            "exact": exact,
            "cer": cer,
            "legibility": legibility,
        }

def percent(part: list, whole: list) -> float:
    return 100 * len(part) / len(whole)


@dataclass
class ConfidenceRates(ReportEvaluator):
    """Whole-run rates that the per-case averages can't show."""

    def evaluate(self, ctx: ReportEvaluatorContext) -> list[ScalarResult]:
        cases = ctx.report.cases
        if not cases:
            return []

        clear = [r for r in cases if r.output.art_legible == "clear"]
        flagged = [r for r in cases if r.output.ambiguous_characters]
        clear_but_wrong = [r for r in clear if not r.assertions["exact"].value]
        overconfident = [
            r for r in clear_but_wrong if not r.output.ambiguous_characters
        ]
        flagged_right = [r for r in flagged if r.assertions["exact"].value]

        results = [
            ScalarResult(
                title="overconfident",
                value=percent(overconfident, cases),
                unit="%",
            ),
            ScalarResult(
                title="flagged but correct",
                value=percent(flagged_right, cases),
                unit="%",
            ),
        ]
        if clear:  # a prompt change could stop the model saying "clear" at all
            results.append(
                ScalarResult(
                    title="clear but wrong",
                    value=percent(clear_but_wrong, clear),
                    unit="%",
                )
            )
        return results


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

def git(*args: str) -> str:
    """Output of a git command run in the repo, or "" if it fails."""
    result = subprocess.run(
        ["git", *args], cwd=EVALS.parent, capture_output=True, text=True
    )
    return result.stdout.strip()


def fingerprint(data: bytes) -> str:
    """Short hash: enough to tell two versions apart, not a security measure."""
    return hashlib.sha256(data).hexdigest()[:12]


def run_metadata(args: argparse.Namespace) -> dict:
    """What produced this run, so a saved report can be traced back to it."""
    return {
        "model": args.model,
        "commit": git("rev-parse", "--short", "HEAD"),
        "dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "prompt": fingerprint(ART_PROMPT.encode()),
        "manifest": fingerprint(MANIFEST.read_bytes()),
        "limit": args.limit,
        "repeat": args.repeat,
        "note": args.note,
    }

def save(report, model) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"{stamp}-{model.replace(':', '_').replace('/', '_')}.json"
    path.write_bytes(EvaluationReportAdapter.dump_json(report, indent=2))
    return path


def load_baseline(path: Path) -> Optional[EvaluationReport]:
    """A report saved by an earlier run, to diff this one against.

    Prints why and returns None if the file is missing or isn't a saved report.
    """
    if not path.is_file():
        print(f"no baseline at {path}")
        return None
    try:
        return EvaluationReportAdapter.validate_json(path.read_bytes())
    except ValidationError:
        print(f"{path} is not a saved eval report. Results from before the "
              "pydantic-evals port use an older format and can't be baselines.")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--model", default=ART_MODEL, help=f"default: {ART_MODEL}")
    ap.add_argument("--workers", type=int, default=4,
                    help="reads at once (default: 4)")
    ap.add_argument("--limit", type=int, help="only run the first N cases")
    ap.add_argument("--repeat", type=int, default=1,
                    help="read every photo N times (default: 1)")
    ap.add_argument("--note", default="",
                    help="what this run is testing, saved with the results")
    ap.add_argument("--no-save", action="store_true",
                    help="don't write the report to evals/results/")
    ap.add_argument("--baseline", type=Path,
                    help="a saved report in evals/results/ to compare this run against")
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

    # Loaded before any reads, so a bad path fails fast instead of after the API calls.
    baseline = None
    if args.baseline:
        baseline = load_baseline(args.baseline)
        if baseline is None:
            return 1
        baseline_repeat = (baseline.experiment_metadata or {}).get("repeat", 1)
        if baseline_repeat != args.repeat:
            # Repeats rename cases ("photo [1/3]"), and the diff matches cases by name.
            print(f"warning: baseline used --repeat {baseline_repeat}, this run uses "
                  f"--repeat {args.repeat}, so cases won't line up in the diff")

    from dotenv import load_dotenv
    load_dotenv()

    dataset = Dataset(name="art-number-transcription",
                      cases=cases, evaluators=[CorrectArtNumber()],
                      report_evaluators=[ConfidenceRates()])
    task = partial(get_art_number_reading, model=args.model)
    report = dataset.evaluate_sync(
        task,
        max_concurrency=args.workers,
        repeat=args.repeat,
        name=args.model,
        metadata=run_metadata(args),
    )
    report.print(include_output=True, include_expected_output=True, baseline=baseline)
    if not args.no_save:
        print(f"\nwrote {save(report, args.model).relative_to(EVALS.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

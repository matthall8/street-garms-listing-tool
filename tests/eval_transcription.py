"""Score the ART number transcription against hand-checked photos.

The decoder has had a number since day one (tests/report_art_number.py, 97.0%).
The vision half has never had one, so every claim about a prompt or a model
change has been a guess. This gives it a number.

The headline metric is OVERCONFIDENCE: how often the model returns
art_legible="clear" while getting the code wrong. It is NOT the rate at which a
wrong listing gets published — that gate is needs_review in labels/pipeline.py,
which also consults the decoder and the catalogue. See evals/README.md for why
this number is wrong in both directions and how to get the publish-gate one.

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
from collections import defaultdict
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
from pydantic_evals.reporting.analyses import ScalarResult, TableResult

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels.schemas import ArtNumberReading  # noqa: E402
from labels.transcribe import ART_MODEL, ART_PROMPT, transcribe_art  # noqa: E402

EVALS = Path(__file__).parent.parent / "evals"
MANIFEST = EVALS / "manifest.csv"
NO_ART_NUMBER = "NONE"
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
        expected = normalise(ctx.expected_output)
        detected = normalise(ctx.output.art_number_raw)
        is_negative = expected == NO_ART_NUMBER

        result = {
            "legibility": ctx.output.art_legible,
            "kind": "negative" if is_negative else "positive"
        }
        
        if is_negative:
            # Correct means no code came back at all. Saying "illegible" rather
            # than "not_visible" is a lesser error, visible via the legibility label.
            # An all-"?" read invents nothing either: ART_PROMPT rule 3 tells the
            # model to write "?" for characters it cannot read, so that is the
            # honest answer here, not a fabrication. Any real character surviving
            # the strip means it claimed to read something that is not there.
            result["exact"] = not detected.strip("?")
        else:
            result["exact"] = expected == detected
            result["cer"] = levenshtein(detected, expected) / len(expected)
        return result

def percent(part: list, whole: list) -> float:
    return 100 * len(part) / len(whole)


# Per-read tests, shared by the whole-run rates and the per-photo table so the
# two can never count differently.

def was_missed(r) -> bool:
    """Judged on what came back, not on the legibility label: an all-"?" read
    found the code and is an attempt; null or blank is a miss whether the model
    called it not_visible or illegible."""
    return not normalise(r.output.art_number_raw)


def was_overconfident(r) -> bool:
    return (r.output.art_legible == "clear"
            and not r.assertions["exact"].value
            and not r.output.ambiguous_characters)


def was_fabricated_clear(r) -> bool:
    return not r.assertions["exact"].value and r.output.art_legible == "clear"


def scored_cases(ctx: ReportEvaluatorContext) -> list:
    # A case whose EVALUATOR raised keeps its row but carries no assertions,
    # so exclude it rather than KeyError. (A case whose task raised goes to
    # report.failures and never reaches here.)
    return [r for r in ctx.report.cases if "exact" in r.assertions]


@dataclass
class ConfidenceRates(ReportEvaluator):
    """Whole-run rates that the per-case averages can't show."""
    def evaluate(self, ctx: ReportEvaluatorContext) -> list[ScalarResult]:
        scored = scored_cases(ctx)
        if not scored:
            return []

        positives = [r for r in scored if r.labels["kind"].value == "positive"]
        negatives = [r for r in scored if r.labels["kind"].value == "negative"]
        results = []

        if positives:
            missed = [r for r in positives if was_missed(r)]
            clear = [r for r in positives if r.output.art_legible == "clear"]
            flagged = [r for r in positives if r.output.ambiguous_characters]
            clear_but_wrong = [r for r in clear if not r.assertions["exact"].value]
            overconfident = [r for r in positives if was_overconfident(r)]
            flagged_right = [r for r in flagged if r.assertions["exact"].value]

            results += [
                ScalarResult(title="missed",
                                value=percent(missed, positives), unit="%"),
                ScalarResult(title="overconfident",
                                value=percent(overconfident, positives), unit="%"),
                ScalarResult(title="flagged but correct",
                                value=percent(flagged_right, positives), unit="%"),
            ]
            if clear:
                results.append(ScalarResult(title="clear but wrong",
                                            value=percent(clear_but_wrong, clear), unit="%"))

        if negatives:
            fabricated = [r for r in negatives if not r.assertions["exact"].value]
            fabricated_clear = [r for r in negatives if was_fabricated_clear(r)]
            results += [
                ScalarResult(title="fabricated on no-code photos",
                                value=percent(fabricated, negatives), unit="%"),
                ScalarResult(title="fabricated and declared clear",
                                value=percent(fabricated_clear, negatives), unit="%"),
            ]

        return results


@dataclass
class PerPhotoCounts(ReportEvaluator):
    """Counts per photo across --repeat: the unit the decision rule in TODO.md
    is judged on, so nobody has to tally `photo [k/3]` rows by hand.

    `reads` is how many reads were scored. A failed read is left out, so
    `reads` below --repeat shows exactly which photo lost one.
    """
    def evaluate(self, ctx: ReportEvaluatorContext) -> list[TableResult]:
        by_photo = defaultdict(list)
        for r in scored_cases(ctx):
            by_photo[r.source_case_name or r.name].append(r)
        if not by_photo:
            return []

        rows = []
        for photo in sorted(by_photo):
            reads = by_photo[photo]
            kind = reads[0].labels["kind"].value
            positive = kind == "positive"

            def count(test):
                return sum(1 for r in reads if test(r))

            rows.append([
                photo, kind, len(reads),
                count(lambda r: r.assertions["exact"].value),
                count(was_missed) if positive else None,
                count(was_overconfident) if positive else None,
                None if positive else count(was_fabricated_clear),
            ])
        return [TableResult(
            title="per photo",
            columns=["photo", "kind", "reads", "exact", "missed",
                     "overconfident", "fabricated clear"],
            rows=rows,
        )]


def load_manifest() -> list[Case]:
    cases = []
    with open(MANIFEST, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            photo = r.get("photo", "").strip()
            expected = r.get("expected_art_number", "").strip()
            if not photo:
                continue
            if not expected:
                print(f"skipping {photo}: no expected_art_number "
                      f"(use {NO_ART_NUMBER} if the photo has no ART number)")
                continue
            cases.append(Case(
                name=photo,
                inputs=PHOTOS / photo,
                expected_output=expected,
                metadata={"note": r.get("note", "").strip()},
            ))
    return cases

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

    all_cases = load_manifest()
    cases = all_cases[: args.limit]
    if not cases:
        print(f"{MANIFEST} has no usable rows.")
        return 1

    # --limit truncates, so it can cut every negative case off the end without
    # saying so. The fabrication rates then vanish from the report rather than
    # reading zero, which looks like a clean run instead of an unmeasured one.
    def negatives(rows):
        return [c for c in rows if normalise(c.expected_output) == NO_ART_NUMBER]

    if negatives(all_cases) and not negatives(cases):
        print(f"warning: --limit {args.limit} excluded every negative case, "
              "so this run cannot measure fabrication")

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
                      report_evaluators=[ConfidenceRates(), PerPhotoCounts()])
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

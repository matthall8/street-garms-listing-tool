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
    python tests/eval_transcription.py --replay evals/results/<report>.json   # no API calls
"""

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from importlib.metadata import PackageNotFoundError, version
from mimetypes import guess_type
from pathlib import Path
from typing import NamedTuple

from pydantic import ValidationError
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import (
    Evaluator,
    EvaluatorContext,
    ReportEvaluator,
    ReportEvaluatorContext,
)
from pydantic_evals.reporting import EvaluationReport, EvaluationReportAdapter
from pydantic_evals.reporting.analyses import ScalarResult, TableResult

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels.pipeline import from_reading
from labels.schemas import ArtNumberReading
from labels.transcribe import ART_MODEL, ART_PROMPT, ART_USER_MESSAGE, transcribe_art

EVALS = Path(__file__).parent.parent / "evals"
MANIFEST = EVALS / "manifest.csv"
NO_ART_NUMBER = "NONE"
UNKNOWN = "UNKNOWN"  # a marker for the run 0 columns, never a legacy value
PHOTOS = EVALS / "photos"
RESULTS = EVALS / "results"
# Between the code and the model, or scoring what comes back.
PACKAGES = ("pydantic-ai", "anthropic", "pydantic", "pydantic-evals")


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


def normalise(s: str | None) -> str:
    """Compare codes ignoring spacing and case, which are not the interesting errors."""
    return "".join((s or "").split()).upper()


@dataclass
class CorrectArtNumber(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> dict:
        # A base-only row has no legacy value: no `exact`, so scored_cases
        # drops it. Scored, its cer would divide by zero.
        if ctx.expected_output is None:
            return {}
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


def base_kind_of(metadata: dict | None) -> str:
    """From the manifest value, as `kind` is, so a photo with no scored read
    still has one."""
    expected = normalise((metadata or {}).get("expected_art_base"))
    if not expected:
        return "unlabelled"
    if expected == UNKNOWN:
        return "unknown"
    return "negative" if expected == NO_ART_NUMBER else "positive"


@dataclass
class CorrectArtBase(Evaluator):
    """Base-exact (ADR-0002): the pipeline's art_base against expected_art_base.

    Runs from_reading(), the app's own code after transcription, so a live run
    and a replay of saved reads score the same way. `base_kind` is a string so
    it stays a label; `base_exact` is left off rows with no usable base.
    """
    def evaluate(self, ctx: EvaluatorContext) -> dict:
        kind = base_kind_of(ctx.metadata)
        if kind not in ("positive", "negative"):
            return {"base_kind": kind}

        art_base = normalise(from_reading(ctx.output).art_base)
        if kind == "negative":
            return {"base_kind": kind, "base_exact": not art_base}
        expected = normalise((ctx.metadata or {})["expected_art_base"])
        return {"base_kind": kind, "base_exact": art_base == expected}


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


def photo_of(r) -> str:
    """The photo a read came from: at --repeat 1 pydantic-evals sets no
    source_case_name, and the case name is the photo."""
    return r.source_case_name or r.name


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
    """Counts per photo across --repeat: the unit the decision rule in ADR-0006
    is judged on, so nobody has to tally `photo [k/3]` rows by hand.

    `reads` is how many reads were scored. A failed read is left out, so
    `reads` below --repeat shows exactly which photo lost one — including a
    photo that lost every read, which still gets a row with `reads` 0.
    """
    def evaluate(self, ctx: ReportEvaluatorContext) -> list[TableResult]:
        # Every photo the run touched, failed reads included, so none can drop
        # out of the table. Kind comes from the manifest value, as it does in
        # CorrectArtNumber, because a photo with no scored read has no label.
        # A base-only row has no legacy value, so no row here.
        expected = {photo_of(r): r.expected_output
                    for r in [*ctx.report.cases, *ctx.report.failures]
                    if r.expected_output is not None}
        if not expected:
            return []
        by_photo = defaultdict(list)
        for r in scored_cases(ctx):
            by_photo[photo_of(r)].append(r)

        rows = []
        for photo in sorted(expected):
            reads = by_photo[photo]
            positive = normalise(expected[photo]) != NO_ART_NUMBER
            kind = "positive" if positive else "negative"

            def count(test, reads=reads):
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


class PhotoBase(NamedTuple):
    photo: str
    garment: str
    side: str
    kind: str
    reads: int          # scored reads
    right: int          # of those, base-exact
    correct: bool | None  # None when the photo has no usable base


def needed(runs: int) -> int:
    """Correct reads a photo needs: a majority of its runs, so 2 of 3."""
    return runs // 2 + 1


@dataclass
class BaseExactCounts(ReportEvaluator):
    """Base-exact per photo, the gate's unit (ADR-0002: a test garment-side is
    one photo). A photo is correct when a majority of its --repeat runs read
    the right base. A failed read is one of those runs, so it counts as wrong.

    Garment-sides are counts only: dev has several photos of some sides,
    such as second shots, so no rule joins its photos into one verdict.
    """
    def evaluate(self, ctx: ReportEvaluatorContext) -> list[TableResult]:
        # Every run of a photo, failed ones included: their number is --repeat.
        runs = defaultdict(list)
        for r in [*ctx.report.cases, *ctx.report.failures]:
            runs[photo_of(r)].append(r)
        if not runs:
            return []

        photos, sides = [], defaultdict(lambda: [0, 0, 0])
        for photo in sorted(runs):
            metadata = runs[photo][0].metadata or {}
            kind = base_kind_of(metadata)
            scored = [r for r in ctx.report.cases
                      if photo_of(r) == photo and "base_exact" in r.assertions]
            right = sum(1 for r in scored if r.assertions["base_exact"].value)
            correct = (right >= needed(len(runs[photo]))
                       if kind in ("positive", "negative") else None)
            p = PhotoBase(photo, metadata.get("garment", ""), metadata.get("side", ""),
                          kind, len(scored), right, correct)
            photos.append(p)

            side = sides[(p.garment, p.side)]
            side[0] += 1
            side[1] += bool(correct)
            side[2] += correct is None

        def of(kind):
            return [p for p in photos if p.kind == kind]

        def rate(title, n, total):
            return [title, n, total, round(100 * n / total, 1) if total else None]

        positives, negatives = of("positive"), of("negative")
        repeat = max(len(r) for r in runs.values())
        return [
            TableResult(
                title=f"base-exact (correct: at least {needed(repeat)} of {repeat} reads)",
                columns=["", "n", "of", "%"],
                rows=[
                    rate("photos correct", sum(1 for p in positives if p.correct),
                         len(positives)),
                    rate("reads correct", sum(p.right for p in positives),
                         sum(p.reads for p in positives)),
                    rate("negatives correct", sum(1 for p in negatives if p.correct),
                         len(negatives)),
                    rate("left out: unknown", len(of("unknown")), len(photos)),
                    rate("left out: unlabelled", len(of("unlabelled")), len(photos)),
                ],
            ),
            TableResult(
                title="base per photo",
                columns=["photo", "garment", "side", "kind", "reads", "correct reads",
                         "correct"],
                rows=[[*p[:6], None if p.correct is None else "✔" if p.correct else "✗"]
                      for p in photos],
            ),
            TableResult(
                title="garment-sides",
                columns=["garment", "side", "photos", "correct", "left out"],
                rows=[[g, sd, *counts] for (g, sd), counts in sorted(sides.items())],
            ),
        ]


def load_manifest() -> list[Case]:
    cases = []
    with open(MANIFEST, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            photo = r.get("photo", "").strip()
            expected = r.get("expected_art_number", "").strip()
            art_base = r.get("expected_art_base", "").strip()
            if not photo:
                continue
            # UNKNOWN is never a legacy value: scored, it would be a code no
            # read can match. Treat it as blank, and say so below.
            legacy_unknown = normalise(expected) == UNKNOWN
            if legacy_unknown:
                expected = ""
            if not expected and normalise(art_base) in ("", UNKNOWN):
                print(f"skipping {photo}: no expected_art_number or expected_art_base "
                      f"(use {NO_ART_NUMBER} if the photo has no ART number)")
                continue
            if legacy_unknown:
                print(f"{photo}: {UNKNOWN} in expected_art_number is not scored "
                      "(leave it blank instead)")
            # The base is kept as written, UNKNOWN and blank included: the
            # base-exact scorer counts those, so the loader doesn't.
            cases.append(Case(
                name=photo,
                inputs=PHOTOS / photo,
                expected_output=expected or None,
                metadata={
                    "id": r.get("id", "").strip(),
                    "note": r.get("note", "").strip(),
                    "garment": r.get("garment", "").strip(),
                    "side": r.get("side", "").strip(),
                    "expected_art_base": art_base,
                },
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


def versions() -> str:
    """Python and PACKAGES as installed, so a run shows its environment
    matched the commit's uv.lock. A missing package is recorded, not fatal."""
    def installed(package: str) -> str:
        try:
            return version(package)
        except PackageNotFoundError:
            return "not installed"
    return ", ".join([f"python {platform.python_version()}",
                      *(f"{p} {installed(p)}" for p in PACKAGES)])


def run_metadata(args: argparse.Namespace) -> dict:
    """What produced this run, so a saved report can be traced back to it."""
    return {
        "model": args.model,
        "commit": git("rev-parse", "--short", "HEAD"),
        "dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "prompt": fingerprint(ART_PROMPT.encode()),
        "user_message": fingerprint(ART_USER_MESSAGE.encode()),
        # The output schema the model sees: field descriptions and docstrings included.
        "schema": fingerprint(
            json.dumps(ArtNumberReading.model_json_schema(), sort_keys=True).encode()),
        "versions": versions(),
        "manifest": fingerprint(MANIFEST.read_bytes()),
        "limit": args.limit,
        "repeat": args.repeat,
        "note": args.note,
    }

def id_problems(cases: list[Case]) -> list[str]:
    """Blank or repeated manifest ids among the cases run: the photo record
    is keyed by id."""
    ids = [(c.metadata or {}).get("id", "") for c in cases]
    problems = [f"{c.name} has no id" for c, i in zip(cases, ids, strict=True) if not i]
    problems += [f"id {i} is on more than one row"
                 for i in sorted({i for i in ids if i and ids.count(i) > 1})]
    return problems


def photo_metadata(cases: list[Case]) -> dict:
    """The photos this run sends, by manifest id: a sha256 each, so one can be
    checked by hand, and one fingerprint over them all. Hashed once per photo,
    whatever --repeat is. A missing photo is None; its read fails as before."""
    hashes = {}
    for c in cases:
        path = Path(c.inputs)
        hashes[(c.metadata or {})["id"]] = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
    return {"photos": fingerprint(json.dumps(hashes, sort_keys=True).encode()),
            "photo_hashes": hashes}


def replay_metadata(args: argparse.Namespace, source: EvaluationReport) -> dict:
    """The scoring run's commit and manifest; the reads' model, prompt, user
    message, schema, photos and library versions. A source from before a field
    existed gives None."""
    read_by = source.experiment_metadata or {}
    return {
        **run_metadata(args),
        "model": read_by.get("model"),
        "prompt": read_by.get("prompt"),
        "user_message": read_by.get("user_message"),
        "schema": read_by.get("schema"),
        "photos": read_by.get("photos"),
        "photo_hashes": read_by.get("photo_hashes"),
        "versions": read_by.get("versions"),
        "repeat": read_by.get("repeat", 1),
        "replay_of": args.replay.name,
    }


def replay_task(source: EvaluationReport, cases: list[Case]):
    """A saved report's reads as a task, so the same evaluators score them
    with no API call. Each call returns the photo's next saved read; once a
    photo's reads run out (one failed in the source run) the call fails, as
    the read did. Expected values come from today's manifest, by photo.
    """
    saved = defaultdict(list)
    for f in source.failures:
        saved.setdefault(photo_of(f), [])   # so a photo that lost every read is a case
    for r in sorted(source.cases, key=lambda r: r.name):
        saved[photo_of(r)].append(ArtNumberReading.model_validate(r.output))

    manifest = {c.name for c in cases if c.name}
    for photo in sorted(set(saved) - manifest):
        print(f"not scored: {photo} has saved reads but no usable manifest row")
    for photo in sorted(manifest - set(saved)):
        print(f"not scored: {photo} has no saved reads")

    def task(photo_path: Path) -> ArtNumberReading:
        reads = saved[photo_path.name]
        if not reads:
            raise LookupError("no saved read left: it failed in the source run")
        return reads.pop(0)

    return task, [c for c in cases if c.name in saved]


def baseline_warnings(baseline: dict, run: dict) -> list[str]:
    """Where the baseline's output schema, user message, library versions or
    photos differ from this run's. Any of them changing alongside the change
    under test makes the diff meaningless, and none shows in a prompt or model
    comparison: a library upgrade can change what's sent without moving the
    schema. Not `prompt` or `model`: a comparison usually changes one on purpose."""
    warnings = []
    for what, key in [("output schema", "schema"), ("user message", "user_message"),
                      ("versions line", "versions")]:
        if baseline.get(key) is None:
            warnings.append(f"warning: the {what} is not recorded in the baseline")
        elif baseline[key] != run[key]:
            warnings.append(f"warning: the {what} differs from the baseline's "
                            f"({baseline[key]} -> {run[key]})")

    then, now = baseline.get("photo_hashes"), run["photo_hashes"]
    if then is None:
        warnings.append("warning: the photo record is not recorded in the baseline")
        return warnings
    for what, ids in [
        ("changed", [i for i in now if i in then and now[i] != then[i]]),
        ("only in the baseline", [i for i in then if i not in now]),
        ("only in this run", [i for i in now if i not in then]),
    ]:
        if ids:
            warnings.append(f"warning: photos {what}: {', '.join(sorted(ids))}")
    return warnings


def printable(report: EvaluationReport) -> EvaluationReport:
    """The report without photo_hashes, which would fill the printed header.
    The saved report keeps them."""
    metadata = {k: v for k, v in (report.experiment_metadata or {}).items()
                if k != "photo_hashes"}
    return replace(report, experiment_metadata=metadata)


def save(report, model) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"{stamp}-{model.replace(':', '_').replace('/', '_')}.json"
    path.write_bytes(EvaluationReportAdapter.dump_json(report, indent=2))
    return path


def load_baseline(path: Path) -> EvaluationReport | None:
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
              "pydantic-evals port use an older format and can't be baselines "
              "or replayed.")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # --model and --repeat default to None so --replay can tell they were passed.
    ap.add_argument("--model", help=f"default: {ART_MODEL}")
    ap.add_argument("--workers", type=int, default=4,
                    help="reads at once (default: 4); ignored by --replay, which is serial")
    ap.add_argument("--limit", type=int, help="only run the first N cases")
    ap.add_argument("--repeat", type=int,
                    help="read every photo N times (default: 1)")
    ap.add_argument("--note", default="",
                    help="what this run is testing, saved with the results")
    ap.add_argument("--no-save", action="store_true",
                    help="don't write the report to evals/results/")
    ap.add_argument("--baseline", type=Path,
                    help="a saved report in evals/results/ to compare this run against")
    ap.add_argument("--replay", type=Path,
                    help="rescore a saved report's reads with this code, no API call")
    args = ap.parse_args()

    if args.replay:
        passed = [flag for flag, value in [
            ("--model", args.model), ("--repeat", args.repeat), ("--limit", args.limit),
            ("--baseline", args.baseline), ("--no-save", args.no_save)] if value]
        if passed:
            # The reads fix the model and repeat, and every replay is saved.
            ap.error(f"--replay can't be used with {', '.join(passed)}")
    args.model = args.model or ART_MODEL
    args.repeat = args.repeat or 1

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

    if args.replay:
        source = load_baseline(args.replay)
        if source is None:
            return 1
        metadata = replay_metadata(args, source)
        if metadata["dirty"]:
            print("warning: uncommitted changes, so the recorded commit isn't "
                  "the code that scored this replay")
        task, cases = replay_task(source, cases)
        # Serial, so each photo's saved reads are scored in saved order.
        workers, repeat, name = 1, metadata["repeat"], f"{metadata['model']}-replay"
    else:
        if problems := id_problems(cases):
            print("\n".join(problems))
            print("every row run needs its own id: the photo record is keyed by it")
            return 1
        from dotenv import load_dotenv
        load_dotenv()
        metadata = {**run_metadata(args), **photo_metadata(cases)}
        if baseline:
            for warning in baseline_warnings(baseline.experiment_metadata or {}, metadata):
                print(warning)
        task = partial(get_art_number_reading, model=args.model)
        workers, repeat, name = args.workers, args.repeat, args.model

    dataset = Dataset(name="art-number-transcription",
                      cases=cases, evaluators=[CorrectArtNumber(), CorrectArtBase()],
                      report_evaluators=[ConfidenceRates(), PerPhotoCounts(),
                                         BaseExactCounts()])
    report = dataset.evaluate_sync(
        task,
        max_concurrency=workers,
        repeat=repeat,
        name=name,
        metadata=metadata,
    )
    printable(report).print(include_output=True, include_expected_output=True,
                            baseline=printable(baseline) if baseline else None)
    if not args.no_save:
        print(f"\nwrote {save(report, name).relative_to(EVALS.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

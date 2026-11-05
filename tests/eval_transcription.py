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
    python tests/eval_transcription.py --holdout --check     # the test-set checks, no API calls
    python tests/eval_transcription.py --holdout --note "gate attempt"   # totals only
"""

import argparse
import csv
import hashlib
import io
import json
import platform
import subprocess
import sys
from collections import defaultdict
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from importlib.metadata import PackageNotFoundError, version
from mimetypes import guess_type
from pathlib import Path
from typing import NamedTuple

from pydantic import ValidationError
from pydantic_evals import Case, Dataset, increment_eval_metric, set_eval_attribute
from pydantic_evals.evaluators import (
    Evaluator,
    EvaluatorContext,
    ReportEvaluator,
    ReportEvaluatorContext,
)
from pydantic_evals.reporting import EvaluationReport, EvaluationReportAdapter
from pydantic_evals.reporting.analyses import ScalarResult, TableResult

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hooks.check_private import HOLDOUT_LEDGER_HEADER, last_ledger_md5
from labels.photo import upright
from labels.pipeline import from_reading
from labels.schemas import ArtNumberReading
from labels.transcribe import (
    ART_MODEL,
    ART_PROMPT,
    ART_USER_MESSAGE,
    SETTINGS_RECORD,
    ArtRead,
    read_art,
)

EVALS = Path(__file__).parent.parent / "evals"
MANIFEST = EVALS / "manifest.csv"
NO_ART_NUMBER = "NONE"
UNKNOWN = "UNKNOWN"  # a marker for the run 0 columns, never a legacy value
PHOTOS = EVALS / "photos"
RESULTS = EVALS / "results"
BASELINES = EVALS / "BASELINES.md"
# The held-out set (ADR-0002): run only by --holdout, which prints totals only.
HOLDOUT_MANIFEST = EVALS / "holdout" / "manifest.csv"
HOLDOUT_PHOTOS = EVALS / "holdout" / "photos"
HOLDOUT_REPEAT, HOLDOUT_WORKERS = 3, 1   # the eval run procedure's settings
MIN_SIDES = 15      # the gate never runs on fewer garment-sides (ADR-0002)
GATE_PERCENT = 80   # of garment-sides correct, rounded up (ADR-0002)
# Between the code and the model, or scoring what comes back.
PACKAGES = ("pydantic-ai", "anthropic", "pydantic", "pydantic-evals", "pillow")
# From each read's run result: model requests (output retries included, the
# SDK's HTTP retries not) and tokens.
USAGE_FIELDS = ("requests", "input_tokens", "output_tokens", "cache_read_tokens",
                "cache_write_tokens")


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
    runs: int           # every run, failed ones included: --repeat


def needed(runs: int) -> int:
    """Correct reads a photo needs: a majority of its runs, so 2 of 3."""
    return runs // 2 + 1


def bases_by_photo(report: EvaluationReport) -> list[PhotoBase]:
    """Base-exact per photo, sorted by photo. A photo is correct when a
    majority of its --repeat runs read the right base; a failed read is one
    of those runs, so it counts as wrong."""
    runs = defaultdict(list)
    for r in [*report.cases, *report.failures]:
        runs[photo_of(r)].append(r)

    photos = []
    for photo in sorted(runs):
        metadata = runs[photo][0].metadata or {}
        kind = base_kind_of(metadata)
        scored = [r for r in report.cases
                  if photo_of(r) == photo and "base_exact" in r.assertions]
        right = sum(1 for r in scored if r.assertions["base_exact"].value)
        correct = (right >= needed(len(runs[photo]))
                   if kind in ("positive", "negative") else None)
        photos.append(PhotoBase(photo, metadata.get("garment", ""), metadata.get("side", ""),
                                kind, len(scored), right, correct, len(runs[photo])))
    return photos


@dataclass
class BaseExactCounts(ReportEvaluator):
    """Base-exact per photo, the gate's unit (ADR-0002: a test garment-side is
    one photo). A photo is correct when a majority of its --repeat runs read
    the right base. A failed read is one of those runs, so it counts as wrong.

    Garment-sides are counts only: dev has several photos of some sides,
    such as second shots, so no rule joins its photos into one verdict.
    """
    def evaluate(self, ctx: ReportEvaluatorContext) -> list[TableResult]:
        photos = bases_by_photo(ctx.report)
        if not photos:
            return []

        sides = defaultdict(lambda: [0, 0, 0])
        for p in photos:
            side = sides[(p.garment, p.side)]
            side[0] += 1
            side[1] += bool(p.correct)
            side[2] += p.correct is None

        def of(kind):
            return [p for p in photos if p.kind == kind]

        def rate(title, n, total):
            return [title, n, total, round(100 * n / total, 1) if total else None]

        positives, negatives = of("positive"), of("negative")
        repeat = max(p.runs for p in photos)
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


def cell(r: dict, column: str) -> str:
    """A manifest cell, stripped; "" for a column the row lacks."""
    return (r.get(column) or "").strip()


def read_rows(manifest: Path) -> list[dict]:
    with open(manifest, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def legacy_value(r: dict) -> str:
    """expected_art_number. UNKNOWN is never a legacy value: scored, it would
    be a code no read can match, so it reads as blank."""
    expected = cell(r, "expected_art_number")
    return "" if normalise(expected) == UNKNOWN else expected


def loader_skips(r: dict) -> bool:
    """A row load_manifest drops: no photo, or nothing to score."""
    return not cell(r, "photo") or (
        not legacy_value(r) and normalise(cell(r, "expected_art_base")) in ("", UNKNOWN))


def load_manifest(manifest: Path | None = None, photos: Path | None = None,
                  say=print) -> list[Case]:
    """The cases in a manifest, photos named from `photos`. The dev set by
    default, looked up at call time so tests can patch them. `say` gets the
    warnings, which name photos: --holdout passes one that drops them, as its
    checks fail every row this would skip."""
    cases = []
    for r in read_rows(manifest or MANIFEST):
        photo, art_base = cell(r, "photo"), cell(r, "expected_art_base")
        if not photo:
            continue
        if loader_skips(r):
            say(f"skipping {photo}: no expected_art_number or expected_art_base "
                f"(use {NO_ART_NUMBER} if the photo has no ART number)")
            continue
        expected = legacy_value(r)
        if normalise(cell(r, "expected_art_number")) == UNKNOWN:
            say(f"{photo}: {UNKNOWN} in expected_art_number is not scored "
                "(leave it blank instead)")
        # The base is kept as written, UNKNOWN and blank included: the
        # base-exact scorer counts those, so the loader doesn't.
        cases.append(Case(
            name=photo,
            inputs=(photos or PHOTOS) / photo,
            expected_output=expected or None,
            metadata={
                "id": cell(r, "id"),
                "note": cell(r, "note"),
                "garment": cell(r, "garment"),
                "side": cell(r, "side"),
                "expected_art_base": art_base,
            },
        ))
    return cases


NO_CODE = ("", NO_ART_NUMBER, UNKNOWN)
EXPECTED_COLUMNS = ("expected_art_number", "expected_art_line", "expected_art_base")


class Check(NamedTuple):
    """One test-set check. `detail` is built from counts and fixed words
    only: it is printed, and the set's values never are."""
    name: str
    ok: bool
    detail: str = ""


def holdout_checks(rows: list[dict], dev_rows: list[dict] | None,
                   photos: Path) -> list[Check]:
    """The held-out set's checks (ADR-0002, *Rules for the test set*), each
    failing with the number of rows that break it. `dev_rows` is the dev
    manifest, read as labels only; None if it is missing, which fails the
    three checks that need it rather than skipping them. `photos` is where
    the rows' photos must be; they are looked for, never read."""
    def failing(n: int) -> str:
        return f"{n} row{'' if n == 1 else 's'}" if n else ""

    def base(r: dict) -> str:
        return normalise(cell(r, "expected_art_base"))

    # 1. Every row scored: none the loader would skip, every base a value,
    # and no row with no ART number, which the test set never holds.
    bad_rows = sum(1 for r in rows if loader_skips(r) or base(r) in NO_CODE
                   or any(normalise(cell(r, c)) == NO_ART_NUMBER for c in EXPECTED_COLUMNS))

    ids = [cell(r, "id") for r in rows]
    bad_ids = sum(1 for i in ids if not i or ids.count(i) > 1)

    # 3. A row with no garment or side can't be told apart, so it fails too.
    sides = [(cell(r, "garment"), cell(r, "side")) for r in rows]
    repeated_sides = sum(1 for g, sd in sides
                         if not g or not sd or sides.count((g, sd)) > 1)

    checks = [
        Check("rows", not bad_rows, failing(bad_rows)),
        Check("ids", not bad_ids, failing(bad_ids)),
        Check("one photo per garment-side", not repeated_sides, failing(repeated_sides)),
    ]

    if dev_rows is None:
        checks += [Check("no garment overlap", False, "no dev manifest"),
                   Check("no product overlap", False, "no dev manifest")]
    else:
        dev_garments = {cell(r, "garment") for r in dev_rows} - {""}
        dev_bases = {base(r) for r in dev_rows} - set(NO_CODE)
        shared_garments = sum(1 for r in rows if cell(r, "garment") in dev_garments)
        shared_bases = sum(1 for r in rows if base(r) in dev_bases)
        checks += [
            Check("no garment overlap", not shared_garments, failing(shared_garments)),
            Check("no product overlap", not shared_bases, failing(shared_bases)),
        ]

    # 6. A substring of the whole prompt, normalised: conservative, as a base
    # could match across two words of prose.
    prompt = normalise(ART_PROMPT)
    in_prompt = sum(1 for r in rows if base(r) not in NO_CODE and base(r) in prompt)
    checks.append(Check("no prompt examples", not in_prompt, failing(in_prompt)))

    n_sides = len(set(sides))
    checks.append(Check("size", n_sides >= MIN_SIDES, f"{n_sides} garment-sides"))

    # 8. A missing photo would fail its reads, and void the run.
    missing = sum(1 for r in rows
                  if not cell(r, "photo") or not (photos / cell(r, "photo")).is_file())
    checks.append(Check("photo files", not missing, failing(missing)))

    if dev_rows is None:
        checks.append(Check("no id overlap", False, "no dev manifest"))
    else:
        dev_ids = {cell(r, "id") for r in dev_rows} - {""}
        shared_ids = sum(1 for i in ids if i in dev_ids)
        checks.append(Check("no id overlap", not shared_ids, failing(shared_ids)))
    return checks


def print_checks(checks: list[Check]) -> bool:
    """Name, pass or fail, and at most a count. True if every check passed."""
    print("test-set checks (ADR-0002):")
    for c in checks:
        print(f"  {c.name}: {'pass' if c.ok else 'fail'}"
              + (f" ({c.detail})" if c.detail else ""))
    return all(c.ok for c in checks)


def gate_needed(sides: int) -> int:
    """Garment-sides correct needed to pass: GATE_PERCENT of them, rounded up."""
    return (GATE_PERCENT * sides + 99) // 100


class GateTotals(NamedTuple):
    sides: int          # positive garment-sides: one photo each, by the checks
    correct: int        # of those, correct by the 2-of-3 rule
    needed: int
    reads: int          # every read, failed ones included
    reads_correct: int
    failed: int         # any makes the run void


def gate_totals(report: EvaluationReport) -> GateTotals:
    """The gate's numbers. `reads` is every read: on a run that isn't void
    no read failed, so it equals the reads scored. A misread counts as
    wrong."""
    sides = [p for p in bases_by_photo(report) if p.kind == "positive"]
    return GateTotals(
        sides=len(sides),
        correct=sum(1 for p in sides if p.correct),
        needed=gate_needed(len(sides)),
        reads=sum(p.runs for p in sides),
        reads_correct=sum(p.right for p in sides),
        failed=len(report.failures),
    )


def media_type(photo_path: Path) -> str:
    """The media type a photo is sent with, guessed from its name. The read
    and the photo record both use it, so they can't disagree."""
    return guess_type(photo_path.name)[0] or "image/jpeg"


def record_call(read: ArtRead) -> None:
    """The read's usage and reported model name, on its case in the report.
    pydantic-evals leaves a metric that stays 0 out of the case's metrics."""
    for field in USAGE_FIELDS:
        increment_eval_metric(field, getattr(read.usage, field))
    set_eval_attribute("reported_model", read.model_name)


def get_art_number_reading(photo_path: Path, model: str) -> ArtNumberReading:
    read = read_art(photo_path.read_bytes(), media_type(photo_path), model=model)
    record_call(read)
    return read.reading


def call_metadata(report: EvaluationReport) -> dict:
    """Header totals over the run's reads: the model names the API reported,
    and usage summed. A failed read records neither: its run raised before
    returning a result."""
    names = {str(r.attributes["reported_model"])
             for r in report.cases if "reported_model" in r.attributes}
    return {
        "reported_model": ", ".join(sorted(names)) or None,
        "usage": {f: sum(int(r.metrics.get(f, 0)) for r in report.cases)
                  for f in USAGE_FIELDS},
    }

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


def run_metadata(args: argparse.Namespace, manifest: Path | None = None) -> dict:
    """What produced this run, so a saved report can be traced back to it.
    `manifest` is the one fingerprinted: the dev set's by default."""
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
        "model_settings": dict(SETTINGS_RECORD),
        "manifest": fingerprint((manifest or MANIFEST).read_bytes()),
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
    """The photos this run sends, by manifest id: a sha256 each of the bytes
    sent, after upright() as read_art applies it, and one fingerprint over
    them all. An untagged photo is sent as its file, so `shasum -a 256` checks
    it by hand. Hashed once per photo, whatever --repeat is. A missing photo is
    None; its read fails as before."""
    hashes = {}
    for c in cases:
        path = Path(c.inputs)
        hashes[(c.metadata or {})["id"]] = (
            hashlib.sha256(upright(path.read_bytes(), media_type(path))[0]).hexdigest()
            if path.is_file() else None)
    return {"photos": fingerprint(json.dumps(hashes, sort_keys=True).encode()),
            "photo_hashes": hashes}


def replay_metadata(args: argparse.Namespace, source: EvaluationReport) -> dict:
    """The scoring run's commit and manifest; the reads' model, prompt, user
    message, schema, photos, library versions, model settings, reported model
    and usage. A source from before a field existed gives None."""
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
        "model_settings": read_by.get("model_settings"),
        "reported_model": read_by.get("reported_model"),
        "usage": read_by.get("usage"),
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
    """Where the baseline's output schema, user message, library versions,
    model settings or photos differ from this run's. Any of them changing
    alongside the change under test makes the diff meaningless, and none shows
    in a prompt or model comparison: a library upgrade can change what's sent
    without moving the schema. Not `prompt` or `model`: a comparison usually
    changes one on purpose."""
    warnings = []
    for what, key in [("output schema", "schema"), ("user message", "user_message"),
                      ("versions line", "versions")]:
        if baseline.get(key) is None:
            warnings.append(f"warning: the {what} is not recorded in the baseline")
        elif baseline[key] != run[key]:
            warnings.append(f"warning: the {what} differs from the baseline's "
                            f"({baseline[key]} -> {run[key]})")

    # A dict: name each setting that changed, not the whole record.
    then, now = baseline.get("model_settings"), run["model_settings"]
    if then is None:
        warnings.append("warning: the model settings are not recorded in the baseline")
    elif then != now:
        changed = ", ".join(f"{k}: {then.get(k)} -> {now.get(k)}"
                            for k in sorted({*then, *now}) if then.get(k) != now.get(k))
        warnings.append(f"warning: the model settings differ from the baseline's ({changed})")

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
        report = EvaluationReportAdapter.validate_json(path.read_bytes())
    except ValidationError:
        print(f"{path} is not a saved eval report. Results from before the "
              "pydantic-evals port use an older format and can't be baselines "
              "or replayed.")
        return None
    if (report.experiment_metadata or {}).get("set") == "holdout":
        # Either would print its results per photo (ADR-0002: opened, they
        # move those garments to development).
        print(f"{path} is a --holdout report: it can't be a baseline or replayed")
        return None
    return report


def dataset_of(cases: list[Case]) -> Dataset:
    return Dataset(name="art-number-transcription",
                   cases=cases, evaluators=[CorrectArtNumber(), CorrectArtBase()],
                   report_evaluators=[ConfidenceRates(), PerPhotoCounts(),
                                      BaseExactCounts()])


def holdout_refusals(args: argparse.Namespace) -> list[str]:
    """Why this --holdout run can't start, before any read. The `test` model
    skips the tag and the ledger, so the path runs offline."""
    refusals = []
    if git("status", "--porcelain"):
        refusals.append("the tree has uncommitted or untracked changes: commit first")
    if args.model != "test":
        if not git("tag", "--points-at", "HEAD"):
            refusals.append("HEAD has no tag: the gate runs from a tagged commit")
        ledger = BASELINES.read_text(encoding="utf-8") if BASELINES.is_file() else ""
        recorded = last_ledger_md5(ledger, HOLDOUT_LEDGER_HEADER)
        if recorded != hashlib.md5(HOLDOUT_MANIFEST.read_bytes()).hexdigest():
            refusals.append(f"the held-out manifest's md5 is not the last row of its "
                            f"ledger in {BASELINES.name}: the set isn't the frozen one")
    return refusals


def holdout_main(args: argparse.Namespace) -> int:
    """--holdout: the gate's run, or with --check the test-set checks alone.
    Nothing per photo is printed. An error prints its type only, as its
    message could name a photo or a value."""
    try:
        return run_holdout(args)
    except Exception as e:
        print(f"--holdout stopped: {type(e).__name__}")
        return 1


def run_holdout(args: argparse.Namespace) -> int:
    if not HOLDOUT_MANIFEST.is_file():
        print(f"no held-out manifest at {HOLDOUT_MANIFEST.relative_to(EVALS.parent)}")
        return 1
    # The dev manifest is read as labels only, for the overlap checks: no
    # dev row is a case, and no dev photo is loaded.
    checks = holdout_checks(read_rows(HOLDOUT_MANIFEST),
                            read_rows(MANIFEST) if MANIFEST.is_file() else None,
                            HOLDOUT_PHOTOS)
    if args.check:
        return 0 if print_checks(checks) else 1

    args.model = args.model or ART_MODEL
    args.repeat, args.workers = HOLDOUT_REPEAT, HOLDOUT_WORKERS
    refusals = holdout_refusals(args)
    if not print_checks(checks):
        refusals.append("a test-set check failed")
    if refusals:
        print("\n".join(f"refused: {r}" for r in refusals))
        return 1

    cases = load_manifest(HOLDOUT_MANIFEST, HOLDOUT_PHOTOS, say=lambda _: None)
    from dotenv import load_dotenv
    load_dotenv()
    metadata = {**run_metadata(args, HOLDOUT_MANIFEST), "set": "holdout",
                **photo_metadata(cases)}
    name = f"{args.model}-holdout"
    # pydantic-evals' progress and anything a read prints could name a photo.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        report = dataset_of(cases).evaluate_sync(
            partial(get_art_number_reading, model=args.model),
            max_concurrency=args.workers, repeat=args.repeat, name=name,
            metadata=metadata, progress=False)
    g = gate_totals(report)
    # ADR-0002: a run with any failed read is void, not an attempt. Its
    # totals stay unprinted, so a rerun can't depend on them.
    void = g.failed > 0
    report = replace(report, experiment_metadata={**metadata, **call_metadata(report),
                                                  "void": void})
    path = save(report, name)

    print(f"\nheld-out run: {args.model} at {metadata['commit']}, "
          f"--repeat {args.repeat}, workers {args.workers}")
    if void:
        print(f"{g.failed} failed reads: run void, rerun")
    else:
        share = f" ({100 * g.reads_correct / g.reads:.1f}%)" if g.reads else ""
        print(f"garment-sides correct: {g.correct} of {g.sides}")
        print(f"needed to pass: {g.needed} ({GATE_PERCENT}% of {g.sides}, rounded up)")
        print(f"reads correct: {g.reads_correct} of {g.reads}{share}")
        print(f"failed reads: {g.failed}")
    print(f"wrote {path.relative_to(EVALS.parent)}")
    return 1 if void else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # --model and --repeat default to None so --replay can tell they were passed.
    ap.add_argument("--model", help=f"default: {ART_MODEL}")
    ap.add_argument("--workers", type=int,
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
    ap.add_argument("--holdout", action="store_true",
                    help="the gate's run on evals/holdout/: --repeat 3, workers 1, "
                         "totals only (evals/README.md, Held-out set)")
    ap.add_argument("--check", action="store_true",
                    help="with --holdout: the test-set checks alone, no API call")
    args = ap.parse_args()

    if args.check and not args.holdout:
        ap.error("--check needs --holdout")
    if args.holdout:
        # Each would print per photo, cut the set, skip the save, or change
        # the run procedure's settings (ADR-0002). `test` keeps an offline run.
        refused = [flag for flag, bad in [
            ("--limit", args.limit is not None), ("--no-save", args.no_save),
            ("--replay", args.replay), ("--baseline", args.baseline),
            ("--repeat", args.repeat not in (None, HOLDOUT_REPEAT)),
            ("--workers", args.workers not in (None, HOLDOUT_WORKERS)),
            ("--model", args.model not in (None, "test")),
        ] if bad]
        if args.check:
            # The checks make no read, so no run setting applies.
            refused += [flag for flag, passed in [
                ("--repeat", args.repeat is not None), ("--workers", args.workers is not None),
                ("--model", args.model is not None), ("--note", bool(args.note)),
            ] if passed and flag not in refused]
        if refused:
            ap.error(f"--holdout{' --check' if args.check else ''} can't be used with "
                     f"{', '.join(refused)}")
        return holdout_main(args)

    if args.replay:
        passed = [flag for flag, value in [
            ("--model", args.model), ("--repeat", args.repeat), ("--limit", args.limit),
            ("--baseline", args.baseline), ("--no-save", args.no_save)] if value]
        if passed:
            # The reads fix the model and repeat, and every replay is saved.
            ap.error(f"--replay can't be used with {', '.join(passed)}")
    args.model = args.model or ART_MODEL
    args.repeat = args.repeat or 1
    args.workers = 4 if args.workers is None else args.workers

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

    report = dataset_of(cases).evaluate_sync(
        task,
        max_concurrency=workers,
        repeat=repeat,
        name=name,
        metadata=metadata,
    )
    if not args.replay:
        # Known only once the reads are in; a replay keeps the source's.
        report = replace(report, experiment_metadata={**metadata, **call_metadata(report)})
    printable(report).print(include_output=True, include_expected_output=True,
                            baseline=printable(baseline) if baseline else None)
    if not args.no_save:
        print(f"\nwrote {save(report, name).relative_to(EVALS.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

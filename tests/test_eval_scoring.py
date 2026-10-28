"""The eval scoring path: the functions that produce every number we act on.

Nothing here touches the network. `eval_transcription` imports cleanly because
the agents in labels/transcribe.py are built lazily, so no API key is needed.

The negative-case tests matter most. A manifest row of NONE means "this photo
contains no ART number", and scoring it as an ordinary case used to divide by
zero. The fix omits `cer` entirely rather than setting it to None — pydantic-
evals rejects a None metric and discards the WHOLE case result, including
`exact`, which ConfidenceRates keys on. TestNegativeBranch pins that down.
"""

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import Field, create_model
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EvaluatorContext
from pydantic_evals.reporting import EvaluationReportAdapter
from pydantic_evals.reporting.analyses import ScalarResult, TableResult

import eval_transcription
from eval_transcription import (
    NO_ART_NUMBER,
    BaseExactCounts,
    ConfidenceRates,
    CorrectArtBase,
    CorrectArtNumber,
    PerPhotoCounts,
    levenshtein,
    load_manifest,
    normalise,
)
from labels.schemas import AmbiguousCharacter, ArtLegibility, ArtNumberReading
from tests import synthetic as s


def ctx(expected, raw, legible: ArtLegibility = "clear") -> EvaluatorContext:
    """Stand-in for EvaluatorContext. evaluate() reads only these two attributes.

    A rename upstream would leave these tests green while the harness broke, so
    the end-to-end wiring is covered by `rates()` below instead.
    """
    # Deliberate test fake, not a real EvaluatorContext: keep the cast.
    return cast(EvaluatorContext, SimpleNamespace(
        expected_output=expected,
        output=ArtNumberReading(art_number_raw=raw, art_legible=legible),
    ))


def score(expected, raw, legible: ArtLegibility = "clear") -> dict:
    return CorrectArtNumber().evaluate(ctx(expected, raw, legible))


def reading(spec) -> ArtNumberReading:
    """(expected, raw, legible, ambiguous_count) -> the model output it stands for."""
    _, raw, legible, ambiguous_count = spec
    return ArtNumberReading(
        art_number_raw=raw,
        art_legible=legible,
        ambiguous_characters=[
            AmbiguousCharacter(position=p + 1, reading="0", alternative="O")
            for p in range(ambiguous_count)
        ],
    )


def scalars_of(analyses) -> dict:
    """title -> value for report analyses that must all be scalars."""
    out = {}
    for a in analyses:
        assert isinstance(a, ScalarResult), f"{a.title!r} is not a scalar"
        out[a.title] = a.value
    return out


def rates(*specs) -> dict:
    """Run the real scoring path over stub readings; return {title: value}.

    Each spec is (expected, raw, legible, ambiguous_count). The task is a dict
    lookup, so this is offline and needs no API key — but it exercises the
    genuine pydantic-evals wiring that ConfidenceRates reads through.
    """
    readings, cases = {}, []
    for i, spec in enumerate(specs):
        name = f"case{i}"
        readings[name] = reading(spec)
        cases.append(Case(name=name, inputs=name, expected_output=spec[0]))

    report = Dataset(
        name="rates",
        cases=cases,
        evaluators=[CorrectArtNumber()],
        report_evaluators=[ConfidenceRates()],
    ).evaluate_sync(lambda n: readings[n])
    return scalars_of(report.analyses)


def per_photo(photos: dict, expected: dict | None = None) -> tuple[dict, dict]:
    """Run photos through the real path with --repeat; return (table, rates).

    `photos` maps a name to one spec per repeat, so each read can differ. A spec
    of None makes that read fail, as an API error would. A photo's manifest
    value comes from its first real spec, or from `expected` — needed when every
    read fails (default "ABC"). Serial, so the order reads are drawn in doesn't
    matter — only the counts are asserted.
    """
    expected = expected or {}
    repeat = len(next(iter(photos.values())))
    # A short list would surface as a failed read and a long one would be
    # silently truncated — either way a typo here would pose as a failure count.
    assert all(len(specs) == repeat for specs in photos.values())
    queues = {name: iter(specs) for name, specs in photos.items()}

    def task(name):
        spec = next(queues[name])
        if spec is None:
            raise RuntimeError("read failed")
        return reading(spec)

    cases = [
        Case(name=name, inputs=name,
             expected_output=expected.get(
                 name, next((s[0] for s in specs if s is not None), "ABC")))
        for name, specs in photos.items()
    ]
    report = Dataset(
        name="per-photo",
        cases=cases,
        evaluators=[CorrectArtNumber()],
        report_evaluators=[ConfidenceRates(), PerPhotoCounts()],
    ).evaluate_sync(task, repeat=repeat, max_concurrency=1)

    [table] = [a for a in report.analyses if a.title == "per photo"]
    assert isinstance(table, TableResult)
    rows = {row[0]: dict(zip(table.columns, row, strict=True)) for row in table.rows}
    scalars = scalars_of(a for a in report.analyses if a.title != "per photo")
    return rows, scalars


class TestLevenshtein:
    def test_identical_is_zero(self):
        assert levenshtein("05CMSH022A", "05CMSH022A") == 0

    def test_both_empty_is_zero(self):
        assert levenshtein("", "") == 0

    @pytest.mark.parametrize("a,b", [("", "ABC"), ("ABC", "")])
    def test_against_empty_is_the_other_length(self, a, b):
        assert levenshtein(a, b) == 3

    def test_single_substitution(self):
        assert levenshtein("50184868", "50184B68") == 1

    def test_single_insertion(self):
        assert levenshtein("5018486", "50184868") == 1

    def test_counts_every_edit(self):
        assert levenshtein("ABCDEF", "ABCXYZ") == 3

    def test_is_symmetric(self):
        assert levenshtein("K1S154", "K15154") == levenshtein("K15154", "K1S154")


class TestNormalise:
    def test_strips_spaces(self):
        assert normalise("05CMSH022A 004275A") == "05CMSH022A004275A"

    def test_upcases(self):
        assert normalise("k1s154100067") == "K1S154100067"

    def test_keeps_leading_zeros(self):
        assert normalise("0126422791") == "0126422791"

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_inputs_give_empty_string(self, value):
        assert normalise(value) == ""

    def test_never_returns_none(self):
        """is_negative compares against the string NONE, so this must be a str."""
        assert isinstance(normalise(None), str)


class TestPositiveBranch:
    """A manifest row carrying a real code."""

    def test_exact_match_scores_clean(self):
        result = score("6915G0424", "6915G0424")
        assert result["exact"] is True
        assert result["cer"] == 0.0
        assert result["kind"] == "positive"

    def test_mismatch_is_not_exact_and_has_positive_cer(self):
        result = score("50184868", "50184B68")
        assert result["exact"] is False
        assert result["cer"] == pytest.approx(1 / 8)

    def test_spacing_and_case_do_not_count_as_errors(self):
        result = score("05CMSH022A 004275A", "05cmsh022a004275a")
        assert result["exact"] is True
        assert result["cer"] == 0.0

    def test_no_read_at_all_is_a_full_miss(self):
        """A positive case where the model returned nothing: cer 1.0, not a crash."""
        result = score("6915G0424", None, legible="not_visible")
        assert result["exact"] is False
        assert result["cer"] == 1.0

    def test_legibility_is_carried_through(self):
        assert score("6915G0424", "6915G0424", legible="partial")["legibility"] == "partial"


class TestNegativeBranch:
    """A manifest row of NONE: the photo contains no ART number."""

    def test_no_code_returned_is_correct(self):
        result = score(NO_ART_NUMBER, None, legible="not_visible")
        assert result["exact"] is True
        assert result["kind"] == "negative"

    def test_cer_is_omitted_entirely(self):
        """The regression. A None metric makes pydantic-evals discard the whole
        case result — including `exact`, which ConfidenceRates keys on."""
        result = score(NO_ART_NUMBER, None, legible="not_visible")
        assert "cer" not in result

    def test_fabricating_a_code_is_not_exact(self):
        """The failure the negative case exists to catch."""
        result = score(NO_ART_NUMBER, "581540923")
        assert result["exact"] is False
        assert "cer" not in result

    @pytest.mark.parametrize("raw", ["?", "?????", "??  ??"])
    def test_an_all_question_mark_read_is_not_a_fabrication(self, raw):
        """ART_PROMPT rule 3 tells the model to write "?" for characters it can't
        read. On a photo with no code that is the honest answer, not an invention,
        and counting it would inflate the metric this change exists to create."""
        result = score(NO_ART_NUMBER, raw, legible="partial")
        assert result["exact"] is True

    @pytest.mark.parametrize("raw", ["?8?", "58?54", "0"])
    def test_a_partial_read_with_real_characters_is_a_fabrication(self, raw):
        """strip("?") only clears the ends, so any surviving character means the
        model claimed to read something that isn't on the label."""
        assert score(NO_ART_NUMBER, raw, legible="partial")["exact"] is False

    def test_question_marks_do_not_rescue_a_positive_case(self):
        """The leniency is scoped to negatives. Against a real expected code an
        all-? read is still a complete miss."""
        result = score("581540923", "?????")
        assert result["exact"] is False
        assert result["cer"] == 1.0

    def test_sentinel_is_case_and_space_insensitive(self):
        """normalise() runs first, so a sloppy manifest entry still registers."""
        assert score(" none ", None, legible="not_visible")["kind"] == "negative"

    def test_illegible_with_no_code_still_counts_as_correct(self):
        """Saying 'illegible' rather than 'not_visible' is a lesser error: no code
        was invented. The distinction stays visible in the legibility label."""
        result = score(NO_ART_NUMBER, None, legible="illegible")
        assert result["exact"] is True
        assert result["legibility"] == "illegible"

    def test_kind_is_a_string_not_a_bool(self):
        """Booleans returned from evaluate() become assertions and get pooled into
        the headline pass rate. `kind` must not do that."""
        assert isinstance(score(NO_ART_NUMBER, None, "not_visible")["kind"], str)


CORRECT = ("ABC", "ABC", "clear", 0)                  # positive, read right
WRONG_AND_SURE = ("ABC", "XYZ", "clear", 0)           # positive, wrong, unflagged
WRONG_BUT_FLAGGED = ("ABC", "XYZ", "clear", 1)        # positive, wrong, flagged
NOT_READ = ("ABC", None, "not_visible", 0)            # positive, nothing came back
CLEAN_NEGATIVE = (NO_ART_NUMBER, None, "not_visible", 0)
FABRICATION = (NO_ART_NUMBER, "581540923", "clear", 0)


class TestConfidenceRates:
    """The whole-run rates. These reach into pydantic-evals internals, so they
    are exercised through a real report rather than a stubbed one — a library
    change here would produce wrong percentages, not an exception."""

    def test_overconfident_counts_clear_wrong_and_unflagged(self):
        assert rates(CORRECT, WRONG_AND_SURE)["overconfident"] == 50.0

    def test_flagging_removes_a_read_from_overconfident(self):
        assert rates(CORRECT, WRONG_BUT_FLAGGED)["overconfident"] == 0.0

    def test_adding_a_negative_does_not_move_overconfident(self):
        """The guarantee that keeps this comparable to pre-negative-case runs:
        the positive rates are scoped to positives, so the denominator is
        unchanged by anything in the negative half of the set."""
        without = rates(CORRECT, WRONG_AND_SURE)["overconfident"]
        with_negative = rates(CORRECT, WRONG_AND_SURE, CLEAN_NEGATIVE)["overconfident"]
        assert without == with_negative == 50.0

    def test_fabrication_is_over_negatives_only(self):
        """Two negatives, one fabricated: 50%. The three positives must not
        dilute it."""
        result = rates(CORRECT, CORRECT, CORRECT, CLEAN_NEGATIVE, FABRICATION)
        assert result["fabricated on no-code photos"] == 50.0

    def test_fabrication_declared_clear_is_tracked_separately(self):
        result = rates(CLEAN_NEGATIVE, FABRICATION)
        assert result["fabricated and declared clear"] == 50.0

    def test_a_flagged_fabrication_is_not_declared_clear(self):
        quiet = (NO_ART_NUMBER, "581540923", "partial", 0)
        result = rates(CLEAN_NEGATIVE, quiet)
        assert result["fabricated on no-code photos"] == 50.0
        assert result["fabricated and declared clear"] == 0.0

    def test_negative_rates_are_omitted_when_the_set_has_none(self):
        """A --limit run that truncates past the negatives lands here."""
        result = rates(CORRECT, WRONG_AND_SURE)
        assert "fabricated on no-code photos" not in result
        assert "fabricated and declared clear" not in result

    def test_positive_rates_are_omitted_when_the_set_is_all_negative(self):
        result = rates(CLEAN_NEGATIVE, FABRICATION)
        assert "missed" not in result
        assert "overconfident" not in result
        assert "flagged but correct" not in result

    def test_clear_but_wrong_is_omitted_when_nothing_was_clear(self):
        murky = ("ABC", "XYZ", "partial", 0)
        assert "clear but wrong" not in rates(murky)

    def test_flagged_but_correct_measures_review_queue_noise(self):
        flagged_right = ("ABC", "ABC", "clear", 1)
        assert rates(flagged_right, CORRECT)["flagged but correct"] == 50.0


class TestMissed:
    """Positive cases where the model returned no characters at all.

    Judged on the output, not the legibility label, so the two ways of declining
    count the same and an all-"?" read counts as an attempt. This separates
    "didn't find the code" from "misread it", which exact and cer conflate.
    """

    def test_a_null_read_is_missed(self):
        assert rates(CORRECT, NOT_READ)["missed"] == 50.0

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_a_blank_read_is_missed(self, raw):
        assert rates(("ABC", raw, "not_visible", 0))["missed"] == 100.0

    def test_illegible_with_no_code_is_missed_too(self):
        """The label says a code is present; the output still has none."""
        assert rates(("ABC", None, "illegible", 0))["missed"] == 100.0

    @pytest.mark.parametrize("raw", ["?", "?????", "58?54"])
    def test_a_question_mark_read_is_an_attempt(self, raw):
        """The model located the code and marked what it couldn't read. That is
        a transcription failure, not a detection one."""
        assert rates(("ABC", raw, "partial", 0))["missed"] == 0.0

    def test_a_wrong_read_is_an_attempt(self):
        assert rates(WRONG_AND_SURE)["missed"] == 0.0

    def test_an_empty_clear_read_is_missed_and_overconfident(self):
        """Incoherent but allowed by the schema. It counts in both rates, which
        the README states; pinned so a change to either is deliberate."""
        result = rates(("ABC", None, "clear", 0))
        assert result["missed"] == 100.0
        assert result["overconfident"] == 100.0

    def test_a_declined_read_is_never_overconfident(self):
        """Why a model that declines most photos shows a clean overconfident
        rate: a not_visible miss sits in the denominator, never the numerator."""
        result = rates(CORRECT, NOT_READ)
        assert result["missed"] == 50.0
        assert result["overconfident"] == 0.0

    def test_negatives_do_not_move_missed(self):
        """Scoped to positives like the other rates, so adding negatives to the
        manifest cannot shift it."""
        without = rates(CORRECT, NOT_READ)["missed"]
        with_negatives = rates(CORRECT, NOT_READ, CLEAN_NEGATIVE, FABRICATION)["missed"]
        assert without == with_negatives == 50.0


class TestPerPhotoCounts:
    """The table the decision rule in ADR-0006 is read from: one row per photo,
    counts out of --repeat. Run through the real pydantic-evals repeat path,
    since grouping reads by photo depends on its source_case_name."""

    def test_counts_every_read_of_a_photo(self):
        rows, _ = per_photo({"a": [CORRECT, NOT_READ, NOT_READ]})
        assert rows["a"]["reads"] == 3
        assert rows["a"]["exact"] == 1
        assert rows["a"]["missed"] == 2

    def test_overconfident_uses_the_same_test_as_the_rate(self):
        """A wrong read with a flagged character goes to review, so it is not
        overconfident here either."""
        rows, _ = per_photo({"a": [WRONG_AND_SURE, WRONG_AND_SURE, WRONG_BUT_FLAGGED]})
        assert rows["a"]["overconfident"] == 2

    def test_a_negative_row_counts_fabricated_clear_only(self):
        rows, _ = per_photo({"n": [CLEAN_NEGATIVE, FABRICATION, FABRICATION]})
        assert rows["n"]["kind"] == "negative"
        assert rows["n"]["fabricated clear"] == 2
        assert rows["n"]["missed"] is None
        assert rows["n"]["overconfident"] is None

    def test_a_positive_row_leaves_fabrication_blank(self):
        rows, _ = per_photo({"a": [CORRECT, CORRECT]})
        assert rows["a"]["fabricated clear"] is None

    def test_a_failed_read_shows_as_fewer_reads(self):
        """The denominator the pooled rates hide: which photo lost a read."""
        rows, _ = per_photo({"a": [CORRECT, None, CORRECT], "b": [CORRECT] * 3})
        assert rows["a"]["reads"] == 2
        assert rows["b"]["reads"] == 3

    def test_a_photo_that_lost_every_read_still_gets_a_row(self):
        """Otherwise it would vanish from the win/loss tally unnoticed."""
        rows, _ = per_photo({"a": [None] * 3, "b": [CORRECT] * 3})
        assert rows["a"]["reads"] == 0
        assert rows["a"]["kind"] == "positive"
        assert rows["a"]["missed"] == 0

    def test_a_negative_that_lost_every_read_keeps_its_kind(self):
        """Kind comes from the manifest value, since there's no scored read to
        carry a label — and losing the only negative must not go unseen."""
        rows, _ = per_photo({"n": [None] * 2, "a": [CORRECT] * 2},
                            expected={"n": NO_ART_NUMBER})
        assert rows["n"]["kind"] == "negative"
        assert rows["n"]["reads"] == 0
        assert rows["n"]["fabricated clear"] == 0
        assert rows["n"]["missed"] is None

    def test_a_single_run_keys_rows_on_the_photo_name(self):
        """At --repeat 1 pydantic-evals sets no source_case_name, so the row
        falls back to the case name — which is the photo."""
        rows, _ = per_photo({"b": [CORRECT], "a": [NOT_READ]})
        assert rows["a"]["reads"] == rows["b"]["reads"] == 1
        assert rows["a"]["missed"] == 1

    def test_rows_are_sorted_by_photo(self):
        rows, _ = per_photo({"b": [CORRECT] * 2, "a": [CORRECT] * 2})
        assert list(rows) == ["a", "b"]

    def test_the_table_and_the_rates_count_the_same_reads(self):
        """Summed over photos, the table must reproduce the pooled rates. If
        the two ever disagree, the decision rule and the headline number are
        being judged on different definitions."""
        rows, scalars = per_photo({
            "a": [CORRECT, NOT_READ, WRONG_AND_SURE],
            "b": [NOT_READ, None, WRONG_BUT_FLAGGED],   # a failed read, where
            "n": [CLEAN_NEGATIVE, FABRICATION, None],   # the two could drift
        })
        positive_reads = sum(r["reads"] for r in rows.values() if r["kind"] == "positive")
        negative_reads = rows["n"]["reads"]

        def pooled(column, reads):
            return 100 * sum(r[column] or 0 for r in rows.values()) / reads

        assert pooled("missed", positive_reads) == pytest.approx(scalars["missed"])
        assert pooled("overconfident", positive_reads) == pytest.approx(scalars["overconfident"])
        assert pooled("fabricated clear", negative_reads) == pytest.approx(
            scalars["fabricated and declared clear"])


def base_score(expected_base, raw, legible: ArtLegibility = "clear") -> dict:
    """CorrectArtBase over one read. Its art_base comes from the split, not
    the catalogue, so these tests need no catalogue patch or fixture."""
    return CorrectArtBase().evaluate(cast(EvaluatorContext, SimpleNamespace(
        metadata={"expected_art_base": expected_base},
        output=ArtNumberReading(art_number_raw=raw, art_legible=legible),
    )))


class TestCorrectArtBase:
    def test_the_base_read_from_a_full_line_is_correct(self):
        line = f"ART. {s.SPLIT_SI_9}/{s.SPLIT_COLOUR[:3]}"
        assert base_score(s.SPLIT_SI_9, line) == {
            "base_kind": "positive", "base_exact": True}

    def test_a_different_base_is_wrong(self):
        assert base_score(s.SPLIT_SI_9, s.SPLIT_SI_8)["base_exact"] is False

    def test_a_failed_split_is_wrong(self):
        """No art_base comes back, which never equals an expected one."""
        marked = s.SPLIT_SI_9[:5] + "?" + s.SPLIT_SI_9[6:]
        assert base_score(s.SPLIT_SI_9, marked)["base_exact"] is False

    def test_no_read_is_wrong(self):
        assert base_score(s.SPLIT_SI_9, None, "not_visible")["base_exact"] is False

    def test_the_expected_base_is_compared_ignoring_spacing_and_case(self):
        assert base_score(f" {s.SPLIT_CP_MODERN.lower()} ", s.SPLIT_CP_MODERN)[
            "base_exact"] is True

    def test_a_negative_is_correct_with_no_base(self):
        assert base_score(NO_ART_NUMBER, None, "not_visible") == {
            "base_kind": "negative", "base_exact": True}

    def test_a_negative_with_a_base_is_wrong(self):
        assert base_score(NO_ART_NUMBER, s.SPLIT_SI_9)["base_exact"] is False

    @pytest.mark.parametrize("expected,kind", [("", "unlabelled"), (None, "unlabelled"),
                                               ("UNKNOWN", "unknown"), ("unknown", "unknown")])
    def test_a_row_with_no_usable_base_is_left_out(self, expected, kind):
        """No base_exact, so it can't pass or fail; base_kind says why."""
        assert base_score(expected, s.SPLIT_SI_9) == {"base_kind": kind}

    def test_base_kind_is_a_string_not_a_bool(self):
        """As with `kind`: a bool would become an assertion."""
        assert isinstance(base_score(s.SPLIT_SI_9, s.SPLIT_SI_9)["base_kind"], str)


RIGHT, WRONG = s.SPLIT_SI_9, s.SPLIT_SI_8   # reads of a photo whose base is RIGHT


def base_counts(photos: dict) -> dict:
    """Run photos through the real path with --repeat; return {title: rows}.

    `photos` maps a name to (expected_art_base, garment, side, reads), one raw
    line per repeat; None makes that read fail, as an API error would. Serial,
    as in per_photo().
    """
    repeat = len(next(iter(photos.values()))[3])
    assert all(len(p[3]) == repeat for p in photos.values())
    queues = {name: iter(p[3]) for name, p in photos.items()}

    def task(name):
        raw = next(queues[name])
        if raw is None:
            raise RuntimeError("read failed")
        return ArtNumberReading(art_number_raw=raw, art_legible="clear")

    cases = [Case(name=name, inputs=name, metadata={
                 "expected_art_base": base, "garment": garment, "side": side})
             for name, (base, garment, side, _) in photos.items()]
    report = Dataset(
        name="base-exact",
        cases=cases,
        evaluators=[CorrectArtBase()],
        report_evaluators=[BaseExactCounts()],
    ).evaluate_sync(task, repeat=repeat, max_concurrency=1)

    tables = {}
    for a in report.analyses:
        assert isinstance(a, TableResult)
        tables[a.title] = [dict(zip(a.columns, row, strict=True)) for row in a.rows]
    return tables


def rates_of(tables: dict) -> tuple[str, dict]:
    """(title, {rate: (n, of, %)}) of the base-exact rates table."""
    [title] = [t for t in tables if t.startswith("base-exact")]
    return title, {r[""]: (r["n"], r["of"], r["%"]) for r in tables[title]}


def photo_rows(tables: dict) -> dict:
    return {r["photo"]: r for r in tables["base per photo"]}


class TestBaseExactCounts:
    def test_two_of_three_is_correct_and_one_is_not(self):
        rows = photo_rows(base_counts({
            "a": (RIGHT, "g1", "back", [RIGHT, RIGHT, WRONG]),
            "b": (RIGHT, "g2", "back", [RIGHT, WRONG, WRONG]),
        }))
        assert (rows["a"]["correct reads"], rows["a"]["correct"]) == (2, "✔")
        assert (rows["b"]["correct reads"], rows["b"]["correct"]) == (1, "✗")

    def test_the_rule_is_printed_with_the_rates(self):
        title, _ = rates_of(base_counts({"a": (RIGHT, "g1", "back", [RIGHT] * 3)}))
        assert title == "base-exact (correct: at least 2 of 3 reads)"

    def test_a_single_read_needs_one(self):
        tables = base_counts({"a": (RIGHT, "g1", "back", [RIGHT])})
        assert rates_of(tables)[0] == "base-exact (correct: at least 1 of 1 reads)"
        assert photo_rows(tables)["a"]["correct"] == "✔"

    def test_a_lost_read_counts_against_repeat(self):
        """Two of three still needed: a failed read can't lower the bar."""
        rows = photo_rows(base_counts({
            "a": (RIGHT, "g1", "back", [RIGHT, RIGHT, None]),
            "b": (RIGHT, "g2", "back", [RIGHT, WRONG, None]),
            "c": (RIGHT, "g3", "back", [None] * 3),
        }))
        assert (rows["a"]["reads"], rows["a"]["correct"]) == (2, "✔")
        assert (rows["b"]["reads"], rows["b"]["correct"]) == (2, "✗")
        assert (rows["c"]["reads"], rows["c"]["correct"]) == (0, "✗")

    def test_rates_are_counts_over_positives(self):
        _, rates = rates_of(base_counts({
            "a": (RIGHT, "g1", "back", [RIGHT, RIGHT, WRONG]),
            "b": (RIGHT, "g2", "back", [RIGHT, WRONG, None]),
            "n": (NO_ART_NUMBER, "g3", "front", ["", "", ""]),
        }))
        assert rates["photos correct"] == (1, 2, 50.0)
        assert rates["reads correct"] == (3, 5, 60.0)   # scored reads only
        assert rates["negatives correct"] == (1, 1, 100.0)

    def test_a_negative_follows_the_same_rule(self):
        rows = photo_rows(base_counts({
            "m": (NO_ART_NUMBER, "g1", "front", ["", "", RIGHT]),
            "n": (NO_ART_NUMBER, "g2", "front", ["", RIGHT, RIGHT]),
        }))
        assert (rows["m"]["correct"], rows["n"]["correct"]) == ("✔", "✗")

    def test_rows_with_no_usable_base_are_counted_and_left_out(self):
        tables = base_counts({
            "a": (RIGHT, "g1", "back", [RIGHT] * 3),
            "u": ("UNKNOWN", "g2", "back", [RIGHT] * 3),
            "v": ("", "g3", "back", [RIGHT] * 3),
        })
        _, rates = rates_of(tables)
        assert rates["photos correct"] == (1, 1, 100.0)
        assert rates["left out: unknown"][:2] == (1, 3)
        assert rates["left out: unlabelled"][:2] == (1, 3)
        rows = photo_rows(tables)
        assert rows["u"]["kind"] == "unknown" and rows["u"]["correct"] is None

    def test_garment_sides_are_counts_only(self):
        """No verdict per side: dev has deliberate hard variants of one side."""
        tables = base_counts({
            "a": (RIGHT, "g1", "back", [RIGHT] * 3),
            "a_rotated": (RIGHT, "g1", "back", [WRONG] * 3),
            "b": (NO_ART_NUMBER, "g1", "front", [""] * 3),
            "c": ("UNKNOWN", "g2", "back", [RIGHT] * 3),
        })
        sides = {(r["garment"], r["side"]): r for r in tables["garment-sides"]}
        assert sides[("g1", "back")] == {"garment": "g1", "side": "back",
                                         "photos": 2, "correct": 1, "left out": 0}
        assert (sides[("g1", "front")]["photos"], sides[("g1", "front")]["correct"]) == (1, 1)
        assert sides[("g2", "back")]["left out"] == 1


def schema_variant(**fields) -> type[ArtNumberReading]:
    """ArtNumberReading with its name and docstring, `fields` overridden: the
    schema the model would see after a description edit."""
    return create_model("ArtNumberReading", __base__=ArtNumberReading,
                        __doc__=ArtNumberReading.__doc__, **fields)


class TestRunMetadata:
    """The header's fingerprints of what the model sees, each its own field."""

    @pytest.fixture
    def header(self, tmp_path, monkeypatch):
        manifest = tmp_path / "manifest.csv"
        manifest.write_text("id,photo\n", encoding="utf-8")
        monkeypatch.setattr(eval_transcription, "MANIFEST", manifest)
        monkeypatch.setattr(eval_transcription, "git", lambda *a: "")
        args = argparse.Namespace(model="test", limit=None, repeat=1, note="")
        return lambda: eval_transcription.run_metadata(args)

    def test_a_changed_schema_description_changes_the_schema_fingerprint(
        self, header, monkeypatch
    ):
        before = header()
        # The control: an unchanged copy keeps the fingerprint, so the edit
        # below is what moves it.
        monkeypatch.setattr(eval_transcription, "ArtNumberReading", schema_variant())
        assert header()["schema"] == before["schema"]

        monkeypatch.setattr(eval_transcription, "ArtNumberReading", schema_variant(
            art_number_raw=(str | None, Field(default=None, description="Changed."))))
        after = header()
        assert after["schema"] != before["schema"]
        assert (after["prompt"], after["user_message"]) == (
            before["prompt"], before["user_message"])

    def test_a_changed_user_message_changes_its_fingerprint(self, header, monkeypatch):
        before = header()
        monkeypatch.setattr(eval_transcription, "ART_USER_MESSAGE", "Changed.")
        after = header()
        assert after["user_message"] != before["user_message"]
        assert (after["prompt"], after["schema"]) == (before["prompt"], before["schema"])


class TestReplay:
    """--replay end to end: a saved report's reads, rescored by main() with
    no API call. The harness's paths and git are patched on the module, as
    MANIFEST is in TestLoadManifest."""

    HEADER = "id,photo,garment,side,expected_art_number,expected_art_base,note"

    @pytest.fixture
    def paths(self, tmp_path, monkeypatch):
        # A live run loads .env; unpatched, a real key would outlive the test.
        monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
        monkeypatch.setattr(eval_transcription, "EVALS", tmp_path)
        monkeypatch.setattr(eval_transcription, "MANIFEST", tmp_path / "manifest.csv")
        monkeypatch.setattr(eval_transcription, "PHOTOS", tmp_path / "photos")
        monkeypatch.setattr(eval_transcription, "RESULTS", tmp_path / "results")
        monkeypatch.setattr(eval_transcription, "git",
                            lambda *a: "" if a[0] == "status" else "abc1234")
        return tmp_path

    @staticmethod
    def no_api(monkeypatch):
        def fail(*_, **__):
            raise AssertionError("a replay must not call the model")
        monkeypatch.setattr(eval_transcription, "get_art_number_reading", fail)

    @pytest.fixture
    def harness(self, paths, monkeypatch):
        self.no_api(monkeypatch)
        return paths

    def source(self, tmp_path, photos: dict, **metadata) -> Path:
        """Save a report as a live run would. `photos` maps a filename to one
        raw line per repeat; None makes that read fail. `metadata` adds header
        fields; without it the header predates user_message and schema."""
        repeat = len(next(iter(photos.values())))
        queues = {name: iter(reads) for name, reads in photos.items()}

        def task(path):
            raw = next(queues[path.name])
            if raw is None:
                raise RuntimeError("read failed")
            return ArtNumberReading(art_number_raw=raw, art_legible="clear")

        report = Dataset(
            name="source",
            cases=[Case(name=n, inputs=tmp_path / n) for n in photos],
        ).evaluate_sync(task, repeat=repeat, max_concurrency=1, metadata={
            "model": "source:model", "prompt": "abc", "repeat": repeat, **metadata})
        path = tmp_path / "source.json"
        path.write_bytes(EvaluationReportAdapter.dump_json(report))
        return path

    def replay(self, tmp_path, monkeypatch, source, rows, *flags):
        (tmp_path / "manifest.csv").write_text(self.HEADER + "\n" + rows, encoding="utf-8")
        monkeypatch.setattr("sys.argv", ["eval", "--replay", str(source), *flags])
        assert eval_transcription.main() == 0
        [saved] = (tmp_path / "results").glob("*.json")
        return EvaluationReportAdapter.validate_json(saved.read_bytes()), saved

    def test_a_saved_live_run_replays_to_the_same_base_exact_results(
        self, paths, monkeypatch
    ):
        """The JSON round trip: a live run's report is saved, its outputs
        reload as plain dicts, and the replay rebuilds them into readings.
        The offline model returns no read, so the positive is wrong and the
        negative right."""
        (paths / "photos").mkdir()
        for photo in ("a", "n"):
            (paths / "photos" / photo).write_bytes(b"not an image")
        (paths / "manifest.csv").write_text(
            f"{self.HEADER}\np1,a,g1,back,,{RIGHT},\n"
            f"p2,n,g1,front,{NO_ART_NUMBER},{NO_ART_NUMBER},\n", encoding="utf-8")

        def analyses(report):
            return {a.title: a.rows for a in report.analyses
                    if isinstance(a, TableResult) and a.title != "garment-sides"}

        monkeypatch.setattr("sys.argv", ["eval", "--model", "test", "--repeat", "3"])
        assert eval_transcription.main() == 0
        [live_file] = (paths / "results").glob("*.json")
        live = EvaluationReportAdapter.validate_json(live_file.read_bytes())

        self.no_api(monkeypatch)
        monkeypatch.setattr("sys.argv", ["eval", "--replay", str(live_file)])
        assert eval_transcription.main() == 0
        [replay_file] = (paths / "results").glob("*-replay.json")
        replay = EvaluationReportAdapter.validate_json(replay_file.read_bytes())

        assert analyses(replay) == analyses(live)
        rows = {r[0]: r for r in analyses(replay)["base per photo"]}
        assert (rows["a"][-1], rows["n"][-1]) == ("✗", "✔")

    def test_saved_reads_are_scored_against_todays_manifest(self, harness, monkeypatch):
        source = self.source(harness, {"a": [RIGHT, RIGHT, WRONG]})
        report, _ = self.replay(harness, monkeypatch, source,
                                f"p1,a,g1,back,,{RIGHT},\n")
        [table] = [a for a in report.analyses if a.title == "base per photo"]
        assert isinstance(table, TableResult)
        [row] = table.rows
        assert dict(zip(table.columns, row, strict=True))["correct"] == "✔"

    def test_it_records_the_source_and_the_scoring_commit(self, harness, monkeypatch):
        source = self.source(harness, {"a": [RIGHT] * 3})
        report, saved = self.replay(harness, monkeypatch, source,
                                    f"p1,a,g1,back,,{RIGHT},\n", "--note", "check")
        meta = report.experiment_metadata or {}
        assert meta["replay_of"] == "source.json"
        assert (meta["model"], meta["prompt"], meta["repeat"]) == ("source:model", "abc", 3)
        assert (meta["commit"], meta["dirty"], meta["note"]) == ("abc1234", False, "check")
        assert saved.name.endswith("-source_model-replay.json")

    def test_it_copies_what_the_model_saw_from_the_source(self, harness, monkeypatch):
        """The reads came from the source's user message and schema, not today's."""
        source = self.source(harness, {"a": [RIGHT]}, user_message="def", schema="ghi")
        report, _ = self.replay(harness, monkeypatch, source, f"p1,a,g1,back,,{RIGHT},\n")
        meta = report.experiment_metadata or {}
        assert (meta["user_message"], meta["schema"]) == ("def", "ghi")

    def test_a_source_from_before_the_fields_records_none(self, harness, monkeypatch):
        """Not today's values: those would claim the reads saw them."""
        source = self.source(harness, {"a": [RIGHT]})
        report, _ = self.replay(harness, monkeypatch, source, f"p1,a,g1,back,,{RIGHT},\n")
        meta = report.experiment_metadata or {}
        assert (meta["user_message"], meta["schema"]) == (None, None)

    def test_a_failed_source_read_fails_again(self, harness, monkeypatch):
        """The photo keeps its --repeat runs, so the lost read still counts against it."""
        source = self.source(harness, {"a": [RIGHT, None, None], "b": [None] * 3})
        report, _ = self.replay(harness, monkeypatch, source,
                                f"p1,a,g1,back,,{RIGHT},\np2,b,g2,back,,{RIGHT},\n")
        assert (len(report.cases), len(report.failures)) == (1, 5)

    def test_photos_on_one_side_only_are_named_and_not_scored(
        self, harness, monkeypatch, capsys
    ):
        source = self.source(harness, {"a": [RIGHT], "gone": [RIGHT]})
        report, _ = self.replay(harness, monkeypatch, source,
                                f"p1,a,g1,back,,{RIGHT},\np2,new,g2,back,,{RIGHT},\n")
        assert [c.name for c in report.cases] == ["a"]
        out = capsys.readouterr().out
        assert "not scored: gone" in out and "not scored: new" in out

    def test_a_dirty_tree_warns(self, harness, monkeypatch, capsys):
        monkeypatch.setattr(eval_transcription, "git",
                            lambda *a: " M x.py" if a[0] == "status" else "abc1234")
        source = self.source(harness, {"a": [RIGHT]})
        report, _ = self.replay(harness, monkeypatch, source, f"p1,a,g1,back,,{RIGHT},\n")
        assert (report.experiment_metadata or {})["dirty"] is True
        assert "warning: uncommitted changes" in capsys.readouterr().out

    @pytest.mark.parametrize("flags", [["--no-save"], ["--model", "test"], ["--repeat", "3"],
                                       ["--limit", "1"], ["--baseline", "x.json"]])
    def test_flags_it_sets_itself_are_rejected(self, monkeypatch, flags):
        monkeypatch.setattr("sys.argv", ["eval", "--replay", "x.json", *flags])
        with pytest.raises(SystemExit) as exc:
            eval_transcription.main()
        assert exc.value.code == 2


class TestBaseOnlyRow:
    """A row with expected_art_base but no legacy value. The legacy metrics
    must pass over it, not crash or count it."""

    def test_correct_art_number_returns_nothing(self):
        assert score(None, "ABC") == {}

    def test_per_photo_and_the_rates_leave_it_out(self):
        rows, scalars = per_photo({"a": [CORRECT, NOT_READ], "b": [WRONG_AND_SURE] * 2},
                                  expected={"b": None})
        _, without = per_photo({"a": [CORRECT, NOT_READ]})
        assert list(rows) == ["a"]
        assert scalars == without


class TestLoadManifest:
    """The loader is the only thing keeping a blank row away from the evaluator.

    MANIFEST is patched on the module, which is where load_manifest looks it up
    at call time — the same rule as the transcribe patch target in CLAUDE.md.
    """

    def write(self, tmp_path, monkeypatch, body, header="photo,expected_art_number,note"):
        manifest = tmp_path / "manifest.csv"
        manifest.write_text(header + "\n" + body, encoding="utf-8")
        monkeypatch.setattr(eval_transcription, "MANIFEST", manifest)

    def test_blank_expected_is_skipped(self, tmp_path, monkeypatch):
        self.write(tmp_path, monkeypatch, "a.jpg,123456789,\nb.jpg,,not labelled yet\n")
        assert [c.name for c in load_manifest()] == ["a.jpg"]

    def test_blank_expected_warns_once_per_dropped_row(
        self, tmp_path, monkeypatch, capsys
    ):
        """Silence here is how a photo vanishes from the eval unnoticed."""
        self.write(tmp_path, monkeypatch, "a.jpg,,\nb.jpg,,\nc.jpg,123456789,\n")
        load_manifest()
        out = capsys.readouterr().out
        assert out.count("skipping") == 2
        assert "a.jpg" in out and "b.jpg" in out

    def test_the_warning_names_the_sentinel(self, tmp_path, monkeypatch, capsys):
        self.write(tmp_path, monkeypatch, "a.jpg,,\n")
        load_manifest()
        assert NO_ART_NUMBER in capsys.readouterr().out

    def test_sentinel_rows_are_kept(self, tmp_path, monkeypatch):
        """The distinction the blank guard exists to protect."""
        self.write(tmp_path, monkeypatch, f"a.jpg,{NO_ART_NUMBER},\nb.jpg,,\n")
        cases = load_manifest()
        assert [c.name for c in cases] == ["a.jpg"]
        assert cases[0].expected_output == NO_ART_NUMBER

    def test_rows_without_a_photo_are_skipped_silently(self, tmp_path, monkeypatch):
        self.write(tmp_path, monkeypatch, ",123456789,\na.jpg,123456789,\n")
        assert [c.name for c in load_manifest()] == ["a.jpg"]

    def test_note_is_carried_into_case_metadata(self, tmp_path, monkeypatch):
        self.write(tmp_path, monkeypatch, "a.jpg,123456789,faded garment dyed\n")
        metadata = load_manifest()[0].metadata
        assert metadata is not None
        assert metadata["note"] == "faded garment dyed"

    def test_unknown_in_the_legacy_column_is_skipped_with_a_warning(
        self, tmp_path, monkeypatch, capsys
    ):
        """UNKNOWN belongs to the run 0 columns. Scored here, it would be a
        code no read can match."""
        self.write(tmp_path, monkeypatch, "a,UNKNOWN,\nb,123456789,\n")
        assert [c.name for c in load_manifest()] == ["b"]
        assert "skipping a" in capsys.readouterr().out

    def test_columns_it_does_not_score_change_nothing(self, tmp_path, monkeypatch):
        """`id` and `expected_art_line`, filled or blank, leave the cases as they were."""
        legacy = "a,123456789,faded\nb,NONE,\nc,,\n"
        self.write(tmp_path, monkeypatch, legacy)
        before = [(c.name, c.expected_output, c.metadata) for c in load_manifest()]
        self.write(
            tmp_path, monkeypatch,
            'p1,a,123456789,"ART. 123456789",faded\n'
            "p2,b,NONE,NONE,\n"
            "p3,c,,,\n",
            header="id,photo,expected_art_number,expected_art_line,note",
        )
        assert [(c.name, c.expected_output, c.metadata) for c in load_manifest()] == before

    def test_scored_columns_keep_every_old_case(self, tmp_path, monkeypatch):
        """Adding the base-exact columns can't move the legacy metrics against
        a baseline: every old case stays, with the same expected value and note."""
        def legacy_view():
            return [(c.name, c.expected_output, (c.metadata or {})["note"])
                    for c in load_manifest()]

        self.write(tmp_path, monkeypatch,
                   f"a,{s.EXPECTED_CODE},faded\nb,NONE,\nc,,\n")
        before = legacy_view()
        self.write(
            tmp_path, monkeypatch,
            f"p1,a,g1,back,{s.EXPECTED_CODE},,UNKNOWN,faded\n"
            "p2,b,g1,front,NONE,NONE,NONE,\n"
            "p3,c,g2,back,,,,\n",
            header="id,photo,garment,side,expected_art_number,expected_art_line,expected_art_base,note",
        )
        assert legacy_view() == before

    FULL = "id,photo,garment,side,expected_art_number,expected_art_base,note"

    def test_a_base_only_row_is_a_case_with_no_legacy_value(self, tmp_path, monkeypatch):
        self.write(tmp_path, monkeypatch, f"p1,a,g1,back,,{s.EXPECTED_CODE},\n",
                   header=self.FULL)
        [case] = load_manifest()
        assert case.expected_output is None
        assert case.metadata == {"note": "", "garment": "g1", "side": "back",
                                 "expected_art_base": s.EXPECTED_CODE}

    def test_legacy_unknown_beside_a_base_warns_and_keeps_the_row(
        self, tmp_path, monkeypatch, capsys
    ):
        self.write(tmp_path, monkeypatch, f"p1,a,g1,back,UNKNOWN,{s.EXPECTED_CODE},\n",
                   header=self.FULL)
        [case] = load_manifest()
        assert case.expected_output is None
        out = capsys.readouterr().out
        assert "UNKNOWN" in out and "skipping" not in out

    @pytest.mark.parametrize("legacy,base", [("", ""), ("", "UNKNOWN"), ("UNKNOWN", "")])
    def test_a_row_with_neither_value_is_skipped_with_one_line(
        self, tmp_path, monkeypatch, capsys, legacy, base
    ):
        self.write(tmp_path, monkeypatch, f"p1,a,g1,back,{legacy},{base},\n",
                   header=self.FULL)
        assert load_manifest() == []
        out = capsys.readouterr().out
        assert out.count("\n") == 1 and "skipping a" in out


class TestSentinelSafety:
    def test_no_real_art_number_decodes_as_the_sentinel(self):
        """NONE must be unreachable as a genuine code, or a real row would be
        silently scored as a negative."""
        from labels.art_number import parse

        assert parse(NO_ART_NUMBER).format is None

    def test_a_real_code_is_never_treated_as_negative(self):
        assert score("581540923", "581540923")["kind"] == "positive"

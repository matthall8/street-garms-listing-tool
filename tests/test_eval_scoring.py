"""The eval scoring path: the functions that produce every number we act on.

Nothing here touches the network. `eval_transcription` imports cleanly because
the agents in labels/transcribe.py are built lazily, so no API key is needed.

The negative-case tests matter most. A manifest row of NONE means "this photo
contains no ART number", and scoring it as an ordinary case used to divide by
zero. The fix omits `cer` entirely rather than setting it to None — pydantic-
evals rejects a None metric and discards the WHOLE case result, including
`exact`, which ConfidenceRates keys on. TestNegativeBranch pins that down.
"""

from types import SimpleNamespace

import pytest
from pydantic_evals import Case, Dataset

import eval_transcription
from eval_transcription import (
    NO_ART_NUMBER,
    ConfidenceRates,
    CorrectArtNumber,
    PerPhotoCounts,
    levenshtein,
    load_manifest,
    normalise,
)
from labels.schemas import AmbiguousCharacter, ArtNumberReading


def ctx(expected, raw, legible="clear"):
    """Stand-in for EvaluatorContext. evaluate() reads only these two attributes.

    A rename upstream would leave these tests green while the harness broke, so
    the end-to-end wiring is covered by `rates()` below instead.
    """
    return SimpleNamespace(
        expected_output=expected,
        output=ArtNumberReading(art_number_raw=raw, art_legible=legible),
    )


def score(expected, raw, legible="clear") -> dict:
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
    return {r.title: r.value for r in report.analyses}


def per_photo(photos: dict) -> tuple[dict, dict]:
    """Run photos through the real path with --repeat; return (table, rates).

    `photos` maps a name to one spec per repeat, so each read can differ. A spec
    of None makes that read fail, as an API error would. Serial, so the order
    reads are drawn in doesn't matter — only the counts are asserted.
    """
    queues = {name: iter(specs) for name, specs in photos.items()}

    def task(name):
        spec = next(queues[name])
        if spec is None:
            raise RuntimeError("read failed")
        return reading(spec)

    cases = [
        Case(name=name, inputs=name,
             expected_output=next(s for s in specs if s is not None)[0])
        for name, specs in photos.items()
    ]
    report = Dataset(
        name="per-photo",
        cases=cases,
        evaluators=[CorrectArtNumber()],
        report_evaluators=[ConfidenceRates(), PerPhotoCounts()],
    ).evaluate_sync(task, repeat=len(next(iter(photos.values()))), max_concurrency=1)

    [table] = [a for a in report.analyses if a.title == "per photo"]
    rows = {row[0]: dict(zip(table.columns, row)) for row in table.rows}
    scalars = {a.title: a.value for a in report.analyses if a.title != "per photo"}
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
    """The table the decision rule in TODO.md is read from: one row per photo,
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

    def test_rows_are_sorted_by_photo(self):
        rows, _ = per_photo({"b": [CORRECT], "a": [CORRECT]})
        assert list(rows) == ["a", "b"]

    def test_the_table_and_the_rates_count_the_same_reads(self):
        """Summed over photos, the table must reproduce the pooled rates. If
        the two ever disagree, the decision rule and the headline number are
        being judged on different definitions."""
        rows, scalars = per_photo({
            "a": [CORRECT, NOT_READ, WRONG_AND_SURE],
            "b": [NOT_READ, NOT_READ, WRONG_BUT_FLAGGED],
            "n": [CLEAN_NEGATIVE, FABRICATION, CLEAN_NEGATIVE],
        })
        positive_reads = sum(r["reads"] for r in rows.values() if r["kind"] == "positive")
        negative_reads = rows["n"]["reads"]

        def pooled(column, reads):
            return 100 * sum(r[column] or 0 for r in rows.values()) / reads

        assert pooled("missed", positive_reads) == pytest.approx(scalars["missed"])
        assert pooled("overconfident", positive_reads) == pytest.approx(scalars["overconfident"])
        assert pooled("fabricated clear", negative_reads) == pytest.approx(
            scalars["fabricated and declared clear"])


class TestLoadManifest:
    """The loader is the only thing keeping a blank row away from the evaluator.

    MANIFEST is patched on the module, which is where load_manifest looks it up
    at call time — the same rule as the transcribe patch target in CLAUDE.md.
    """

    def write(self, tmp_path, monkeypatch, body):
        manifest = tmp_path / "manifest.csv"
        manifest.write_text("photo,expected_art_number,note\n" + body, encoding="utf-8")
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
        assert load_manifest()[0].metadata["note"] == "faded garment dyed"


class TestSentinelSafety:
    def test_no_real_art_number_decodes_as_the_sentinel(self):
        """NONE must be unreachable as a genuine code, or a real row would be
        silently scored as a negative."""
        from labels.art_number import parse

        assert parse(NO_ART_NUMBER).format is None

    def test_a_real_code_is_never_treated_as_negative(self):
        assert score("581540923", "581540923")["kind"] == "positive"

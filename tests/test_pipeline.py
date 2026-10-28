"""The pipeline: transcription joined to structure and identity.

Every test here stubs transcribe(), so nothing touches the network or needs an
API key. The stub target is labels.pipeline.transcribe, NOT
labels.transcribe.transcribe — pipeline.py does `from labels.transcribe import
transcribe`, which binds the name at import time, so patching the source module
would have no effect.
"""

from dataclasses import asdict

import pytest

from labels import pipeline
from labels.art_number import parse
from labels.pipeline import extract_bytes, from_reading
from labels.schemas import (
    AmbiguousCharacter,
    ArtLegibility,
    ArtNumberReading,
    LabelReading,
)
from tests import synthetic as s

PHOTO = (b"not-really-an-image", "image/png")


@pytest.fixture
def run(monkeypatch):
    """Run the pipeline over a transcription you specify.

    Returns a callable: run(code, legibility=..., ambiguous=...) -> Extraction
    """

    def _run(code=None, legibility: ArtLegibility = "clear", ambiguous=()):
        reading = LabelReading(
            art=ArtNumberReading(
                art_number_raw=code,
                art_legible=legibility,
                ambiguous_characters=list(ambiguous),
            ),
        )
        monkeypatch.setattr(pipeline, "transcribe", lambda art: reading)
        return extract_bytes(art=PHOTO, source="test.png")

    return _run


# ---------------------------------------------------------------------------
# 1. needs_review — seven clauses; all but `format is None` can fire on their own
# ---------------------------------------------------------------------------


class TestNeedsReview:
    def test_clean_read_does_not_flag(self, run, clean_code):
        """The baseline. If this flags, every other test here is meaningless."""
        assert run(clean_code).needs_review is False

    @pytest.mark.parametrize("legibility", ["partial", "illegible", "not_visible"])
    def test_any_legibility_short_of_clear_flags(self, run, clean_code, legibility):
        assert run(clean_code, legibility=legibility).needs_review is True

    def test_ambiguous_characters_flag(self, run, clean_code):
        assert run(
            clean_code,
            ambiguous=[AmbiguousCharacter(position=1, reading="0", alternative="O")],
        ).needs_review is True

    def test_undecodable_code_flags(self, run):
        assert run("!!!not-a-code!!!").needs_review is True

    def test_correction_flags_even_when_everything_else_is_clean(
        self, run, misread_pair
    ):
        """The regression that prompted this file.

        A misread that the catalogue silently fixes used to pass as a clean
        read: the decoder parsed it, legibility was "clear", no ambiguities.
        The substitution happened with nothing on screen to say so.
        """
        misread, real = misread_pair
        result = run(misread)

        assert result.catalogue_match == "corrected"
        assert result.legibility == "clear"
        assert result.all_reads == []
        assert result.flags == []
        assert result.needs_review is True, (
            "a correction is a silent substitution and must be surfaced"
        )

    def test_catalogue_miss_does_not_flag(self, run, clean_code):
        """Deliberate: a miss is visible on the page as a missing title, and
        flagging every one would make the flag meaningless."""
        missing = clean_code[:-1] + ("Z" if clean_code[-1] != "Z" else "Y")
        result = run(missing)
        assert result.catalogue_match == "miss"
        assert result.needs_review is False


class TestNeedsReviewSynthetic:
    """Test Needs Review using synthetic data, to allow for CI testing without making
    private data public.
    """
    # One clean code per format family: an exact hit that decodes with a
    # format, a year and no flags
    BASELINES = [
        s.GATE_SI_NUMERIC, s.GATE_SI_ALPHA, s.GATE_CP_TRANSITIONAL, s.GATE_CP_MODERN,
    ]

    FAKE = {
        s.GATE_SI_NUMERIC: {"ART": s.GATE_SI_NUMERIC, "Product Name": "GATE_SI_NUMERIC"},
        s.GATE_SI_ALPHA: {"ART": s.GATE_SI_ALPHA, "Product Name": "GATE_SI_ALPHA"},
        s.GATE_CP_TRANSITIONAL: {"ART": s.GATE_CP_TRANSITIONAL, "Product Name": "GATE_CP_TRANSITIONAL"},
        s.GATE_CP_MODERN: {"ART": s.GATE_CP_MODERN, "Product Name": "GATE_CP_MODERN"},
        s.GATE_COUNTERFEIT_MARKER: {"ART": s.GATE_COUNTERFEIT_MARKER, "Product Name": "GATE_COUNTERFEIT_MARKER"},
        s.GATE_COLLAB_LINE: {"ART": s.GATE_COLLAB_LINE, "Product Name": "GATE_COLLAB_LINE"},
        s.GATE_NO_YEAR: {"ART": s.GATE_NO_YEAR, "Product Name": "GATE_NO_YEAR"},
        s.GATE_CORRECTED_KEY: {"ART": s.GATE_CORRECTED_KEY, "Product Name": "GATE_CORRECTED_KEY"},
        s.GATE_AMBIGUOUS_KEY_A: {"ART": s.GATE_AMBIGUOUS_KEY_A, "Product Name": "GATE_AMBIGUOUS_KEY_A"},
        s.GATE_AMBIGUOUS_KEY_B: {"ART": s.GATE_AMBIGUOUS_KEY_B, "Product Name": "GATE_AMBIGUOUS_KEY_B"},
        s.GATE_UNKNOWN_BRAND_GARMENT: {"ART": s.GATE_UNKNOWN_BRAND_GARMENT, "Product Name": "GATE_UNKNOWN_BRAND_GARMENT"},
    }

    @pytest.fixture(autouse=True)
    def use_synthetic_catalogue(self, monkeypatch):
        monkeypatch.setattr(
            "labels.catalogue.load_catalogue", lambda *a, **k: self.FAKE
        )

    @pytest.mark.parametrize("code", BASELINES)
    def test_clean_read_does_not_flag(self, run, code):
        """The baseline. If this flags, every other test here is meaningless."""
        result = run(code)

        assert result.matched_art == code
        assert result.catalogue_match == "exact"
        assert result.legibility == "clear"
        assert result.all_reads == []
        assert result.flags == []
        assert result.year is not None
        assert result.decoded != "Unrecognised"
        assert result.needs_review is False

    @pytest.mark.parametrize("legibility", ["partial", "illegible", "not_visible"])
    def test_any_legibility_short_of_clear_flags(self, run, legibility):
        assert run(s.GATE_SI_ALPHA, legibility=legibility).needs_review is True

    def test_ambiguous_characters_flag(self, run):
        assert run(
            s.GATE_SI_NUMERIC,
            ambiguous=[AmbiguousCharacter(position=1, reading="0", alternative="O")],
        ).needs_review is True

    @pytest.mark.parametrize("code, flag", [
        (s.GATE_COUNTERFEIT_MARKER, "possible-counterfeit-marker"),
        (s.GATE_COLLAB_LINE, "collab-or-special-line-verify-season"),
    ])
    def test_a_parser_flag_alone_flags(self, run, code, flag):
        """A flag on a code that otherwise decodes cleanly: a format, a year
        and an exact hit, so only the flags clause can fire."""
        result = run(code)

        assert result.catalogue_match == "exact"
        assert result.year is not None
        assert result.flags == [flag]
        assert result.needs_review is True

    def test_no_year_on_a_recognised_format_flags(self, run):
        """A season key outside the frozen table: the format is recognised but
        there is no year, and no flag."""
        result = run(s.GATE_NO_YEAR)

        assert parse(s.GATE_NO_YEAR).format == "cp_modern"
        assert result.catalogue_match == "exact"
        assert result.flags == []
        assert result.year is None
        assert result.needs_review is True

    @pytest.mark.parametrize(
        "code", [s.GATE_UNRECOGNISED, s.GATE_TRUNCATED, s.GATE_TRUNCATED_CP]
    )
    def test_no_format_flags_but_never_alone(self, run, code):
        """`format is None` can't fire on its own: every branch of parse() that
        returns no format also adds a flag. One code per such branch, reached
        by parse() on the code, as catalogue callers call it. In the pipeline
        each fails the split, so parse() gets "" and flags it unrecognised."""
        result = run(code)

        assert parse(code).format is None
        assert parse(code).flags
        assert result.flags != []
        assert result.needs_review is True

    def test_correction_flags_even_when_everything_else_is_clean(self, run):
        """A correction is a silent substitution and must be surfaced."""
        result = run(s.GATE_CORRECTED_READ)

        assert result.catalogue_match == "corrected"
        assert result.matched_art == s.GATE_CORRECTED_KEY
        assert result.product_name == "GATE_CORRECTED_KEY"
        assert result.flags == []
        assert result.year is not None
        assert result.needs_review is True

    def test_ambiguous_catalogue_match_flags(self, run):
        """The read is one confusion from two keys, so nothing can choose
        between them. Constructed, like `TestResolveAmbiguous`."""
        result = run(s.GATE_AMBIGUOUS_READ)

        assert result.catalogue_match == "ambiguous"
        assert result.matched_art is None
        assert result.flags == []
        assert result.year is not None
        assert result.needs_review is True

    def test_pin_catalogue_miss_does_not_flag(self, run):
        """Pins current behaviour, which ADR-0004 will change: it decides how
        catalogue misses flag (TODO.md, *Backlog*). The PR that implements
        that rule changes this test."""
        result = run(s.GATE_MISS)

        assert result.catalogue_match == "miss"
        assert result.product_name is None
        assert result.flags == []
        assert result.year is not None
        assert result.needs_review is False

    def test_pin_unknown_brand_and_garment_do_not_flag(self, run):
        """Pins current behaviour: brand and garment are for display and not in
        the gate. Which parser checks become review reasons is decided after
        the parser split (TODO.md)."""
        result = run(s.GATE_UNKNOWN_BRAND_GARMENT)

        assert result.catalogue_match == "exact"
        assert result.brand is None
        assert result.garment is None
        assert result.flags == []
        assert result.needs_review is False

    def test_unreadable_mark_in_a_clear_read_flags(self, run):
        """Any `?` flags (ADR-0005, *Flag table*). A `?` past the decoded
        prefix never resolves, so the read misses; without the flag a clear
        read would pass unflagged."""
        result = run(s.GATE_UNREADABLE_MARK)

        assert result.legibility == "clear"
        assert result.catalogue_match == "miss"
        assert result.flags == ["question_mark"]
        assert result.needs_review is True


# ---------------------------------------------------------------------------
# 2. The resolve() wiring, across every reachable status
# ---------------------------------------------------------------------------


class TestCatalogueWiring:
    def test_exact_match_carries_the_product_name(self, run, clean_code, catalogue):
        result = run(clean_code)
        assert result.catalogue_match == "exact"
        assert result.product_name == catalogue[clean_code]["Product Name"]
        assert result.matched_art == clean_code

    def test_correction_reports_both_codes(self, run, misread_pair, catalogue):
        misread, real = misread_pair
        result = run(misread)
        assert result.art_number_raw == misread
        assert result.matched_art == real
        assert result.matched_art != result.art_number_raw
        assert result.product_name == catalogue[real]["Product Name"]

    def test_miss_has_no_name_and_does_not_raise(self, run, clean_code):
        missing = clean_code[:-1] + ("Z" if clean_code[-1] != "Z" else "Y")
        result = run(missing)
        assert result.catalogue_match == "miss"
        assert result.product_name is None
        assert result.matched_art is None

    @pytest.mark.parametrize("legibility", ["not_visible", "illegible"])
    def test_unusable_read_skips_the_catalogue(self, run, clean_code, legibility):
        """Even a valid code is not looked up when the read was unusable."""
        result = run(clean_code, legibility=legibility)
        assert result.catalogue_match == "no_art_number"
        assert result.product_name is None

    def test_no_code_at_all(self, run):
        result = run(None, legibility="not_visible")
        assert result.catalogue_match == "no_art_number"
        assert result.art_number_raw is None
        assert result.decoded == "Unrecognised"


# ---------------------------------------------------------------------------
# 3. Field provenance — spot checks for swaps, not all fourteen fields
# ---------------------------------------------------------------------------


class TestFieldMapping:
    def test_ambiguous_characters_serialise_to_dicts(self, run, clean_code):
        """all_reads goes through json.dumps in the CLI, so pydantic models
        would raise. They must be plain dicts by this point."""
        result = run(
            clean_code,
            ambiguous=[AmbiguousCharacter(position=5, reading="O", alternative="0")],
        )
        assert result.all_reads == [
            {"position": 5, "reading": "O", "alternative": "0"}
        ]

    def test_source_is_carried_through(self, run, clean_code):
        assert run(clean_code).source_image == "test.png"

    def test_extraction_is_json_serialisable(self, run, clean_code):
        """main.py does json.dumps(asdict(...)) — this is the contract."""
        import json
        from dataclasses import asdict

        json.dumps(asdict(run(clean_code)))


# ---------------------------------------------------------------------------
# 4. One photo, one read
# ---------------------------------------------------------------------------


class TestOneRead:
    def test_photo_is_passed_to_transcribe(self, monkeypatch, clean_code):
        """The pipeline hands the photo through untouched."""
        seen = []

        def fake_transcribe(art):
            seen.append(art)
            return LabelReading(
                art=ArtNumberReading(art_number_raw=clean_code, art_legible="clear")
            )

        monkeypatch.setattr(pipeline, "transcribe", fake_transcribe)
        extract_bytes(art=PHOTO, source="one.png")

        assert seen == [PHOTO]

    def test_transcribe_makes_one_art_call(self, monkeypatch):
        """One API call per listing. No code needed, so this runs without the
        private catalogue."""
        from labels import transcribe as T

        calls = []
        monkeypatch.setattr(
            T, "transcribe_art",
            lambda data, media_type, model=None: calls.append((data, media_type))
            or ArtNumberReading(art_legible="not_visible"),
        )

        T.transcribe(art=PHOTO)

        assert calls == [PHOTO]

    def test_the_call_sends_the_user_message_constant(self):
        """The harness fingerprints ART_USER_MESSAGE, so it must be what is
        sent. A real agent on pydantic-ai's offline test model: no key needed."""
        from pydantic_ai import BinaryContent, capture_run_messages
        from pydantic_ai.messages import UserPromptPart

        from labels import transcribe as T

        with capture_run_messages() as messages:
            T.transcribe_art(*PHOTO, model="test")

        [user] = [p for p in messages[0].parts if isinstance(p, UserPromptPart)]
        assert user.content == [T.ART_USER_MESSAGE,
                                BinaryContent(data=PHOTO[0], media_type=PHOTO[1])]


# ---------------------------------------------------------------------------
# 5. from_reading() — what the eval replay and scorer call on a saved read
# ---------------------------------------------------------------------------


class TestFromReading:
    """from_reading() must be the app's gate, reachable without an API call.
    Synthetic catalogue, so these run in CI."""

    FAKE = {
        s.GATE_SI_NUMERIC: {"ART": s.GATE_SI_NUMERIC, "Product Name": "GATE_SI_NUMERIC"},
        s.GATE_CORRECTED_KEY: {"ART": s.GATE_CORRECTED_KEY, "Product Name": "GATE_CORRECTED_KEY"},
    }

    # One read per kind of result, with the catalogue status and gate verdict
    # it must give, so a change to the synthetic data can't quietly drop one
    READINGS = [
        pytest.param(
            ArtNumberReading(art_number_raw=s.GATE_SI_NUMERIC, art_legible="clear"),
            "exact", False, id="exact",
        ),
        pytest.param(
            ArtNumberReading(
                art_number_raw=s.GATE_SI_NUMERIC,
                art_legible="partial",
                ambiguous_characters=[
                    AmbiguousCharacter(position=4, reading="5", alternative="S")
                ],
            ),
            "exact", True, id="flagged",
        ),
        pytest.param(
            ArtNumberReading(art_number_raw=s.GATE_CORRECTED_READ, art_legible="clear"),
            "corrected", True, id="corrected",
        ),
        pytest.param(
            ArtNumberReading(art_number_raw=s.GATE_MISS, art_legible="clear"),
            "miss", False, id="miss",
        ),
        pytest.param(
            ArtNumberReading(art_legible="not_visible"),
            "no_art_number", True, id="nothing-read",
        ),
    ]

    @pytest.fixture(autouse=True)
    def use_synthetic_catalogue(self, monkeypatch):
        monkeypatch.setattr(
            "labels.catalogue.load_catalogue", lambda *a, **k: self.FAKE
        )

    def test_makes_no_api_call(self, monkeypatch):
        """The replay runs it over saved reads, so it must never transcribe."""

        def no_transcribe(art):
            raise AssertionError("from_reading() called transcribe()")

        monkeypatch.setattr(pipeline, "transcribe", no_transcribe)
        reading = ArtNumberReading(art_number_raw=s.GATE_SI_NUMERIC, art_legible="clear")
        result = from_reading(reading, source="saved.json")

        assert result.catalogue_match == "exact"
        assert result.source_image == "saved.json"

    @pytest.mark.parametrize("reading, status, needs_review", READINGS)
    def test_gives_what_extract_bytes_gives(
        self, monkeypatch, reading, status, needs_review
    ):
        """One gate, two entry points: a replay of a saved read must get what
        the app got from the same read."""
        monkeypatch.setattr(
            pipeline, "transcribe", lambda art: LabelReading(art=reading)
        )
        replayed = from_reading(reading, source="test.png")

        assert replayed.catalogue_match == status
        assert replayed.needs_review is needs_review
        assert asdict(replayed) == asdict(extract_bytes(art=PHOTO, source="test.png"))


# ---------------------------------------------------------------------------
# 6. The split (ADR-0005): what is looked up, decoded and flagged
# ---------------------------------------------------------------------------


class TestSplitWiring:
    """from_reading() splits the read: the catalogue looks up the art_base,
    parse() decodes it, and every split problem flags. Synthetic catalogue,
    so these run in CI."""

    FAKE = {
        s.GATE_SI_NUMERIC: {"ART": s.GATE_SI_NUMERIC, "Product Name": "GATE_SI_NUMERIC"},
        s.GATE_CP_MODERN: {"ART": s.GATE_CP_MODERN, "Product Name": "GATE_CP_MODERN"},
        s.GATE_FUSED_KEY: {"ART": s.GATE_FUSED_KEY, "Product Name": "GATE_FUSED_KEY"},
        s.GATE_TRUNCATED_CP: {"ART": s.GATE_TRUNCATED_CP, "Product Name": "GATE_TRUNCATED_CP"},
    }

    @pytest.fixture(autouse=True)
    def use_synthetic_catalogue(self, monkeypatch):
        monkeypatch.setattr(
            "labels.catalogue.load_catalogue", lambda *a, **k: self.FAKE
        )

    @pytest.mark.parametrize(
        "line, base",
        [
            ("ART. " + s.GATE_SI_NUMERIC, s.GATE_SI_NUMERIC),
            (s.GATE_SI_NUMERIC + "/" + s.SPLIT_COLOUR, s.GATE_SI_NUMERIC),
            (s.GATE_SI_NUMERIC + " / " + s.SPLIT_LOT_SHORT, s.GATE_SI_NUMERIC),
            (s.GATE_CP_MODERN + " " + s.SPLIT_CP_FABRIC, s.GATE_CP_MODERN),
            (s.GATE_CP_MODERN.lower(), s.GATE_CP_MODERN),
        ],
        ids=["caption", "colour", "lot", "fabric", "lower_case"],
    )
    def test_a_clean_split_looks_up_and_decodes_the_base(self, run, line, base):
        """A caption, a suffix or a lot is no problem (art_lot never flags), so
        an exact hit on a clean split's art_base doesn't flag."""
        result = run(line)

        assert result.art_number_raw == line
        assert result.art_base == base
        assert result.catalogue_match == "exact"
        assert result.matched_art == base
        assert result.decoded == parse(base).label
        assert result.year == parse(base).year
        assert result.flags == []
        assert result.needs_review is False

    @pytest.mark.parametrize(
        "line, problem",
        [
            (s.GATE_SI_NUMERIC + " " + s.SPLIT_NEXT_LINE, "art_unmatched"),
            (s.GATE_UNREADABLE_MARK, "question_mark"),
            (s.GATE_SI_NUMERIC[:4] + " " + s.GATE_SI_NUMERIC[4:], "base_shape"),
            (s.GATE_SI_NUMERIC + " ", "disallowed_character"),
        ],
        ids=["art_unmatched", "question_mark", "base_shape", "disallowed_character"],
    )
    def test_every_split_problem_flags(self, run, line, problem):
        """All are "always" (ADR-0005, *Flag table*), and each shows in flags,
        as the split names it, so a flagged read says why."""
        result = run(line)

        assert result.legibility == "clear"
        assert result.all_reads == []
        assert problem in result.flags
        assert result.needs_review is True

    def test_unmatched_tail_flags_even_on_an_exact_hit(self, run):
        """The base is kept and found, but the tail fits no known shape."""
        result = run(s.GATE_SI_NUMERIC + " " + s.SPLIT_NEXT_LINE)

        assert result.art_base == s.GATE_SI_NUMERIC
        assert result.catalogue_match == "exact"
        assert result.flags == ["art_unmatched"]
        assert result.needs_review is True

    @pytest.mark.parametrize(
        "line, candidate, problem",
        [
            (s.GATE_FUSED_KEY + "/" + s.SPLIT_COLOUR, s.GATE_FUSED_KEY, "base_shape"),
            ("ART. " + s.GATE_TRUNCATED_CP + " " + s.SPLIT_CP_FABRIC, s.GATE_TRUNCATED_CP, "art_unmatched"),
        ],
        ids=["base_shape", "no_family"],
    )
    def test_a_failed_split_looks_up_the_candidate_and_flags(
        self, run, line, candidate, problem
    ):
        """No art_base is stored; the catalogue looks up the line without its
        caption, up to the first separator, and the result always flags, even
        on an exact hit (ADR-0005, *When the split fails*)."""
        result = run(line)

        assert result.art_base is None
        assert result.catalogue_match == "exact"
        assert result.matched_art == candidate
        assert problem in result.flags
        assert result.needs_review is True

    def test_a_failed_split_is_not_decoded(self, run):
        """parse() gets "" when the split fails, so nothing is decoded from a
        base the split rejected."""
        assert parse(s.GATE_FUSED_KEY).year is not None  # the premise: the line alone decodes
        result = run(s.GATE_FUSED_KEY)

        assert result.decoded == "Unrecognised"
        assert result.year is None

    def test_the_read_is_never_repaired(self, run):
        """A 0 read for an O stays a 0: the split keeps it, parse() doesn't
        decode it, and the catalogue's swap is a correction, which flags
        (ADR-0005, *When the split fails*; CLAUDE.md, *Corrections always
        surface*)."""
        result = run(s.GATE_CP_ZERO_FOR_O)

        assert result.art_base == s.GATE_CP_ZERO_FOR_O
        assert parse(s.GATE_CP_ZERO_FOR_O).format is None
        assert result.catalogue_match == "corrected"
        assert result.matched_art == s.GATE_CP_MODERN
        assert result.needs_review is True

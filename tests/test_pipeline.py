"""The pipeline: transcription joined to structure and identity.

Every test here stubs transcribe(), so nothing touches the network or needs an
API key. The stub target is labels.pipeline.transcribe, NOT
labels.transcribe.transcribe — pipeline.py does `from labels.transcribe import
transcribe`, which binds the name at import time, so patching the source module
would have no effect.
"""

import pytest

import labels.pipeline as pipeline
from labels.pipeline import extract_bytes
from labels.schemas import (
    AmbiguousCharacter,
    ArtNumberReading,
    LabelDetails,
    LabelReading,
    SizeMarking,
)

PHOTO = (b"not-really-an-image", "image/png")


@pytest.fixture
def run(monkeypatch):
    """Run the pipeline over a transcription you specify.

    Returns a callable: run(code, legibility=..., **detail_fields) -> Extraction
    """

    def _run(code=None, legibility="clear", ambiguous=(), **details):
        reading = LabelReading(
            art=ArtNumberReading(
                art_number_raw=code,
                art_legible=legibility,
                ambiguous_characters=list(ambiguous),
            ),
            details=LabelDetails(**details),
        )
        monkeypatch.setattr(
            pipeline, "transcribe", lambda art=None, details=None: reading
        )
        return extract_bytes(art=PHOTO, source="test.png")

    return _run


# ---------------------------------------------------------------------------
# 1. needs_review — six clauses, each able to fire on its own
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
# 3. Field provenance — spot checks for swaps, not all nineteen fields
# ---------------------------------------------------------------------------


class TestFieldMapping:
    def test_details_fields_come_from_the_details_read(self, run, clean_code):
        result = run(
            clean_code,
            composition="100% Poliestere",
            made_in="Made in Italy",
            clg_number="CLG123",
            garment_colour_observed="olive green",
        )
        assert result.composition == "100% Poliestere"
        assert result.made_in == "Made in Italy"
        assert result.certilogo == "CLG123"
        assert result.colour_observed == "olive green"

    def test_sizes_join_across_systems(self, run, clean_code):
        result = run(
            clean_code,
            sizes=[
                SizeMarking(system="IT", value="50"),
                SizeMarking(system="UK", value="40"),
            ],
        )
        assert result.size == "IT 50 / UK 40"

    def test_no_sizes_gives_none_not_empty_string(self, run, clean_code):
        assert run(clean_code).size is None

    def test_brand_falls_back_to_the_printed_brand(self, run):
        """The decoder cannot name a brand it does not recognise, so the
        printed text stands in."""
        result = run("!!!not-a-code!!!", brand_printed="C.P. COMPANY")
        assert result.brand == "C.P. COMPANY"

    def test_decoder_brand_wins_over_printed(self, run, clean_code, catalogue):
        result = run(clean_code, brand_printed="SOMETHING ELSE")
        assert result.brand != "SOMETHING ELSE"

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
# 4. One photo, two reads
# ---------------------------------------------------------------------------


class TestSinglePhotoFallback:
    def test_one_photo_is_read_by_both_prompts(self, monkeypatch, clean_code):
        """The C.P. case: everything on one label, so the single photo has to
        serve both the ART read and the details read."""
        seen = []

        def fake_transcribe(art=None, details=None):
            seen.append(("art", art))
            seen.append(("details", details))
            return LabelReading(
                art=ArtNumberReading(art_number_raw=clean_code, art_legible="clear"),
                details=LabelDetails(),
            )

        monkeypatch.setattr(pipeline, "transcribe", fake_transcribe)
        extract_bytes(art=PHOTO, source="one.png")

        assert dict(seen)["art"] == PHOTO
        assert dict(seen)["details"] is None, (
            "pipeline passes both through; transcribe() owns the fallback"
        )

    def test_transcribe_falls_back_to_the_other_photo(self, monkeypatch, clean_code):
        """The fallback itself lives in transcribe(), so test it there: given
        only one photo, both reads run against it."""
        from labels import transcribe as T

        calls = []
        monkeypatch.setattr(
            T, "transcribe_art",
            lambda data, media_type, model=None: calls.append(("art", data))
            or ArtNumberReading(art_number_raw=clean_code, art_legible="clear"),
        )
        monkeypatch.setattr(
            T, "transcribe_details",
            lambda data, media_type, model=None: calls.append(("details", data))
            or LabelDetails(),
        )

        T.transcribe(art=PHOTO, details=None)

        assert [c[0] for c in calls] == ["art", "details"]
        assert calls[0][1] == calls[1][1] == PHOTO[0], (
            "both reads should have seen the same single photo"
        )

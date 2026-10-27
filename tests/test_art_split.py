import pytest

from labels.art_number import ArtSplit, split_art_line
from tests import synthetic as s


class TestFamilies:
    @pytest.mark.parametrize(
        "code",
        [
            s.SPLIT_SI_9, s.SPLIT_SI_8, s.SPLIT_SI_NAMESPACE, s.SPLIT_SI_ALPHA,
            s.SPLIT_CP_MODERN, s.SPLIT_CP_REORDER, s.SPLIT_CP_TRANSITIONAL,
            s.SPLIT_CP_TRANSITIONAL_11,
        ],
        ids=[
            "si_9", "si_8", "si_namespace", "si_alpha", "cp_modern",
            "cp_reorder", "cp_transitional", "cp_transitional_11",
        ],
    )
    def test_family_table(self, code):
        """CAP-01, BASE-01 to -06: a bare code of each family is the whole base."""
        assert split_art_line(code) == ArtSplit(art_base=code)


class TestCaption:
    def test_caption_printed_onto_the_code_is_stripped(self):
        """CAP-03"""
        assert split_art_line("ART." + s.SPLIT_SI_9) == ArtSplit(
            art_caption="ART.", art_base=s.SPLIT_SI_9
        )

    def test_code_starting_with_caption_letters_is_not_eaten(self):
        """CAP-03: without its dot, ART is text before the code, not a caption."""
        line = "ART" + s.SPLIT_SI_9
        assert split_art_line(line) == ArtSplit(
            art_unmatched=(line,), problems=("art_unmatched",)
        )

    def test_caption_then_space_is_stripped(self):
        """CAP-04"""
        assert split_art_line("ART. " + s.SPLIT_CP_MODERN) == ArtSplit(
            art_caption="ART.", art_base=s.SPLIT_CP_MODERN
        )

    @pytest.mark.parametrize("caption", ["ART.", "Art."])
    def test_caption_case_varies(self, caption):
        """CAP-05: either case is a caption, and it is kept as printed."""
        assert split_art_line(caption + s.SPLIT_SI_ALPHA) == ArtSplit(
            art_caption=caption, art_base=s.SPLIT_SI_ALPHA
        )

    @pytest.mark.parametrize("caption", ["ART NO.", "Art No."])
    def test_art_no_caption_is_stripped(self, caption):
        """CAP-06"""
        assert split_art_line(caption + " " + s.SPLIT_CP_TRANSITIONAL) == ArtSplit(
            art_caption=caption, art_base=s.SPLIT_CP_TRANSITIONAL
        )

    def test_caption_alone_is_unmatched(self):
        """A caption with nothing after it: no base, nothing unmatched, but it still flags."""
        assert split_art_line("ART.") == ArtSplit(
            art_caption="ART.", problems=("art_unmatched",)
        )

    @pytest.mark.parametrize(
        "before", ["MADE IN ITALY ", "MADE IN ITALY ART. "], ids=["text", "text_then_caption"]
    )
    def test_text_before_the_code_makes_the_line_unmatched(self, before):
        """CAP-07: the base is anchored at the start; code never searches inside the line."""
        line = before + s.SPLIT_CP_MODERN
        assert split_art_line(line) == ArtSplit(
            art_unmatched=(line,), problems=("art_unmatched",)
        )
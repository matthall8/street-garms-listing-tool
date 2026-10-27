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


WRONG_LENGTH =ArtSplit(problems=("base_shape",))


class TestBase:
    @pytest.mark.parametrize(
        "line",
        [s.SPLIT_SI_8[:-1], s.SPLIT_SI_9 + "1"],
        ids=["7", "10"],
    )
    def test_si_numeric_wrong_length_flags(self, line):
        """BASE-01: an SI numeric base is 8 or 9 characters; one too few or too many flags."""
        assert split_art_line(line) == WRONG_LENGTH

    @pytest.mark.parametrize(
        "separator", ["/", " ", " / "], ids=["slash", "space", "spaced_slash"]
    )
    def test_si_numeric_base_ends_at_a_separator(self, separator):
        """BASE-01: the base runs to the first separator; the rest is art_unmatched until step 2."""
        line = s.SPLIT_SI_9 + separator + s.SPLIT_NEXT_LINE
        assert split_art_line(line) == ArtSplit(
            art_base=s.SPLIT_SI_9,
            art_unmatched=((separator + s.SPLIT_NEXT_LINE).strip(),),
            problems=("art_unmatched",),
        )

    @pytest.mark.parametrize(
        "line, expected",
        [
            (s.SPLIT_SI_NAMESPACE, ArtSplit(art_base=s.SPLIT_SI_NAMESPACE)),
            (s.SPLIT_SI_NAMESPACE[:-1], ArtSplit(art_base=s.SPLIT_SI_NAMESPACE[:-1])),
            (s.SPLIT_SI_NAMESPACE + "1", WRONG_LENGTH),
        ],
        ids=["9", "8", "10"],
    )
    def test_si_namespace_splits_like_si_numeric(self, line, expected):
        """BASE-02: the namespace prefix has SI numeric's lengths; no season isn't the split's problem."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "line",
        [s.SPLIT_SI_ALPHA[:-1], s.SPLIT_SI_ALPHA + "1"],
        ids=["11", "13"],
    )
    def test_si_alpha_base_is_12_characters(self, line):
        """BASE-03"""
        assert split_art_line(line) == WRONG_LENGTH

    @pytest.mark.parametrize(
        "line",
        [s.SPLIT_CP_TRANSITIONAL[:-1], s.SPLIT_CP_TRANSITIONAL_11 + "1"],
        ids=["c_printed_11", "no_c_12"],
    )
    def test_cp_transitional_length_follows_the_c(self, line):
        """BASE-04: 12 with the C printed, 11 without; the other length flags."""
        assert split_art_line(line) == WRONG_LENGTH

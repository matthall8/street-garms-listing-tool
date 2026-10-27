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


BAD_BASE = ArtSplit(problems=("base_shape",))


class TestBase:
    @pytest.mark.parametrize(
        "line",
        [s.SPLIT_SI_8[:-1], s.SPLIT_SI_9 + "1"],
        ids=["7", "10"],
    )
    def test_si_numeric_wrong_length_flags(self, line):
        """BASE-01: an SI numeric base is 8 or 9 characters; one too few or too many flags."""
        assert split_art_line(line) == BAD_BASE

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
            (s.SPLIT_SI_NAMESPACE + "1", BAD_BASE),
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
        assert split_art_line(line) == BAD_BASE

    @pytest.mark.parametrize(
        "line",
        [s.SPLIT_CP_TRANSITIONAL[:-1], s.SPLIT_CP_TRANSITIONAL_11 + "1"],
        ids=["c_printed_11", "no_c_12"],
    )
    def test_cp_transitional_length_follows_the_c(self, line):
        """BASE-04: 12 with the C printed, 11 without; the other length flags."""
        assert split_art_line(line) == BAD_BASE

    @pytest.mark.parametrize(
        "line, expected",
        [
            (s.SPLIT_CP_MODERN[:-1], BAD_BASE),
            (s.SPLIT_CP_MODERN + "1", BAD_BASE),
            (
                s.SPLIT_CP_MODERN + " " + s.SPLIT_CP_FABRIC,
                ArtSplit(
                    art_base=s.SPLIT_CP_MODERN,
                    art_unmatched=(s.SPLIT_CP_FABRIC,),
                    problems=("art_unmatched",),
                ),
            ),
        ],
        ids=["9", "11", "space_then_fabric"],
    )
    def test_cp_modern_base_is_10_characters(self, line, expected):
        """BASE-05: the printed space and the fixed length agree; the fabric code waits for step 2."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "line, expected",
        [
            (s.SPLIT_CP_REORDER, ArtSplit(art_base=s.SPLIT_CP_REORDER)),
            ("RC" + s.SPLIT_CP_REORDER[2:], ArtSplit(art_base="RC" + s.SPLIT_CP_REORDER[2:])),
            (s.SPLIT_CP_REORDER + "1", BAD_BASE),
        ],
        ids=["rf", "rc", "11"],
    )
    def test_cp_reorder_prefix_is_cp_modern(self, line, expected):
        """BASE-06: a reorder prefix splits like CP modern; no season isn't the split's problem."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "code",
        [s.SPLIT_SI_9, s.SPLIT_SI_LETTER_8, s.SPLIT_SI_LETTERS_END],
        ids=["position_5", "position_8", "last_two"],
    )
    def test_si_numeric_letter_positions(self, code):
        """BASE-08 to -10: after the four digits, letters may fall anywhere."""
        assert split_art_line(code) == ArtSplit(art_base=code)

    def test_leading_zero_is_kept(self):
        """BASE-11"""
        assert split_art_line(s.SPLIT_SI_LEADING_ZERO) == ArtSplit(
            art_base=s.SPLIT_SI_LEADING_ZERO
        )

    @pytest.mark.parametrize(
        "code", [s.SPLIT_SI_ALPHA, s.SPLIT_CP_MODERN], ids=["si_alpha", "cp_modern"]
    )
    def test_lower_case_is_uppercased(self, code):
        """BASE-12: matching is in upper case, and art_base is upper case."""
        assert split_art_line(code.lower()) == ArtSplit(art_base=code)


    @pytest.mark.parametrize(
        "mark", [".", "'"], ids=["full_stop", "apostrophe"]
    )
    def test_punctuation_inside_base_flags(self, mark):
        """BASE-18: never stripped; punctuation fails the base shape."""
        assert split_art_line(s.SPLIT_SI_9[:5] + mark + s.SPLIT_SI_9[5:]) == BAD_BASE

    @pytest.mark.parametrize(
        "code", [s.SPLIT_SI_9, s.SPLIT_CP_MODERN], ids=["si_numeric", "cp_modern"]
    )
    def test_gap_inside_base_flags(self, code):
        """BASE-19: a gap ends the base early, so it fails its length. With no
        base there is nothing for a tail to follow, so the rest isn't kept."""
        assert split_art_line(code[:4] + " " + code[4:]) == BAD_BASE

    @pytest.mark.parametrize(
        "line",
        [s.GATE_TRUNCATED_CP, s.SPLIT_CP_TRANSITIONAL[2:]],
        ids=["cp_modern", "cp_transitional"],
    )
    def test_cp_without_prefix_flags(self, line):
        """BASE-21: with the season prefix missing, no family fits."""
        assert split_art_line(line) == ArtSplit(
            art_unmatched=(line,), problems=("art_unmatched",)
        )

class TestQuestionMark:
    @pytest.mark.parametrize(
        "code",
        [s.SPLIT_SI_9[:5] + "?" + s.SPLIT_SI_9[6:], s.SPLIT_CP_MODERN[:6] + "?" + s.SPLIT_CP_MODERN[7:]],
        ids=["si_numeric", "cp_modern"],
    )
    def test_question_mark_in_base_flags(self, code):
        """BASE-13: a ? stands for one character and stays where it falls; it always flags."""
        assert split_art_line(code) == ArtSplit(art_base=code, problems=("question_mark",))

    def test_question_mark_in_tail_flags(self):
        """BASE-13: wherever it falls; the base is kept."""
        tail = s.SPLIT_NEXT_LINE[:2] + "?" + s.SPLIT_NEXT_LINE[3:]
        assert split_art_line(s.SPLIT_SI_9 + " " + tail) == ArtSplit(
            art_base=s.SPLIT_SI_9,
            art_unmatched=(tail,),
            problems=("question_mark", "art_unmatched"),
        )

    @pytest.mark.parametrize("length", [9, 10, 12])
    def test_all_question_marks_flag(self, length):
        """BASE-14: every family fits, so none is picked; the whole line is art_unmatched."""
        line = "?" * length
        assert split_art_line(line) == ArtSplit(
            art_unmatched=(line,), problems=("question_mark", "art_unmatched")
        )

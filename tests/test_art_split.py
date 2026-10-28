import re

import pytest

from labels.art_number import FAMILY_TAILS, ArtSplit, parse, split_art_line
from tests import synthetic as s

FAMILIES = pytest.mark.parametrize(
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


class TestFamilies:
    @FAMILIES
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
        """BASE-01: the base runs to the first separator; a tail of no known shape is art_unmatched."""
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
                ArtSplit(art_base=s.SPLIT_CP_MODERN, art_suffix=s.SPLIT_CP_FABRIC),
            ),
        ],
        ids=["9", "11", "space_then_fabric"],
    )
    def test_cp_modern_base_is_10_characters(self, line, expected):
        """BASE-05: the printed space and the fixed length agree; the fabric code is the suffix."""
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

    @pytest.mark.parametrize(
        "line",
        ["99" + s.SPLIT_SI_9[2:], "Z" + s.SPLIT_SI_ALPHA[1:], "99" + s.SPLIT_CP_MODERN[2:]],
        ids=["si_numeric", "si_alpha", "cp_modern"],
    )
    def test_unknown_season_still_splits(self, line):
        """BASE-23: the family comes from the shape, never the season tables."""
        assert parse(line).year is None  # the premise: parse() can't date it
        assert split_art_line(line) == ArtSplit(art_base=line)


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

    @pytest.mark.parametrize(
        "line",
        ["?" + s.SPLIT_SI_ALPHA[1:], s.SPLIT_CP_TRANSITIONAL[:3] + "?" + s.SPLIT_CP_TRANSITIONAL[4:]],
        ids=["si_alpha_leading_letter", "cp_transitional_c"],
    )
    def test_question_mark_in_family_position_fitting_one_family(self, line):
        """BASE-25: one family still fits, so the line splits as usual."""
        assert split_art_line(line) == ArtSplit(art_base=line, problems=("question_mark",))

    def test_question_mark_in_family_position_is_ambiguous(self):
        """BASE-25: two families fit, so none is picked and the line is art_unmatched."""
        line = s.SPLIT_CP_MODERN[:2] + "??" + s.SPLIT_CP_MODERN[4:]  # SI numeric or CP modern
        assert split_art_line(line) == ArtSplit(
            art_unmatched=(line,), problems=("question_mark", "art_unmatched")
        )

    def test_question_mark_where_a_separator_would_be_flags(self):
        """BASE-25: a ? is never a separator, so the base runs on and fails its length."""
        line = s.SPLIT_SI_9 + "?" + s.SPLIT_NEXT_LINE
        assert split_art_line(line) == ArtSplit(problems=("question_mark", "base_shape"))

    @pytest.mark.parametrize(
        "line",
        [s.SPLIT_SI_9[:5] + "?", s.SPLIT_CP_MODERN[:6] + "?"],
        ids=["si_numeric", "cp_modern"],
    )
    def test_one_question_mark_for_several_characters_flags(self, line):
        """BASE-26: the base comes out short and fails its length."""
        assert split_art_line(line) == ArtSplit(problems=("question_mark", "base_shape"))


class TestSpacing:
    @FAMILIES
    def test_space_ends_the_base_in_every_family(self, code):
        """SPC-01: a space marks a break; a tail of no known shape is art_unmatched."""
        assert split_art_line(code + " " + s.SPLIT_NEXT_LINE) == ArtSplit(
            art_base=code, art_unmatched=(s.SPLIT_NEXT_LINE,), problems=("art_unmatched",)
        )

    def test_space_before_a_lot_code(self):
        """SPC-01: a hyphen inside the LOT code is never a separator."""
        assert split_art_line(s.SPLIT_SI_9 + " / " + s.SPLIT_LOT_SHORT) == ArtSplit(
            art_base=s.SPLIT_SI_9, art_lot=s.SPLIT_LOT_SHORT
        )

    def test_space_and_length_disagree_flags(self):
        """SPC-01: the space ends the base, then its length is checked."""
        line = s.SPLIT_CP_MODERN[:-1] + " " + s.SPLIT_CP_FABRIC
        assert split_art_line(line) == BAD_BASE

    @pytest.mark.parametrize(
        "line, expected",
        [
            (s.SPLIT_CP_MODERN[:5] + " " + s.SPLIT_CP_MODERN[5:], BAD_BASE),
            (s.SPLIT_CP_MODERN[:5] + "\t" + s.SPLIT_CP_MODERN[5:], BAD_BASE),
            (
                s.SPLIT_SI_9[:8] + " " + s.SPLIT_SI_9[8:],
                ArtSplit(
                    art_base=s.SPLIT_SI_9[:8],
                    art_unmatched=(s.SPLIT_SI_9[8:],),
                    problems=("art_unmatched",),
                ),
            ),
        ],
        ids=["cp_space", "cp_tab", "si_space_before_the_last_character"],
    )
    def test_space_inside_base_flags(self, line, expected):
        """SPC-02: a tab counts as a space. Even after the 8th of 9 SI characters
        it flags, because the last character is left as an unknown tail."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "line",
        [s.SPLIT_CP_MODERN + s.SPLIT_CP_FABRIC, s.SPLIT_SI_8 + s.SPLIT_NEXT_LINE],
        ids=["cp_fabric", "si_next_line"],
    )
    def test_tail_typed_on_without_a_separator_flags(self, line):
        """SPC-03: with no separator the base runs on and fails its length."""
        assert split_art_line(line) == BAD_BASE

    @pytest.mark.parametrize(
        "line, expected",
        [
            ("  " + s.SPLIT_SI_9 + "\t ", ArtSplit(art_base=s.SPLIT_SI_9)),
            (" ART. " + s.SPLIT_SI_9 + " ", ArtSplit(art_caption="ART.", art_base=s.SPLIT_SI_9)),
        ],
        ids=["bare", "caption"],
    )
    def test_surrounding_whitespace_is_ignored(self, line, expected):
        """SPC-04"""
        assert split_art_line(line) == expected


class TestCharacters:
    @pytest.mark.parametrize(
        "line",
        [
            s.SPLIT_SI_9[:6] + "\uff12" + s.SPLIT_SI_9[7:],
            s.SPLIT_SI_9 + "\uff0f" + s.SPLIT_NEXT_LINE,
            s.SPLIT_SI_9[:4] + "\u200b" + s.SPLIT_SI_9[4:],
            s.SPLIT_CP_MODERN[:2] + "\u0421" + s.SPLIT_CP_MODERN[3:],
            s.SPLIT_CP_MODERN + "\u00a0" + s.SPLIT_CP_FABRIC,
            s.SPLIT_SI_9 + "\u00a0",
            s.SPLIT_SI_9 + "\n" + s.SPLIT_NEXT_LINE,
        ],
        ids=[
            "full_width_digit", "full_width_slash", "zero_width_space", "cyrillic_letter",
            "non_breaking_space", "trailing_non_breaking_space", "newline_inside",
        ],
    )
    def test_non_ascii_characters_flag(self, line):
        """LINE-12: ASCII only, never normalised; anything else flags. A newline
        inside the line is outside the allowed set, so it flags here; whether it
        also gets its own multi_line flag is undecided (TODO.md)."""
        assert "disallowed_character" in split_art_line(line).problems

    @pytest.mark.parametrize(
        "line",
        [
            s.SPLIT_SI_ALPHA[:2] + "\u017f" + s.SPLIT_SI_ALPHA[3:],
            s.SPLIT_SI_8[:-1] + "\u00df",
            "ART.\u00a0" + s.SPLIT_SI_9,
        ],
        ids=["long_s_upper_cases_to_s", "sharp_s_upper_cases_to_ss", "non_breaking_space_after_caption"],
    )
    def test_non_ascii_characters_are_never_normalised_into_a_base(self, line):
        """LINE-12: no case mapping or stripping turns a non-ASCII character into
        an ASCII one, so no base is stored from it."""
        split = split_art_line(line)
        assert split.art_base is None
        assert "disallowed_character" in split.problems

    def test_tail_keeps_non_ascii_whitespace_as_read(self):
        """LINE-12: only ASCII whitespace is stripped from a tail, as from the line."""
        tail = s.SPLIT_NEXT_LINE + "\u00a0"
        assert split_art_line(s.SPLIT_SI_9 + " " + tail) == ArtSplit(
            art_base=s.SPLIT_SI_9,
            art_unmatched=(tail,),
            problems=("disallowed_character", "art_unmatched"),
        )


def unmatched(line):
    return ArtSplit(art_unmatched=(line,), problems=("art_unmatched",))


class TestWrongLine:
    def test_barcode_number_flags(self):
        """LINE-01: it starts like an SI code, so only the length check catches it."""
        assert split_art_line(s.SPLIT_BARCODE) == BAD_BASE

    @pytest.mark.parametrize(
        "line", ["Tg. M", s.SPLIT_NEXT_LINE], ids=["size_line", "variant_code"]
    )
    def test_back_tag_lines_flag(self, line):
        """LINE-02: no family fits."""
        assert split_art_line(line) == unmatched(line)

    @pytest.mark.parametrize(
        "line", [s.SPLIT_PHONE, s.SPLIT_PHONE.replace("-", "")], ids=["hyphenated", "digits_only"]
    )
    def test_phone_number_flags(self, line):
        """LINE-03: a hyphen is never a separator, so the base runs on and fails its shape."""
        assert split_art_line(line) == BAD_BASE

    def test_manufacturing_date_flags(self):
        """LINE-03: two digits then a slash fit no family's prefix."""
        assert split_art_line(s.SPLIT_DATE) == unmatched(s.SPLIT_DATE)

    @pytest.mark.parametrize(
        "line, expected",
        [(s.SPLIT_SI_9[:5], BAD_BASE), (s.SPLIT_SI_9[3:], unmatched(s.SPLIT_SI_9[3:]))],
        ids=["end_cut_off", "start_cut_off"],
    )
    def test_cut_off_fragment_flags(self, line, expected):
        """LINE-04: too short, or no family."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "line, expected",
        [
            (s.SPLIT_CERTILOGO, BAD_BASE),
            ("CLG " + s.SPLIT_CERTILOGO, unmatched("CLG " + s.SPLIT_CERTILOGO)),
        ],
        ids=["digits_only", "with_clg"],
    )
    def test_certilogo_number_flags(self, line, expected):
        """LINE-05: 12 digits is no family's length; with CLG no family fits."""
        assert split_art_line(line) == expected

    def test_postcode_flags(self):
        """LINE-05: too short."""
        assert split_art_line(s.SPLIT_POSTCODE) == BAD_BASE


def unmatched_tail(base, tail):
    return ArtSplit(art_base=base, art_unmatched=(tail,), problems=("art_unmatched",))


class TestTails:
    @pytest.mark.parametrize(
        "separator", ["/", " ", " / ", "\t"], ids=["slash", "space", "spaced_slash", "tab"]
    )
    @pytest.mark.parametrize(
        "colour", [s.SPLIT_COLOUR[:2], s.SPLIT_COLOUR[:3], s.SPLIT_COLOUR], ids=["2", "3", "4"]
    )
    def test_colour_code_is_a_suffix(self, separator, colour):
        """SUF-01: 2 to 4 digits after an SI numeric base and any separator."""
        assert split_art_line(s.SPLIT_SI_9 + separator + colour) == ArtSplit(
            art_base=s.SPLIT_SI_9, art_suffix=colour
        )

    def test_slash_letter_flags(self):
        """SUF-01: there are no single-letter suffixes."""
        assert split_art_line(s.SPLIT_SI_9 + "/Q") == unmatched_tail(s.SPLIT_SI_9, "/Q")

    def test_slash_letter_digits_is_not_a_suffix(self):
        """SUF-01: a colour code is digits only."""
        tail = "/" + s.SPLIT_NEXT_LINE[:3]
        assert split_art_line(s.SPLIT_SI_9 + tail) == unmatched_tail(s.SPLIT_SI_9, tail)

    @pytest.mark.parametrize("separator", [" ", "\t"], ids=["space", "tab"])
    @pytest.mark.parametrize("base", [s.SPLIT_CP_MODERN, s.SPLIT_CP_REORDER], ids=["cp_modern", "cp_reorder"])
    def test_cp_fabric_code_is_a_suffix(self, base, separator):
        """SUF-02: 6 digits and a letter after a CP modern base, reorder prefix
        included. A tab counts as a space."""
        assert split_art_line(base + separator + s.SPLIT_CP_FABRIC) == ArtSplit(
            art_base=base, art_suffix=s.SPLIT_CP_FABRIC
        )

    @pytest.mark.parametrize(
        "line, expected",
        [
            (
                s.SPLIT_CP_MODERN + " " + s.SPLIT_CP_FABRIC.lower(),
                ArtSplit(art_base=s.SPLIT_CP_MODERN, art_suffix=s.SPLIT_CP_FABRIC.lower()),
            ),
            (
                s.SPLIT_SI_9 + " / " + s.SPLIT_LOT_SHORT.lower(),
                ArtSplit(art_base=s.SPLIT_SI_9, art_lot=s.SPLIT_LOT_SHORT.lower()),
            ),
        ],
        ids=["suffix", "lot"],
    )
    def test_tail_case_is_kept_as_read(self, line, expected):
        """BASE-12: tails are matched in upper case and stored as read (ADR-0005, Characters)."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "separator", ["/", " ", " / "], ids=["slash", "space", "spaced_slash"]
    )
    def test_short_lot_code_is_art_lot(self, separator):
        """SUF-03: a hyphen inside the LOT code is never a separator; art_lot never flags."""
        assert split_art_line(s.SPLIT_SI_9 + separator + s.SPLIT_LOT_SHORT) == ArtSplit(
            art_base=s.SPLIT_SI_9, art_lot=s.SPLIT_LOT_SHORT
        )

    def test_long_lot_code_is_art_lot(self):
        """SUF-04"""
        assert split_art_line(s.SPLIT_SI_9 + " / " + s.SPLIT_LOT_LONG) == ArtSplit(
            art_base=s.SPLIT_SI_9, art_lot=s.SPLIT_LOT_LONG
        )

    @pytest.mark.parametrize(
        "lot", [s.SPLIT_LOT_SHORT[:-3], s.SPLIT_LOT_LONG[:-3]], ids=["short", "long"]
    )
    def test_cut_off_lot_code_is_unmatched(self, lot):
        """SUF-05: it fits neither LOT shape; the separator stays with it."""
        assert split_art_line(s.SPLIT_SI_9 + " / " + lot) == unmatched_tail(
            s.SPLIT_SI_9, "/ " + lot
        )

    def test_joined_variant_code_is_unmatched(self):
        """SUF-06: a code from the next line, joined on with a space."""
        assert split_art_line(s.SPLIT_SI_9 + " " + s.SPLIT_NEXT_LINE) == unmatched_tail(
            s.SPLIT_SI_9, s.SPLIT_NEXT_LINE
        )

    def test_variant_code_after_slash_is_unmatched(self):
        """SUF-07: an invented / doesn't make a variant code a colour code."""
        tail = "/" + s.SPLIT_NEXT_LINE
        assert split_art_line(s.SPLIT_SI_9 + tail) == unmatched_tail(s.SPLIT_SI_9, tail)

    @pytest.mark.parametrize("line", [s.SPLIT_SI_9 + "/", s.SPLIT_SI_9 + " /"], ids=["slash", "spaced_slash"])
    def test_trailing_slash_flags(self, line):
        """SUF-09: it may be a cut-off colour code, so the / is kept and flags."""
        assert split_art_line(line) == unmatched_tail(s.SPLIT_SI_9, "/")

    def test_hyphen_letter_flags(self):
        """SUF-10: a hyphen is never a separator, so the base runs on and fails its shape."""
        assert split_art_line(s.SPLIT_SI_9 + "-Q") == BAD_BASE

    def test_other_hyphen_tail_flags(self):
        """SUF-10"""
        assert split_art_line(s.SPLIT_SI_9 + "-" + s.SPLIT_COLOUR) == BAD_BASE

    def test_colour_code_then_lot_code(self):
        """SUF-12: tails are read in order, a suffix then a lot."""
        line = s.SPLIT_SI_9 + "/" + s.SPLIT_COLOUR + " / " + s.SPLIT_LOT_SHORT
        assert split_art_line(line) == ArtSplit(
            art_base=s.SPLIT_SI_9, art_suffix=s.SPLIT_COLOUR, art_lot=s.SPLIT_LOT_SHORT
        )

    @pytest.mark.parametrize(
        "line, expected",
        [
            (
                s.SPLIT_SI_9 + " / " + s.SPLIT_LOT_SHORT + " " + s.SPLIT_COLOUR,
                ArtSplit(
                    art_base=s.SPLIT_SI_9, art_lot=s.SPLIT_LOT_SHORT,
                    art_unmatched=(s.SPLIT_COLOUR,), problems=("art_unmatched",),
                ),
            ),
            (
                s.SPLIT_SI_9 + "/" + s.SPLIT_COLOUR + " " + s.SPLIT_COLOUR,
                ArtSplit(
                    art_base=s.SPLIT_SI_9, art_suffix=s.SPLIT_COLOUR,
                    art_unmatched=(s.SPLIT_COLOUR,), problems=("art_unmatched",),
                ),
            ),
            (
                s.SPLIT_SI_9 + " " + s.SPLIT_NEXT_LINE + " / " + s.SPLIT_LOT_SHORT,
                unmatched_tail(s.SPLIT_SI_9, s.SPLIT_NEXT_LINE + " / " + s.SPLIT_LOT_SHORT),
            ),
        ],
        ids=["lot_then_colour", "two_colours", "unknown_then_lot"],
    )
    def test_matching_stops_at_the_first_piece_that_fits_nothing_left(self, line, expected):
        """SUF-12, SUF-13: a piece out of order, repeated or after an unknown piece is
        art_unmatched, with everything after it."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "base, tail",
        [
            (s.SPLIT_SI_ALPHA, "/" + s.SPLIT_COLOUR),
            (s.SPLIT_CP_TRANSITIONAL, s.SPLIT_CP_FABRIC),
            (s.SPLIT_SI_9, s.SPLIT_CP_FABRIC),
            (s.SPLIT_CP_MODERN, s.SPLIT_COLOUR),
        ],
        ids=["si_alpha_colour", "cp_transitional_fabric", "si_numeric_fabric", "cp_modern_colour"],
    )
    def test_unknown_tail_is_unmatched(self, base, tail):
        """SUF-13: SI alpha and CP transitional take no tails, and a tail shape
        only follows its own family."""
        line = base + ("" if tail.startswith("/") else " ") + tail
        assert split_art_line(line) == unmatched_tail(base, tail)

    @pytest.mark.parametrize(
        "line, expected",
        [
            (
                s.SPLIT_SI_LETTERS_END[:8] + "/" + s.SPLIT_SI_LETTERS_END[8:],
                unmatched_tail(s.SPLIT_SI_LETTERS_END[:8], "/" + s.SPLIT_SI_LETTERS_END[8:]),
            ),
            (s.SPLIT_SI_LETTERS_END[:8] + "-" + s.SPLIT_SI_LETTERS_END[8:], BAD_BASE),
        ],
        ids=["slash", "hyphen"],
    )
    def test_invented_separator_before_last_letter_flags(self, line, expected):
        """SUF-16: no single-letter suffix, so / leaves an unknown tail; a hyphen
        is never a separator, so the base runs on and fails its shape."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "line, expected",
        [
            (s.SPLIT_SI_9 + " " + s.SPLIT_SI_9, unmatched_tail(s.SPLIT_SI_9, s.SPLIT_SI_9)),
            (
                (s.SPLIT_CP_MODERN + " " + s.SPLIT_CP_FABRIC + " ") * 2,
                ArtSplit(
                    art_base=s.SPLIT_CP_MODERN, art_suffix=s.SPLIT_CP_FABRIC,
                    art_unmatched=(s.SPLIT_CP_MODERN + " " + s.SPLIT_CP_FABRIC,),
                    problems=("art_unmatched",),
                ),
            ),
        ],
        ids=["si_numeric", "cp_modern_with_fabric"],
    )
    def test_code_repeated_on_the_line_flags(self, line, expected):
        """LINE-06: the second copy fits no tail shape."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "line",
        [
            s.SPLIT_SI_9 + "/" + s.SPLIT_COLOUR + " / " + s.SPLIT_LOT_SHORT,
            s.SPLIT_SI_9 + " / " + s.SPLIT_LOT_LONG + " " + s.SPLIT_COLOUR,
            s.SPLIT_SI_9 + " " + s.SPLIT_NEXT_LINE + " / " + s.SPLIT_LOT_SHORT,
            s.SPLIT_SI_9 + "/",
            s.SPLIT_CP_MODERN + " " + s.SPLIT_CP_FABRIC + " " + s.SPLIT_CP_MODERN,
            s.SPLIT_SI_ALPHA + " / " + s.SPLIT_COLOUR,
        ],
        ids=["suffix_lot", "lot_unmatched", "unmatched", "slash", "suffix_unmatched", "no_tails"],
    )
    def test_every_tail_character_lands_once(self, line):
        """When a base is kept, every character after it lands in exactly one of
        art_suffix, art_lot or art_unmatched, in that order, separators aside."""
        split = split_art_line(line)
        assert split.art_base is not None
        pieces = "".join([split.art_suffix or "", split.art_lot or "", *split.art_unmatched])
        tail = line[len(split.art_base):]
        assert re.sub(r"[ \t/]", "", pieces) == re.sub(r"[ \t/]", "", tail)


def with_mark(code, i):
    return code[:i] + "?" + code[i + 1:]


class TestTailQuestionMark:
    @pytest.mark.parametrize(
        "line, expected",
        [
            (
                s.SPLIT_SI_9 + "/" + with_mark(s.SPLIT_COLOUR, 2),
                ArtSplit(art_base=s.SPLIT_SI_9, art_suffix=with_mark(s.SPLIT_COLOUR, 2),
                         problems=("question_mark",)),
            ),
            (
                s.SPLIT_CP_MODERN + " " + with_mark(s.SPLIT_CP_FABRIC, 3),
                ArtSplit(art_base=s.SPLIT_CP_MODERN, art_suffix=with_mark(s.SPLIT_CP_FABRIC, 3),
                         problems=("question_mark",)),
            ),
            (
                s.SPLIT_CP_MODERN + " " + with_mark(s.SPLIT_CP_FABRIC, 6),
                ArtSplit(art_base=s.SPLIT_CP_MODERN, art_suffix=with_mark(s.SPLIT_CP_FABRIC, 6),
                         problems=("question_mark",)),
            ),
            (
                s.SPLIT_SI_9 + " / " + with_mark(s.SPLIT_LOT_SHORT, 1),
                ArtSplit(art_base=s.SPLIT_SI_9, art_lot=with_mark(s.SPLIT_LOT_SHORT, 1),
                         problems=("question_mark",)),
            ),
            (
                s.SPLIT_SI_9 + " / " + with_mark(s.SPLIT_LOT_SHORT, 4),
                ArtSplit(art_base=s.SPLIT_SI_9, art_lot=with_mark(s.SPLIT_LOT_SHORT, 4),
                         problems=("question_mark",)),
            ),
            (
                s.SPLIT_SI_9 + " / " + with_mark(s.SPLIT_LOT_LONG, 9),
                ArtSplit(art_base=s.SPLIT_SI_9, art_lot=with_mark(s.SPLIT_LOT_LONG, 9),
                         problems=("question_mark",)),
            ),
        ],
        ids=[
            "colour_digit", "fabric_digit", "fabric_letter", "short_lot_literal",
            "short_lot_hyphen", "long_lot_hyphen",
        ],
    )
    def test_question_mark_in_suffix_flags(self, line, expected):
        """SUF-08: a tail that a ? lets fit exactly one shape takes it, in any
        position, LOT letters and hyphens included. question_mark is a
        whole-line check, so it is still raised."""
        assert split_art_line(line) == expected

    @pytest.mark.parametrize(
        "tail",
        ["/?", "/" + s.SPLIT_COLOUR + "?", "/ " + s.SPLIT_LOT_SHORT[:-1] + "??"],
        ids=["one_character", "colour_too_long", "lot_too_long"],
    )
    def test_question_mark_fitting_no_shape_is_unmatched(self, tail):
        """SUF-08: a ? stands for exactly one character, so it never changes a
        piece's length to fit."""
        assert split_art_line(s.SPLIT_SI_9 + tail) == ArtSplit(
            art_base=s.SPLIT_SI_9, art_unmatched=(tail,),
            problems=("question_mark", "art_unmatched"),
        )

    @pytest.mark.parametrize("family", FAMILY_TAILS)
    def test_no_piece_fits_two_tail_shapes(self, family):
        """SUF-08: a ? fits any character, so an all-? piece fits a shape
        exactly when its length does. Each shape fits some length, and no
        length fits two shapes, so a ? never lets a piece fit two (ADR-0005)
        and the first match is the only one."""
        lengths = [
            {n for n in range(1, 31) if shape.fullmatch("?" * n)}
            for _, shape in FAMILY_TAILS[family]
        ]
        assert all(lengths)
        assert sum(len(fits) for fits in lengths) == len(set().union(*lengths))

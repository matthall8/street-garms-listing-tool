"""Variant generation and the resolve() ladder.

resolve() has five outcomes and they are not equally safe. "corrected" quietly
substitutes a different code for the one that was read, so the test that
matters most is the last class here: how often does correction land on the
WRONG garment?
"""

import pytest

from labels.catalogue import (
    CONFUSIONS,
    Resolution,
    art_lookup,
    normalise,
    resolve,
    variants,
)


class TestVariants:
    def test_one_substitution_per_position(self):
        # 50184868 has 7 confusable characters, so 7 variants.
        got = variants("50184868")
        assert len(got) == sum(1 for ch in "50184868" if ch in CONFUSIONS)

    def test_substitutes_only_one_character_at_a_time(self):
        for v in variants("50184868"):
            differences = sum(a != b for a, b in zip(v, "50184868"))
            assert differences == 1

    def test_finds_the_known_neighbour(self):
        assert "50184B68" in variants("50184868")

    def test_never_returns_the_original(self):
        assert "50184868" not in variants("50184868")

    def test_normalises_first(self):
        assert variants("0518 4868") == variants("05184868")

    def test_same_length_as_input(self, a_code):
        assert all(len(v) == len(a_code) for v in variants(a_code))

    @pytest.mark.parametrize("value", ["", "4327"])
    def test_nothing_to_substitute_gives_empty_list(self, value):
        assert variants(value) == []

    def test_is_reversible(self):
        """Every substitution has a partner, so the original is one hop back."""
        for v in variants("50184868"):
            assert "50184868" in variants(v)


class TestResolveGuards:
    @pytest.mark.parametrize("legibility", ["not_visible", "illegible"])
    def test_unusable_reads_short_circuit(self, legibility, a_code):
        # Even a perfectly valid code is not looked up when the read was bad.
        assert resolve(a_code, legibility).status == "no_art_number"

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty_code_short_circuits(self, value):
        assert resolve(value).status == "no_art_number"

    def test_no_art_number_carries_no_row(self):
        assert resolve(None).row is None


class TestResolveExact:
    def test_real_code_resolves_exactly(self, a_code, catalogue):
        r = resolve(a_code)
        assert r.status == "exact"
        assert r.row is catalogue[a_code]
        assert r.matched_art == a_code

    def test_exact_is_confident(self, a_code):
        assert resolve(a_code).confident

    def test_spacing_does_not_prevent_exact(self, a_code):
        assert resolve(f"{a_code[:4]} {a_code[4:]}").status == "exact"

    def test_product_name_available(self, a_code, catalogue):
        assert resolve(a_code).product_name == catalogue[a_code]["Product Name"]


class TestResolveMiss:
    def test_unknown_code_is_a_miss(self):
        r = resolve("ZZZZZZZZZ")
        assert r.status == "miss"
        assert r.row is None
        assert r.product_name is None

    def test_miss_is_not_confident(self):
        assert not resolve("ZZZZZZZZZ").confident

    def test_partial_read_with_wildcards_misses(self):
        """'?' is not a confusable character, so no variant can ever match."""
        assert resolve("05CMSH02?A").status == "miss"


def corrupt(code: str) -> list[str]:
    """Every single confusion-pair misreading of a code."""
    return [
        code[:i] + CONFUSIONS[ch] + code[i + 1:]
        for i, ch in enumerate(code)
        if ch in CONFUSIONS
    ]


class TestResolveCorrected:
    def test_recovers_a_corrupted_code(self, catalogue):
        code = next(
            k for k in catalogue
            if any(art_lookup(c) is None for c in corrupt(k))
        )
        misread = next(c for c in corrupt(code) if art_lookup(c) is None)

        r = resolve(misread)
        assert r.status == "corrected"
        assert r.matched_art == code
        assert r.row is catalogue[code]

    def test_corrected_is_not_confident(self, catalogue):
        """A correction is a guess the catalogue endorsed, not a certainty."""
        code = next(iter(catalogue))
        misread = next((c for c in corrupt(code) if art_lookup(c) is None), None)
        if misread is None:
            pytest.skip("no unambiguous corruption available for this code")
        assert not resolve(misread).confident


class TestResolveAmbiguous:
    # "0O" has two confusable positions: swapping the first gives "OO",
    # swapping the second gives "00". If both are real codes, the read sits
    # between them and nothing can choose.
    FAKE = {
        "OO": {"ART": "OO", "Brand": "X", "Type": "Y", "Product Name": "One"},
        "00": {"ART": "00", "Brand": "X", "Type": "Y", "Product Name": "Two"},
    }

    def test_two_neighbours_are_reported_as_candidates(self, monkeypatch):
        """Constructed, because no real code reaches this branch today.

        Every colliding pair in the catalogue is two REAL codes, so a misread
        lands on one of them and exits at "exact" before variants are tried.
        """
        monkeypatch.setattr(
            "labels.catalogue.load_catalogue", lambda *a, **k: self.FAKE
        )
        r = resolve("0O")
        assert r.status == "ambiguous"
        assert len(r.candidates) == 2
        assert {c["Product Name"] for c in r.candidates} == {"One", "Two"}

    def test_candidates_carry_rows_not_codes(self, monkeypatch):
        monkeypatch.setattr(
            "labels.catalogue.load_catalogue", lambda *a, **k: self.FAKE
        )
        assert all(isinstance(c, dict) for c in resolve("0O").candidates)

    def test_ambiguous_is_not_confident(self, monkeypatch):
        monkeypatch.setattr(
            "labels.catalogue.load_catalogue", lambda *a, **k: self.FAKE
        )
        r = resolve("0O")
        assert not r.confident
        assert r.row is None, "no single row should be picked when ambiguous"


class TestCorrectionSafety:
    """The number that decides whether correction can be trusted.

    Every catalogue code, corrupted every way a confusion pair allows, fed back
    through resolve(). A correction landing on a DIFFERENT garment is the
    failure that would put a wrong title on a listing.
    """

    @pytest.fixture(scope="class")
    @staticmethod
    def sweep(catalogue):
        recovered = wrong = ambiguous = missed = exact = 0
        wrong_examples = []

        for code, row in catalogue.items():
            for misread in corrupt(code):
                r = resolve(misread)
                if r.status == "exact":
                    # The corruption landed on another real code. Not a
                    # correction failure — resolve() was never asked to guess.
                    exact += 1
                elif r.status == "corrected":
                    if r.matched_art == code:
                        recovered += 1
                    else:
                        wrong += 1
                        wrong_examples.append((code, misread, r.matched_art))
                elif r.status == "ambiguous":
                    ambiguous += 1
                else:
                    missed += 1

        total = recovered + wrong + ambiguous + missed + exact
        print(
            f"\n  corruptions tested : {total}"
            f"\n  recovered correctly: {recovered} ({recovered / total:.1%})"
            f"\n  WRONG garment      : {wrong} ({wrong / total:.1%})"
            f"\n  ambiguous          : {ambiguous}"
            f"\n  landed on real code: {exact}"
            f"\n  not recovered      : {missed}"
        )
        for original, misread, got in wrong_examples[:5]:
            print(f"    {misread} -> {got}, should have been {original}")

        return {
            "total": total, "recovered": recovered, "wrong": wrong,
            "ambiguous": ambiguous, "missed": missed, "exact": exact,
        }

    def test_never_corrects_to_the_wrong_garment(self, sweep):
        assert sweep["wrong"] == 0, (
            f"{sweep['wrong']} corrections landed on a different garment"
        )

    def test_recovers_the_overwhelming_majority(self, sweep):
        recoverable = sweep["total"] - sweep["exact"]
        rate = sweep["recovered"] / recoverable
        assert rate > 0.95, f"only {rate:.1%} of misreads recovered"

    def test_nothing_silently_disappears(self, sweep):
        assert sweep["total"] == (
            sweep["recovered"] + sweep["wrong"]
            + sweep["ambiguous"] + sweep["missed"] + sweep["exact"]
        )

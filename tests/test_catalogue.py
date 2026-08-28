"""Catalogue loading and exact lookup."""

from pathlib import Path

import pytest

from labels.catalogue import art_lookup, load_catalogue, normalise, product_name


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


class TestLoadCatalogue:
    def test_missing_file_returns_empty(self):
        assert load_catalogue(Path("data/does-not-exist.csv")) == {}

    def test_keys_are_normalised(self, catalogue):
        assert all(k == normalise(k) for k in catalogue)

    def test_every_row_has_the_expected_columns(self, catalogue):
        expected = {"ART", "Brand", "Type", "Product Name"}
        assert all(expected <= set(row) for row in catalogue.values())

    def test_no_duplicate_codes(self, catalogue):
        # A dict cannot hold duplicates, so this checks the CSV itself.
        import csv

        from labels.catalogue import ART_CSV_PATH

        with open(ART_CSV_PATH, encoding="utf-8-sig") as f:
            codes = [normalise(r["ART"]) for r in csv.DictReader(f)]
        assert len(codes) == len(set(codes)), "duplicate ART numbers in the CSV"


class TestArtLookup:
    def test_every_row_looks_up_to_itself(self, catalogue):
        """The core guarantee. Would have caught the .iloc[0] bug immediately."""
        missed = [k for k, row in catalogue.items() if art_lookup(k) is not row]
        assert not missed, f"{len(missed)} rows did not resolve, e.g. {missed[:3]}"

    def test_matches_despite_spacing(self, a_code, catalogue):
        spaced = f"{a_code[:4]} {a_code[4:]}"
        assert art_lookup(spaced) is catalogue[a_code]

    def test_matches_despite_case(self, a_code, catalogue):
        assert art_lookup(a_code.lower()) is catalogue[a_code]

    def test_leading_zero_codes_resolve(self, catalogue):
        zeros = [k for k in catalogue if k.startswith("0")]
        assert zeros, "expected some codes with a leading zero"
        assert all(art_lookup(k) for k in zeros)

    @pytest.mark.parametrize("value", ["NOTAREALCODE", None, ""])
    def test_misses_return_none(self, value):
        assert art_lookup(value) is None

    def test_returns_the_whole_row(self, a_code):
        row = art_lookup(a_code)
        assert {"ART", "Brand", "Type", "Product Name"} <= set(row)


class TestProductName:
    def test_matches_the_row(self, catalogue):
        wrong = [
            k for k, row in catalogue.items()
            if product_name(k) != (row.get("Product Name") or None)
        ]
        assert not wrong, f"{len(wrong)} names did not match"

    def test_miss_returns_none(self):
        assert product_name("NOTAREALCODE") is None

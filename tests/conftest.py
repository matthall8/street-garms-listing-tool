"""Shared fixtures.

The catalogue is gitignored, so every test that needs it skips rather than
fails when it is absent. A fresh clone runs green.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels.catalogue import load_catalogue  # noqa: E402


@pytest.fixture(scope="session")
def catalogue() -> dict[str, dict]:
    rows = load_catalogue()
    if not rows:
        pytest.skip("no catalogue on disk — it is private and not in the repo")
    return rows


@pytest.fixture(scope="session")
def a_code(catalogue) -> str:
    """Any real ART number, for tests that just need a known-good one."""
    return next(iter(catalogue))


def _parses_cleanly(code: str) -> bool:
    """Decodes with a year and no flags, so needs_review depends only on the
    thing a test is actually varying."""
    from labels.art_number import parse

    decoded = parse(code)
    return bool(decoded.format and decoded.year and not decoded.flags)


@pytest.fixture(scope="session")
def clean_code(catalogue) -> str:
    """A catalogue code that also decodes cleanly, so a pipeline run over it
    yields needs_review=False. Derived from the catalogue rather than hardcoded,
    so these tests survive the catalogue changing."""
    for code in catalogue:
        if _parses_cleanly(code):
            return code
    pytest.skip("no catalogue code decodes cleanly")


@pytest.fixture(scope="session")
def misread_pair(catalogue) -> tuple[str, str]:
    """(misread, real) where the misread is one confusion-pair substitution
    away, is NOT itself in the catalogue, and still decodes cleanly.

    That last condition is what makes it useful: the decoder is happy, so any
    needs_review it triggers must come from the correction itself.
    """
    from labels.catalogue import CONFUSIONS, art_lookup

    for code in catalogue:
        if not _parses_cleanly(code):
            continue
        for i, ch in enumerate(code):
            if ch not in CONFUSIONS:
                continue
            misread = code[:i] + CONFUSIONS[ch] + code[i + 1:]
            if art_lookup(misread) is None and _parses_cleanly(misread):
                return misread, code
    pytest.skip("no clean misread/real pair available")

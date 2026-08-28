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

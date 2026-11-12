"""What the Docker build can see and copy, checked statically.

CI never has data/, .env or images/, so a CI build can't show they stay out
of the image. These tests guard the two files that keep them out instead:
`.dockerignore` blocks everything and allows a fixed list, and the
Dockerfile never copies the whole build context. The real proof is the hand
check on a machine that has the private files.
"""

import json
import posixpath
import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# What the image needs. Letting more in (the frontend build, say) means
# changing this set in the same PR, so a reviewer sees what was added.
ALLOWED = {"app", "labels", "pyproject.toml", "uv.lock"}


def _clean(path: str) -> str:
    """Normalise a context path as Docker does: '/app/' and './app' are 'app'."""
    return posixpath.normpath(path.strip()).lstrip("/") or "."


def _ignore_rules(text: str) -> list[str]:
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _instructions(text: str) -> list[tuple[str, str]]:
    """(KEYWORD, arguments) for each instruction, continuation lines joined."""
    found = []
    for line in re.sub(r"\\[ \t]*\n", " ", text).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keyword, _, args = line.partition(" ")
            found.append((keyword.upper(), args.strip()))
    return found


def _context_sources(args: str) -> list[str]:
    """The sources a COPY or ADD takes from the build context.

    None for `--from`, which copies from another image or stage.
    """
    flags = []
    while args.startswith("--"):
        flag, _, args = args.partition(" ")
        flags.append(flag)
        args = args.strip()
    if any(flag.startswith("--from") for flag in flags):
        return []
    words = json.loads(args) if args.startswith("[") else shlex.split(args)
    return words[:-1]


def _is_broad(source: str) -> bool:
    """The whole context, or a wildcard at its top level."""
    path = _clean(source)
    return path == "." or any(char in path.split("/")[0] for char in "*?[")


def _copies(text: str) -> list[tuple[str, list[str]]]:
    return [
        (f"{keyword} {args}", _context_sources(args))
        for keyword, args in _instructions(text)
        if keyword in {"COPY", "ADD"}
    ]


def _broad_copies(text: str) -> list[str]:
    return [line for line, sources in _copies(text) if any(map(_is_broad, sources))]


class TestDockerignore:
    rules = _ignore_rules((ROOT / ".dockerignore").read_text())

    def test_blocks_everything_first(self):
        assert self.rules[:1] == ["*"]

    def test_allows_only_what_the_image_needs(self):
        allowed = {_clean(rule[1:]) for rule in self.rules if rule.startswith("!")}
        assert allowed == ALLOWED


class TestDockerfile:
    text = (ROOT / "Dockerfile").read_text()

    def test_copies_found(self):
        assert any(sources for _, sources in _copies(self.text))

    def test_never_copies_the_whole_context(self):
        assert _broad_copies(self.text) == []


class TestBroadCopyCheck:
    """The check itself, on invented lines."""

    @pytest.mark.parametrize("line", [
        "COPY . .",
        "COPY ./ /srv/app/",
        "ADD . /srv/app",
        "COPY * ./",
        "COPY --chown=app . .",
        'COPY [".", "/srv/app"]',
        "COPY . \\\n    /srv/app",
    ])
    def test_flags_a_broad_copy(self, line):
        assert len(_broad_copies(line)) == 1

    @pytest.mark.parametrize("line", [
        "COPY pyproject.toml uv.lock ./",
        "COPY app ./app",
        "COPY --from=builder /srv/app/.venv ./.venv",
        "COPY --from=ghcr.io/example/tool:1.0 / /opt/tool",
    ])
    def test_allows_an_explicit_copy(self, line):
        assert _broad_copies(line) == []

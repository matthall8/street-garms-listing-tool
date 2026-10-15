"""The module boundaries CLAUDE.md describes under *Flow*, checked statically.

Imports are read with ast rather than by importing anything, so a violation
can't hide behind a lazy import inside a function, and nothing here needs an
API key. tests/ is left out on purpose: the route tests import `app`.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted([*(ROOT / "labels").glob("*.py"), *(ROOT / "app").glob("*.py"), ROOT / "main.py"])

API_CLIENTS = {"pydantic_ai", "anthropic", "openai", "httpx", "requests", "urllib.request"}


def _module(path: Path) -> str:
    """labels/catalogue.py -> labels.catalogue, app/__init__.py -> app."""
    parts = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(path: Path) -> list[tuple[int, str]]:
    """(line, module) for every import anywhere in the file.

    `from a import b` yields both a and a.b, since b may be a submodule.
    Relative imports are resolved against the file's package.
    """
    package = _module(path) if path.name == "__init__.py" else _module(path).rpartition(".")[0]
    found = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                base = f"{anchor}.{base}" if base else anchor
            found.append((node.lineno, base))
            found += [(node.lineno, f"{base}.{alias.name}") for alias in node.names]
    return found


def _within(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


def _violations(paths, forbidden) -> list[str]:
    return [
        f"{path.relative_to(ROOT)}:{line} imports {name}"
        for path in paths
        for line, name in _imports(path)
        if forbidden(name)
    ]


def _source(relative: str) -> Path:
    path = ROOT / relative
    assert path.exists(), f"{relative} is gone: update tests/test_boundaries.py"
    return path


class TestImportGraph:
    def test_sources_found(self):
        assert _source("labels/transcribe.py") in SOURCES
        assert _source("main.py") in SOURCES
        assert any(path.parent.name == "app" for path in SOURCES)

    def test_only_transcribe_imports_an_api_client(self):
        others = [p for p in SOURCES if p != _source("labels/transcribe.py")]
        bad = _violations(others, lambda name: any(_within(name, c) for c in API_CLIENTS))
        assert not bad, (
            "CLAUDE.md, Engineering constraints: labels/transcribe.py is the only "
            "module permitted to call an API.\n" + "\n".join(bad)
        )

    def test_schemas_imports_nothing_of_ours(self):
        bad = _violations([_source("labels/schemas.py")], lambda name: _within(name, "labels"))
        assert not bad, (
            "CLAUDE.md, Flow: schemas.py is shared vocabulary and imports "
            "nothing of ours.\n" + "\n".join(bad)
        )

    @pytest.mark.parametrize(
        "importer, imported",
        [("art_number", "catalogue"), ("catalogue", "art_number")],
    )
    def test_decoder_and_catalogue_stay_apart(self, importer, imported):
        bad = _violations(
            [_source(f"labels/{importer}.py")],
            lambda name: _within(name, f"labels.{imported}"),
        )
        assert not bad, (
            "CLAUDE.md, Flow: art_number.py and catalogue.py don't know about "
            "each other; pipeline.py is where they meet.\n" + "\n".join(bad)
        )

    def test_nothing_imports_app_or_main(self):
        bad = [
            v
            for top in ("app", "main")
            for v in _violations(
                # app/ importing its own submodules is not a violation.
                [p for p in SOURCES if not _within(_module(p), top)],
                lambda name, top=top: _within(name, top),
            )
        ]
        assert not bad, "CLAUDE.md, Flow: nothing imports app/ or main.py.\n" + "\n".join(bad)

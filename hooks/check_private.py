#!/usr/bin/env python3
"""Block a commit that adds a private value.

The repo is public; the catalogue, the photos and the eval manifests (dev and
held-out) are not. This checks what a commit adds against the real private
values, locally, where they exist (CI never can). Standard library only, so
it runs before `uv sync`.

    check_private.py                      the staged diff (pre-commit)
    check_private.py --commit-msg FILE    a commit message (commit-msg)
    check_private.py --range main...HEAD  committed changes and their messages
    check_private.py --file PATH          any text file, every line (a PR body)
    check_private.py --text STRING        a string, every line (a PR title)

Each finding prints as "private value (<type>) in <file>:<line>", never the
value itself; line 0 means the file's path. Any finding, or any error, exits 1.
An error prints only its exception type, and bad arguments only a fixed line:
either message could hold a value.

A value is flagged per file, when the added lines hold it more often than the
removed lines. Editing a line that already carries a value passes; a new value,
a swapped one or one moved to another file does not.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

ALLOWLIST = "hooks/allowed.sha256"
LEDGER_FILES = ("evals/BASELINES.md", "TODO.md")
LEDGER_HEADER = re.compile(r"^\|\s*date\s*\|\s*md5\s*\|")
HOLDOUT_LEDGER_HEADER = re.compile(r"^\|\s*date\s*\|\s*holdout\s+md5\s*\|")
MD5 = re.compile(r"\b[0-9a-f]{32}\b")

# The reviewer's two patterns. Code-shaped is ASCII, as `git grep -P` is.
CODE_SHAPED = re.compile(r"\b(?=(?:[A-Z]*[0-9]){4})[0-9A-Z]{8,12}\b", re.ASCII)
IMAGE_NAME = re.compile(r"[\w./-]*\w\.(?:jpe?g|png|heic|heif|webp)\b", re.IGNORECASE)

# Where CLAUDE.md allows code-shaped literals. Whole files, or one region of
# a file, found by name in its staged version.
PATTERN_EXEMPT_FILES = {"uv.lock", "tests/synthetic.py", "evals/manifest.example.csv"}
PATTERN_EXEMPT_REGIONS = {
    "labels/transcribe.py": "ART_PROMPT",
    "labels/art_number.py": "__doc__",
}

# Every manifest column, classified. A column not listed here is a KeyError,
# so a new column blocks until someone decides which kind it is.
MANIFEST_COLUMNS = {
    "photo": "private",
    "expected_art_number": "private",
    "expected_line": "private",
    "expected_style": "private",
    "note": "public",
    "id": "public",
}
NO_CODE = {"", "NONE"}
MIN_NAME_WORDS = 3

ASCII_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def normalise(art_number: str | None) -> str:
    """labels/catalogue.py's `normalise`: strip spacing and case."""
    return "".join((art_number or "").split()).upper()


def digest(value: str) -> str:
    """The allowlist form of a value: SHA-256 of it normalised."""
    return hashlib.sha256(normalise(value).encode()).hexdigest()


def fold(text: str) -> str:
    return " ".join(text.casefold().split())


@dataclass
class Private:
    codes: dict[str, str] = field(default_factory=dict)  # normalised → type
    names: dict[str, list[tuple[str, re.Pattern]]] = field(default_factory=dict)
    filenames: set[str] = field(default_factory=set)  # from every manifest
    photos: re.Pattern | None = None

    def lengths(self) -> list[int]:
        return sorted({len(c) for c in self.codes})

    def compile_photos(self) -> None:
        """One pattern over the filenames of every manifest loaded, so a
        second manifest adds to the first rather than replacing it."""
        alternatives = sorted({fold(f) for f in self.filenames if f}, key=len, reverse=True)
        if alternatives:
            body = "|".join(re.escape(a).replace(r"\ ", r"\s+") for a in alternatives)
            self.photos = re.compile(r"(?<!\w)(?:" + body + r")(?!\w)", re.IGNORECASE)


def load_catalogue(path: Path, private: Private) -> None:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        if not {"ART", "Product Name"} <= set(reader.fieldnames or ()):
            raise ValueError("catalogue is missing a column")
        rows = list(reader)
    for row in rows:
        if None in row or None in row.values():
            raise ValueError("catalogue row has the wrong number of fields")
        if key := normalise(row["ART"]):
            private.codes[key] = "catalogue_key"
        name = fold(row["Product Name"])
        words = re.findall(r"\w+", name)
        if len(name.split()) >= MIN_NAME_WORDS and words:
            pattern = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
            private.names.setdefault(words[0], []).append((name, pattern))
    if not private.codes:
        raise ValueError("catalogue has no keys")


def load_manifest(path: Path, private: Private) -> None:
    """Add a manifest's codes and filenames. A manifest with a header and no
    rows is an error, so a new manifest's first row and the first row of its
    md5 ledger go in together."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        columns = list(reader.fieldnames or ())
        kinds = {column: MANIFEST_COLUMNS[column] for column in columns}
        if "photo" not in kinds:
            raise ValueError("manifest has no photo column")
        rows = list(reader)
    if not rows:
        raise ValueError("manifest has no rows")
    for row in rows:
        if None in row or None in row.values():
            raise ValueError("manifest row has the wrong number of fields")
        for column, kind in kinds.items():
            value = row[column].strip()
            if kind != "private" or not value:
                continue
            if column == "photo":
                private.filenames |= {value, Path(value).stem}
            elif normalise(value) not in NO_CODE:
                private.codes.setdefault(normalise(value), "expected_code")


def code_hits(line: str, private: Private, lengths: list[int]) -> list[tuple[str, str]]:
    """Codes on the line, ignoring spacing and case, starting and ending on a
    token edge so a code never matches inside a longer token."""
    upper = line.translate(ASCII_UPPER)
    idx = [i for i, c in enumerate(line) if not c.isspace()]
    joined = "".join(upper[i] for i in idx)
    hits = []
    for j, i in enumerate(idx):
        if i > 0 and line[i - 1].isalnum():
            continue
        for length in lengths:
            if j + length > len(idx):
                break
            last = idx[j + length - 1]
            if last + 1 < len(line) and line[last + 1].isalnum():
                continue
            value = joined[j:j + length]
            if kind := private.codes.get(value):
                hits.append((kind, value))
    return hits


def private_hits(line: str, private: Private, lengths: list[int]) -> list[tuple[str, str]]:
    hits = code_hits(line, private, lengths) if lengths else []
    if private.names:
        folded = fold(line)
        for word in set(re.findall(r"\w+", folded)):
            for name, pattern in private.names.get(word, ()):
                hits += [("product_name", name)] * len(pattern.findall(folded))
    if private.photos is not None:
        hits += [("photo_filename", fold(m)) for m in private.photos.findall(line)]
    return hits


def pattern_hits(line: str, tracked: Callable[[str], bool]) -> list[tuple[str, str]]:
    hits = [("code_shaped", m) for m in CODE_SHAPED.findall(line)]
    hits += [("image_filename", m) for m in IMAGE_NAME.findall(line) if not tracked(m)]
    return hits


@dataclass
class FileChange:
    added: list[tuple[int, str]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def unquote(path: str) -> str:
    path = path.rstrip("\t")
    if path.startswith('"') and path.endswith('"'):
        path = re.sub(r'\\(["\\])', r"\1", path[1:-1]).replace(r"\t", "\t").replace(r"\n", "\n")
    return path


def hunk_start(header: str) -> int:
    """The first new-file line number from an `@@ -a,b +c,d @@` header."""
    m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", header)
    if m is None:
        raise ValueError("unreadable hunk header")
    return int(m.group(1))


def parse_diff(text: str) -> dict[str, FileChange]:
    """Added lines (with new line numbers) and removed lines, per file. A
    deleted file's lines count under its old path, anything else's under its
    new one, so an edit inside a renamed file nets out."""
    changes: dict[str, FileChange] = {}
    old = new = None
    change = None
    line_no = 0
    in_hunk = False
    for raw in text.split("\n"):
        if raw.startswith("diff --git "):
            old = new = change = None
            in_hunk = False
        elif not in_hunk:
            if raw.startswith("--- "):
                old = unquote(raw[4:])
            elif raw.startswith("+++ "):
                new = unquote(raw[4:])
            elif raw.startswith("@@"):
                in_hunk = True
                name = new if new and new != "/dev/null" else old
                if name is None or name == "/dev/null":
                    raise ValueError("diff hunk without a file")
                change = changes.setdefault(name[2:], FileChange())
        if not in_hunk or change is None:
            continue
        if raw.startswith("@@"):
            line_no = hunk_start(raw)
        elif raw.startswith("+"):
            change.added.append((line_no, raw[1:]))
            line_no += 1
        elif raw.startswith("-"):
            change.removed.append(raw[1:])
        elif raw.startswith(" "):
            line_no += 1
    return changes


def net_findings(
    label: str,
    change: FileChange,
    scan: Callable[[str], list[tuple[str, str]]],
    allowed: set[str],
    skip_lines: Collection[int] = (),
) -> set[tuple[str, str, int]]:
    """(type, file, line) for each value the change adds more often than it
    removes, at every added line that holds it."""
    added = [
        (n, hit)
        for n, text in change.added
        if n not in skip_lines
        for hit in scan(text)
        if digest(hit[1]) not in allowed
    ]
    removed = Counter(hit for text in change.removed for hit in scan(text))
    counts = Counter(hit for _, hit in added)
    over = {hit for hit, c in counts.items() if c > removed[hit]}
    return {(hit[0], label, n) for n, hit in added if hit in over}


def exempt_lines(source: str | None, region: str) -> set[int] | None:
    """Line numbers of ART_PROMPT or the module docstring, or None if the
    file doesn't parse (then nothing in it is exempt)."""
    if source is None:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        if region == "__doc__":
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                return set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
            return set()
        targets = node.targets if isinstance(node, ast.Assign) else []
        if any(isinstance(t, ast.Name) and t.id == region for t in targets):
            return set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return set()


def git_bytes(*args: str, input: bytes | None = None, ok: tuple[int, ...] = (0,)) -> bytes:
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        input=input,
        capture_output=True,
    )
    if result.returncode not in ok:
        raise RuntimeError("git failed")
    return result.stdout


def git(*args: str, input: bytes | None = None, ok: tuple[int, ...] = (0,)) -> str:
    return git_bytes(*args, input=input, ok=ok).decode("utf-8", errors="replace")


def read_blobs(rev: str, paths: list[str]) -> dict[str, str | None]:
    """Files as committed at `rev` (":" for the index), None where absent,
    from one git process."""
    out = git_bytes("cat-file", "--batch", input="".join(f"{rev}{p}\n" for p in paths).encode())
    blobs: dict[str, str | None] = {}
    pos = 0
    for path in paths:
        end = out.index(b"\n", pos)
        header = out[pos:end].split()
        pos = end + 1
        blobs[path] = None
        if len(header) == 3:  # <sha> <type> <size>, then the content
            size = int(header[2])
            if header[1] == b"blob":
                blobs[path] = out[pos:pos + size].decode("utf-8", errors="replace")
            pos += size + 1
    return blobs


def changed_paths(diff: str) -> list[str]:
    """Paths added, copied, modified, renamed (the new name) or retyped, from
    the `--raw` lines that lead the diff. Binary files have no hunks, so this
    is the only place a staged photo shows up."""
    paths = []
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            break
        if line.startswith(":"):
            meta, *names = line.split("\t")
            if names and meta.split()[-1][0] in "ACMRT":
                paths.append(unquote(names[-1]))
    return paths


def load_allowlist(text: str | None) -> set[str]:
    allowed = set()
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", line):
            raise ValueError("allowlist line is not a SHA-256 hash")
        allowed.add(line)
    return allowed


def last_ledger_md5(text: str, header: re.Pattern) -> str | None:
    last = None
    in_table = False
    for line in text.splitlines():
        if header.match(line):
            in_table = True
        elif in_table:
            if not line.startswith("|"):
                break
            cells = line.split("|")
            if len(cells) > 2 and (m := MD5.search(cells[2])):
                last = m.group(0)
    return last


def check_md5(
    manifest: Path, show: Callable[[str], str | None], header: re.Pattern, label: str
) -> str | None:
    """None if the manifest's md5 is the last row of the ledger table under
    `header`, else the problem, naming the manifest by `label`."""
    actual = hashlib.md5(manifest.read_bytes()).hexdigest()
    found = find_ledger(show, header)
    if found is None:
        return f"{label} exists but its md5 ledger was not found: add a ledger row"
    name, text = found
    if last_ledger_md5(text, header) == actual:
        return None
    return (
        f"{label} md5 does not match the last row of its md5 ledger in {name}: "
        "an unrecorded ground-truth edit needs a ledger row"
    )


def find_ledger(show: Callable[[str], str | None], header: re.Pattern) -> tuple[str, str] | None:
    """The first ledger file with a table under `header`, and its text."""
    for name in LEDGER_FILES:
        text = show(name)
        if text is not None and any(header.match(line) for line in text.splitlines()):
            return name, text
    return None


def message_lines(text: str, comment: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """The message up to the `commit -v` scissors line: every line, and the
    lines that aren't comments. Without an editor (`-m`, `-F`) git keeps
    comment lines, so the real-value checks read every line; the patterns
    skip comments, where git's own status text would trip them."""
    lines = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith(f"{comment} ") and ">8" in line:
            break
        lines.append((n, line))
    return lines, [(n, line) for n, line in lines if not line.startswith(comment)]


def private_file(roots: list[Path], name: str) -> Path:
    """The gitignored file in this worktree or, from a linked worktree, in the
    main one, which is the only place it exists. The main worktree is the
    parent of the common git dir; in a submodule that parent holds no data
    file, so the lookup misses and the check skips, as with no file at all."""
    return next((root / name for root in roots if (root / name).exists()), roots[0] / name)


class Parser(argparse.ArgumentParser):
    """argparse quotes a bad argument back, and that argument could be the
    value being checked (a mistyped `--text`). Say only that it was bad."""

    def error(self, message: str) -> NoReturn:
        self.exit(1, "check_private: bad arguments; see --help\n")


def run(argv: list[str]) -> int:
    parser = Parser(description="Block a commit that adds a private value.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--commit-msg", metavar="FILE", type=Path)
    mode.add_argument("--range", metavar="A...B")
    mode.add_argument("--file", metavar="PATH", type=Path)
    mode.add_argument("--text", metavar="STRING")
    parser.add_argument("--catalogue", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--manifest", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--holdout", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    roots = [Path(".")]
    if not (args.catalogue and args.manifest and args.holdout):
        top, common = git(
            "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"
        ).splitlines()
        roots = [Path(top), Path(common).parent]
    catalogue = args.catalogue or private_file(roots, "data/art-number.csv")
    manifest = args.manifest or private_file(roots, "evals/manifest.csv")
    holdout = args.holdout or private_file(roots, "evals/holdout/manifest.csv")

    private = Private()
    if catalogue.exists():
        load_catalogue(catalogue, private)
    else:
        print("check_private: no catalogue; catalogue checks skipped", file=sys.stderr)
    if manifest.exists():
        load_manifest(manifest, private)
    else:
        print("check_private: no manifest; manifest and md5 checks skipped", file=sys.stderr)
    if holdout.exists():
        load_manifest(holdout, private)
    else:
        print("check_private: no held-out set; holdout checks skipped", file=sys.stderr)
    private.compile_photos()
    lengths = private.lengths()

    if args.range:
        base, dots, tip = args.range.rpartition("...")
        if not dots:
            base, dots, tip = args.range.rpartition("..")
        if not dots:
            raise ValueError("range needs .. or ...")
        tip = tip or "HEAD"
        rev = f"{tip}:"
        diff_args = [args.range]
    else:
        rev = ":"
        diff_args = ["--cached"]

    blobs = read_blobs(rev, [ALLOWLIST, *LEDGER_FILES])

    def show(path: str) -> str | None:
        if path not in blobs:
            blobs.update(read_blobs(rev, [path]))
        return blobs[path]

    allowed = load_allowlist(show(ALLOWLIST))
    findings: set[tuple[str, str, int]] = set()
    problems: list[str] = []

    # /open-pr and the reviewer fail on the catalogue and dev manifest notices
    # but ignore the held-out one, which is normal until the set exists. Once
    # its ledger has a row, a missing file means unchecked values, so block.
    found = find_ledger(show, HOLDOUT_LEDGER_HEADER)
    if not holdout.exists() and found and last_ledger_md5(found[1], HOLDOUT_LEDGER_HEADER):
        problems.append(
            "no holdout manifest, but its md5 ledger has rows: its values can't be checked"
        )

    def scan_private(text: str) -> list[tuple[str, str]]:
        return private_hits(text, private, lengths)

    if args.commit_msg or args.file or args.text is not None:
        # Text with nothing to net against, so every line counts as added. No
        # tracked-image exception: a message, PR body or title holds no
        # filenames at all.
        if args.commit_msg:
            comment = git("config", "--get", "core.commentChar", ok=(0, 1)).strip() or "#"
            if comment == "auto":
                comment = "#"
            text = args.commit_msg.read_text(encoding="utf-8", errors="replace")
            label = "commit message"
            lines, pattern_lines = message_lines(text, comment)
        elif args.file:
            text = args.file.read_text(encoding="utf-8", errors="replace")
            label, lines = str(args.file), list(enumerate(text.splitlines(), 1))
            pattern_lines = lines
        else:
            label, lines = "text", list(enumerate(args.text.splitlines(), 1))
            pattern_lines = lines
        findings |= net_findings(label, FileChange(added=lines), scan_private, allowed)
        findings |= net_findings(
            label, FileChange(added=pattern_lines), lambda t: pattern_hits(t, lambda _: False), allowed
        )
    else:
        tracked_paths: set[str] = set()
        listed = False

        def tracked(name: str) -> bool:
            nonlocal listed
            if not listed:  # only once an image filename turns up
                listing = (
                    git("ls-tree", "-r", "--name-only", "-z", tip)
                    if args.range
                    else git("ls-files", "-z")
                )
                tracked_paths.update(filter(None, listing.split("\0")))
                listed = True
            name = name.removeprefix("./")
            return name in tracked_paths or any(p.endswith("/" + name) for p in tracked_paths)

        diff = git(
            "diff", *diff_args, "--raw", "--patch", "--no-color", "--no-ext-diff",
            "--no-textconv", "--find-renames", "-U0", "--src-prefix=a/", "--dst-prefix=b/",
        )
        for path, change in parse_diff(diff).items():
            findings |= net_findings(path, change, scan_private, allowed)
            if path in PATTERN_EXEMPT_FILES:
                continue
            skip = None
            if path in PATTERN_EXEMPT_REGIONS:
                skip = exempt_lines(show(path), PATTERN_EXEMPT_REGIONS[path])
            findings |= net_findings(
                path, change, lambda t: pattern_hits(t, tracked), allowed, skip or ()
            )

        paths = changed_paths(diff)
        for path in paths:
            findings |= {(k, path, 0) for k, v in scan_private(path) if digest(v) not in allowed}
        if paths:
            ignored = git(
                "check-ignore", "--no-index", "-z", "--stdin",
                input="\0".join(paths).encode(), ok=(0, 1),
            )
            findings |= {("ignored_path", p, 0) for p in ignored.split("\0") if p}

        if args.range:
            log_range = f"{base}..{tip}" if base else tip
            log = git("log", "--format=%h%x00%B%x00", log_range)
            parts = log.split("\0")
            for i in range(0, len(parts) - 1, 2):
                sha, body = parts[i], parts[i + 1]
                label = f"commit {sha.strip()} message"
                change = FileChange(added=list(enumerate(body.splitlines(), 1)))
                findings |= net_findings(label, change, scan_private, allowed)
                findings |= net_findings(
                    label, change, lambda t: pattern_hits(t, lambda _: False), allowed
                )

        ledgers = [
            (manifest, LEDGER_HEADER, "manifest"),
            (holdout, HOLDOUT_LEDGER_HEADER, "holdout manifest"),
        ]
        for path, header, label in ledgers:
            if path.exists() and (problem := check_md5(path, show, header, label)):
                problems.append(problem)

    # A value that is private is reported once, as private.
    located = {(f, n) for t, f, n in findings if t not in ("code_shaped", "image_filename")}
    findings = {
        (t, f, n)
        for t, f, n in findings
        if t not in ("code_shaped", "image_filename") or (f, n) not in located
    }
    for kind, path, line in sorted(findings, key=lambda x: (x[1], x[2], x[0])):
        print(f"private value ({kind}) in {path}:{line}")
    for problem in problems:
        print(problem)
    return 1 if findings or problems else 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 — fail closed on anything
        print(f"check_private: blocked by an internal error ({type(e).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

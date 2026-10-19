"""hooks/check_private.py against synthetic data.

Every test gets a throwaway git repo with an invented catalogue and manifest
from tests/synthetic.py, and passes their paths on the command line. Nothing
here reads the real private data, so this runs in CI.

Most tests call the script's `main` in-process, for speed. The crash path and
the installed git hooks run as subprocesses, as git runs them.
"""

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from labels.catalogue import normalise
from tests import synthetic as s

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "check_private.py"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

# No inherited GIT_* state (as inside a hook) and no user or system config.
CLEAN_GIT = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
GIT_IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.com"]


def load_script():
    spec = importlib.util.spec_from_file_location("check_private", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_private"] = module  # dataclasses look the module up
    spec.loader.exec_module(module)
    return module


check_private = load_script()


def ledger(md5: str, column: str = "md5") -> str:
    return f"| date | {column} | what changed |\n|---|---|---|\n| 2026-01-01 | `{md5}` | synthetic |\n"


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str


def git_env() -> dict[str, str]:
    return {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, **CLEAN_GIT}


class Repo:
    def __init__(self, base: Path, monkeypatch=None, capsys=None):
        self.monkeypatch, self.capsys = monkeypatch, capsys
        self.path = base / "repo"
        self.catalogue = base / "private" / "catalogue.csv"
        self.manifest = base / "private" / "manifest.csv"
        self.holdout = base / "private" / "holdout.csv"  # absent until add_holdout()

    @classmethod
    def create(cls, base: Path) -> "Repo":
        repo = cls(base)
        repo.path.mkdir()
        repo.catalogue.parent.mkdir()
        repo.catalogue.write_text(
            "ART,Brand,Type,Product Name\n"
            f"{s.KEY},Brand,Jacket,{s.NAME}\n"
            f"{s.OTHER_KEY},Brand,Shirt,{s.SHORT_NAME}\n"
            f"{s.COMPOUND_KEY},Brand,Shirt,\n"
        )
        repo.manifest.write_text(
            "photo,expected_art_number,note\n"
            f"{s.PHOTO},{s.EXPECTED_CODE},clear\n"
            f"{s.NEGATIVE_PHOTO},NONE,not_visible\n"
        )
        repo.git("init", "-q", "-b", "main")
        repo.write("TODO.md", ledger(repo.manifest_md5()))
        repo.commit("start")
        return repo

    def manifest_md5(self) -> str:
        return hashlib.md5(self.manifest.read_bytes()).hexdigest()

    def holdout_md5(self) -> str:
        return hashlib.md5(self.holdout.read_bytes()).hexdigest()

    def add_holdout(self) -> None:
        """Opt in to a held-out manifest, its ledger table committed beside
        the dev one."""
        self.holdout.write_text(
            "photo,expected_art_number,note\n"
            f"{s.HOLDOUT_PHOTO},{s.HOLDOUT_EXPECTED_CODE},clear\n"
        )
        self.write("TODO.md", ledger(self.manifest_md5()) + "\n" + ledger(self.holdout_md5(), "holdout md5"))
        self.commit("holdout ledger")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *GIT_IDENTITY, *args],
            cwd=self.path, env=git_env(), capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    def write(self, name: str, text: str) -> Path:
        path = self.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def stage(self, name: str, text: str) -> None:
        self.write(name, text)
        self.git("add", "--", name)

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("-c", f"core.hooksPath={os.devnull}", "commit", "-q", "-m", message)

    def argv(self, args, catalogue, manifest) -> list[str]:
        return [
            "--catalogue", str(catalogue or self.catalogue),
            "--manifest", str(manifest or self.manifest),
            "--holdout", str(self.holdout),
            *args,
        ]

    def check(self, *args: str, catalogue=None, manifest=None) -> Result:
        """main() in-process, from inside the repo."""
        mp, capsys = self.monkeypatch, self.capsys
        assert mp and capsys
        mp.chdir(self.path)
        mp.setattr(sys, "argv", ["check_private.py", *self.argv(args, catalogue, manifest)])
        capsys.readouterr()
        code = check_private.main()
        out = capsys.readouterr()
        return Result(code, out.out, out.err)

    def check_subprocess(self, *args: str) -> Result:
        """The script as git runs it: its own process, its own output."""
        result = subprocess.run(
            [sys.executable, SCRIPT, *self.argv(args, None, None)],
            cwd=self.path, env=git_env(), capture_output=True, text=True,
        )
        return Result(result.returncode, result.stdout, result.stderr)


@pytest.fixture(scope="session")
def template(tmp_path_factory) -> Path:
    """One repo built once; each test gets a copy, which is much faster than
    git init plus a first commit."""
    base = tmp_path_factory.mktemp("template")
    mp = pytest.MonkeyPatch()
    for k in [k for k in os.environ if k.startswith("GIT_")]:
        mp.delenv(k)
    Repo.create(base)
    mp.undo()
    return base


@pytest.fixture
def repo(template, tmp_path, monkeypatch, capsys) -> Repo:
    for k in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(k)
    for k, v in CLEAN_GIT.items():
        monkeypatch.setenv(k, v)
    shutil.copytree(template, tmp_path, dirs_exist_ok=True, symlinks=True)
    return Repo(tmp_path, monkeypatch, capsys)


def blocked(result, kind: str, where: str) -> bool:
    return result.returncode == 1 and f"private value ({kind}) in {where}" in result.stdout


def internal_error(result) -> bool:
    return result.returncode == 1 and "blocked by an internal error" in result.stderr


def leaks(result) -> list[str]:
    output = result.stdout + result.stderr
    return [v for v in s.ALL if v in output]


class TestCatalogueKeys:
    def test_added_key_blocks(self, repo):
        repo.stage("notes.md", f"intro\nsee {s.KEY} here\n")
        assert blocked(repo.check(), "catalogue_key", "notes.md:2")

    def test_removed_key_passes(self, repo):
        repo.write("notes.md", f"see {s.KEY}\n")
        repo.commit("add")
        repo.stage("notes.md", "see nothing\n")
        assert repo.check().returncode == 0

    def test_swapped_key_blocks(self, repo):
        repo.write("notes.md", f"see {s.KEY}\n")
        repo.commit("add")
        repo.stage("notes.md", f"see {s.OTHER_KEY}\n")
        assert blocked(repo.check(), "catalogue_key", "notes.md:1")

    def test_editing_a_line_that_keeps_its_key_passes(self, repo):
        repo.write("notes.md", f"- [ ] check {s.KEY}\n")
        repo.commit("add")
        repo.stage("notes.md", f"- [x] check {s.KEY}\n")
        assert repo.check().returncode == 0

    def test_editing_a_key_line_in_a_renamed_file_passes(self, repo):
        filler = "".join(f"line {i}\n" for i in range(10))  # enough for git to see a rename
        repo.write("a.md", f"{filler}- [ ] check {s.KEY}\n")
        repo.commit("add")
        repo.git("mv", "a.md", "b.md")
        repo.stage("b.md", f"{filler}- [x] check {s.KEY}\n")
        assert repo.check().returncode == 0

    def test_key_moved_to_another_file_blocks(self, repo):
        repo.write("a.md", f"see {s.KEY}\n")
        repo.commit("add")
        repo.git("rm", "-q", "a.md")
        repo.stage("b.md", f"unrelated\nsee {s.KEY} too\n")
        assert blocked(repo.check(), "catalogue_key", "b.md:2")

    def test_key_with_spacing_and_case_blocks(self, repo):
        repo.stage("notes.md", f"printed as {s.COMPOUND_PRINTED}\n")
        assert blocked(repo.check(), "catalogue_key", "notes.md:1")

    def test_key_at_the_end_of_a_longer_token_passes(self, repo):
        repo.stage("notes.md", f"ref{s.KEY}\n")
        assert repo.check().returncode == 0

    def test_key_at_the_start_of_a_longer_token_passes(self, repo):
        repo.stage("notes.md", f"{s.KEY}x\n")
        assert repo.check().returncode == 0

    def test_allowlisted_hash_passes(self, repo):
        digest = hashlib.sha256(normalise(s.KEY).encode()).hexdigest()
        repo.stage("hooks/allowed.sha256", f"# example\n{digest}\n")
        repo.stage("notes.md", f"see {s.KEY}\n")
        assert repo.check().returncode == 0

    def test_unstaged_allowlist_does_not_count(self, repo):
        digest = hashlib.sha256(normalise(s.KEY).encode()).hexdigest()
        repo.write("hooks/allowed.sha256", f"{digest}\n")
        repo.stage("notes.md", f"see {s.KEY}\n")
        assert blocked(repo.check(), "catalogue_key", "notes.md:1")


class TestProductNames:
    def test_product_name_blocks(self, repo):
        repo.stage("notes.md", f"the {s.NAME.lower()}, in navy\n")
        assert blocked(repo.check(), "product_name", "notes.md:1")

    def test_a_single_word_from_a_name_passes(self, repo):
        repo.stage("notes.md", f"an {s.NAME_WORD} in navy\n")
        assert repo.check().returncode == 0

    def test_a_two_word_name_passes(self, repo):
        repo.stage("notes.md", f"a {s.SHORT_NAME}\n")
        assert repo.check().returncode == 0


class TestManifestValues:
    def test_photo_filename_blocks(self, repo):
        repo.stage("notes.md", f"photo {s.PHOTO} is blurred\n")
        assert blocked(repo.check(), "photo_filename", "notes.md:1")

    def test_photo_stem_blocks(self, repo):
        repo.stage("notes.md", f"photo {s.PHOTO_STEM} is blurred\n")
        assert blocked(repo.check(), "photo_filename", "notes.md:1")

    def test_photo_filename_in_a_path_blocks(self, repo):
        repo.stage(f"fixtures/{s.PHOTO_STEM}.txt", "nothing private inside\n")
        assert blocked(repo.check(), "photo_filename", f"fixtures/{s.PHOTO_STEM}.txt:0")

    def test_expected_code_blocks(self, repo):
        repo.stage("notes.md", f"expected {s.EXPECTED_CODE}\n")
        assert blocked(repo.check(), "expected_code", "notes.md:1")

    def test_categorical_values_pass(self, repo):
        repo.stage("notes.md", "legibility clear, not_visible, expected NONE\n")
        assert repo.check().returncode == 0


class TestManifestColumns:
    """Each column added for run 0 loads, and is private or public as
    classified. A column the hook can't classify blocks every commit."""

    def with_column(self, repo, column: str, value: str) -> None:
        repo.manifest.write_text(f"photo,{column},note\n{s.PHOTO},{value},\n")
        repo.stage("TODO.md", ledger(repo.manifest_md5()))  # so only the value can block

    @pytest.mark.parametrize("column", ["expected_art_line", "expected_art_base"])
    def test_expected_values_block(self, repo, column):
        self.with_column(repo, column, s.EXPECTED_CODE)
        repo.stage("notes.md", f"expected {s.EXPECTED_CODE}\n")
        assert blocked(repo.check(), "expected_code", "notes.md:1")

    @pytest.mark.parametrize(
        ("column", "value"), [("id", "r07"), ("garment", "g03"), ("side", "back")]
    )
    def test_grouping_values_pass(self, repo, column, value):
        self.with_column(repo, column, value)
        repo.stage("notes.md", f"{column} {value} is blurred\n")
        assert repo.check().returncode == 0

    @pytest.mark.parametrize("column", ["expected_line", "expected_style"])
    def test_names_before_the_glossary_block(self, repo, column):
        """Renamed in GLOSSARY.md; a manifest still using them must not pass."""
        self.with_column(repo, column, s.EXPECTED_CODE)
        assert internal_error(repo.check())

    def test_example_manifest_columns_are_classified(self):
        header = (ROOT / "evals" / "manifest.example.csv").read_text().splitlines()[0]
        assert set(header.split(",")) <= set(check_private.MANIFEST_COLUMNS)


class TestPatterns:
    def test_code_shaped_token_blocks(self, repo):
        repo.stage("notes.md", f"try {s.CODE_SHAPED}\n")
        assert blocked(repo.check(), "code_shaped", "notes.md:1")

    def test_code_shaped_token_in_art_prompt_passes(self, repo):
        repo.stage("labels/transcribe.py", f'ART_PROMPT = """\nlike {s.CODE_SHAPED}\n"""\n')
        assert repo.check().returncode == 0

    def test_code_shaped_token_elsewhere_in_transcribe_blocks(self, repo):
        repo.stage(
            "labels/transcribe.py",
            f'ART_PROMPT = """\nplain\n"""\nOTHER = "{s.CODE_SHAPED}"\n',
        )
        assert blocked(repo.check(), "code_shaped", "labels/transcribe.py:4")

    def test_code_shaped_token_in_art_number_docstring_passes(self, repo):
        repo.stage("labels/art_number.py", f'"""Formats.\n\nlike {s.CODE_SHAPED}\n"""\n')
        assert repo.check().returncode == 0

    def test_code_shaped_token_after_art_number_docstring_blocks(self, repo):
        repo.stage(
            "labels/art_number.py",
            f'"""Formats."""\n\nOTHER = "{s.CODE_SHAPED}"\n',
        )
        assert blocked(repo.check(), "code_shaped", "labels/art_number.py:3")

    def test_code_shaped_token_in_synthetic_passes(self, repo):
        repo.stage("tests/synthetic.py", f'X = "{s.CODE_SHAPED}"\n')
        assert repo.check().returncode == 0

    def test_image_filename_blocks(self, repo):
        repo.stage("notes.md", f"see {s.IMAGE}\n")
        assert blocked(repo.check(), "image_filename", "notes.md:1")

    def test_reference_to_a_tracked_image_passes(self, repo):
        repo.write(f"assets/{s.IMAGE}", "not really an image\n")
        repo.commit("add asset")
        repo.stage("notes.md", f"see assets/{s.IMAGE}\n")
        assert repo.check().returncode == 0

    def test_force_added_ignored_path_blocks(self, repo):
        repo.write(".gitignore", "secret/\n")
        repo.commit("ignore")
        repo.write("secret/notes.txt", "nothing\n")
        repo.git("add", "-f", "secret/notes.txt")
        assert blocked(repo.check(), "ignored_path", "secret/notes.txt:0")


class TestCommitMessage:
    def message(self, repo, text: str):
        path = repo.write(".git/COMMIT_EDITMSG", text)
        return repo.check("--commit-msg", str(path))

    def test_key_in_a_message_blocks(self, repo):
        assert blocked(self.message(repo, f"fix: read {s.KEY}\n"), "catalogue_key", "commit message:1")

    def test_clean_message_passes(self, repo):
        assert self.message(repo, "fix: a clean message\n").returncode == 0

    def test_patterns_skip_comments_and_verbose_diff_is_ignored(self, repo):
        text = (
            "fix: a clean message\n"
            f"# {s.CODE_SHAPED}\n"
            "# ------------------------ >8 ------------------------\n"
            f"+see {s.KEY}\n"
        )
        assert self.message(repo, text).returncode == 0

    def test_key_in_a_comment_line_blocks(self, repo):
        # As `git commit -m` writes it: no editor, so git keeps `#` lines.
        text = f"fix: a clean message\n\n# see {s.KEY}\n"
        assert blocked(self.message(repo, text), "catalogue_key", "commit message:3")


class TestFileAndText:
    """For a PR body and title: every line counts, `#` lines included."""

    def test_file_checks_every_line(self, repo):
        body = repo.write("pr-body.md", f"## Review\n# {s.KEY}\nclean\n")
        assert blocked(repo.check("--file", str(body)), "catalogue_key", f"{body}:2")
        body.write_text("## Review\nclean\n")
        assert repo.check("--file", str(body)).returncode == 0

    def test_text_is_checked(self, repo):
        assert blocked(repo.check("--text", f"feat: the {s.NAME}"), "product_name", "text:1")
        assert repo.check("--text", "feat: block private values").returncode == 0

    @pytest.mark.parametrize(
        "args",
        [["--txt", f"feat: the {s.NAME}"], ["--text", "clean", s.KEY]],
        ids=["mistyped flag", "stray argument"],
    )
    def test_bad_arguments_print_no_value(self, repo, capsys, args):
        with pytest.raises(SystemExit) as exit_:
            repo.check(*args)
        out = capsys.readouterr()
        assert exit_.value.code == 1
        assert out.err == "check_private: bad arguments; see --help\n"
        assert leaks(Result(1, out.out, out.err)) == []


class TestRange:
    def test_committed_key_blocks(self, repo):
        repo.git("switch", "-q", "-c", "topic")
        repo.write("notes.md", f"see {s.KEY}\n")
        repo.commit("docs: notes")
        assert blocked(repo.check("--range", "main...HEAD"), "catalogue_key", "notes.md:1")

    def test_key_in_a_commit_message_blocks(self, repo):
        repo.git("switch", "-q", "-c", "topic")
        repo.write("notes.md", "nothing\n")
        repo.commit(f"docs: about {s.KEY}")
        result = repo.check("--range", "main...HEAD")
        assert result.returncode == 1
        assert "private value (catalogue_key) in commit " in result.stdout

    # The passing tests below commit, then stage a change so the index no
    # longer agrees with the tip: a pass means range mode read the tip.

    def test_allowlist_is_read_from_the_tip(self, repo):
        repo.git("switch", "-q", "-c", "topic")
        digest = hashlib.sha256(normalise(s.KEY).encode()).hexdigest()
        repo.write("hooks/allowed.sha256", f"{digest}\n")
        repo.write("notes.md", f"see {s.KEY}\n")
        repo.commit("docs: notes")
        repo.git("rm", "-q", "hooks/allowed.sha256")
        assert repo.check("--range", "main...HEAD").returncode == 0

    def test_art_prompt_region_is_read_from_the_tip(self, repo):
        repo.git("switch", "-q", "-c", "topic")
        repo.write("labels/transcribe.py", f'ART_PROMPT = """\nlike {s.CODE_SHAPED}\n"""\n')
        repo.commit("feat: prompt")
        repo.git("rm", "-q", "labels/transcribe.py")
        assert repo.check("--range", "main...HEAD").returncode == 0

    def test_tracked_images_are_listed_from_the_tip(self, repo):
        repo.write(f"assets/{s.IMAGE}", "not really an image\n")
        repo.commit("add asset")
        repo.git("switch", "-q", "-c", "topic")
        repo.write("notes.md", f"see assets/{s.IMAGE}\n")
        repo.commit("docs: notes")
        repo.git("rm", "-q", f"assets/{s.IMAGE}")
        assert repo.check("--range", "main...HEAD").returncode == 0

    def test_md5_mismatch_blocks(self, repo):
        repo.git("switch", "-q", "-c", "topic")
        repo.write("notes.md", "nothing\n")
        repo.commit("docs: notes")
        with repo.manifest.open("a") as f:
            f.write("zz_another,NONE,\n")
        result = repo.check("--range", "main...HEAD")
        assert result.returncode == 1
        assert "unrecorded ground-truth edit needs a ledger row" in result.stdout

    def test_ledger_is_read_from_the_tip(self, repo):
        repo.git("switch", "-q", "-c", "topic")
        with repo.manifest.open("a") as f:
            f.write("zz_another,NONE,\n")
        repo.write("TODO.md", ledger(repo.manifest_md5()))
        repo.commit("docs: ledger row")
        repo.git("rm", "-q", "TODO.md")
        assert repo.check("--range", "main...HEAD").returncode == 0


class TestDataFiles:
    def test_missing_catalogue_skips(self, repo, tmp_path):
        # Not code-shaped, so only the catalogue check could catch it.
        repo.stage("notes.md", f"see {s.COMPOUND_PRINTED}\n")
        result = repo.check(catalogue=tmp_path / "absent.csv")
        assert result.returncode == 0
        assert "catalogue checks skipped" in result.stderr

    def test_missing_manifest_skips(self, repo, tmp_path):
        repo.stage("notes.md", f"photo {s.PHOTO_STEM}\n")
        result = repo.check(manifest=tmp_path / "absent.csv")
        assert result.returncode == 0
        assert "manifest and md5 checks skipped" in result.stderr

    def test_linked_worktree_with_no_data_anywhere_skips(self, repo, tmp_path, monkeypatch, capsys):
        linked = tmp_path / "linked"
        repo.git("worktree", "add", "-q", "-b", "topic", str(linked))
        monkeypatch.chdir(linked)
        monkeypatch.setattr(sys, "argv", ["check_private.py"])
        capsys.readouterr()
        assert check_private.main() == 0
        err = capsys.readouterr().err
        assert "catalogue checks skipped" in err
        assert "manifest and md5 checks skipped" in err
        assert "holdout checks skipped" in err

    def test_catalogue_missing_a_column_blocks(self, repo):
        repo.catalogue.write_text(f"Brand,Product Name\nBrand,{s.NAME}\n")
        assert internal_error(repo.check())

    def test_empty_catalogue_blocks(self, repo):
        repo.catalogue.write_text("ART,Brand,Type,Product Name\n")
        assert internal_error(repo.check())

    def test_ragged_manifest_blocks(self, repo):
        repo.manifest.write_text(f"photo,expected_art_number,note\n{s.PHOTO},NONE,a,extra\n")
        repo.stage("TODO.md", ledger(repo.manifest_md5()))  # so only the row can block
        assert internal_error(repo.check())

    def test_crash_blocks_and_names_only_the_exception_type(self, repo):
        # An unclassified column is a KeyError whose message is the column
        # name, invented here to look like a code.
        repo.manifest.write_text(f"photo,{s.UNKNOWN_COLUMN}\n{s.PHOTO},{s.KEY}\n")
        repo.stage("notes.md", f"see {s.NAME} and {s.EXPECTED_CODE}\n")
        result = repo.check_subprocess()
        assert result.returncode == 1
        assert result.stderr.strip() == "check_private: blocked by an internal error (KeyError)"
        assert result.stdout == ""
        assert leaks(result) == []


class TestManifestMd5:
    def test_matching_md5_passes(self, repo):
        repo.stage("notes.md", "nothing\n")
        assert repo.check().returncode == 0

    def test_md5_mismatch_blocks(self, repo):
        with repo.manifest.open("a") as f:
            f.write("zz_another,NONE,\n")
        result = repo.check()
        assert result.returncode == 1
        assert "unrecorded ground-truth edit needs a ledger row" in result.stdout

    def test_staged_ledger_row_passes(self, repo):
        with repo.manifest.open("a") as f:
            f.write("zz_another,NONE,\n")
        repo.stage("TODO.md", ledger("0" * 32) + f"| 2026-01-02 | `{repo.manifest_md5()}` | row added |\n")
        assert repo.check().returncode == 0

    def test_unstaged_ledger_row_does_not_count(self, repo):
        with repo.manifest.open("a") as f:
            f.write("zz_another,NONE,\n")
        repo.write("TODO.md", ledger(repo.manifest_md5()))
        assert repo.check().returncode == 1


class TestHoldout:
    """The held-out manifest, loaded beside the dev one. Each test opts in, so
    the rest of the suite runs without it."""

    @pytest.fixture
    def held(self, repo):
        repo.add_holdout()
        return repo

    def append_row(self, path: Path) -> None:
        with path.open("a") as f:
            f.write("zz_another,NONE,\n")

    def test_holdout_photo_filename_blocks(self, held):
        held.stage("notes.md", f"photo {s.HOLDOUT_PHOTO} is blurred\n")
        assert blocked(held.check(), "photo_filename", "notes.md:1")

    def test_holdout_photo_stem_blocks(self, held):
        held.stage("notes.md", f"photo {s.HOLDOUT_PHOTO_STEM} is blurred\n")
        assert blocked(held.check(), "photo_filename", "notes.md:1")

    def test_holdout_expected_code_blocks(self, held):
        held.stage("notes.md", f"expected {s.HOLDOUT_EXPECTED_CODE}\n")
        assert blocked(held.check(), "expected_code", "notes.md:1")

    def test_dev_photo_still_blocks(self, held):
        held.stage("notes.md", f"photo {s.PHOTO_STEM} is blurred\n")
        assert blocked(held.check(), "photo_filename", "notes.md:1")

    def test_matching_holdout_md5_passes(self, held):
        held.stage("notes.md", "nothing\n")
        result = held.check()
        assert result.returncode == 0
        assert "skipped" not in result.stderr

    def test_holdout_md5_mismatch_blocks(self, held):
        self.append_row(held.holdout)
        result = held.check()
        assert result.returncode == 1
        assert "holdout manifest md5 does not match" in result.stdout
        assert "unrecorded ground-truth edit needs a ledger row" in result.stdout

    def test_staged_holdout_ledger_row_passes(self, held):
        self.append_row(held.holdout)
        held.stage(
            "TODO.md",
            ledger(held.manifest_md5()) + "\n" + ledger("0" * 32, "holdout md5")
            + f"| 2026-01-02 | `{held.holdout_md5()}` | row added |\n",
        )
        assert held.check().returncode == 0

    def test_dev_ledger_row_does_not_satisfy_the_holdout(self, repo):
        # The same bytes as the dev manifest, so the dev table's last row
        # carries the holdout's md5 too; only a holdout table counts.
        shutil.copy(repo.manifest, repo.holdout)
        result = repo.check()
        assert result.returncode == 1
        assert result.stdout.splitlines() == [
            "holdout manifest exists but its md5 ledger was not found: add a ledger row"
        ]

    def test_missing_holdout_skips_while_dev_checks_run(self, repo):
        repo.stage("notes.md", f"photo {s.PHOTO_STEM}\n")
        self.append_row(repo.manifest)
        result = repo.check()
        assert blocked(result, "photo_filename", "notes.md:1")
        assert "manifest md5 does not match" in result.stdout
        assert "holdout checks skipped" in result.stderr
        assert "manifest and md5 checks skipped" not in result.stderr

    def test_missing_holdout_with_an_empty_ledger_passes(self, repo):
        # The state before the set exists: a ledger table with no rows.
        empty = "| date | holdout md5 | what changed |\n|---|---|---|\n"
        repo.stage("TODO.md", ledger(repo.manifest_md5()) + "\n" + empty)
        result = repo.check()
        assert result.returncode == 0
        assert "holdout checks skipped" in result.stderr

    @pytest.mark.parametrize("args", [[], ["--text", "feat: clean"]], ids=["staged", "text"])
    def test_missing_holdout_with_ledger_rows_blocks(self, repo, args):
        repo.stage("TODO.md", ledger(repo.manifest_md5()) + "\n" + ledger("0" * 32, "holdout md5"))
        result = repo.check(*args)
        assert result.returncode == 1
        assert "no holdout manifest, but its md5 ledger has rows" in result.stdout

    def test_header_only_holdout_blocks(self, repo):
        # Fails closed: the first row and its ledger row go in together.
        repo.holdout.write_text("photo,expected_art_number,note\n")
        assert internal_error(repo.check())


class TestWrappers:
    """The real hooks, installed in the throwaway repo. No catalogue or
    manifest there, so only the pattern checks can block."""

    @pytest.fixture
    def hooked(self, repo):
        # Linked, not copied: macOS vets each new executable on first run,
        # which costs more than the commit.
        (repo.path / "hooks").symlink_to(ROOT / "hooks")
        if (ROOT / ".venv").exists():  # the wrappers prefer it, as in a real clone
            (repo.path / ".venv").symlink_to(ROOT / ".venv")
        repo.write(".git/info/exclude", "hooks\n.venv\n")
        return repo

    def commit(self, repo, message: str):
        return subprocess.run(
            ["git", *GIT_IDENTITY, "-c", "core.hooksPath=hooks", "commit", "-q", "-m", message],
            cwd=repo.path, env=git_env(), capture_output=True, text=True,
        )

    def test_pre_commit_blocks(self, hooked):
        hooked.stage("notes.md", f"try {s.CODE_SHAPED}\n")
        result = self.commit(hooked, "docs: notes")
        assert result.returncode != 0
        assert "private value (code_shaped) in notes.md:1" in result.stderr  # git routes hook output there
        assert hooked.git("diff", "--cached", "--name-only").strip() == "notes.md"

    def test_commit_msg_blocks(self, hooked):
        hooked.stage("notes.md", "nothing\n")
        result = self.commit(hooked, f"docs: try {s.CODE_SHAPED}")
        assert result.returncode != 0
        assert "private value (code_shaped) in commit message:1" in result.stderr

    def test_clean_commit_passes(self, hooked):
        hooked.stage("notes.md", "nothing\n")
        assert self.commit(hooked, "docs: notes").returncode == 0

    def test_linked_worktree_reads_the_main_worktrees_data(self, hooked, tmp_path):
        # The private files sit gitignored in the main worktree only, as in a
        # real clone; an agent's worktree has none of its own.
        hooked.add_holdout()
        shutil.copy(hooked.catalogue, hooked.write("data/art-number.csv", ""))
        shutil.copy(hooked.manifest, hooked.write("evals/manifest.csv", ""))
        shutil.copy(hooked.holdout, hooked.write("evals/holdout/manifest.csv", ""))
        hooked.write(
            ".git/info/exclude", "hooks\n.venv\ndata/\nevals/manifest.csv\nevals/holdout/\n"
        )
        linked = Repo(tmp_path / "linked")
        hooked.git("worktree", "add", "-q", "-b", "topic", str(linked.path))
        (linked.path / "hooks").symlink_to(ROOT / "hooks")
        if (ROOT / ".venv").exists():
            (linked.path / ".venv").symlink_to(ROOT / ".venv")
        # Not code-shaped, so only the catalogue check could catch it.
        linked.stage("notes.md", f"see {s.COMPOUND_PRINTED}\n")
        result = self.commit(linked, "docs: notes")
        assert result.returncode != 0
        assert "private value (catalogue_key) in notes.md:1" in result.stderr
        assert "skipped" not in result.stderr


@pytest.mark.parametrize(
    "value",
    [None, "", "  ", "abc", " a b c ", "a\tb\nc", "a b", "0012 34", "x-y/z",
     s.COMPOUND_PRINTED, s.KEY.lower()],
)
def test_normalise_matches_the_catalogue(value):
    assert check_private.normalise(value) == normalise(value)

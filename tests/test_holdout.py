"""--holdout: the gate's run mode, and --holdout --check, the test-set checks.

The point of the flag is what it doesn't print: nothing per photo reaches
stdout or stderr, only totals and pass/fail (ADR-0002, *Rules for the test
set*). Every manifest here is built in tmp_path from tests/synthetic.py, and
no test calls the model: `--model test` or a patched reader.
"""

import csv
import hashlib
from pathlib import Path

import pytest
from pydantic_evals.reporting import EvaluationReport, EvaluationReportAdapter

import eval_transcription
from eval_transcription import Check, gate_needed, gate_totals, holdout_checks, photo_of
from labels import transcribe
from labels.schemas import ArtNumberReading
from tests import synthetic as s

RIGHT, WRONG = s.SPLIT_SI_9, s.SPLIT_SI_8   # reads of a held-out photo whose base is RIGHT
DEV_BASE = s.SPLIT_SI_ALPHA
COLUMNS = ["id", "photo", "garment", "side", "expected_art_number", "expected_art_base", "note"]
SUFFIX = Path(s.HOLDOUT_PHOTO).suffix


def side_row(i: int, **cells: str) -> dict:
    """One held-out garment-side, its own garment, labelled RIGHT."""
    return {"id": f"hid-{i:02d}", "photo": f"{s.HOLDOUT_PHOTO_STEM}_{i:02d}{SUFFIX}",
            "garment": f"hgarm-{i:02d}", "side": "front", "expected_art_number": "",
            "expected_art_base": RIGHT, "note": "", **cells}


def held_out(n: int = 15) -> list[dict]:
    return [side_row(i) for i in range(1, n + 1)]


DEV_ROWS = [{"id": "p1", "photo": s.PHOTO, "garment": "g1", "side": "back",
             "expected_art_number": "", "expected_art_base": DEV_BASE, "note": ""}]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def ledger(md5: str) -> str:
    return ("| date | holdout md5 | what changed |\n|---|---|---|\n"
            f"| 2026-11-07 | `{md5}` | frozen |\n")


class HoldoutSet:
    """A synthetic held-out set beside a synthetic dev set, and main()."""

    def __init__(self, root: Path, monkeypatch):
        self.root, self.monkeypatch = root, monkeypatch
        self.manifest = root / "holdout" / "manifest.csv"
        self.photos = root / "holdout" / "photos"

    def write(self, rows: list[dict] | None = None, dev: list[dict] | None = DEV_ROWS,
              missing: tuple[str, ...] = (), ledger_md5: str | None = "match") -> list[dict]:
        """`missing` names photos left off disk; `ledger_md5` "match" records
        the manifest's own md5, None writes no BASELINES.md."""
        rows = held_out() if rows is None else rows
        write_csv(self.manifest, rows)
        self.photos.mkdir(parents=True, exist_ok=True)
        for r in rows:
            if r["photo"] and r["photo"] not in missing:
                (self.photos / r["photo"]).write_bytes(f"photo {r['id']}".encode())
        if dev is not None:
            write_csv(self.root / "manifest.csv", dev)
            (self.root / "photos").mkdir(exist_ok=True)
            for r in dev:
                (self.root / "photos" / r["photo"]).write_bytes(b"dev photo")
        if ledger_md5 is not None:
            md5 = (hashlib.md5(self.manifest.read_bytes()).hexdigest()
                   if ledger_md5 == "match" else ledger_md5)
            (self.root / "BASELINES.md").write_text(ledger(md5), encoding="utf-8")
        return rows

    def run(self, *flags: str) -> int:
        self.monkeypatch.setattr("sys.argv", ["eval", "--holdout", *flags])
        return eval_transcription.main()

    def saved(self) -> tuple[EvaluationReport, Path]:
        [path] = (self.root / "results").glob("*.json")
        return EvaluationReportAdapter.validate_json(path.read_bytes()), path


@pytest.fixture
def holdout(tmp_path, monkeypatch):
    """The harness's paths and git, patched on the module, so main() runs end
    to end under tmp_path: a clean tree whose HEAD carries a tag."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    for name, path in [("EVALS", tmp_path), ("MANIFEST", tmp_path / "manifest.csv"),
                       ("PHOTOS", tmp_path / "photos"), ("RESULTS", tmp_path / "results"),
                       ("BASELINES", tmp_path / "BASELINES.md"),
                       ("HOLDOUT_MANIFEST", tmp_path / "holdout" / "manifest.csv"),
                       ("HOLDOUT_PHOTOS", tmp_path / "holdout" / "photos")]:
        monkeypatch.setattr(eval_transcription, name, path)
    git(monkeypatch)
    return HoldoutSet(tmp_path, monkeypatch)


def git(monkeypatch, status: str = "", tag: str = "gate-1") -> None:
    def fake(*args):
        if args[0] == "status":
            return status
        if args[0] == "tag":
            return tag
        return "abc1234"
    monkeypatch.setattr(eval_transcription, "git", fake)


def no_api(monkeypatch):
    def fail(*_, **__):
        raise AssertionError("the run should have stopped before reading")
    monkeypatch.setattr(eval_transcription, "get_art_number_reading", fail)


def fake_reads(monkeypatch, by_photo: dict[str, list[str | None]]) -> list[Path]:
    """Each photo's reads in turn; None fails the read, with the path in its
    message. Each read prints the photo too, so nothing a read prints may
    escape. Returns the paths read, as they are passed."""
    queues = {name: iter(reads) for name, reads in by_photo.items()}
    seen = []

    def read(photo_path: Path, model: str) -> ArtNumberReading:
        seen.append(photo_path)
        print(f"reading {photo_path}")
        raw = next(queues[photo_path.name])
        if raw is None:
            raise RuntimeError(f"read failed: {photo_path}")
        return ArtNumberReading(art_number_raw=raw, art_legible="clear")

    monkeypatch.setattr(eval_transcription, "get_art_number_reading", read)
    return seen


def values_of(rows: list[dict]) -> list[str]:
    """Everything per photo that must never be printed."""
    values = [RIGHT, WRONG, DEV_BASE, s.PHOTO, Path(s.PHOTO).stem]
    for r in rows:
        values += [r["id"], r["photo"], Path(r["photo"]).stem, r["garment"],
                   r["expected_art_base"]]
    return [v for v in values if v]


def assert_nothing_per_photo(printed: str, rows: list[dict]) -> None:
    for value in values_of(rows):
        assert value not in printed


class TestPrivacy:
    """Nothing per photo reaches stdout or stderr, at either level."""

    @pytest.mark.parametrize("capture", ["capsys", "capfd"])
    def test_a_test_model_run_prints_totals_only(self, holdout, request, capture):
        cap = request.getfixturevalue(capture)
        rows = holdout.write()
        assert holdout.run("--model", "test") == 0
        out, err = cap.readouterr()
        assert_nothing_per_photo(out + err, rows)
        assert "garment-sides correct: 0 of 15" in out

    @pytest.mark.parametrize("capture", ["capsys", "capfd"])
    def test_a_void_run_prints_no_read_or_failure(
        self, holdout, monkeypatch, request, capture
    ):
        """Each failed read's error carries its photo's path."""
        cap = request.getfixturevalue(capture)
        rows = holdout.write()
        fake_reads(monkeypatch, {r["photo"]: [RIGHT, WRONG, None] for r in rows})
        assert holdout.run("--model", "test") == 1
        out, err = cap.readouterr()
        assert_nothing_per_photo(out + err, rows)
        assert "15 failed reads: run void, rerun" in out

    def test_the_saved_report_keeps_every_read(self, holdout, monkeypatch):
        """Local and gitignored, so it may hold per-photo results."""
        rows = holdout.write()
        fake_reads(monkeypatch, {r["photo"]: [RIGHT, WRONG, None] for r in rows})
        holdout.run("--model", "test")
        report, path = holdout.saved()
        assert len(report.cases) == 30 and len(report.failures) == 15
        assert path.name.endswith("-test-holdout.json")

    def test_an_error_prints_its_type_only(self, holdout, monkeypatch, capsys):
        """An exception's message could name a photo or a value."""
        holdout.write()

        def boom(*_):
            raise ValueError(f"bad row {s.HOLDOUT_PHOTO} {s.HOLDOUT_EXPECTED_CODE}")

        monkeypatch.setattr(eval_transcription, "holdout_checks", boom)
        assert holdout.run("--check") == 1
        out, err = capsys.readouterr()
        assert out == "--holdout stopped: ValueError\n" and err == ""


class TestHeldOutOnly:
    def test_the_cases_are_the_held_out_rows_and_no_dev_photo_is_read(
        self, holdout, monkeypatch
    ):
        rows = holdout.write()
        seen = fake_reads(monkeypatch, {r["photo"]: [RIGHT] * 3 for r in rows})
        assert holdout.run("--model", "test") == 0
        report, _ = holdout.saved()
        assert sorted({photo_of(c) for c in report.cases}) == sorted(r["photo"] for r in rows)
        assert len(seen) == 45
        assert {p.parent for p in seen} == {holdout.photos}
        assert all(p.name != s.PHOTO for p in seen)
        meta = report.experiment_metadata or {}
        assert set(meta["photo_hashes"]) == {r["id"] for r in rows}

    def test_the_header_is_the_held_out_sets(self, holdout, monkeypatch):
        holdout.write()
        holdout.run("--model", "test", "--note", "gate attempt")
        meta = holdout.saved()[0].experiment_metadata or {}
        assert (meta["set"], meta["void"]) == ("holdout", False)
        assert meta["manifest"] == eval_transcription.fingerprint(holdout.manifest.read_bytes())
        assert (meta["repeat"], meta["limit"], meta["note"]) == (3, None, "gate attempt")

    def test_a_dev_run_has_no_set_or_void_field(self, holdout, monkeypatch):
        holdout.write()
        monkeypatch.setattr("sys.argv", ["eval", "--model", "test"])
        assert eval_transcription.main() == 0
        meta = holdout.saved()[0].experiment_metadata or {}
        assert "set" not in meta and "void" not in meta


@pytest.fixture
def checks(tmp_path):
    """holdout_checks by name, with every row's photo on disk in tmp_path
    except those in `missing`."""
    def run(rows: list[dict], dev: list[dict] | None = DEV_ROWS,
            missing: tuple[str, ...] = ()) -> dict[str, Check]:
        for r in rows:
            if r["photo"] and r["photo"] not in missing:
                (tmp_path / r["photo"]).write_bytes(b"photo")
        return {c.name: c for c in holdout_checks(rows, dev, tmp_path)}
    return run


@pytest.fixture
def failed(checks):
    """The failing checks' details, by name."""
    def run(rows: list[dict], dev: list[dict] | None = DEV_ROWS,
            missing: tuple[str, ...] = ()) -> dict[str, str]:
        return {n: c.detail for n, c in checks(rows, dev, missing).items() if not c.ok}
    return run


class TestChecks:
    """Each check passes on a clean set and fails on one broken row, by
    count. The printed lines are tested end to end in TestCheckFlag."""

    NAMES = ["rows", "ids", "one photo per garment-side", "no garment overlap",
             "no product overlap", "no prompt examples", "size", "photo files",
             "no id overlap"]

    def test_a_clean_set_passes_every_check(self, checks):
        result = checks(held_out())
        assert list(result) == self.NAMES
        assert all(c.ok for c in result.values())

    @pytest.mark.parametrize("cells", [
        {"expected_art_base": ""}, {"expected_art_base": "UNKNOWN"},
        {"expected_art_base": "none"}, {"expected_art_number": "NONE"},
    ], ids=["blank base", "unknown base", "none base", "none legacy"])
    def test_rows_fail_on_a_row_that_is_not_scored(self, failed, cells):
        rows = [*held_out(), side_row(16, **cells)]
        assert failed(rows) == {"rows": "1 row"}

    def test_a_row_with_no_photo_fails_rows_and_photo_files(self, failed):
        assert failed([*held_out(), side_row(16, photo="")]) == {
            "rows": "1 row", "photo files": "1 row"}

    def test_rows_fail_on_a_row_the_loader_would_skip(self, checks):
        """Never skipped quietly: the loader's own rule is part of the check."""
        row = side_row(16, expected_art_base="")
        assert eval_transcription.loader_skips(row)
        assert not checks([*held_out(), row])["rows"].ok

    @pytest.mark.parametrize("cells,detail", [
        ({"id": ""}, "1 row"), ({"id": "hid-01"}, "2 rows")])
    def test_ids_fail_on_a_blank_or_repeated_id(self, failed, cells, detail):
        assert failed([*held_out(), side_row(16, **cells)]) == {"ids": detail}

    def test_one_photo_per_garment_side(self, failed):
        second_shot = side_row(16, garment="hgarm-01")
        assert failed([*held_out(), second_shot]) == {"one photo per garment-side": "2 rows"}

    def test_two_sides_of_one_garment_are_two_garment_sides(self, failed):
        back = side_row(16, garment="hgarm-01", side="back")
        assert failed([*held_out(14), back]) == {}

    @pytest.mark.parametrize("cells", [{"garment": ""}, {"side": ""}])
    def test_a_row_with_no_garment_or_side_fails(self, failed, cells):
        assert failed([*held_out(), side_row(16, **cells)]) == {
            "one photo per garment-side": "1 row"}

    def test_no_garment_overlap(self, failed):
        assert failed([*held_out(), side_row(16, garment="g1")]) == {
            "no garment overlap": "1 row"}

    def test_no_product_overlap_after_normalising(self, failed):
        spaced = f"{DEV_BASE[:3].lower()} {DEV_BASE[3:]}"
        assert failed([*held_out(), side_row(16, expected_art_base=spaced)]) == {
            "no product overlap": "1 row"}

    def test_a_missing_dev_manifest_fails_every_check_that_needs_it(self, failed):
        assert failed(held_out(), dev=None) == {"no garment overlap": "no dev manifest",
                                                "no product overlap": "no dev manifest",
                                                "no id overlap": "no dev manifest"}

    def test_the_prompt_is_the_one_sent(self):
        assert eval_transcription.ART_PROMPT is transcribe.ART_PROMPT

    def test_no_prompt_examples_after_normalising(self, failed, monkeypatch):
        """Spacing and case in the prompt don't hide a base."""
        spaced = f"{WRONG[:4]} {WRONG[4:].lower()}"
        monkeypatch.setattr(eval_transcription, "ART_PROMPT", f"e.g. ART. {spaced}/12")
        assert failed([*held_out(), side_row(16, expected_art_base=WRONG)]) == {
            "no prompt examples": "1 row"}

    @pytest.mark.parametrize("n,ok", [(14, False), (15, True)])
    def test_size_counts_garment_sides(self, checks, n, ok):
        size = checks(held_out(n))["size"]
        assert (size.ok, size.detail) == (ok, f"{n} garment-sides")

    def test_photo_files_fail_on_a_missing_photo(self, failed):
        rows = held_out()
        assert failed(rows, missing=(rows[0]["photo"], rows[1]["photo"])) == {
            "photo files": "2 rows"}

    def test_photo_files_look_in_the_directory_given(self, tmp_path):
        """The held-out photos' directory, never the dev one."""
        rows = held_out()
        (tmp_path / "elsewhere").mkdir()
        for r in rows:
            (tmp_path / "elsewhere" / r["photo"]).write_bytes(b"photo")
        result = {c.name: c for c in holdout_checks(rows, DEV_ROWS, tmp_path)}
        assert result["photo files"] == Check("photo files", False, "15 rows")

    def test_no_id_overlap(self, failed):
        assert failed([*held_out(), side_row(16, id="p1")]) == {"no id overlap": "1 row"}


class TestCheckFlag:
    """--holdout --check: pass or fail per check, at most a count."""

    PASS = ("test-set checks (ADR-0002):\n"
            "  rows: pass\n  ids: pass\n  one photo per garment-side: pass\n"
            "  no garment overlap: pass\n  no product overlap: pass\n"
            "  no prompt examples: pass\n  size: pass (15 garment-sides)\n"
            "  photo files: pass\n  no id overlap: pass\n")

    def test_a_clean_set_passes(self, holdout, capsys):
        holdout.write()
        assert holdout.run("--check") == 0
        assert capsys.readouterr().out == self.PASS

    def test_every_check_failing_prints_counts_only(self, holdout, monkeypatch, capsys):
        rows = [side_row(1, expected_art_base="NONE"), side_row(2, id="hid-01"),
                side_row(3, garment="hgarm-02"), side_row(4, garment="g1"),
                side_row(5, expected_art_base=DEV_BASE), side_row(6, expected_art_base=WRONG),
                side_row(7, id="p1")]
        monkeypatch.setattr(eval_transcription, "ART_PROMPT", f"e.g. {WRONG}")
        holdout.write(rows, missing=(rows[6]["photo"],))
        assert holdout.run("--check") == 1
        out, err = capsys.readouterr()
        assert out == ("test-set checks (ADR-0002):\n"
                       "  rows: fail (1 row)\n  ids: fail (2 rows)\n"
                       "  one photo per garment-side: fail (2 rows)\n"
                       "  no garment overlap: fail (1 row)\n"
                       "  no product overlap: fail (1 row)\n"
                       "  no prompt examples: fail (1 row)\n"
                       "  size: fail (6 garment-sides)\n"
                       "  photo files: fail (1 row)\n"
                       "  no id overlap: fail (1 row)\n")
        assert err == ""
        assert_nothing_per_photo(out, rows)

    def test_it_needs_no_tag_ledger_or_clean_tree(self, holdout, monkeypatch, capsys):
        holdout.write(ledger_md5=None)
        git(monkeypatch, status=" M x.py", tag="")
        no_api(monkeypatch)
        assert holdout.run("--check") == 0

    def test_it_sends_no_photo(self, holdout, monkeypatch):
        holdout.write()
        no_api(monkeypatch)
        assert holdout.run("--check") == 0
        assert not (holdout.root / "results").exists()

    def test_a_missing_held_out_manifest_fails(self, holdout, capsys):
        assert holdout.run("--check") == 1
        assert "no held-out manifest" in capsys.readouterr().out


class TestRefusals:
    @pytest.mark.parametrize("flags", [
        ["--limit", "1"], ["--limit", "0"], ["--no-save"], ["--replay", "x.json"],
        ["--baseline", "x.json"], ["--repeat", "1"], ["--repeat", "5"], ["--workers", "4"],
        ["--model", transcribe.ART_MODEL], ["--model", "anthropic:claude-opus-5"],
    ])
    def test_flags_that_change_the_run_are_refused(self, holdout, monkeypatch, flags):
        holdout.write()
        no_api(monkeypatch)
        with pytest.raises(SystemExit) as exc:
            holdout.run(*flags)
        assert exc.value.code == 2

    @pytest.mark.parametrize("flags", [
        ["--model", "test"], ["--repeat", "3"], ["--workers", "1"], ["--note", "x"],
        ["--limit", "1"],
    ])
    def test_check_takes_no_run_flags(self, holdout, monkeypatch, flags):
        with pytest.raises(SystemExit) as exc:
            holdout.run("--check", *flags)
        assert exc.value.code == 2

    def test_check_needs_holdout(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["eval", "--check"])
        with pytest.raises(SystemExit) as exc:
            eval_transcription.main()
        assert exc.value.code == 2

    def test_the_fixed_settings_may_be_passed(self, holdout):
        holdout.write()
        assert holdout.run("--model", "test", "--repeat", "3", "--workers", "1",
                           "--note", "gate") == 0

    def refused(self, holdout, monkeypatch, capsys, *flags) -> str:
        no_api(monkeypatch)
        assert holdout.run(*flags) == 1
        assert not (holdout.root / "results").exists()
        return capsys.readouterr().out

    @pytest.mark.parametrize("status", [" M labels/transcribe.py", "?? labels/new.py"])
    @pytest.mark.parametrize("model", [[], ["--model", "test"]], ids=["real", "test"])
    def test_a_dirty_tree(self, holdout, monkeypatch, capsys, status, model):
        holdout.write()
        git(monkeypatch, status=status)
        assert "refused: the tree has uncommitted" in self.refused(
            holdout, monkeypatch, capsys, *model)

    def test_an_untagged_head(self, holdout, monkeypatch, capsys):
        holdout.write()
        git(monkeypatch, tag="")
        assert "refused: HEAD has no tag" in self.refused(holdout, monkeypatch, capsys)

    @pytest.mark.parametrize("md5", ["0" * 32, None], ids=["mismatch", "no ledger"])
    def test_a_manifest_not_in_the_ledger(self, holdout, monkeypatch, capsys, md5):
        holdout.write(ledger_md5=md5)
        assert "refused: the held-out manifest's md5" in self.refused(
            holdout, monkeypatch, capsys)

    def test_an_earlier_ledger_row_is_not_enough(self, holdout, monkeypatch, capsys):
        holdout.write()
        current = hashlib.md5(holdout.manifest.read_bytes()).hexdigest()
        (holdout.root / "BASELINES.md").write_text(
            ledger(current) + f"| 2026-11-08 | `{'1' * 32}` | edited |\n", encoding="utf-8")
        assert "refused: the held-out manifest's md5" in self.refused(
            holdout, monkeypatch, capsys)

    def test_a_failed_check(self, holdout, monkeypatch, capsys):
        holdout.write(held_out(14))
        out = self.refused(holdout, monkeypatch, capsys, "--model", "test")
        assert "size: fail (14 garment-sides)" in out
        assert "refused: a test-set check failed" in out

    def test_the_test_model_skips_the_tag_and_the_ledger(self, holdout, monkeypatch):
        holdout.write(ledger_md5=None)
        git(monkeypatch, tag="")
        assert holdout.run("--model", "test") == 0

    def test_the_real_path_runs_when_everything_holds(self, holdout, monkeypatch):
        rows = holdout.write()
        fake_reads(monkeypatch, {r["photo"]: [RIGHT] * 3 for r in rows})
        assert holdout.run() == 0
        meta = holdout.saved()[0].experiment_metadata or {}
        assert meta["model"] == transcribe.ART_MODEL

    @pytest.mark.parametrize("flag", ["--replay", "--baseline"])
    def test_a_holdout_report_is_never_replayed_or_a_baseline(
        self, holdout, monkeypatch, capsys, flag
    ):
        """Either would print its results per photo."""
        rows = holdout.write()
        holdout.run("--model", "test")
        _, path = holdout.saved()
        capsys.readouterr()
        no_api(monkeypatch)
        argv = ["eval", flag, str(path)] + (["--model", "test"] if flag == "--baseline" else [])
        monkeypatch.setattr("sys.argv", argv)
        assert eval_transcription.main() == 1
        out = capsys.readouterr().out
        assert "is a --holdout report: it can't be a baseline or replayed" in out
        assert_nothing_per_photo(out, rows)


class TestGateArithmetic:
    @pytest.mark.parametrize("sides,needed", [(15, 12), (20, 16), (30, 24), (16, 13), (0, 0)])
    def test_80_percent_rounded_up(self, sides, needed):
        assert gate_needed(sides) == needed

    def test_misreads_count_as_wrong_and_every_read_is_counted(
        self, holdout, monkeypatch, capsys
    ):
        rows = holdout.write()
        reads: dict[str, list[str | None]] = {r["photo"]: [RIGHT] * 3 for r in rows}
        photo = [r["photo"] for r in rows]
        reads[photo[0]] = [WRONG, RIGHT, RIGHT]  # correct: 2 of 3
        reads[photo[1]] = [WRONG, WRONG, RIGHT]  # wrong
        reads[photo[2]] = [WRONG, WRONG, WRONG]  # wrong
        fake_reads(monkeypatch, reads)
        assert holdout.run("--model", "test") == 0
        out = capsys.readouterr().out
        totals = out[out.index("held-out run:"):].splitlines()
        assert totals[:5] == [
            "held-out run: test at abc1234, --repeat 3, workers 1",
            "garment-sides correct: 13 of 15",
            "needed to pass: 12 (80% of 15, rounded up)",
            "reads correct: 39 of 45 (86.7%)",
            "failed reads: 0",
        ]
        assert totals[5].startswith("wrote ") and "/results/" in totals[5]
        assert len(totals) == 6
        report, _ = holdout.saved()
        assert gate_totals(report) == (15, 13, 12, 45, 39, 0)
        assert (report.experiment_metadata or {})["void"] is False


class TestVoidRun:
    """ADR-0002: a run with any failed read is void, not an attempt."""

    def run_with_one_failure(self, holdout, monkeypatch) -> int:
        rows = holdout.write()
        reads: dict[str, list[str | None]] = {r["photo"]: [RIGHT] * 3 for r in rows}
        reads[rows[0]["photo"]] = [RIGHT, RIGHT, None]   # still 2 of 3 correct
        fake_reads(monkeypatch, reads)
        return holdout.run("--model", "test")

    def test_one_failed_read_voids_the_run_and_hides_the_totals(
        self, holdout, monkeypatch, capsys
    ):
        assert self.run_with_one_failure(holdout, monkeypatch) == 1
        out = capsys.readouterr().out
        lines = out[out.index("held-out run:"):].splitlines()
        assert lines[:2] == ["held-out run: test at abc1234, --repeat 3, workers 1",
                             "1 failed reads: run void, rerun"]
        assert lines[2].startswith("wrote ") and len(lines) == 3
        for total in ("garment-sides correct", "needed to pass", "reads correct"):
            assert total not in out

    def test_the_void_report_is_saved_and_marked(self, holdout, monkeypatch):
        self.run_with_one_failure(holdout, monkeypatch)
        report, _ = holdout.saved()
        assert (report.experiment_metadata or {})["void"] is True
        assert len(report.cases) == 44 and len(report.failures) == 1

    def test_the_denominator_is_every_read(self, holdout, monkeypatch):
        """Failed reads included; on a run that isn't void there are none."""
        self.run_with_one_failure(holdout, monkeypatch)
        report, _ = holdout.saved()
        assert gate_totals(report) == (15, 15, 12, 45, 44, 1)

    def test_a_void_report_is_still_refused_by_replay(self, holdout, monkeypatch, capsys):
        self.run_with_one_failure(holdout, monkeypatch)
        _, path = holdout.saved()
        monkeypatch.setattr("sys.argv", ["eval", "--replay", str(path)])
        assert eval_transcription.main() == 1
        assert "is a --holdout report" in capsys.readouterr().out

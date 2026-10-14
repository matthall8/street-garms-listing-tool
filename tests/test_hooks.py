"""The Claude Code hooks in .claude/hooks/, run the way the harness runs them.

Each hook gets the harness's JSON on stdin. Exit 2 hands a failure back to the
agent; exit 0 lets it through. Every test points CLAUDE_PROJECT_DIR at a
throwaway project under tmp_path, with this repo's .venv linked in, so nothing
here touches the real tree and the Stop hook never runs this suite.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / ".claude" / "hooks"

pytestmark = [
    pytest.mark.skipif(shutil.which("jq") is None, reason="the hooks need jq"),
    pytest.mark.skipif(not (ROOT / ".venv" / "bin" / "ruff").exists(), reason="no .venv"),
]


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".venv").symlink_to(ROOT / ".venv")
    return tmp_path


def run(hook, project, payload, env=None):
    return subprocess.run(
        [HOOKS / hook],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), **(env or {})},
    )


def edited(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}


class TestRuffHook:
    def test_lint_error_is_handed_back(self, project):
        f = project / "bad.py"
        f.write_text("import os\n")
        result = run("ruff-edited.sh", project, edited(f))
        assert result.returncode == 2
        assert "F401" in result.stderr

    def test_clean_file_passes(self, project):
        f = project / "good.py"
        f.write_text("x = 1\n")
        assert run("ruff-edited.sh", project, edited(f)).returncode == 0

    def test_non_python_file_is_skipped(self, project):
        f = project / "notes.md"
        f.write_text("import os\n")
        assert run("ruff-edited.sh", project, edited(f)).returncode == 0

    def test_file_outside_the_project_is_skipped(self, project, tmp_path_factory):
        f = tmp_path_factory.mktemp("elsewhere") / "bad.py"
        f.write_text("import os\n")
        assert run("ruff-edited.sh", project, edited(f)).returncode == 0


class TestStopHook:
    def test_failing_tests_are_handed_back(self, project):
        (project / "test_x.py").write_text("def test_x():\n    assert False\n")
        result = run("stop-tests.sh", project, {"stop_hook_active": False})
        assert result.returncode == 2
        assert "Tests fail" in result.stderr

    def test_passing_tests_let_the_turn_end(self, project):
        (project / "test_x.py").write_text("def test_x():\n    assert True\n")
        assert run("stop-tests.sh", project, {"stop_hook_active": False}).returncode == 0

    def test_second_stop_is_let_through(self, project):
        """The loop guard: a failure the agent can't fix must not block forever."""
        (project / "test_x.py").write_text("def test_x():\n    assert False\n")
        assert run("stop-tests.sh", project, {"stop_hook_active": True}).returncode == 0


class TestWithoutJq:
    """Without jq the Stop hook's loop guard can't read its input, so both
    hooks must let everything through rather than block every stop."""

    def test_stop_hook_does_nothing(self, project, tmp_path_factory):
        (project / "test_x.py").write_text("def test_x():\n    assert False\n")
        no_jq = {"PATH": str(tmp_path_factory.mktemp("empty-bin"))}
        result = run("stop-tests.sh", project, {"stop_hook_active": False}, no_jq)
        assert result.returncode == 0

    def test_ruff_hook_does_nothing(self, project, tmp_path_factory):
        f = project / "bad.py"
        f.write_text("import os\n")
        no_jq = {"PATH": str(tmp_path_factory.mktemp("empty-bin"))}
        assert run("ruff-edited.sh", project, edited(f), no_jq).returncode == 0

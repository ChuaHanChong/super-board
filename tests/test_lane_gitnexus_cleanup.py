"""Checks the lane exit unregisters its GitNexus index (#1694) from every exit path."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest_lite as pytest

ROOT = Path(__file__).resolve().parents[1]

FAKE_OPENCODE = """#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = debug ] && [ "${2:-}" = paths ]; then
  echo "data $FAKE_STATE/data"
  exit 0
fi
touch "$TMPDIR/.opencode-started"
[ -n "${FAKE_SLEEP:-}" ] && sleep "$FAKE_SLEEP"
[ -n "${FAKE_EXIT:-}" ] && exit "$FAKE_EXIT"
printf '%s\\n' '{"part":{"type":"text","text":"{\\"status\\":\\"advanced\\",\\"column\\":\\"Building\\",\\"detail\\":\\"e2e\\",\\"prUrl\\":null,\\"branch\\":null,\\"priorFindings\\":null}"}}'
"""

# Records cwd, argv and the registry home; the launcher may only call `remove --force <path>` here.
FAKE_GITNEXUS = """#!/usr/bin/env bash
printf '%s gitnexus %s home=%s\\n' "$PWD" "$*" "$GITNEXUS_HOME" >> "$GITNEXUS_LOG"
exit 0
"""

SKILLS_READY = ("def hydrate(cards, root):\n    return None\n\n\n"
                "def report(root, backend, cards, lane=None, home=None, catalog=None):\n"
                "    return {'ready': True, 'entries': []}\n")
SKILLS_NOT_READY = ("def hydrate(cards, root):\n    return None\n\n\n"
                    "def report(root, backend, cards, lane=None, home=None, catalog=None):\n"
                    "    return {'ready': False, 'entries': [{'name': 'super-build', 'status': 'missing'}]}\n")


def _repo(tmp_path: Path) -> Path:
    """Return a one-commit git repo, so the launcher finds a git root."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "f").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True)
    return repo


def _lane_bin(tmp_path: Path, skills_ready: str = SKILLS_READY) -> Path:
    """Copy the real launcher and its temp helper next to fast stubs for the gates and both hosts."""
    binary = tmp_path / "bin"
    binary.mkdir()
    for name in ("super-board-lane.sh", "super-board-lane-tmp.py"):
        shutil.copy2(ROOT / "scripts" / name, binary / name)
    (binary / "super-board-verification-ready.py").write_text("import sys\nsys.exit(0)\n")
    (binary / "super-board-github-read.py").write_text("import sys\nsys.exit(0)\n")
    (binary / "super-board-skills-ready.py").write_text(skills_ready)
    for name, body in (("opencode", FAKE_OPENCODE), ("gitnexus", FAKE_GITNEXUS)):
        stub = binary / name
        stub.write_text(body)
        stub.chmod(0o755)
    return binary


def _lane_env(tmp_path: Path, binary: Path, **extra: str) -> dict[str, str]:
    """Environment for one launcher run: both stubs first on PATH, a private index home, a call log."""
    return dict(os.environ, PATH=f"{binary}{os.pathsep}{os.environ['PATH']}",
                GITNEXUS_HOME=str(tmp_path / "gitnexus"), GITNEXUS_LOG=str(tmp_path / "gitnexus.log"),
                FAKE_STATE=str(tmp_path / "state"), **extra)


def _lane_config(tmp_path: Path) -> Path:
    """Board config with the lane temp root on the test disk, not the host /tmp."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"verify_commands": ["true"], "lane": {"tmp_root": str(tmp_path / "lanes")},
                                  "opencode": {"model": "fake-model"}}))
    return config


def _lane_command(binary: Path, tmp_path: Path, number: int = 1) -> list[str]:
    """The real launcher argv for one build lane with the fake hosts."""
    card = json.dumps({"number": number, "status": "Building", "labels": ["bug"]})
    return ["bash", str(binary / "super-board-lane.sh"), "--backend", "opencode",
            "--config", str(_lane_config(tmp_path)), "--card", card, "--lane", "build", "--opencode"]


def _crew(tmp_path: Path, repo: Path, number: int = 1, **extra: str) -> tuple[list[str], dict[str, str], Path]:
    """Launcher argv, environment and the lane worktree path the card would build in."""
    binary = _lane_bin(tmp_path)
    lane_worktree = repo / ".claude" / "worktrees" / f"issue-{number}-build"
    lane_worktree.mkdir(parents=True)
    return _lane_command(binary, tmp_path, number), _lane_env(tmp_path, binary, **extra), lane_worktree


def _calls(tmp_path: Path) -> list[str]:
    """The recorded stub-gitnexus calls, one `cwd gitnexus args home=…` line each."""
    log = tmp_path / "gitnexus.log"
    return log.read_text().splitlines() if log.exists() else []


def _expected(tmp_path: Path, repo: Path, lane_worktree: Path) -> str:
    """The one registry call a finished lane owes: unregister by path, from the repo root."""
    return (f"{repo} gitnexus remove --force {lane_worktree} "
            f"home={(tmp_path / 'gitnexus').resolve()}")


def test_a_normal_exit_unregisters_the_lane_worktree_index(tmp_path):
    """Input: a finished lane with a worktree -> remove --force runs and the lane JSON is unchanged."""
    repo = _repo(tmp_path)
    command, env, lane_worktree = _crew(tmp_path, repo)
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "advanced"
    assert _calls(tmp_path) == [_expected(tmp_path, repo, lane_worktree)]


def test_an_ordinary_exit_unregisters_a_worktree_the_lane_already_removed(tmp_path):
    """Input: the lane removed its worktree before returning (run.md step 9) -> the index still goes."""
    repo = _repo(tmp_path)
    command, env, lane_worktree = _crew(tmp_path, repo)
    shutil.rmtree(lane_worktree)
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "advanced"
    assert not lane_worktree.exists()
    assert _calls(tmp_path) == [_expected(tmp_path, repo, lane_worktree)]


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="the OpenCode lane needs bubblewrap")
def test_a_killed_lane_unregisters_its_worktree_index(tmp_path):
    """Input: SIGTERM mid-run (a timeout reaches the launcher the same way) -> the index still goes."""
    repo = _repo(tmp_path)
    command, env, lane_worktree = _crew(tmp_path, repo, FAKE_SLEEP="3")
    proc = subprocess.Popen(command, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    started = tmp_path / "lanes" / "1-build" / ".opencode-started"
    try:
        deadline = time.monotonic() + 60
        while not started.exists() and time.monotonic() < deadline:
            assert proc.poll() is None, proc.stderr.read()
            time.sleep(0.1)
        assert started.exists(), "the fake host never started inside the lane root"
        proc.send_signal(signal.SIGTERM)
        stdout, stderr = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
    assert proc.returncode == 128 + signal.SIGTERM, stderr
    assert json.loads(stdout)["status"] == "halted"
    assert _calls(tmp_path) == [_expected(tmp_path, repo, lane_worktree)]


def test_a_halt_after_the_child_unregisters_the_lane_worktree_index(tmp_path):
    """Input: the child exits 9 (halt) -> remove --force runs and the halt JSON stays the payload."""
    repo = _repo(tmp_path)
    command, env, lane_worktree = _crew(tmp_path, repo, FAKE_EXIT="9")
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 9, result.stderr
    assert json.loads(result.stdout)["status"] == "halted"
    assert _calls(tmp_path) == [_expected(tmp_path, repo, lane_worktree)]


def test_a_halt_before_the_child_leaves_the_registry_alone(tmp_path):
    """Input: skills gate halts before any child runs -> no registry call and no worktree invented."""
    repo = _repo(tmp_path)
    binary = _lane_bin(tmp_path, skills_ready=SKILLS_NOT_READY)
    result = subprocess.run(_lane_command(binary, tmp_path), cwd=repo, capture_output=True, text=True,
                            timeout=120, env=_lane_env(tmp_path, binary))
    assert result.returncode == 10, result.stderr
    assert _calls(tmp_path) == []
    assert not (repo / ".claude" / "worktrees" / "issue-1-build").exists()


if __name__ == "__main__":
    import pytest_lite
    raise SystemExit(pytest_lite.main(globals()))

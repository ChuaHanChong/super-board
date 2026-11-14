"""Checks the per-lane temp root (#1486): created on /data, cleaned, and never hides /tmp work."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest_lite as pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "super-board-lane-tmp.py"
LANE = ROOT / "scripts" / "super-board-lane.sh"


def _run(*args: str | Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run the temp-root helper with stringified arguments and an optional extra environment."""
    return subprocess.run([sys.executable, str(HELPER), *map(str, args)],
                          capture_output=True, text=True, timeout=60,
                          env=dict(os.environ, **env) if env else None)


def _repo(tmp_path: Path) -> Path:
    """Return a one-commit git repo so worktrees can be registered against it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "f").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True)
    return repo


def _worktrees(repo: Path) -> str:
    """The repo's registered worktree listing."""
    return subprocess.run(["git", "-C", str(repo), "worktree", "list"],
                          capture_output=True, text=True, timeout=60).stdout


def test_create_makes_lane_root_and_caches(tmp_path):
    """Input: card 1486 + lane build -> one root per card and lane, with the uv dirs inside."""
    result = _run("create", tmp_path / "lanes", 1486, "build")
    assert result.returncode == 0, result.stderr
    lane_root = Path(result.stdout.strip())
    assert lane_root == (tmp_path / "lanes" / "1486-build").resolve()
    assert (lane_root / "uv-cache").is_dir()
    assert (lane_root / "uv-python").is_dir()


def test_cleanup_removes_registered_worktree_and_root(tmp_path):
    """Input: a worktree inside the lane root -> the worktree and the root are gone."""
    repo = _repo(tmp_path)
    lane_root = tmp_path / "lanes" / "1486-build"
    worktree = lane_root / "checkout"
    worktree.parent.mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(worktree), "-b", "wt"],
                   check=True)
    result = _run("cleanup", repo, lane_root)
    assert result.returncode == 0, result.stderr
    assert not lane_root.exists()
    assert str(worktree) not in _worktrees(repo)


def test_cleanup_reports_tmp_worktree_without_deleting_it(tmp_path):
    """Input: another lane's worktree in the temp tree -> reported on stderr and left in place."""
    repo = _repo(tmp_path)
    host_tmp = tmp_path / "host-tmp"
    host_tmp.mkdir()
    stale = Path(tempfile.mkdtemp(prefix="sb-stale-", dir=host_tmp)).resolve()
    lane_root = tmp_path / "lanes" / "1486-build"
    lane_root.mkdir(parents=True)
    try:
        stale_worktree = stale / "wt"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(stale_worktree), "-b", "stale"],
                       check=True)
        # The stale tree is a parameter because a host may mount /tmp read-only.
        result = _run("cleanup", repo, lane_root, host_tmp)
        assert result.returncode == 0, result.stderr
        assert "stale-tmp-worktree:" in result.stderr
        assert str(stale_worktree) in result.stderr
        assert stale_worktree.exists()
    finally:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(stale / "wt")],
                       capture_output=True)
        shutil.rmtree(stale, ignore_errors=True)


def test_cleanup_reports_a_stale_worktree_under_a_read_only_temp_root(tmp_path):
    """Input: TMPDIR and the stale root are read-only -> the stale worktree is still reported."""
    repo = _repo(tmp_path)
    read_only = tmp_path / "read-only-tmp"
    read_only.mkdir()
    stale_worktree = read_only / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(stale_worktree), "-b", "stale"],
                   check=True)
    lane_root = tmp_path / "lanes" / "1486-build"
    lane_root.mkdir(parents=True)
    read_only.chmod(0o500)  # a lane jail mounts its temp dir read-only, so nothing may be written there
    try:
        result = _run("cleanup", repo, lane_root, read_only, env={"TMPDIR": str(read_only)})
        assert result.returncode == 0, result.stderr
        assert "stale-tmp-worktree:" in result.stderr
        assert str(stale_worktree) in result.stderr
        assert stale_worktree.exists()
    finally:
        read_only.chmod(0o700)
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(stale_worktree)],
                       capture_output=True)


def test_cleanup_keeps_root_when_git_refuses_to_remove_a_dirty_worktree(tmp_path):
    """Input: a dirty worktree inside the lane root -> git refuses, so the root keeps the work."""
    repo = _repo(tmp_path)
    lane_root = tmp_path / "lanes" / "1486-build"
    worktree = lane_root / "checkout"
    worktree.parent.mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(worktree), "-b", "dirty"],
                   check=True)
    (worktree / "f").write_text("changed")
    result = _run("cleanup", repo, lane_root)
    assert result.returncode == 1
    assert lane_root.exists()
    assert "kept worktree" in result.stderr


def test_cleanup_removes_a_killed_lane_leftover(tmp_path):
    """Input: a killed lane's leftover .mjb under its root -> cleanup removes file and root."""
    repo = _repo(tmp_path)
    lane_root = tmp_path / "lanes" / "1486-build"
    (lane_root / "uv-cache").mkdir(parents=True)
    leftover = lane_root / "tmp8a5ruka1.mjb"
    leftover.write_bytes(b"x" * 1024)
    result = _run("cleanup", repo, lane_root)
    assert result.returncode == 0, result.stderr
    assert not leftover.exists()
    assert not lane_root.exists()


def test_lane_exports_the_temp_root_to_children():
    """Input: the lane launcher source -> TMPDIR, uv dirs and the cleanup call come from the root."""
    source = LANE.read_text()
    assert "TMPDIR=str(lane_tmp)" in source
    assert "UV_CACHE_DIR=str(lane_tmp / 'uv-cache')" in source
    assert "write_roots.append(lane_tmp)" in source
    assert "'cleanup', str(root), str(lane_tmp)" in source
    assert "dir=str(lane_tmp)" in source
    assert "finish_lane()" in source.split("def interrupted", 1)[1].split("signal.signal", 1)[0]


FAKE_OPENCODE = """#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = debug ] && [ "${2:-}" = paths ]; then
  echo "data $FAKE_STATE/data"
  exit 0
fi
echo "LANE_TMPDIR=$TMPDIR" >&2
echo "LANE_TMP=$TMP" >&2
echo "LANE_TEMP=$TEMP" >&2
echo "LANE_UV_CACHE_DIR=$UV_CACHE_DIR" >&2
echo "LANE_UV_PYTHON_INSTALL_DIR=$UV_PYTHON_INSTALL_DIR" >&2
echo "LANE_PWD=$PWD" >&2
touch "$TMPDIR/.opencode-started"
# Stands in for the merge gate's scratch checkout: mktemp honours TMPDIR, then git worktree adds there.
[ -n "${FAKE_WORKTREE:-}" ] && git worktree add -q --detach "$TMPDIR/gate-scratch" HEAD \
  && echo "LANE_WORKTREE=$TMPDIR/gate-scratch" >&2
[ -n "${FAKE_SLEEP:-}" ] && sleep "$FAKE_SLEEP"
printf '%s\\n' '{"part":{"type":"text","text":"{\\"status\\":\\"advanced\\",\\"column\\":\\"Building\\",\\"detail\\":\\"e2e\\",\\"prUrl\\":null,\\"branch\\":null,\\"priorFindings\\":null}"}}'
"""


SKILLS_READY = ("def hydrate(cards, root):\n    return None\n\n\n"
                "def report(root, backend, cards, lane=None, home=None, catalog=None):\n"
                "    return {'ready': True, 'entries': []}\n")
SKILLS_NOT_READY = ("def hydrate(cards, root):\n    return None\n\n\n"
                    "def report(root, backend, cards, lane=None, home=None, catalog=None):\n"
                    "    return {'ready': False, 'entries': [{'name': 'super-qa', 'status': 'missing'}]}\n")


def _lane_bin(tmp_path: Path, github_read: str = "import sys\nsys.exit(0)\n",
              skills_ready: str = SKILLS_READY) -> Path:
    """Copy the real launcher and helper into a bin dir with fast stubs for its gates."""
    binary = tmp_path / "bin"
    binary.mkdir()
    for name in ("super-board-lane.sh", "super-board-lane-tmp.py"):
        shutil.copy2(ROOT / "scripts" / name, binary / name)
    (binary / "super-board-verification-ready.py").write_text("import sys\nsys.exit(0)\n")
    (binary / "super-board-github-read.py").write_text(github_read)
    (binary / "super-board-skills-ready.py").write_text(skills_ready)
    fake = binary / "opencode"
    fake.write_text(FAKE_OPENCODE)
    fake.chmod(0o755)
    return binary


def _lane_env(tmp_path: Path, binary: Path, **extra: str) -> dict[str, str]:
    """Environment for one launcher run: fake host, a private GitNexus home, and its state."""
    env = dict(os.environ, PATH=f"{binary}{os.pathsep}{os.environ['PATH']}",
               GITNEXUS_HOME=str(tmp_path / "gitnexus"), FAKE_STATE=str(tmp_path / "state"))
    env.update(extra)
    return env


def _lane_config(tmp_path: Path) -> Path:
    """Board config with a lane temp root on the test disk, not the host /tmp."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"verify_commands": ["true"], "lane": {"tmp_root": str(tmp_path / "lanes")},
                                  "opencode": {"model": "fake-model"}}))
    return config


def _start_lane(tmp_path: Path, repo: Path, **extra: str) -> subprocess.Popen:
    """Start the real launcher with the fake OpenCode host."""
    binary = _lane_bin(tmp_path)
    card = json.dumps({"number": 1, "status": "Building", "labels": ["bug"]})
    return subprocess.Popen(
        ["bash", str(binary / "super-board-lane.sh"), "--backend", "opencode",
         "--config", str(_lane_config(tmp_path)), "--card", card, "--lane", "build", "--opencode"],
        cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=_lane_env(tmp_path, binary, **extra))


def test_a_lane_run_takes_its_temp_root_and_own_temp_dir_from_the_lane_root(tmp_path):
    """Input: one real launcher run -> TMPDIR, TMP, uv cache and the launcher temp dir are the lane root."""
    repo = _repo(tmp_path)
    binary = _lane_bin(tmp_path)
    result = subprocess.run(
        ["bash", str(binary / "super-board-lane.sh"), "--backend", "opencode",
         "--config", str(_lane_config(tmp_path)),
         "--card", json.dumps({"number": 1, "status": "Building", "labels": ["bug"]}),
         "--lane", "build", "--opencode"],
        cwd=repo, capture_output=True, text=True, timeout=120,
        env=_lane_env(tmp_path, binary))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "advanced"
    lane_root = str(tmp_path / "lanes" / "1-build")
    assert f"LANE_TMPDIR={lane_root}" in result.stderr
    assert f"LANE_TMP={lane_root}" in result.stderr
    assert f"LANE_TEMP={lane_root}" in result.stderr
    assert f"LANE_UV_CACHE_DIR={lane_root}/uv-cache" in result.stderr
    assert f"LANE_UV_PYTHON_INSTALL_DIR={lane_root}/uv-python" in result.stderr
    assert not Path(lane_root).exists()


def test_a_lane_worktree_under_the_temp_root_is_removed_on_exit(tmp_path):
    """Input: a lane-run worktree in $TMPDIR (the merge gate's scratch) -> removed, so none lands in /tmp."""
    repo = _repo(tmp_path)
    binary = _lane_bin(tmp_path)
    result = subprocess.run(
        ["bash", str(binary / "super-board-lane.sh"), "--backend", "opencode",
         "--config", str(_lane_config(tmp_path)),
         "--card", json.dumps({"number": 1486, "status": "Building", "labels": ["bug"]}),
         "--lane", "build", "--opencode"],
        cwd=repo, capture_output=True, text=True, timeout=120,
        env=_lane_env(tmp_path, binary, FAKE_WORKTREE="1"))
    assert result.returncode == 0, result.stderr
    lane_root = tmp_path / "lanes" / "1486-build"
    assert f"LANE_WORKTREE={lane_root}/gate-scratch" in result.stderr
    assert "gate-scratch" not in _worktrees(repo)
    assert not lane_root.exists()


def _run_lane(binary: Path, repo: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the real launcher once with the fake OpenCode host."""
    return subprocess.run(
        ["bash", str(binary / "super-board-lane.sh"), "--backend", "opencode",
         "--config", str(_lane_config(tmp_path)),
         "--card", json.dumps({"number": 1, "status": "Building", "labels": ["bug"]}),
         "--lane", "build", "--opencode"],
        cwd=repo, capture_output=True, text=True, timeout=120,
        env=_lane_env(tmp_path, binary))


@pytest.mark.parametrize("stub, exit_code", [
    ({"github_read": "import sys\nsys.exit(79)\n"}, 79),
    ({"skills_ready": SKILLS_NOT_READY}, 10),
])
def test_a_halt_before_the_child_removes_the_temp_root(tmp_path, stub, exit_code):
    """Input: a gate halts before the child starts (79 GitHub read, 10 skills) -> no lane root is left."""
    repo = _repo(tmp_path)
    binary = _lane_bin(tmp_path, **stub)
    result = _run_lane(binary, repo, tmp_path)
    assert result.returncode == exit_code, result.stderr
    assert json.loads(result.stdout)["status"] == "halted"
    assert not (tmp_path / "lanes" / "1-build").exists()


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="the OpenCode lane needs bubblewrap")
def test_a_signalled_lane_removes_its_temp_root_before_it_halts(tmp_path):
    """Input: SIGTERM mid-run -> the lane root is gone and the halt result is written."""
    repo = _repo(tmp_path)
    proc = _start_lane(tmp_path, repo, FAKE_SLEEP="3")
    lane_root = tmp_path / "lanes" / "1-build"
    started = lane_root / ".opencode-started"
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
    assert not lane_root.exists()



if __name__ == "__main__":
    import pytest_lite
    raise SystemExit(pytest_lite.main(globals()))

"""Checks the verify-log prune: old logs go, a fresh one and a held lock stay."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRUNE = ROOT / "scripts" / "super-board-prune-verify-logs.py"

DAY = 86400.0


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    """Return the verify-log directory and the merge-lock path under a tmp root."""
    inflight = tmp_path / ".claude" / "super-board" / "inflight"
    logs = inflight / "verify-logs"
    logs.mkdir(parents=True)
    return logs, inflight / "merge.lock"


def _log(directory: Path, name: str, age_seconds: float) -> Path:
    """Write one verify log whose mtime is age_seconds in the past."""
    path = directory / name
    path.write_text("head: abc\n")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))
    return path


def _prune(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Run the prune script against a repository root."""
    return subprocess.run(
        ["python3", str(PRUNE), "--root", str(root), *extra],
        capture_output=True, text=True,
    )


def test_an_old_log_is_pruned_and_a_fresh_one_kept(tmp_path: Path) -> None:
    """A log past the retention goes; a newer one stays."""
    logs, _ = _layout(tmp_path)
    old = _log(logs, "old.log", 30 * DAY)
    fresh = _log(logs, "fresh.log", 60)
    result = _prune(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not old.exists()
    assert fresh.exists()


def test_a_held_merge_lock_keeps_every_log(tmp_path: Path) -> None:
    """While a gate holds the merge lock its own log and the rest are untouched."""
    logs, lock = _layout(tmp_path)
    lock.mkdir()
    old = _log(logs, "old.log", 30 * DAY)
    result = _prune(tmp_path)
    assert result.returncode == 0, result.stderr
    assert old.exists()
    assert "merge lock held" in result.stdout


def test_a_log_written_by_a_run_in_flight_is_kept(tmp_path: Path) -> None:
    """Even an aggressive retention keeps the log a run has just written."""
    logs, _ = _layout(tmp_path)
    in_flight = _log(logs, "in-flight.log", 1)
    old = _log(logs, "old.log", DAY)
    result = _prune(tmp_path, "--retention-hours", "0.001")
    assert result.returncode == 0, result.stderr
    assert in_flight.exists()
    assert not old.exists()


def test_a_non_log_file_is_never_pruned(tmp_path: Path) -> None:
    """Only `*.log` entries are the prune's business."""
    logs, _ = _layout(tmp_path)
    note = logs / "notes.json"
    note.write_text("{}\n")
    stamp = time.time() - 30 * DAY
    os.utime(note, (stamp, stamp))
    result = _prune(tmp_path)
    assert result.returncode == 0, result.stderr
    assert note.exists()


def test_a_missing_log_directory_is_not_an_error(tmp_path: Path) -> None:
    """A board that has never verified has nothing to prune."""
    result = _prune(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "removed 0" in result.stdout


def test_a_non_positive_retention_is_refused(tmp_path: Path) -> None:
    """A zero retention would delete the log a run is still writing."""
    logs, _ = _layout(tmp_path)
    fresh = _log(logs, "fresh.log", 1)
    result = _prune(tmp_path, "--retention-hours", "0")
    assert result.returncode != 0
    assert fresh.exists()
    assert "retention" in result.stderr


if __name__ == "__main__":
    import pytest_lite
    raise SystemExit(pytest_lite.main(globals()))

"""Checks the GitNexus health gate blocks a blank Function layer, and the lane docs state the re-index rule."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [ROOT / "scripts" / "super-board-gitnexus-health.py"]
DOCS = ROOT / "skills" / "super-build" / "references" / "gitnexus-lanes.md"

FAKE_GITNEXUS = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GITNEXUS_LOG"
printf '%s\\n' "$FAKE_PAYLOAD"
exit "${FAKE_EXIT:-0}"
"""


def payload(count: int) -> str:
    """Return gitnexus cypher's one-row markdown table for `count` blank names."""
    return json.dumps({"markdown": f"| blank |\n| --- |\n| {count} |", "row_count": 1})


def run_check(tmp_path: Path, count: int = 0, exit_code: int = 0) -> tuple[subprocess.CompletedProcess[str], list[str], Path]:
    """Run one health check against a stub gitnexus and return its result, argv log and repo path."""
    binary = tmp_path / "bin"
    binary.mkdir(exist_ok=True)
    stub = binary / "gitnexus"
    stub.write_text(FAKE_GITNEXUS)
    stub.chmod(0o755)
    log = tmp_path / "gitnexus.log"
    repo = tmp_path / "worktree"
    repo.mkdir(exist_ok=True)
    env = dict(os.environ, PATH=f"{binary}:{os.environ['PATH']}", GITNEXUS_LOG=str(log),
               FAKE_PAYLOAD=payload(count), FAKE_EXIT=str(exit_code))
    result = subprocess.run([sys.executable, str(SCRIPTS[0]), "--repo", str(repo)],
                            capture_output=True, text=True, env=env)
    calls = log.read_text().splitlines() if log.exists() else []
    return result, calls, repo


def test_zero_blank_names_passes(tmp_path: Path) -> None:
    """An intact index passes and names the count."""
    result, _, _ = run_check(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "0 blank Function names" in result.stdout


def test_blank_names_block_naming_count(tmp_path: Path) -> None:
    """A blanked index fails and the message names the count and the rebuild command."""
    result, _, _ = run_check(tmp_path, count=4304)
    assert result.returncode == 1
    assert "4304 Function nodes have a blank name" in result.stderr
    assert "--force --index-only" in result.stderr


def test_query_failure_blocks(tmp_path: Path) -> None:
    """A failed query is its own block, never a pass."""
    result, _, _ = run_check(tmp_path, exit_code=1)
    assert result.returncode == 2
    assert "query failed" in result.stderr


def test_query_targets_the_absolute_worktree(tmp_path: Path) -> None:
    """The query runs against the resolved worktree path, not repo folder names."""
    _, calls, repo = run_check(tmp_path)
    assert len(calls) == 1
    assert 'MATCH (n:Function) WHERE n.name = "" RETURN count(n) AS blank' in calls[0]
    assert f"--repo {repo.resolve()}" in calls[0]


def test_lane_docs_state_the_reindex_rule() -> None:
    """The lanes doc splits fresh from re-index, bans --watch and names the health check."""
    text = DOCS.read_text(encoding="utf-8")
    assert "gitnexus analyze --index-only ." in text
    assert "gitnexus analyze --force --index-only ." in text
    assert "never run `gitnexus analyze --watch`" in text.lower()
    assert "super-board-gitnexus-health.py" in text



if __name__ == "__main__":
    import pytest_lite
    raise SystemExit(pytest_lite.main(globals()))

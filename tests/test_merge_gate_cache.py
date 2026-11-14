"""Checks the merge gate's verified-tree cache: a green suite is reused only for the same base, tree and commands."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "super-board-merge-gate.sh"

META_EMPTY = '{"files":[],"labels":[],"body":"","additions":0,"deletions":0,"changedFiles":0}'

GH_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GH_LOG"
case "$1 $2" in
  "pr view")
    case "$*" in
      *mergeCommit*)
        printf '{"state":"%s","headRefOid":"%s","mergeCommit":null}\\n' "${STUB_STATE:-OPEN}" "$STUB_OID"
        exit 0 ;;
    esac
    case "$*" in
      *labels*) cat "$STUB_META_FILE"; exit 0 ;;
    esac
    echo "$STUB_REF $STUB_OID"; exit 0 ;;
  "pr merge") exit "${STUB_MERGE_RC:-0}" ;;
  "pr diff") exit 0 ;;
esac
if [ "$1" = api ]; then
  if [ -n "${STUB_COMMENTS_FILE:-}" ]; then cat "$STUB_COMMENTS_FILE"; else printf '[]\\n'; fi
  exit 0
fi
exit 1
"""


def _git(cwd: Path, *args: str) -> str:
    """Run one git command in cwd and return its stdout."""
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout


def _commit(repo: Path, message: str) -> None:
    """Commit the current index with a throwaway identity."""
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", message)


class Harness:
    """A local bare origin, a working repo and a `gh` stub the gate can run against."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.repo = tmp_path / "repo"
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "README.md").write_text("base\n")
        _git(self.repo, "add", "-A")
        _commit(self.repo, "base")
        _git(self.repo, "remote", "add", "origin", str(origin))
        _git(self.repo, "push", "-q", "origin", "main")
        # feat-a and feat-b add the same content with different messages: different
        # heads, byte-identical tree — the cross-PR cache hit this gate exists for.
        for branch, message, content in (("feat-a", "feat a", "1\n"),
                                         ("feat-b", "feat b", "1\n"),
                                         ("feat-c", "feat c", "2\n")):
            _git(self.repo, "checkout", "-q", "-b", branch, "main")
            (self.repo / "x.txt").write_text(content)
            _git(self.repo, "add", "-A")
            _commit(self.repo, message)
            _git(self.repo, "push", "-q", "origin", branch)
        _git(self.repo, "checkout", "-q", "main")
        self.runs = tmp_path / "runs"
        self.gh_log = tmp_path / "gh.log"
        self.gh_log.write_text("")
        self.meta = tmp_path / "meta.json"
        self.meta.write_text(META_EMPTY)
        self.comments = tmp_path / "comments.json"
        self.comments.write_text("[]")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(GH_STUB)
        (self.bin / "gh").chmod(0o755)
        self.cache = self.repo / ".claude" / "super-board" / "inflight" / "verify-cache"
        self.logs = self.repo / ".claude" / "super-board" / "inflight" / "verify-logs"
        self.config = tmp_path / "config.json"
        self.set_commands([self.counting_command()])

    def counting_command(self) -> str:
        """Return a verify command that records each execution."""
        return f"sh -c 'echo run >> {self.runs}'"

    def set_commands(self, commands: list[str]) -> None:
        """Write the gate config with the given verify commands."""
        self.config.write_text(json.dumps({
            "base_branch": "main",
            "repo": {"path": str(self.repo), "remote": "https://github.com/acme/app"},
            "verify_commands": commands,
            "merge_policy": {"default": "auto"},
        }))

    def head(self, branch: str) -> str:
        """Return the branch's head commit sha."""
        return _git(self.repo, "rev-parse", branch).strip()

    def gate(self, pr: int, branch: str, *extra: str) -> subprocess.CompletedProcess[str]:
        """Run the merge gate for one PR whose head is the branch."""
        env = dict(os.environ)
        env.update({
            "PATH": f"{self.bin}:{env['PATH']}",
            "GH_LOG": str(self.gh_log),
            "SB_GITHUB_HALT_FILE": str(self.tmp / "halt.json"),
            "SB_GITHUB_RETRY_DELAY": "0",
            "STUB_REF": branch,
            "STUB_OID": self.head(branch),
            "STUB_META_FILE": str(self.meta),
            "STUB_COMMENTS_FILE": str(self.comments),
        })
        return subprocess.run(
            [str(GATE), "--config", str(self.config), "--pr", str(pr),
             "--lock-timeout", "5", *extra],
            cwd=self.repo, env=env, capture_output=True, text=True,
        )

    def verify_runs(self) -> int:
        """Return how many times the verify command has executed."""
        return len(self.runs.read_text().splitlines()) if self.runs.exists() else 0

    def set_qa_report(self, body: str | None) -> None:
        """Publish one QA report comment for the stub, or none when body is None."""
        self.comments.write_text("[]" if body is None else json.dumps([[{"body": body}]]))


def _cache_entries(harness: Harness) -> list[dict]:
    """Return every cached verify result on disk."""
    if not harness.cache.is_dir():
        return []
    return [json.loads(path.read_text()) for path in harness.cache.glob("*.json")]


def test_a_green_tree_is_reused_by_a_pr_with_the_same_tree(tmp_path: Path) -> None:
    """A second PR with the same base, tree and commands reuses the green result."""
    h = Harness(tmp_path)
    first = h.gate(1, "feat-a")
    assert first.returncode == 0, first.stderr
    assert h.verify_runs() == 1
    assert "verify-cache key:" in first.stderr

    second = h.gate(2, "feat-b")
    assert second.returncode == 0, second.stderr
    assert h.head("feat-a") != h.head("feat-b")
    assert h.verify_runs() == 1, second.stderr
    assert "verify: cached from #1 at" in second.stderr
    assert "verify: sh -c" not in second.stderr


def test_a_changed_tree_misses_the_cache(tmp_path: Path) -> None:
    """A different tree runs the suite again, even inside the TTL."""
    h = Harness(tmp_path)
    assert h.gate(1, "feat-a").returncode == 0
    changed = h.gate(2, "feat-c")
    assert changed.returncode == 0, changed.stderr
    assert h.verify_runs() == 2, changed.stderr
    assert "verify: cached from" not in changed.stderr


def test_a_failure_is_never_cached(tmp_path: Path) -> None:
    """A red verify runs again on the next attempt and leaves no green entry."""
    h = Harness(tmp_path)
    h.set_commands(["sh -c 'echo run >> %s; exit 1'" % h.runs])
    for attempt in (1, 2):
        result = h.gate(attempt, "feat-a")
        assert result.returncode == 2, result.stderr
        assert h.verify_runs() == attempt, result.stderr
    assert [e for e in _cache_entries(h) if e["status"] == "green"] == []


def test_an_entry_with_a_non_numeric_age_is_ignored(tmp_path: Path) -> None:
    """A hand-edited entry whose `at` is not a number re-runs instead of aborting the gate."""
    h = Harness(tmp_path)
    assert h.gate(1, "feat-a").returncode == 0
    entry_path = next(h.cache.glob("*.json"))
    entry = json.loads(entry_path.read_text())
    entry["at"] = "later"
    entry_path.write_text(json.dumps(entry))
    again = h.gate(1, "feat-a")
    assert again.returncode == 0, again.stderr
    assert h.verify_runs() == 2, again.stderr
    assert "verify: cached from" not in again.stderr


def test_an_entry_that_is_not_green_is_ignored(tmp_path: Path) -> None:
    """A non-green entry never stands in for a pass."""
    h = Harness(tmp_path)
    assert h.gate(1, "feat-a").returncode == 0
    entry_path = next(h.cache.glob("*.json"))
    entry = json.loads(entry_path.read_text())
    entry["status"] = "red"
    entry_path.write_text(json.dumps(entry))
    again = h.gate(1, "feat-a")
    assert again.returncode == 0, again.stderr
    assert h.verify_runs() == 2, again.stderr
    assert "verify: cached from" not in again.stderr


def test_a_base_move_invalidates_the_cache(tmp_path: Path) -> None:
    """A new base commit re-runs the suite even when the merged tree is unchanged."""
    h = Harness(tmp_path)
    assert h.gate(1, "feat-a").returncode == 0
    _git(h.repo, "checkout", "-q", "main")
    _commit(h.repo, "advance the base")
    _git(h.repo, "push", "-q", "origin", "main")
    moved = h.gate(1, "feat-a")
    assert moved.returncode == 0, moved.stderr
    assert h.verify_runs() == 2, moved.stderr
    assert "verify: cached from" not in moved.stderr


def test_ttl_expiry_invalidates_the_cache(tmp_path: Path) -> None:
    """A green older than the TTL is not reused."""
    h = Harness(tmp_path)
    assert h.gate(1, "feat-a").returncode == 0
    expired = h.gate(1, "feat-a", "--verify-cache-ttl", "0")
    assert expired.returncode == 0, expired.stderr
    assert h.verify_runs() == 2, expired.stderr
    assert "verify: cached from" not in expired.stderr


def test_a_changed_verify_command_invalidates_the_cache(tmp_path: Path) -> None:
    """A different command list re-runs the suite."""
    h = Harness(tmp_path)
    assert h.gate(1, "feat-a").returncode == 0
    h.set_commands([h.counting_command(), "true"])
    changed = h.gate(1, "feat-a")
    assert changed.returncode == 0, changed.stderr
    assert h.verify_runs() == 2, changed.stderr
    assert "verify: cached from" not in changed.stderr


def test_a_dry_run_records_nothing(tmp_path: Path) -> None:
    """A dry run proves no merge, so it writes no cache entry."""
    h = Harness(tmp_path)
    dry = h.gate(1, "feat-a", "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert h.verify_runs() == 1
    assert _cache_entries(h) == []


def test_a_changed_qa_selection_reruns_on_the_same_tree(tmp_path: Path) -> None:
    """The same tree and PR with a changed QA selection re-runs the suite."""
    h = Harness(tmp_path)
    h.set_qa_report("[qa] [report] ✅ passed · v1\nLocal tests: first selection\n")
    assert h.gate(1, "feat-a").returncode == 0
    assert h.verify_runs() == 1
    h.set_qa_report("[qa] [report] ✅ passed · v1\nLocal tests: second selection\n")
    again = h.gate(1, "feat-a")
    assert again.returncode == 0, again.stderr
    assert h.verify_runs() == 2, again.stderr
    assert "verify: cached from" not in again.stderr


def test_a_missing_qa_report_reruns_on_the_same_tree(tmp_path: Path) -> None:
    """A QA report that disappeared cannot reuse the green it once proved."""
    h = Harness(tmp_path)
    h.set_qa_report("[qa] [report] ✅ passed · v1\nLocal tests: selection\n")
    assert h.gate(1, "feat-a").returncode == 0
    h.set_qa_report(None)
    again = h.gate(1, "feat-a")
    assert again.returncode == 0, again.stderr
    assert h.verify_runs() == 2, again.stderr
    assert "verify: cached from" not in again.stderr


def test_an_identical_selection_and_tree_still_reuses(tmp_path: Path) -> None:
    """The selection is keyed by content, so identical reports share a green."""
    h = Harness(tmp_path)
    h.set_qa_report("[qa] [report] ✅ passed · v1\nLocal tests: selection\n")
    assert h.gate(1, "feat-a").returncode == 0
    second = h.gate(2, "feat-b")
    assert second.returncode == 0, second.stderr
    assert h.verify_runs() == 1, second.stderr
    assert "verify: cached from #1 at" in second.stderr


def test_an_unreadable_qa_selection_never_serves_a_later_green(tmp_path: Path) -> None:
    """A failed selection read records its own key, so a readable report still reruns."""
    h = Harness(tmp_path)
    h.comments.write_text("not json")
    assert h.gate(1, "feat-a").returncode == 0
    assert h.verify_runs() == 1
    h.set_qa_report("[qa] [report] ✅ passed · v1\nLocal tests: selection\n")
    again = h.gate(1, "feat-a")
    assert again.returncode == 0, again.stderr
    assert h.verify_runs() == 2, again.stderr
    assert "verify: cached from" not in again.stderr


def test_the_success_log_is_kept_after_cleanup(tmp_path: Path) -> None:
    """The run's output, command and head survive the scratch worktree's removal."""
    h = Harness(tmp_path)
    h.set_commands([f"sh -c 'echo the-selected-output; echo run >> {h.runs}'"])
    result = h.gate(1, "feat-a")
    assert result.returncode == 0, result.stderr
    logs = list(h.logs.glob("*.log"))
    assert len(logs) == 1, result.stderr
    text = logs[0].read_text()
    assert "the-selected-output" in text
    assert h.head("feat-a") in text
    assert "sh -c 'echo the-selected-output" in text


def test_a_relative_venv_interpreter_runs_in_the_scratch_worktree(tmp_path: Path) -> None:
    """The main checkout's git-ignored venvs/ reaches a relative `venvs/...` line."""
    h = Harness(tmp_path)
    marker = tmp_path / "venv-ran"
    interpreter = h.repo / "venvs" / "probe" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text(f"#!/usr/bin/env bash\nprintf ran > {marker}\n")
    interpreter.chmod(0o755)
    h.set_commands(["venvs/probe/bin/python"])
    result = h.gate(1, "feat-a")
    assert result.returncode == 0, result.stderr
    assert marker.read_text() == "ran"


def test_the_verify_commands_see_the_card_pr(tmp_path: Path) -> None:
    """The gate exports SB_PR so verify commands can find the card's QA report."""
    h = Harness(tmp_path)
    seen = tmp_path / "seen-pr"
    h.set_commands([f"sh -c 'printf %s \"$SB_PR\" > {seen}'"])
    result = h.gate(7, "feat-a")
    assert result.returncode == 0, result.stderr
    assert seen.read_text() == "7"


def test_the_cache_entry_names_its_key_base_tree_and_source(tmp_path: Path) -> None:
    """The stored entry carries the key, base commit, tree, head and source PR."""
    h = Harness(tmp_path)
    result = h.gate(7, "feat-a")
    assert result.returncode == 0, result.stderr
    key = next(line for line in result.stderr.splitlines() if "verify-cache key:" in line).split()[-1]
    entry = json.loads((h.cache / f"{key}.json").read_text())
    assert entry["status"] == "green"
    assert entry["pr"] == 7
    assert entry["head"] == h.head("feat-a")
    assert entry["base"] == h.head("main")
    assert len(entry["tree"]) == 40


def test_the_gate_prunes_old_verify_logs(tmp_path: Path) -> None:
    """A gate run deletes logs past the retention and keeps a fresh one."""
    h = Harness(tmp_path)
    h.logs.mkdir(parents=True)
    old = h.logs / "old.log"
    old.write_text("head: dead\n")
    stamp = time.time() - 30 * 86400
    os.utime(old, (stamp, stamp))
    fresh = h.logs / "fresh.log"
    fresh.write_text("head: live\n")
    result = h.gate(1, "feat-a")
    assert result.returncode == 0, result.stderr
    assert not old.exists()
    assert fresh.exists()
    assert "prune: removed 1 verify log" in result.stderr


if __name__ == "__main__":
    import pytest_lite
    raise SystemExit(pytest_lite.main(globals()))

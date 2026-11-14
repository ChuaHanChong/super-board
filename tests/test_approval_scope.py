"""Checks the pinned human-approval scope: the PR head and required human steps, never the base.

The scope a request pins must survive an `origin/main` move (the merge diff is recomputed
against a new merge base) while a new PR head still invalidates the approval, and the gate
still reruns the card's QA selection on the current merge result.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "super-board-merge-gate.sh"
APPROVAL = ROOT / "scripts" / "super-board-approval.py"
POLICY = ROOT / "scripts" / "super-board-merge-policy.py"

CAP = 10  # merge_policy.auto_max_lines: a bigger diff asks for a human

GH_STUB = """#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]
log = os.environ.get("GH_LOG")
if log:
    with open(log, "a") as stream:
        stream.write(" ".join(args) + "\\n")


def emit(value):
    sys.stdout.write(value if isinstance(value, str) else json.dumps(value))
    sys.exit(0)


def read(path):
    try:
        return open(path).read()
    except OSError:
        return ""


if args[:2] == ["pr", "view"]:
    if "mergeCommit" in " ".join(args):
        emit({"state": os.environ.get("STUB_STATE", "OPEN"),
              "headRefOid": os.environ["STUB_OID"], "mergeCommit": None})
    if any("labels" in arg for arg in args):
        emit(read(os.environ["STUB_META"]))
    emit(f"{os.environ['STUB_REF']} {os.environ['STUB_OID']}")
if args[:2] == ["pr", "diff"]:
    emit(read(os.environ["STUB_DIFF"]))
if args[:2] == ["pr", "merge"]:
    sys.exit(int(os.environ.get("STUB_MERGE_RC", "0")))
if args[0] == "api":
    if "graphql" in args:
        emit([{"data": {"repository": {
            "defaultBranchRef": {"name": "main"},
            "pullRequest": {"headRefOid": os.environ["STUB_OID"], "state": "OPEN",
                            "baseRefName": "main", "body": "",
                            "closingIssuesReferences": {"pageInfo": {"hasNextPage": False,
                                                                     "endCursor": None},
                                                        "nodes": []}}}}}])
    if args[-1].endswith("/permission"):
        emit({"permission": os.environ.get("STUB_PERMISSION", "write")})
    if any("/comments" in arg for arg in args):
        emit(json.loads(read(os.environ["STUB_COMMENTS"]) or "[]"))
    emit({})
sys.exit(1)
"""


def approval_module():
    """Load the approval helper as a module without running its CLI."""
    spec = importlib.util.spec_from_file_location("super_board_approval", APPROVAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> str:
    """Run one git command in cwd and return its stdout."""
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout


def _commit(repo: Path, message: str) -> None:
    """Commit the current index with a throwaway identity."""
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
         "--allow-empty", "-m", message)


def _diff(path: str, added: int) -> str:
    """Return a one-file unified diff with `added` added lines, as GitHub would render it."""
    body = "".join(f"+line {index}\n" for index in range(1, added + 1))
    return (f"diff --git a/{path} b/{path}\nindex 0000000..1111111 100644\n"
            f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{added} @@\n" + body)


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
        _git(self.repo, "checkout", "-q", "-b", "feat-a", "main")
        (self.repo / "x.txt").write_text("feature\n")
        _git(self.repo, "add", "-A")
        _commit(self.repo, "feat a")
        _git(self.repo, "push", "-q", "origin", "feat-a")
        _git(self.repo, "checkout", "-q", "main")

        self.runs = tmp_path / "runs"
        self.gh_log = tmp_path / "gh.log"
        self.gh_log.write_text("")
        self.meta = tmp_path / "meta.json"
        self.diff = tmp_path / "diff.txt"
        self.set_diff(15)
        self.comments = tmp_path / "comments.json"
        self.comments.write_text("[[]]")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(GH_STUB)
        (self.bin / "gh").chmod(0o755)
        self.config = tmp_path / "config.json"
        self.write_config()
        self.verify_runs = 0

    def write_config(self) -> None:
        """Write the gate config the harness's counting verify command runs under."""
        self.config.write_text(json.dumps({
            "base_branch": "main",
            "repo": {"path": str(self.repo), "remote": "https://github.com/acme/app"},
            "verify_commands": [f"sh -c 'echo run >> {self.runs}'"],
            "merge_policy": {"default": "auto", "auto_max_lines": CAP},
            "host": "claude",
        }))

    def set_diff(self, added: int) -> None:
        """Publish PR metadata and its diff with exactly `added` added lines."""
        self.meta.write_text(json.dumps({
            "files": [{"path": "x.txt"}], "labels": [], "body": "",
            "additions": added, "deletions": 0, "changedFiles": 1,
        }))
        self.diff.write_text(_diff("x.txt", added))

    def head(self, branch: str) -> str:
        """Return the branch's head commit sha."""
        return _git(self.repo, "rev-parse", branch).strip()

    def advance_main(self) -> None:
        """Move origin/main forward by one commit, as a concurrent merge does."""
        _git(self.repo, "checkout", "-q", "main")
        _commit(self.repo, "advance the base")
        _git(self.repo, "push", "-q", "origin", "main")

    def push_head(self, branch: str) -> str:
        """Add one commit to a branch and push it, then return the new head."""
        _git(self.repo, "checkout", "-q", branch)
        _commit(self.repo, "new head")
        head = self.head(branch)
        _git(self.repo, "push", "-q", "origin", branch)
        _git(self.repo, "checkout", "-q", "main")
        return head

    def plan(self) -> dict:
        """Return the merge-policy plan the gate derives from the current metadata and diff."""
        result = subprocess.run(
            [sys.executable, str(POLICY), "--config", str(self.config),
             "--meta", str(self.meta), "--diff", str(self.diff)],
            check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def request(self, head: str) -> str:
        """Return the approval-request marker line pinning head under the current plan."""
        module = approval_module()
        return module.marker(module.request_for("acme/app", 1, head, module.scope_for(self.plan())))

    @staticmethod
    def comment(ident: int, body: str, minute: int = 0) -> dict:
        """Return one REST comment authored by a trusted human."""
        return {"id": ident, "body": body, "user": {"login": "t1z", "type": "User"},
                "created_at": f"2026-11-14T00:0{minute}:00Z",
                "updated_at": f"2026-11-14T00:0{minute}:00Z"}

    def approve(self, request: str, done: str = "done") -> None:
        """Publish the pinned request and the human's reply that answers it."""
        self.comments.write_text(json.dumps([[self.comment(1, request),
                                              self.comment(2, done, minute=1)]]))

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
            "STUB_META": str(self.meta),
            "STUB_DIFF": str(self.diff),
            "STUB_COMMENTS": str(self.comments),
        })
        return subprocess.run(
            [str(GATE), "--config", str(self.config), "--pr", str(pr),
             "--lock-timeout", "5", *extra],
            cwd=self.repo, env=env, capture_output=True, text=True,
        )

    def verify_count(self) -> int:
        """Return how many times the verify command has executed."""
        return len(self.runs.read_text().splitlines()) if self.runs.exists() else 0


def _requests(text: str) -> list[dict]:
    """Return the approval-request payloads printed by one gate run."""
    prefix = "approval-request: "
    return [json.loads(line[len(prefix):]) for line in text.splitlines()
            if line.startswith(prefix)]


def test_scope_ignores_policy_holds_and_tracks_each_human_step() -> None:
    """Policy holds (`human`) are base-dependent evidence; migrations, run and needs-you are steps."""
    module = approval_module()
    plan = {"human": [{"category": "size", "why": "15 changed lines > auto_max_lines 10"}],
            "migrations": ["db/migrate/001.sql"],
            "run": [{"env": "staging", "cmd": "migrate staging"}],
            "needs_you": ["run the prod migration"], "done": False}
    moved = dict(plan, human=[{"category": "size", "why": "20 changed lines > auto_max_lines 10"}])
    assert module.scope_for(plan) == module.scope_for(moved)
    assert module.scope_for(plan) != module.scope_for(dict(plan, migrations=["db/migrate/002.sql"]))
    assert module.scope_for(plan) != module.scope_for(dict(plan, run=[{"env": "live", "cmd": "x"}]))
    assert module.scope_for(plan) != module.scope_for(dict(plan, needs_you=["run the live migration"]))


def test_scope_does_not_depend_on_step_order() -> None:
    """A reordered file list is the same required migration set."""
    module = approval_module()
    plan = {"migrations": ["db/migrate/002.sql", "db/migrate/001.sql"],
            "run": [{"env": "b", "cmd": "y"}, {"env": "a", "cmd": "x"}],
            "needs_you": ["two", "one"]}
    reordered = {"migrations": list(reversed(plan["migrations"])),
                 "run": list(reversed(plan["run"])),
                 "needs_you": list(reversed(plan["needs_you"]))}
    assert module.scope_for(plan) == module.scope_for(reordered)


def test_a_main_move_after_done_still_merges_and_reruns_the_qa_selection(tmp_path: Path) -> None:
    """A done posted at the head survives an origin/main move: the gate merges and reruns verify."""
    h = Harness(tmp_path)
    first = h.gate(1, "feat-a")
    assert first.returncode == 7, first.stderr
    assert "human-gate: size" in first.stdout
    request = _requests(first.stdout)
    assert len(request) == 1, first.stdout
    assert h.verify_count() == 0, "a policy hold must not spend the build proof"

    h.approve(f"approval-request: {json.dumps(request[0], sort_keys=True, separators=(',', ':'))}")
    approved = h.gate(1, "feat-a")
    assert approved.returncode == 0, approved.stderr
    assert h.verify_count() == 1

    h.advance_main()
    h.set_diff(20)  # the same PR diff recomputed against the new merge base
    moved = h.gate(1, "feat-a")
    assert moved.returncode == 0, moved.stderr
    assert not _requests(moved.stdout), "a base move must not re-request the approval"
    assert h.verify_count() == 2, "the gate must rerun the QA selection against the current base"


def test_a_new_head_after_done_is_re_requested(tmp_path: Path) -> None:
    """Any new commit invalidates the approval and makes the gate pin a fresh request."""
    h = Harness(tmp_path)
    first = h.gate(1, "feat-a")
    assert first.returncode == 7, first.stderr
    old = _requests(first.stdout)
    assert len(old) == 1, first.stdout
    h.approve(f"approval-request: {json.dumps(old[0], sort_keys=True, separators=(',', ':'))}")
    assert h.gate(1, "feat-a").returncode == 0

    new_head = h.push_head("feat-a")
    again = h.gate(1, "feat-a")
    assert again.returncode == 7, again.stderr
    fresh = _requests(again.stdout)
    assert len(fresh) == 1, again.stdout
    assert fresh[0]["head"] == new_head
    assert fresh[0]["head"] != old[0]["head"]


if __name__ == "__main__":
    import pytest_lite
    raise SystemExit(pytest_lite.main(globals()))

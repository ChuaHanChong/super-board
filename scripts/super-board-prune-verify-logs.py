#!/usr/bin/env python3
"""Prune the merge gate's verify logs by age, never live evidence.

The gate writes `.claude/super-board/inflight/verify-logs/<key>.log` for every
uncached verify run and nothing removed them, so the directory grew without
bound. Retention is 7 days (`--retention-hours`, default 168): long past the 4 h
lane timeout, so a log from a run still in flight is never old enough to select.
While `merge.lock` is held a gate is verifying, so nothing is pruned at all.

  python3 .claude/bin/super-board-prune-verify-logs.py --root <repo>

The merge gate calls it before taking the lock; the nightly loop may call it too.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

RETENTION_HOURS = 168


def prune(logs: Path, lock: Path, retention_hours: float) -> int:
    """Delete logs older than the retention and return how many were removed."""
    if lock.exists():
        print(f"prune: merge lock held at {lock}; keeping every verify log")
        return 0
    if not logs.is_dir():
        print("prune: removed 0 verify log(s); nothing to prune")
        return 0
    cutoff = time.time() - retention_hours * 3600
    removed = 0
    for log in sorted(logs.glob("*.log")):
        try:
            if log.stat().st_mtime < cutoff:
                log.unlink()
                removed += 1
        except FileNotFoundError:
            continue
    print(f"prune: removed {removed} verify log(s) older than {retention_hours:g}h")
    return removed


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, prune the board's verify logs, and report the count."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--retention-hours", type=float, default=RETENTION_HOURS,
                        help=f"age past which a log is deleted (default {RETENTION_HOURS})")
    args = parser.parse_args(argv)
    if args.retention_hours <= 0:
        parser.error("--retention-hours must be positive: a zero retention deletes a log a run is writing")
    inflight = Path(args.root) / ".claude" / "super-board" / "inflight"
    prune(inflight / "verify-logs", inflight / "merge.lock", args.retention_hours)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Gate a GitNexus index: blank Function names mean every impact query silently returns nothing."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

QUERY = 'MATCH (n:Function) WHERE n.name = "" RETURN count(n) AS blank'


def blank_count(payload: str) -> int:
    """Return the count cell of the query's one-row markdown table."""
    rows = [line for line in json.loads(payload)["markdown"].splitlines() if line.strip()]
    return int(rows[-1].strip().strip("|").split("|")[0].strip())


def main(argv: list[str] | None = None) -> int:
    """Run the blank-name query and exit 1 naming the count when it is not zero."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="worktree to query (. resolves to an absolute path)")
    parser.add_argument("--gitnexus", default="gitnexus", help="gitnexus binary")
    args = parser.parse_args(argv)
    repo = str(Path(args.repo).resolve())
    result = subprocess.run([args.gitnexus, "cypher", QUERY, "--repo", repo],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"gitnexus health: query failed in {repo}: "
              f"{(result.stderr or result.stdout).strip()}", file=sys.stderr)
        return 2
    try:
        count = blank_count(result.stdout)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        print(f"gitnexus health: unreadable query output in {repo}: {error}", file=sys.stderr)
        return 2
    if count:
        print(f"gitnexus health: {count} Function nodes have a blank name in {repo} - Blocked; "
              "re-index with `gitnexus analyze --force --index-only .`", file=sys.stderr)
        return 1
    print(f"gitnexus health: 0 blank Function names in {repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

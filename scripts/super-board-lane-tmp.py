#!/usr/bin/env python3
"""Per-lane temp root: create it for one lane, then remove it and the worktrees it registered.

`create <base> <card> <lane>` prints the root it made. `cleanup <repo> <root> [stale_root]`
removes every registered worktree under the root, reports (never deletes) a registered worktree
under `stale_root` (default /tmp, which a host may mount read-only), then removes the root. A
worktree git refuses to remove keeps the root, so work survives.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

TMP = Path('/tmp')


def create(base: str, card: str, lane: str) -> Path:
    """Create <base>/<card>-<lane> with the uv cache and python dirs inside; print the path."""
    root = Path(base).resolve() / f'{card}-{lane}'
    for name in ('', 'uv-cache', 'uv-python'):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def worktrees(repo: str) -> list[Path]:
    """Registered worktree paths of one repo; empty when git cannot list them."""
    listed = subprocess.run(['git', '-C', repo, 'worktree', 'list', '--porcelain'],
                            capture_output=True, text=True)
    if listed.returncode:
        return []
    return [Path(line[len('worktree '):]) for line in listed.stdout.splitlines()
            if line.startswith('worktree ')]


def cleanup(repo: str, root: str, stale_root: str = str(TMP)) -> int:
    """Remove worktrees under the root, report temp-tree leftovers, then remove the root."""
    lane_root = Path(root).resolve()
    stale_tree = Path(stale_root).resolve()
    under, stale = [], []
    for path in worktrees(repo):
        if path == lane_root or lane_root in path.parents:
            under.append(path)
        elif stale_tree in path.parents:
            stale.append(path)
    kept = []
    # Deepest first: a worktree inside another one goes before its parent folder.
    for path in sorted(under, key=lambda item: len(item.parts), reverse=True):
        removed = subprocess.run(['git', '-C', repo, 'worktree', 'remove', str(path)],
                                 capture_output=True, text=True)
        if removed.returncode:
            kept.append(path)
            print(f'lane-tmp: kept worktree {path}: {removed.stderr.strip()}', file=sys.stderr)
    for path in stale:
        print(f'stale-tmp-worktree: {path} (reported, not deleted)', file=sys.stderr)
    if kept:
        print(f'lane-tmp: root kept at {lane_root} so the work above survives', file=sys.stderr)
        return 1
    shutil.rmtree(lane_root, ignore_errors=True)
    return 0


def main(argv: list[str]) -> int:
    """Run the create or cleanup subcommand."""
    if len(argv) == 4 and argv[0] == 'create':
        print(create(argv[1], argv[2], argv[3]))
        return 0
    if len(argv) == 3 and argv[0] == 'cleanup':
        return cleanup(argv[1], argv[2])
    if len(argv) == 4 and argv[0] == 'cleanup':
        return cleanup(argv[1], argv[2], argv[3])
    print('usage: super-board-lane-tmp.py create <base> <card> <lane> | '
          'cleanup <repo> <root> [stale_root]', file=sys.stderr)
    return 64


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

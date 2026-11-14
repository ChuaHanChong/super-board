# GitNexus in the lanes

Use GitNexus on every code card, in the lane's own worktree. A code card is any card except a `docs` card.

## Setup

1. Index the worktree from its root. The command depends on whether it already has an index:
   - Fresh worktree, no `.gitnexus` folder: `gitnexus analyze --index-only .`
   - Worktree that already has `.gitnexus` (a rebuild round, the run after merging `origin/main`, any second index): `gitnexus analyze --force --index-only .`
2. Never run `gitnexus analyze --watch`, and never index a worktree that already has `.gitnexus` without `--force`: the incremental refresh blanks `Function` `name`/`id`/`filePath` (seen on gitnexus 1.6.12), so `impact`, `context` and `detect-changes` return nothing. `--force` rebuilds the graph; `--index-only` writes nothing into the PR. A research card already indexed in its preamble does not repeat this.
3. Health check after every index: `.claude/bin/super-board-gitnexus-health.py --repo <absolute worktree path>`. It runs `MATCH (n:Function) WHERE n.name = "" RETURN count(n)`. A non-zero count Blocks the lane, and the block names the count.
4. Pass the worktree's absolute path as `repo`, because folder names repeat across projects.
5. Run `gitnexus clean --force` in the worktree on every exit from the lane.

## What each lane runs

| Lane or card | Use |
|---|---|
| Build, any label or none, unless a row below fits | `gitnexus-exploring`, then `gitnexus-impact-analysis` before editing |
| Build, `bug` | `gitnexus-debugging`, plus `trace` between the symptom and the suspect |
| Build, `refactor` or `tech-debt` | `gitnexus-refactoring`; `rename` is not allowlisted (it can write outside the worktree), so edit by hand from `impact` |
| Build, every code card | `detect-changes --scope compare --base-ref origin/<base>` before the final commit: an unexpected symbol is scope drift, HIGH or CRITICAL goes in the `risk` block |
| Research card | Its [preamble](research-preamble.md), plus the Build row for its label |
| QA, test-gap check | `detect-changes --scope compare --base-ref origin/<base>`, then aim tests at the affected flows |
| QA, security pass | `gitnexus-taint-analysis`: index with `--pdg`, then `explain` and `pdg_query`, in addition to `pr-security-review` |
| Review | `gitnexus-pr-review`, plus `check --cycles`: a caller the diff breaks is a Bug finding, an understated `risk` block is a Gap finding |
| Review, diff touches an API route or tool definition | `api_impact`, `shape_check`, `route_map`, `tool_map` |
| `/super-collect architecture` | Clusters, processes, `check --cycles` and `cypher` as the finder's input |

## Rules

1. `gitnexus` is required on a code card: readiness halts without it. A failed index is Blocked, naming the error.
   A row's skill the host does not have: run its commands directly.
2. An empty `impact` is not proof of safety: `getattr`, registries, decorators and Hydra `_target_` leave no edge. Also text-search the symbol, including config files.
3. A blank `Function` name is a broken index, not a clean one: the health check in Setup decides, never an empty `impact` result.

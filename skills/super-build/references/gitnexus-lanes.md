# GitNexus in the lanes

Use GitNexus on every code card, in the lane's own worktree. A code card is any card except a `docs` card.
It finds what a change reaches, so a lane reads callers and flows instead of guessing from text matches.

## Setup

1. Index the worktree: `gitnexus analyze --index-only .` from its root.
   `--index-only` writes nothing into the PR. A research card already indexed in its preamble does not repeat this.
2. Pass the worktree's absolute path as `repo`, because folder names repeat across projects.
3. Run `gitnexus clean --force` in the worktree on every exit from the lane.

## What each lane runs

| Lane or card | Use |
|---|---|
| Build, any label or none, unless a row below fits | `gitnexus-exploring`, then `gitnexus-impact-analysis` before editing |
| Build, `bug` | `gitnexus-debugging`, plus `trace` between the symptom and the suspect |
| Build, `refactor` or `tech-debt` | `gitnexus-refactoring`. `rename` is not allowlisted because it can write outside the worktree: use it only if the host asks a person, otherwise edit by hand from `impact` |
| Build, every code card | `detect-changes --scope compare --base-ref origin/<base>` before the final commit: an unexpected symbol is scope drift, HIGH or CRITICAL goes in the `risk` block |
| Research card | Its [preamble](research-preamble.md), plus the Build row for its label |
| QA, test-gap check | `detect-changes --scope compare --base-ref origin/<base>`, then aim tests at the affected flows |
| QA, security pass | `gitnexus-taint-analysis`: index with `--pdg`, then `explain` and `pdg_query`, in addition to `pr-security-review` |
| Review | `gitnexus-pr-review`, plus `check --cycles`: a caller the diff breaks is a Bug finding, an understated `risk` block is a Gap finding |
| Review, diff touches an API route or tool definition | `api_impact`, `shape_check`, `route_map`, `tool_map` |
| `/super-collect architecture` | Clusters, processes, `check --cycles` and `cypher` as the finder's input |

## Rules

1. A plain card with no `gitnexus`, or a failed index: use text search and write `GitNexus: unavailable, <why>` in the lane's report. Do not halt.
   A row's skill the host does not have: run its commands directly. Readiness does not track these skills, because it would load all of them on every card.
2. An empty `impact` is not proof of safety: `getattr`, registries, decorators and Hydra `_target_` leave no edge. Also text-search the symbol, including config files.
3. A Codex or OpenCode lane is CLI-only: its index is in a private `GITNEXUS_HOME` that the MCP server cannot see, even when the server is enabled.
   It ignores MCP tools and `gitnexus://` resources, including where a skill says to read them, and uses `query`, `context`, `impact`, `trace`, `detect-changes`, `check` and `cypher` with `-r <worktree path>`.
   `api_impact`, `shape_check`, `route_map`, `tool_map`, `pdg_query` and `explain` exist only as MCP tools, so there it uses `cypher` where it can and otherwise text search, and says so in its report.

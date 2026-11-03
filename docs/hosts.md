# Agent hosts

super-board runs inside an agent host: the CLI whose session types `/super-board run`.
`scripts/super-board-host.sh` (installed as `.claude/bin/super-board-host.sh`) names it.

| Host value | Tested version | Start a run | Sign-in | Gaps |
|---|---|---|---|---|
| `claude` | Claude Code 2.1.302 | `/super-board run` (Workflow backend) | `claude` then `/login`; `gh auth login` | None. The reference host. |
| `codex` | codex-cli 0.160.0 | `/super-board run` inside Codex runs as `--codex`; from Claude, `/super-board run --codex` | `codex login`; `gh auth login` | No Workflow tool, so every lane is headless `codex exec`. Review runs only with explicit `--codex` (a host-switched plain `run` counts). No Claude usage guard. |
| `opencode` | OpenCode v2.2.5 | `/super-board run` inside OpenCode runs as `--opencode`; from Claude, `/super-board run --opencode` | `opencode auth login`; `gh auth login` | No Workflow tool, so every lane is headless `opencode run`. Its `permission` rules filter tool calls only, so each lane runs inside an OS write jail (Seatbelt on macOS, bubblewrap on Linux): write is limited to the worktree, tmp and OpenCode's own state dirs. No schema flag, so the launcher extracts the result JSON from the last text event and validates it. No model ladder, so no router. Review runs only with explicit `--opencode`. Paper2Code is claude/codex only. |

Every host also needs `gh`, `jq`, `gitnexus`, bash 3.2+ and Python 3.9+.

## How the host is picked

`super-board-host.sh [--config <config.json>]` prints one value. First match wins:

1. `SUPER_BOARD_HOST=claude|codex|opencode`, the manual override. Any other value exits 64.
2. `CODEX_THREAD_ID` or `CODEX_SESSION_ID` → `codex`.
3. `OPENCODE=1` → `opencode`. Checked before `CLAUDECODE`, which leaks into an OpenCode
   session started from Claude Code. `AGENT=1` is ignored: other tools set it too.
4. `CLAUDECODE` → `claude`.
5. The board config's top-level `host` key, when `--config` is given.
6. Nothing matched: empty stdout, a hint on stderr, exit 65. The run halts and asks for a
   host. It never guesses Claude.

A live env sign beats the saved config, so a Codex lane started from a Claude-configured
board still answers `codex`.

Onboard always writes `host` into `.claude/super-board/configs/<slug>.json`.
`super-board-setup.py fix` adds a missing one from `--host`; `check` flags any other value.

## Evidence

- Codex: env of `codex exec -s read-only`, 2026-10-04 (recorded in the script header).
- OpenCode: env diff of an `opencode run` shell, 2026-10-19: `OPENCODE=1`,
  `OPENCODE_SESSION_ID`, `OPENCODE_TERMINAL=1`, `AGENT=1`. Lane evidence, 2026-11-03
  on v2.2.5: `opencode debug paths` lists the state dirs the jail grants, and
  `opencode run --format json --standalone` emits `{"type":"text","part":{"type":"text",...}}`
  events, the last of which carries the lane result.

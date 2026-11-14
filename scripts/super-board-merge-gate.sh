#!/usr/bin/env bash
# super-board-merge-gate.sh — take the merge mutex, prove the branch still works
# against the base as it is RIGHT NOW, then merge. Release either way.
#
# WHY THIS EXISTS, MEASURED
#
# GitHub's `mergeable: MERGEABLE` / `mergeStateStatus: CLEAN` answers one
# question: does the text conflict? It says nothing about whether the branch
# still compiles against the base it is about to land on. On 2026-08-20 that gap
# was hit twice in one session on the same repo:
#
#   PR #89 read MERGEABLE/CLEAN and failed `tsc` against current `staging`,
#   because a PR that merged after #89 was tested had added a member to a shared
#   interface. Eleven test files that git merged without a single conflict marker
#   no longer typechecked. Merging on GitHub's word would have turned the base
#   branch red.
#
# Nothing textual conflicted. Nothing was wrong with either branch. The two facts
# were simply established at different times, and only one of them was rechecked.
#
# WHY THE CHECK IS INSIDE THE LOCK, NOT BEFORE IT
#
# A check that runs before the mutex proves the branch was good against a base
# that another lane may replace while this one waits its turn — which is exactly
# the stale-approval shape above, reintroduced one level down. Inside the lock,
# nothing can move the base between the proof and the merge.
#
# The cost is one verification run serialised per merge. The alternative, paid
# once, is a red base branch and every lane after it bouncing on someone else's
# failure.
#
# WHY A DIRECTORY LOCK RATHER THAN THE ORCHESTRATOR'S PROMISE CHAIN
#
# The previous mutex lived in the wave workflow as a JS promise chain, which
# serialised the WHOLE Review lane — reading the diff, rerunning the suite and
# the truth-check all queued behind one card, not just the merge. It also could
# not be seen by the `claude-p` backend or by a second orchestrator on another
# machine. `mkdir` is atomic on every POSIX filesystem, so the lock is visible to
# anything that can see the repo.
#
# CONFIG
#
#   verify_commands: ["cd server && npm run typecheck", "cd server && npm test"]
#
# Missing, empty, or whitespace-only commands halt with exit 9 before locking or
# reading GitHub. Configure the owning project's checks; this gate invents none.
#
# Usage:
#   super-board-merge-gate.sh --config <config.json> --pr <number>
#                             [--expect-head <sha>] [--subject <title>] [--body-file <md>]
#                             [--lock-timeout 1800] [--stale-after 5400]
#                             [--verify-cache-ttl 1200] [--dry-run]
#
# VERIFIED-TREE CACHE
#
# Several PRs usually share one base, so the same suite is proven green again and
# again for a tree that has not changed. The gate hashes what it is about to prove:
# base commit + the merged tree it verifies + the verify command list and the
# `scripts/verify.sh` those commands run + the QA report selection the commands
# read - and reuses a green result recorded under that key within
# `--verify-cache-ttl` (default 1200s). A new push (different tree), a moved base,
# a changed command list, a changed/missing/failing QA report, an expired entry or
# a cache miss runs the full suite as before. The key itself is printed, so the log
# proves what was reused: `verify: cached from #<pr> at <time> (key <key>)`.
#
# Only a green run is recorded. A failure never writes an entry, so it can never be
# replayed as a pass. The run's own output is kept under
# `.claude/super-board/inflight/verify-logs/<key>.log` with its head and command,
# outside the scratch worktree the gate deletes. Those logs are pruned past a 7-day
# retention by `super-board-prune-verify-logs.py`, which the gate calls before it
# takes the lock and which deletes nothing while `merge.lock` is held — a log from
# a run in flight is hours old, never days. Everything else stays as it was:
# the check still happens inside the merge lock, approval pins the head, and
# `--match-head-commit` still makes GitHub refuse a push that landed during
# verification.
#
# `--expect-head` is the PR head commit the Reviewer actually reviewed and
# tested (its `headRefOid` when review passed). The gate pins everything to one
# commit: it verifies that commit, and merges with `--match-head-commit`, so a
# push that lands after review — or during verification — cannot ride in on
# evidence gathered for a different commit. Without the flag the gate pins the
# head it reads on entry and warns.
#
# `--subject` / `--body-file` set the squash commit message (writing-standard.md
# § 1): subject = the PR title (`🐛 [fix] receipts: …`), body = the commit bullets
# plus `Closes #N`. Without them GitHub writes its own message.
#
# `--lock-timeout` is how long THIS caller waits for its turn. `--stale-after` is
# how old a lock must be before it is presumed abandoned. They are deliberately
# two numbers: collapsing them means a caller that waits 20 minutes will reap a
# lock legitimately held for 20 minutes by a slow verification run — which is
# exactly the merge it was waiting politely for.
#
# Exit codes, all meaningful to the caller:
#   0  merged
#   2  verification failed — branch needs a rebase pass, NOT a Blocked card
#   3  PR is closed without a merge; no merge attempted
#   4  could not take the lock within the timeout
#   5  the base could not be merged in (real conflict) — needs a rebase pass
#   6  the PR head is not the commit that was reviewed — review evidence is void,
#      the card goes back to Review (not Blocked, not a rebase pass)
#   7  merge policy says a human merges this one (money / auth / destructive
#      schema, a diff over auto_max_lines — default 400, "big PR — please
#      review" — or merge_policy.default "human"). Stdout lists each
#      `human-gate: <category> — <evidence>`. Nothing ran, nothing merged; the
#      card → Blocked with the 🙋 template: the human reviews and merges it, or
#      comments "done" after its pinned request to approve — the next wave re-runs
#      the gate, which then skips the policy check and merges.
#   9  verification-readiness: repair config.verify_commands and restart; preserve
#      card/worktree/approval state. Never bounce to Build or retry a rebase.
#   10 the gate's own checkout is behind origin/<base>: fast-forward it, else
#      merged board tooling (card moves, acceptance ticks, approvals) never runs.
#   11 a `Closes #N` issue still has open acceptance boxes: tick each as its
#      evidence lands, or drop the Closes line. Bulk ticking at merge hides a gap.
#   79 required GitHub evidence unavailable: local run halt; preserve card and
#      approval state, stop dispatch, and explicitly restart after diagnosis.
#   8  🙋 needs you — the PR has migrations for a database the robot may not
#      touch (merge_policy → migrations.allowed_envs), an allowed migrate command
#      failed, or a human-only step is declared (`needs-you:` line in the PR body,
#      or migrations.human_steps). Stdout lists the exact commands as
#      `needs-you: <command>` lines. Card → Blocked with the 🙋 template; once the
#      current request has verified trusted-human approval, the gate re-runs and
#      merges.
#
# MERGE POLICY AND MIGRATIONS (config, all optional — defaults shown in
# references/config-schema.json)
#
#   merge_policy: { default: "auto"|"human", auto_max_lines: 400, size_exclude,
#                   always_human: { <category>: {labels, paths, keywords} } }
#   migrations:   { globs, allowed_envs, target_env, commands: {<env>: cmd},
#                   human_steps }
#
# Detection reads the PR's labels, changed paths and the diff's ADDED lines
# (keywords, case-insensitive). The policy is checked before verification — a
# card a human will merge does not need the gate's build proof spent on it —
# and migrations run after verification, inside the lock, right before the
# merge. `--dry-run` reports both and runs neither.
set -euo pipefail
# Fixed read commands: a malformed payload is GitHub's, so it halts (#32).
export SB_GITHUB_READ_STRICT=1
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GITHUB_READ="$HERE/super-board-github-read.py"

CONFIG=""; PR=""; LOCK_TIMEOUT=1800; STALE_AFTER=""; DRY=0; EXPECT_HEAD=""; SUBJECT=""; MSG_FILE=""
CACHE_TTL=1200
while [ $# -gt 0 ]; do
  case "$1" in
    --config)        CONFIG="$2"; shift 2 ;;
    --pr)            PR="$2"; shift 2 ;;
    --expect-head)   EXPECT_HEAD="$2"; shift 2 ;;
    --subject)       SUBJECT="$2"; shift 2 ;;
    --body-file)     MSG_FILE="$2"; shift 2 ;;
    --lock-timeout)  LOCK_TIMEOUT="$2"; shift 2 ;;
    --stale-after)   STALE_AFTER="$2"; shift 2 ;;
    --verify-cache-ttl) CACHE_TTL="$2"; shift 2 ;;
    --dry-run)       DRY=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done
[ -n "$CONFIG" ] && [ -e "$CONFIG" ] || { echo "config not found: ${CONFIG:-<unset>}" >&2; exit 66; }
[ -n "$PR" ] || { echo "--pr <number> is required" >&2; exit 64; }
case "$CACHE_TTL" in
  ''|*[!0-9]*) echo "--verify-cache-ttl needs whole seconds, got: $CACHE_TTL" >&2; exit 64 ;;
esac
[ -z "$MSG_FILE" ] || [ -r "$MSG_FILE" ] || { echo "--body-file not readable: $MSG_FILE" >&2; exit 66; }
# A lock is presumed abandoned only well past the point a caller stops waiting,
# so a slow-but-alive merge is never stolen from. The floor matters as much as
# the multiple: an impatient caller (say --lock-timeout 6 in a test) would
# otherwise outlive 3x its own wait and reap a lock that was never abandoned.
# Nothing this gate does legitimately exceeds half an hour, so half an hour is
# the earliest anything may be presumed dead.
STALE_FLOOR=1800
if [ -z "$STALE_AFTER" ]; then
  STALE_AFTER=$(( LOCK_TIMEOUT * 3 ))
  [ "$STALE_AFTER" -lt "$STALE_FLOOR" ] && STALE_AFTER="$STALE_FLOOR"
fi

CONFIG_JSON=$(cat "$CONFIG")
printf '%s\n' "$CONFIG_JSON" | python3 "$HERE/super-board-verification-ready.py" --config -
BASE=$(echo "$CONFIG_JSON" | jq -r '.base_branch // "main"')
REPO=$(echo "$CONFIG_JSON" | jq -r '.repo.remote // ""' | sed -E 's#^https?://github\.com/##; s#\.git$##')
REPO_PATH=$(echo "$CONFIG_JSON" | jq -r '.repo.path // "."')
export SB_REPO_PATH="$REPO_PATH"
# Verify commands may read the card's QA report by PR number.
export SB_PR="$PR"
# Read with a while-loop rather than `mapfile`: macOS ships bash 3.2 and every
# other script in this repo runs there, so this one does too.
VERIFY=()
while IFS= read -r line; do
  if [[ "$line" =~ [^[:space:]] ]]; then VERIFY+=("$line"); fi
done < <(echo "$CONFIG_JSON" | jq -r '.verify_commands[] | select(test("\\S"))')

# Defend the shell boundary too: extraction must leave a command to execute.
if [ "${#VERIFY[@]}" -eq 0 ]; then
  echo "verification-readiness: verify_commands yielded no usable shell commands; repair the project config and restart the board." >&2
  exit 9
fi
python3 "$GITHUB_READ" --check

LOCK_DIR="${REPO_PATH}/.claude/super-board/inflight/merge.lock"
mkdir -p "$(dirname "$LOCK_DIR")"

# Bounded retention for the verified-tree cache's logs: one per uncached run, and
# nothing removed them before. Before the lock, so a held lock means another gate
# is verifying and every log stays. Pruning is tidying, never the merge's proof.
python3 "$HERE/super-board-prune-verify-logs.py" --root "$REPO_PATH" >&2 \
  || echo "[merge-gate #${PR}] could not prune verify logs (not fatal)" >&2

say() { echo "[merge-gate #${PR}] $*" >&2; }

# ---- the mutex -------------------------------------------------------------
# mkdir is atomic: it succeeds for exactly one caller and fails for the rest.
# The pid/date inside is for a human reading a stuck lock, never for logic.
acquire() {
  local waited=0
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    # A lock older than the timeout belongs to a process that died holding it.
    # Reaping it is safe because the only thing it guards is a merge, and a dead
    # merge has already either landed or not.
    if [ -f "$LOCK_DIR/at" ]; then
      local age=$(( $(date +%s) - $(cat "$LOCK_DIR/at" 2>/dev/null || echo 0) ))
      if [ "$age" -gt "$STALE_AFTER" ]; then
        say "reaping a lock abandoned ${age}s ago (stale-after ${STALE_AFTER}s) by pid $(cat "$LOCK_DIR/pid" 2>/dev/null || echo '?')"
        rm -rf "$LOCK_DIR"; continue
      fi
    fi
    [ "$waited" -ge "$LOCK_TIMEOUT" ] && return 1
    sleep 5; waited=$(( waited + 5 ))
  done
  date +%s > "$LOCK_DIR/at"; echo "$$" > "$LOCK_DIR/pid"; echo "$PR" > "$LOCK_DIR/pr"
  return 0
}
release() { rm -rf "$LOCK_DIR"; }

acquire || { say "could not take the merge lock within ${LOCK_TIMEOUT}s"; exit 4; }
trap release EXIT

say "lock taken; verifying against ${BASE} as it is now"

# ---- the freshness check ---------------------------------------------------
# Done in a throwaway worktree so the branch under test is never mutated: the
# gate proves a merge, it does not perform one locally and it never pushes.
SCRATCH=$(mktemp -d)
cleanup() { git -C "$REPO_PATH" worktree remove --force "$SCRATCH" 2>/dev/null || true; rm -rf "$SCRATCH" "${META:-}" "${DIFF:-}"; release; }
trap cleanup EXIT

# ---- the head guard --------------------------------------------------------
# Review evidence belongs to one commit. If the branch moved after the Reviewer
# passed it, the tests it reran and the diff it read describe something else.
pr_head() { python3 "$GITHUB_READ" --kind head -- pr view "$PR" ${REPO:+--repo "$REPO"} --json headRefName,headRefOid \
              -q '.headRefName + " " + .headRefOid'; }
HEAD=$(pr_head) || exit $?
read -r HEAD_REF HEAD_SHA <<<"$HEAD"
[ -n "${HEAD_SHA:-}" ] || { say "could not read the PR head from GitHub"; exit 1; }
pr_state() { python3 "$GITHUB_READ" --kind merge-state -- pr view "$PR" ${REPO:+--repo "$REPO"} --json state,mergeCommit,headRefOid; }
STATE=$(pr_state) || exit $?
if [ "$(echo "$STATE" | jq -r .state)" = MERGED ]; then
  say "already merged; no verification, migration, or merge is repeated"
  exit 0
fi
[ "$(echo "$STATE" | jq -r .state)" = OPEN ] || { say "PR is closed; refusing merge"; exit 3; }
if [ -n "$EXPECT_HEAD" ]; then
  case "$HEAD_SHA" in
    "$EXPECT_HEAD"*) : ;;
    *) say "head moved: reviewed ${EXPECT_HEAD}, PR head is now ${HEAD_SHA}"
       say "the review evidence is void — send the card back to Review"
       exit 6 ;;
  esac
else
  say "WARNING: no --expect-head; pinning the head read now (${HEAD_SHA}), not the reviewed one"
fi

# ---- merge policy + migration plan ----------------------------------------
# One read of the PR's labels, paths, size and body plus its diff, classified by
# super-board-merge-policy.py (beside this script). Unreadable → human: a policy
# the gate cannot evaluate must not default to "merge".
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Outside $SCRATCH: `git worktree add` below needs that directory empty.
META=$(mktemp); DIFF=$(mktemp)
python3 "$GITHUB_READ" --kind metadata -- pr view "$PR" ${REPO:+--repo "$REPO"} --json labels,files,additions,deletions,changedFiles,body > "$META"
python3 "$GITHUB_READ" --kind diff --meta "$META" -- pr diff "$PR" ${REPO:+--repo "$REPO"} > "$DIFF"
PLAN=$(python3 "$HERE/super-board-merge-policy.py" --config "$CONFIG" --meta "$META" --diff "$DIFF") || {
  echo "human-gate: policy — could not classify the PR (unreadable metadata)"
  say "merge policy could not be evaluated — a human merges this one"; exit 7; }

# The label is display-only. A request posted before `done` pins the exact head
# and the required human steps/migrations. Policy holds stay out of the scope: their
# evidence comes from the merge diff, so an `origin/main` move would re-request a
# `done` that still holds. Re-read trusted approval evidence; never mint it here.
APPROVED=false
approval_check() {
  APPROVAL=$(python3 "$HERE/super-board-approval.py" --repo "$REPO" --pr "$PR" \
    --head "$HEAD_SHA" --plan "$PLAN") || APPROVAL='{"approved":false}'
  python3 "$GITHUB_READ" --check || exit $?
  APPROVED=$(echo "$APPROVAL" | jq -r '.approved // false')
}
approval_request() {
  python3 "$HERE/super-board-approval.py" --request --repo "$REPO" --pr "$PR" \
    --head "$HEAD_SHA" --plan "$PLAN"
}
HUMAN=$(echo "$PLAN" | jq -r '.human[] | "human-gate: \(.category) — \(.why)"')
if [ -n "$HUMAN" ] || [ "$(echo "$PLAN" | jq '.needs_you | length')" -gt 0 ]; then
  approval_check
fi
if [ -n "$HUMAN" ] && [ "$APPROVED" != true ]; then
  echo "$HUMAN"
  echo "$PLAN" | jq -r '.needs_you[] | "needs-you: " + .'
  approval_request
  say "merge policy: waiting for a trusted human to approve this exact head"; exit 7
fi

# A `Closes #N` is a delivery claim, and ticking belongs to each AC's own evidence.
# Refuse while the named issue still has open boxes: bulk-ticking at merge hides a gap.
open_claim=""
for issue in $(jq -r '.body // ""' "$META" \
    | grep -oiE '^[[:space:]]*(closes|fixes|resolves)[[:space:]]+#[0-9]+' \
    | grep -oE '[0-9]+' | sort -u || true); do
  boxes=$(gh issue view "$issue" ${REPO:+--repo "$REPO"} --json body --jq .body 2>/dev/null \
    | grep '^- \[ \]' || true)
  [ -z "$boxes" ] || open_claim="$open_claim #$issue"
done
if [ -n "$open_claim" ]; then
  say "acceptance boxes still open:$open_claim — tick each as its evidence lands, or drop the Closes line"
  exit 11
fi

git -C "$REPO_PATH" fetch origin "$HEAD_REF" "$BASE" --quiet

# This gate runs the main checkout's copy, not the merged one. A checkout that is
# behind silently runs old board code (a merged acceptance tick never fired), so
# refuse instead of merging with stale tooling.
if ! git -C "$REPO_PATH" diff --quiet "origin/${BASE}" -- .agents/bin; then
  say "board tooling is stale: fast-forward ${REPO_PATH} to origin/${BASE} before merging"
  exit 10
fi

git -C "$REPO_PATH" worktree add --detach "$SCRATCH" "$HEAD_SHA" --quiet 2>/dev/null || {
  say "could not create a scratch worktree for ${HEAD_REF}@${HEAD_SHA}"; exit 5; }

if ! git -C "$SCRATCH" merge "origin/${BASE}" --no-edit --quiet 2>/dev/null; then
  CONFLICTS=$(git -C "$SCRATCH" diff --name-only --diff-filter=U | tr '\n' ' ')
  say "the base does not merge in cleanly — conflicts: ${CONFLICTS}"
  say "this is a rebase pass for the Builder lane, not a Blocked card"
  exit 5
fi

# venvs/ is usually git-ignored, so the scratch worktree has no interpreter and a
# relative `venvs/...` verify command exits 127. Link the main checkout's venvs/
# only, and only when it exists.
if [ -d "${REPO_PATH}/venvs" ] && [ ! -e "${SCRATCH}/venvs" ]; then
  ln -s "${REPO_PATH}/venvs" "${SCRATCH}/venvs"
fi

# ---- the verified-tree cache ------------------------------------------------
# The proof below is a function of three things: the base commit merged in, the
# exact tree left in the scratch worktree, and the commands that proved it (plus
# the `scripts/verify.sh` those commands usually run, so editing the suite
# invalidates without touching the command list). Hash them together, print the
# key, and reuse a recorded green only when every part still matches.
sha256_of_stdin() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum; else shasum -a 256; fi | cut -d' ' -f1
}
BASE_SHA=$(git -C "$REPO_PATH" rev-parse "origin/${BASE}")
TREE=$(git -C "$SCRATCH" rev-parse 'HEAD^{tree}')
COMMANDS_HASH=$(
  {
    printf '%s\n' "${VERIFY[@]}"
    if [ -f "$SCRATCH/scripts/verify.sh" ]; then cat "$SCRATCH/scripts/verify.sh"; fi
  } | sha256_of_stdin
)
# A cached green proves the QA report's own selection, so the selection is part of
# the key: the newest `[qa] [report]` comments on this PR, as written. A changed,
# missing, failing or unreadable report hashes differently from any recorded green,
# so the gate re-runs the selection on the same tree. Two PRs naming the same
# selection on the same tree still share an entry, which is what the cache is for.
# Raw `gh` because a missing report is a cache miss, never a run halt.
QA_SELECTION=$(
  gh api "repos/${REPO}/issues/${PR}/comments" --paginate --slurp 2>/dev/null \
    | jq -c '[.[][] | select(.body | contains("[qa] [report]")) | .body]' 2>/dev/null
) || QA_SELECTION="<unreadable qa report>"
QA_SELECTION=${QA_SELECTION:-"<no qa report>"}
SELECTION_HASH=$(printf '%s\n' "$QA_SELECTION" | sha256_of_stdin)
CACHE_KEY=$(printf 'base:%s\ntree:%s\ncommands:%s\nselection:%s\n' \
  "$BASE_SHA" "$TREE" "$COMMANDS_HASH" "$SELECTION_HASH" | sha256_of_stdin)
CACHE_DIR="${REPO_PATH}/.claude/super-board/inflight/verify-cache"
CACHE_FILE="${CACHE_DIR}/${CACHE_KEY}.json"
say "verify-cache key: ${CACHE_KEY}"
say "verify-cache base ${BASE_SHA} tree ${TREE} selection ${SELECTION_HASH}"

CACHED_PR=""; CACHED_AT=""; CACHED_HEAD=""
if [ -f "$CACHE_FILE" ]; then
  ENTRY=$(jq -r '[.status, (.pr // "" | tostring), (.at // 0 | tostring), (.head // "")] | @tsv' \
    "$CACHE_FILE" 2>/dev/null || true)
  IFS=$'\t' read -r E_STATUS E_PR E_AT E_HEAD <<<"$ENTRY"
  # Only the gate writes this entry, but a hand-edited `at` must not abort the
  # run under `set -u`: an age that is not a number is not evidence.
  case "${E_AT:-0}" in
    ''|*[!0-9]*)
      say "verify-cache entry has no usable age; ignoring it"
      E_STATUS=""; E_AT=0 ;;
  esac
  E_AT=${E_AT:-0}
  E_AGE=$(( $(date +%s) - E_AT ))
  if [ "${E_STATUS:-}" != green ]; then
    say "verify-cache entry is not a recorded pass; ignoring it"
  elif [ "$E_AGE" -ge "$CACHE_TTL" ]; then
    say "verify-cache stale: recorded ${E_AGE}s ago, ttl ${CACHE_TTL}s; re-running"
    rm -f "$CACHE_FILE"
  else
    CACHED_PR="$E_PR"; CACHED_HEAD="$E_HEAD"
    CACHED_AT=$(date -u -r "${E_AT:-0}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
      || date -u -d "@${E_AT:-0}" +%Y-%m-%dT%H:%M:%SZ)
  fi
fi

if [ -n "$CACHED_PR" ]; then
  say "verify: cached from #${CACHED_PR} at ${CACHED_AT} (key ${CACHE_KEY}, head ${CACHED_HEAD})"
else
  # The log lives outside $SCRATCH so cleanup cannot drop the output that proved
  # this tree green. It names the command, the head and the selection.
  LOG_DIR="${REPO_PATH}/.claude/super-board/inflight/verify-logs"
  mkdir -p "$LOG_DIR"
  VERIFY_LOG="${LOG_DIR}/${CACHE_KEY}.log"
  printf 'head: %s\nbase: %s\npr: %s\nselection: %s\n' \
    "$HEAD_SHA" "$BASE_SHA" "$PR" "$SELECTION_HASH" > "$VERIFY_LOG"
  for cmd in "${VERIFY[@]}"; do
    say "verify: ${cmd}"
    printf '\n$ %s\n' "$cmd" >> "$VERIFY_LOG"
    if ! ( cd "$SCRATCH" && eval "$cmd" ) >>"$VERIFY_LOG" 2>&1; then
      say "FAILED: ${cmd}"
      tail -30 "$VERIFY_LOG" >&2
      say "the branch is stale against ${BASE} - send it back to Build for a rebase pass"
      exit 2
    fi
  done
  say "verified green against ${BASE} (${#VERIFY[@]} command(s); log ${VERIFY_LOG})"
  # Recorded only after every command passed, so a red run can never be replayed
  # as green. A dry run proves nothing about a merge, so it records nothing.
  if [ "$DRY" -eq 0 ]; then
    mkdir -p "$CACHE_DIR"
    jq -cn --arg base "$BASE_SHA" --arg tree "$TREE" --arg commands "$COMMANDS_HASH" \
        --arg key "$CACHE_KEY" --arg head "$HEAD_SHA" --argjson pr "$PR" \
        --argjson at "$(date +%s)" \
        '{status:"green",base:$base,tree:$tree,commands:$commands,key:$key,pr:$pr,head:$head,at:$at}' \
      > "$CACHE_FILE.tmp" 2>/dev/null && mv "$CACHE_FILE.tmp" "$CACHE_FILE" \
      || say "could not record the verify cache (not fatal; the suite still ran)"
  fi
fi

python3 "$GITHUB_READ" --check

# ---- migrations (inside the lock, after the build proof) -------------------
# Run the configured migrate command for every allowed env, from the verified
# scratch tree. Collect, never stop early, so a human gets every command at once.
NEEDS=()
while IFS= read -r line; do [ -n "$line" ] && NEEDS+=("$line"); done \
  < <(echo "$PLAN" | jq -r '.needs_you[]')
if [ "$(echo "$PLAN" | jq '.migrations | length')" -gt 0 ]; then
  say "migrations in this PR: $(echo "$PLAN" | jq -r '.migrations | join(" ")')"
  while IFS=$'\t' read -r env cmd; do
    [ -n "$env" ] || continue
    if [ "$DRY" -eq 1 ]; then say "dry run: would migrate ${env}: ${cmd}"; continue; fi
    say "migrate ${env}: ${cmd}"
    python3 "$GITHUB_READ" --check
    if ! ( cd "$SCRATCH" && eval "$cmd" ) >"$SCRATCH/.migrate.log" 2>&1; then
      say "FAILED: migrate ${env}"; tail -20 "$SCRATCH/.migrate.log" >&2
      NEEDS+=("${cmd}   # ${env}: failed in the merge gate — fix, run it, then mark done")
    fi
  done < <(echo "$PLAN" | jq -r '.run[] | [.env, .cmd] | @tsv')
fi
if [ "${#NEEDS[@]}" -gt 0 ]; then
  if [ "$APPROVED" = true ] && [ "$(echo "$PLAN" | jq '.needs_you | length')" -eq "${#NEEDS[@]}" ]; then
    say "a trusted human confirmed the current head and human steps"
  else
    for n in "${NEEDS[@]}"; do echo "needs-you: $n"; done
    approval_request
    say "🙋 needs you before this merges — card → Blocked with the commands above"
    exit 8
  fi
fi

# An approval can be superseded while verification/migrations run. Re-read just
# before merging; GitHub independently pins the code with --match-head-commit.
if [ "$APPROVED" = true ]; then
  # Code remains pinned; body-declared human steps and config can change without
  # a commit. Reclassify them too instead of reusing the old approval scope.
  python3 "$GITHUB_READ" --kind metadata -- pr view "$PR" ${REPO:+--repo "$REPO"} --json labels,files,additions,deletions,changedFiles,body > "$META"
  PLAN=$(python3 "$HERE/super-board-merge-policy.py" --config "$CONFIG" --meta "$META" --diff "$DIFF") || {
    say "human approval scope could not be refreshed"; exit 7; }
  approval_check
  if [ "$APPROVED" != true ]; then
    approval_request
    say "human approval changed during verification; keep the card Blocked"
    if [ -n "$HUMAN" ]; then exit 7; else exit 8; fi
  fi
fi

# ---- the merge -------------------------------------------------------------
if [ "$DRY" -eq 1 ]; then
  say "dry run: would squash-merge PR #${PR}"
  exit 0
fi

# --match-head-commit makes GitHub refuse if anything was pushed after HEAD_SHA,
# including during the verification run above.
python3 "$GITHUB_READ" --check
if gh pr merge "$PR" ${REPO:+--repo "$REPO"} --squash --delete-branch \
     ${SUBJECT:+--subject "$SUBJECT"} ${MSG_FILE:+--body-file "$MSG_FILE"} \
     --match-head-commit "$HEAD_SHA" 2>&1 | tail -3 >&2; then
  say "merged ${HEAD_SHA}"
  # GitHub closes the `Closes #N` issue itself; every box was ticked by its evidence
  # before this gate let the merge through.
  # Post-merge tidy-up: drop worktrees and local branches the merge just made
  # redundant. Optional (only when the cleanup-wt hook is installed), local-only, and it
  # can never fail the merge that already happened.
  if [ -f "$REPO_PATH/.claude/hooks/cleanup-wt.py" ]; then
    ( cd "$REPO_PATH" && python3 .claude/hooks/cleanup-wt.py --post-merge --base "$BASE" </dev/null ) >&2 || true
  fi
  exit 0
fi
STATE=$(pr_state) || exit $?
if [ "$(echo "$STATE" | jq -r .state)" = MERGED ]; then
  say "merge response was lost; GitHub confirms the merge commit"
  exit 0
fi
NOW_SHA=$(echo "$STATE" | jq -r .headRefOid)
if [ "$NOW_SHA" != "$HEAD_SHA" ]; then
  say "head moved during the gate: verified ${HEAD_SHA}, PR head is now ${NOW_SHA}"
  say "the review evidence is void — send the card back to Review"
  exit 6
fi
python3 "$GITHUB_READ" --halt "Merge response failed and GitHub has not confirmed a merge; reconcile PR #${PR} before restarting. No merge was retried."

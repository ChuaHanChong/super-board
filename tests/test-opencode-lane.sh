#!/usr/bin/env bash
# Stubbed OpenCode only: lane consent, model precedence, the OS write jail, result
# extraction, and wave routing. No network, no real model.
set -euo pipefail
KIT=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/repo" "$T/home" "$T/state"
git init -q "$T/repo"
python3 "$KIT/tests/fixtures/install_worker_skills.py" "$T/repo"
export SUPER_BOARD_SKILLS_HOME="$T/home"
cat > "$T/bin/gh" <<'PYGH'
#!/usr/bin/env python3
import json,sys
args=sys.argv[1:]
if args[:2]==['issue','view']:
    print(json.dumps({'labels':[]} if args[args.index('--json')+1] == 'labels' else {'number':int(args[2]),'title':'fixture','body':''}))
else:
    sys.exit('unexpected gh fixture call: '+str(args))
PYGH
cat > "$T/bin/opencode" < "$KIT/tests/fixtures/fake_opencode.py"
chmod +x "$T/bin/gh" "$T/bin/opencode"
export SB_OPENCODE_TEST_LOG="$T/calls.jsonl"
export SB_OPENCODE_TEST_STATE="$T/state"
export PATH="$T/bin:$PATH"
cd "$T/repo"
echo '{"verify_commands":["git diff --check"]}' > "$T/config.json"
CARD='{"number":1,"status":"Ready","title":"example"}'
lane() { bash "$KIT/scripts/super-board-lane.sh" --backend opencode --config "$T/config.json" --card "$CARD" --lane "$@" 2>"$T/stderr"; }
wave() { bash "$KIT/scripts/super-board-codex-wave.sh" --config "$T/config.json" --cards "$CARDS" "$@" 2>"$T/stderr"; }
fail() { echo "FAIL: $*" >&2; cat "$T/stderr" >&2; exit 1; }

# A backend flag is required, and claude is not a lane backend.
for args in "--backend claude" "--backend gemini"; do
  RC=0; bash "$KIT/scripts/super-board-lane.sh" $args --config x --card '{}' --lane build >/dev/null 2>"$T/stderr" || RC=$?
  [ "$RC" -eq 64 ] && grep -q 'valid backends: codex, opencode' "$T/stderr" || fail "'$args' must exit 64 naming both backends"
done
# The wave requires exactly one explicit backend flag.
for args in "" "--codex --opencode" "--opencode="; do
  RC=0; bash "$KIT/scripts/super-board-codex-wave.sh" --config "$T/config.json" --cards '[]' $args >/dev/null 2>"$T/stderr" || RC=$?
  [ "$RC" -eq 2 ] || fail "wave '$args' must be refused (rc=$RC)"
done

# Review needs the same explicit consent as Codex; usage fallback still needs config opt-in.
RC=0; lane review >"$T/out" || RC=$?
[ "$RC" -eq 78 ] && [ ! -e "$SB_OPENCODE_TEST_LOG" ] || fail 'fallback review must refuse before OpenCode'
RC=0; lane build >"$T/out" || RC=$?
[ "$RC" -eq 78 ] || fail 'fallback build needs usage_fallback "opencode"'

lane review --opencode >"$T/out"
jq -e '.status == "advanced" and .column == "Done"' "$T/out" >/dev/null || fail 'explicit review allowed'
tail -1 "$SB_OPENCODE_TEST_LOG" | jq -e '.gitnexus_home | test("super-board-opencode-.*/gitnexus$")' >/dev/null || fail 'lane needs a private GITNEXUS_HOME'
python3 - "$SB_OPENCODE_TEST_LOG" <<'PY' || fail 'lane argv keeps the headless jail contract'
import json, pathlib, sys
call = json.loads(pathlib.Path(sys.argv[1]).read_text().splitlines()[-1])
args = call['args']
assert args[:4] == ['run', '--format', 'json', '--standalone'], args
assert '--auto' in args, args
PY
grep -q 'Never run bare gh pr merge' "$SB_OPENCODE_TEST_LOG" || fail 'review must keep merge protocol'

args_of_last() { tail -1 "$SB_OPENCODE_TEST_LOG" | jq -r '.args | if index("--model") then .[index("--model")+1] else "default" end'; }
lane build --opencode=flag-model >"$T/out"
[ "$(args_of_last)" = flag-model ] || fail 'flag model must reach --model'
echo '{"opencode":{"model":"config-model"},"verify_commands":["git diff --check"]}' > "$T/config.json"
lane build --opencode >"$T/out"
[ "$(args_of_last)" = config-model ] || fail 'opencode.model must reach --model'
lane build --opencode=flag-model >"$T/out"
[ "$(args_of_last)" = flag-model ] || fail 'flag must beat config'

# The jail is the boundary: a lane cannot write outside its grants, and its own state still works.
echo '{"verify_commands":["git diff --check"]}' > "$T/config.json"
ESCAPE=$([ "$(uname -s)" = Darwin ] && echo /private/tmp || echo /var/tmp)/sb-lane-escape-$$
trap 'rm -rf "$T" "$ESCAPE"' EXIT
RC=0; SB_OPENCODE_TEST_ESCAPE="$ESCAPE" lane build --opencode >"$T/out" || RC=$?
[ "$RC" -eq 0 ] && jq -e '.status == "advanced"' "$T/out" >/dev/null || fail 'jailed lane must still advance'
[ ! -e "$ESCAPE" ] || fail 'lane wrote outside its grants'
[ "$(cat "$SB_OPENCODE_TEST_LOG.escape" 2>/dev/null)" = blocked ] || fail 'the write outside the jail must be refused'
rm -f "$SB_OPENCODE_TEST_LOG.escape"

# The generated profile itself: canonical paths, repo granted, home and the rest denied.
if [ "$(uname -s)" = Darwin ]; then
  SB_OPENCODE_TEST_PROFILE="$T/profile.sb" lane build --opencode >"$T/out"
  python3 - "$T/profile.sb" "$T/repo" "$HOME" <<'PY' || fail 'generated Seatbelt profile is wrong'
import pathlib, sys
profile, repo, home = pathlib.Path(sys.argv[1]).read_text(), str(pathlib.Path(sys.argv[2]).resolve()), str(pathlib.Path(sys.argv[3]).resolve())
assert '(deny file-write*)' in profile and '(allow default)' in profile, profile
assert f'(subpath "{repo}")' in profile, 'the repo must be writable'
assert f'(subpath "{home}")' not in profile, 'the home directory must not be writable'
assert '(subpath "/private/' in profile or '(subpath "/Users/' in profile, 'paths must be canonical'
assert '(literal "/dev/null")' in profile, 'git and every shell need /dev/null inside the jail'
PY
  # The jail must not break the tools a lane lives on: git writes .git and opens /dev/null.
  /usr/bin/sandbox-exec -f "$T/profile.sb" git -C "$T/repo" -c user.email=a@b -c user.name=a commit -qm jail --allow-empty \
    || fail 'git must work inside the jail'
  /usr/bin/sandbox-exec -f "$T/profile.sb" git -C "$T/repo" worktree add -q .claude/worktrees/jail -b jail-check \
    || fail 'git worktree must work inside the jail'
else
  command -v bwrap >/dev/null || fail 'the Linux lane needs bubblewrap'
fi

# Result extraction: prose before the JSON is tolerated, a reply without JSON fails.
RC=0; SB_OPENCODE_TEST_INVALID=1 lane build --opencode >"$T/out" || RC=$?
[ "$RC" -eq 1 ] && jq -e '.status == "failed"' "$T/out" >/dev/null || fail 'a reply without JSON fails the lane'
RC=0; SB_OPENCODE_TEST_EXIT=2 lane build --opencode >"$T/out" || RC=$?
[ "$RC" -eq 1 ] && jq -e '.status == "failed"' "$T/out" >/dev/null || fail 'a nonzero exit never trusts success JSON'

# Wave: OpenCode has no ladder, so nothing is graded and the marker is per backend.
echo '{"max_workers":1,"verify_commands":["git diff --check"]}' > "$T/config.json"
CARDS='[{"number":1,"status":"Ready"},{"number":2,"status":"Review"}]'
: > "$SB_OPENCODE_TEST_LOG"
wave --opencode=wave-model --output "$T/wave.json" >"$T/out"
cmp "$T/out" "$T/wave.json" || fail 'file and stdout wave result differ'
jq -e '.halted == false and .cards[0].lanesRun == "build:advanced → qa:advanced → review:advanced" and .cards[1].column == "Done"' "$T/out" >/dev/null || fail 'wave routing/summary'
jq -s -e 'all(.lane != "grade")' "$SB_OPENCODE_TEST_LOG" >/dev/null || fail 'OpenCode has no ladder, so the wave must not grade'
jq -s -e 'all(.args | index("--model")) and all(.args | .[. | index("--model") + 1] == "wave-model")' "$SB_OPENCODE_TEST_LOG" >/dev/null || fail 'wave propagates the pinned model'
[ ! -e .claude/super-board/opencode-wave.pid ] && [ -z "$(ls -A .claude/super-board/inflight)" ] || fail 'completed wave leaves no PID/worker locks'
echo "PASS: test-opencode-lane.sh (consent/model/jail/result/wave)"

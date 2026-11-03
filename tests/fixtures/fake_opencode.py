#!/usr/bin/env python3
# Stubbed `opencode` for the offline OpenCode lane/wave suite; behaviour set by SB_OPENCODE_TEST_*.
import fcntl, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
args = sys.argv[1:]
if args[:2] == ['debug', 'paths']:
    base = Path(os.environ['SB_OPENCODE_TEST_STATE'])
    print(f'{"home":<10} {Path.home()}')
    for name in ('data', 'cache', 'config', 'state', 'tmp', 'log', 'bin', 'db'):
        print(f'{name:<10} {base / name}')
    sys.exit(0)
prompt = args[-1]
if os.environ.get('SB_OPENCODE_TEST_PROFILE'):
    # The lane writes the Seatbelt profile beside its own temp dir; copy it out for assertions.
    for path in Path(tempfile.gettempdir()).glob('super-board-opencode-*/write.sb'):
        Path(os.environ['SB_OPENCODE_TEST_PROFILE']).write_text(path.read_text())
        break
if os.environ.get('SB_OPENCODE_TEST_ESCAPE'):
    try:
        Path(os.environ['SB_OPENCODE_TEST_ESCAPE']).write_text('escaped')
    except OSError:
        outcome = 'blocked'
    else:
        outcome = 'escaped'
    with open(os.environ['SB_OPENCODE_TEST_LOG'] + '.escape', 'w') as log:
        log.write(outcome)
card = json.loads(re.search(r'^Card: (.+)$', prompt, re.M).group(1))
lane = re.search(r'Run super-(build|qa|review)', prompt).group(1)
with open(os.environ['SB_OPENCODE_TEST_LOG'], 'a') as log:
    fcntl.flock(log, fcntl.LOCK_EX)
    counter = Path(os.environ['SB_OPENCODE_TEST_LOG'] + '.active')
    active = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(active))
    log.write(json.dumps(dict(args=args[:-1], prompt=prompt, number=card['number'], lane=lane, active=active, gitnexus_home=os.environ.get('GITNEXUS_HOME'))) + '\n')
if os.environ.get('SB_OPENCODE_TEST_SLEEP'):
    descendant = subprocess.Popen(['sleep', '60'])
    Path(os.environ['SB_OPENCODE_TEST_PID']).write_text(str(descendant.pid))
    time.sleep(60)
time.sleep(float(os.environ.get('SB_OPENCODE_TEST_DELAY', '0')))
status = os.environ.get('SB_OPENCODE_TEST_STATUS', 'advanced')
column = {'build': 'QA', 'qa': 'Review', 'review': 'Done'}[lane] if status == 'advanced' else card['status']
if os.environ.get('SB_OPENCODE_TEST_INVALID'):
    text = 'no json here'
elif os.environ.get('SB_OPENCODE_TEST_RESULT'):
    text = os.environ['SB_OPENCODE_TEST_RESULT']
else:
    text = json.dumps(dict(status=status, column=column, detail=os.environ.get('SB_OPENCODE_TEST_DETAIL', 'stub lane result'),
                           prUrl=None, branch=None, priorFindings=None))
# Prose before the JSON, then an older text event: the launcher must take the last one.
event = {'type': 'text', 'part': {'type': 'text', 'text': 'Narrating the work.\n\n' + text}}
print(json.dumps({'type': 'step_start', 'part': {'type': 'step-start'}}))
print(json.dumps(event))
print(json.dumps({'type': 'step_finish', 'part': {'type': 'step-finish', 'reason': 'stop'}}))
with open(os.environ['SB_OPENCODE_TEST_LOG'], 'a') as log:
    fcntl.flock(log, fcntl.LOCK_EX)
    counter.write_text(str(int(counter.read_text()) - 1))
sys.exit(int(os.environ.get('SB_OPENCODE_TEST_EXIT', '0')))

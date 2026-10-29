#!/usr/bin/env python3
"""Exercise the installed capability boundary with isolated external commands."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / 'scripts/super-board-paper2code.py'
CONTROLLER = '''"""Record an independent external controller contract fixture."""
import argparse,hashlib,json,os,pathlib,signal,sys
parser=argparse.ArgumentParser()
parser.add_argument('--backend',required=True)
parser.add_argument('--timeout',required=True)
parser.add_argument('--paper_format',required=True)
parser.add_argument('--paper_name',required=True)
parser.add_argument('--input',required=True)
parser.add_argument('--output_dir',required=True)
parser.add_argument('--output_repo_dir',required=True)
parser.add_argument('--stage',required=True)
parser.add_argument('--model')
args,extra=parser.parse_known_args()
if any(os.environ.get(k) for k in ('OPENAI_API_KEY','ANTHROPIC_API_KEY')):
    raise SystemExit(9)
artifacts=pathlib.Path(args.output_dir)
candidate=pathlib.Path(args.output_repo_dir)
artifacts.mkdir(parents=True,exist_ok=True)
if os.environ.get('CONTROLLER_WAIT'):
    print('fixture-controller-ready',file=sys.stderr,flush=True)
    signal.pause()
status='failed' if os.environ.get('CONTROLLER_FAIL') else 'completed'
if status=='completed':
    candidate.mkdir(exist_ok=True)
    (candidate/'model.py').write_text('def transform(x):\\n    return 2*x+1\\n')
    (candidate/'reproduce.sh').write_text('touch MUST_NOT_EXECUTE\\n')
    (candidate/'config.yaml').write_text('scale: 2\\nbias: 1\\n')
    (artifacts/'task_list.json').write_text(json.dumps({'Task list':['config.yaml','model.py']}))
result={'status':status,'stage':'reproduction','backend':args.backend,'model':args.model,
        'paper2code_revision':'b'*40,'cli_version':'fixture-agent 1.0',
        'input_sha256':hashlib.sha256(pathlib.Path(args.input).read_bytes()).hexdigest(),
        'output_dir':str(artifacts),'project_dir':str(candidate),
        'completed_stages':['planning.overview','planning.architecture','planning.tasks','planning.config','analysis:model.py','coding:model.py','reproduction'],'error':'controlled failure' if status=='failed' else None}
bad=os.environ.get('CONTROLLER_BAD')
if bad=='paths': result['project_dir']=str(candidate.parent/'wrong')
if bad=='input': result['input_sha256']='0'*64
if bad=='stages': result['completed_stages']=[]
if bad=='empty-candidate':
    for path in candidate.iterdir(): path.unlink()
if bad=='missing-file': (candidate/'model.py').unlink()
alias=os.environ.get('CONTROLLER_ALIAS')
if alias:
    (candidate/alias).write_text('noncanonical alias content\\n')
    names=['model.py',alias] if alias.casefold()=='config.yaml' else ['config.yaml','model.py',alias]
    (artifacts/'task_list.json').write_text(json.dumps({'Task list':names}))
    result['completed_stages']+=['analysis:'+alias,'coding:'+alias]
(artifacts/'run.json').write_text(json.dumps(result if bad!='manifest' else dict(result,status='failed')))
(artifacts/'controller-arguments.json').write_text(json.dumps(vars(args)|{'extra':extra}))
print(json.dumps(result) if not os.environ.get('CONTROLLER_MALFORMED') else 'not-json')
raise SystemExit(1 if status=='failed' or os.environ.get('CONTROLLER_EXIT') else 0)
'''


class Paper2Code(unittest.TestCase):
    """Observe readiness and generation through the public installed helper."""

    def setUp(self) -> None:
        """Create separate installation and issue-worktree roots."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project'
        self.root = self.project / '.claude/worktrees/issue-7-build'
        self.root.mkdir(parents=True)
        self.helper = self.project / '.agents/bin/super-board-paper2code.py'
        self.helper.parent.mkdir(parents=True)
        self.runtime = self.project / '.agents/lib/paper2code'
        self.fakebin = self.base / 'bin'
        self.fakebin.mkdir()
        self.env = {**os.environ, 'PATH': str(self.fakebin) + os.pathsep + os.environ['PATH'],
                    'OPENAI_API_KEY': 'must-not-reach-child', 'ANTHROPIC_API_KEY': 'must-not-reach-child'}
        self.paper = self.root / 'paper.json'
        self.paper.write_text('{"title":"Affine","abstract":"y=2*x+1"}')

    def install(self) -> None:
        """Install a public controller fixture and fake runtime interpreter."""
        shutil.copy2(CLI, self.helper)
        (self.runtime / 'codes').mkdir(parents=True)
        (self.runtime / '.venv/bin').mkdir(parents=True)
        interpreter = self.runtime / '.venv/bin/python'
        interpreter.write_text('#!' + sys.executable + '\nimport json,os,sys\n'
                               'if sys.argv[1] == "-c":\n'
                               ' print(json.dumps({"python":[3,13,0],"pyyaml":"6.0.3"}))\n'
                               'else:\n os.execv(sys.executable,[sys.executable,*sys.argv[1:]])\n')
        interpreter.chmod(0o755)
        (self.runtime / 'codes/pipeline.py').write_text('"""External controller fixture."""\n')
        for name in ('cli_runner.py', 'prompts.py', 'auxiliary.py'):
            (self.runtime / 'codes' / name).write_text('"""External fixture module."""\n')
        self.metadata()
        for backend in ('codex', 'claude'):
            binary = self.fakebin / backend
            binary.write_text('#!' + sys.executable + '\nimport os,sys\n'
                              'if any(os.environ.get(k) for k in ("OPENAI_API_KEY","ANTHROPIC_API_KEY")):\n raise SystemExit(9)\n'
                              'raise SystemExit(int(os.environ.get("AUTH_EXIT", "0")))\n')
            binary.chmod(0o755)

    def metadata(self) -> None:
        """Bind the fixture runtime to its recorded installation content."""
        hashes = {str(path.relative_to(self.runtime)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted((self.runtime / 'codes').glob('*.py'))}
        (self.runtime / 'installation.json').write_text(json.dumps({
            'revision': 'a' * 40, 'dirty': True, 'source_sha256': hashes,
            'dependency_versions': {'PyYAML': '6.0.3'}}))

    def invoke(self, *arguments: str, expected: int = 0) -> dict:
        """Invoke the installed public helper and decode its result."""
        result = subprocess.run([sys.executable, str(self.helper), '--root', str(self.root),
                                 '--host', 'codex', *arguments], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def generation(self, *arguments: str, expected: int = 0) -> dict:
        """Generate through the helper's isolated run-directory contract."""
        return self.invoke('--paper', str(self.paper), '--paper-format', 'JSON', '--paper-name', 'Affine',
                           '--timeout', '10', '--output-dir', '.paper2code/first', *arguments, expected=expected)

    def test_readiness_is_installed_and_source_bound(self) -> None:
        """Resolve a runtime from its installation even for a separate worktree."""
        self.install()
        result = self.invoke('--check')
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['paper2code_revision'], 'a' * 40)
        self.assertTrue(result['source_dirty'])
        self.assertEqual(result['authentication'], 'not_checked')
        (self.runtime / 'codes/pipeline.py').write_text('changed')
        result = self.invoke('--check', expected=10)
        self.assertEqual(result['status'], 'halted')
        self.assertIn('changed', result['error'])

    def test_shared_readiness_rejects_an_unsupported_host(self) -> None:
        """Keep the resolver's shared preflight from accepting another available CLI."""
        self.install()
        (self.fakebin / 'opencode').symlink_to(self.fakebin / 'codex')
        spec = importlib.util.spec_from_file_location('paper2code_capability', self.helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaisesRegex(module.CapabilityError, 'codex or claude'):
            module.installed_runtime(self.root, 'opencode')

    def test_generation_delegates_without_executing_or_integrating_candidates(self) -> None:
        """Keep generated files and authoritative provenance in a dedicated run tree."""
        self.install()
        (self.runtime / 'codes/pipeline.py').write_text(CONTROLLER)
        self.metadata()
        sentinel = self.root / 'model.py'
        sentinel.write_text('user implementation')
        result = self.generation('--model', 'explicit-model')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['paper2code_revision'], 'a' * 40)
        self.assertTrue(result['source_dirty'])
        self.assertEqual(sentinel.read_text(), 'user implementation')
        self.assertFalse(list(self.root.rglob('MUST_NOT_EXECUTE')))
        self.assertEqual((self.root / '.paper2code/first/candidate/model.py').read_text(), 'def transform(x):\n    return 2*x+1\n')
        evidence = json.loads(Path(result['evidence_path']).read_text())
        self.assertEqual(evidence, result)
        self.assertEqual(evidence['controller_result']['paper2code_revision'], 'b' * 40)
        self.assertEqual(evidence['model'], 'explicit-model')
        self.assertEqual(evidence['backend'], 'codex')
        arguments = json.loads((self.root / '.paper2code/first/artifacts/controller-arguments.json').read_text())
        self.assertEqual(arguments['stage'], 'all')
        self.assertEqual(arguments['timeout'], '10.0')

    def test_failed_or_malformed_controller_results_never_complete(self) -> None:
        """Reject model failures, malformed results, and contradictory process success."""
        self.install()
        (self.runtime / 'codes/pipeline.py').write_text(CONTROLLER)
        self.metadata()
        for name in ('CONTROLLER_FAIL', 'CONTROLLER_MALFORMED', 'CONTROLLER_EXIT'):
            with self.subTest(failure=name):
                self.env[name] = '1'
                result = self.generation('--output-dir', '.paper2code/' + name, expected=1)
                self.assertEqual(result['status'], 'failed')
                self.assertTrue(result['error'])
                self.assertTrue(Path(result['evidence_path']).is_file())
                self.env.pop(name)

    def test_completion_requires_matching_manifest_and_input_evidence(self) -> None:
        """Reject a successful stdout claim contradicted by saved artifacts."""
        self.install()
        (self.runtime / 'codes/pipeline.py').write_text(CONTROLLER)
        self.metadata()
        for failure in ('manifest', 'paths', 'input', 'stages', 'empty-candidate', 'missing-file'):
            with self.subTest(failure=failure):
                self.env['CONTROLLER_BAD'] = failure
                result = self.generation('--output-dir', '.paper2code/bad-' + failure, expected=1)
                self.assertEqual(result['status'], 'failed')
                self.assertTrue(result['error'])

    def test_completion_rejects_case_aliases_of_controller_owned_files(self) -> None:
        """Reject stale controller evidence that aliases automatic config or reproduction files."""
        self.install()
        (self.runtime / 'codes/pipeline.py').write_text(CONTROLLER)
        self.metadata()
        for index, alias in enumerate(('CONFIG.YAML', 'Config.yaml', 'cOnFiG.yAmL', 'REPRODUCE.SH', 'Reproduce.sh', 'rePRODUCE.sh')):
            with self.subTest(alias=alias):
                self.env['CONTROLLER_ALIAS'] = alias
                result = self.generation('--output-dir', '.paper2code/alias-' + str(index), expected=1)
                self.assertEqual(result['status'], 'failed')
                self.assertIn('canonical spelling', result['error'])

    def test_preflight_preserves_existing_runs_and_rejects_unsafe_paths(self) -> None:
        """Reject unsafe destinations or missing login before controller writes."""
        self.install()
        (self.runtime / 'codes/pipeline.py').write_text(CONTROLLER)
        self.metadata()
        self.generation()
        run = self.root / '.paper2code/first'
        original = {str(path.relative_to(run)): path.read_bytes() for path in run.rglob('*') if path.is_file()}
        self.generation(expected=10)
        self.assertEqual({str(path.relative_to(run)): path.read_bytes() for path in run.rglob('*') if path.is_file()}, original)
        for target in (str(self.base / 'outside'), '.agents/overwrite', '../escape', '.'):
            with self.subTest(target=target):
                self.generation('--output-dir', target, expected=64)
        outside = self.base / 'outside'
        outside.mkdir()
        (self.root / 'linked').symlink_to(outside, target_is_directory=True)
        self.generation('--output-dir', 'linked/new', expected=64)
        self.assertEqual(list(outside.iterdir()), [])
        self.env['AUTH_EXIT'] = '1'
        result = self.generation('--output-dir', '.paper2code/no-auth', expected=10)
        self.assertEqual(result['status'], 'halted')
        self.assertIn('login', result['error'])
        self.assertFalse((self.root / '.paper2code/no-auth').exists())

    def test_interruption_reaches_controller_without_completion(self) -> None:
        """Forward termination and preserve a halted result after the child exits."""
        self.install()
        (self.runtime / 'codes/pipeline.py').write_text(CONTROLLER)
        self.metadata()
        self.env['CONTROLLER_WAIT'] = '1'
        process = subprocess.Popen([sys.executable, str(self.helper), '--root', str(self.root), '--host', 'codex',
                                    '--paper', str(self.paper), '--timeout', '10', '--output-dir', '.paper2code/cancel'],
                                   env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(process.stderr.readline().strip(), 'fixture-controller-ready')
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=10)  # The fixture uses the same explicit 10-second budget as this invocation.
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        self.assertEqual(process.returncode, 1, stderr)
        result = json.loads(stdout)
        self.assertEqual(result['status'], 'halted')
        self.assertEqual(result['exit_code'], -signal.SIGTERM)
        self.assertTrue(Path(result['evidence_path']).is_file())

    def test_preflight_interruption_and_timeout_reap_the_process_group(self) -> None:
        """Reap interrupted runtime probes and timed-out authentication with their descendants."""
        self.install()
        auth = self.fakebin / 'codex'
        auth.write_text('#!' + sys.executable + '\nimport os,pathlib,signal,subprocess,sys\n'
                        'child=subprocess.Popen([sys.executable,"-c","import signal;signal.pause()"] )\n'
                        'pathlib.Path(os.environ["AUTH_PIDS"]).write_text(str(os.getpid())+" "+str(child.pid))\n'
                        'signal.pause()\n')
        auth.chmod(0o755)
        for mode in ('interrupt', 'timeout', 'runtime'):
            with self.subTest(mode=mode):
                pids = self.base / ('auth-' + mode + '.pids')
                self.env['AUTH_PIDS'] = str(pids)
                if mode == 'runtime':
                    shutil.copy2(auth, self.runtime / '.venv/bin/python')
                command = [sys.executable, str(self.helper), '--root', str(self.root), '--host', 'codex']
                command += ['--check'] if mode == 'runtime' else ['--paper', str(self.paper), '--timeout', '1', '--output-dir', '.paper2code/' + mode]
                process = subprocess.Popen(command,
                                           env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                owned = []
                try:
                    deadline = time.monotonic() + 10  # The test supervisor uses the same explicit ten-second invocation budget as other fixtures.
                    while not pids.exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)  # Polling affects observation latency only; the explicit deadline bounds the test.
                    self.assertTrue(pids.exists())
                    owned = [int(value) for value in pids.read_text().split()]
                    if mode != 'timeout':
                        process.send_signal(signal.SIGTERM)
                    stdout, stderr = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 10, stderr)
                    self.assertEqual(json.loads(stdout)['status'], 'halted')
                    for pid in owned:
                        while time.monotonic() < deadline:
                            try:
                                os.kill(pid, 0)
                            except ProcessLookupError:
                                break
                            time.sleep(0.01)  # Allow the OS reaper to retire a terminated orphan within the supervisor budget.
                        with self.assertRaises(ProcessLookupError):
                            os.kill(pid, 0)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
                    for pid in owned:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass

    def test_invalid_inference_options_never_create_outputs(self) -> None:
        """Reject invalid explicit budgets and selectors before external execution."""
        self.install()
        for arguments in (('--timeout', '0'), ('--timeout', '-1'), ('--timeout', 'nan'),
                          ('--timeout', 'inf'), ('--model', ' '), ('--host', 'opencode'),
                          ('--stage', 'evaluation'), ('--generated-n', '0')):
            with self.subTest(arguments=arguments):
                result = self.generation(*arguments, expected=64)
                self.assertEqual(result['status'], 'failed')
                self.assertFalse((self.root / '.paper2code').exists())

    def test_auxiliary_options_reuse_the_run_tree_without_replacing_evidence(self) -> None:
        """Expose retained stages through the same contained controller boundary."""
        self.install()
        (self.runtime / 'codes/pipeline.py').write_text(CONTROLLER)
        self.metadata()
        initial = self.generation()
        original = Path(initial['evidence_path']).read_bytes()
        lookup = self.root / 'lookup.json'
        lookup.write_text('{}')
        result = self.generation('--stage', 'refinement', '--lookup-file', str(lookup))
        self.assertEqual(result['status'], 'completed')
        self.assertNotEqual(result['evidence_path'], initial['evidence_path'])
        self.assertEqual(Path(initial['evidence_path']).read_bytes(), original)
        arguments = json.loads((self.root / '.paper2code/first/artifacts/controller-arguments.json').read_text())
        self.assertEqual(arguments['stage'], 'refinement')
        self.assertEqual(arguments['extra'], ['--lookup_file', str(lookup)])


if __name__ == '__main__':
    unittest.main()

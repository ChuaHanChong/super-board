#!/usr/bin/env python3
"""Generate Paper2Code candidates inside an existing issue worktree."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from typing import Any
import uuid

PROVIDER_CREDENTIALS = {'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN'}
CONTROL_NAMES = {'.git', '.gitmodules', '.agents', '.claude', '.codex', '.github', 'agents.md', 'claude.md'}
STAGES = ['all', 'planning', 'extract', 'analyzing', 'coding', 'reproduction', 'refinement', 'debugging', 'evaluation']


class CapabilityError(ValueError):
    """Report an unavailable or unsafe capability invocation."""


class InputError(ValueError):
    """Report an invalid capability request before any external work."""


class UsageParser(argparse.ArgumentParser):
    """Return the Board usage exit code with machine-readable diagnostics."""

    def error(self, message: str) -> None:
        """Report invalid command arguments without invoking the capability."""
        print(json.dumps({'status': 'failed', 'stage': 'input', 'error': message}))
        raise SystemExit(64)


def environment() -> dict[str, str]:
    """Use saved CLI authentication and the installed Python environment."""
    removed = PROVIDER_CREDENTIALS | {'PYTHONPATH', 'PYTHONHOME'}
    return {**{key: value for key, value in os.environ.items() if key not in removed}, 'PYTHONDONTWRITEBYTECODE': '1'}


def contained(root: Path, target: Path) -> Path:
    """Validate a dedicated output path without crossing control directories or links."""
    path = target if target.is_absolute() else root / target
    if '..' in path.parts:
        raise InputError('output paths cannot contain parent traversal')
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise InputError('output directory must be strictly inside the issue worktree')
    relative = resolved.relative_to(root)
    if any(part.casefold() in CONTROL_NAMES or part.casefold().startswith('.env') for part in relative.parts):
        raise InputError('output directory cannot use agent or repository control paths')
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent.resolve() != root and parent.resolve().is_relative_to(root)):
        raise InputError('output directory cannot cross symlinks')
    return resolved


def probe(command: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    """Supervise a local preflight command and stop its group on interruption or timeout."""
    def terminate(signum: int, frame: Any) -> None:
        """Unwind the probe through process-group cleanup."""
        raise CapabilityError('Paper2Code preflight interrupted by signal ' + str(signum))
    # Python delivers signals to the main thread; threaded wave callers retain their parent's handlers.
    previous = {kind: signal.getsignal(kind) for kind in (signal.SIGTERM, signal.SIGINT)} if threading.current_thread() is threading.main_thread() else {}
    process = None
    try:
        for kind in previous:
            signal.signal(kind, terminate)
        process = subprocess.Popen(command, env=environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
        raise
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def installed_runtime(root: Path, host: str, require_cli: bool = True) -> dict[str, Any]:
    """Verify the optional installed runtime and its recorded source hashes."""
    if host not in ('codex', 'claude'):
        raise CapabilityError('Paper2Code supports only codex or claude; select a supported lane host explicitly')
    script_root = Path(__file__).resolve().parent
    shared = script_root.parent if script_root.name == 'bin' else root / '.agents'
    runtime = shared / 'lib/paper2code'
    metadata_path = runtime / 'installation.json'
    try:
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise CapabilityError('Paper2Code is not installed; reinstall Super Board with --with-paper2code') from error
    if not isinstance(metadata, dict):
        raise CapabilityError('Paper2Code installation metadata must be an object; reinstall the capability')
    revision = metadata.get('revision')
    hashes = metadata.get('source_sha256')
    dependencies = metadata.get('dependency_versions')
    if (not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision)
            or type(metadata.get('dirty')) is not bool or not isinstance(hashes, dict) or not hashes
            or not isinstance(dependencies, dict) or not isinstance(dependencies.get('PyYAML'), str)):
        raise CapabilityError('Paper2Code installation metadata is invalid; reinstall the capability')
    for name, expected in hashes.items():
        path = runtime / name if isinstance(name, str) else runtime
        if (not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts
                or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected)
                or not path.resolve().is_relative_to(runtime.resolve())
                or any(parent.is_symlink() for parent in [path, *path.parents] if parent != runtime.parent)):
            raise CapabilityError('Paper2Code source manifest contains an unsafe path')
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise CapabilityError('Paper2Code installed source is missing: ' + name) from error
        if actual != expected:
            raise CapabilityError('Paper2Code installed source changed: ' + name + '; reinstall the capability')
    source_files = {str(path.relative_to(runtime)) for path in (runtime / 'codes').rglob('*.py')}
    if not source_files or not source_files <= hashes.keys() or 'codes/pipeline.py' not in source_files:
        raise CapabilityError('Paper2Code source manifest does not cover its installed Python files')
    python = runtime / '.venv/bin/python'
    if not python.is_file() or not os.access(python, os.X_OK):
        raise CapabilityError('Paper2Code Python environment is missing; reinstall with --with-paper2code')
    inspection = probe([str(python), '-c', 'import json,sys,yaml; print(json.dumps({"python":list(sys.version_info[:3]),"pyyaml":yaml.__version__}))'])
    try:
        versions = json.loads(inspection.stdout)
        compatible = inspection.returncode == 0 and tuple(versions['python']) >= (3, 10) and versions['pyyaml'] == dependencies['PyYAML']
    except (ValueError, KeyError, TypeError):
        compatible = False
    if not compatible:
        raise CapabilityError('Paper2Code requires its installed Python 3.10+ environment and declared PyYAML version; reinstall the capability')
    if require_cli and shutil.which(host, path=environment().get('PATH')) is None:
        raise CapabilityError(host + ' executable is missing; install it and authenticate before generation')
    return {'status': 'ready', 'backend': host, 'runtime': str(runtime), 'python': str(python),
            'paper2code_revision': revision, 'source_dirty': metadata['dirty'], 'source_sha256': hashes,
            'dependency_versions': dependencies, 'authentication': 'not_checked'}


def authenticate(host: str, timeout: float) -> None:
    """Check saved CLI login before any model request using the caller's budget."""
    command = ['codex', 'login', 'status'] if host == 'codex' else ['claude', 'auth', 'status', '--json']
    result = probe(command, timeout)
    valid = result.returncode == 0
    if valid and host == 'claude':
        try:
            valid = json.loads(result.stdout).get('loggedIn') is True
        except (ValueError, AttributeError):
            valid = False
    if not valid:
        raise CapabilityError(host + ' saved login is unavailable; authenticate with the CLI before generation')


def record_result(path: Path, result: dict[str, Any]) -> None:
    """Preserve one capability result atomically without replacing earlier evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(json.dumps(result, indent=2) + '\n')
            stream.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def candidate_files(root: Path, artifacts: Path, candidate: Path, stages: list[str]) -> dict[str, str]:
    """Bind full-workflow completion to every declared candidate file and stage."""
    tasks = json.loads(contained(root, artifacts / 'task_list.json').read_text(encoding='utf-8'))
    names = tasks.get('Task list') if isinstance(tasks, dict) else None
    if not isinstance(names, list) or not names or any(not isinstance(name, str) or not name for name in names):
        raise CapabilityError('completed workflow has no valid declared task list')
    if len({name.casefold() for name in names}) != len(names):
        raise CapabilityError('completed workflow has duplicate candidate names')
    if any(name.casefold() in ('config.yaml', 'reproduce.sh') and name != name.casefold() for name in names):
        raise CapabilityError('controller-owned config.yaml and reproduce.sh require their canonical spelling')
    expected = set(names) | {'config.yaml', 'reproduce.sh'}
    hashes = {}
    for name in sorted(expected):
        if Path(name).is_absolute() or Path(name).as_posix() != name or '\\' in name:
            raise CapabilityError('completed workflow has an invalid candidate name')
        path = contained(root, candidate / name)
        if not path.is_file() or not path.stat().st_size:
            raise CapabilityError('completed workflow is missing a nonempty candidate file: ' + name)
        if name not in ('config.yaml', 'reproduce.sh') and not {'analysis:' + name, 'coding:' + name} <= set(stages):
            raise CapabilityError('completed workflow lacks analysis/coding evidence for ' + name)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in candidate.rglob('*'):
        if path.is_symlink() or (path.is_file() and str(path.relative_to(candidate)) not in expected):
            raise CapabilityError('completed workflow contains an undeclared or linked candidate file')
    return hashes


def generate(root: Path, args: argparse.Namespace, runtime: dict[str, Any], output: Path) -> tuple[dict[str, Any], int]:
    """Delegate the existing workflow and preserve a provenance-bound Board result."""
    artifacts, candidate = output / 'artifacts', output / 'candidate'
    command = [runtime['python'], str(Path(runtime['runtime']) / 'codes/pipeline.py'),
               '--backend', args.host, '--timeout', str(args.timeout), '--stage', args.stage,
               '--paper_name', args.paper_name, '--paper_format', args.paper_format,
               '--input', str(args.paper.resolve(strict=True)), '--output_dir', str(artifacts),
               '--output_repo_dir', str(candidate)]
    for name in ('model', 'lookup_file', 'error_file_name', 'save_num', 'eval_type', 'generated_n', 'gold_repo_dir', 'selected_file_path'):
        value = getattr(args, name)
        if value is not None:
            command += ['--' + name, str(value)]
    if args.papercoder:
        command.append('--papercoder')
    process = subprocess.Popen(command, cwd=root, env=environment(), stdout=subprocess.PIPE, text=True)
    interrupted = None
    def terminate(signum: int, frame: Any) -> None:
        """Forward interruption to the controller so its inference cleanup runs."""
        nonlocal interrupted
        interrupted = signum
        try:
            process.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass
    previous = {kind: signal.getsignal(kind) for kind in (signal.SIGTERM, signal.SIGINT)}
    for kind in previous:
        signal.signal(kind, terminate)
    try:
        stdout, _ = process.communicate()
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)
    error = None
    controller = None
    hashes = None
    try:
        controller = json.loads(stdout)
        if not isinstance(controller, dict) or controller.get('status') not in ('completed', 'failed'):
            raise CapabilityError('controller returned an invalid status')
        if controller['status'] == 'completed':
            manifest = json.loads(contained(root, artifacts / 'run.json').read_text(encoding='utf-8'))
            if manifest != controller:
                raise CapabilityError('controller stdout does not match its saved run manifest')
            if (controller.get('backend') != args.host or controller.get('output_dir') != str(artifacts)
                    or controller.get('project_dir') != str(candidate) or not isinstance(controller.get('completed_stages'), list)):
                raise CapabilityError('controller returned mismatched output paths, backend, or stages')
            if (controller.get('input_sha256') != hashlib.sha256(args.paper.read_text(encoding='utf-8').encode()).hexdigest()
                    or (args.model is not None and controller.get('model') != args.model)
                    or (args.stage != 'extract' and (not isinstance(controller.get('cli_version'), str) or not controller['cli_version'].strip()))
                    or controller.get('error') is not None):
                raise CapabilityError('controller completion does not match the requested input, model, or successful CLI evidence')
            stages = controller['completed_stages']
            if not all(isinstance(stage, str) for stage in stages) or len(set(stages)) != len(stages):
                raise CapabilityError('controller completed stages must be distinct names')
            if args.stage == 'all':
                required = {'planning.overview', 'planning.architecture', 'planning.tasks', 'planning.config', 'reproduction'}
                if not required <= set(stages) or controller.get('stage') != 'reproduction' or not candidate.is_dir():
                    raise CapabilityError('controller did not complete the full planning-to-reproduction workflow')
                hashes = candidate_files(root, artifacts, candidate, stages)
            if process.returncode:
                raise CapabilityError('controller reported completion with a nonzero exit')
        else:
            error = controller.get('error') or 'Paper2Code controller failed'
    except (OSError, ValueError, TypeError) as failure:
        error = 'Paper2Code did not return a valid completed result: ' + str(failure)
    status = 'halted' if interrupted else 'failed' if error or process.returncode else 'completed'
    if interrupted:
        error = 'Paper2Code interrupted by signal ' + str(interrupted)
    result = {**runtime, 'status': status, 'authentication': 'checked' if args.stage != 'extract' else 'not_checked',
              'stage': controller.get('stage') if isinstance(controller, dict) else args.stage,
              'requested_stage': args.stage, 'model': args.model, 'paper_format': args.paper_format,
              'input_sha256': hashlib.sha256(args.paper.read_text(encoding='utf-8').encode()).hexdigest(),
              'paper_file_sha256': hashlib.sha256(args.paper.read_bytes()).hexdigest(),
              'artifact_dir': str(artifacts), 'candidate_dir': str(candidate),
              'controller_manifest': str(artifacts / 'run.json'), 'controller_result': controller,
              'candidate_sha256': hashes,
              'completed_stages': controller.get('completed_stages', []) if isinstance(controller, dict) else [],
              'exit_code': process.returncode, 'error': error}
    if artifacts.is_dir():
        evidence = contained(root, artifacts / 'board-results' / (args.stage + '-' + uuid.uuid4().hex + '.json'))
        result['evidence_path'] = str(evidence)
        record_result(evidence, result)
    return result, 0 if status == 'completed' else 1


def main(argv: list[str] | None = None) -> int:
    """Check the installed capability or generate a bounded candidate project."""
    parser = UsageParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--host', choices=['codex', 'claude'], required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--paper', type=Path)
    parser.add_argument('--paper-format', choices=['JSON', 'LaTeX'], default='JSON')
    parser.add_argument('--paper-name', default='paper')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--timeout', type=float)
    parser.add_argument('--model')
    parser.add_argument('--stage', choices=STAGES, default='all')
    parser.add_argument('--lookup-file', type=Path)
    parser.add_argument('--error-file-name', type=Path)
    parser.add_argument('--save-num', type=int)
    parser.add_argument('--eval-type', choices=['ref_free', 'ref_based'])
    parser.add_argument('--generated-n', type=int)
    parser.add_argument('--gold-repo-dir', type=Path)
    parser.add_argument('--selected-file-path', type=Path)
    parser.add_argument('--papercoder', action='store_true')
    arguments = parser.parse_args(argv)
    if not arguments.check:
        if arguments.paper is None or arguments.output_dir is None or arguments.timeout is None:
            parser.error('generation requires --paper, --output-dir and an explicit --timeout')
        if not math.isfinite(arguments.timeout) or arguments.timeout <= 0:
            parser.error('--timeout must be positive and finite')
        if arguments.model is not None and not arguments.model.strip():
            parser.error('--model must be nonempty when supplied')
        if arguments.generated_n is not None and arguments.generated_n <= 0:
            parser.error('--generated-n must be positive')
        if arguments.stage == 'evaluation' and arguments.generated_n is None:
            parser.error('evaluation requires an explicit --generated-n')
    try:
        root = arguments.root.resolve(strict=True)
        if not root.is_dir():
            raise CapabilityError('--root must be an existing issue worktree directory')
        if not arguments.check:
            output = contained(root, arguments.output_dir)
            if arguments.stage == 'all' and (output.exists() or output.is_symlink()):
                raise CapabilityError('full runs require a fresh output directory; existing evidence is preserved')
            content = arguments.paper.read_text(encoding='utf-8')
            if not content.strip() or (arguments.paper_format == 'JSON' and not isinstance(json.loads(content), dict)):
                raise CapabilityError('paper must contain a nonempty JSON object or LaTeX text')
        result = installed_runtime(root, arguments.host, arguments.stage != 'extract' or arguments.check)
        if not arguments.check:
            if arguments.stage != 'extract':
                authenticate(arguments.host, arguments.timeout)
            result, code = generate(root, arguments, result, output)
            print(json.dumps(result))
            return code
        print(json.dumps(result))
        return 0
    except InputError as error:
        print(json.dumps({'status': 'failed', 'stage': 'input', 'backend': arguments.host, 'error': str(error)}))
        return 64
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'halted', 'backend': arguments.host, 'error': str(error)}))
        return 10


if __name__ == '__main__':
    raise SystemExit(main())

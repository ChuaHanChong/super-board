#!/usr/bin/env python3
"""Exercise the optional capability's readiness check and Codex lane permissions."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]


class Paper2Code(unittest.TestCase):
    """Observe the runtime check and lane grants through the public scripts."""

    def setUp(self) -> None:
        """Create a project root and a fake CLI directory."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project'
        self.project.mkdir()
        self.fakebin = self.base / 'bin'
        self.fakebin.mkdir()
        self.env = {**os.environ, 'PATH': str(self.fakebin) + os.pathsep + os.environ['PATH']}

    def install(self) -> None:
        """Install a fake runtime interpreter."""
        interpreter = self.project / '.agents/lib/paper2code/.venv/bin/python'
        interpreter.parent.mkdir(parents=True)
        interpreter.write_text('#!/bin/sh\n')
        interpreter.chmod(0o755)
        (self.project / '.agents/lib/paper2code/codes').mkdir()
        (self.project / '.agents/lib/paper2code/codes/1_planning.py').write_text('')
        (self.project / '.agents/lib/paper2code/installation.json').write_text('{}')

    def test_readiness_requires_the_runtime_and_a_supported_host(self) -> None:
        """Report a missing runtime and refuse a backend Paper2Code cannot run."""
        spec = importlib.util.spec_from_file_location('skills_ready', KIT / 'scripts/super-board-skills-ready.py')
        resolver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(resolver)
        self.assertIn('--with-paper2code', resolver.paper2code_runtime(self.project, 'codex')['error'])
        self.install()
        self.assertTrue(resolver.paper2code_runtime(self.project, 'claude')['ready'])
        (self.project / '.agents/lib/paper2code/codes/1_planning.py').unlink()
        self.assertFalse(resolver.paper2code_runtime(self.project, 'claude')['ready'])
        self.assertIn('codex or claude', resolver.paper2code_runtime(self.project, 'opencode')['error'])

    def test_codex_wave_runs_selected_capability_through_all_lanes(self) -> None:
        """Keep real wave thread readiness from halting an installed optional capability."""
        self.install()
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        subprocess.run([sys.executable, str(KIT / 'tests/fixtures/install_worker_skills.py'), str(self.project)], check=True)
        skill = self.project / '.agents/skills/super-paper2code/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('Fixture-only optional capability.\n')
        shutil.copy2(KIT / 'tests/fixtures/fake_codex.py', self.fakebin / 'codex')
        (self.fakebin / 'python3').symlink_to(sys.executable)
        self.env.update(SUPER_BOARD_SKILLS_HOME=str(self.base / 'home'), SB_CODEX_TEST_LOG=str(self.base / 'calls.jsonl'))
        codex_home = self.base / 'codex-home'
        codex_home.mkdir()
        installation_id = codex_home / 'installation_id'
        installation_id.write_text('fixture-installation-id')
        self.env['CODEX_HOME'] = str(codex_home)
        config = self.base / 'config.json'
        config.write_text('{"max_workers":1,"verify_commands":["git diff --check"]}')
        card = dict(number=7, status='Ready', labels=['feature'], body='Skills: super-paper2code')
        result = subprocess.run(['bash', str(KIT / 'scripts/super-board-codex-wave.sh'), '--config', str(config),
                                 '--cards', json.dumps([card]), '--codex=fixture'], cwd=self.project,
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output['halted'])
        self.assertEqual(output['cards'][0]['column'], 'Done')
        calls = [json.loads(line) for line in (self.base / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual([call['lane'] for call in calls], ['build', 'qa', 'review'])
        for call in calls:
            configs = [call['args'][index + 1] for index, arg in enumerate(call['args']) if arg == '-c']
            grants = next(value.split('=', 1)[1] for value in configs
                          if value.startswith('permissions.super-board-lane.filesystem='))
            filesystem = json.loads(grants.replace('=', ':'))
            expected = {':root': 'read', ':slash_tmp': 'write', ':tmpdir': 'write',
                        str(self.project.resolve()): 'write', str((self.project / '.git').resolve()): 'write'}
            if call['lane'] == 'build':
                expected[str(installation_id.resolve())] = 'write'
            expected[str(Path(self.env.get('GITNEXUS_HOME') or Path.home() / '.gitnexus').resolve())] = 'write'
            self.assertEqual(filesystem, expected)
            self.assertEqual([value for value in configs if value.startswith('shell_environment_policy.set.CODEX_HOME=')],
                             ['shell_environment_policy.set.CODEX_HOME=' + json.dumps(str(codex_home.resolve()))]
                             if call['lane'] == 'build' else [])
        self.assertEqual(installation_id.read_text(), 'fixture-installation-id')

        # Unsafe ID aliases must halt before a model starts or lifecycle state changes.
        command = ['bash', str(KIT / 'scripts/super-board-codex-lane.sh'), '--config', str(config),
                   '--card', json.dumps(card), '--lane', 'build', '--codex=fixture']
        auth = codex_home / 'auth.json'
        auth.write_text('fixture-auth-must-stay-untouched')
        preserved = self.project / '.claude/worktrees/preserved'
        preserved.mkdir(parents=True)
        sentinel = preserved / 'keep'
        sentinel.write_text('preserved')
        log = self.base / 'calls.jsonl'
        for kind in ('missing', 'directory', 'symlink', 'hardlink', 'fifo'):
            with self.subTest(unsafe_id=kind):
                installation_id.unlink()
                if kind == 'directory':
                    installation_id.mkdir()
                elif kind == 'symlink':
                    installation_id.symlink_to(auth)
                elif kind == 'hardlink':
                    os.link(auth, installation_id)
                elif kind == 'fifo':
                    os.mkfifo(installation_id)
                log.write_text('')
                result = subprocess.run(command, cwd=self.project, env=self.env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 79, result.stdout + result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual(output['status'], 'halted')
                self.assertIn('installation_id', output['detail'])
                self.assertEqual(log.read_text(), '')
                self.assertEqual(sentinel.read_text(), 'preserved')
                self.assertEqual(auth.read_text(), 'fixture-auth-must-stay-untouched')
                if kind == 'directory':
                    installation_id.rmdir()
                elif kind != 'missing':
                    installation_id.unlink()
                installation_id.write_text('fixture-installation-id')

        # Codex canonicalizes CODEX_HOME; a directory alias must grant only its real ID.
        alias = self.base / 'codex-home-alias'
        alias.symlink_to(codex_home, target_is_directory=True)
        for configured_home in (str(alias), os.path.relpath(codex_home, self.project)):
            with self.subTest(codex_home=configured_home):
                result = subprocess.run(command, cwd=self.project, env={**self.env, 'CODEX_HOME': configured_home},
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                call = json.loads(log.read_text().splitlines()[-1])
                grants = next(arg.split('=', 1)[1] for arg in call['args']
                              if arg.startswith('permissions.super-board-lane.filesystem='))
                filesystem = json.loads(grants.replace('=', ':'))
                self.assertEqual({path: access for path, access in filesystem.items() if 'codex-home' in path},
                                 {str(installation_id.resolve()): 'write'})
                self.assertIn('shell_environment_policy.set.CODEX_HOME=' + json.dumps(str(codex_home.resolve())), call['args'])

        default_home = self.base / 'default-home'
        default_home.mkdir()
        shutil.copytree(codex_home, default_home / '.codex')
        for configured_home in (None, ''):
            with self.subTest(default_codex_home=configured_home):
                env = {**self.env, 'HOME': str(default_home)}
                env.pop('CODEX_HOME', None)
                if configured_home is not None:
                    env['CODEX_HOME'] = configured_home
                result = subprocess.run(command, cwd=self.project, env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                call = json.loads(log.read_text().splitlines()[-1])
                grants = next(arg.split('=', 1)[1] for arg in call['args']
                              if arg.startswith('permissions.super-board-lane.filesystem='))
                filesystem = json.loads(grants.replace('=', ':'))
                self.assertEqual(filesystem[str((default_home / '.codex/installation_id').resolve())], 'write')
                self.assertIn('shell_environment_policy.set.CODEX_HOME=' + json.dumps(str((default_home / '.codex').resolve())),
                              call['args'])

        looping_home = self.base / 'looping-home'
        looping_home.symlink_to(looping_home)
        for invalid_home in (self.base / 'missing', auth, looping_home):
            with self.subTest(invalid_codex_home=str(invalid_home)):
                log.write_text('')
                result = subprocess.run(command, cwd=self.project, env={**self.env, 'CODEX_HOME': str(invalid_home)},
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 79, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], 'halted')
                self.assertEqual(log.read_text(), '')

        # Ordinary cards do not need an ID and never receive its write grant.
        ordinary = dict(card, body='Ordinary feature card.')
        command[command.index('--card') + 1] = json.dumps(ordinary)
        for lane in ('build', 'qa', 'review'):
            with self.subTest(ordinary_lane=lane):
                command[command.index('--lane') + 1] = lane
                result = subprocess.run(command, cwd=self.project, env={**self.env, 'CODEX_HOME': str(self.base / 'missing')},
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                call = json.loads(log.read_text().splitlines()[-1])
                self.assertFalse(any('installation_id' in arg for arg in call['args']))
                self.assertFalse(any(arg.startswith('shell_environment_policy.set.CODEX_HOME=') for arg in call['args']))


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Exercise optional Paper2Code packaging through the public installers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


PACK = Path(__file__).resolve().parents[1]


def command(arguments: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run an installer with isolated environment and captured diagnostics."""
    return subprocess.run(arguments, env=environment, text=True, capture_output=True, check=False)


class Paper2CodeInstall(unittest.TestCase):
    """Keep optional runtime installation independent from normal Board installs."""

    def setUp(self) -> None:
        """Create a disposable pack and an offline dependency wheel."""
        self.directory = tempfile.TemporaryDirectory(prefix='board-paper2code-install-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.pack = self.root / 'pack'
        self.pack.mkdir()
        for name in ['install.sh', 'get.sh', 'VERSION', 'skills', 'scripts', 'workflows', 'hooks']:
            source = PACK / name
            if source.is_dir():
                shutil.copytree(source, self.pack / name, ignore=shutil.ignore_patterns('__pycache__'))
            else:
                shutil.copy2(source, self.pack / name)
        skill = self.pack / 'skills/super-paper2code'
        skill.mkdir(exist_ok=True)
        (skill / 'SKILL.md').write_text('---\nname: super-paper2code\ndescription: Paper2Code fixture.\n---\nGenerate candidates.\n')
        self.target = self.root / 'target'
        self.target.mkdir()
        binaries = self.root / 'bin'
        binaries.mkdir()
        (binaries / 'python3').symlink_to(sys.executable)
        self.environment = dict(os.environ, HOME=str(self.root / 'home'), PATH=str(binaries) + os.pathsep + os.environ['PATH'], PIP_NO_INDEX='1', PIP_FIND_LINKS=str(self.root / 'wheels'))
        for key in ['CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'SUPER_BOARD_HOST', 'SUPER_BOARD_TARBALL', 'SUPER_BOARD_REF']:
            self.environment.pop(key, None)
        self.wheel = self.root / 'wheels/tqdm-6.0.3-py3-none-any.whl'
        self.wheel.parent.mkdir()
        with zipfile.ZipFile(self.wheel, 'w') as wheel:
            wheel.writestr('tqdm/__init__.py', '__version__ = "6.0.3"\n')
            wheel.writestr('tqdm-6.0.3.dist-info/METADATA', 'Metadata-Version: 2.1\nName: tqdm\nVersion: 6.0.3\n')
            wheel.writestr('tqdm-6.0.3.dist-info/WHEEL', 'Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
            wheel.writestr('tqdm-6.0.3.dist-info/RECORD', '')

    def source(self) -> Path:
        """Create a source packaging fixture with immutable revision metadata."""
        source = self.pack / 'vendor/Paper2Code'
        (source / 'codes').mkdir(parents=True)
        (source / 'codes/1_planning.py').write_text('import tqdm\nprint("fixture-controller:" + tqdm.__version__)\n')
        for name in ['cli_client.py']:
            (source / 'codes' / name).write_text('# Packaging fixture.\n')
        (source / 'LICENSE').write_text('LICENSE\n')
        (source / 'data/prompts').mkdir(parents=True)
        (source / 'data/prompts/ref_free.txt').write_text('Prompt fixture.\n')
        git = ['git', '-C', str(source), '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.com']
        subprocess.run(['git', 'init', '-q', str(source)], check=True)
        subprocess.run([*git, 'add', '.'], check=True)
        subprocess.run([*git, 'commit', '-qm', 'fixture'], check=True)
        self.revision = subprocess.run([*git, 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
        return source

    def install(self, *options: str) -> subprocess.CompletedProcess[str]:
        """Invoke the public checkout installer against the fixture target."""
        return command(['bash', str(self.pack / 'install.sh'), '--no-hooks', '--hosts=codex', *options, str(self.target)], self.environment)

    def test_opt_in_installs_relocatable_pinned_runtime_and_preserves_opt_out(self) -> None:
        """Install only the selected capability and keep it usable after source removal."""
        normal = self.install()
        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertFalse((self.target / '.agents/lib/paper2code').exists())
        self.assertFalse((self.target / '.agents/skills/super-paper2code').exists())
        self.source()
        installed = self.install('--with-paper2code')
        self.assertEqual(installed.returncode, 0, installed.stderr)
        runtime = self.target / '.agents/lib/paper2code'
        metadata = json.loads((runtime / 'installation.json').read_text())
        self.assertEqual(metadata['revision'], self.revision)
        for host in ['claude', 'codex']:
            self.assertTrue((self.target / f'.{host}/skills/super-paper2code/SKILL.md').is_file())
        repeated = self.install('--with-paper2code')
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads((runtime / 'installation.json').read_text()), metadata)
        self.wheel.unlink()
        normal_again = self.install()
        self.assertEqual(normal_again.returncode, 0, normal_again.stderr)
        self.assertEqual(json.loads((runtime / 'installation.json').read_text()), metadata)
        moved = self.root / 'moved-target'
        self.target.rename(moved)
        shutil.rmtree(self.pack)
        result = command([str(moved / '.agents/lib/paper2code/.venv/bin/python'), str(moved / '.agents/lib/paper2code/codes/1_planning.py')], self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'fixture-controller:6.0.3')

    def test_failed_upgrade_preserves_prior_runtime(self) -> None:
        """Reject dependency failures and a missing source before changing prior files."""
        source = self.source()
        installed = self.install('--with-paper2code')
        self.assertEqual(installed.returncode, 0, installed.stderr)
        runtime = self.target / '.agents/lib/paper2code'
        before = {str(path.relative_to(runtime)): path.read_bytes() for path in runtime.rglob('*') if path.is_file() and not path.is_symlink()}
        self.wheel.unlink()
        failed = self.install('--with-paper2code')
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('installation failed', failed.stderr)
        after = {str(path.relative_to(runtime)): path.read_bytes() for path in runtime.rglob('*') if path.is_file() and not path.is_symlink()}
        self.assertEqual(before, after)
        (source / 'codes/1_planning.py').unlink()
        missing = self.install('--with-paper2code')
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('source is missing', missing.stderr)

    def test_git_clone_fallback_initializes_only_the_selected_submodule(self) -> None:
        """Fetch the pinned nested checkout only when optional installation is requested."""
        self.source()
        binaries = self.root / 'clone-bin'
        binaries.mkdir()
        for name in ['bash', 'id', 'python3', 'mktemp', 'mkdir', 'rm', 'dirname', 'tr', 'cp', 'ln', 'chmod', 'grep', 'basename', 'sed']:
            executable = sys.executable if name == 'python3' else shutil.which(name)
            self.assertIsNotNone(executable)
            (binaries / name).symlink_to(executable)
        git = binaries / 'git'
        git.write_text('#!/usr/bin/env python3\nimport os,pathlib,shutil,sys\nargs=sys.argv[1:]\nwith open(os.environ["GIT_LOG"],"a") as log: log.write(" ".join(args)+"\\n")\nif args[0]=="clone": shutil.copytree(os.environ["GIT_FIXTURE"],args[-1])\nelif args[0]=="-C" and args[2:]==["submodule","update","--init","--","vendor/Paper2Code"]: pass\nelif args[0]=="-C" and args[2] in ("status","checkout"): pass\nelif args[0]=="-C" and args[2]=="rev-parse": print(args[1] if args[3]=="--show-toplevel" else "a"*40)\nelse: sys.exit(1)\n')
        git.chmod(0o755)
        log = self.root / 'git.log'
        self.environment.update(PATH=str(binaries), GIT_FIXTURE=str(self.pack), GIT_LOG=str(log))
        result = command([str(binaries / 'bash'), str(self.pack / 'get.sh'), '--ref', 'dev', '--with-paper2code', '--no-hooks', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / '.agents/lib/paper2code/installation.json').is_file())
        calls = log.read_text().splitlines()
        self.assertTrue(any('submodule update --init -- vendor/Paper2Code' in line for line in calls))
        self.assertFalse(any('--recursive' in line for line in calls))
        commit = 'b' * 40
        result = command([str(binaries / 'bash'), str(self.pack / 'get.sh'), '--ref', commit, '--with-paper2code', '--no-hooks', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(line.endswith('checkout -q ' + commit) for line in log.read_text().splitlines()))

    def test_modified_source_is_refused(self) -> None:
        """Refuse local edits the recorded revision would not show."""
        source = self.source()
        (source / 'codes/prompts.py').write_text('# Local edit.\n')
        result = self.install('--with-paper2code')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('local changes', result.stderr)
        self.assertFalse((self.target / '.agents/lib/paper2code').exists())

    def test_custom_archive_is_refused(self) -> None:
        """Refuse a custom archive, which cannot carry the pinned submodule."""
        self.environment['SUPER_BOARD_TARBALL'] = 'file:///unused-archive.tgz'
        result = command(['bash', str(self.pack / 'get.sh'), '--with-paper2code', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('needs a git clone', result.stderr)
        self.assertFalse((self.target / '.agents').exists())


if __name__ == '__main__':
    unittest.main()

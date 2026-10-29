#!/usr/bin/env python3
"""Exercise optional Paper2Code packaging through the public installers."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile


PACK = Path(__file__).resolve().parents[1]
REVISION = 'a' * 40


def command(arguments: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run an installer with isolated environment and captured diagnostics."""
    return subprocess.run(arguments, env=environment, text=True, capture_output=True, check=False)


@unittest.skipIf(sys.version_info < (3, 10), 'Optional Paper2Code runtime requires Python 3.10+')
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
        self.wheel = self.root / 'wheels/PyYAML-6.0.3-py3-none-any.whl'
        self.wheel.parent.mkdir()
        with zipfile.ZipFile(self.wheel, 'w') as wheel:
            wheel.writestr('yaml/__init__.py', '__version__ = "6.0.3"\n')
            wheel.writestr('PyYAML-6.0.3.dist-info/METADATA', 'Metadata-Version: 2.1\nName: PyYAML\nVersion: 6.0.3\n')
            wheel.writestr('PyYAML-6.0.3.dist-info/WHEEL', 'Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
            wheel.writestr('PyYAML-6.0.3.dist-info/RECORD', '')

    def source(self) -> Path:
        """Create a converted-source packaging fixture with immutable revision metadata."""
        source = self.pack / 'vendor/Paper2Code'
        (source / 'codes').mkdir(parents=True)
        (source / 'data/prompts').mkdir(parents=True)
        (source / 'codes/pipeline.py').write_text('import yaml\nprint("fixture-controller:" + yaml.__version__)\n')
        for name in ['cli_runner.py', 'prompts.py', 'auxiliary.py']:
            (source / 'codes' / name).write_text('# Packaging fixture.\n')
        for name in ['LICENSE', 'CONTRACTS.md']:
            (source / name).write_text(name + '\n')
        (source / 'requirements.txt').write_text('PyYAML>=6.0\n')
        (source / 'data/prompts/ref_based.txt').write_text('Reference critique fixture.\n')
        (source / '.paper2code-revision').write_text(REVISION + '\n')
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
        source = self.source()
        installed = self.install('--with-paper2code')
        self.assertEqual(installed.returncode, 0, installed.stderr)
        runtime = self.target / '.agents/lib/paper2code'
        metadata = json.loads((runtime / 'installation.json').read_text())
        self.assertEqual(metadata['revision'], REVISION)
        self.assertFalse(metadata['dirty'])
        self.assertEqual(metadata['dependency_versions']['PyYAML'], '6.0.3')
        self.assertEqual(metadata['source_sha256']['codes/pipeline.py'], hashlib.sha256((source / 'codes/pipeline.py').read_bytes()).hexdigest())
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
        result = command([str(moved / '.agents/lib/paper2code/.venv/bin/python'), str(moved / '.agents/lib/paper2code/codes/pipeline.py')], self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'fixture-controller:6.0.3')

    def test_failed_upgrade_and_unsafe_destinations_preserve_prior_runtime(self) -> None:
        """Reject dependency failures and redirected paths before changing prior files."""
        source = self.source()
        installed = self.install('--with-paper2code')
        self.assertEqual(installed.returncode, 0, installed.stderr)
        runtime = self.target / '.agents/lib/paper2code'
        before = {str(path.relative_to(runtime)): path.read_bytes() for path in runtime.rglob('*') if path.is_file() and not path.is_symlink()}
        self.wheel.unlink()
        failed = self.install('--with-paper2code')
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('prior runtime preserved', failed.stderr)
        after = {str(path.relative_to(runtime)): path.read_bytes() for path in runtime.rglob('*') if path.is_file() and not path.is_symlink()}
        self.assertEqual(before, after)
        (source / 'codes/pipeline.py').unlink()
        missing = self.install('--with-paper2code')
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('converted runtime is missing', missing.stderr)
        outside = self.root / 'outside'
        outside.mkdir()
        sentinel = outside / 'untouched'
        sentinel.write_text('user data')
        shutil.rmtree(self.target / '.agents/lib')
        (self.target / '.agents/lib').symlink_to(outside, target_is_directory=True)
        unsafe = self.install('--with-paper2code')
        self.assertNotEqual(unsafe.returncode, 0)
        self.assertIn('symlinked', unsafe.stderr)
        self.assertEqual(sentinel.read_text(), 'user data')

    def archive_downloads(self, missing_gitlink: bool = False) -> tuple[Path, Path]:
        """Serve immutable Board and Paper2Code archives through a recording curl fixture."""
        source = self.source()
        board_sha = 'b' * 40
        paper_archive = self.root / 'paper.tgz'
        with tarfile.open(paper_archive, 'w:gz') as archive:
            archive.add(source, arcname='Paper2Code-' + REVISION)
        shutil.rmtree(self.pack / 'vendor')
        board_archive = self.root / 'board.tgz'
        with tarfile.open(board_archive, 'w:gz') as archive:
            archive.add(self.pack, arcname='super-board-' + board_sha)
        commit = self.root / 'commit.json'
        commit.write_text(json.dumps({'sha': board_sha}))
        tree = self.root / 'tree.json'
        tree.write_text(json.dumps({'truncated': False, 'tree': [] if missing_gitlink else [{'path': 'vendor/Paper2Code', 'mode': '160000', 'type': 'commit', 'sha': REVISION}]}))
        responses = {
            'https://api.github.com/repos/fixture/super-board/commits/dev': str(commit),
            f'https://api.github.com/repos/fixture/super-board/git/trees/{board_sha}?recursive=1': str(tree),
            f'https://codeload.github.com/fixture/super-board/tar.gz/{board_sha}': str(board_archive),
            f'https://codeload.github.com/ChuaHanChong/Paper2Code/tar.gz/{REVISION}': str(paper_archive),
        }
        mapping = self.root / 'curl-responses.json'
        mapping.write_text(json.dumps(responses))
        curl = self.root / 'bin/curl'
        curl.write_text('#!/usr/bin/env python3\nimport json,os,pathlib,sys\nargs=sys.argv[1:]\nurl=next(arg for arg in args if arg.startswith("https://"))\nwith open(os.environ["CURL_LOG"],"a") as log: log.write(url+"\\n")\nsource=json.loads(pathlib.Path(os.environ["CURL_RESPONSES"]).read_text()).get(url)\nif source is None: sys.exit(22)\ndata=pathlib.Path(source).read_bytes()\nif "-o" in args: pathlib.Path(args[args.index("-o")+1]).write_bytes(data)\nelse: sys.stdout.buffer.write(data)\n')
        curl.chmod(0o755)
        log = self.root / 'curl.log'
        self.environment.update(SUPER_BOARD_REPO='fixture/super-board', CURL_RESPONSES=str(mapping), CURL_LOG=str(log))
        return board_archive, log

    def test_archive_install_fetches_the_gitlink_from_the_downloaded_board_commit(self) -> None:
        """Install the exact nested revision when a GitHub Board archive omits submodules."""
        _, log = self.archive_downloads()
        result = command(['bash', str(self.pack / 'get.sh'), '--ref', 'dev', '--with-paper2code', '--no-hooks', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = json.loads((self.target / '.agents/lib/paper2code/installation.json').read_text())
        self.assertEqual(metadata['revision'], REVISION)
        urls = log.read_text().splitlines()
        self.assertIn('https://codeload.github.com/fixture/super-board/tar.gz/' + 'b' * 40, urls)
        self.assertIn('https://api.github.com/repos/fixture/super-board/git/trees/' + 'b' * 40 + '?recursive=1', urls)
        self.assertIn('https://codeload.github.com/ChuaHanChong/Paper2Code/tar.gz/' + REVISION, urls)
        self.assertFalse(any(url.endswith('/master') or url.endswith('/dev') and 'codeload' in url for url in urls))

    def test_missing_archive_gitlink_fails_before_installation(self) -> None:
        """Refuse an absent pinned nested revision without touching the project."""
        _, log = self.archive_downloads(missing_gitlink=True)
        result = command(['bash', str(self.pack / 'get.sh'), '--ref', 'dev', '--with-paper2code', '--no-hooks', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no exact Paper2Code gitlink', result.stderr)
        self.assertFalse((self.target / '.agents').exists())
        self.assertFalse(any('ChuaHanChong/Paper2Code/tar.gz/' in url for url in log.read_text().splitlines()))

    def test_unavailable_pinned_revision_leaves_the_target_unchanged(self) -> None:
        """Stop when the exact nested commit cannot be downloaded."""
        self.archive_downloads()
        mapping = self.root / 'curl-responses.json'
        responses = json.loads(mapping.read_text())
        del responses['https://codeload.github.com/ChuaHanChong/Paper2Code/tar.gz/' + REVISION]
        mapping.write_text(json.dumps(responses))
        result = command(['bash', str(self.pack / 'get.sh'), '--ref', 'dev', '--with-paper2code', '--no-hooks', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('could not download pinned Paper2Code revision ' + REVISION, result.stderr)
        self.assertEqual(list(self.target.iterdir()), [])

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
        git.write_text('#!/usr/bin/env python3\nimport os,pathlib,shutil,sys\nargs=sys.argv[1:]\nwith open(os.environ["GIT_LOG"],"a") as log: log.write(" ".join(args)+"\\n")\nif args[0]=="clone": shutil.copytree(os.environ["GIT_FIXTURE"],args[-1])\nelif args[0]=="-C" and args[2:]==["submodule","update","--init","--","vendor/Paper2Code"]: pass\nelse: sys.exit(1)\n')
        git.chmod(0o755)
        log = self.root / 'git.log'
        self.environment.update(PATH=str(binaries), GIT_FIXTURE=str(self.pack), GIT_LOG=str(log))
        result = command([str(binaries / 'bash'), str(self.pack / 'get.sh'), '--ref', 'dev', '--with-paper2code', '--no-hooks', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / '.agents/lib/paper2code/installation.json').is_file())
        calls = log.read_text().splitlines()
        self.assertTrue(any('submodule update --init -- vendor/Paper2Code' in line for line in calls))
        self.assertFalse(any('--recursive' in line for line in calls))

    def test_archive_paths_are_validated_before_extraction(self) -> None:
        """Reject a nested archive escape before publishing any runtime files."""
        self.archive_downloads()
        with tarfile.open(self.root / 'paper.tgz', 'w:gz') as archive:
            entry = tarfile.TarInfo('../escaped-paper2code')
            entry.size = 7
            archive.addfile(entry, io.BytesIO(b'outside'))
        result = command(['bash', str(self.pack / 'get.sh'), '--ref', 'dev', '--with-paper2code', '--no-hooks', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unsafe path or link', result.stderr)
        self.assertFalse((self.target / '.agents').exists())

    def test_archive_destination_symlink_never_receives_source_files(self) -> None:
        """Prevent a downloaded Board archive from redirecting the nested source write."""
        board, _ = self.archive_downloads()
        replacement = self.root / 'replacement.tgz'
        outside = self.root / 'outside-vendor'
        outside.mkdir()
        with tarfile.open(board, 'r:gz') as original, tarfile.open(replacement, 'w:gz') as modified:
            for entry in original.getmembers():
                modified.addfile(entry, original.extractfile(entry) if entry.isfile() else None)
            redirect = tarfile.TarInfo('super-board-' + 'b' * 40 + '/vendor')
            redirect.type = tarfile.SYMTYPE
            redirect.linkname = str(outside)
            modified.addfile(redirect)
        replacement.replace(board)
        result = command(['bash', str(self.pack / 'get.sh'), '--ref', 'dev', '--with-paper2code', '--no-hooks', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlinked Paper2Code archive destination', result.stderr)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.target / '.agents').exists())

    def test_custom_archive_requires_an_immutable_board_ref(self) -> None:
        """Refuse ambiguous custom archives before fetching a nested revision."""
        self.environment['SUPER_BOARD_TARBALL'] = 'file:///unused-archive.tgz'
        result = command(['bash', str(self.pack / 'get.sh'), '--with-paper2code', '--no-helper-skills', '--target', str(self.target)], self.environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exact Board commit SHA', result.stderr)
        self.assertFalse((self.target / '.agents').exists())

    def test_source_overlap_and_symlinks_are_refused_without_mutation(self) -> None:
        """Protect source files and external link targets during optional installation."""
        source = self.source()
        original = (source / 'codes/pipeline.py').read_bytes()
        (source / 'codes/pipeline.py').unlink()
        outside = self.root / 'outside-controller.py'
        outside.write_bytes(original)
        (source / 'codes/pipeline.py').symlink_to(outside)
        linked = self.install('--with-paper2code')
        self.assertNotEqual(linked.returncode, 0)
        self.assertIn('symlink', linked.stderr)
        self.assertEqual(outside.read_bytes(), original)
        (source / 'codes/pipeline.py').unlink()
        (source / 'codes/pipeline.py').write_bytes(original)
        self.target = source
        overlapping = self.install('--with-paper2code')
        self.assertNotEqual(overlapping.returncode, 0)
        self.assertIn('overlap', overlapping.stderr)
        self.assertEqual((source / 'codes/pipeline.py').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()

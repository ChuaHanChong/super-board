"""Optional post-run calibration at its public prepare CLI; no model or live board."""
import copy
import json
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts/super-board-calibration.py'


class Calibration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name).resolve()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=t', '-c', 'user.email=t@t',
                        'commit', '-q', '--allow-empty', '-m', 'landed'], check=True)
        self.sha = subprocess.check_output(['git', '-C', str(self.root), 'rev-parse', 'HEAD'], text=True).strip()
        subprocess.run(['git', '-C', str(self.root), 'update-ref', 'refs/remotes/origin/main', self.sha], check=True)
        self.skill = self.root / '.agents/skills/calibrate/SKILL.md'
        self.target = self.root / '.agents/skills/check-work/SKILL.md'
        for path, name in ((self.skill, 'calibrate'), (self.target, 'check-work')):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'---\nname: {name}\ndescription: Test fixture\n---\nExisting skill.\n')
        self.config = {'repo': {'path': '.'}, 'base_branch': 'main',
                       'calibration': {'enabled': True, 'mode': 'apply-existing',
                                       'allowed_skill_paths': [str(self.target)]}}
        self.run = self.root / 'docs/super-board/runs/current-run'
        self.run.mkdir(parents=True)
        self.manifest = self.run / 'manifest.md'
        self.manifest.write_text('Current run: issue #1, PR #2 landed.\n')
        self.proof = self.run / 'review-proof.md'
        self.proof.write_text(f'Final reconciliation: PR #2 merged {self.sha}; reviewed {self.sha}; checks passed.\n')
        self.receipt = {'version': 1, 'run_id': 'current-run', 'outcome': 'completed',
                        'source': 'final-reconciliation', 'selected_issues': [1],
                        'active_workers': [], 'pending': [],
                        'manifest': str(self.manifest.relative_to(self.root)),
                        'cards': [{'number': 1, 'state': 'merged', 'pr': 2,
                                   'pr_url': 'https://github.com/example/app/pull/2',
                                   'reviewed_head_sha': self.sha, 'merge_sha': self.sha,
                                   'evidence_files': [str(self.proof.relative_to(self.root))]}]}

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, config=None, receipt=None):
        cfg = self.root / 'config.json'
        cfg.write_text(json.dumps(self.config if config is None else config))
        note = self.run / 'completion.json'
        note.write_text(json.dumps(self.receipt if receipt is None else receipt))
        result = subprocess.run(['python3', str(SCRIPT), '--config', str(cfg), '--receipt', str(note)],
                                cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_disabled_hook_does_not_require_a_skill_or_receipt(self):
        self.skill.unlink()
        self.assertEqual(self.prepare({'repo': {'path': '.'}})['reason'], 'disabled')

    def test_completed_run_emits_only_external_skill_and_explicit_existing_edit_targets(self):
        result = self.prepare()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['skill_path'], str(self.skill))
        self.assertEqual(result['allowed_skill_paths'], [str(self.target)])
        self.assertIn('personal chat', result['brief'])
        self.assertIn('AGENTS.md', result['brief'])
        self.assertIn('final reconciliation', result['provenance'])
        self.assertEqual(self.target.read_text().splitlines()[-1], 'Existing skill.')

    def test_exit_zero_done_counts_and_partial_states_do_not_authorize_calibration(self):
        for patch in ({'outcome': 'halted'}, {'active_workers': ['worker']}, {'pending': ['approval']},
                      {'selected_issues': [1, 3]}, {'cards': []}, {'source': 'process-exit'}):
            with self.subTest(patch=patch):
                note = dict(self.receipt, **patch)
                self.assertEqual(self.prepare(receipt=note)['status'], 'skipped')
        for state in ('Done', 'partial', 'blocked', 'human-gate'):
            note = copy.deepcopy(self.receipt)
            note['cards'][0]['state'] = state
            self.assertEqual(self.prepare(receipt=note)['status'], 'skipped')

    def test_existing_lane_state_blocks_a_caller_claim_of_zero_workers(self):
        lock = self.root / '.claude/super-board/inflight/1'
        lock.parent.mkdir(parents=True)
        lock.write_text('PID=123\n')
        self.assertEqual(self.prepare()['reason'], 'unfinished-work')
        lock.unlink()
        marker = self.root / '.claude/super-board/codex-wave.pid'
        marker.write_text('123\n')
        self.assertEqual(self.prepare()['reason'], 'unfinished-work')

    def test_native_workflow_marker_blocks_calibration_until_completion_cleanup(self):
        marker = self.root / '.claude/super-board/inflight/workflow-wave.lock'
        marker.parent.mkdir(parents=True)
        marker.write_text('SLUG=app\nSTARTED=now\n')
        self.assertEqual(self.prepare()['status'], 'skipped')
        marker.unlink()
        self.assertEqual(self.prepare()['status'], 'ready')

    def test_unlanded_commit_and_missing_concrete_proof_are_rejected(self):
        subprocess.run(['git', '-C', str(self.root), 'checkout', '-q', '-b', 'unlanded'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=t', '-c', 'user.email=t@t',
                        'commit', '-q', '--allow-empty', '-m', 'not merged'], check=True)
        note = copy.deepcopy(self.receipt)
        note['cards'][0]['merge_sha'] = subprocess.check_output(
            ['git', '-C', str(self.root), 'rev-parse', 'HEAD'], text=True).strip()
        self.assertEqual(self.prepare(receipt=note)['reason'], 'unlanded-commit')
        self.proof.unlink()
        self.assertEqual(self.prepare()['status'], 'skipped')

    def test_evidence_cannot_escape_current_run_to_private_chats(self):
        private = self.root / 'personal-chat.md'
        private.write_text('Unrelated private context')
        note = copy.deepcopy(self.receipt)
        note['cards'][0]['evidence_files'] = [str(private)]
        self.assertEqual(self.prepare(receipt=note)['reason'], 'evidence-outside-run')
        link = self.run / 'escaped.md'
        link.symlink_to(private)
        note['cards'][0]['evidence_files'] = [str(link)]
        self.assertEqual(self.prepare(receipt=note)['reason'], 'evidence-outside-run')

    def test_edit_targets_must_be_existing_canonical_skills(self):
        for path in (self.root / 'AGENTS.md', self.root / 'new-skill/SKILL.md', self.target.parent):
            cfg = copy.deepcopy(self.config)
            cfg['calibration']['allowed_skill_paths'] = [str(path)]
            self.assertEqual(self.prepare(config=cfg)['status'], 'skipped')
        self.target.write_text('---\nname: check-work\n---\nDo not edit this file. Read the canonical skill.\n')
        self.assertEqual(self.prepare()['reason'], 'noncanonical-target')
        self.target.unlink()
        self.target.symlink_to(self.skill)
        self.assertEqual(self.prepare()['reason'], 'noncanonical-target')

    def test_explicit_external_canonical_skill_is_supported_without_copying(self):
        with tempfile.TemporaryDirectory() as other:
            external = pathlib.Path(other).resolve() / 'SKILL.md'
            external.write_text('---\nname: check-work\n---\nCanonical fixture\n')
            cfg = copy.deepcopy(self.config)
            cfg['calibration']['skill_path'] = str(self.skill)
            cfg['calibration']['allowed_skill_paths'] = [str(external)]
            self.assertEqual(self.prepare(config=cfg)['allowed_skill_paths'], [str(external)])
        self.skill.unlink()
        self.assertEqual(self.prepare()['reason'], 'skill-unavailable')


if __name__ == '__main__':
    unittest.main()

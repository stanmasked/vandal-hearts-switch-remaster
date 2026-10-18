"""Synthetic Git fixtures to ensure audio-main integration gate fails closed."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / 'tools/audit_audio_branch_lineage.py'
spec = importlib.util.spec_from_file_location('audit_audio_branch_lineage', MODULE_PATH)
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


def run(root, *args):
    return subprocess.run(['git', '-C', str(root), *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def add(root, files, message):
    for path in files:
        out = root / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text('generated fixture\n', encoding='utf-8')
    run(root, 'add', '.')
    run(root, 'commit', '-m', message)


class BranchLineageAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run(self.root, 'init', '-b', 'main')
        run(self.root, 'config', 'user.email', 'ci-fixture@example.invalid')
        run(self.root, 'config', 'user.name', 'CI Fixture')
        add(self.root, ['source/main.c'], 'common source')
        self.shared = run(self.root, 'rev-parse', 'HEAD')
        run(self.root, 'checkout', '-b', 'audio')
        add(self.root, audit_module.CORE, 'audio foundation')
        self.audio = run(self.root, 'rev-parse', 'HEAD')
        run(self.root, 'checkout', 'main')
        add(self.root, ['source/map02_projection.h'], 'map02 graphics')

    def test_missing_foundation_blocks_even_with_two_valid_branches(self):
        x = audit_module.audit(self.root, 'main', 'audio')
        self.assertEqual(x['status'], 'BLOCKED_DESTINATION_MISSING_AUDIO_FOUNDATION')
        self.assertEqual(x['merge_base_sha'], self.shared)
        self.assertEqual(x['destination_only_commits'], 1)
        self.assertEqual(x['audio_only_commits'], 1)
        self.assertEqual(x['missing_in_destination'], sorted(audit_module.CORE))
        self.assertEqual(x['missing_in_audio'], [])
        self.assertFalse(x['safe_to_merge_asserted'])
        self.assertFalse(x['git_merge_tested'])

    def test_required_audio_missing_in_audio_branch_is_invalid(self):
        run(self.root, 'checkout', 'audio')
        run(self.root, 'rm', audit_module.CORE[0])
        run(self.root, 'commit', '-m', 'remove module')
        x = audit_module.audit(self.root, 'main', 'audio')
        self.assertEqual(x['status'], 'INVALID_AUDIO_BRANCH_MISSING_REQUIRED_FOUNDATION')
        self.assertIn(audit_module.CORE[0], x['missing_in_audio'])

    def test_diverged_with_shared_foundation_requires_review(self):
        add(self.root, audit_module.CORE, 'bring audio foundation onto main')
        x = audit_module.audit(self.root, 'main', 'audio')
        self.assertEqual(x['status'], 'BLOCKED_DIVERGENT_HISTORY_NEEDS_INTEGRATION_REVIEW')

    def test_linear_history_is_only_reviewable_not_merge_approved(self):
        x = audit_module.audit(self.root, 'audio', 'audio')
        self.assertEqual(x['status'], 'READY_FOR_REVIEW_NOT_MERGE_APPROVAL')
        self.assertFalse(x['safe_to_merge_asserted'])
        self.assertEqual(x['audio_source_file_count'], x['destination_source_file_count'])

    def test_missing_branch_fails_closed(self):
        with self.assertRaises(audit_module.BranchAuditError):
            audit_module.audit(self.root, 'main', 'unknown-branch')

    def test_expected_status_enforced(self):
        cmd = ['python3', str(MODULE_PATH), '--repo', str(self.root),
               '--destination', 'main', '--audio', 'audio']
        mismatch = subprocess.run(cmd + ['--expect-status',
                 'READY_FOR_REVIEW_NOT_MERGE_APPROVAL'], text=True,
                 capture_output=True)
        self.assertEqual(mismatch.returncode, 3)
        matched = subprocess.run(cmd + ['--expect-status',
                'BLOCKED_DESTINATION_MISSING_AUDIO_FOUNDATION'], text=True,
                capture_output=True)
        self.assertEqual(matched.returncode, 0)
        without_expectation = subprocess.run(cmd, text=True, capture_output=True)
        self.assertEqual(without_expectation.returncode, 4)


if __name__ == '__main__':
    unittest.main()

"""No-original-assets CLI import smoke test, including Python 3.9 support.

This test intentionally uses the active Python executable so that it catches
runtime annotation evaluation errors such as `bytes | None` on Python 3.9.
"""
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class Map02AuditCliImportTests(unittest.TestCase):
    def test_read_only_auditor_help_imports(self):
        completed = subprocess.run(
            [sys.executable, "-m", "tools.audit_map02_disc_prs", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--require-prior-provenance", completed.stdout)
        self.assertIn("--dat-from-disc", completed.stdout)


if __name__ == "__main__":
    unittest.main()

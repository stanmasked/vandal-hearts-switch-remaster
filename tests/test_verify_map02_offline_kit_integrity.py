"""Mutation tests: prevent execution when an extracted MAP02 kit is altered.

All fixtures and the included PC port are public/synthetic. These probes do
not open any original PlayStation image or user's private VRAM.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from tools.build_map02_intel_mac_offline_kit import bundle
from tools.verify_map02_offline_kit import verify

REPO = Path(__file__).resolve().parent.parent
PUBLIC_RASTER = os.environ.get("MAP02_PINNED_RASTER")


class OfflineKitPreExecutionIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PUBLIC_RASTER:
            raise RuntimeError("public pinned PC-port raster required")

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.base = Path(self.workspace.name)
        archive = self.base / "public-only-kit.zip"
        bundle(REPO, Path(PUBLIC_RASTER), archive)
        self.root = self.base / "extract"
        self.root.mkdir()
        with zipfile.ZipFile(archive) as source:
            source.extractall(self.root)

    def assert_rejects_before_tool_execution(self):
        with self.assertRaises((ValueError, OSError)):
            verify(self.root)
        # Execute the actual owner-facing shell script, not just in-process
        # verifier. macOS-specific tools MUST NOT be reached if files differ.
        p = subprocess.run(
            ["sh", "run-selfcheck.sh"],
            cwd=str(self.root), capture_output=True, text=True, timeout=25,
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("VH_MAP02_INTEL_OFFLINE_SELFCHECK_PASS", p.stdout)
        self.assertNotIn("VH_MAP02_CATALINA_REAL_HELPERS_PASS", p.stdout)
        self.assertNotIn(str(self.base), p.stdout + p.stderr)
        self.assertIn("offline kit integrity verification failed", p.stderr)

    def test_unmodified_extracted_public_kit_verifies(self):
        result = verify(self.root)
        self.assertGreaterEqual(result["file_digests_verified"], 15)
        self.assertTrue(result["no_unlisted_files_or_symlinks"])
        self.assertTrue(result["public_pc_source_git_blob_verified"])
        self.assertFalse(result["kit_signature_verified"])
        self.assertFalse(result["private_user_data_read"])

    def test_modified_python_is_blocked_before_import(self):
        target = self.root / "tools/map02_intel_mac_offline_selfcheck.py"
        target.write_bytes(target.read_bytes() + b"\nprint('MUST_NOT_EXECUTE')\n")
        self.assert_rejects_before_tool_execution()

    def test_corrupted_public_raster_is_blocked(self):
        target = self.root / "upstream/platform/pc/src/pc_raster.c"
        target.write_bytes(target.read_bytes() + b"\n/* altered source */\n")
        self.assert_rejects_before_tool_execution()

    def test_modified_runner_still_checked_by_direct_integrity(self):
        target = self.root / "run-selfcheck.sh"
        target.write_bytes(target.read_bytes() + b"\n# corrupted offline entrypoint\n")
        # Important: a maliciously rewritten shell can skip verification,
        # hence users must authenticate the ZIP against independent SHA-256.
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_symlinked_diagnostic_module_is_blocked(self):
        original = self.root / "source/map02_vram4_page.h"
        relocated = self.root / "source/map02_vram4_frame.h"
        original.unlink()
        original.symlink_to(relocated)
        self.assert_rejects_before_tool_execution()

    def test_extra_executable_file_is_blocked(self):
        (self.root / "tools/injected.py").write_text("print('INJECTED')\n")
        self.assert_rejects_before_tool_execution()

    def test_unexpected_directory_is_blocked(self):
        (self.root / "private").mkdir()
        self.assert_rejects_before_tool_execution()

    def test_dropped_packaged_helper_is_blocked(self):
        (self.root / "tests/test_map02_vram4_frame.c").unlink()
        self.assert_rejects_before_tool_execution()

    def test_forged_manifest_digest_is_blocked(self):
        path = self.root / "files.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["files"]["README.md"] = "0" * 64
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assert_rejects_before_tool_execution()

    def test_false_provenance_flag_is_blocked(self):
        path = self.root / "files.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["retail_assets_included"] = True
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assert_rejects_before_tool_execution()


if __name__ == "__main__":
    unittest.main()

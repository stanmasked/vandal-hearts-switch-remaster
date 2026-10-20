"""Safety checks for the no-disc Intel Mac offline readiness command."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_intel_mac_offline_selfcheck import (
    SCHEMA, SUITES, pinned_public_raster, require_intel_mac,
)

PUBLIC = os.environ.get("MAP02_PINNED_RASTER")


class IntelMacOfflineSelfcheckContractTests(unittest.TestCase):
    def test_linux_cannot_claim_intel_macos(self):
        with patch("platform.system", return_value="Linux"), patch(
            "platform.machine", return_value="x86_64"
        ):
            with self.assertRaisesRegex(ValueError, "requires macOS"):
                require_intel_mac()

    def test_apple_silicon_cannot_claim_intel_macos(self):
        with patch("platform.system", return_value="Darwin"), patch(
            "platform.machine", return_value="arm64"
        ):
            with self.assertRaisesRegex(ValueError, "requires macOS"):
                require_intel_mac()

    def test_exact_pinned_public_source_required(self):
        if not PUBLIC:
            self.fail("MAP02_PINNED_RASTER must name a pinned PUBLIC pc_raster.c")
        reference = Path(PUBLIC)
        self.assertEqual(pinned_public_raster(reference), reference.absolute())
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            altered = folder / "pc_raster.c"
            raw = reference.read_bytes()
            altered.write_bytes(raw + b"\n/* changed public source */\n")
            with self.assertRaisesRegex(ValueError, "Git blob differs"):
                pinned_public_raster(altered)
            altered.unlink()
            altered.symlink_to(reference.resolve())
            with self.assertRaisesRegex(ValueError, "unlinked"):
                pinned_public_raster(altered)

    def test_no_retail_input_suite_and_explicit_result_schema(self):
        self.assertEqual(SCHEMA, "vh.map02.intel-mac.offline-private-ft4-readiness.v1")
        self.assertEqual(sum(n for _, n in SUITES), 42)
        for pattern, _ in SUITES:
            self.assertNotIn("retail", pattern)
            self.assertNotIn("owned", pattern)
            self.assertTrue(pattern.endswith(".py"))


if __name__ == "__main__":
    unittest.main()

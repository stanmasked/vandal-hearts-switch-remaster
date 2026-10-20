"""Native asset-free GNU cc/ar/ld tests for real after-X11 libxcb.a witness."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.check_map02_private_incremental_link import OUTPUT
from tools.check_map02_public_xcb_after_x11 import (
    SCHEMA, measure_xcb_after_x11,
)


class XcbAfterX11NativeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="map02-xcb-native-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.original = self.compile(
            "previous-x11-result",
            "extern int xcb_needed(void); extern int absent(void);\n"
            "int root(void) {return xcb_needed()+absent();}\n")
        self.original.chmod(0o600)
        member = self.compile(
            "xcb-provider",
            "extern int deeper(void); int xcb_needed(void){return deeper();}\n")
        self.archive = self.root / "system-xcb.a"
        subprocess.run(["ar", "rcs", str(self.archive), str(member)],
                       check=True, capture_output=True, timeout=30)

    def compile(self, name, code):
        source = self.root / (name+".c")
        source.write_text(code, encoding="utf-8")
        output = self.root / (name+".o")
        subprocess.run(["cc", "-std=c99", "-c", str(source), "-o", str(output)],
                       check=True, capture_output=True, timeout=30)
        return output

    def test_genuine_native_xcb_link_and_exact_private_outputs(self):
        dest = self.root / "real-second-system-archive"
        report = measure_xcb_after_x11(
            self.original, self.archive, dest, expected_x11_undefined=2)
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["initial_after_x11_strong_undefined"], 2)
        self.assertEqual(report["xcb_strong_export_matches"], 1)
        self.assertEqual(report["input_symbols_without_xcb_strong_export"], 1)
        self.assertEqual(report["original_after_x11_imports_resolved"], 1)
        self.assertEqual(report["original_after_x11_imports_remaining"], 1)
        self.assertEqual(report["new_imports_introduced_by_xcb"], 1)
        self.assertEqual(report["final_strong_undefined_after_xcb"], 2)
        self.assertTrue(report["ordinary_native_static_archive_tested"])
        self.assertFalse(report["system_archive_package_origin_independently_attested"])
        self.assertFalse(report["retail_assets_linked"])
        self.assertFalse(report["fully_linked_game_executable"])
        self.assertFalse(report["authentic_map02_execution_proven"])
        self.assertEqual((dest / "after-x11-unresolved.private.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((dest / "xcb-system-candidate.a").stat().st_mode & 0o777, 0o600)
        self.assertEqual((dest / "linked" / OUTPUT).stat().st_mode & 0o777, 0o600)
        self.assertEqual(dest.stat().st_mode & 0o777, 0o700)
        self.assertEqual((dest / "linked").stat().st_mode & 0o777, 0o700)
        self.assertEqual(
            hashlib.sha256((dest / "linked" / OUTPUT).read_bytes()).hexdigest(),
            report["output_xcb_partial_sha256"])
        self.assertEqual(
            hashlib.sha256(self.original.read_bytes()).hexdigest(),
            report["input_x11_partial_sha256"])
        for private in ("xcb_needed", "absent", "deeper",
                        str(self.original), str(self.archive)):
            self.assertNotIn(private, json.dumps(report))

    def test_wrong_verified_996_baseline_aborts_without_directory(self):
        for baseline in (996, -1, True, "2"):
            with self.subTest(baseline=baseline):
                dest = self.root / ("wrong-"+str(baseline))
                with self.assertRaisesRegex(
                        ValueError, "strong baseline invalid|count differs"):
                    measure_xcb_after_x11(
                        self.original, self.archive, dest,
                        expected_x11_undefined=baseline)
                self.assertFalse(dest.exists())

    def test_thin_archive_does_not_fetch_external_members(self):
        member = self.compile(
            "external-member",
            "int xcb_needed(void) {return 8;}\n")
        thin = self.root / "unsafe-thin-xcb.a"
        subprocess.run(["ar", "rcsT", str(thin), str(member)],
                       check=True, capture_output=True, timeout=30)
        dest = self.root / "no-external-refs"
        with self.assertRaisesRegex(
                ValueError, "not an ordinary static archive"):
            measure_xcb_after_x11(
                self.original, thin, dest, expected_x11_undefined=2)
        self.assertFalse((dest / "linked").exists())

    def test_existing_output_never_overwritten(self):
        dest = self.root / "preexisting-output"
        dest.mkdir()
        marker = dest / "important-file"
        marker.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            measure_xcb_after_x11(
                self.original, self.archive, dest, expected_x11_undefined=2)
        self.assertEqual(marker.read_bytes(), b"keep")

    def test_cli_wrong_baseline_does_not_disclose_symbol_names_or_paths(self):
        dest = self.root / "private-cli-output"
        result = subprocess.run(
            [sys.executable, "-m", "tools.check_map02_public_xcb_after_x11",
             str(self.original), str(self.archive), str(dest)],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(dest.exists())
        for private in ("xcb_needed", "absent", str(self.original),
                        str(self.archive)):
            self.assertNotIn(private, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

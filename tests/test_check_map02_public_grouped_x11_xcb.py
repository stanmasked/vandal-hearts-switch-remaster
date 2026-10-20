"""Real native compiler and GNU ld archive-rescan tests, no retail inputs."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_map02_private_incremental_link import (
    _open_owned, _unresolved, OUTPUT,
)
from tools.check_map02_public_x11_after_sdl2 import _save_local_undefined_manifest
from tools.check_map02_public_grouped_x11_xcb import (
    SCHEMA, measure_grouped_x11_xcb,
)


class PublicGroupedX11XCBTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="map02-public-x11-xcb-group-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.compile(
            "source",
            "extern int alpha_provider(void); extern int never_found(void);\n"
            "int entrypoint(void) {return alpha_provider()+never_found();}\n")
        self.source.chmod(0o600)
        first = self.compile(
            "alpha",
            "extern int beta_provider(void);\n"
            "int alpha_provider(void) {return beta_provider();}\n")
        final_x11 = self.compile(
            "last-x11",
            "int after_xcb_provider(void) {return 42;}\n")
        middle_xcb = self.compile(
            "beta",
            "extern int after_xcb_provider(void);\n"
            "int beta_provider(void) {return after_xcb_provider();}\n")
        self.x11 = self.root / "libx11-copied.a"
        self.xcb = self.root / "libxcb-copied.a"
        subprocess.run(
            ["ar", "rcs", str(self.x11), str(first), str(final_x11)],
            check=True, capture_output=True, timeout=30)
        subprocess.run(
            ["ar", "rcs", str(self.xcb), str(middle_xcb)],
            check=True, capture_output=True, timeout=30)
        self.x11.chmod(0o600)
        self.xcb.chmod(0o600)
        folder = self.root / "private"
        folder.mkdir(mode=0o700)
        entry = _open_owned(self.source, require_private=True)
        try:
            strong, weak = _unresolved(entry)
            self.manifest = _save_local_undefined_manifest(
                folder, entry, strong, weak)
        finally:
            import os
            os.close(entry[0])

    def compile(self, name, source):
        src = self.root / (name + ".c")
        src.write_text(source, encoding="utf-8")
        obj = self.root / (name + ".o")
        subprocess.run(["cc", "-std=c99", "-c", str(src), "-o", str(obj)],
                       check=True, capture_output=True, timeout=30)
        return obj

    def measure(self, destination, **kwargs):
        return measure_grouped_x11_xcb(
            self.manifest, self.source, self.x11, self.xcb,
            destination, expected_sdl2_strong_imports=2, **kwargs)

    def test_real_group_rescans_x11_for_xcb_imports(self):
        sequential = self.root / "plain-sequential.o"
        subprocess.run(
            ["ld", "-r", "-o", str(sequential), str(self.source),
             str(self.x11), str(self.xcb)],
            check=True, capture_output=True, timeout=30)
        old_missing = subprocess.run(
            ["nm", "-u", str(sequential)],
            check=True, capture_output=True, text=True, timeout=30).stdout
        self.assertIn("after_xcb_provider", old_missing)
        outdir = self.root / "actual-grouped-link"
        result = self.measure(outdir)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["initial_strong_undefined_after_sdl2"], 2)
        self.assertEqual(result["original_imports_resolved_by_grouped_ld_r"], 1)
        self.assertEqual(result["original_imports_remaining_after_grouped_ld_r"], 1)
        self.assertEqual(result["new_imports_introduced_by_grouped_x11_xcb"], 0)
        self.assertEqual(result["final_strong_undefined_after_grouped_x11_xcb"], 1)
        self.assertEqual(result["original_inputs_with_any_x11_xcb_strong_provider"], 1)
        self.assertEqual(result["original_inputs_without_x11_xcb_strong_provider"], 1)
        self.assertEqual(result["original_inputs_with_multiple_x11_xcb_providers"], 0)
        self.assertTrue(result["real_gnu_archive_group_executed"])
        self.assertFalse(result["retail_assets_linked"])
        self.assertFalse(result["fully_linked_game_executable"])
        self.assertFalse(result["authentic_map02_execution_proven"])
        grouped = subprocess.run(
            ["nm", "-u", str(outdir / OUTPUT)],
            check=True, capture_output=True, text=True, timeout=30).stdout
        self.assertIn("never_found", grouped)
        self.assertNotIn("after_xcb_provider", grouped)
        self.assertEqual(outdir.stat().st_mode & 0o777, 0o700)
        self.assertEqual((outdir / OUTPUT).stat().st_mode & 0o777, 0o600)
        for hidden in ("alpha_provider", "beta_provider", "after_xcb_provider",
                       "never_found", str(self.source)):
            self.assertNotIn(hidden, json.dumps(result))

    def test_invalid_expected_strong_baseline_fails_before_output(self):
        target = self.root / "wrong-source-strong-count"
        with self.assertRaisesRegex(ValueError, "known|invalid|differs"):
            measure_grouped_x11_xcb(
                self.manifest, self.source, self.x11, self.xcb, target,
                expected_sdl2_strong_imports=1085)
        self.assertFalse(target.exists())

    def test_archive_symlink_rejected_before_link(self):
        fake = self.root / "symlink-libxcb.a"
        fake.symlink_to(self.xcb)
        target = self.root / "unsafe-link"
        with self.assertRaises(ValueError):
            measure_grouped_x11_xcb(
                self.manifest, self.source, self.x11, fake, target,
                expected_sdl2_strong_imports=2)
        self.assertFalse(target.exists())

    def test_existing_target_remains_unchanged(self):
        folder = self.root / "already-in-use"
        folder.mkdir()
        sentinel = folder / "do-not-touch"
        sentinel.write_bytes(b"original")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.measure(folder)
        self.assertEqual(sentinel.read_bytes(), b"original")

    def test_only_one_archive_cannot_satisfy_grouped_two_archive_contract(self):
        target = self.root / "repeat-the-same-archive"
        with self.assertRaisesRegex(ValueError, "repeated candidate inode"):
            measure_grouped_x11_xcb(
                self.manifest, self.source, self.x11, self.x11, target,
                expected_sdl2_strong_imports=2)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()

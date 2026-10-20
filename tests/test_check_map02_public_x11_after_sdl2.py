"""Synthetic native archive experiment for real system follow-up; no retail bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.check_map02_private_incremental_link import OUTPUT
from tools.check_map02_public_x11_after_sdl2 import (
    SCHEMA, measure_x11_after_sdl2,
)


class PublicX11AfterSdl2Tests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="map02-x11-followup-")
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.source = self.compile(
            "sdl2-linked-public",
            "extern int x11_needed(void); extern int missing(void);\n"
            "int initial(void) {return x11_needed() + missing();}\n")
        self.source.chmod(0o600)
        provider = self.compile(
            "real-libx11-member",
            "extern int further(void);\n"
            "int x11_needed(void) {return further();}\n")
        self.archive = self.root / "real-candidate-libX11.a"
        subprocess.run(
            ["ar", "rcs", str(self.archive), str(provider)],
            check=True, capture_output=True, timeout=30)

    def compile(self, name, code):
        path = self.root / (name + ".c")
        path.write_text(code, encoding="utf-8")
        obj = self.root / (name + ".o")
        subprocess.run(["cc", "-std=c99", "-c", str(path), "-o", str(obj)],
                       check=True, capture_output=True, timeout=30)
        return obj

    def test_actual_second_system_archive_link_and_owner_only_report(self):
        target = self.root / "second-stage"
        result = measure_x11_after_sdl2(
            self.source, self.archive, target,
            expected_sdl2_undefined=2)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["initial_after_sdl2_undefined"], 2)
        self.assertEqual(result["x11_strong_export_matches"], 1)
        self.assertEqual(result["original_after_sdl2_imports_resolved"], 1)
        self.assertEqual(result["original_after_sdl2_imports_remaining"], 1)
        self.assertEqual(result["new_imports_introduced_by_x11"], 1)
        self.assertEqual(result["final_strong_undefined_after_x11"], 2)
        self.assertTrue(result["ordinary_native_static_archive_tested"])
        self.assertFalse(result["system_package_origin_independently_attested"])
        self.assertFalse(result["retail_assets_linked"])
        self.assertFalse(result["fully_linked_game_executable"])
        self.assertFalse(result["authentic_map02_execution_proven"])
        self.assertEqual((target / "after-sdl2-unresolved.private.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((target / "x11-system-candidate.a").stat().st_mode & 0o777, 0o600)
        self.assertEqual((target / "linked" / OUTPUT).stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.stat().st_mode & 0o777, 0o700)
        self.assertEqual((target / "linked").stat().st_mode & 0o777, 0o700)
        self.assertEqual(hashlib.sha256(
            (target / "linked" / OUTPUT).read_bytes()).hexdigest(),
            result["output_x11_partial_sha256"])
        for private in ("x11_needed", "missing", "further", str(self.source), str(self.archive)):
            self.assertNotIn(private, json.dumps(result))

    def test_false_real_1085_baseline_rejected_without_writing_outputs(self):
        for wrong in (1085, -1, "2", True):
            target = self.root / ("false-baseline-" + str(wrong))
            with self.subTest(value=wrong):
                with self.assertRaisesRegex(ValueError, "baseline invalid|count differs"):
                    measure_x11_after_sdl2(
                        self.source, self.archive, target,
                        expected_sdl2_undefined=wrong)
                self.assertFalse(target.exists())

    def test_thin_library_rejected_as_external_member_reference(self):
        ext = self.compile("thin-external", "int x11_needed(void) {return 9;}\n")
        thin = self.root / "thin-X11.a"
        subprocess.run(
            ["ar", "rcsT", str(thin), str(ext)],
            check=True, capture_output=True, timeout=30)
        target = self.root / "thin-input"
        with self.assertRaisesRegex(ValueError, "not an ordinary static archive"):
            measure_x11_after_sdl2(
                self.source, thin, target, expected_sdl2_undefined=2)
        self.assertFalse((target / "linked").exists())

    def test_existing_output_never_overwritten(self):
        target = self.root / "existing"
        target.mkdir()
        marker = target / "keep.txt"
        marker.write_text("do not overwrite", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            measure_x11_after_sdl2(
                self.source, self.archive, target,
                expected_sdl2_undefined=2)
        self.assertEqual(marker.read_text(encoding="utf-8"), "do not overwrite")

    def test_cli_false_baseline_omits_private_names_and_paths(self):
        target = self.root / "cli-false-baseline"
        run = subprocess.run(
            [sys.executable, "-m", "tools.check_map02_public_x11_after_sdl2",
             str(self.source), str(self.archive), str(target)],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(target.exists())
        for private in ("x11_needed", "missing", str(self.source), str(self.archive)):
            self.assertNotIn(private, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()

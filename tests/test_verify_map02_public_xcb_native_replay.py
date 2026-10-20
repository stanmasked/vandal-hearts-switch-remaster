"""Synthetic native GCC/ar/ld tests for genuine XCB byte-replay provenance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.check_map02_private_incremental_link import OUTPUT
from tools.check_map02_public_xcb_after_x11 import measure_xcb_after_x11
from tools.verify_map02_public_xcb_native_replay import (
    SCHEMA, verify_xcb_relink,
)


class PublicXcbNativeReplayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="map02-xcb-byte-replay-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.x11 = self.compile(
            "real-prior-x11-output",
            "extern int xcb_needed(void); extern int not_available(void);\n"
            "int initial(void) {return xcb_needed()+not_available();}\n")
        self.x11.chmod(0o600)
        provider = self.compile(
            "xcb-archive-provider",
            "extern int xcb_new_import(void);\n"
            "int xcb_needed(void) {return xcb_new_import();}\n")
        archive = self.root / "genuine-static-libxcb.a"
        subprocess.run(["ar", "rcs", str(archive), str(provider)],
                       check=True, capture_output=True, timeout=30)
        self.first_dir = self.root / "first-native-xcb-link"
        self.original_report = measure_xcb_after_x11(
            self.x11, archive, self.first_dir, expected_x11_undefined=2)
        self.numeric_report = self.root / "public-aggregate.json"
        self.numeric_report.write_text(
            json.dumps(self.original_report), encoding="utf-8")
        self.manifest = self.first_dir / "after-x11-unresolved.private.json"
        self.copied = self.first_dir / "xcb-system-candidate.a"
        self.linked = self.first_dir / "linked" / OUTPUT

    def compile(self, name, code):
        c = self.root / (name + ".c")
        c.write_text(code, encoding="utf-8")
        dest = self.root / (name + ".o")
        subprocess.run(["cc", "-std=c99", "-c", str(c), "-o", str(dest)],
                       check=True, capture_output=True, timeout=30)
        return dest

    def audit(self, folder, *, linked=None, aggregate=None):
        return verify_xcb_relink(
            self.manifest, self.x11, self.copied,
            linked or self.linked, aggregate or self.numeric_report,
            folder, expected_x11_strong=2)

    def test_real_second_link_is_identical_and_owner_only(self):
        folder = self.root / "independent-native-xcb-link"
        r = self.audit(folder)
        self.assertEqual(r["schema"], SCHEMA)
        self.assertEqual(r["input_x11_strong_undefined"], 2)
        self.assertEqual(r["xcb_original_strong_imports_resolved"], 1)
        self.assertEqual(r["xcb_new_strong_imports"], 1)
        self.assertEqual(r["output_xcb_strong_undefined"], 2)
        self.assertTrue(r["saved_xcb_report_recount_verified"])
        self.assertTrue(r["second_native_xcb_ld_r_executed"])
        self.assertTrue(r["byte_identical_xcb_ld_r_verified"])
        self.assertFalse(r["retail_assets_linked"])
        self.assertFalse(r["fully_linked_game_executable"])
        self.assertFalse(r["authentic_map02_execution_proven"])
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual((folder / OUTPUT).stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            hashlib.sha256((folder / OUTPUT).read_bytes()).hexdigest(),
            hashlib.sha256(self.linked.read_bytes()).hexdigest())
        for private in ("xcb_needed", "not_available", "xcb_new_import",
                        str(self.x11), str(self.copied)):
            self.assertNotIn(private, json.dumps(r))

    def test_forged_valid_elf_with_updated_sha_and_counts_fails(self):
        unrelated = self.compile(
            "fake-extra-function",
            "int irrelevant_defined_symbol(void) {return 19;}\n")
        fake_elf = self.root / "fake-still-valid-xcb-link.o"
        subprocess.run(
            ["ld", "-r", str(self.linked), str(unrelated),
             "-o", str(fake_elf)],
            check=True, capture_output=True, timeout=30)
        fake_elf.chmod(0o600)
        report = dict(self.original_report)
        report["output_xcb_partial_sha256"] = hashlib.sha256(
            fake_elf.read_bytes()).hexdigest()
        forged_json = self.root / "forged-numeric-report.json"
        forged_json.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "independent GNU ld-r output differs"):
            self.audit(self.root / "detect-fake-by-native-replay",
                       linked=fake_elf, aggregate=forged_json)

    def test_modified_counts_false_game_claim_and_input_hash_fail_closed(self):
        cases = (
            ("original_after_x11_imports_resolved", 0),
            ("fully_linked_game_executable", True),
            ("input_x11_partial_sha256", "0" * 64),
        )
        for key, value in cases:
            with self.subTest(key=key):
                report = dict(self.original_report)
                report[key] = value
                filename = self.root / ("changed-" + key + ".json")
                filename.write_text(json.dumps(report), encoding="utf-8")
                output = self.root / ("refused-" + key)
                with self.assertRaisesRegex(
                        ValueError, "recount mismatch|invalid schema|hash mismatch"):
                    self.audit(output, aggregate=filename)
                self.assertFalse(output.exists())

    def test_report_symlink_and_already_existing_output_rejected(self):
        alias = self.root / "symlink-aggregate.json"
        alias.symlink_to(self.numeric_report)
        with self.assertRaisesRegex(ValueError, "aggregate inaccessible"):
            self.audit(self.root / "uncreated-output", aggregate=alias)
        dest = self.root / "occupied"
        dest.mkdir()
        important = dest / "keep"
        important.write_text("do not overwrite", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.audit(dest)
        self.assertEqual(important.read_text(encoding="utf-8"),
                         "do not overwrite")

    def test_wrong_baseline_aborts_before_output(self):
        dest = self.root / "bad-expected-count"
        with self.assertRaisesRegex(ValueError, "expected baseline invalid"):
            verify_xcb_relink(
                self.manifest, self.x11, self.copied, self.linked,
                self.numeric_report, dest, expected_x11_strong=True)
        self.assertFalse(dest.exists())

    def test_cli_fail_closed_without_leaking_raw_symbol_names(self):
        target = self.root / "cli-wrong-baseline"
        run = subprocess.run(
            [sys.executable, "-m", "tools.verify_map02_public_xcb_native_replay",
             str(self.manifest), str(self.x11), str(self.copied),
             str(self.linked), str(self.numeric_report), str(target)],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(target.exists())
        for private in ("xcb_needed", "not_available", "xcb_new_import",
                        str(self.x11), str(self.manifest)):
            self.assertNotIn(private, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()

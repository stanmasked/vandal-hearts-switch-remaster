"""Real GNU cc/ar/ld regression for privacy-safe X11 import provenance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.check_map02_private_incremental_link import (
    OUTPUT, _open_owned, _unresolved, probe_private_incremental_link,
)
from tools.check_map02_private_provider_coverage import _sha_names
from tools.check_map02_public_x11_origin_partition import (
    SCHEMA, partition_x11_import_origin,
)


class X11ImportOriginPartitionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="map02-x11-origin-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private = self.root / "private-manifests"
        self.private.mkdir(mode=0o700)
        self.original = self.compile(
            "original", "extern int needed(void);\n"
            "extern int original_x(void); extern int still_missing(void);\n"
            "int root(void) {return needed()+original_x()+still_missing();}\n")
        self.original.chmod(0o600)
        self.original_manifest = self.make_manifest(self.original, "original")
        sdl_provider = self.compile(
            "sdl-provider", "extern int sdl_new(void);\n"
            "int needed(void) {return sdl_new();}\n")
        sdl_archive = self.archive("libSDL2", sdl_provider)
        probe_private_incremental_link(
            self.original_manifest, self.original, [sdl_archive],
            self.root / "sdl-stage", expected_initial_strong_imports=3)
        self.sdl = self.root / "sdl-stage" / OUTPUT
        self.sdl_manifest = self.make_manifest(self.sdl, "after-sdl")
        x11_provider = self.compile(
            "x11-provider", "extern int x11_new(void);\n"
            "int sdl_new(void) {return x11_new();}\n"
            "int original_x(void) {return 7;}\n")
        x11_archive = self.archive("libX11", x11_provider)
        probe_private_incremental_link(
            self.sdl_manifest, self.sdl, [x11_archive],
            self.root / "x11-stage", expected_initial_strong_imports=3)
        self.x11 = self.root / "x11-stage" / OUTPUT

    def compile(self, name, code):
        source = self.root / (name + ".c")
        source.write_text(code, encoding="utf-8")
        obj = self.root / (name + ".o")
        subprocess.run(
            ["cc", "-std=c99", "-c", str(source), "-o", str(obj)],
            check=True, capture_output=True, timeout=30)
        return obj

    def archive(self, name, obj):
        archive = self.root / (name + ".a")
        subprocess.run(
            ["ar", "rcs", str(archive), str(obj)],
            check=True, capture_output=True, timeout=30)
        return archive

    def make_manifest(self, path, label):
        entry = _open_owned(path, require_private=True)
        try:
            strong, weak = _unresolved(entry)
            data = {
                "schema": "vh.map02.private-undefined-symbol-manifest.v1",
                "relocatable_elf_sha256": entry[3],
                "partial_elf_unresolved_strong_symbol_count": len(strong),
                "partial_elf_unresolved_weak_symbol_count": len(weak),
                "partial_elf_unresolved_strong_symbols_sha256":
                    _sha_names(strong),
                "strong_symbols": strong,
                "weak_symbols": weak,
            }
        finally:
            import os
            os.close(entry[0])
        manifest = self.private / (label + ".private.json")
        manifest.write_text(json.dumps(data), encoding="utf-8")
        manifest.chmod(0o600)
        return manifest

    def audit(self, **kwargs):
        return partition_x11_import_origin(
            self.original_manifest, self.original,
            self.sdl_manifest, self.sdl, self.x11,
            expected_original=3, expected_after_sdl2=3,
            expected_original_remaining=2, expected_sdl2_introduced=1,
            **kwargs)

    def test_real_three_elf_origin_partition_and_sanitized_results(self):
        report = self.audit()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["original_initial_imports"], 3)
        self.assertEqual(report["original_remaining_after_sdl2"], 2)
        self.assertEqual(report["original_remaining_after_x11"], 1)
        self.assertEqual(report["original_imports_newly_resolved_by_x11"], 1)
        self.assertEqual(report["sdl2_new_imports"], 1)
        self.assertEqual(report["sdl2_new_imports_remaining_after_x11"], 0)
        self.assertEqual(report["sdl2_new_imports_resolved_by_x11"], 1)
        self.assertEqual(report["x11_new_imports_after_link"], 1)
        self.assertEqual(report["final_strong_undefined_after_x11"], 2)
        self.assertTrue(report["all_undefined_imports_partitioned"])
        self.assertFalse(report["retail_assets_linked"])
        self.assertFalse(report["fully_linked_game_executable"])
        self.assertFalse(report["authentic_map02_execution_proven"])
        self.assertEqual(
            report["original_remaining_after_x11"] +
            report["sdl2_new_imports_remaining_after_x11"] +
            report["x11_new_imports_after_link"], 2)
        for label in ("original_x", "still_missing", "needed",
                      "sdl_new", "x11_new", str(self.original)):
            self.assertNotIn(label, json.dumps(report))
        for field in ("public_original_partial_sha256",
                      "public_sdl2_partial_sha256",
                      "public_x11_partial_sha256"):
            self.assertEqual(len(report[field]), 64)

    def test_wrong_baseline_never_claims_progress(self):
        with self.assertRaisesRegex(ValueError, "known SDL2 baseline mismatch"):
            partition_x11_import_origin(
                self.original_manifest, self.original,
                self.sdl_manifest, self.sdl, self.x11)
        with self.assertRaisesRegex(ValueError, "expected counts invalid"):
            partition_x11_import_origin(
                self.original_manifest, self.original,
                self.sdl_manifest, self.sdl, self.x11,
                expected_original=True)

    def test_private_manifest_with_fake_but_self_consistent_symbols_rejected(self):
        doc = json.loads(self.sdl_manifest.read_text(encoding="utf-8"))
        doc["strong_symbols"] = sorted(["fabricated", "original_x", "still_missing"])
        doc["partial_elf_unresolved_strong_symbols_sha256"] = _sha_names(
            doc["strong_symbols"])
        self.sdl_manifest.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest ELF names differ"):
            self.audit()

    def test_x11_elf_modified_after_nm_rejected_before_positive_report(self):
        """A late in-place byte mutation cannot survive the final input seal."""
        from tools import check_map02_public_x11_origin_partition as module
        actual_unresolved = module._unresolved

        def mutate_after_read(entry):
            names = actual_unresolved(entry)
            if entry[1] == self.x11.absolute():
                with self.x11.open("ab") as target:
                    target.write(b"late-content-mutation")
            return names

        with mock.patch.object(
                module, "_unresolved", side_effect=mutate_after_read):
            with self.assertRaisesRegex(ValueError, "changed during link"):
                self.audit()

    def test_x11_elf_identical_bytes_new_inode_rejected(self):
        """Even byte-identical replacement must fail path/inode confirmation."""
        from tools import check_map02_public_x11_origin_partition as module
        actual_unresolved = module._unresolved

        def replace_after_read(entry):
            names = actual_unresolved(entry)
            if entry[1] == self.x11.absolute():
                alternate = self.root / "fresh-inode-x11.o"
                alternate.write_bytes(self.x11.read_bytes())
                alternate.chmod(0o600)
                alternate.replace(self.x11)
            return names

        with mock.patch.object(
                module, "_unresolved", side_effect=replace_after_read):
            with self.assertRaisesRegex(ValueError, "path replaced"):
                self.audit()

    def test_reused_source_inode_rejected(self):
        with self.assertRaisesRegex(ValueError, "inputs alias"):
            partition_x11_import_origin(
                self.original_manifest, self.original,
                self.original_manifest, self.original, self.x11,
                expected_original=3, expected_after_sdl2=3,
                expected_original_remaining=3, expected_sdl2_introduced=0)

    def test_cli_real_three_elf_input_redacts_private_names(self):
        run = subprocess.run(
            [sys.executable, "-m", "tools.check_map02_public_x11_origin_partition",
             str(self.original_manifest), str(self.original),
             str(self.sdl_manifest), str(self.sdl), str(self.x11)],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(run.returncode, 0)
        for secret in ("original_x", "still_missing", "sdl_new",
                       str(self.sdl), str(self.original_manifest)):
            self.assertNotIn(secret, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()

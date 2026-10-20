"""Synthetic Linux GNU cc/ar/ld test; no private retail data is used."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.check_map02_private_incremental_link import OUTPUT
from tools.check_map02_public_sdl2_archive_witness import (
    SCHEMA, probe_public_sdl2_archive,
)
from tools.verify_map02_public_sdl2_archive_recount import (
    verify_saved_sdl2_recount,
)


class PublicSdl2StaticWitnessTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="map02-system-archive-")
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        owner = self.root / "original-public"
        owner.mkdir(mode=0o700)
        self.partial = self.compile(
            "public-code", "extern int needed(void); extern int missing(void);\n"
            "int root(void) {return needed() + missing();}\n")
        self.partial.chmod(0o600)
        names = ["missing", "needed"]
        self.manifest = owner / "map02-unresolved-symbols.private.json"
        self.manifest.write_text(json.dumps({
            "schema": "vh.map02.private-undefined-symbol-manifest.v1",
            "relocatable_elf_sha256":
                hashlib.sha256(self.partial.read_bytes()).hexdigest(),
            "partial_elf_unresolved_strong_symbol_count": 2,
            "partial_elf_unresolved_weak_symbol_count": 0,
            "partial_elf_unresolved_strong_symbols_sha256":
                hashlib.sha256(json.dumps(
                    names, ensure_ascii=True,
                    separators=(",", ":")).encode("ascii")).hexdigest(),
            "strong_symbols": names,
            "weak_symbols": [],
        }), encoding="utf-8")
        self.manifest.chmod(0o600)
        provider = self.compile(
            "provided-from-sdl2", "extern int extra(void);\n"
            "int needed(void) {return extra();}\n")
        self.archive = self.root / "synthetic-real-libSDL2.a"
        subprocess.run(
            ["ar", "rcs", str(self.archive), str(provider)],
            check=True, capture_output=True, timeout=30)

    def compile(self, name, text):
        source = self.root / (name + ".c")
        source.write_text(text, encoding="utf-8")
        obj = self.root / (name + ".o")
        subprocess.run(
            ["cc", "-std=c99", "-c", str(source), "-o", str(obj)],
            capture_output=True, check=True, timeout=30)
        return obj

    def test_real_native_system_archive_copy_and_partial_link(self):
        target = self.root / "sealed-native-result"
        result = probe_public_sdl2_archive(
            self.manifest, self.partial, self.archive, target,
            expected_initial_strong_imports=2)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["initial_strong_undefined"], 2)
        self.assertEqual(
            result["sdl2_candidate_strong_exports_matching_initial"], 1)
        self.assertEqual(result["initial_without_sdl2_candidate_export"], 1)
        self.assertEqual(result["original_imports_resolved_by_actual_ld_r"], 1)
        self.assertEqual(result["original_imports_still_unresolved"], 1)
        self.assertEqual(result["new_undefined_imports_introduced_by_sdl2"], 1)
        self.assertEqual(result["final_undefined_strong_count"], 2)
        self.assertTrue(result["ordinary_native_static_archive_tested"])
        self.assertFalse(result["system_archive_package_origin_independently_attested"])
        self.assertTrue(result["asset_free_public_pc_code_only"])
        self.assertFalse(result["fully_linked_game_executable"])
        self.assertFalse(result["original_map02_execution_proven"])
        self.assertEqual((target / "linked" / OUTPUT).stat().st_mode & 0o777, 0o600)
        self.assertEqual((target / "sdl2-system-candidate.a").stat().st_mode & 0o777, 0o600)
        self.assertEqual((target / "linked").stat().st_mode & 0o777, 0o700)
        for name in ("needed", "missing", "extra", str(self.manifest),
                     str(self.partial)):
            self.assertNotIn(name, json.dumps(result))

    def test_modified_copy_after_nm_coverage_does_not_reach_linker(self):
        """An in-place change between the real nm and ld steps fails closed."""
        from tools import check_map02_public_sdl2_archive_witness as module
        real_audit = module.audit_provider_coverage
        destination = self.root / "mutated-after-coverage"

        def tamper_copy(*args, **kwargs):
            aggregate = real_audit(*args, **kwargs)
            with (destination / "sdl2-system-candidate.a").open("ab") as fd:
                fd.write(b"tampered-after-nm")
            return aggregate

        with mock.patch.object(module, "audit_provider_coverage",
                               side_effect=tamper_copy):
            with self.assertRaisesRegex(ValueError, "changed during link"):
                probe_public_sdl2_archive(
                    self.manifest, self.partial, self.archive, destination,
                    expected_initial_strong_imports=2)
        self.assertFalse((destination / "linked").exists())

    def test_identical_bytes_new_archive_inode_after_nm_is_rejected(self):
        """SHA agreement alone cannot permit pathname substitution."""
        from tools import check_map02_public_sdl2_archive_witness as module
        real_audit = module.audit_provider_coverage
        destination = self.root / "swapped-after-coverage"

        def swap_copy(*args, **kwargs):
            aggregate = real_audit(*args, **kwargs)
            current = destination / "sdl2-system-candidate.a"
            replacement = destination / "replacement-temp.a"
            replacement.write_bytes(current.read_bytes())
            replacement.chmod(0o600)
            replacement.replace(current)
            return aggregate

        with mock.patch.object(module, "audit_provider_coverage",
                               side_effect=swap_copy):
            with self.assertRaisesRegex(
                    ValueError, "changed during link|path replaced"):
                probe_public_sdl2_archive(
                    self.manifest, self.partial, self.archive, destination,
                    expected_initial_strong_imports=2)
        self.assertFalse((destination / "linked").exists())

        target = self.root / "wrong-source-count"
        with self.assertRaisesRegex(ValueError, "baseline mismatch"):
            probe_public_sdl2_archive(
                self.manifest, self.partial, self.archive, target)
        self.assertFalse(target.exists())

    def make_saved_recount(self, label):
        target = self.root / label
        report = probe_public_sdl2_archive(
            self.manifest, self.partial, self.archive, target,
            expected_initial_strong_imports=2)
        saved = target / "aggregate.json"
        saved.write_text(json.dumps(report), encoding="utf-8")
        local_archive = target / "sdl2-system-candidate.a"
        linked = target / "linked" / OUTPUT
        return report, saved, local_archive, linked

    def test_saved_report_recounts_actual_source_candidate_and_linked_elf(self):
        report, saved, candidate, linked = self.make_saved_recount(
            "recount-valid")
        self.assertEqual(len(report["sdl2_candidate_archive_sha256"]), 64)
        verified = verify_saved_sdl2_recount(
            self.manifest, self.partial, candidate, linked, saved,
            expected_initial_strong_imports=2)
        self.assertEqual(verified["baseline_strong_imports"], 2)
        self.assertEqual(verified["original_imports_resolved"], 1)
        self.assertEqual(verified["new_imports"], 1)
        self.assertEqual(verified["final_strong_imports"], 2)
        self.assertTrue(verified["saved_report_recount_verified"])
        self.assertTrue(verified["copied_candidate_archive_identity_verified"])
        self.assertFalse(verified["full_game_executable_proven"])
        self.assertFalse(verified["authentic_map02_execution_proven"])
        for private_name in ("needed", "missing", "extra"):
            self.assertNotIn(private_name, json.dumps(verified))

    def test_changed_saved_count_fails_independent_recount(self):
        data, saved, candidate, linked = self.make_saved_recount(
            "recount-corrupted")
        data["original_imports_resolved_by_actual_ld_r"] = 0
        saved.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "recount differs"):
            verify_saved_sdl2_recount(
                self.manifest, self.partial, candidate, linked, saved,
                expected_initial_strong_imports=2)

    def test_substituted_static_candidate_fails_digest_audit(self):
        _, saved, candidate, linked = self.make_saved_recount(
            "recount-changed-archive")
        with candidate.open("ab") as output:
            output.write(b"extra-bytes")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            verify_saved_sdl2_recount(
                self.manifest, self.partial, candidate, linked, saved,
                expected_initial_strong_imports=2)

    def test_saved_report_symlink_and_wrong_claims_are_rejected(self):
        data, saved, candidate, linked = self.make_saved_recount(
            "recount-symlink-unsafe")
        data["fully_linked_game_executable"] = True
        saved.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "claims invalid"):
            verify_saved_sdl2_recount(
                self.manifest, self.partial, candidate, linked, saved,
                expected_initial_strong_imports=2)
        alias = self.root / "aliased-report.json"
        alias.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, "aggregate unavailable"):
            verify_saved_sdl2_recount(
                self.manifest, self.partial, candidate, linked, alias,
                expected_initial_strong_imports=2)

    def test_thin_archive_and_symlink_refused(self):
        thin = self.root / "thin.a"
        external = self.compile(
            "thin-external", "int needed(void) {return 10;}\n")
        subprocess.run(
            ["ar", "rcsT", str(thin), str(external)],
            check=True, capture_output=True, timeout=30)
        destination = self.root / "thin-destination"
        with self.assertRaisesRegex(ValueError, "not an ordinary static archive"):
            probe_public_sdl2_archive(
                self.manifest, self.partial, thin, destination,
                expected_initial_strong_imports=2)
        self.assertFalse((destination / "linked").exists())
        alias = self.root / "alias.a"
        alias.symlink_to(self.archive)
        dest2 = self.root / "linked-source"
        with self.assertRaises(OSError):
            probe_public_sdl2_archive(
                self.manifest, self.partial, alias, dest2,
                expected_initial_strong_imports=2)
        self.assertFalse((dest2 / "linked").exists())

    def test_existing_target_never_overwritten(self):
        target = self.root / "existing"
        target.mkdir()
        keep = target / "keep.private"
        keep.write_text("untouched", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            probe_public_sdl2_archive(
                self.manifest, self.partial, self.archive, target,
                expected_initial_strong_imports=2)
        self.assertEqual(keep.read_text(encoding="utf-8"), "untouched")


if __name__ == "__main__":
    unittest.main()

"""Synthetic real GNU gcc/ar/ld-r tests; never use or log retail media."""
import json
from pathlib import Path
import unittest

from tools.check_map02_public_glibc_pc_provider_census import audit_glibc_static_coverage
from tools.check_map02_public_glibc_actual_ld_r import audit_glibc_real_link, SCHEMA
from tests.test_check_map02_public_glibc_pc_provider_census import (
    OriginalPCGLibCProviderCensusTests as Fixture,
)


class RealGlibcGroupedLinkTests(unittest.TestCase):
    setUp = Fixture.setUp
    compile = Fixture.compile
    archive = Fixture.archive
    make_manifest = Fixture.make_manifest

    def build_case(self, *, independent_provider_members=True):
        # In a real group, 'both' duplicated within selected members causes a
        # legitimate multiple-definition linker failure. Split libm members
        # for the positive case so the double-export remains selectable but
        # the duplicate member is not pulled into the actual GNU ld-r.
        if independent_provider_members:
            part = self.compile("libm-only", "int orig_libm(void){return 3;}\n")
            alternate = self.compile("libm-alternate", "int orig_both(void){return 4;}\n")
            self.libm = self.archive("libm-separate-members.a", part, alternate)
        census = audit_glibc_static_coverage(
            self.orig_manifest, self.original, self.sdl_manifest,
            self.sdl_elf, self.four_elf, self.libc, self.libm,
            self.root / "provider-census",
            expected_original=5, expected_after_sdl=5,
            expected_original_survivors=4, expected_final=5)
        self.census_json = self.root / "aggregate.json"
        self.census_json.write_text(json.dumps(census), encoding="utf-8")
        return census

    def probe(self, folder="real-ld-r", **kwargs):
        return audit_glibc_real_link(
            self.orig_manifest, self.original,
            self.sdl_manifest, self.sdl_elf, self.four_elf,
            self.root / "provider-census/glibc-system-libc-static.a",
            self.root / "provider-census/glibc-system-libm-static.a",
            self.census_json, self.root / folder,
            expected_pc_survivors=4, expected_four_total=5, **kwargs)

    def test_actual_grouped_ld_r_preserves_origin_equations(self):
        self.build_case()
        result = self.probe()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["initial_four_group_undefined"], 5)
        self.assertEqual(result["initial_original_pc_undefined"], 4)
        self.assertEqual(result["original_pc_resolved_by_real_glibc_ld_r"], 3)
        self.assertEqual(result["original_pc_remaining_after_real_glibc_ld_r"], 1)
        self.assertEqual(result["sdl2_survivors_resolved_by_real_glibc_ld_r"], 0)
        self.assertEqual(result["four_archive_new_remaining_after_real_glibc_ld_r"], 1)
        self.assertEqual(result["glibc_new_strong_undefined"], 0)
        self.assertEqual(result["final_strong_undefined"], 2)
        self.assertTrue(result["actual_native_grouped_ld_r_executed"])
        self.assertFalse(result["fully_linked_game_executable"])
        self.assertFalse(result["authentic_map02_execution_proven"])
        self.assertFalse(result["private_symbol_names_disclosed"])
        for sensitive in ("orig_libc", "orig_libm", "orig_both",
                          "orig_uncovered", str(self.root)):
            self.assertNotIn(sensitive, json.dumps(result))

    def test_report_source_sha_mismatch_fails_before_link(self):
        self.build_case()
        report = json.loads(self.census_json.read_text())
        report["copied_native_libm_archive_sha256"] = "0" * 64
        self.census_json.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "census SHA mismatched"):
            self.probe("sha-rejected")
        self.assertFalse((self.root / "sha-rejected").exists())

    def test_rejects_wrong_pc_survivor_count_before_link(self):
        self.build_case()
        with self.assertRaisesRegex(ValueError, "original origin baseline invalid"):
            audit_glibc_real_link(
                self.orig_manifest, self.original,
            self.sdl_manifest, self.sdl_elf, self.four_elf,
                self.root / "provider-census/glibc-system-libc-static.a",
                self.root / "provider-census/glibc-system-libm-static.a",
                self.census_json, self.root / "bad-baseline",
                expected_pc_survivors=3, expected_four_total=5)
        self.assertFalse((self.root / "bad-baseline").exists())

    def test_real_native_duplicate_definition_fails_closed(self):
        self.build_case(independent_provider_members=False)
        with self.assertRaisesRegex(ValueError, "native linker tool failed"):
            self.probe("duplicate-symbols")
        # No report of a successful grouped link may be emitted.
        self.assertFalse((self.root / "duplicate-symbols/linked/map02-private-candidate-linked.o").exists())

    def test_rejects_census_symlink(self):
        self.build_case()
        alias = self.root / "census-alias.json"
        alias.symlink_to(self.census_json)
        self.census_json = alias
        with self.assertRaisesRegex(ValueError, "symlink forbidden"):
            self.probe("symlink-rejected")
        self.assertFalse((self.root / "symlink-rejected").exists())


if __name__ == "__main__":
    unittest.main()

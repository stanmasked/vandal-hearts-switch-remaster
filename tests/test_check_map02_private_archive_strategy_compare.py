"""Only synthetic GNU cc/ar/ld objects; never use retail game resources."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import check_map02_private_archive_strategy_compare as comparison
from tools.check_map02_private_incremental_link import OUTPUT


class PairedArchiveComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-paired-ld-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        private = self.root / "manifest"
        private.mkdir(mode=0o700)
        self.manifest = private / "imports.private.json"
        self.base = self.compile(
            "root", "extern int needed(void); extern int missing(void);\n"
            "int root(void) { return needed() + missing(); }\n")
        self.base.chmod(0o600)
        names = ["missing", "needed"]
        doc = {
            "schema": "vh.map02.private-undefined-symbol-manifest.v1",
            "relocatable_elf_sha256":
                hashlib.sha256(self.base.read_bytes()).hexdigest(),
            "partial_elf_unresolved_strong_symbol_count": 2,
            "partial_elf_unresolved_weak_symbol_count": 0,
            "partial_elf_unresolved_strong_symbols_sha256":
                hashlib.sha256(json.dumps(
                    names, ensure_ascii=True,
                    separators=(",", ":")).encode("ascii")).hexdigest(),
            "strong_symbols": names,
            "weak_symbols": [],
        }
        self.manifest.write_text(json.dumps(doc), encoding="utf-8")
        self.manifest.chmod(0o600)
        self.provider = self.compile(
            "provider", "extern int followup(void);\n"
            "int needed(void) { return followup(); }\n")
        self.followup = self.compile(
            "followup", "int followup(void) { return 42; }\n")
        self.first = self.archive("lib-needed", self.provider)
        self.second = self.archive("lib-followup", self.followup)

    def compile(self, name, source):
        cfile = self.root / (name + ".c")
        cfile.write_text(source, encoding="utf-8")
        output = self.root / (name + ".o")
        subprocess.run(["cc", "-std=c99", "-fno-stack-protector",
                        "-c", str(cfile), "-o", str(output)],
                       check=True, capture_output=True, timeout=30)
        return output

    def archive(self, name, object_file):
        output = self.root / (name + ".a")
        subprocess.run(["ar", "rcs", str(output), str(object_file)],
                       check=True, capture_output=True, timeout=30)
        return output

    def test_two_real_links_are_pinned_and_report_only_aggregate_delta(self):
        parent = self.root / "both-strategies"
        report = comparison.compare_private_archive_strategies(
            self.manifest, self.base,
            [self.second, self.first], parent)
        self.assertEqual(report["schema"], comparison.SCHEMA)
        self.assertEqual(report["candidate_archive_count"], 2)
        self.assertEqual(report["single_pass_original_imports_resolved"], 1)
        self.assertEqual(report["grouped_original_imports_resolved"], 1)
        self.assertEqual(report["single_pass_new_imports"], 1)
        self.assertEqual(report["grouped_new_imports"], 0)
        self.assertEqual(report["single_pass_final_strong_import_count"], 2)
        self.assertEqual(report["grouped_final_strong_import_count"], 1)
        self.assertEqual(report["group_minus_single_final_strong_imports"], -1)
        self.assertTrue(report["inputs_verified_unchanged_after_both_links"])
        self.assertFalse(report["fully_linked_game_executable"])
        self.assertFalse(report["original_map02_execution_proven"])
        self.assertEqual(parent.stat().st_mode & 0o777, 0o700)
        for dirname, hash_field in [
                ("single-pass", "single_pass_partial_elf_sha256"),
                ("grouped", "grouped_partial_elf_sha256")]:
            output_dir = parent / dirname
            output_file = output_dir / OUTPUT
            self.assertEqual(output_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(output_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(hashlib.sha256(output_file.read_bytes()).hexdigest(),
                             report[hash_field])
        for name in ("needed", "missing", "followup"):
            self.assertNotIn(name, json.dumps(report))

    def test_invalid_candidates_and_existing_parent_rejected(self):
        for label, candidates in [
                ("mixed", [self.first, self.provider]),
                ("only-one", [self.first]),
                ("no-archives", [self.provider, self.followup])]:
            target = self.root / label
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "2..64 native archive"):
                    comparison.compare_private_archive_strategies(
                        self.manifest, self.base, candidates, target)
                self.assertFalse(target.exists())
        exists = self.root / "already-there"
        exists.mkdir()
        sentinel = exists / "must-stay"
        sentinel.write_text("unaltered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            comparison.compare_private_archive_strategies(
                self.manifest, self.base, [self.second, self.first], exists)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "unaltered")

    def test_tampered_archive_between_links_blocks_second_result(self):
        original = comparison.probe_private_incremental_link
        invoked = []

        def mutate_after_first(*args, **kwargs):
            result = original(*args, **kwargs)
            invoked.append(result)
            with self.first.open("ab") as handle:
                handle.write(b"altered-after-one-pass")
            return result

        with mock.patch.object(
                comparison, "probe_private_incremental_link",
                side_effect=mutate_after_first):
            with self.assertRaisesRegex(ValueError, "changed during link"):
                comparison.compare_private_archive_strategies(
                    self.manifest, self.base, [self.second, self.first],
                    self.root / "tamper-block")
        self.assertEqual(len(invoked), 1)
        self.assertFalse((self.root / "tamper-block" / "grouped").exists())

    def test_mutated_manifest_between_links_is_rejected(self):
        original = comparison.probe_private_incremental_link

        def mutate_manifest_after_first(*args, **kwargs):
            result = original(*args, **kwargs)
            with self.manifest.open("ab") as handle:
                handle.write(b" ")
            return result

        with mock.patch.object(
                comparison, "probe_private_incremental_link",
                side_effect=mutate_manifest_after_first):
            with self.assertRaisesRegex(ValueError, "changed during link"):
                comparison.compare_private_archive_strategies(
                    self.manifest, self.base, [self.second, self.first],
                    self.root / "manifest-tamper")


if __name__ == "__main__":
    unittest.main()

"""Synthetic native-toolchain tests for an entirely private one-command MAP02 audit."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.check_map02_private_incremental_link import OUTPUT
from tools.run_map02_private_link_gap_audit import (
    SCHEMA, run_private_link_gap_audit,
)
from tools.verify_map02_private_archive_comparison import (
    verify_private_archive_comparison,
)


class OneShotPrivateMap02LinkGapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="vh-map02-one-shot-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        private = self.root / "manifest-dir"
        private.mkdir(mode=0o700)
        self.manifest = private / "imports.private.json"
        self.partial = self.compile(
            "original", "extern int needed(void); extern int missing(void);\n"
            "int root(void) { return needed() + missing(); }\n")
        self.partial.chmod(0o600)
        names = ["missing", "needed"]
        manifest = {
            "schema": "vh.map02.private-undefined-symbol-manifest.v1",
            "relocatable_elf_sha256":
                hashlib.sha256(self.partial.read_bytes()).hexdigest(),
            "partial_elf_unresolved_strong_symbol_count": len(names),
            "partial_elf_unresolved_weak_symbol_count": 0,
            "partial_elf_unresolved_strong_symbols_sha256":
                hashlib.sha256(json.dumps(
                    names, ensure_ascii=True,
                    separators=(",", ":")).encode("ascii")).hexdigest(),
            "strong_symbols": names,
            "weak_symbols": [],
        }
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        self.manifest.chmod(0o600)
        needs_followup = self.compile(
            "requires-followup", "extern int followup(void);\n"
            "int needed(void) { return followup(); }\n")
        supplies_followup = self.compile(
            "provides-followup", "int followup(void) { return 21; }\n")
        self.needs = self.archive("needs", needs_followup)
        self.supplies = self.archive("supplies", supplies_followup)
        self.archives = [self.supplies, self.needs]

    def compile(self, name, content):
        input_c = self.root / (name + ".c")
        input_c.write_text(content, encoding="utf-8")
        obj = self.root / (name + ".o")
        subprocess.run(
            ["cc", "-std=c99", "-fno-stack-protector", "-c",
             str(input_c), "-o", str(obj)],
            check=True, capture_output=True, timeout=30)
        return obj

    def archive(self, name, obj):
        output = self.root / (name + ".a")
        subprocess.run(
            ["ar", "rcs", str(output), str(obj)],
            check=True, capture_output=True, timeout=30)
        return output

    def test_one_command_creates_sealed_report_and_rechecked_elfs(self):
        root = self.root / "audit-output"
        actual = run_private_link_gap_audit(
            self.manifest, self.partial, self.archives, root)
        self.assertEqual(actual["schema"], SCHEMA)
        self.assertEqual(actual["initial_strong_import_count"], 2)
        self.assertEqual(actual["candidate_archive_count"], 2)
        self.assertEqual(actual["candidate_direct_object_count"], 0)
        self.assertFalse(actual["group_strategy_reorders_direct_objects_before_archives"])
        self.assertEqual(actual["single_pass_original_imports_resolved"], 1)
        self.assertEqual(actual["grouped_original_imports_resolved"], 1)
        self.assertEqual(actual["single_pass_final_strong_import_count"], 2)
        self.assertEqual(actual["grouped_final_strong_import_count"], 1)
        self.assertEqual(actual["group_minus_single_final_strong_imports"], -1)
        self.assertEqual(actual["single_pass_original_imports_remaining"], 1)
        self.assertEqual(actual["grouped_original_imports_remaining"], 1)
        self.assertEqual(actual["single_pass_new_strong_imports"], 1)
        self.assertEqual(actual["grouped_new_strong_imports"], 0)
        self.assertFalse(actual["expected_initial_import_count_confirmed"])
        for prefix in ("single_pass", "grouped"):
            self.assertEqual(
                actual[prefix + "_original_imports_remaining"]
                + actual[prefix + "_new_strong_imports"],
                actual[prefix + "_final_strong_import_count"])
        self.assertTrue(actual["owner_only_saved_report"])
        self.assertTrue(actual["independent_elf_and_count_audit_passed"])
        self.assertFalse(actual["fully_linked_game_executable"])
        self.assertFalse(actual["original_map02_execution_proven"])
        receipt = root / "receipts" / "paired.private.json"
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        for directory in (root, root / "receipts", root / "linked",
                          root / "linked" / "single-pass",
                          root / "linked" / "grouped"):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        for name in ("single-pass", "grouped"):
            path = root / "linked" / name / OUTPUT
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        check = verify_private_archive_comparison(
            self.manifest, self.partial, receipt, root / "linked")
        self.assertTrue(check["verified_report_arithmetic"])
        for private_name in ("needed", "missing", "followup"):
            self.assertNotIn(private_name, json.dumps(actual))

    def test_one_shot_mixed_direct_object_and_grouped_archives(self):
        """A non-archive provider must be included, counted and auditable."""
        direct = self.compile(
            "one-shot-direct", "extern int followup(void);\n"
            "int needed(void) { return followup(); }\n")
        followup = self.compile(
            "one-shot-provider", "extern int leaf(void);\n"
            "int followup(void) { return leaf(); }\n")
        leaf = self.compile("one-shot-leaf", "int leaf(void) {return 11;}\n")
        first = self.archive("one-shot-leaf-lib", leaf)
        second = self.archive("one-shot-provider-lib", followup)
        output = self.root / "mixed-one-shot"
        result = run_private_link_gap_audit(
            self.manifest, self.partial, [first, direct, second], output,
            expected_initial_strong_imports=2)
        self.assertEqual(result["candidate_archive_count"], 2)
        self.assertEqual(result["candidate_direct_object_count"], 1)
        self.assertTrue(
            result["group_strategy_reorders_direct_objects_before_archives"])
        self.assertEqual(result["single_pass_final_strong_import_count"], 2)
        self.assertEqual(result["grouped_final_strong_import_count"], 1)
        self.assertEqual(result["single_pass_new_strong_imports"], 1)
        self.assertEqual(result["grouped_new_strong_imports"], 0)
        self.assertTrue(result["independent_elf_and_count_audit_passed"])
        self.assertFalse(result["fully_linked_game_executable"])
        self.assertFalse(result["original_map02_execution_proven"])

    def test_bad_archive_set_rejected_before_creating_root(self):
        cases = [[self.needs], [self.needs, self.partial]]
        for idx, candidates in enumerate(cases):
            target = self.root / ("bad-" + str(idx))
            with self.subTest(idx=idx):
                with self.assertRaisesRegex(ValueError, "2..64 inputs and two archives"):
                    run_private_link_gap_audit(
                        self.manifest, self.partial, candidates, target)
                self.assertFalse(target.exists())

    def test_expected_initial_import_count_preflights_before_creating_output(self):
        """Reject a wrong claimed 520-like baseline before any I/O outputs."""
        wrong = self.root / "wrong-expected"
        with self.assertRaisesRegex(ValueError, "count differs"):
            run_private_link_gap_audit(
                self.manifest, self.partial, self.archives, wrong,
                expected_initial_strong_imports=520)
        self.assertFalse(wrong.exists())

        for malformed in (True, -1, "2"):
            target = self.root / ("bad-type-" + str(malformed))
            with self.subTest(value=malformed):
                with self.assertRaisesRegex(ValueError, "count differs"):
                    run_private_link_gap_audit(
                        self.manifest, self.partial, self.archives, target,
                        expected_initial_strong_imports=malformed)
                self.assertFalse(target.exists())

        matched = self.root / "matched-expected"
        report = run_private_link_gap_audit(
            self.manifest, self.partial, self.archives, matched,
            expected_initial_strong_imports=2)
        self.assertEqual(report["initial_strong_import_count"], 2)
        self.assertTrue(report["expected_initial_import_count_confirmed"])

    def test_cli_expected_baseline_failure_is_private_and_has_no_output(self):
        """Real CLI must reject a false baseline without printing raw symbols."""
        target = self.root / "cli-baseline-reject"
        run = subprocess.run(
            [sys.executable, "-m", "tools.run_map02_private_link_gap_audit",
             str(self.manifest), str(self.partial), str(target),
             *(str(x) for x in self.archives),
             "--expect-initial-strong-imports", "520"],
            text=True, capture_output=True, timeout=120)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(target.exists())
        for private_name in ("needed", "missing", "followup",
                             str(self.partial), str(self.manifest)):
            self.assertNotIn(private_name, run.stdout + run.stderr)

    def test_failure_to_reverify_never_claims_success(self):
        root = self.root / "failed-verification"
        with mock.patch(
                "tools.run_map02_private_link_gap_audit."
                "verify_private_archive_comparison",
                side_effect=ValueError("synthetic private verifier rejection")):
            with self.assertRaisesRegex(ValueError, "verifier rejection"):
                run_private_link_gap_audit(
                    self.manifest, self.partial, self.archives, root)
        self.assertEqual((root / "receipts").stat().st_mode & 0o777, 0o700)
        # A failed audit may retain forensic inputs, but cannot emit a
        # positive summary or overwrite them on a second run.
        with self.assertRaisesRegex(ValueError, "must not exist"):
            run_private_link_gap_audit(
                self.manifest, self.partial, self.archives, root)

    def test_cli_prints_only_safe_aggregate_numbers(self):
        target = self.root / "cli-outputs"
        result = subprocess.run(
            [sys.executable, "-m", "tools.run_map02_private_link_gap_audit",
             str(self.manifest), str(self.partial), str(target),
             *(str(x) for x in self.archives)],
            text=True, check=True, timeout=120, capture_output=True)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["initial_strong_import_count"], 2)
        self.assertTrue(doc["independent_elf_and_count_audit_passed"])
        for item in ("needed", "missing", "followup",
                     str(self.partial), str(self.manifest)):
            self.assertNotIn(item, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Real, synthetic GNU ld-r tests of single-pass-only private MAP02 audit."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools.check_map02_private_incremental_link import OUTPUT
from tools.run_map02_private_single_pass_gap_audit import (
    SCHEMA, audit_private_single_pass_gap,
)


class SinglePassOnlyGapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="vh-map02-direct-gap-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private = self.root / "owner-manifest"
        self.private.mkdir(mode=0o700)
        self.manifest = self.private / "original.private.json"
        self.original = self.compile(
            "original", "extern int needed(void); extern int missing(void);\n"
            "int root(void) { return needed() + missing(); }\n")
        self.original.chmod(0o600)
        initial = ["missing", "needed"]
        self.manifest.write_text(json.dumps({
            "schema": "vh.map02.private-undefined-symbol-manifest.v1",
            "relocatable_elf_sha256":
                hashlib.sha256(self.original.read_bytes()).hexdigest(),
            "partial_elf_unresolved_strong_symbol_count": 2,
            "partial_elf_unresolved_weak_symbol_count": 0,
            "partial_elf_unresolved_strong_symbols_sha256":
                hashlib.sha256(json.dumps(
                    initial, ensure_ascii=True,
                    separators=(",", ":")).encode("ascii")).hexdigest(),
            "strong_symbols": initial, "weak_symbols": [],
        }), encoding="utf-8")
        self.manifest.chmod(0o600)
        self.direct = self.compile(
            "direct-needed", "int needed(void) { return 16; }\n")
        self.needs_followup = self.compile(
            "archive-needed", "extern int followup(void);\n"
            "int needed(void) {return followup();}\n")
        self.archive = self.root / "only-one-lib.a"
        subprocess.run(["ar", "rcs", str(self.archive), str(self.needs_followup)],
                       check=True, capture_output=True, timeout=30)

    def compile(self, name, source):
        code = self.root / (name + ".c")
        code.write_text(source, encoding="utf-8")
        output = self.root / (name + ".o")
        subprocess.run(["cc", "-std=c99", "-fno-stack-protector", "-c",
                        str(code), "-o", str(output)],
                       check=True, capture_output=True, timeout=30)
        return output

    def test_direct_object_only_can_measure_actual_import_gap(self):
        directory = self.root / "one-direct"
        result = audit_private_single_pass_gap(
            self.manifest, self.original, [self.direct], directory,
            expected_initial_strong_imports=2, audit_strong_providers=True)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["initial_strong_import_count"], 2)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidate_archive_count"], 0)
        self.assertEqual(result["candidate_direct_object_count"], 1)
        self.assertEqual(result["original_strong_imports_resolved"], 1)
        self.assertEqual(result["original_strong_imports_remaining"], 1)
        self.assertEqual(result["new_strong_imports_introduced"], 0)
        self.assertEqual(result["final_strong_import_count"], 1)
        self.assertEqual(result["initial_imports_with_strong_provider_candidate"], 1)
        self.assertEqual(result["initial_imports_without_strong_provider_candidate"], 1)
        self.assertTrue(result["independent_single_output_elf_recount_passed"])
        self.assertTrue(result["inputs_verified_unchanged_across_audit_stages"])
        self.assertFalse(result["grouped_archive_rescan_performed"])
        self.assertFalse(result["fully_linked_game_executable"])
        self.assertFalse(result["original_map02_execution_proven"])
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((directory / OUTPUT).stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            hashlib.sha256((directory / OUTPUT).read_bytes()).hexdigest(),
            result["linked_partial_elf_sha256"])
        for name in ("needed", "missing", "followup", str(self.original)):
            self.assertNotIn(name, json.dumps(result))

    def test_one_archive_alone_reports_introduced_dependency(self):
        result = audit_private_single_pass_gap(
            self.manifest, self.original, [self.archive],
            self.root / "single-archive")
        self.assertEqual(result["candidate_archive_count"], 1)
        self.assertEqual(result["candidate_direct_object_count"], 0)
        self.assertEqual(result["original_strong_imports_resolved"], 1)
        self.assertEqual(result["original_strong_imports_remaining"], 1)
        self.assertEqual(result["new_strong_imports_introduced"], 1)
        self.assertEqual(result["final_strong_import_count"], 2)
        self.assertFalse(result["candidate_strong_provider_coverage_checked"])

    def test_wrong_baseline_and_no_candidates_fail_before_any_output(self):
        wrong = self.root / "wrong-baseline"
        with self.assertRaisesRegex(ValueError, "count differs"):
            audit_private_single_pass_gap(
                self.manifest, self.original, [self.direct], wrong,
                expected_initial_strong_imports=520)
        self.assertFalse(wrong.exists())
        empty = self.root / "empty"
        with self.assertRaisesRegex(ValueError, "1..64"):
            audit_private_single_pass_gap(
                self.manifest, self.original, [], empty)
        self.assertFalse(empty.exists())

    def test_corrupted_result_after_ld_fails_independent_recheck(self):
        from tools import run_map02_private_single_pass_gap_audit as module
        native = module.probe_private_incremental_link
        output = self.root / "tampered-after-link"

        def corrupt(*args, **kwargs):
            report = native(*args, **kwargs)
            with (output / OUTPUT).open("ab") as handle:
                handle.write(b"tampered-linked-output")
            return report

        with mock.patch.object(module, "probe_private_incremental_link",
                               side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "independent ELF audit differs"):
                audit_private_single_pass_gap(
                    self.manifest, self.original, [self.direct], output)

    def test_input_mutation_after_ld_cannot_claim_success(self):
        from tools import run_map02_private_single_pass_gap_audit as module
        native = module.probe_private_incremental_link
        output = self.root / "changed-source"

        def corrupt_input(*args, **kwargs):
            report = native(*args, **kwargs)
            with self.direct.open("ab") as handle:
                handle.write(b"changed-provider")
            return report

        with mock.patch.object(module, "probe_private_incremental_link",
                               side_effect=corrupt_input):
            with self.assertRaisesRegex(ValueError, "changed during link"):
                audit_private_single_pass_gap(
                    self.manifest, self.original, [self.direct], output)

    def test_duplicate_inode_cannot_fake_two_candidates(self):
        output = self.root / "duplicated-provider"
        with self.assertRaisesRegex(ValueError, "inode repeated"):
            audit_private_single_pass_gap(
                self.manifest, self.original, [self.direct, self.direct], output)
        self.assertFalse(output.exists())

    def test_real_cli_direct_only_hides_private_names(self):
        output = self.root / "native-cli"
        response = subprocess.run([
            sys.executable, "-m", "tools.run_map02_private_single_pass_gap_audit",
            str(self.manifest), str(self.original), str(output),
            str(self.direct), "--expect-initial-strong-imports", "2",
            "--audit-strong-provider-coverage"],
            check=True, capture_output=True, text=True, timeout=120)
        result = json.loads(response.stdout)
        self.assertEqual(result["candidate_archive_count"], 0)
        self.assertEqual(result["final_strong_import_count"], 1)
        for secret in ("needed", "missing", str(self.manifest), str(self.original)):
            self.assertNotIn(secret, response.stdout + response.stderr)


if __name__ == "__main__":
    unittest.main()

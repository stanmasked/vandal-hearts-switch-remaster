"""Synthetic native ELF-only regressions; never ingest original game resources."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_map02_private_archive_strategy_compare import (
    compare_private_archive_strategies,
)
from tools.verify_map02_private_archive_comparison import (
    VERIFY_SCHEMA, verify_private_archive_comparison,
)
from tools.check_map02_private_incremental_link import OUTPUT


class IndependentPairedAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="map02-independent-verify-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        owner = self.root / "owned"
        owner.mkdir(mode=0o700)
        self.manifest = owner / "imports.private.json"
        self.partial = self.compile(
            "base", "extern int needed(void); extern int missing(void);\n"
            "int root(void) { return needed() + missing(); }\n")
        self.partial.chmod(0o600)
        strong = ["missing", "needed"]
        self.manifest.write_text(json.dumps({
            "schema": "vh.map02.private-undefined-symbol-manifest.v1",
            "relocatable_elf_sha256":
                hashlib.sha256(self.partial.read_bytes()).hexdigest(),
            "partial_elf_unresolved_strong_symbol_count": len(strong),
            "partial_elf_unresolved_weak_symbol_count": 0,
            "partial_elf_unresolved_strong_symbols_sha256":
                hashlib.sha256(json.dumps(
                    strong, ensure_ascii=True,
                    separators=(",", ":")).encode("ascii")).hexdigest(),
            "strong_symbols": strong, "weak_symbols": [],
        }), encoding="utf-8")
        self.manifest.chmod(0o600)
        first = self.compile(
            "provider", "extern int followup(void);\n"
            "int needed(void) {return followup();}\n")
        second = self.compile("followup", "int followup(void) {return 42;}\n")
        self.first = self.archive("first", first)
        self.second = self.archive("second", second)
        self.output_root = self.root / "outputs"
        summary = compare_private_archive_strategies(
            self.manifest, self.partial, [self.second, self.first],
            self.output_root)
        self.report_dir = self.root / "reports"
        self.report_dir.mkdir(mode=0o700)
        self.report = self.report_dir / "paired.private.json"
        self.write_report(summary)

    def compile(self, stem, code):
        source = self.root / (stem + ".c")
        source.write_text(code, encoding="utf-8")
        output = self.root / (stem + ".o")
        subprocess.run(["cc", "-std=c99", "-fno-stack-protector", "-c",
                        str(source), "-o", str(output)],
                       check=True, timeout=30, capture_output=True)
        return output

    def archive(self, stem, obj):
        dest = self.root / (stem + ".a")
        subprocess.run(["ar", "rcs", str(dest), str(obj)],
                       check=True, timeout=30, capture_output=True)
        return dest

    def write_report(self, data):
        self.report.write_text(json.dumps(data, sort_keys=True, indent=2),
                               encoding="utf-8")
        self.report.chmod(0o600)

    def verify(self):
        return verify_private_archive_comparison(
            self.manifest, self.partial, self.report, self.output_root)

    def test_valid_saved_report_rechecked_against_both_actual_elf_files(self):
        status = self.verify()
        self.assertEqual(status["schema"], VERIFY_SCHEMA)
        self.assertEqual(status["candidate_archive_count"], 2)
        self.assertEqual(status["single_pass_remaining_strong_imports"], 2)
        self.assertEqual(status["grouped_remaining_strong_imports"], 1)
        self.assertTrue(status["verified_both_output_elf_files"])
        self.assertTrue(status["verified_report_arithmetic"])
        self.assertFalse(status["link_invocation_independently_attested"])
        for name in ("needed", "missing", "followup"):
            self.assertNotIn(name, json.dumps(status))

    def test_changed_group_elf_blocks_report_verification(self):
        output = self.output_root / "grouped" / OUTPUT
        with output.open("ab") as stream:
            stream.write(b"untrusted-final-output")
        with self.assertRaisesRegex(ValueError, "evidence mismatch"):
            self.verify()

    def test_forged_count_rejected_despite_valid_output_digests(self):
        data = json.loads(self.report.read_text(encoding="utf-8"))
        data["grouped_new_imports"] += 1
        self.write_report(data)
        with self.assertRaisesRegex(ValueError, "evidence mismatch"):
            self.verify()

    def test_forged_delta_is_not_accepted(self):
        data = json.loads(self.report.read_text(encoding="utf-8"))
        data["group_minus_single_final_strong_imports"] = 0
        self.write_report(data)
        with self.assertRaisesRegex(ValueError, "delta inconsistent"):
            self.verify()

    def test_duplicate_json_key_and_false_gameplay_evidence_rejected(self):
        text = self.report.read_text(encoding="utf-8")
        self.report.write_text(text.replace(
            '"schema":', '"schema": "forged", "schema":', 1),
            encoding="utf-8")
        self.report.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "JSON invalid"):
            self.verify()
        data = json.loads(text)
        data["original_map02_execution_proven"] = True
        self.write_report(data)
        with self.assertRaisesRegex(ValueError, "evidence flags invalid"):
            self.verify()

    def test_symlinked_grouped_directory_is_refused(self):
        grouped = self.output_root / "grouped"
        moved = self.root / "moved-real"
        grouped.rename(moved)
        grouped.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "folder metadata unsafe"):
            self.verify()


if __name__ == "__main__":
    unittest.main()

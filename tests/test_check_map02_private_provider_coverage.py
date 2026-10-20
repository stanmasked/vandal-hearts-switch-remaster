"""Asset-free native compiler tests for private MAP02 ELF candidate coverage."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_map02_private_provider_coverage import (
    audit_provider_coverage, read_private_manifest,
)


class LocalProviderCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-providers-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "private-output"
        self.private.mkdir(mode=0o700)
        self.manifest = self.private / "map02-unresolved-symbols.private.json"
        self.strong = ["alpha", "beta", "unfound"]
        digest = hashlib.sha256(json.dumps(
            self.strong, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")).hexdigest()
        self.doc = {
            "schema": "vh.map02.private-undefined-symbol-manifest.v1",
            "relocatable_elf_sha256": "c" * 64,
            "partial_elf_unresolved_strong_symbol_count": 3,
            "partial_elf_unresolved_weak_symbol_count": 0,
            "partial_elf_unresolved_strong_symbols_sha256": digest,
            "strong_symbols": self.strong,
            "weak_symbols": [],
        }
        self.save()

    def save(self):
        self.manifest.write_text(
            json.dumps(self.doc, sort_keys=True), encoding="utf-8")
        self.manifest.chmod(0o600)

    def compile(self, name, source):
        path = self.root / (name + ".c")
        path.write_text(source, encoding="utf-8")
        obj = self.root / (name + ".o")
        subprocess.run(
            ["cc", "-std=c99", "-c", str(path), "-o", str(obj)],
            check=True, capture_output=True, timeout=30)
        return obj

    def test_real_object_and_archive_report_unique_and_ambiguous_coverage(self):
        alpha = self.compile("provider-alpha", "void alpha(void) {}\n")
        beta = self.compile("provider-beta", "void beta(void) {}\n")
        archive = self.root / "candidate-lib.a"
        subprocess.run(
            ["ar", "rcs", str(archive), str(alpha), str(beta)],
            check=True, capture_output=True, timeout=30)
        report = audit_provider_coverage(self.manifest, [alpha, archive])
        self.assertEqual(report["original_strong_unresolved_count"], 3)
        self.assertEqual(report["candidate_provider_file_count"], 2)
        self.assertEqual(report["strong_symbols_with_candidate_provider"], 2)
        self.assertEqual(report["strong_symbols_with_multiple_candidates"], 1)
        self.assertEqual(report["strong_symbols_without_candidate_provider"], 1)
        self.assertFalse(report["candidate_resolves_full_game_link"])
        self.assertFalse(report["original_map02_execution_proven"])
        for name in self.strong:
            self.assertNotIn(name, json.dumps(report))

    def test_weak_or_common_export_does_not_claim_strong_definition(self):
        weak = self.compile(
            "only-weak", "__attribute__((weak)) void unfound(void) {}\n")
        report = audit_provider_coverage(self.manifest, [weak])
        self.assertEqual(report["strong_symbols_with_candidate_provider"], 0)
        self.assertEqual(report["strong_symbols_without_candidate_provider"], 3)

    def test_corrupt_sha_or_unsorted_names_rejected_before_inspection(self):
        self.doc["partial_elf_unresolved_strong_symbols_sha256"] = "0" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "digest/count mismatch"):
            read_private_manifest(self.manifest)
        self.doc["partial_elf_unresolved_strong_symbols_sha256"] = (
            hashlib.sha256(json.dumps(self.strong, separators=(",", ":")
                                 ).encode()).hexdigest())
        self.doc["strong_symbols"] = list(reversed(self.strong))
        self.save()
        with self.assertRaisesRegex(ValueError, "symbol names invalid"):
            read_private_manifest(self.manifest)

    def test_manifest_public_mode_and_provider_links_fail_closed(self):
        alpha = self.compile("unsafe-alpha", "void alpha(void) {}\n")
        self.manifest.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "metadata unsafe"):
            audit_provider_coverage(self.manifest, [alpha])
        self.manifest.chmod(0o600)
        alias = self.root / "linked-provider.o"
        alias.symlink_to(alpha)
        with self.assertRaisesRegex(ValueError, "provider input unavailable"):
            audit_provider_coverage(self.manifest, [alias])

    def test_invalid_candidate_not_mistaken_for_linked_symbol(self):
        fake = self.root / "broken.o"
        fake.write_bytes(b"not an ELF object")
        with self.assertRaisesRegex(ValueError, "symbol inspection failed"):
            audit_provider_coverage(self.manifest, [fake])
        with self.assertRaisesRegex(ValueError, "candidate list is empty"):
            audit_provider_coverage(self.manifest, [])


if __name__ == "__main__":
    unittest.main()

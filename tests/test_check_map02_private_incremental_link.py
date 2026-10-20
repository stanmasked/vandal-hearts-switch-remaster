"""Real Linux GNU ld -r smoke tests with synthetic native C objects only.

Never pass retail game data or proprietary assets to these tests.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.check_map02_private_incremental_link import (
    OUTPUT, _run_native_tool, probe_private_incremental_link,
)


class NativeIncrementalRelinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-ld-proof-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / "source-receipt"
        self.private.mkdir(mode=0o700)
        self.manifest = self.private / "map02-unresolved-symbols.private.json"
        self.base = self.compile(
            "base",
            "extern int needed(void); extern int missing(void);\n"
            "int root(void) { return needed() + missing(); }\n")
        self.base.chmod(0o600)
        self.initial = ["missing", "needed"]
        self.doc = {
            "schema": "vh.map02.private-undefined-symbol-manifest.v1",
            "relocatable_elf_sha256": hashlib.sha256(
                self.base.read_bytes()).hexdigest(),
            "partial_elf_unresolved_strong_symbol_count": 2,
            "partial_elf_unresolved_weak_symbol_count": 0,
            "partial_elf_unresolved_strong_symbols_sha256": hashlib.sha256(
                json.dumps(self.initial, ensure_ascii=True,
                           separators=(",", ":")).encode("ascii")).hexdigest(),
            "strong_symbols": self.initial,
            "weak_symbols": [],
        }
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.doc), encoding="utf-8")
        self.manifest.chmod(0o600)

    def compile(self, name, code):
        source = self.root / (name + ".c")
        source.write_text(code, encoding="utf-8")
        dest = self.root / (name + ".o")
        subprocess.run(
            ["cc", "-std=c99", "-fno-stack-protector", "-c", str(source),
             "-o", str(dest)],
            check=True, capture_output=True, timeout=30)
        return dest

    def archive(self, name, *objects):
        dest = self.root / (name + ".a")
        subprocess.run(
            ["ar", "rcs", str(dest), *(str(x) for x in objects)],
            check=True, capture_output=True, timeout=30)
        return dest

    def test_real_archive_link_resolves_one_import_and_adds_another(self):
        provider = self.compile(
            "provider", "extern int followup(void);\n"
            "int needed(void) { return followup(); }\n")
        archive = self.archive("provider", provider)
        report = probe_private_incremental_link(
            self.manifest, self.base, [archive], self.root / "output")
        self.assertEqual(report["original_strong_import_count"], 2)
        self.assertEqual(report["original_strong_imports_resolved_by_ld_r"], 1)
        self.assertEqual(report["original_strong_imports_remaining_after_ld_r"], 1)
        self.assertEqual(report["new_strong_imports_introduced_by_candidates"], 1)
        self.assertEqual(report["final_strong_import_count"], 2)
        self.assertEqual(report["candidate_count"], 1)
        self.assertFalse(report["fully_linked_game_executable"])
        self.assertFalse(report["original_map02_execution_proven"])
        output = self.root / "output"
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        file = output / OUTPUT
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            hashlib.sha256(file.read_bytes()).hexdigest(),
            report["linked_candidate_elf_sha256"])
        for name in ("missing", "needed", "followup"):
            self.assertNotIn(name, json.dumps(report))

    def test_direct_object_removes_required_import_without_new_ones(self):
        provider = self.compile("needed-direct", "int needed(void) {return 42;}\n")
        report = probe_private_incremental_link(
            self.manifest, self.base, [provider], self.root / "direct")
        self.assertEqual(report["original_strong_imports_resolved_by_ld_r"], 1)
        self.assertEqual(report["original_strong_imports_remaining_after_ld_r"], 1)
        self.assertEqual(report["new_strong_imports_introduced_by_candidates"], 0)
        self.assertEqual(report["final_strong_import_count"], 1)

    def test_mismatched_source_sha_and_existing_output_fail_before_ld(self):
        provider = self.compile("provider", "int needed(void) {return 1;}\n")
        self.doc["relocatable_elf_sha256"] = "0" * 64
        self.write_manifest()
        output = self.root / "do-not-create"
        with self.assertRaisesRegex(ValueError, "hash differs"):
            probe_private_incremental_link(self.manifest, self.base,
                                           [provider], output)
        self.assertFalse(output.exists())
        self.doc["relocatable_elf_sha256"] = hashlib.sha256(
            self.base.read_bytes()).hexdigest()
        self.write_manifest()
        output.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "must not exist"):
            probe_private_incremental_link(self.manifest, self.base,
                                           [provider], output)

    def test_elf32_provider_is_rejected_before_running_link(self):
        source = self.root / "foreign.s"
        source.write_text(".globl needed\nneeded:\n ret\n", encoding="ascii")
        target = self.root / "foreign.o"
        subprocess.run(
            ["as", "--32", str(source), "-o", str(target)],
            check=True, capture_output=True, timeout=30)
        output = self.root / "reject-foreign"
        with self.assertRaisesRegex(ValueError, "incompatible PC ELF ABI"):
            probe_private_incremental_link(
                self.manifest, self.base, [target], output)
        self.assertFalse(output.exists())

    def test_duplicate_definition_does_not_claim_linked_result(self):
        provider = self.compile("duplicate-root", "int root(void) {return 99;}\n")
        with self.assertRaisesRegex(ValueError, "native linker tool failed"):
            probe_private_incremental_link(
                self.manifest, self.base, [provider], self.root / "duplicate")

    def test_unsafe_partial_mode_or_symlink_rejected_without_new_output(self):
        provider = self.compile("good", "int needed(void) {return 10;}\n")
        self.base.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "metadata unsafe"):
            probe_private_incremental_link(
                self.manifest, self.base, [provider], self.root / "unsafe")
        self.base.chmod(0o600)
        linked = self.root / "substitute.o"
        linked.symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, "object inaccessible"):
            probe_private_incremental_link(
                self.manifest, linked, [provider], self.root / "linked")


    def test_native_tools_do_not_inherit_dynamic_loader_hooks(self):
        """No caller-controlled native loader/Python hooks see private objects."""
        danger = {
            "LD_PRELOAD": "/owner/fake-preload.so",
            "LD_LIBRARY_PATH": "/owner/other-libs",
            "LD_AUDIT": "/owner/fake-audit.so",
            "DYLD_INSERT_LIBRARIES": "/owner/fake-dylib",
            "PYTHONPATH": "/owner/private-python",
            "VH_PSX_EXE": "/owner/retail/SLUS_004.47",
        }
        with mock.patch.dict(os.environ, danger):
            with mock.patch(
                "tools.check_map02_private_incremental_link.subprocess.run"
            ) as execute:
                execute.return_value = subprocess.CompletedProcess(
                    ["ld", "--version"], 0, stdout="GNU ld")
                self.assertEqual(
                    _run_native_tool(["ld", "--version"], [], timeout=10),
                    "GNU ld")
                subprocess_env = execute.call_args.kwargs["env"]
                for name in danger:
                    self.assertNotIn(name, subprocess_env)
                self.assertEqual(subprocess_env.get("PATH"),
                                 os.environ.get("PATH"))
                self.assertEqual(execute.call_args.kwargs["umask"], 0o077)

    def test_repeated_input_inode_rejected_before_link(self):
        """Repeated archives must not inflate candidate counts in reports."""
        provider = self.compile("one-archive-member", "int needed(void) {return 5;}\n")
        archive = self.archive("one-provider", provider)
        out = self.root / "reject-repeated"
        with self.assertRaisesRegex(ValueError, "input repeated"):
            probe_private_incremental_link(
                self.manifest, self.base, [archive, archive], out)
        self.assertFalse(out.exists())

    def test_original_partial_cannot_be_reused_as_candidate(self):
        """Do not quietly link the same base ELF twice."""
        out = self.root / "reject-base"
        with self.assertRaisesRegex(ValueError, "input repeated"):
            probe_private_incremental_link(
                self.manifest, self.base, [self.base], out)
        self.assertFalse(out.exists())

    def test_mutated_candidate_during_real_ld_r_is_rejected(self):
        """The final rehash must catch same-inode provider tampering."""
        from tools import check_map02_private_incremental_link as module

        provider = self.compile("late-provider", "int needed(void) {return 7;}\n")
        original_run = module._run_native_tool

        def alter_after_link(args, descriptors, **kwargs):
            result = original_run(args, descriptors, **kwargs)
            if args[0] == "ld" and "-r" in args:
                with provider.open("ab") as changed:
                    changed.write(b"tampered-after-link")
            return result

        with mock.patch.object(module, "_run_native_tool",
                               side_effect=alter_after_link):
            with self.assertRaisesRegex(ValueError, "changed during link"):
                probe_private_incremental_link(
                    self.manifest, self.base, [provider],
                    self.root / "late-mutation")

if __name__ == "__main__":
    unittest.main()

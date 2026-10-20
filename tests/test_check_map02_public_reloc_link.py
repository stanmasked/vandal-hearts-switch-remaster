"""Host-toolchain regressions for asset-free MAP02 native partial-ELF link.

Source fixtures are tiny, independent synthetic C snippets. These tests do
NOT link actual game resources or claim to run original MAP02.
"""
from contextlib import redirect_stderr
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.check_map02_public_reloc_link import (
    REQUIRED_SYMBOLS, inspect_relocatable, make_inventory, main,
    stable_relocatable_output,
)


class PublicRelocatableELFTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-reloc-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def compile(self, data, name="fixture", *, shared=False):
        src = self.root / (name + ".c")
        obj = self.root / (name + (".so" if shared else ".o"))
        src.write_text(data, encoding="utf-8")
        cmd = ["cc", "-std=c99", "-fPIC", str(src)]
        if shared:
            cmd += ["-shared"]
        else:
            cmd += ["-c"]
        subprocess.run(
            [*cmd, "-o", str(obj)], check=True, capture_output=True,
            text=True, timeout=30)
        return obj

    def all_exports(self):
        return "\n".join(
            f"void {name}(void) {{}}" for name in REQUIRED_SYMBOLS)

    def test_real_ld_r_proves_all_expected_exports_but_not_full_elf(self):
        names = list(REQUIRED_SYMBOLS)
        left = self.compile(
            "\n".join(f"void {name}(void) {{}}" for name in names[:5]),
            "cdside")
        right = self.compile(
            "\n".join(f"void {name}(void) {{}}" for name in names[5:]),
            "gpuside")
        combined = self.root / "combined.o"
        subprocess.run(["ld", "-r", "-o", str(combined), str(left),
                        str(right)], check=True, capture_output=True,
                       text=True, timeout=30)
        report = inspect_relocatable(combined)
        self.assertEqual(report["original_cd_gpu_and_vram_exports_verified"],
                         len(REQUIRED_SYMBOLS))
        self.assertTrue(
            report["ordinary_game_or_private_asset_symbols_may_be_unresolved"])

    def test_missing_cd_gpu_or_capture_export_rejected(self):
        missing = REQUIRED_SYMBOLS[-1]
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != missing))
        with self.assertRaisesRegex(ValueError, "export absent"):
            inspect_relocatable(obj)

    def test_global_data_cannot_impersonate_original_code_export(self):
        impostor = REQUIRED_SYMBOLS[0]
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != impostor) +
            f"\nint {impostor} = 1;\n")
        with self.assertRaisesRegex(ValueError, "strong code export"):
            inspect_relocatable(obj)

    def test_weak_function_cannot_impersonate_original_code_export(self):
        impostor = REQUIRED_SYMBOLS[-1]
        obj = self.compile(
            "\n".join(f"void {name}(void) {{}}"
                      for name in REQUIRED_SYMBOLS if name != impostor) +
            f"\nvoid {impostor}(void) __attribute__((weak));\n"
            f"void {impostor}(void) {{}}\n")
        with self.assertRaisesRegex(ValueError, "strong code export"):
            inspect_relocatable(obj)

    def test_unresolved_capture_hook_rejected_even_if_other_exports_present(self):
        obj = self.compile(
            self.all_exports() +
            "\nextern void vh_map02_unresolved_callback(void);\n"
            "void call_unverified_probe(void) { vh_map02_unresolved_callback(); }")
        with self.assertRaisesRegex(ValueError, "unresolved MAP02 observer"):
            inspect_relocatable(obj)

    def test_complete_shared_object_cannot_impersonate_relocatable_evidence(self):
        obj = self.compile(self.all_exports(), shared=True)
        with self.assertRaisesRegex(ValueError, "relocatable ELF"):
            inspect_relocatable(obj)

    def test_non_elf_rejected(self):
        invalid = self.root / "not-an-ELF"
        invalid.write_bytes(b"invalid-original-code")
        with self.assertRaisesRegex(ValueError, "relocatable ELF"):
            inspect_relocatable(invalid)

    def test_partial_elf_double_read_proof_is_stable(self):
        obj = self.compile(self.all_exports(), name="stable")
        obj.chmod(0o600)
        proof = stable_relocatable_output(obj)
        self.assertEqual(proof[0], hashlib.sha256(obj.read_bytes()).hexdigest())
        self.assertEqual(stable_relocatable_output(obj, expected=proof), proof)

    def test_partial_elf_rejects_world_readable_symlink_and_hardlink(self):
        obj = self.compile(self.all_exports(), name="untrusted")
        with self.assertRaisesRegex(ValueError, "metadata"):
            stable_relocatable_output(obj)
        obj.chmod(0o600)
        symlink = self.root / "partial-symlink.o"
        symlink.symlink_to(obj)
        with self.assertRaises((ValueError, OSError)):
            stable_relocatable_output(symlink)
        hardlink = self.root / "partial-hardlink.o"
        os.link(obj, hardlink)
        with self.assertRaisesRegex(ValueError, "metadata"):
            stable_relocatable_output(obj)

    def test_partial_elf_rejects_identical_bytes_different_inode(self):
        obj = self.compile(self.all_exports(), name="original")
        obj.chmod(0o600)
        proof = stable_relocatable_output(obj)
        replacement = self.root / "same-bytes-different-inode.o"
        replacement.write_bytes(obj.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, obj)
        with self.assertRaisesRegex(ValueError, "differs from linked proof"):
            stable_relocatable_output(obj, expected=proof)

    def test_partial_elf_rejects_path_swap_during_descriptor_read(self):
        obj = self.compile(self.all_exports(), name="during-read")
        obj.chmod(0o600)
        replacement = self.root / "swapped.o"
        replacement.write_bytes(obj.read_bytes())
        replacement.chmod(0o600)
        original_read = os.read
        swapped = False

        def read_and_swap(fd, count):
            nonlocal swapped
            data = original_read(fd, count)
            if data and not swapped:
                swapped = True
                os.replace(replacement, obj)
            return data

        with patch("tools.check_map02_public_reloc_link.os.read",
                   side_effect=read_and_swap):
            with self.assertRaisesRegex(ValueError, "inode or metadata changed"):
                stable_relocatable_output(obj)
        self.assertTrue(swapped)

    def test_make_inventory_ignores_inherited_untrusted_makefile(self):
        # Only tiny synthetic inventories are evaluated. A caller-supplied
        # MAKEFILES script must never run during the audit's GNU Make read.
        upstream = self.root / "upstream"
        pc = upstream / "platform" / "pc"
        pc.mkdir(parents=True)
        bundle = self.root / "private-bundle"
        bundle.mkdir()
        (pc / "Makefile").write_text(
            "VH_MAP02_PUBLIC_CODE_OBJS := build-map02-cycle/game.o\n"
            "VH_MAP02_PUBLIC_BACKEND_OBJS := build-map02-cycle/gpu.o\n",
            encoding="utf-8")
        (bundle / "map02_cycle.mk").write_text(
            "# Synthetic opt-in overlay\n", encoding="utf-8")
        hostile = self.root / "unexpected-makefile"
        hostile.write_text(
            "$(shell touch untrusted-makefile-parsed)\n", encoding="utf-8")
        marker = pc / "untrusted-makefile-parsed"
        injected = {
            "MAKEFILES": str(hostile),
            "MAKEFLAGS": "--no-print-directory",
            "PYTHONPATH": str(self.root / "foreign-python"),
        }
        with patch.dict(os.environ, injected):
            result = make_inventory(upstream, bundle)
        self.assertEqual(result, [
            ["build-map02-cycle/game.o"], ["build-map02-cycle/gpu.o"]])
        self.assertFalse(marker.exists())

    def test_cli_redacts_filesystem_paths_and_linker_errors(self):
        private_path = str(self.root / "owned-original-private-psx-image")
        arguments = [
            "check_map02_public_reloc_link", "pinned-upstream",
            "private-bundle", "new-partial-output"]
        for failure in (
                OSError("private file: " + private_path),
                subprocess.TimeoutExpired(["ld", private_path], 30),
                ValueError("ld stderr included " + private_path)):
            output = io.StringIO()
            with patch("sys.argv", arguments), patch(
                    "tools.check_map02_public_reloc_link.audit_public_link",
                    side_effect=failure), redirect_stderr(output):
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 2)
            self.assertNotIn(private_path, output.getvalue())
            self.assertIn("public relocatable audit failed", output.getvalue())


if __name__ == "__main__":
    unittest.main()

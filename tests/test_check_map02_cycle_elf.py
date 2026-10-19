"""Real host ELF structural tests for the opt-in full MAP02 cycle gate.

The positive fixture is a synthetic symbol-only ELF, NOT original source,
not a game, and not a claim of actual hooks being executed. The fixture
proves only the scope and fail-closed behavior of the structural audit.
"""
import os
from contextlib import redirect_stderr
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import tools.check_map02_cycle_elf as elf

from tools.check_map02_cycle_elf import (
    SYMBOLS, ORIGINAL_FONT_DATA_SYMBOLS, audit_cycle_elf)


class OriginalCycleElfAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vh-cycle-elf-")
        cls.root = Path(cls.temp.name)
        source = cls.root / "fixture.c"
        source.write_text(
            "/* Synthetic names, NO original game/observer implementation */\n"
            + "\n".join("void " + sym + "(void) {}" for sym in SYMBOLS)
            + "\nconst unsigned char pc_kanji_charset2[6270] = {1};\n"
            + "int main(void) { return 0; }\n", encoding="utf-8")
        cls.executable = cls.root / "symbols-only"
        built = subprocess.run(
            ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
             str(source), "-o", str(cls.executable)],
            capture_output=True, text=True, timeout=30)
        if built.returncode:
            raise AssertionError(built.stderr)
        cls.object = cls.root / "symbols-only.o"
        obj = subprocess.run(
            ["cc", "-c", str(source), "-o", str(cls.object)],
            capture_output=True, text=True, timeout=30)
        if obj.returncode:
            raise AssertionError(obj.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_full_executable_with_all_names_is_structurally_accepted_only(self):
        result = audit_cycle_elf(self.executable)
        self.assertEqual(result["required_symbols_present"], len(SYMBOLS))
        self.assertEqual(
            result["original_us_font_initialized_data_symbols_present"],
            len(ORIGINAL_FONT_DATA_SYMBOLS))
        self.assertFalse(result["original_gameplay_authenticated"])
        self.assertFalse(result["original_map02_rendering_proven"])
        self.assertFalse(result["physical_ps1_equivalence_proven"])

    def test_entry_must_be_mapped_by_executable_file_backed_segment(self):
        # Use the compiled host ELF rather than invented symbol-table text.
        # Redirect only the ELF entry point to an unmapped virtual address.
        source = self.executable.read_bytes()
        wrong = self.root / "entry-unmapped"
        modified = bytearray(source)
        if modified[4] == 2:  # ELFCLASS64
            modified[24:32] = (0xfffffffffffff000).to_bytes(8, "little")
        elif modified[4] == 1:  # ELFCLASS32
            modified[24:28] = (0xfffff000).to_bytes(4, "little")
        else:
            self.fail("synthetic compiler generated an unrecognized ELF class")
        wrong.write_bytes(modified)
        wrong.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "entry is not in executable"):
            audit_cycle_elf(wrong)

    def test_elf_load_map_checks_file_bounds_and_executable_flags(self):
        load = elf._require_entry_in_executable_load
        valid = "  LOAD 0x001000 0x00004000 0x00004000 0x000030 0x000040 R E 0x1000"
        load(valid, 0x4010, 0x5000)
        cases = (
            (valid, 0x4030, 0x5000, "entry is not in executable"),
            (valid.replace("R E", "RW"), 0x4010, 0x5000,
             "entry is not in executable"),
            (valid.replace("0x000030 0x000040", "0x000050 0x000040"),
             0x4010, 0x5000, "invalid executable load extent"),
            (valid, 0x4010, 0x1010, "invalid executable load extent"),
            ("  LOAD incomplete", 0x4010, 0x5000,
             "malformed load program headers"),
            ("", 0x4010, 0x5000, "entry is not in executable"),
        )
        for raw, entry, size, error in cases:
            with self.subTest(case=error, entry=entry, file_size=size):
                with self.assertRaisesRegex(ValueError, error):
                    load(raw, entry, size)

    def test_native_introspection_timeout_redacts_private_elf_path(self):
        private = str(self.executable)
        timeout = subprocess.TimeoutExpired(
            ["readelf", "-h", private], 30, output=private.encode())
        with patch.object(elf.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(ValueError, "introspection unavailable") as caught:
                audit_cycle_elf(self.executable)
        self.assertNotIn(private, str(caught.exception))

    def test_native_introspection_os_error_redacts_private_elf_path(self):
        private = str(self.executable)
        with patch.object(elf.subprocess, "run",
                          side_effect=OSError("cannot open " + private)):
            with self.assertRaisesRegex(ValueError, "introspection unavailable") as caught:
                audit_cycle_elf(self.executable)
        self.assertNotIn(private, str(caught.exception))

    def test_cli_redacts_unexpected_private_executable_timeouts(self):
        private = str(self.executable)
        for failure in (
            OSError("private executable " + private),
            subprocess.TimeoutExpired(["nm", private], 30),
        ):
            with self.subTest(reason=type(failure).__name__):
                stderr = io.StringIO()
                with (patch("sys.argv", ["audit-cycle-elf", private]),
                      patch.object(elf, "audit_cycle_elf", side_effect=failure),
                      redirect_stderr(stderr)):
                    with self.assertRaises(SystemExit) as caught:
                        elf.main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("filesystem introspection unavailable",
                              stderr.getvalue())
                self.assertNotIn(private, stderr.getvalue())

    def test_partial_link_cannot_pass_as_executable(self):
        self.object.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "fully linked ELF"):
            audit_cycle_elf(self.object)

    def test_uninstrumented_real_elf_is_rejected(self):
        simple = self.root / "plain"
        source = self.root / "plain.c"
        source.write_text("int main(void) {return 0;}\n")
        subprocess.run(["cc", str(source), "-o", str(simple)],
                       check=True, capture_output=True, text=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "lacks required symbol"):
            audit_cycle_elf(simple)

    def test_shared_library_cannot_impersonate_executable(self):
        library = self.root / "lib-symbols.so"
        source = self.root / "fixture.c"
        subprocess.run(
            ["cc", "-shared", "-fPIC", str(source), "-o", str(library)],
            check=True, capture_output=True, text=True, timeout=30)
        library.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "no executable entry point"):
            audit_cycle_elf(library)

    def test_missing_even_one_required_original_hook_fails(self):
        without = self.root / "without-cd"
        source = self.root / "without-cd.c"
        source.write_text(
            "\n".join("void " + sym + "(void) {}"
                      for sym in SYMBOLS if sym != "ContinueLoadingCdFile")
            + "\nint main(void) {return 0;}\n")
        subprocess.run(["cc", str(source), "-o", str(without)],
                       check=True, capture_output=True, text=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "ContinueLoadingCdFile"):
            audit_cycle_elf(without)

    def test_full_elf_without_private_original_font_data_is_rejected(self):
        missing = self.root / "no-font"
        source = self.root / "no-font.c"
        source.write_text(
            "\n".join("void " + sym + "(void) {}" for sym in SYMBOLS)
            + "\nint main(void) {return 0;}\n")
        subprocess.run(["cc", str(source), "-o", str(missing)], check=True,
                       capture_output=True, text=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "initialized original US font"):
            audit_cycle_elf(missing)

    def test_truncated_initialized_glyph_symbol_is_rejected(self):
        smaller = self.root / "font-truncated"
        source = self.root / "font-truncated.c"
        source.write_text(
            "\n".join("void " + sym + "(void) {}" for sym in SYMBOLS)
            + "\nconst unsigned char pc_kanji_charset2[6269] = {1};\n"
            + "int main(void) {return 0;}\n")
        subprocess.run(["cc", str(source), "-o", str(smaller)], check=True,
                       capture_output=True, text=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "initialized original US font"):
            audit_cycle_elf(smaller)

    def test_uninitialized_font_name_cannot_substitute_for_original_glyphs(self):
        missing = self.root / "font-bss"
        source = self.root / "font-bss.c"
        source.write_text(
            "\n".join("void " + sym + "(void) {}" for sym in SYMBOLS)
            + "\nunsigned char pc_kanji_charset2[6270];\n"
            + "int main(void) {return 0;}\n")
        subprocess.run(["cc", str(source), "-o", str(missing)], check=True,
                       capture_output=True, text=True, timeout=30)
        with self.assertRaisesRegex(ValueError, "initialized original US font"):
            audit_cycle_elf(missing)

    def test_symlink_and_non_executable_rejected(self):
        link = self.root / "linked"
        link.symlink_to(self.executable)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            audit_cycle_elf(link)
        dst = self.root / "nonexecutable"
        dst.write_bytes(self.executable.read_bytes())
        dst.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "owned executable"):
            audit_cycle_elf(dst)

    def test_stripped_symbols_fail_closed(self):
        stripped = self.root / "stripped"
        stripped.write_bytes(self.executable.read_bytes())
        stripped.chmod(0o700)
        subprocess.run(["strip", "--strip-all", str(stripped)],
                       check=True, capture_output=True, text=True, timeout=30)
        with self.assertRaises(ValueError):
            audit_cycle_elf(stripped)


if __name__ == "__main__":
    unittest.main()

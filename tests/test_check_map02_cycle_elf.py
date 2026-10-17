"""Real host ELF structural tests for the opt-in full MAP02 cycle gate.

The positive fixture is a synthetic symbol-only ELF, NOT original source,
not a game, and not a claim of actual hooks being executed. The fixture
proves only the scope and fail-closed behavior of the structural audit.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_map02_cycle_elf import SYMBOLS, audit_cycle_elf


class OriginalCycleElfAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vh-cycle-elf-")
        cls.root = Path(cls.temp.name)
        source = cls.root / "fixture.c"
        source.write_text(
            "/* Synthetic names, NO original game/observer implementation */\n"
            + "\n".join("void " + sym + "(void) {}" for sym in SYMBOLS)
            + "\nint main(void) { return 0; }\n", encoding="utf-8")
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
        self.assertFalse(result["original_gameplay_authenticated"])
        self.assertFalse(result["original_map02_rendering_proven"])
        self.assertFalse(result["physical_ps1_equivalence_proven"])

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

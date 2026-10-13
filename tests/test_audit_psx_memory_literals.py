"""Regression tests for the PS1 address-literal inventory script."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_psx_memory_literals.py"


class AddressInventoryTests(unittest.TestCase):
    def test_reports_each_supported_address_range(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "src" / "memory_probe.c"
            source.parent.mkdir(parents=True)
            source.write_text(
                "void *ram = (void *)0x80140878;\n"
                "#define PSX_RAM_BASE ((void *)0x80000000UL)\n"
                "unsigned char *scratch = (unsigned char *)0x1f800000;\n"
                "unsigned int io = 0x1f801810;\n"
                "void *null_mirror = (void *)0x00000000;\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("[main-RAM] 2 occurrence(s): 2 code, 0 comment/string", result.stdout)
            self.assertIn("[scratchpad] 1 occurrence(s): 1 code, 0 comment/string", result.stdout)
            self.assertIn("[I/O-register-range] 1 occurrence(s): 1 code, 0 comment/string", result.stdout)
            self.assertIn("[NULL-mirror-or-zero] 1 occurrence(s): 1 code, 0 comment/string", result.stdout)
            self.assertIn("[code] src/memory_probe.c:1: 0x80140878", result.stdout)
            self.assertIn("[code] src/memory_probe.c:2: 0x80000000", result.stdout)

    def test_separates_comments_and_string_literals_from_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "src" / "comments.c"
            source.parent.mkdir(parents=True)
            source.write_text(
                "void *ram = (void *)0x80001234; // 0x80005678\n"
                "/* 0x80009999 */ const char *s = \"0x8000abcd\";\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("[main-RAM] 4 occurrence(s): 1 code, 3 comment/string", result.stdout)
            self.assertIn("[code] src/comments.c:1: 0x80001234", result.stdout)
            self.assertIn("[comment/string] src/comments.c:1: 0x80005678", result.stdout)

    def test_errors_when_no_source_tree_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("no upstream C/C++ sources", result.stderr)


if __name__ == "__main__":
    unittest.main()

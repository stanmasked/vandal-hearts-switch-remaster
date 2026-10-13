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
            self.assertIn("[main-RAM] 1 occurrence(s)", result.stdout)
            self.assertIn("[scratchpad] 1 occurrence(s)", result.stdout)
            self.assertIn("[I/O-register-range] 1 occurrence(s)", result.stdout)
            self.assertIn("[NULL-mirror-or-zero] 1 occurrence(s)", result.stdout)
            self.assertIn("src/memory_probe.c:1: 0x80140878", result.stdout)

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

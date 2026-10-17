"""Prove .text-only comparisons miss changed external C symbol targets."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class BaselineElfParityTests(unittest.TestCase):
    def test_disabled_observer_preserves_native_baseline(self):
        cc = shutil.which(os.environ.get("CC") or "cc")
        readelf = shutil.which("readelf")
        objcopy = shutil.which("objcopy")
        if not all((cc, readelf, objcopy)):
            self.fail("selected compiler, readelf and objcopy are required")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = []
            for enabled_source in (False, True):
                stem = "candidate" if enabled_source else "original"
                source = root / (stem + ".c")
                source.write_text(
                    "extern int original_target(int);\n"
                    + ("#if defined(VH_MAP02_DDA_REJECTED_EDGES_TRACE)\n"
                       "static int optional_counter;\n"
                       "static void record_candidate(void) { optional_counter++; }\n"
                       "#endif\n" if enabled_source else "")
                    + "int shared_entry(int value) { return original_target(value) + 1; }\n",
                    encoding="utf-8")
                obj = root / (stem + ".o")
                subprocess.run([cc, "-std=c11", "-O0", "-Wall", "-Wextra",
                                "-Werror", "-c", str(source), "-o", str(obj)],
                               check=True, capture_output=True)
                binary = root / (stem + ".text")
                subprocess.run([objcopy, "--only-section=.text", "-O", "binary",
                                str(obj), str(binary)], check=True, capture_output=True)
                reloc = subprocess.run([readelf, "-rW", str(obj)],
                                       check=True, capture_output=True, text=True).stdout
                data.append((binary.read_bytes(), reloc))
            self.assertEqual(data[0], data[1])

    def test_relocations_detect_changed_target_with_identical_text(self):
        cc = shutil.which(os.environ.get("CC") or "cc")
        readelf = shutil.which("readelf")
        objcopy = shutil.which("objcopy")
        if not cc or not readelf or not objcopy:
            self.fail("selected compiler, readelf and objcopy are required")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outputs = []
            for name in ("original_target", "other_target"):
                source = root / (name + ".c")
                source.write_text(
                    f"extern int {name}(int);\n"
                    f"int shared_entry(int value) {{ return {name}(value) + 1; }}\n",
                    encoding="utf-8",
                )
                obj = root / (name + ".o")
                subprocess.run([cc, "-std=c11", "-O0", "-Wall", "-Wextra",
                                "-Werror", "-c", str(source),
                                "-o", str(obj)], check=True, capture_output=True)
                binary = root / (name + ".text")
                subprocess.run([objcopy, "--only-section=.text", "-O", "binary",
                                str(obj), str(binary)], check=True, capture_output=True)
                relocation = subprocess.run([readelf, "-rW", str(obj)], check=True,
                                            capture_output=True, text=True).stdout
                outputs.append((binary.read_bytes(), relocation))
            self.assertEqual(outputs[0][0], outputs[1][0],
                             "fixture must have identical instructions")
            self.assertNotEqual(outputs[0][1], outputs[1][1],
                                "relocation parity must expose changed symbol target")
            self.assertIn("original_target", outputs[0][1])
            self.assertIn("other_target", outputs[1][1])


if __name__ == "__main__":
    unittest.main()

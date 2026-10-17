"""Read-only PC-port ELF probe readiness checks, entirely asset-free."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.check_map02_private_pc_binary import inspect_binary

ELF_C = r"""
#include <stdlib.h>
void VH_CaptureEvent(void) {}
void VH_Map02PixelScopeSet(void) {}
void VH_Map02PixelScopeClear(void) {}
void VH_PixelSampleRecord(void) {}
const char *volatile px = "VH_MAP02_PUTPIXEL_X2";
const char *volatile py = "VH_MAP02_PUTPIXEL_Y2";
int main(void) {
    VH_CaptureEvent();
    VH_Map02PixelScopeSet();
    VH_Map02PixelScopeClear();
    VH_PixelSampleRecord();
    return (px[0] != 'V') || (py[0] != 'V');
}
"""


class PrivatePcProbeReadinessTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("gcc") or not shutil.which("nm"):
            self.skipTest("native GCC and nm required")
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-elf-readiness-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.elf = self.root / "local-native-elf"

    def compile(self, text=ELF_C):
        completed = subprocess.run(
            ["gcc", "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror",
             "-x", "c", "-", "-o", str(self.elf)],
            input=text, text=True, capture_output=True, timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.elf.chmod(0o700)

    def test_four_symbols_and_two_selectors_in_real_native_elf(self):
        self.compile()
        result = inspect_binary(self.elf)
        self.assertEqual(result["schema"], "vh.map02.private-pc-elf-static-readiness.v1")
        self.assertEqual(result["required_probe_symbols_checked"], 4)
        self.assertTrue(result["required_probe_symbols_present"])
        self.assertTrue(result["second_coordinate_selectors_present"])
        self.assertEqual(len(result["executable_sha256"]), 64)
        self.assertTrue(result["static_probe_readiness_only"])
        for field in (
            "native_probes_executed", "original_pc_port_authenticated",
            "retail_map02_gameplay_authenticated",
            "native_process_to_gpu_log_causality_authenticated",
            "switch_rendering_verified", "hd_replacement_authorized",
        ):
            self.assertFalse(result[field])
        result_text = json.dumps(result)
        self.assertNotIn(str(self.root), result_text)
        self.assertNotIn("VH_MAP02_PUTPIXEL_X2", result_text)
        self.assertNotIn("VH_PixelSampleRecord", result_text)

    def test_missing_original_gpu_event_symbol_rejected(self):
        self.compile(ELF_C.replace("void VH_CaptureEvent(void) {}", "")
                     .replace("    VH_CaptureEvent();", ""))
        with self.assertRaisesRegex(ValueError, "probe evidence missing"):
            inspect_binary(self.elf)

    def test_no_second_sample_selector_rejected(self):
        self.compile(ELF_C.replace("VH_MAP02_PUTPIXEL_Y2", "OTHER_PIXEL_SELECTOR"))
        with self.assertRaisesRegex(ValueError, "probe evidence missing"):
            inspect_binary(self.elf)

    def test_stripped_symbol_table_rejected(self):
        self.compile()
        subprocess.run(["strip", "--strip-all", str(self.elf)],
                       check=True, timeout=20)
        with self.assertRaisesRegex(ValueError, "symbol table unavailable"):
            inspect_binary(self.elf)

    def test_non_elf_and_symlink_rejected(self):
        self.elf.write_text("#!/bin/sh\nexit 0\n")
        self.elf.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "native ELF executable image required"):
            inspect_binary(self.elf)
        link = self.root / "elf-symlink"
        link.symlink_to(self.elf)
        with self.assertRaisesRegex(ValueError, "symlink"):
            inspect_binary(link)

    def test_unavailable_symbol_inspector_fails_closed(self):
        self.compile()
        with self.assertRaisesRegex(ValueError, "nm unavailable"):
            inspect_binary(self.elf, nm="vh-impossible-nm-99999999")


if __name__ == "__main__":
    unittest.main()

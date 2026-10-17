"""Smoke-test real GPU compilation gate orchestration with synthetic C TUs.

Unlike CI's pinned-upstream check, these fixtures only verify compiler mode,
linker, and unresolved-observer rejection. No game source is bundled.
"""
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.check_map02_original_gpu_tus import verify_gpu_objects


@unittest.skipUnless(shutil.which("cc") and shutil.which("nm"),
                     "host cc and nm required")
class OriginalGpuCompileOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.upstream = Path(self.temp.name)
        src = self.upstream / "platform" / "pc" / "src"
        src.mkdir(parents=True)
        (self.upstream / "platform" / "pc" / "include").mkdir()
        (src / "pc_raster.c").write_text("/* synthetic original */\n", encoding="utf-8")
        (src / "libgpu.c").write_text("/* synthetic original */\n", encoding="utf-8")

    def test_three_modes_compiled_and_linked(self):
        with (
            patch("tools.check_map02_original_gpu_tus.patch_raster",
                  return_value="int fake_native_raster(void) { return 1; }\n"),
            patch("tools.check_map02_original_gpu_tus.patch_drawotag",
                  return_value="int fake_native_walker(void) { return 2; }\n"),
        ):
            self.assertEqual(verify_gpu_objects(self.upstream),
                             ["ordinary", "scoped", "private-posix"])

    def test_unresolved_private_probe_symbol_rejected(self):
        with (
            patch("tools.check_map02_original_gpu_tus.patch_raster",
                  return_value="int fake_native_raster(void) { return 1; }\n"),
            patch("tools.check_map02_original_gpu_tus.patch_drawotag",
                  return_value=("extern void vh_map02_missing(void);\n"
                                "void fake_native_walker(void) { "
                                "vh_map02_missing(); }\n")),
        ):
            with self.assertRaisesRegex(ValueError, "unresolved private"):
                verify_gpu_objects(self.upstream)

    def test_source_missing_fails_instead_of_skipping(self):
        (self.upstream / "platform" / "pc" / "src" / "libgpu.c").unlink()
        with self.assertRaises(OSError):
            verify_gpu_objects(self.upstream)


if __name__ == "__main__":
    unittest.main()

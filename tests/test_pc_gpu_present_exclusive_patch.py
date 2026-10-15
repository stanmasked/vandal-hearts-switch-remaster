import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "patch_pc_gpu_present_exclusive.py"
spec = importlib.util.spec_from_file_location("exclusive_patch", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ExclusivePresentPatchTests(unittest.TestCase):
    def setUp(self):
        self.original = """void PC_GpuPresent(unsigned short *vram, int w) {
    /* Scale the native w*h framebuffer up to fill the current window, preserving
     * source aspect. */
    glDrawPixels(w, h, GL_RGB, GL_UNSIGNED_BYTE, s_rgbaScratch);
    SDL_GL_SwapWindow(s_window);
    if (s_ptTime) pt2 = presentNowMs();
}
"""

    def test_mutually_exclusive_and_preserves_desktop_tail(self):
        patched = module.patch(self.original)
        self.assertEqual(patched.count("#if defined(VH_SWITCH_EXCLUSIVE_PRESENT)"), 1)
        self.assertEqual(patched.count("#else"), 1)
        self.assertEqual(patched.count("#endif /* VH_SWITCH_EXCLUSIVE_PRESENT */"), 1)
        self.assertEqual(patched.count("SDL_GL_SwapWindow(s_window);"), 1)
        self.assertLess(patched.index("VH_ObserveCompletedRGB24(s_rgbaScratch"),
                        patched.index("#else"))
        self.assertLess(patched.index("#else"), patched.index("glDrawPixels("))\n        self.assertLess(patched.index("SDL_GL_SwapWindow(s_window);"),\n                        patched.index("#endif /* VH_SWITCH_EXCLUSIVE_PRESENT */"))
        self.assertIn("(size_t)w <= ((size_t)s_scratchCap / 3u) / (size_t)h", patched)
        self.assertEqual(patched.split("#else\n", 1)[1].split(
            "#endif /* VH_SWITCH_EXCLUSIVE_PRESENT */", 1)[0],
            self.original[self.original.index(module.START):self.original.index(module.END)])

    def test_fails_closed_on_unexpected_source(self):
        with self.assertRaisesRegex(ValueError, "already instrumented"):
            module.patch(module.patch(self.original))
        with self.assertRaisesRegex(ValueError, "unique"):
            module.patch(self.original.replace(module.START, "missing"))
        with self.assertRaisesRegex(ValueError, "draw/swap"):
            module.patch(self.original.replace("glDrawPixels(", "otherDraw("))
        with self.assertRaisesRegex(ValueError, "one desktop GL swap"):
            module.patch(self.original.replace("SDL_GL_SwapWindow(s_window);", ""))

if __name__ == "__main__":
    unittest.main()

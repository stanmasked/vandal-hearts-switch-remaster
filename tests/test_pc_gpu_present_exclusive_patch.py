import importlib.util
import pathlib
import subprocess
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
    if (s_ptTime) pt2 = presentNowMs();
#if defined(__APPLE__)
    SDL_RenderPresent(s_renderer);
#else
    SDL_GL_SwapWindow(s_window);
#endif
    if (s_ptTime) {
        pt3 = presentNowMs();
    }
}
"""

    def test_mutually_exclusive_and_preserves_desktop_tail(self):
        patched = module.patch(self.original)
        self.assertEqual(patched.count("#if defined(VH_SWITCH_EXCLUSIVE_PRESENT)"), 1)
        self.assertEqual(patched.count("#endif /* VH_SWITCH_EXCLUSIVE_PRESENT */"), 1)
        self.assertEqual(patched.count("SDL_GL_SwapWindow(s_window);"), 1)
        self.assertLess(patched.index("VH_ObserveCompletedRGB24(s_rgbaScratch"),
                        patched.index("#else"))
        self.assertLess(patched.index("#else"), patched.index("glDrawPixels("))
        self.assertLess(patched.index("SDL_GL_SwapWindow(s_window);"),
                        patched.index("#endif /* VH_SWITCH_EXCLUSIVE_PRESENT */"))
        self.assertIn("(size_t)w <= ((size_t)s_scratchCap / 3u) / (size_t)h", patched)
        preserved = patched.split("#else\n", 1)[1].split(
            "#endif /* VH_SWITCH_EXCLUSIVE_PRESENT */", 1)[0]
        expected = self.original[self.original.index(module.START):self.original.index(module.END)]
        self.assertEqual(preserved, expected)

    def test_preprocessed_backend_selection(self):
        # Check emitted C after conditional compilation, not only source text.
        patched = module.patch(self.original)
        cases = (
            (["-DVH_SWITCH_EXCLUSIVE_PRESENT"], True, False),
            ([], False, False),
            (["-D__APPLE__"], False, True),
            (["-DVH_SWITCH_EXCLUSIVE_PRESENT", "-D__APPLE__"], True, True),
        )
        for flags, switch, apple in cases:
            with self.subTest(flags=flags):
                result = subprocess.run(
                    ["cc", "-E", "-P", "-x", "c", *flags, "-"],
                    input=patched, text=True, capture_output=True, check=True,
                ).stdout
                self.assertEqual("VH_ObserveCompletedRGB24(" in result, switch)
                self.assertEqual("glDrawPixels(" in result, not switch)
                self.assertEqual("SDL_GL_SwapWindow(" in result,
                                 not switch and not apple)
                self.assertEqual("SDL_RenderPresent(" in result,
                                 not switch and apple)

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

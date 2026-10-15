import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "patch_pc_gpu_present_observer.py"
spec = importlib.util.spec_from_file_location("observer_patch", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ObserverPatchTests(unittest.TestCase):
    def setUp(self):
        self.upstream = """void PC_GpuPresent(unsigned short *vram, int a) {
    if (PC_OverlayIsOpen()) PC_GpuDrawOverlay(w, h);   /* options overlay, on top */
    SDL_GL_SwapWindow(s_window);
}
"""

    def test_exact_insertion_and_default_disabled(self):
        result = module.patch(self.upstream)
        self.assertEqual(result.count("VH_ObserveCompletedRGB24(s_rgbaScratch"), 1)
        self.assertIn("#if defined(VH_SWITCH_COMPLETED_FRAME_OBSERVER)", result)
        self.assertLess(result.index("PC_GpuDrawOverlay(w, h);"),
                        result.index("VH_ObserveCompletedRGB24(s_rgbaScratch"))
        self.assertLess(result.index("VH_ObserveCompletedRGB24(s_rgbaScratch"),
                        result.index("SDL_GL_SwapWindow(s_window)"))
        self.assertEqual(result.count("SDL_GL_SwapWindow(s_window)"), 1)

    def test_reject_repeated_patching(self):
        patched = module.patch(self.upstream)
        with self.assertRaisesRegex(ValueError, "already instrumented"):
            module.patch(patched)

    def test_reject_unrecognized_upstream(self):
        with self.assertRaisesRegex(ValueError, "precisely one"):
            module.patch(self.upstream.replace(module.ANCHOR, ""))
        with self.assertRaisesRegex(ValueError, "precisely one"):
            module.patch(self.upstream.replace(module.ANCHOR, module.ANCHOR + module.ANCHOR))
        with self.assertRaisesRegex(ValueError, "not the pinned"):
            module.patch(self.upstream.replace("PC_GpuPresent", "WrongName"))
        with self.assertRaisesRegex(ValueError, "tail not found"):
            module.patch(self.upstream.replace("SDL_GL_SwapWindow(s_window);", ""))

if __name__ == "__main__":
    unittest.main()

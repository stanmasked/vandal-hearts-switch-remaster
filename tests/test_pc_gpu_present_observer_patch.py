import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "patch_pc_gpu_present_observer.py"
spec = importlib.util.spec_from_file_location("observer_patch", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ObserverPatchTests(unittest.TestCase):
    def setUp(self):
        self.upstream = """#include <SDL2/SDL_opengl.h>
int PC_GpuInit(int width, int height, const char *title) {
    /* synthetic desktop init content for patch-anchor testing */
    return 1;
}

/* Report the actual window size from desktop state */
void PC_GpuPresent(unsigned short *vram, int a) {
#if defined(__APPLE__)
    if (!s_window || !s_renderer) return; /* headless: no-op */
#else
    if (!s_window || !s_glCtx) return; /* headless: no-op */
#endif
    (void)vramH;
    PC_GpuPumpEvents();
    if (PC_OverlayIsOpen()) PC_GpuDrawOverlay(w, h);   /* options overlay, on top */
    /* Scale the native w*h framebuffer up to fill the current window. */
    SDL_GL_SwapWindow(s_window);
}
"""

    def test_exact_insertion_and_default_disabled(self):
        result = module.patch(self.upstream)
        self.assertEqual(result.count("VH_ObserveCompletedRGB24(s_rgbaScratch"), 1)
        self.assertIn("#if !defined(VH_SWITCH_EXCLUSIVE_PRESENT)\n#if defined(__APPLE__)", result)
        self.assertEqual(result.count("if (!s_window || !s_glCtx) return;"), 1)
        self.assertLess(result.index("desktop-only window prerequisite"), result.index("PC_GpuDrawOverlay(w, h);"))
        self.assertIn("#if defined(VH_SWITCH_COMPLETED_FRAME_OBSERVER)", result)
        self.assertIn("#include <SDL2/SDL_opengles2.h>", result)
        self.assertIn("vh_switch_observer_query_viewport(&drawable_w, &drawable_h)", result)
        self.assertIn("#else /* original desktop SDL window initialization */", result)
        self.assertIn("#endif /* desktop GPU initialization */", result)
        self.assertIn("#if !defined(VH_SWITCH_EXCLUSIVE_PRESENT) /* desktop GL draw and swap */", result)
        self.assertIn("#endif /* desktop presentation tail */", result)
        self.assertLess(result.index("external Switch event loop owns SDL pumping"),
                        result.index("PC_GpuDrawOverlay(w, h);"))
        self.assertLess(result.index("PC_GpuDrawOverlay(w, h);"),
                        result.index("VH_ObserveCompletedRGB24(s_rgbaScratch"))
        self.assertLess(result.index("VH_ObserveCompletedRGB24(s_rgbaScratch"),
                        result.index("SDL_GL_SwapWindow(s_window)"))
        self.assertEqual(result.count("SDL_GL_SwapWindow(s_window)"), 1)
        self.assertIn("#if defined(VH_SWITCH_EXCLUSIVE_PRESENT)", result)
        self.assertIn("#error VH_SWITCH_EXCLUSIVE_PRESENT requires", result)
        self.assertLess(result.index("VH_ObserveCompletedRGB24(s_rgbaScratch"),
                        result.index("Target owns frame presentation"))
        self.assertLess(result.index("Target owns frame presentation"),
                        result.index("SDL_GL_SwapWindow(s_window)"))
        self.assertIn("s_rgbaScratch && w > 0 && h > 0 && s_scratchCap > 0", result)
        self.assertIn("(size_t)w <= ((size_t)s_scratchCap / 3u) / (size_t)h", result)
        self.assertLess(result.index("s_rgbaScratch && w > 0"),
                        result.index("VH_ObserveCompletedRGB24(s_rgbaScratch"))

    def test_event_pump_is_not_duplicated_by_patch(self):
        result = module.patch(self.upstream)
        self.assertEqual(result.count("    PC_GpuPumpEvents();"), 1)
        self.assertIn(module.TARGET_EVENT_PUMP, result)
        self.assertEqual(result.count("external Switch event loop owns SDL pumping"), 1)

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
        with self.assertRaisesRegex(ValueError, "precisely one desktop window guard"):
            module.patch(self.upstream.replace(module.WINDOW_GUARD, ""))
        with self.assertRaisesRegex(ValueError, "precisely one desktop SDL event pump"):
            module.patch(self.upstream.replace(module.EVENT_PUMP, ""))
        with self.assertRaisesRegex(ValueError, "expected pinned desktop OpenGL header"):
            module.patch(self.upstream.replace(module.GL_HEADER, ""))
        with self.assertRaisesRegex(ValueError, "exact pinned PC_GpuInit lifecycle anchors"):
            module.patch(self.upstream.replace(module.INIT_ANCHOR, "WrongInit(void) {"))
        with self.assertRaisesRegex(ValueError, "tail not found"):
            module.patch(self.upstream.replace("SDL_GL_SwapWindow(s_window);", ""))

if __name__ == "__main__":
    unittest.main()

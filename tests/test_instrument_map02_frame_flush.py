"""No-game-assets structural checks for the source-pinned DrawOTag completion hook."""
import unittest
from unittest.mock import patch

from tools import instrument_map02_frame_flush as hook


def fixture():
    return (
        "#include <stdio.h>\n"
        "#define VRAM_H 512\n"
        + hook.INSERT_AT
        + "void DrawOTag(unsigned int *p) {\n"
        "    TrcFrameEnd();\n"
        "    if (HiresActive())\n"
        "        HiresRasterizeThreaded(0, 512);\n"
        + hook.CALL_AFTER + "\n"
        "    if (HiresActive()) {\n"
        "        HiresPresent(0, 0, 320, 240);\n"
        "    }\n"
        "}\n"
    ).encode("utf-8")


class FrameFlushHookTests(unittest.TestCase):
    def generated(self, contents=None):
        with patch.object(hook, "git_blob_sha1", return_value=hook.PINNED_SOURCE):
            return hook.instrument(fixture() if contents is None else contents)

    def test_hooks_once_after_frame_end_before_presentation(self):
        source = self.generated()
        self.assertEqual(source.count("VH_Map02PrivateFrameFlush();"), 1)
        self.assertEqual(source.count("static void VH_Map02PrivateFrameFlush("), 1)
        self.assertLess(source.index("    TrcFrameEnd();"),
                        source.index("    VH_Map02PrivateFrameFlush();"))
        self.assertLess(source.index("    VH_Map02PrivateFrameFlush();"),
                        source.index("    if (HiresActive()) {"))
        self.assertIn("vram = PC_GpuVram();", source)
        self.assertIn("VRAM_W, VRAM_H, &vram[0][0], VRAM_W", source)
        self.assertIn('getenv("VH_MAP02_PRIVATE_FRAME_PIPE_FRAME")', source)
        self.assertIn("vh_map02_frame_pipe_wait_release(STDIN_FILENO)", source)
        self.assertIn("_exit(0);", source)
        self.assertIn("#if defined(VH_MAP02_PRIVATE_FRAME_PIPE_TRACE)", source)

    def test_unpinned_source_must_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "exact pinned"):
            hook.instrument(fixture())

    def test_missing_completion_boundary_rejected(self):
        data = fixture().replace(b"    TrcFrameEnd();", b"")
        with self.assertRaisesRegex(ValueError, "completion"):
            self.generated(data)

    def test_missing_presentation_boundary_rejected(self):
        data = fixture().replace(b"    if (HiresActive()) {", b"    if (hires) {")
        with self.assertRaisesRegex(ValueError, "completion"):
            self.generated(data)

    def test_missing_original_source_anchor_rejected(self):
        data = fixture().replace(hook.CALL_AFTER.encode(), b"")
        with self.assertRaisesRegex(ValueError, "anchor count"):
            self.generated(data)

    def test_duplicate_flush_site_refused(self):
        data = fixture().replace(hook.CALL_AFTER.encode(),
                                 hook.CALL_AFTER.encode() * 2)
        with self.assertRaisesRegex(ValueError, "anchor count"):
            self.generated(data)

    def test_wrong_order_rejected(self):
        data = fixture().replace(
            b"    TrcFrameEnd();\n", b"").replace(
            hook.CALL_AFTER.encode(), hook.CALL_AFTER.encode() +
            b"\n    TrcFrameEnd();")
        with self.assertRaisesRegex(ValueError, "after raster walk"):
            self.generated(data)

    def test_double_instrumentation_rejected_even_if_digest_stubbed(self):
        generated = self.generated().encode("utf-8")
        with self.assertRaisesRegex(ValueError, "already instrumented"):
            self.generated(generated)

    def test_corrupt_utf8_refused(self):
        with self.assertRaises(UnicodeDecodeError):
            self.generated(fixture() + b"\xff")

    def test_baseline_source_text_unchanged_with_opt_in_guards_only(self):
        before = fixture()
        transformed = self.generated(before)
        self.assertEqual(transformed.count(hook.CALL_AFTER), 1)
        self.assertEqual(transformed.count("void DrawOTag(unsigned int *p)"), 1)
        self.assertEqual(transformed.count("TrcFrameEnd();"), 1)
        self.assertIn("HiresRasterizeThreaded(0, 512)", transformed)


if __name__ == "__main__":
    unittest.main()

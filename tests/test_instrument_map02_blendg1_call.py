"""Synthetic source-level regressions for native-only BlendG1 observer."""
import unittest
from tools.instrument_map02_blendg1_call import (
    instrument, SIGNATURE, HIRES, NATIVE, CALL,
)


class BlendG1SourceHookTests(unittest.TestCase):
    def setUp(self):
        self.source = "\n".join([SIGNATURE, CALL, HIRES, NATIVE])

    def test_native_only_actual_blend_call(self):
        patched = instrument(self.source)
        self.assertIn("int textured, int nativeTarget)", patched)
        self.assertIn("textured, 0);", patched)
        self.assertIn("textured, 1);", patched)
        self.assertIn("unsigned short result = BlendG1(fg, bg, abr, textured);", patched)
        self.assertIn("vh_map02_blendg1_call(x, y, fg, bg, result", patched)
        self.assertIn("#else\n" + CALL + "\n#endif", patched)

    def test_fail_closed_on_drift_or_repeat(self):
        bad = [self.source + "\n" + CALL,
               self.source.replace(CALL, ""),
               self.source.replace(NATIVE, ""),
               self.source.replace(HIRES, ""),
               instrument(self.source)]
        for value in bad:
            with self.subTest(source=value[:40]), self.assertRaises(ValueError):
                instrument(value)


if __name__ == "__main__":
    unittest.main()

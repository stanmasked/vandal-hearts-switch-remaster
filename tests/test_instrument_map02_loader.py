"""Synthetic checks for opt-in map02 loader instrumentation."""
import unittest

from tools.instrument_map02_loader import ANCHOR, GUARD, instrument


def upstream_fixture():
    return (
        "void LoadMap(void) {\n"
        "   ProcessMapFileData(&gScratch1_801317c0[0]);\n"
        "   pTiles[iz][ix].gfx[iFace] += GFX_MAP_TEXTURES_OFS;\n"
        + ANCHOR
    )


class InstrumentLoaderTests(unittest.TestCase):
    def test_adds_trace_after_conversion(self):
        source = upstream_fixture()
        result = instrument(source)
        self.assertEqual(result.count(GUARD), 1)
        self.assertIn('traceTiles[8][19].gfx[0]', result)
        self.assertIn('traceTiles[11][11].gfx[0]', result)
        self.assertLess(result.index("GFX_MAP_TEXTURES_OFS;"),
                        result.index(GUARD))
        self.assertLess(result.index(GUARD), result.index("   SetupField();"))

    def test_rejects_double_instrumentation(self):
        with self.assertRaisesRegex(ValueError, "already instrumented"):
            instrument(instrument(upstream_fixture()))

    def test_rejects_missing_or_ambiguous_anchor(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            instrument(upstream_fixture().replace(ANCHOR, ""))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            instrument(upstream_fixture() + ANCHOR)

    def test_requires_expected_loader_calls(self):
        with self.assertRaisesRegex(ValueError, "decompression"):
            instrument(upstream_fixture().replace("ProcessMapFileData(", "Other("))
        with self.assertRaisesRegex(ValueError, "conversion"):
            instrument(upstream_fixture().replace("GFX_MAP_TEXTURES_OFS", "OTHER"))


if __name__ == "__main__":
    unittest.main()

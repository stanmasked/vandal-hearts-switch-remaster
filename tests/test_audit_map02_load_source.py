"""Offline regression tests for source-level PRS selection of map 11."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.audit_map02_load_source import audit_cd_route, audit_loader_source, EXPECTED_DIMENSIONS


def fixture(resource="CDF_M_MAP02_PRS"):
    dims = "\n".join(f"      {name} = {value};" for name, value in EXPECTED_DIMENSIONS.items())
    return f'''void LoadMap(void) {{
   for (i = 0; i < 22; i++) {{
      gMapRowPointers[i] = ((MapTileModel(*)[28])gMapDataPtr)[i];
   }}
   switch (gState.mapNum) {{
   case 10:
      LoadCdFile(CDF_M_MAP01_PRS, 1);
      break;
   case 11:
{dims}
      LoadCdFile({resource}, 1);
      break;
   case 12:
      LoadCdFile(CDF_M_MAP03_PRS, 1);
      break;
   }}
   ProcessMapFileData(&gScratch1_801317c0[0]);
   pTiles = (MapTileModel(*)[28])gMapDataPtr;
   pTiles[iz][ix].gfx[iFace] += GFX_MAP_TEXTURES_OFS;
   SetupField();
}}

void SetupField(void) {{
}}
'''


CD_SOURCE = """CdFileInfo gCdFiles[712] = {
    [CDF_M_MAP02_PRS] = {0x1bcc, 0x0c, gScratch1_801317c0},
};
void LoadCdFile(s32 cdfIdx, s32 showLoadingScreen) {
   gCdLoader.cdf = cdfIdx;
   gCdLoader.loadingVabBody = 0;
   gCdLoader.sectorsToRead = gCdFiles[cdfIdx].sectorCt;
   gCdLoader.sector = gCdFiles[cdfIdx].startingSector;
}
"""
CD_HEADER = """typedef enum CdFileInfoIdx {
   CDF_M_MAP01_PRS = 150,
   CDF_M_MAP02_PRS = 151,
   CDF_M_MAP03_PRS = 152,
} CdFileInfoIdx;
"""


class AuditMap02LoadSourceTests(unittest.TestCase):
    def test_static_source_selects_prs_and_targets_fit(self):
        result = audit_loader_source(fixture())
        self.assertEqual(result["load_resource"], "CDF_M_MAP02_PRS")
        self.assertEqual(result["selection"], "PRS")
        self.assertEqual(result["runtime_map_number"], 11)
        self.assertEqual(result["map_dimensions"]["gMapMaxX"], 23)
        self.assertEqual(result["map_dimensions"]["gMapMaxZ"], 11)
        self.assertEqual([(v["z"], v["x"]) for v in result["target_faces"]],
                         [(8, 19), (11, 11)])

    def test_rejects_dat_or_other_map_resource(self):
        for chosen in ("CDF_M_MAP02_DAT", "CDF_M_MAP01_PRS", "CDF_M_MAP03_PRS"):
            with self.subTest(chosen=chosen):
                with self.assertRaisesRegex(ValueError, "must load only"):
                    audit_loader_source(fixture(resource=chosen))

    def test_rejects_tampered_map_dimensions(self):
        original = fixture()
        for symbol, expected in EXPECTED_DIMENSIONS.items():
            with self.subTest(symbol=symbol):
                changed = original.replace(f"{symbol} = {expected};",
                                           f"{symbol} = {expected + 1};")
                with self.assertRaisesRegex(ValueError, symbol):
                    audit_loader_source(changed)

    def test_rejects_missing_or_duplicated_map11_branch(self):
        source = fixture()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            audit_loader_source(source.replace("   case 11:", "   case 77:"))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            audit_loader_source(source.replace("   case 12:", "   case 11:"))

    def test_rejects_modified_decode_and_global_gfx_conversion(self):
        for needle in ("ProcessMapFileData(&gScratch1_801317c0[0]);",
                       "pTiles = (MapTileModel(*)[28])gMapDataPtr;",
                       "pTiles[iz][ix].gfx[iFace] += GFX_MAP_TEXTURES_OFS;",
                       "gMapRowPointers[i] = ((MapTileModel(*)[28])gMapDataPtr)[i];"):
            with self.subTest(needle=needle):
                with self.assertRaises(ValueError):
                    audit_loader_source(fixture().replace(needle, "/* removed */"))

    def test_rejects_order_changes(self):
        source = fixture()
        decode = "   ProcessMapFileData(&gScratch1_801317c0[0]);"
        setup = "   SetupField();"
        with self.assertRaisesRegex(ValueError, "order changed"):
            audit_loader_source(source.replace(decode, setup).replace(
                setup + "\n}", decode + "\n}"))

    def test_cd_table_proves_symbol_to_sector_mapping(self):
        result = audit_cd_route(CD_SOURCE, CD_HEADER)
        self.assertEqual(result["cd_file_enum"], 151)
        self.assertEqual(result["cd_table_start_sector"], 0x1bcc)
        self.assertEqual(result["cd_table_sector_count"], 12)
        self.assertEqual(result["cd_destination"], "gScratch1_801317c0")

    def test_cd_table_rejects_wrong_sector_count_or_destination(self):
        for replacement in ("0x1bcd, 0x0c, gScratch1_801317c0",
                            "0x1bcc, 0x0b, gScratch1_801317c0",
                            "0x1bcc, 0x0c, gScratch3_80180210"):
            with self.subTest(row=replacement):
                modified = CD_SOURCE.replace(
                    "0x1bcc, 0x0c, gScratch1_801317c0", replacement)
                with self.assertRaisesRegex(ValueError, "sector table|PRS mapping"):
                    audit_cd_route(modified, CD_HEADER)

    def test_cd_header_rejects_changed_prs_identifier(self):
        with self.assertRaisesRegex(ValueError, "enum identifier"):
            audit_cd_route(CD_SOURCE, CD_HEADER.replace("PRS = 151", "PRS = 152"))

    def test_cd_loader_must_take_read_parameters_from_indexed_table(self):
        broken = CD_SOURCE.replace(
            "gCdLoader.sectorsToRead = gCdFiles[cdfIdx].sectorCt;",
            "gCdLoader.sectorsToRead = 12;")
        with self.assertRaisesRegex(ValueError, "does not initialize sector"):
            audit_cd_route(broken, CD_HEADER)

    def test_cli_refuses_unpinned_source_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "game_setup.c"
            path.write_text(fixture(), encoding="utf-8")
            cmd = [sys.executable, "-m", "tools.audit_map02_load_source", str(path)]
            strict = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(strict.returncode, 0)
            self.assertIn("source differs from pinned", strict.stderr)
            permissive = subprocess.run(cmd + ["--allow-modified-source"],
                                        capture_output=True, text=True)
            self.assertEqual(permissive.returncode, 0, permissive.stderr)
            result = json.loads(permissive.stdout)
            self.assertFalse(result["matches_pinned"])
            self.assertEqual(result["selection"], "PRS")


if __name__ == "__main__":
    unittest.main()

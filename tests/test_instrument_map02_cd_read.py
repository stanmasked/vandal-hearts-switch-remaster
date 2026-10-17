"""Strict pinned original CD source-instrumentation regression tests."""
import unittest
from unittest.mock import patch

from tools.instrument_map02_cd_read import (
    SOURCE_CD, SOURCE_LIBCD, instrument_libcd, instrument_core_cd,
)

LIBCD = """#include "PsyQ/libcd.h"
int CdRead(int sectors, unsigned int *buf, int mode) {
    unsigned char *out = (unsigned char *)buf;
        memcpy(out + (size_t)i * SECTOR_DATA_SIZE, raw + SECTOR_DATA_OFFSET, SECTOR_DATA_SIZE);
    PC_LangPatchRead(s_targetLBA, sectors, out);
}
"""

CORE = """void LoadCdFile(s32 cdfIdx, s32 showLoadingScreen) {
   gCdLoader.sectorsToRead = gCdFiles[cdfIdx].sectorCt;
   gCdLoader.sector = gCdFiles[cdfIdx].startingSector;
}
void ContinueLoadingCdFile(void) {
       } else {
          gCdLoader.state = 99;
       }
       break;
}
"""


class OriginalMap02CdReadInstrumentTests(unittest.TestCase):
    def test_original_cdread_hooks_are_only_compile_time_opt_in(self):
        with patch("tools.instrument_map02_cd_read.git_blob_sha1",
                   return_value=SOURCE_LIBCD):
            got = instrument_libcd(LIBCD)
        self.assertIn("vh_map02_cd_read_start(s_targetLBA, sectors)", got)
        self.assertIn("vh_map02_cd_read_sector(lba, raw + SECTOR_DATA_OFFSET)", got)
        self.assertIn("vh_map02_cd_read_finish(s_targetLBA, sectors, out)", got)
        self.assertEqual(got.count("#ifdef VH_MAP02_CD_READ_PROBE"), 4)
        self.assertIn("PC_LangPatchRead(s_targetLBA, sectors, out);", got)
        self.assertIn("memcpy(out + (size_t)i * SECTOR_DATA_SIZE", got)

    def test_real_core_cd_loader_claims_and_finishes_map02(self):
        with patch("tools.instrument_map02_cd_read.git_blob_sha1",
                   return_value=SOURCE_CD):
            got = instrument_core_cd(CORE)
        self.assertIn("vh_map02_cd_loader_claim(cdfIdx, CDF_M_MAP02_PRS", got)
        self.assertIn("vh_map02_cd_loader_complete(gCdLoader.cdf", got)
        self.assertIn("gCdLoader.state = 99;", got)

    def test_missing_or_duplicated_libcd_anchor_rejected(self):
        with patch("tools.instrument_map02_cd_read.git_blob_sha1",
                   return_value=SOURCE_LIBCD):
            with self.assertRaisesRegex(ValueError, "anchor"):
                instrument_libcd(LIBCD.replace("PC_LangPatchRead", "NoLangPatch"))
            with self.assertRaisesRegex(ValueError, "anchor"):
                instrument_libcd(LIBCD + '    PC_LangPatchRead(s_targetLBA, sectors, out);\n')

    def test_original_core_state_transition_must_exist(self):
        with patch("tools.instrument_map02_cd_read.git_blob_sha1",
                   return_value=SOURCE_CD):
            with self.assertRaisesRegex(ValueError, "anchor"):
                instrument_core_cd(CORE.replace("state = 99", "state = 98"))

    def test_pinned_source_sha_enforced(self):
        with patch("tools.instrument_map02_cd_read.git_blob_sha1",
                   return_value="f" * 40):
            with self.assertRaisesRegex(ValueError, "hash differs"):
                instrument_libcd(LIBCD)
            with self.assertRaisesRegex(ValueError, "hash differs"):
                instrument_core_cd(CORE)


if __name__ == "__main__":
    unittest.main()

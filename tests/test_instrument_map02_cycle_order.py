"""Regression tests for exact placement of same-process CD -> DrawOTag hooks.

These tests isolate the source-instrumentation composition with small source
fragments; full pinned-source generation and compilation remain separate CI
steps. No game image or retail source bytes are included.
"""
import unittest
from unittest.mock import patch

from tools.instrument_map02_cycle_order import (
    GPU_SOURCE, patch_core, patch_gpu, patch_libcd,
)


CORE = r"""
#include "map02_cd_read_probe.h"
#endif
void LoadCdFile(s32 cdfIdx, s32 showLoadingScreen) {
   gCdLoader.sectorsToRead = gCdFiles[cdfIdx].sectorCt;
   gCdLoader.sector = gCdFiles[cdfIdx].startingSector;
   vh_map02_cd_loader_claim(cdfIdx, CDF_M_MAP02_PRS,
       gCdFiles[cdfIdx].startingSector, gCdFiles[cdfIdx].sectorCt);
#endif
}
void ContinueLoadingCdFile(void) {
   vh_map02_cd_loader_complete(gCdLoader.cdf,
          CDF_M_MAP02_PRS, gCdLoader.state);
#endif
}
"""

LIBCD = r"""
#include "map02_cd_read_probe.h"
#endif
void CdRead(void) {
    vh_map02_cd_read_start(s_targetLBA, sectors);
#endif
    memcpy(out + (size_t)i * SECTOR_DATA_SIZE, raw + SECTOR_DATA_OFFSET, SECTOR_DATA_SIZE);
    vh_map02_cd_read_finish(s_targetLBA, sectors, out);
#endif
}
"""

GPU = """void DrawOTag(unsigned int *p) {
    s_drawFrame++;
    TrcFrameEnd();
}
"""


class CycleHookCompositionTests(unittest.TestCase):
    def test_core_cycle_claim_and_completion_follow_cd_probe_hooks(self):
        with patch("tools.instrument_map02_cycle_order.instrument_core_cd",
                   return_value=CORE):
            result = patch_core("unused pinned source is supplied by mock")
        self.assertLess(result.index("vh_map02_cd_loader_claim"),
                        result.index("vh_map02_cycle_load"))
        self.assertLess(result.index("vh_map02_cd_loader_complete"),
                        result.index("vh_map02_cycle_loader_complete"))
        self.assertIn("vh_map02_cycle_load(cdfIdx, CDF_M_MAP02_PRS", result)
        self.assertIn("vh_map02_cycle_loader_complete(gCdLoader.cdf", result)

    def test_libcd_cycle_boundaries_follow_original_crc_observer(self):
        with patch("tools.instrument_map02_cycle_order.instrument_libcd",
                   return_value=LIBCD):
            result = patch_libcd("unused pinned source is supplied by mock")
        self.assertLess(result.index("vh_map02_cd_read_start"),
                        result.index("vh_map02_cycle_read_start"))
        self.assertLess(result.index("vh_map02_cd_read_finish"),
                        result.index("vh_map02_cycle_read_finish"))
        self.assertIn("vh_map02_cycle_read_start(s_targetLBA, sectors)", result)
        self.assertIn("vh_map02_cycle_read_finish(s_targetLBA, sectors)", result)

    def test_gpu_frame_hooks_bracket_actual_draw_walk(self):
        with patch("tools.instrument_map02_cycle_order.git_blob_sha1",
                   return_value=GPU_SOURCE), \
             patch("tools.instrument_map02_cycle_order.instrument_gpu_native",
                   side_effect=lambda source: source), \
             patch("tools.instrument_map02_cycle_order.instrument_gpu_scope",
                   side_effect=lambda source: source):
            result = patch_gpu(GPU)
        self.assertLess(result.index("s_drawFrame++;"),
                        result.index("vh_map02_cycle_draw_start(s_drawFrame)"))
        self.assertLess(result.index("vh_map02_cycle_draw_start(s_drawFrame)"),
                        result.index("TrcFrameEnd();"))
        self.assertLess(result.index("vh_map02_cycle_draw_finish(s_drawFrame, nextTok == 0)"),
                        result.index("TrcFrameEnd();"))

    def test_ambiguous_or_missing_gpu_walk_anchor_fails_closed(self):
        with patch("tools.instrument_map02_cycle_order.git_blob_sha1",
                   return_value=GPU_SOURCE), \
             patch("tools.instrument_map02_cycle_order.instrument_gpu_native",
                   side_effect=lambda source: source), \
             patch("tools.instrument_map02_cycle_order.instrument_gpu_scope",
                   side_effect=lambda source: source):
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                patch_gpu(GPU + GPU)
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                patch_gpu(GPU.replace("s_drawFrame++;", ""))


if __name__ == "__main__":
    unittest.main()

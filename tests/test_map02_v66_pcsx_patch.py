#!/usr/bin/env python3
"""v66 exact pinned PCSX source patch adversarial/unit checks (no retail ROM)."""
from __future__ import annotations
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch as mock_patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.apply_map02_v66_pcsx_rearmed import PIN,one,patch

HW_SRC='''#include "psxhw.h"
void psxHwWrite32(void) {
\tcase 0x1814: psxHwWriteGpuSR(value); return;
}
'''
DMA_SRC='''#include "psxdma.h"
void psxDma2(void) {
\t\t\tcycles_sum = GPU_dmaChain((u32 *)psxRegs.ptrs.psxM, madr & 0x1fffff,
\t\t\t\t\tmadr_next_p, &cycles_last_cmd);
}
'''
MAKE_SRC='''OBJS += libpcsxcore/gte.o libpcsxcore/gte_nf.o libpcsxcore/gte_divider.o
'''

class FakeCommand:
    def __init__(self,sha=PIN):
        self.stdout=sha+"\n"
        self.returncode=0

class V66PcsxPatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"pcsx"
        (self.root/"libpcsxcore").mkdir(parents=True)
        (self.root/"libpcsxcore/psxhw.c").write_text(HW_SRC)
        (self.root/"libpcsxcore/psxdma.c").write_text(DMA_SRC)
        (self.root/"Makefile").write_text(MAKE_SRC)

    def patched(self):
        with mock_patch("tools.apply_map02_v66_pcsx_rearmed.subprocess.run",return_value=FakeCommand()):
            return patch(self.root)

    def test_exact_pin_is_40_hex(self):
        self.assertEqual(len(PIN),40)
        self.assertTrue(all(x in "0123456789abcdef" for x in PIN))

    def test_reject_wrong_upstream_commit(self):
        with mock_patch("tools.apply_map02_v66_pcsx_rearmed.subprocess.run",
                        return_value=FakeCommand("0"*40)):
            with self.assertRaises(ValueError):patch(self.root)

    def test_patch_keeps_all_original_target_calls(self):
        self.patched()
        s=(self.root/"libpcsxcore/psxhw.c").read_text()
        t=(self.root/"libpcsxcore/psxdma.c").read_text()
        self.assertIn("psxHwWriteGpuSR(value); return;",s)
        self.assertIn("GPU_dmaChain((u32 *)psxRegs.ptrs.psxM",t)

    def test_gp1_hook_precedes_real_gpu_status_write(self):
        self.patched()
        s=(self.root/"libpcsxcore/psxhw.c").read_text()
        self.assertLess(s.index("vh66_pcsx_gp1_observe(value)"),
                        s.index("psxHwWriteGpuSR(value); return;"))

    def test_dma_pre_submit_hook_precedes_gpu_dma_chain(self):
        self.patched()
        s=(self.root/"libpcsxcore/psxdma.c").read_text()
        self.assertLess(s.index("vh66_pcsx_dma2_observe("),
                        s.index("cycles_sum = GPU_dmaChain("))

    def test_opt_in_macro_guards_both_hooks(self):
        self.patched()
        for name in ("psxhw.c","psxdma.c"):
            s=(self.root/"libpcsxcore"/name).read_text()
            self.assertEqual(s.count("#ifdef VH_MAP02_V66_PCSX_PROBE"),2)
            self.assertEqual(s.count("#endif"),2)

    def test_makefile_feature_off_by_default(self):
        self.patched()
        s=(self.root/"Makefile").read_text()
        self.assertIn("ifneq ($(VH_MAP02_V66_PCSX_PROBE),)",s)
        self.assertIn("OBJS += libpcsxcore/vh66_gpu_probe_bridge.o",s)
        self.assertIn("CFLAGS += -DVH_MAP02_V66_PCSX_PROBE",s)

    def test_copies_required_hook_headers(self):
        self.patched()
        for name in ("vh65_gpu_probe.h","vh66_gpu_probe_bridge.h","vh66_gpu_probe_bridge.c"):
            self.assertTrue((self.root/"libpcsxcore"/name).is_file())

    def test_source_unchanged_on_missing_unique_anchor(self):
        hw=self.root/"libpcsxcore/psxhw.c"
        before=hw.read_bytes()
        hw.write_text(HW_SRC.replace("case 0x1814","case 0x1818"))
        with self.assertRaises(ValueError):self.patched()
        self.assertEqual(hw.read_text(),HW_SRC.replace("case 0x1814","case 0x1818"))
        self.assertEqual((self.root/"libpcsxcore/psxdma.c").read_text(),DMA_SRC)
        self.assertFalse((self.root/"libpcsxcore/vh66_gpu_probe_bridge.c").exists())

    def test_patch_never_applies_twice(self):
        self.patched()
        s=(self.root/"libpcsxcore/psxhw.c").read_bytes()
        with self.assertRaises(ValueError):self.patched()
        self.assertEqual((self.root/"libpcsxcore/psxhw.c").read_bytes(),s)

    def test_reject_existing_adapter_without_overwrite(self):
        target=self.root/"libpcsxcore/vh66_gpu_probe_bridge.c"
        target.write_text("PRIVATE_INPUT")
        with self.assertRaises(ValueError):self.patched()
        self.assertEqual(target.read_text(),"PRIVATE_INPUT")

    def test_uniqueness_rejects_multiple_identical_anchors(self):
        with self.assertRaises(ValueError):one("abc abc","abc","xx","test")
        with self.assertRaises(ValueError):one("abc","xyz","xx","test")

    def test_no_main_branch_or_project_mutations(self):
        result=self.patched()
        self.assertFalse(result["gp0_packet_consumption_or_hardware_observed"])
        self.assertFalse(result["original_retail_MAP02_verified"])
        self.assertFalse(result["HD_replacement_approved"])

    def test_all_added_adapter_files_live_in_emulator_clone(self):
        self.patched()
        names={p.name for p in (self.root/"libpcsxcore").iterdir()}
        self.assertEqual({x for x in names if x.startswith("vh")},
                         {"vh65_gpu_probe.h","vh66_gpu_probe_bridge.h","vh66_gpu_probe_bridge.c"})

if __name__=="__main__": unittest.main()

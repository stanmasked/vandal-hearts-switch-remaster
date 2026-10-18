#!/usr/bin/env python3
"""v172 source-MMIO + real PCSX psxRcntUpdate GPU_vBlank + native Unai pixels."""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.apply_map02_v172_mips_real_vblank_vram import (
    check_v78_extends_exact_v171_mips,
    native_vblank_provenance_oracle,
    patch_frontend,
)
from tools.apply_map02_v171_mips_multiphase_vram import expected_phase_source
from tools.make_map02_v78_vblank_mips_exe import (
    build as v78_build,WAIT_NOPS,MAGIC
)
from tools.make_map02_v77_gpu_multiphase_exe import (
    build as v77_build,PHASE_GP0,PHASE_GP1
)


def frontend_fixture():
    return ('\tint vh171_mips_multiphase_smoke = 0;\n'
            '\t\telse if (!strcmp(argv[i], "--vh171-mips-multiphase-vram"))\n'
            '\tif (loadst_f) {\n')


class FourRealNativeVBlankGuestOrigins172(unittest.TestCase):
    def test_self_authored_v78_has_exact_four_v171_gpu_phases_plus_mips_nop_wait(self):
        stops,wait=check_v78_extends_exact_v171_mips()
        earlier,old_stops,old_ops,old_starts=v77_build()
        image,new_stops,starts,wait_pc,new_ops=v78_build()
        self.assertEqual(stops,old_stops)
        self.assertEqual(stops,new_stops)
        self.assertEqual(starts,old_starts)
        self.assertEqual(tuple(new_ops[:len(old_ops)]),tuple(old_ops))
        self.assertEqual(wait,wait_pc)
        self.assertEqual(len(image),10240)
        self.assertEqual(image[0x4c:0x54],MAGIC)
        self.assertEqual(MAGIC,b"VH78SYN!")
        self.assertEqual(new_ops[len(old_ops):len(old_ops)+WAIT_NOPS],
                         (0,)*512)
        self.assertEqual(WAIT_NOPS,512)
        pcs,gp1,lens,expected_stops=expected_phase_source()
        self.assertEqual(lens,(49,7,7,9))
        self.assertEqual(sum(lens),72)
        self.assertEqual(sum(x!=0 for x in gp1),3)
        self.assertEqual(tuple(stops),tuple(expected_stops))

    def test_genuine_native_vblank_counter_not_host_forged_cycles(self):
        source=native_vblank_provenance_oracle()
        for signal in (
            "vh78_vblank_observed_count==entry_count",
            "vh78_vblank_last_cycle<=start_cycle",
            "vh78_vblank_last_frame!=previous_vblank_frame+1",
            "vh78_vblank_last_hsync==0",
            "psxRegs.pc=VH78_WAIT_PC",
            "vh78_vblank_observed_count!=initial_vblank_count+4",
            "vblank",  # actual original native observer; not console parity
            "VH78_VBLANK_OBSERVED",
            "VH78_PHASE_PASS phase=%u checked=595 guard=499",
        ):
            if signal=="psxRegs.pc=VH78_WAIT_PC":
                self.assertIn("psxRegs.pc=0x",source)
            else:
                self.assertIn(signal,source)
        self.assertNotIn("GPU_vBlank(1,0);",source)
        self.assertNotIn("psxRegs.cycle+=",source)
        self.assertNotIn("vh78_vblank_observed_count++;",source)
        self.assertIn("console_frame_asserted=0",source)
        self.assertIn("original_retail=0",source)

    def test_mips_origin_verification_precedes_wait_and_real_vram_readback(self):
        src=patch_frontend(frontend_fixture())
        for mark in (
            "--vh172-mips-real-vblank-vram",
            "vh172_mips_vblank_vram_smoke=1;",
            "VH172_MIPS_GP1_VBLANK_ORIGIN_REFUSED",
            "vh171_arm_guest_phase(phase)!=0",
            "vh171_guest_phase_gp0_words();",
            "vh171_guest_phase_gp1_writes();",
            "vh171_disarm_guest_phase();",
            "vh172_gp0!=vh172_expect_gp0[phase]",
            "vh172_gp1!=vh172_expect_gp1[phase]",
            "vh78_vblank_observed_count==entry_count",
            "GPU_freeze(1,&state,&vram)",
            "vram[y*1024+x]!=expected",
            "VH78_VBLANK_VRAM_PASS vblanks=4 phases=4 samples=2380",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
            "source=psxRcntUpdate console_frame_asserted=0",
        ):
            self.assertIn(mark,src)
        self.assertEqual(src.count("psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"),2)
        self.assertLess(src.index("vh171_arm_guest_phase(phase)!=0"),
                        src.index("vh171_disarm_guest_phase();"))
        self.assertLess(src.index("vh171_disarm_guest_phase();"),
                        src.index("vh78_vblank_observed_count==entry_count"))
        self.assertLess(src.index("vh78_vblank_observed_count==entry_count"),
                        src.index("GPU_freeze(1,&state,&vram)"))
        self.assertLess(src.index("VH78_GPU_STATE_REFUSED count=%u"),
                        src.index("VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS"))
        with self.assertRaises(ValueError):
            patch_frontend(src)

    def test_actual_pinned_native_and_mutated_gp1_negative_wiring(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        own=(ROOT/".github/workflows/map02-v172-mips-real-vblank-vram.yml").read_text()
        for token in (
            "apply_map02_v172_mips_real_vblank_vram",
            "test_map02_v172_mips_real_vblank_vram.py",
            "--vh172-mips-real-vblank-vram",
            "V172_SYNTHETIC.EXE",
            "V172_BAD_GP1.EXE",
            "VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS",
            "VH172_MIPS_GP1_VBLANK_ORIGIN_REFUSED",
            "VH78_VBLANK_VRAM_PASS vblanks=4",
        ):
            self.assertIn(token,workflow)
        self.assertIn("test_map02_v171_mips_multiphase_vram.py",own)
        self.assertIn("original_retail_executed=0",own)


if __name__=="__main__":
    unittest.main()

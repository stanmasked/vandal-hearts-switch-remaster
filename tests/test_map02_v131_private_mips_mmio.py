#!/usr/bin/env python3
"""Private original-PSX executable input guard and actual synthetic MIPS tests."""
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from tools.analyze_map02_v131_private_mips_mmio import (
    HEADER_BYTES, MAX_EXE_BYTES, NAME_ORDER, SCHEMA, Refused,
    analyze_mips_text, audit_private_exe, parse_psx_text, read_private_exe
)
from tools.make_map02_v129_four_vblank_exe import build

def ins(*values):
    return b"".join(struct.pack("<I",v) for v in values)

def lui(rt,imm):
    return (0x0f<<26)|(rt<<16)|imm

def ori(rt,rs,imm):
    return (0x0d<<26)|(rs<<21)|(rt<<16)|imm

def sw(rt,off,rs):
    return (0x2b<<26)|(rs<<21)|(rt<<16)|(off&0xffff)

def lw(rt,off,rs):
    return (0x23<<26)|(rs<<21)|(rt<<16)|(off&0xffff)

class PrivateRetailMipsMmioAudit(unittest.TestCase):
    def test_real_generated_synthetic_mips_has_expected_three_dma2_sequences(self):
        raw,_,_,_,_=build()
        self.assertEqual(len(raw),10240)
        text=parse_psx_text(raw)
        counters=analyze_mips_text(text)
        self.assertEqual(counters["dma2_madr"],3)
        self.assertEqual(counters["dma2_bcr"],3)
        self.assertEqual(counters["dma2_chcr"],6)
        self.assertEqual(counters["dma2_linked_list_chcr_literal"],3)
        self.assertEqual(counters["dma_dpcr"],1)
        self.assertGreater(counters["gpu_gp0"],0)
        self.assertEqual(counters["gpu_gp1"],0)

    def test_exact_base_and_constant_source_required(self):
        two=ins(lui(11,0x1f80),ori(11,11,0x1000),
                lui(9,0x0100),ori(9,9,0x0401),
                sw(9,0xa8,11))
        counts=analyze_mips_text(two)
        self.assertEqual(counts["dma2_chcr"],1)
        self.assertEqual(counts["dma2_linked_list_chcr_literal"],1)
        # Invalidate the known MMIO base with an actual MIPS load.
        counts=analyze_mips_text(ins(lui(11,0x1f80),
            ori(11,11,0x1000),lw(11,0,4),sw(9,0xa8,11)))
        self.assertEqual(counts["dma2_chcr"],0)
        # Invalidate the data value; SW remains a candidate, not a linked list.
        counts=analyze_mips_text(ins(lui(11,0x1f80),ori(11,11,0x1000),
            lui(9,0x0100),ori(9,9,0x0401),lw(9,0,4),sw(9,0xa8,11)))
        self.assertEqual(counts["dma2_chcr"],1)
        self.assertEqual(counts["dma2_linked_list_chcr_literal"],0)
        # Unconditional MIPS jump is a control-flow barrier in the linear scan.
        counts=analyze_mips_text(ins(lui(11,0x1f80),ori(11,11,0x1000),
            0x08004000,sw(9,0xa8,11)))
        self.assertEqual(counts["dma2_chcr"],0)
        # Direct kseg1 MMIO physical alias is accepted only when known.
        counts=analyze_mips_text(ins(lui(11,0xbf80),ori(11,11,0x1000),
                                     sw(9,0xa8,11)))
        self.assertEqual(counts["dma2_chcr"],1)

    def test_only_sw_counts_and_gp1_vs_gp0_separate(self):
        source=ins(lui(8,0x1f80),ori(8,8,0x1800),sw(9,0x10,8),
                   sw(9,0x14,8),sw(9,0x10,8))
        result=analyze_mips_text(source)
        self.assertEqual(result["gpu_gp0"],2)
        self.assertEqual(result["gpu_gp1"],1)
        self.assertEqual(result["dma2_chcr"],0)
        self.assertEqual(result["dma2_linked_list_chcr_literal"],0)
        self.assertEqual(tuple(k for k in result if k!="dma2_linked_list_chcr_literal"),
                         NAME_ORDER)

    def test_header_bounds_and_trailing_material_rejected(self):
        raw,_,_,_,_=build()
        bad=[
            b"PS-X EXE",
            b"NOT EXE!"+raw[8:],
            raw[:HEADER_BYTES+1],
            raw+ b"retail_payload",
        ]
        t=bytearray(raw)
        struct.pack_into("<I",t,0x1c,0x200004)
        bad.append(bytes(t))
        t=bytearray(raw)
        struct.pack_into("<I",t,0x10,0x80400000)
        bad.append(bytes(t))
        t=bytearray(raw)
        struct.pack_into("<I",t,0x18,0x801ffffc)
        bad.append(bytes(t))
        t=bytearray(raw)
        struct.pack_into("<I",t,0x1c,0)
        bad.append(bytes(t))
        for case in bad:
            with self.subTest(case_length=len(case)),self.assertRaises(Refused):
                parse_psx_text(case)
        with self.assertRaises(Refused):
            analyze_mips_text(b"\x00")
        with self.assertRaises(Refused):
            parse_psx_text(bytearray(raw))

    def test_local_private_permissions_hardlinks_symlink_and_read_back(self):
        raw,_,_,_,_=build()
        with tempfile.TemporaryDirectory(prefix="vh131-private-") as temp:
            root=Path(temp)
            file=root/"private_user_supplied_only.exe"
            file.write_bytes(raw)
            file.chmod(0o600)
            self.assertEqual(read_private_exe(file),raw)
            result=audit_private_exe(file)
            self.assertEqual(result["schema"],SCHEMA)
            self.assertEqual(result["candidate_sw_instruction_counts"]["dma2_madr"],3)
            self.assertFalse(result["retail_map02_scene_identity_verified"])
            self.assertFalse(result["retail_map02_gpu_rendering_verified"])
            self.assertFalse(result["physical_ps1_equivalence_verified"])
            self.assertFalse(result["nintendo_switch_hd_parity_verified"])
            public=json.dumps(result,sort_keys=True)
            for sensitive in (str(file),"SLUS_004.47","sha256",
                              "raw_mips","program_bytes","retail_payload",
                              "PS-X EXE","0x1f8010a8","original_disc_sha"):
                self.assertNotIn(sensitive,public)
            file.chmod(0o644)
            with self.assertRaises(Refused):
                read_private_exe(file)
            file.chmod(0o600)
            hard=root/"linked"
            os.link(file,hard)
            with self.assertRaises(Refused):
                read_private_exe(file)
            hard.unlink()
            link=root/"symlink"
            link.symlink_to(file)
            with self.assertRaises(Refused):
                read_private_exe(link)
            self.assertEqual(read_private_exe(file),raw)

    def test_zero_padding_not_counted_and_exe_header_never_executed(self):
        raw,_,_,_,_=build()
        # Valid padding may follow the declared MIPS code and is not scanned.
        padded=raw+b"\0"*16
        self.assertEqual(parse_psx_text(raw),parse_psx_text(padded))
        # Guard off-by-one when length is reduced: only declared bytes matter.
        shorter=bytearray(raw)
        struct.pack_into("<I",shorter,0x1c,4)
        shorter[HEADER_BYTES+4:]=b"\0"*(len(raw)-HEADER_BYTES-4)
        self.assertEqual(len(parse_psx_text(bytes(shorter))),4)
        self.assertTrue(all(v==0 for v in
            analyze_mips_text(parse_psx_text(bytes(shorter))).values()))

    def test_full_ci_executes_private_safe_synthetic_only_audit(self):
        workflow=(ROOT/".github/workflows/map02-v131-private-mips-mmio.yml").read_text()
        for term in ("test_map02_v131_private_mips_mmio.py",
                     "test_map02_v130_native_bounds.py",
                     "no_real_retail_input_in_ci",
                     "contents: read"):
            self.assertIn(term,workflow)
        base=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("test_map02_v131_private_mips_mmio.py",base)
        self.assertIn("check_map02_v130_native_bounds",base)
        self.assertIn("for mode in 04 13 22 31 40; do",base)
        for guard in (
            "chmod 600 proof/private/V129_SYNTHETIC.EXE",
            "v131-same-exe.sha256",
            "v131-static-candidates.json",
            'counts["dma2_linked_list_chcr_literal"]!=3',
            "VH131_NATIVE_STATIC_COUNTS_PASS",
            'report["same_source_authored_exe_privately_hashed_before_after_each_mode"]=True',
            'report["v131_static_dma_mmio_candidate_counts_checked"]=True',
            'report["retail_map02_gpu_rendering_verified"]=False',
        ):
            self.assertIn(guard,base)
        self.assertGreaterEqual(base.count(
            "sha256sum -c proof/private/v131-same-exe.sha256"),2)

if __name__ == "__main__":
    unittest.main()

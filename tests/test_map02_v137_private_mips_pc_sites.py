#!/usr/bin/env python3
"""Private code-bound PC / MMIO-class candidate witness: synthetic-only tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"))

from test_map02_v136_original_code_sections import synthetic_with_exec_section
from tools.analyze_map02_v131_private_mips_mmio import Refused,NAME_ORDER
from tools.analyze_map02_v132_mips_delay_slots import analyze_delay_aware_text
from tools.analyze_map02_v135_original_us_elf_pair import PINNED_LOAD
from tools.verify_map02_v137_private_mips_pc_sites import (
    EVENT_SCHEMA,MAX_CLAIM_BYTES,MAX_CLAIMS,SCHEMA,read_private_claims,
    parse_pc_claims,source_bound_pc_sites,correlate_pc_claims,
    audit_private_pair_and_pc_claims,
)

def encode_claim(pc,kind):
    return (json.dumps({"schema":EVENT_SCHEMA,"pc":pc,"kind":kind},
                       sort_keys=True,separators=(",",":"))+"\n").encode()

class PrivatePCToMMIOProvenance(unittest.TestCase):
    def setUp(self):
        self.exe,self.elf=synthetic_with_exec_section()
        self.sites,self.static_counts=source_bound_pc_sites(self.exe,self.elf)

    def test_real_source_generated_site_pcs_exact_and_consistent_counts(self):
        sites=self.sites
        counts=self.static_counts
        self.assertGreater(len(sites),10)
        self.assertTrue(all(pc%4==0 and
                            PINNED_LOAD<=pc<PINNED_LOAD+8192
                            for pc in sites))
        self.assertEqual(counts["dma2_madr"],3)
        self.assertEqual(counts["dma2_bcr"],3)
        self.assertEqual(counts["dma2_chcr"],6)
        self.assertEqual(counts["dma2_linked_list_chcr_literal"],3)
        self.assertEqual(counts["dma_dpcr"],1)
        self.assertGreater(counts["gpu_gp0"],0)
        self.assertTrue(all(kind in NAME_ORDER for kind,_ in sites.values()))
        self.assertEqual(sum(1 for kind,linked in sites.values()
                             if kind=="dma2_chcr" and linked),3)

    def test_delay_slot_site_callback_is_exactly_one_mips_word(self):
        def ins(*words):
            return b"".join(struct.pack("<I",w) for w in words)
        # A normal MIPS-I jump has a real delay-slot SW to DMA CHCR.
        text=ins(0x3c0b1f80,0x356b1000,0x08004000,0xad6000a8,0)
        found=[]
        counts,meta=analyze_delay_aware_text(
            text,site_sink=lambda offset,kind,linked: found.append(
                (offset,kind,linked)))
        self.assertEqual(found,[(12,"dma2_chcr",False)])
        self.assertEqual(counts["dma2_chcr"],1)
        self.assertEqual(meta["constant_proven_sw_in_delay_slots"],1)
        self.assertEqual(analyze_delay_aware_text(text)[0],counts)
        # A MIPS-II branch-likely resets the values and is not counted.
        rejected=[]
        code=ins(0x3c0b1f80,0x356b1000,0x50000001,0xad6000a8,0)
        result,_=analyze_delay_aware_text(
            code,site_sink=lambda offset,kind,linked: rejected.append(offset))
        self.assertEqual(result["dma2_chcr"],0)
        self.assertEqual(rejected,[])

    def test_same_pc_wrong_class_neighbor_and_unverified_pc_refuse(self):
        good=next((pc,kind) for pc,(kind,_) in self.sites.items()
                  if kind=="dma2_chcr")
        result=correlate_pc_claims(self.exe,self.elf,[good,good])
        self.assertEqual(result["schema"],SCHEMA)
        self.assertEqual(result["private_claims_matching_static_code_candidates"],2)
        self.assertEqual(result["private_unique_source_pc_sites_matched"],1)
        self.assertEqual(result["claimed_mmio_register_class_counts"]["dma2_chcr"],2)
        for altered in (
            (good[0],"gpu_gp0"),
            (good[0]+1,good[1]),
            (0x00010000,good[1]), # do not silently fold kseg aliases
            (good[0]^0x20000000,good[1]),
            (0xffffffff,good[1]),
            (0x80000000,good[1]),
        ):
            with self.subTest(mutation="candidate mismatch"),self.assertRaises(Refused):
                correlate_pc_claims(self.exe,self.elf,[altered])

    def test_claim_jsonl_canonical_format_and_adversarial_input(self):
        pc,(kind,_)=next(iter(self.sites.items()))
        raw=encode_claim(pc,kind)
        self.assertEqual(parse_pc_claims(raw),[(pc,kind)])
        record=json.loads(raw)
        cases=(
            raw[:-1], # missing newline
            raw+b"\n",
            b"not json\n",
            b'{"schema":"vh.map02.private-mmio-pc-claim.v1","pc":1,"pc":1,"kind":"dma2_chcr"}\n',
            raw.replace(b'"pc":',b'"code_pc":'),
            raw.replace(str(pc).encode(),b'true'),
            raw.replace(str(pc).encode(),b'-1'),
            raw.replace(kind.encode(),b'unknown'),
            raw.replace(b'"kind":',b'"offset":'),
            raw+b"x"*(MAX_CLAIM_BYTES+1),
        )
        for case in cases:
            with self.subTest(kind="noncanonical claim"),self.assertRaises(Refused):
                parse_pc_claims(case)
        with self.assertRaises(Refused):
            parse_pc_claims(raw*(MAX_CLAIMS+1))
        self.assertEqual(record["pc"],pc)

    def test_executable_code_one_byte_change_refuses_before_any_match(self):
        pc,kind=next((pc,kind) for pc,(kind,_) in self.sites.items())
        mutated=bytearray(self.elf)
        mutated[0x800+20]^=1
        with self.assertRaises(Refused):
            source_bound_pc_sites(self.exe,bytes(mutated))
        with self.assertRaises(Refused):
            correlate_pc_claims(self.exe,bytes(mutated),[(pc,kind)])

    def test_private_event_reader_refuses_symlink_and_fifo_and_checks_modes(self):
        pc,(kind,_)=next(iter(self.sites.items()))
        raw=encode_claim(pc,kind)
        with tempfile.TemporaryDirectory(prefix="vh137-owned-") as tmp:
            root=Path(tmp)
            private=root/"private-event.jsonl"
            private.write_bytes(raw)
            private.chmod(0o600)
            self.assertEqual(read_private_claims(private),raw)
            self.assertEqual(parse_pc_claims(read_private_claims(private)),[(pc,kind)])
            private.chmod(0o644)
            with self.assertRaises(Refused):read_private_claims(private)
            private.chmod(0o600)
            leaf=root/"symlink.jsonl"
            leaf.symlink_to(private)
            with self.assertRaises(Refused):read_private_claims(leaf)
            directory=root/"linked-directory"
            directory.symlink_to(root,target_is_directory=True)
            with self.assertRaises(Refused):
                read_private_claims(directory/private.name)
            hard=root/"hardlink.jsonl"
            os.link(private,hard)
            with self.assertRaises(Refused):read_private_claims(private)
            hard.unlink()
            os.mkfifo(root/"fifo",0o600)
            child=subprocess.run([sys.executable,"-c",
                "import sys\nfrom tools.verify_map02_v137_private_mips_pc_sites "
                "import read_private_claims,Refused\ntry:"
                "\n read_private_claims(sys.argv[1])\nexcept Refused:"
                "\n print('VH137_FIFO_REFUSED')\n sys.exit(0)\nsys.exit(3)",
                str(root/"fifo")],cwd=ROOT,text=True,capture_output=True,
                timeout=3,check=False)
            self.assertEqual(child.returncode,0)
            self.assertEqual(child.stdout.strip(),"VH137_FIFO_REFUSED")

    def test_synthetic_pair_must_fail_original_retail_gate_and_not_print_pc(self):
        pc,(kind,_)=next(iter(self.sites.items()))
        with tempfile.TemporaryDirectory(prefix="vh137-synthetic-") as tmp:
            root=Path(tmp)
            exe=root/"artificial.exe"
            elf=root/"artificial.elf"
            claims=root/"claims.jsonl"
            for path,raw in (
                (exe,self.exe),(elf,self.elf),(claims,encode_claim(pc,kind)),
            ):
                path.write_bytes(raw)
                path.chmod(0o600)
            with self.assertRaises(Refused):
                audit_private_pair_and_pc_claims(exe,elf,claims)
            result=subprocess.run([
                sys.executable,"-m","tools.verify_map02_v137_private_mips_pc_sites",
                str(exe),str(elf),str(claims)],cwd=ROOT,text=True,
                capture_output=True,check=False,timeout=15)
            self.assertEqual(result.returncode,2)
            self.assertEqual(result.stdout,"")
            self.assertEqual(result.stderr.strip(),
                             "VH137_PRIVATE_MMIO_PC_CORRELATION_REFUSED")
            for secret in (str(exe),str(elf),str(claims),hex(pc),str(pc)):
                self.assertNotIn(secret,result.stdout+result.stderr)
        report=correlate_pc_claims(self.exe,self.elf,[(pc,kind)])
        self.assertIs(report["claim_producer_authenticated"],False)
        self.assertIs(report["execution_or_reachability_proven"],False)
        self.assertIs(report["dma_or_gpu_runtime_execution_proven"],False)
        self.assertIs(report["original_map02_frame_or_rendering_proven"],False)
        self.assertIs(report["physical_ps1_equivalence_proven"],False)
        self.assertIs(report["nintendo_switch_hd_parity_proven"],False)
        printable=json.dumps(report)
        self.assertNotIn(str(pc),printable)
        self.assertNotIn(hex(pc),printable)

    def test_full_native_and_dedicated_ci_carry_v137(self):
        main=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        standalone=(ROOT/".github/workflows/map02-v137-private-pc-sites.yml").read_text()
        for token in ("test_map02_v137_private_mips_pc_sites.py",
                      "test_map02_v136_original_code_sections.py"):
            self.assertIn(token,main)
            self.assertIn(token,standalone)
        self.assertIn("for mode in 04 13 22 31 40; do",main)
        self.assertIn("VH137_PRIVATE_PC_CLASS_SYNTHETIC_PASS",standalone)
        self.assertIn("no_original_retail_assets=1",standalone)

if __name__=="__main__":
    unittest.main()


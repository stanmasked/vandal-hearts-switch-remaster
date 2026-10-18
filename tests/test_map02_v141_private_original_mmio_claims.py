#!/usr/bin/env python3
"""Original-private MMIO (PC, SW word, effective address, value) source gate tests.

Only synthesized PS-X image and independently synthesized ELF32 MIPS are
present in CI. Original retail MD5 and runtime authentic execution remain
deliberately unproved.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"))

from test_map02_v136_original_code_sections import synthetic_with_exec_section
from tools.analyze_map02_v131_private_mips_mmio import Refused
from tools.apply_map02_v139_mips_word_stages import codeword_expectations
from tools.apply_map02_v140_mmio_effects import expected_actual_mmio
from tools.verify_map02_v141_private_original_mmio_claims import (
    SCHEMA,EVENT_SCHEMA,MAX_TRACE_BYTES,MAX_TRACE_EVENTS,
    parse_exact_mmio_trace,read_private_exact_mmio_trace,
    verify_source_bound_exact_mmio_claims,audit_private_source_and_claimed_effects,
)


def synthetic_source_claims():
    exe,elf=synthetic_with_exec_section()
    sites,words,_=codeword_expectations()
    effects=expected_actual_mmio()
    assert len(sites)==len(words)==len(effects)==19
    records=[(pc,word,addr,value) for (pc,*_),word,(addr,value)
             in zip(sites,words,effects)]
    return exe,elf,records


def encode_events(records):
    return b"".join(
        (json.dumps({
            "schema":EVENT_SCHEMA,"seq":i,"pc":pc,"word":word,
            "address":addr,"value":value},
            sort_keys=True,separators=(",",":"))+"\n").encode()
        for i,(pc,word,addr,value) in enumerate(records)
    )


class PrivateOriginalExactEffectCorrelator(unittest.TestCase):
    def setUp(self):
        self.exe,self.elf,self.records=synthetic_source_claims()

    def test_positive_source_authored_mips_run_matches_19_whole_tuples(self):
        payload=encode_events(self.records)
        self.assertEqual(parse_exact_mmio_trace(payload),self.records)
        report=verify_source_bound_exact_mmio_claims(
            self.exe,self.elf,self.records)
        self.assertEqual(report["schema"],SCHEMA)
        self.assertEqual(report["source_bound_candidate_events"],19)
        self.assertEqual(report["source_bound_distinct_mips_sw_sites"],19)
        self.assertEqual(report["claimed_mmio_register_class_counts"][
            "gpu_gp0"],6)
        self.assertEqual(report["claimed_mmio_register_class_counts"][
            "dma2_chcr"],6)
        self.assertEqual(report["statically_bound_linked_list_start_claims"],3)
        self.assertEqual(report["kuseg_address_claims"],19)
        self.assertEqual(report["kseg0_address_claims"],0)
        self.assertEqual(report["kseg1_address_claims"],0)
        for negative in (
            "mmio_value_compared_to_full_cpu_state",
            "trace_producer_authenticated",
            "mips_execution_or_reachability_proven",
            "original_map02_loaded_or_rendered",
            "physical_ps1_parity_verified",
            "nintendo_switch_hd_parity_verified",
            "private_pcs_values_paths_or_hashes_exported",
        ):
            self.assertIs(report[negative],False)
        serialized=json.dumps(report,sort_keys=True)
        for pc,word,address,value in self.records:
            # A coarse count might coincidentally equal a tiny value; no
            # private 32-bit addresses, source words or GP0 values may print.
            for secret in (pc,word,address):
                self.assertNotIn(str(secret),serialized)

    def test_full_word_code_change_and_unknown_pc_are_refused(self):
        base=list(self.records)
        for pos,field,mutation in ((0,0,4),(0,1,1),(2,1,0x10000)):
            altered=list(base)
            t=list(altered[pos])
            t[field]^=mutation
            altered[pos]=tuple(t)
            with self.subTest(position=pos,field=field):
                with self.assertRaises(Refused):
                    verify_source_bound_exact_mmio_claims(
                        self.exe,self.elf,altered)
        changed_elf=bytearray(self.elf)
        changed_elf[0x800+16]^=1
        with self.assertRaises(Refused):
            verify_source_bound_exact_mmio_claims(
                self.exe,bytes(changed_elf),self.records)

    def test_wrong_mmio_class_and_unmapped_segment_are_refused(self):
        for address in (0x1f801814,0x9f801814,0xbf801814,
                        0x5f801810,0xdf801810,0x1f801811,
                        0x1f801820):
            changed=list(self.records)
            pc,word,_,value=changed[0]
            changed[0]=(pc,word,address,value)
            with self.subTest(alias=address),self.assertRaises(Refused):
                verify_source_bound_exact_mmio_claims(
                    self.exe,self.elf,changed)

    def test_original_kseg0_kseg1_alias_is_explicitly_counted_not_confused(self):
        for segment in (0x80000000,0xa0000000):
            changed=list(self.records)
            pc,word,addr,value=changed[0]
            changed[0]=(pc,word,addr|segment,value)
            report=verify_source_bound_exact_mmio_claims(
                self.exe,self.elf,changed)
            key="kseg0_address_claims" if segment==0x80000000 else "kseg1_address_claims"
            self.assertEqual(report[key],1)
            self.assertEqual(report["kuseg_address_claims"],18)

    def test_zero_register_write_and_known_dma2_start_value(self):
        zero_index=next(i for i,r in enumerate(self.records)
                        if (r[1]>>16)&31==0)
        linked_index=next(i for i,r in enumerate(self.records)
                          if r[2]&0x1fffffff==0x1f8010a8
                          and r[3]==0x01000401)
        for index,bad_value in ((zero_index,1),(linked_index,2)):
            changed=list(self.records)
            pc,word,addr,_=changed[index]
            changed[index]=(pc,word,addr,bad_value)
            with self.subTest(index=index),self.assertRaises(Refused):
                verify_source_bound_exact_mmio_claims(
                    self.exe,self.elf,changed)
        # A GP0 value is not dynamically recoverable without full CPU
        # register-state testimony. Do not falsely label it proven.
        changed=list(self.records)
        pc,word,addr,value=changed[0]
        changed[0]=(pc,word,addr,value^1)
        report=verify_source_bound_exact_mmio_claims(
            self.exe,self.elf,changed)
        self.assertIs(report["mmio_value_compared_to_full_cpu_state"],False)

    def test_repeated_static_site_allowed_but_trace_sequence_must_be_exact(self):
        sample=[self.records[0],self.records[0]]
        report=verify_source_bound_exact_mmio_claims(
            self.exe,self.elf,sample)
        self.assertEqual(report["source_bound_candidate_events"],2)
        self.assertEqual(report["source_bound_distinct_mips_sw_sites"],1)
        self.assertEqual(len(parse_exact_mmio_trace(encode_events(sample))),2)

    def test_strict_trace_jsonl_refuses_duplicates_escapes_bounds_and_boolean(self):
        full=encode_events(self.records)
        self.assertEqual(parse_exact_mmio_trace(full),self.records)
        original=json.loads(full.splitlines()[0])
        first=json.dumps(original,sort_keys=True,separators=(",",":")).encode()
        bad=(
            full[:-1],full+b"\n",b"not json\n",full.replace(b'"seq":0',b'"seq":1',1),
            full.replace(b'"seq":0',b'"seq":true',1),
            full.replace(b'"pc":',b'"pc_raw":',1),
            full.replace(b'"word":',b'"words":',1),
            full.replace(b'"value":',b'"data":',1),
            b'{"schema":"'+EVENT_SCHEMA.encode()+
                b'","seq":0,"pc":1,"pc":1,"word":0,"address":1,"value":0}\n',
            full+b"x"*(MAX_TRACE_BYTES+1),
            encode_events([self.records[0]]*(MAX_TRACE_EVENTS+1)),
            first+b" \n",
        )
        for idx,data in enumerate(bad):
            with self.subTest(index=idx),self.assertRaises(Refused):
                parse_exact_mmio_trace(data)

    def test_private_trace_owner_modes_parent_symlink_fifo_and_hardlink(self):
        payload=encode_events(self.records)
        with tempfile.TemporaryDirectory(prefix="vh141-privacy-") as tmp:
            base=Path(tmp)
            d=base/"private"
            d.mkdir(mode=0o700)
            path=d/"claims.jsonl"
            path.write_bytes(payload)
            path.chmod(0o600)
            self.assertEqual(read_private_exact_mmio_trace(path),payload)
            path.chmod(0o644)
            with self.assertRaises(Refused):read_private_exact_mmio_trace(path)
            path.chmod(0o600)
            leaf=base/"symlink"
            leaf.symlink_to(path)
            with self.assertRaises(Refused):read_private_exact_mmio_trace(leaf)
            parent=base/"parent"
            parent.symlink_to(d,target_is_directory=True)
            with self.assertRaises(Refused):
                read_private_exact_mmio_trace(parent/path.name)
            other=d/"hardlink"
            os.link(path,other)
            with self.assertRaises(Refused):read_private_exact_mmio_trace(path)
            other.unlink()
            fifo=d/"fifo"
            os.mkfifo(fifo,0o600)
            cmd=(
                "import sys\n"
                "from tools.verify_map02_v141_private_original_mmio_claims "
                "import read_private_exact_mmio_trace, Refused\n"
                "try:\n read_private_exact_mmio_trace(sys.argv[1])\n"
                "except Refused:\n print('VH141_FIFO_REFUSED')\n sys.exit(0)\n"
                "sys.exit(3)\n")
            outcome=subprocess.run([sys.executable,"-c",cmd,str(fifo)],
                cwd=ROOT,capture_output=True,text=True,timeout=3,check=False)
            self.assertEqual(outcome.returncode,0)
            self.assertEqual(outcome.stdout.strip(),"VH141_FIFO_REFUSED")

    def test_public_synthetic_pair_can_never_claim_retail_us_identity(self):
        with tempfile.TemporaryDirectory(prefix="vh141-cli-") as tmp:
            root=Path(tmp)
            files=(
                (root/"user-owned-private-exe",self.exe),
                (root/"user-extracted-original-elf",self.elf),
                (root/"trace-real-candidate.jsonl",encode_events(self.records)),
            )
            for file,raw in files:
                file.write_bytes(raw)
                file.chmod(0o600)
            with self.assertRaises(Refused):
                audit_private_source_and_claimed_effects(
                    *(file for file,raw in files))
            completed=subprocess.run([
                sys.executable,"-m",
                "tools.verify_map02_v141_private_original_mmio_claims",
                *(str(file) for file,raw in files)],
                cwd=ROOT,capture_output=True,text=True,timeout=15,
                check=False)
            self.assertEqual(completed.returncode,2)
            self.assertEqual(completed.stdout,"")
            self.assertEqual(completed.stderr.strip(),
                "VH141_PRIVATE_EXACT_ORIGINAL_MMIO_REFUSED")
            for file,raw in files:
                self.assertNotIn(str(file),completed.stderr)

    def test_existing_native_gpu_matrix_remains_and_new_guard_runs_first(self):
        native=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        dedicated=(ROOT/".github/workflows/map02-v141-private-original-mmio.yml").read_text()
        for need in (
            "test_map02_v141_private_original_mmio_claims.py",
            "test_map02_v140_native_mmio_effects.py",
            "test_map02_v139_native_words.py",
        ):
            self.assertIn(need,native)
            self.assertIn(need,dedicated)
        self.assertIn("for mode in 04 13 22 31 40; do",native)
        self.assertIn("VH140_NATIVE_MMIO_VALUES_PASS",native)
        self.assertIn("no_retail_assets_in_ci=1",dedicated)


if __name__=="__main__":
    unittest.main()

#!/usr/bin/env python3
"""v65 local GPU producer JSONL and independently stored DMA RAM tests."""
from __future__ import annotations

from contextlib import redirect_stderr,redirect_stdout
from io import StringIO
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.ingest_map02_v65_gpu_probe import (
    SCHEMA,MAX_LOG_BYTES,audit,main,parse_observations,translate,DmaError
)
from tools.audit_map02_v64_event_journal import check_journal
from tools.make_map02_v63_state_fixture import generate
from tools.verify_map02_v60_ps1_dma import walk_dma

def make_log(ram,manifest,gp1,source_class="synthetic"):
    header={"kind":"CAPTURE_BEGIN","schema":SCHEMA,
            "source_class":source_class,"clock":"producer-monotonic-counter",
            "initial_state":"power-on-assumed"}
    events=[]
    resets={x["before_frame"]:x["word"] for x in gp1["events"]}
    tick=100
    for idx,head in enumerate(manifest["entry_points"]):
        if idx in resets:
            events.append({"kind":"GP1_WRITE","tick":tick,
                           "before_frame":idx,"word":resets[idx]})
            tick+=1
        words,_=walk_dma(ram,manifest["base_address"],head)
        events.append({"kind":"GP0_DMA2","tick":tick,
                       "frame":idx,"head":head,"words":words})
        tick+=1
    return header,events

def as_jsonl(header,events):
    return ("\n".join(json.dumps(x,sort_keys=True,separators=(",",":"))
            for x in [header]+events)+"\n").encode("utf-8")

class LocalGpuProbeTests(unittest.TestCase):
    def setUp(self):
        self.ram,self.manifest,self.gp1=generate()
        self.header,self.events=make_log(self.ram,self.manifest,self.gp1)
        self.log=as_jsonl(self.header,self.events)

    def rejected(self,header=None,events=None,ram=None,manifest=None):
        data=as_jsonl(self.header if header is None else header,
                      self.events if events is None else events)
        with self.assertRaises((DmaError,ValueError,TypeError)):
            audit(self.ram if ram is None else ram,
                  self.manifest if manifest is None else manifest,data)

    def test_producer_observation_contract(self):
        header,events=parse_observations(self.log)
        self.assertEqual(header["schema"],SCHEMA)
        self.assertEqual(len(events),6)
        self.assertEqual([e["kind"] for e in events],
                         ["GP0_DMA2","GP0_DMA2","GP1_WRITE",
                          "GP0_DMA2","GP1_WRITE","GP0_DMA2"])

    def test_all_four_dma_frames_word_equal(self):
        report=audit(self.ram,self.manifest,self.log)
        self.assertEqual(report["status"],"synthetic_probe_adapter_consistency_verified")
        self.assertEqual((report["frames"],report["ordered_events"]),(4,6))
        self.assertEqual((report["gp0_dma_submissions"],report["gp1_write_events"]),(4,2))
        self.assertTrue(report["gp0_dma_ram_word_for_word_equal"])
        self.assertTrue(report["ordered_journal_cross_audit_succeeded"])

    def test_no_provenance_promotion(self):
        out=audit(self.ram,self.manifest,self.log)
        for gate in ("producer_instrumentation_actually_installed",
                     "independent_capture_provenance_verified",
                     "gp1_write_proven_to_originate_from_hardware",
                     "original_retail_MAP02_verified",
                     "retail_gp0_provenance_verified",
                     "HD_replacement_approved",
                     "raw_gpu_payload_exported"):
            self.assertFalse(out[gate],gate)
        self.assertTrue(out["capture_log_integrity_not_authenticity"])

    def test_translates_to_v64_consistency_journal(self):
        journal,counts=translate(self.ram,self.manifest,self.log)
        self.assertEqual(check_journal(self.ram,self.manifest,journal)["dma_events"],4)
        self.assertEqual(counts["captured_gp1_reset_writes"],2)
        self.assertEqual(counts["observed_gp0_words"],
                         sum(len(e["words"]) for e in self.events if "words" in e))

    def test_e6_words_inside_ft4_not_events(self):
        journal,_=translate(self.ram,self.manifest,self.log)
        self.assertEqual(sum(e["kind"]=="GP0_DMA2" for e in journal["events"]),4)
        self.assertEqual(sum(e["kind"]=="GP1_WRITE" for e in journal["events"]),2)

    def test_relabel_as_unverified_still_not_hardware_proven(self):
        h=dict(self.header,source_class="user-supplied-unverified")
        m=dict(self.manifest,source_class="user-supplied-unverified")
        out=audit(self.ram,m,as_jsonl(h,self.events))
        self.assertEqual(out["status"],"unverified_emulator_probe_consistency_verified")
        self.assertFalse(out["gp1_write_proven_to_originate_from_hardware"])

    def test_payload_word_modified_detected_with_valid_probe_format(self):
        events=copy.deepcopy(self.events)
        events[0]["words"][0]^=1
        self.rejected(events=events)

    def test_entire_dma_payload_replaced_rejected(self):
        events=copy.deepcopy(self.events)
        events[3]["words"]=[0xe6000003]
        self.rejected(events=events)

    def test_different_capture_ram_modified_refused(self):
        blob=bytearray(self.ram)
        blob[-1]^=1
        self.rejected(ram=bytes(blob))

    def test_rehashed_ram_but_probe_payload_mismatch(self):
        blob=bytearray(self.ram)
        blob[-1]^=1
        meta=dict(self.manifest,sha256=hashlib.sha256(blob).hexdigest())
        self.rejected(ram=bytes(blob),manifest=meta)

    def test_wrong_dma_head_refused(self):
        events=copy.deepcopy(self.events)
        events[0]["head"]+=4
        self.rejected(events=events)

    def test_wrong_frame_sequence_refused(self):
        events=copy.deepcopy(self.events)
        events[0]["frame"]=1
        self.rejected(events=events)

    def test_duplicate_frame_refused(self):
        events=copy.deepcopy(self.events)
        events[1]["frame"]=0
        self.rejected(events=events)

    def test_missing_frame_refused(self):
        self.rejected(events=self.events[:-1])

    def test_gp1_after_dma_cannot_be_reinterpreted_as_before(self):
        events=copy.deepcopy(self.events)
        events[2],events[3]=events[3],events[2]
        self.rejected(events=events)

    def test_two_gp1_writes_same_boundary_refused(self):
        events=copy.deepcopy(self.events)
        events.insert(3,{"kind":"GP1_WRITE","tick":102.5,
                          "before_frame":2,"word":0})
        # Even if tick is an integer, duplicate boundary must be refused.
        for i,e in enumerate(events):e["tick"]=100+i
        self.rejected(events=events)

    def test_unrecognized_gp1_register_value_refused(self):
        events=copy.deepcopy(self.events)
        events[2]["word"]=0x02000000
        self.rejected(events=events)

    def test_private_instrumentation_cannot_claim_hw_verification(self):
        header=dict(self.header,hardware_verified=True)
        self.rejected(header=header)

    def test_private_instrumentation_cannot_claim_retail(self):
        header=dict(self.header,source_class="genuine-retail")
        self.rejected(header=header)

    def test_observation_port_typos_refused(self):
        events=copy.deepcopy(self.events)
        events[2]["kind"]="GP0_COMMAND"
        self.rejected(events=events)

    def test_unsupported_gp1_words_in_wrong_event_refused(self):
        events=copy.deepcopy(self.events)
        events[2]["words"]=[0]
        self.rejected(events=events)

    def test_extra_sensitive_metadata_refused(self):
        events=copy.deepcopy(self.events)
        events[0]["game_serial"]="secret"
        self.rejected(events=events)

    def test_bool_word_refused(self):
        events=copy.deepcopy(self.events)
        events[0]["words"][2]=True
        self.rejected(events=events)

    def test_out_of_range_word_refused(self):
        events=copy.deepcopy(self.events)
        events[0]["words"][0]=1<<32
        self.rejected(events=events)

    def test_no_observed_words_refused(self):
        events=copy.deepcopy(self.events)
        events[0]["words"]=[]
        self.rejected(events=events)

    def test_non_monotonic_observation_clock_refused(self):
        events=copy.deepcopy(self.events)
        events[1]["tick"]=events[0]["tick"]
        self.rejected(events=events)

    def test_bool_observation_clock_refused(self):
        events=copy.deepcopy(self.events)
        events[2]["tick"]=True
        self.rejected(events=events)

    def test_duplicate_key_json_refused(self):
        malicious=b'{"kind":"CAPTURE_BEGIN","kind":"CAPTURE_BEGIN"}\n'
        with self.assertRaises(DmaError):parse_observations(malicious)

    def test_missing_final_newline_refused(self):
        with self.assertRaises(DmaError):parse_observations(self.log.rstrip(b"\n"))

    def test_blank_line_refused(self):
        with self.assertRaises(DmaError):parse_observations(self.log+b"\n")

    def test_bounded_log_refused(self):
        with self.assertRaises(DmaError):parse_observations(b"x"*(MAX_LOG_BYTES+1))

    def test_empty_capture_stream_refused(self):
        with self.assertRaises(DmaError):parse_observations(b"")

    def test_no_gpu_records_refused(self):
        with self.assertRaises(DmaError):
            translate(self.ram,self.manifest,as_jsonl(self.header,[]))

    def test_sanitized_audit_does_not_export_raw_words(self):
        out=json.dumps(audit(self.ram,self.manifest,self.log))
        for bad in ("e6000003","0xe600","0x6000",'"head":',
                    '"words":',"tpage_x",
                    "gp0_sha256","before_frame","entry_points","private_gpu_ram.bin"):
            self.assertNotIn(bad,out)

    def test_cli_output_reports_only_safe_aggregates(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            ram=root/"private_gpu_ram.bin";ram.write_bytes(self.ram)
            manifest=root/"manifest.json";manifest.write_text(json.dumps(self.manifest))
            log=root/"probe.jsonl";log.write_bytes(self.log)
            output=root/"safe.json"
            buf=StringIO()
            with patch.object(sys,"argv",["v65","--ram",str(ram),"--manifest",
                                        str(manifest),"--probe",str(log),
                                        "--output",str(output)]),redirect_stdout(buf):
                self.assertEqual(main(),0)
            self.assertNotIn(str(root),buf.getvalue())
            self.assertNotIn(str(root),output.read_text())
            self.assertTrue(json.loads(output.read_text())["gp0_dma_ram_word_for_word_equal"])

    def test_cli_private_journal_is_opt_in(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            ram=root/"ram.bin";ram.write_bytes(self.ram)
            manifest=root/"meta.json";manifest.write_text(json.dumps(self.manifest))
            probe=root/"log.jsonl";probe.write_bytes(self.log)
            journal=root/"v64_private.json"
            with patch.object(sys,"argv",["v65","--ram",str(ram),"--manifest",
                                        str(manifest),"--probe",str(probe),
                                        "--private-journal-out",str(journal)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            self.assertEqual(json.loads(journal.read_text())["schema"],
                             "map02-v64-ordered-gpu-event-journal-v1")

    def test_cli_cannot_overwrite_capture_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            ram=root/"ram.bin";ram.write_bytes(self.ram)
            manifest=root/"m.json";manifest.write_text(json.dumps(self.manifest))
            probe=root/"p.jsonl";probe.write_bytes(self.log)
            with patch.object(sys,"argv",["v65","--ram",str(ram),
                  "--manifest",str(manifest),"--probe",str(probe),
                  "--output",str(ram)]),redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(),2)
            self.assertEqual(ram.read_bytes(),self.ram)

    def test_cli_cannot_use_identical_output_targets(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            ram=root/"ram.bin";ram.write_bytes(self.ram)
            manifest=root/"m.json";manifest.write_text(json.dumps(self.manifest))
            probe=root/"p.jsonl";probe.write_bytes(self.log)
            out=root/"result.json"
            with patch.object(sys,"argv",["v65","--ram",str(ram),
                  "--manifest",str(manifest),"--probe",str(probe),
                  "--output",str(out),"--private-journal-out",str(out)]),redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(),2)

    def test_cli_rejects_symlinked_probe(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            ram=root/"ram.bin";ram.write_bytes(self.ram)
            manifest=root/"m.json";manifest.write_text(json.dumps(self.manifest))
            probe=root/"real.jsonl";probe.write_bytes(self.log)
            fake=root/"link.jsonl";fake.symlink_to(probe)
            buf=StringIO()
            with patch.object(sys,"argv",["v65","--ram",str(ram),
                 "--manifest",str(manifest),"--probe",str(fake)]),redirect_stdout(buf):
                self.assertEqual(main(),1)
            self.assertEqual(json.loads(buf.getvalue())["status"],"refused")
            self.assertNotIn(str(root),buf.getvalue())

if __name__=="__main__":unittest.main()

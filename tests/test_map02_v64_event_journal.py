#!/usr/bin/env python3
"""v64 ordered GPU event journal: malformed, forged and private input tests."""
from __future__ import annotations
import copy
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.audit_map02_v64_event_journal import (
    audit,check_journal,seal_events,SCHEMA,ZERO_SHA,DmaError,main
)
from tools.make_map02_v64_event_fixture import generate
from tools.audit_map02_v63_gp0_gp1_state import interpret_capture,GP1_SCHEMA

def reseal(journal):
    j=copy.deepcopy(journal)
    records=[]
    for e in j["events"]:
        records.append({k:v for k,v in e.items()
                        if k not in ("seq","previous","digest")})
    j["events"]=seal_events(records)
    return j

class V64OrderedJournalTests(unittest.TestCase):
    def setUp(self):
        self.raw,self.meta,self.journal=generate()

    def refused(self,j,ram=None,manifest=None):
        with self.assertRaises((DmaError,ValueError,TypeError,OverflowError)):
            audit(self.raw if ram is None else ram,
                  self.meta if manifest is None else manifest,j)

    def test_four_dma_two_gp1_events(self):
        r=audit(self.raw,self.meta,self.journal)
        self.assertEqual(r["status"],"synthetic_ordered_gpu_event_journal_consistent")
        self.assertEqual((r["frames"],r["ordered_events"],r["gp0_dma_events"]),(4,6,4))
        self.assertEqual((r["gp1_full_reset_events"],r["gp1_fifo_reset_events"]),(1,1))
        self.assertEqual(r["gp0_register_updates"],13)

    def test_provenance_never_promoted(self):
        r=audit(self.raw,self.meta,self.journal)
        for f in ("gp1_write_proven_to_originate_from_hardware",
                  "independent_retail_capture_authenticity_proven",
                  "retail_gp0_provenance_verified",
                  "original_retail_MAP02_verified",
                  "HD_replacement_approved",
                  "raw_gpu_payload_exported"):
            self.assertFalse(r[f],f)
        self.assertTrue(r["unknown_unlogged_external_gpu_events_possible"])
        self.assertTrue(r["initial_gpu_state_is_assumed_not_observed"])

    def test_exact_cross_match_real_dma2_ram_words(self):
        p=check_journal(self.raw,self.meta,self.journal)
        self.assertEqual(p["dma_events"],4)
        self.assertEqual(p["journal_events"],6)
        self.assertEqual(p["gp1_events"],[{"before_frame":2,"word":0},
                                          {"before_frame":3,"word":0x01000000}])

    def test_journal_hash_chain_changes_when_modified(self):
        j=copy.deepcopy(self.journal)
        j["events"][3]["gp0_word_count"]+=1
        self.refused(j)

    def test_digest_chain_broken_previous(self):
        j=copy.deepcopy(self.journal)
        j["events"][2]["previous"]=ZERO_SHA
        self.refused(j)

    def test_digest_chain_broken_digest(self):
        j=copy.deepcopy(self.journal)
        j["events"][1]["digest"]="f"*64
        self.refused(j)

    def test_sequence_duplicate_refused_even_resealed(self):
        j=copy.deepcopy(self.journal)
        j["events"][2]["seq"]=1
        self.refused(j)

    def test_non_monotonic_tick_refused_even_resealed(self):
        j=copy.deepcopy(self.journal)
        j["events"][4]["tick"]=j["events"][3]["tick"]
        self.refused(reseal(j))

    def test_non_integer_tick_refused(self):
        j=copy.deepcopy(self.journal)
        j["events"][4]["tick"]=True
        self.refused(reseal(j))

    def test_fake_gp1_operation_refused_resealed(self):
        j=copy.deepcopy(self.journal)
        j["events"][2]["word"]=0x02000000
        self.refused(reseal(j))

    def test_gp1_after_frame_not_before_refused(self):
        j=copy.deepcopy(self.journal)
        j["events"][2]["before_frame"]=1
        self.refused(reseal(j))

    def test_gp1_wrong_port_name_refused(self):
        j=copy.deepcopy(self.journal)
        j["events"][2]["kind"]="GP0_WRITE"
        self.refused(reseal(j))

    def test_gp1_duplicate_before_same_frame_refused(self):
        j=copy.deepcopy(self.journal)
        duplicate={k:v for k,v in j["events"][2].items()
                   if k not in ("seq","previous","digest")}
        duplicate["tick"]=j["events"][2]["tick"]+1
        records=[{k:v for k,v in e.items()
                  if k not in ("seq","previous","digest")}
                 for e in j["events"]]
        records.insert(3,duplicate)
        j["events"]=seal_events(records)
        self.refused(j)

    def test_wrong_dma_head_refused_resealed(self):
        j=copy.deepcopy(self.journal)
        j["events"][0]["head"]+=4
        self.refused(reseal(j))

    def test_swapped_dma_frames_refused_resealed(self):
        j=copy.deepcopy(self.journal)
        j["events"][0],j["events"][1]=j["events"][1],j["events"][0]
        self.refused(reseal(j))

    def test_mismatched_gp0_word_count_refused_resealed(self):
        j=copy.deepcopy(self.journal)
        j["events"][0]["gp0_word_count"]+=1
        self.refused(reseal(j))

    def test_mismatched_gp0_stream_sha_refused_resealed(self):
        j=copy.deepcopy(self.journal)
        j["events"][0]["gp0_sha256"]="f"*64
        self.refused(reseal(j))

    def test_changed_raw_ram_refused(self):
        raw=bytearray(self.raw)
        raw[-1]^=1
        self.refused(self.journal,ram=bytes(raw))

    def test_changed_raw_ram_with_recomputed_manifest_refused(self):
        raw=bytearray(self.raw)
        raw[-1]^=1
        meta=dict(self.meta,sha256=hashlib.sha256(raw).hexdigest())
        self.refused(self.journal,ram=bytes(raw),manifest=meta)

    def test_journal_ram_header_claim_cannot_escape_digest(self):
        j=copy.deepcopy(self.journal)
        j["ram_sha256"]="f"*64
        self.refused(j)

    def test_extra_private_user_metadata_refused(self):
        j=copy.deepcopy(self.journal)
        j["private_game_serial"]="SLUS..."
        self.refused(j)

    def test_extra_private_event_metadata_refused(self):
        j=copy.deepcopy(self.journal)
        j["events"][2]["filepath"]="/users/private/capture.bin"
        self.refused(reseal(j))

    def test_missing_dma_event_refused(self):
        j=copy.deepcopy(self.journal)
        del j["events"][3]
        self.refused(reseal(j))

    def test_missing_gp1_still_cannot_verify_real_origin(self):
        j=copy.deepcopy(self.journal)
        j["events"]=[e for e in j["events"] if e["kind"]!="GP1_WRITE"]
        j=reseal(j)
        r=audit(self.raw,self.meta,j)
        self.assertEqual(r["gp1_full_reset_events"],0)
        self.assertFalse(r["gp1_write_proven_to_originate_from_hardware"])
        self.assertTrue(r["unknown_unlogged_external_gpu_events_possible"])

    def test_self_resealed_forgery_remains_unverified(self):
        # A malicious writer can change GP1(00) to GP1(01), recompute
        # all journal hashes, and still pass a structural consistency
        # check. This explicitly tests the limit of digest chaining.
        j=copy.deepcopy(self.journal)
        j["events"][2]["word"]=0x01000000
        r=audit(self.raw,self.meta,reseal(j))
        self.assertEqual(r["gp1_full_reset_events"],0)
        self.assertEqual(r["gp1_fifo_reset_events"],2)
        self.assertFalse(r["gp1_write_proven_to_originate_from_hardware"])

    def test_source_class_forgery_refused(self):
        j=copy.deepcopy(self.journal)
        j["source_class"]="verified-original-retail"
        self.refused(j)

    def test_user_supplied_relabel_not_retail_verified(self):
        j=copy.deepcopy(self.journal)
        m=dict(self.meta,source_class="user-supplied-unverified")
        j["source_class"]="user-supplied-unverified"
        r=audit(self.raw,m,j)
        self.assertEqual(r["status"],"unverified_ordered_gpu_event_journal_consistent")
        self.assertFalse(r["independent_retail_capture_authenticity_proven"])

    def test_bogus_initial_state_refused(self):
        j=copy.deepcopy(self.journal)
        j["initial_state"]="retail-hardware-proven"
        self.refused(j)

    def test_bad_schema_refused(self):
        j=copy.deepcopy(self.journal)
        j["schema"]="VHT1"
        self.refused(j)

    def test_bad_hash_lowercase_refused(self):
        j=copy.deepcopy(self.journal)
        j["events"][0]["gp0_sha256"]=j["events"][0]["gp0_sha256"].upper()
        self.refused(reseal(j))

    def test_sanitized_output_has_no_ports_or_dma_addresses(self):
        s=json.dumps(audit(self.raw,self.meta,self.journal))
        for bad in ("0xe600","e6000001","0x6000","head","gp0_sha256",
                    "frame_indices","before_frame","private_game_serial",
                    "tpage_x","gp1_sidecar"):
            self.assertNotIn(bad,s)

    def test_cli_writes_sanitized_output_only(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            ram=root/"secret-ram.bin";ram.write_bytes(self.raw)
            m=root/"m.json";m.write_text(json.dumps(self.meta))
            j=root/"j.json";j.write_text(json.dumps(self.journal))
            out=root/"sanitized.json"
            output=StringIO()
            with patch.object(sys,"argv",["v64","--ram",str(ram),
                          "--manifest",str(m),"--journal",str(j),
                          "--output",str(out)]),redirect_stdout(output):
                self.assertEqual(main(),0)
            data=json.loads(out.read_text())
            self.assertEqual(data["status"],"synthetic_ordered_gpu_event_journal_consistent")
            self.assertNotIn(str(root),out.read_text())
            self.assertNotIn(str(root),output.getvalue())

    def test_cli_rejects_capture_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            ram=root/"ram.bin";ram.write_bytes(self.raw)
            m=root/"m.json";m.write_text(json.dumps(self.meta))
            j=root/"j.json";j.write_text(json.dumps(self.journal))
            with patch.object(sys,"argv",["v64","--ram",str(ram),"--manifest",str(m),
                           "--journal",str(j),"--output",str(ram)]),redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(main(),2)
            self.assertEqual(ram.read_bytes(),self.raw)

    def test_cli_refuses_bad_digest_with_private_safe_error(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            ram=root/"private-ram.bin";ram.write_bytes(self.raw)
            m=root/"m.json";m.write_text(json.dumps(self.meta))
            j=root/"j.json"
            bad=copy.deepcopy(self.journal)
            bad["events"][0]["gp0_sha256"]="0"*64
            j.write_text(json.dumps(bad))
            output=StringIO()
            with patch.object(sys,"argv",["v64","--ram",str(ram),
                          "--manifest",str(m),"--journal",str(j)]),redirect_stdout(output):
                self.assertEqual(main(),1)
            self.assertEqual(json.loads(output.getvalue())["status"],"refused")
            self.assertNotIn(str(root),output.getvalue())

if __name__=="__main__":
    unittest.main()

#!/usr/bin/env python3
"""v67 mutable per-DMA PS1 RAM and GP0/GP1 observed-stream tests."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from io import StringIO
from contextlib import redirect_stdout,redirect_stderr

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.make_map02_v63_state_fixture import generate
from tools.ingest_map02_v65_gpu_probe import SCHEMA as PROBE_SCHEMA
from tools.verify_map02_v60_ps1_dma import walk_dma,DmaError
from tools.audit_map02_v67_versioned_ram import (
    RAM_BYTES,SCHEMA,manifest_for_frames,check_manifest,audit,read_snapshots,main,
)

def cases():
    initial, old, gp1=generate()
    base=old["base_address"]
    mutable=bytearray(RAM_BYTES)
    mutable[base:base+len(initial)]=initial
    heads=old["entry_points"]
    observations=[{"kind":"CAPTURE_BEGIN","schema":PROBE_SCHEMA,
                   "source_class":"user-supplied-unverified",
                   "clock":"producer-monotonic-counter",
                   "initial_state":"power-on-assumed"}]
    versions=[]
    tick=100
    for i,head in enumerate(heads):
        if i in (1,3):
            pointer=struct.unpack_from("<I",mutable,head)[0]&0xffffff
            mutable[pointer+8]^=1
        versions.append(bytes(mutable))
        if i==2 or i==3:
            observations.append({"kind":"GP1_WRITE","tick":tick,
                                 "before_frame":i,
                                 "word":0 if i==2 else 0x01000000})
            tick+=1
        words,_=walk_dma(versions[i],0,head)
        observations.append({"kind":"GP0_DMA2","tick":tick,
                             "frame":i,"head":head,"words":words})
        tick+=1
    raw=("\n".join(json.dumps(x,sort_keys=True) for x in observations)+"\n").encode()
    return versions,manifest_for_frames(versions,"user-supplied-unverified"),raw,observations

class VersionedRamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.versions,cls.manifest,cls.probe,cls.records=cases()

    def reject(self,versions=None,meta=None,probe=None):
        with self.assertRaises((DmaError,ValueError,TypeError)):
            audit(self.versions if versions is None else versions,
                  self.manifest if meta is None else meta,
                  self.probe if probe is None else probe)

    def as_log(self,records):
        return ("\n".join(json.dumps(x,sort_keys=True) for x in records)+"\n").encode()

    def test_four_capture_versions_with_mutation(self):
        p=audit(self.versions,self.manifest,self.probe)
        self.assertEqual(p["frames"],4)
        self.assertEqual(p["observed_gp0_words"],80)
        self.assertEqual(p["gp1_events"],2)
        self.assertEqual(p["gp1_full_reset_events"],1)
        self.assertEqual(p["gp1_fifo_reset_events"],1)
        self.assertEqual(p["gp0_register_updates"],13)

    def test_actual_ram_snapshots_vary(self):
        p=audit(self.versions,self.manifest,self.probe)
        self.assertEqual(p["unique_ram_versions"],3)
        self.assertTrue(p["multiple_distinct_ram_versions_observed"])
        self.assertNotEqual(self.versions[0],self.versions[1])
        self.assertEqual(self.versions[1],self.versions[2])
        self.assertNotEqual(self.versions[2],self.versions[3])

    def test_exact_each_frame_matching_words(self):
        p=audit(self.versions,self.manifest,self.probe)
        self.assertTrue(p["per_dma_ram_snapshot_gp0_words_equal"])
        self.assertTrue(p["cross_dma_gpu_state_carried_or_gp1_reset_applied"])

    def test_retailability_gates_never_promoted(self):
        p=audit(self.versions,self.manifest,self.probe)
        for key in ("full_emulator_runtime_boot_verified",
                    "gpu_plugin_gp0_fifo_consumption_verified",
                    "producer_instrumentation_actually_installed",
                    "gp1_write_proven_to_originate_from_hardware",
                    "retail_gp0_provenance_verified",
                    "original_retail_MAP02_verified",
                    "HD_replacement_approved","raw_gpu_payload_exported"):
            self.assertFalse(p[key],key)

    def test_original_v65_one_snapshot_cannot_validate_later_changes(self):
        from tools.ingest_map02_v65_gpu_probe import audit as old_audit
        old=self.versions[-1]
        meta={"format":"ps1-dma2-linked-list-ram-v1",
              "source_class":"user-supplied-unverified",
              "base_address":0,"entry_points":[e["head"] for e in self.records
                      if e["kind"]=="GP0_DMA2"],
              "sha256":hashlib.sha256(old).hexdigest()}
        with self.assertRaises(DmaError):
            old_audit(old,meta,self.probe)

    def test_swapped_snapshot_order_refused(self):
        snapshots=list(self.versions)
        snapshots[0],snapshots[3]=snapshots[3],snapshots[0]
        self.reject(versions=snapshots)

    def test_swapped_snapshot_order_even_rehashed_refused(self):
        snapshots=list(self.versions)
        snapshots[0],snapshots[3]=snapshots[3],snapshots[0]
        updated=manifest_for_frames(snapshots,"user-supplied-unverified")
        self.reject(versions=snapshots,meta=updated)

    def test_single_corrupt_byte_hash_refused(self):
        snapshots=list(self.versions)
        b=bytearray(snapshots[0]); b[123]^=1
        snapshots[0]=bytes(b)
        self.reject(versions=snapshots)

    def test_rehashed_corrupt_gpu_payload_refused(self):
        snapshots=list(self.versions)
        b=bytearray(snapshots[0])
        head=self.records[1]["head"]
        ptr=struct.unpack_from("<I",b,head)[0]&0xffffff
        b[ptr+8]^=1
        snapshots[0]=bytes(b)
        self.reject(versions=snapshots,
                    meta=manifest_for_frames(snapshots,"user-supplied-unverified"))

    def test_modified_probe_word_refused(self):
        records=copy.deepcopy(self.records)
        dma=next(x for x in records if x["kind"]=="GP0_DMA2")
        dma["words"][1]^=1
        self.reject(probe=self.as_log(records))

    def test_changed_head_refused(self):
        records=copy.deepcopy(self.records)
        dma=next(x for x in records if x["kind"]=="GP0_DMA2")
        dma["head"]+=4
        self.reject(probe=self.as_log(records))

    def test_dangling_gp1_refused(self):
        records=copy.deepcopy(self.records[:-1])
        self.reject(probe=self.as_log(records))

    def test_wrong_gp1_opcode_refused(self):
        records=copy.deepcopy(self.records)
        gp1=next(x for x in records if x["kind"]=="GP1_WRITE")
        gp1["word"]=0x02000000
        self.reject(probe=self.as_log(records))

    def test_forged_reset_remains_unverified(self):
        records=copy.deepcopy(self.records)
        gp1=next(x for x in records if x["kind"]=="GP1_WRITE")
        gp1["word"]=0x01000000
        p=audit(self.versions,self.manifest,self.as_log(records))
        self.assertEqual(p["gp1_full_reset_events"],0)
        self.assertEqual(p["gp1_fifo_reset_events"],2)
        self.assertFalse(p["gp1_write_proven_to_originate_from_hardware"])

    def test_duplicate_gp1_refused(self):
        records=copy.deepcopy(self.records)
        gp1=next(x for x in records if x["kind"]=="GP1_WRITE")
        extra=dict(gp1)
        extra["tick"]=gp1["tick"]+1
        records.insert(records.index(gp1)+1,extra)
        for i,item in enumerate(records[1:]): item["tick"]=100+i
        self.reject(probe=self.as_log(records))

    def test_nonmonotonic_ticks_refused(self):
        records=copy.deepcopy(self.records)
        records[2]["tick"]=records[1]["tick"]
        self.reject(probe=self.as_log(records))

    def test_invalid_frame_sha_refused(self):
        meta=copy.deepcopy(self.manifest)
        meta["frame_sha256"][1]="0"*64
        self.reject(meta=meta)

    def test_false_retail_source_refused(self):
        meta=copy.deepcopy(self.manifest)
        meta["source_class"]="authenticated-retail"
        self.reject(meta=meta)

    def test_extraneous_manifest_fields_refused(self):
        meta=copy.deepcopy(self.manifest)
        meta["retail_proven"]=True
        self.reject(meta=meta)

    def test_frame_count_mismatch_refused(self):
        meta=copy.deepcopy(self.manifest)
        meta["frame_sha256"]=meta["frame_sha256"][:-1]
        self.reject(meta=meta)

    def test_nonstandard_ram_size_refused(self):
        meta=copy.deepcopy(self.manifest)
        meta["ram_size"]=RAM_BYTES//2
        self.reject(meta=meta)

    def test_aliased_bool_base_refused(self):
        meta=copy.deepcopy(self.manifest)
        meta["base_address"]=False
        self.reject(meta=meta)

    def test_no_gp0_frames_refused(self):
        self.reject(probe=self.as_log(self.records[:1]))

    def test_mutable_capture_manifest_is_not_authentication(self):
        meta=manifest_for_frames(self.versions,"synthetic")
        self.assertEqual(meta["schema"],SCHEMA)
        self.assertEqual(meta["ram_size"],RAM_BYTES)
        self.assertEqual(meta["base_address"],0)
        self.assertEqual(len(meta["frame_sha256"]),4)

    def test_local_per_frame_file_reader(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for i,v in enumerate(self.versions):
                (root/f"frame-{i:06d}.ram").write_bytes(v)
            self.assertEqual(read_snapshots(root,4),self.versions)

    def test_symlink_snapshot_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"real.ram").write_bytes(self.versions[0])
            (root/"frame-000000.ram").symlink_to(root/"real.ram")
            with self.assertRaises(DmaError):read_snapshots(root,1)

    def test_partial_snapshot_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"frame-000000.ram").write_bytes(b"x"*100)
            with self.assertRaises(DmaError):read_snapshots(root,1)

    def test_missing_capture_frame_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(DmaError):read_snapshots(Path(d),1)

    def test_cli_manifest_generation_then_audit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            snaps=root/"private";snaps.mkdir()
            for i,v in enumerate(self.versions):
                (snaps/f"frame-{i:06d}.ram").write_bytes(v)
            log=root/"event.jsonl";log.write_bytes(self.probe)
            meta=root/"manifest.json"
            output=root/"report.json"
            with patch.object(sys,"argv",["v67","--snapshot-dir",str(snaps),
                            "--frames","4","--make-manifest",str(meta)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            with patch.object(sys,"argv",["v67","--snapshot-dir",str(snaps),
                            "--manifest",str(meta),"--probe",str(log),
                            "--output",str(output)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),0)
            report=json.loads(output.read_text())
            self.assertEqual(report["status"],"unverified_versioned_ram_consistent")
            self.assertEqual(report["unique_ram_versions"],3)
            self.assertNotIn(str(root),output.read_text())

    def test_cli_refuses_overwrite_existing_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"frame-000000.ram").write_bytes(self.versions[0])
            dest=root/"manifest.json";dest.write_text("PRIVATE")
            with patch.object(sys,"argv",["v67","--snapshot-dir",str(root),
                            "--frames","1","--make-manifest",str(dest)]),redirect_stdout(StringIO()):
                self.assertEqual(main(),1)
            self.assertEqual(dest.read_text(),"PRIVATE")

    def test_cli_refuses_corrupt_probe_and_sanitizes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); snaps=root/"snaps";snaps.mkdir()
            for i,v in enumerate(self.versions):
                (snaps/f"frame-{i:06d}.ram").write_bytes(v)
            meta=root/"meta.json";meta.write_text(json.dumps(self.manifest))
            log=root/"probe.jsonl";log.write_bytes(b"CORRUPT\n")
            captured=StringIO()
            with patch.object(sys,"argv",["v67","--snapshot-dir",str(snaps),
                            "--manifest",str(meta),"--probe",str(log)]),redirect_stdout(captured):
                self.assertEqual(main(),1)
            out=json.loads(captured.getvalue())
            self.assertEqual(out["status"],"refused")
            self.assertNotIn(str(root),captured.getvalue())

if __name__=="__main__":
    unittest.main()

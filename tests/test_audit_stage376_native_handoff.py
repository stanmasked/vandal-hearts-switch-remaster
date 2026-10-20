"""Stage376 host-only synthetic controls; never evidence of guest/hardware audio."""
from __future__ import annotations
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import audit_stage376_native_handoff as gate

class Stage376Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.meta=self.root/"metadata"
        self.meta.mkdir()
        binary=bytearray(0x280)
        binary[0x10:0x14]=b"NRO0"
        struct.pack_into("<I",binary,0x18,0x200)
        for field,off,size in ((0x20,0,0x100),(0x28,0x100,0x80),(0x30,0x180,0x80)):
            struct.pack_into("<II",binary,field,off,size)
        self.nro=bytes(binary)
        self.nro_sha=gate.sha(self.nro)
        self.archive=self.root/"source.zip"
        self.rezip()
        self.write_meta()

    def rezip(self, extra=None):
        with zipfile.ZipFile(self.archive,"w",compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(gate.NRO_NAME,self.nro)
            z.writestr(gate.HASH_NAME,f"{self.nro_sha}  build/{gate.NRO_NAME}\n")
            if extra is not None:
                z.writestr(*extra)
        self.archive_sha=gate.sha(self.archive.read_bytes())

    def put(self,name,record):
        (self.meta/name).write_text(json.dumps(record),encoding="utf-8")

    def make_run(self,id,name=None,conclusion="success"):
        result={"id":id,"name":name,"status":"completed","conclusion":conclusion,
                "head_sha":gate.HEAD,"event":"pull_request","run_attempt":1,
                "repository":{"full_name":gate.REPO}}
        return result

    def write_meta(self):
        self.put("integrated-run.json",self.make_run(gate.SOURCE_RUN))
        self.put("integrated-jobs.json",{"jobs":[{"name":"Build tactical framebuffer game with nonblocking libnx audout",
             "run_id":gate.SOURCE_RUN,"status":"completed","conclusion":"success"}]})
        self.put("integrated-artifact.json",{"id":gate.SOURCE_ARTIFACT,
            "name":gate.SOURCE_ARTIFACT_NAME,"digest":"sha256:"+self.archive_sha,
            "size_in_bytes":self.archive.stat().st_size,"expired":False,
            "workflow_run":{"id":gate.SOURCE_RUN,"head_sha":gate.HEAD}})
        for label,(run_id,name) in gate.NATIVE_JOBS.items():
            self.put(label+"-run.json",self.make_run(run_id,name=name))
        self.put("optional-sdl2-run.json",self.make_run(gate.SDL2_RUN,conclusion="failure"))

    def check(self):
        return gate.audit(self.archive,self.meta,archive_sha=self.archive_sha,
            nro_sha=self.nro_sha,nro_size=len(self.nro),nro_declared=0x200)

    def test_synthetic_correct_metadata_bytes_and_red_optional(self):
        report=self.check()
        self.assertEqual(report["result"],gate.RESULT)
        self.assertEqual(len(report["independent_native_ci"]),4)
        self.assertEqual(report["hardware_status"],"HARDWARE NOT TESTED")
        self.assertEqual(report["optional_sdl2"]["status"],"FAILED_EXTERNAL_DEPENDENCY_NOT_RECLASSIFIED")

    def test_wrong_head_sha_rejected(self):
        run=self.make_run(gate.SOURCE_RUN)
        run["head_sha"]="0"*40
        self.put("integrated-run.json",run)
        with self.assertRaises(gate.AuditError):self.check()

    def test_pending_guest_ci_not_accepted_as_success(self):
        run=self.make_run(gate.NATIVE_JOBS["stage374"][0],gate.NATIVE_JOBS["stage374"][1],"pending")
        self.put("stage374-run.json",run)
        with self.assertRaises(gate.AuditError):self.check()

    def test_optional_failure_cannot_be_disguised_as_green(self):
        self.put("optional-sdl2-run.json",self.make_run(gate.SDL2_RUN,conclusion="success"))
        with self.assertRaises(gate.AuditError):self.check()

    def test_source_artifact_digest_mismatch_rejected(self):
        item=json.loads((self.meta/"integrated-artifact.json").read_text())
        item["digest"]="sha256:"+"0"*64
        self.put("integrated-artifact.json",item)
        with self.assertRaises(gate.AuditError):self.check()

    def test_duplicate_or_extra_zip_member_rejected(self):
        self.rezip(extra=(gate.NRO_NAME,b"bogus"))
        self.write_meta()
        with self.assertRaises(gate.AuditError):self.check()

    def test_truncated_nro_rejected_even_when_source_hashes_self_consistent(self):
        self.nro=self.nro[:0x180]
        self.nro_sha=gate.sha(self.nro)
        self.rezip()
        self.write_meta()
        with self.assertRaises(gate.AuditError):self.check()

    def test_corrupted_nro_segment_structure_rejected(self):
        data=bytearray(self.nro)
        struct.pack_into("<II",data,0x30,0x150,0xB0)
        self.nro=bytes(data)
        self.nro_sha=gate.sha(self.nro)
        self.rezip()
        self.write_meta()
        with self.assertRaises(gate.AuditError):self.check()

    def test_symlink_input_rejected(self):
        new=self.root/"redirect.zip"
        new.symlink_to(self.archive)
        with self.assertRaises(gate.AuditError):
            gate.audit(new,self.meta,archive_sha=self.archive_sha,
                nro_sha=self.nro_sha,nro_size=len(self.nro),nro_declared=0x200)

    def test_missing_provenance_job_fails_closed(self):
        item=json.loads((self.meta/"integrated-jobs.json").read_text())
        item["jobs"]=[]
        self.put("integrated-jobs.json",item)
        with self.assertRaises(gate.AuditError):self.check()

if __name__=="__main__":unittest.main()
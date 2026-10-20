"""Pure Python controls; synthetic binaries are NOT NeXium and not guest tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import audit_stage384_nexium_binary_provenance as m

HEAD="1"*40
RUN=12345

class Stage384Tests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.release=self.root/"release.json"
        self.archive=self.root/"nexium-linux-x86_64.tar.gz"
        self.binary=self.root/"nexium-gui"
        self.receipt=self.root/"receipt.json"
        self.archive.write_bytes(b"TEST-TAR-ARCHIVE")
        self.binary.write_bytes(b"TEST-EXECUTABLE")
        self.binary.chmod(0o755)
        self.meta={"id":55,"tag_name":"nightly","assets":[{
            "id":200,"state":"uploaded","name":m.ASSET,
            "size":len(self.archive.read_bytes()),
            "digest":"sha256:"+m.digest(self.archive.read_bytes())}]}
        self.sync_release()
    def sync_release(self):
        self.release.write_text(json.dumps(self.meta),encoding="utf-8")
    def make(self):
        return m.make_receipt(self.release,self.archive,self.binary,run_id=RUN,head=HEAD)
    def receipt_file(self):
        self.receipt.write_text(json.dumps(self.make())+"\n")
    def test_valid_asset_binary_one_run_then_verify(self):
        self.receipt_file()
        outcome=m.verify_receipt(self.receipt,self.archive,self.binary,run_id=RUN,head=HEAD)
        self.assertEqual(outcome["result"],"STAGE384_SAME_NEXIUM_BINARY_BEFORE_AND_AFTER_GUEST_RUN")
        self.assertFalse(self.make()["same_binary_in_historical_runs_proven"])
    def test_no_advertised_asset_hash_still_identifies_actual_bytes(self):
        self.meta["assets"][0]["digest"]=None;self.sync_release()
        r=self.make()
        self.assertFalse(r["advertised_asset_digest_checked"])
        self.assertEqual(r["asset_sha256"],m.digest(self.archive.read_bytes()))
    def test_reject_wrong_asset_sha(self):
        self.meta["assets"][0]["digest"]="sha256:"+"0"*64;self.sync_release()
        with self.assertRaises(m.ProvenanceError):self.make()
    def test_reject_wrong_asset_size(self):
        self.meta["assets"][0]["size"]+=1;self.sync_release()
        with self.assertRaises(m.ProvenanceError):self.make()
    def test_reject_missing_and_duplicate_release_asset(self):
        self.meta["assets"]=[];self.sync_release()
        with self.assertRaises(m.ProvenanceError):self.make()
        self.meta["assets"]=self.meta["assets"]+[{
            "id":2,"name":m.ASSET,"state":"uploaded","size":len(self.archive.read_bytes())}]*2
        self.sync_release()
        with self.assertRaises(m.ProvenanceError):self.make()
    def test_mutated_binary_after_guest_rejected(self):
        self.receipt_file();self.binary.write_bytes(b"MUTATED-BINARY")
        with self.assertRaises(m.ProvenanceError):
            m.verify_receipt(self.receipt,self.archive,self.binary,run_id=RUN,head=HEAD)
    def test_mutated_archive_after_guest_rejected(self):
        self.receipt_file();self.archive.write_bytes(b"MUTATED-ARCHIVE")
        with self.assertRaises(m.ProvenanceError):
            m.verify_receipt(self.receipt,self.archive,self.binary,run_id=RUN,head=HEAD)
    def test_other_run_head_rejected(self):
        self.receipt_file()
        for run,head in [(RUN+1,HEAD),(RUN,"2"*40)]:
            with self.subTest(run=run,head=head),self.assertRaises(m.ProvenanceError):
                m.verify_receipt(self.receipt,self.archive,self.binary,run_id=run,head=head)
    def test_reject_symlink_binary_archive_or_receipt(self):
        for kind in ("binary","archive"):
            with self.subTest(kind=kind):
                obj=getattr(self,kind)
                safe=self.root/(kind+".safe")
                obj.rename(safe)
                obj.symlink_to(safe)
                with self.assertRaises(m.ProvenanceError):self.make()
                obj.unlink();safe.rename(obj)
        self.receipt_file();old=self.root/"receipt.original"
        self.receipt.rename(old);self.receipt.symlink_to(old)
        with self.assertRaises(m.ProvenanceError):
            m.verify_receipt(self.receipt,self.archive,self.binary,run_id=RUN,head=HEAD)
    def test_reject_false_cross_run_hardware_claim(self):
        doc=self.make();doc["same_binary_in_historical_runs_proven"]=True
        self.receipt.write_text(json.dumps(doc))
        with self.assertRaises(m.ProvenanceError):
            m.verify_receipt(self.receipt,self.archive,self.binary,run_id=RUN,head=HEAD)
    def test_cli_refuses_overwrite(self):
        self.receipt.write_text("already-existing")
        result=m.main(["create","--release",str(self.release),"--archive",str(self.archive),
               "--binary",str(self.binary),"--receipt",str(self.receipt),
               "--run-id",str(RUN),"--head",HEAD])
        self.assertEqual(result,2)
        self.assertEqual(self.receipt.read_text(),"already-existing")
    def test_invalid_source_run_rejected(self):
        with self.assertRaises(m.ProvenanceError):
            m.make_receipt(self.release,self.archive,self.binary,run_id=-1,head=HEAD)
        with self.assertRaises(m.ProvenanceError):
            m.make_receipt(self.release,self.archive,self.binary,run_id=RUN,head="bad")

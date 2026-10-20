#!/usr/bin/env python3
"""Stage368 strict future guest same-directory CSV parser negative controls."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import audit_nexium_stage368_wait_descriptor as a

def make_sources(directory,code=7,raw=0,count=1,present=1,same=1):
    directory.mkdir(parents=True,exist_ok=True)
    acquired,released,abandoned=(1438,1438,0) if code==7 else (1414,1413,1)
    rows={
      "reason":[1,code,int(code!=0),int(code==7),int(code>=3),
                acquired,released,abandoned],
      "result":[1,int(code>=4),raw,code],
      "descriptor":[1,int(code>=4),raw,count,present,same,code,1],
    }
    for kind,numbers in rows.items():
        blob="scope,value\n"+"".join(f"{label},{num}\n" for label,num in zip(a.LABELS[kind],numbers))
        (directory/a.NAMES[kind]).write_text(blob)
    return directory

class Stage368Audit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.csv=make_sources(self.root/"guest")
    def test_synthetic_success_is_not_authentic_archive(self):
        r=a.audit_directory(self.root)
        self.assertEqual(r["result"],a.VERDICT)
        self.assertEqual(r["reported_released_count"],1)
        self.assertFalse(r["original_neXium_archive_proven"])
        self.assertFalse(r["old_0xEA01_cause_proven"])
    def test_timeout_result_preserved_without_queue_claim(self):
        make_sources(self.csv,4,0xEA01,0,0,0)
        r=a.audit_directory(self.root)
        self.assertEqual(r["raw_wait_result"],0xEA01)
        self.assertEqual(r["reported_released_count"],0)
        self.assertFalse(r["actual_queue_depth_measured"])
    def test_no_wait_is_explicit_unknown_count(self):
        make_sources(self.csv,0,0,0,0,0)
        r=a.audit_directory(self.root)
        self.assertIsNone(r["reported_released_count"])
        self.assertIsNone(r["returned_pointer_present"])
    def test_forged_cross_source_result_or_reason_rejected(self):
        for kind,old,new in (
            ("result","audout_wait_result_raw,0","audout_wait_result_raw,59905"),
            ("descriptor","stage351_tail_reason_code,7","stage351_tail_reason_code,4"),
            ("descriptor","stage357_raw_result_crosschecked,1","stage357_raw_result_crosschecked,0"),
        ):
            with self.subTest(kind=kind):
                path=self.csv/a.NAMES[kind]
                content=path.read_text()
                self.assertIn(old,content)
                path.write_text(content.replace(old,new))
                with self.assertRaises(ValueError):
                    a.audit_directory(self.root)
                path.write_text(content)
    def test_forbidden_release_and_pointer_claims_rejected(self):
        for old,new in (
            ("released_count_reported,1","released_count_reported,0"),
            ("returned_pointer_matches_submitted,1","returned_pointer_matches_submitted,0"),
            ("returned_pointer_present,1","returned_pointer_present,0"),
            ("released_count_reported,1","released_count_reported,4294967296"),
        ):
            with self.subTest(old=old,new=new):
                f=self.csv/a.NAMES["descriptor"]
                content=f.read_text()
                f.write_text(content.replace(old,new))
                with self.assertRaises(ValueError):
                    a.audit_directory(self.root)
                f.write_text(content)
    def test_noncanonical_bytes_rejected(self):
        f=self.csv/a.NAMES["descriptor"]
        original=f.read_bytes()
        for bad in (original.replace(b"scope,value\n",b"scope,value\r\n"),
                    original.replace(b"released_count_reported,1",b"released_count_reported,01"),
                    original+b"extra,1\n",
                    original.replace(b"returned_pointer_present,1",b"returned_pointer_present,-1")):
            f.write_bytes(bad)
            with self.assertRaises(ValueError):
                a.audit_directory(self.root)
        f.write_bytes(original)
    def test_duplicate_and_cross_directory_source_rejected(self):
        other=self.root/"other";other.mkdir()
        source=self.csv/a.NAMES["descriptor"]
        (other/a.NAMES["descriptor"]).write_bytes(source.read_bytes())
        with self.assertRaises(ValueError):
            a.audit_directory(self.root)
        (other/a.NAMES["descriptor"]).unlink()
        (other/a.NAMES["result"]).write_bytes((self.csv/a.NAMES["result"]).read_bytes())
        (self.csv/a.NAMES["result"]).unlink()
        with self.assertRaises(ValueError):
            a.audit_directory(self.root)
    def test_symlink_rejected(self):
        f=self.csv/a.NAMES["descriptor"]
        data=f.read_bytes()
        f.unlink()
        target=self.root/"outside.csv"
        target.write_bytes(data)
        f.symlink_to(target)
        with self.assertRaises(ValueError):
            a.audit_directory(self.root)
if __name__=="__main__":
    unittest.main()

#!/usr/bin/env python3
"""Reproducible, isolated NeXium SD trace provenance regressions."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"tools"))
from audit_nexium_guest_sd_handoff import run,TraceError

class TestGuestSdHandoff(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.run_id="12345"
        self.sd_root=self.root/f"vh-nexium-stage266-{self.run_id}"
        self.guest=self.sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
        self.guest.mkdir(parents=True)
        self.receipt=self.root/"guest-sd-root.txt"
        self.receipt.write_text(str(self.sd_root)+"\n")
        self.evidence=self.root/"runtime-evidence"
        self.evidence.mkdir()

    def csv_data(self, scenes=(2,1,2,1), dropped=0):
        lines=["index,event,serial,scene,monotonic_ns,dropped_total"]
        index=0
        for serial,scene in enumerate(scenes,1):
            t=serial*100_000_000
            for event,offset in (("INPUT",0),("POST",100_000),
                                 ("ACCEPT",200_000),
                                 ("SUBMIT_CALL",250_000),
                                 ("RELEASE_RETURN",8_000_000)):
                lines.append(f"{index},{event},{serial},{scene},{t+offset},{dropped}")
                index+=1
        return ("\n".join(lines)+"\n").encode("ascii")

    def write_csv(self,data=None,name="audio-scene-trace-0000.csv"):
        path=self.guest/name
        path.write_bytes(data if data is not None else self.csv_data())
        return path

    def test_verified_four_transitions_and_exact_copy(self):
        data=self.csv_data()
        self.write_csv(data)
        result=run(self.receipt,self.evidence,self.root,self.run_id)
        self.assertEqual(result["result"],"FOUR_GUEST_SCENE_INTERNAL_PHASES_OBSERVED")
        self.assertEqual(len(result["trace_audit"]["complete_scene_serials"]),4)
        self.assertEqual((self.evidence/"guest-scene-trace.csv").read_bytes(),data)
        self.assertIsNone(result["actual_input_to_dac_latency_ms"])
        self.assertEqual(result["hardware_status"],"HARDWARE NOT TESTED")
        with self.assertRaises(TraceError):
            run(self.receipt,self.evidence,self.root,self.run_id)

    def test_missing_file_or_only_incomplete_temp_not_observed(self):
        with self.assertRaises(TraceError):
            run(self.receipt,self.evidence,self.root,self.run_id)
        (self.guest/"audio-scene-trace-0000.tmp").write_bytes(self.csv_data())
        with self.assertRaises(TraceError):
            run(self.receipt,self.evidence,self.root,self.run_id)

    def test_dropped_or_incorrect_scene_order_fails(self):
        self.write_csv(self.csv_data(dropped=1))
        with self.assertRaises(TraceError):
            run(self.receipt,self.evidence,self.root,self.run_id)
        self.write_csv(self.csv_data(scenes=(2,1,1,2)))
        with self.assertRaises(TraceError):
            run(self.receipt,self.evidence,self.root,self.run_id)

    def test_duplicate_and_corrupt_sd_csv_rejected(self):
        self.write_csv()
        self.write_csv(name="audio-scene-trace-0001.csv")
        with self.assertRaises(TraceError):
            run(self.receipt,self.evidence,self.root,self.run_id)
        (self.guest/"audio-scene-trace-0001.csv").unlink()
        self.write_csv(self.csv_data()[:-3])
        with self.assertRaises(TraceError):
            run(self.receipt,self.evidence,self.root,self.run_id)

    def test_wrong_root_and_symlink_rejected(self):
        self.write_csv()
        self.receipt.write_text(str(self.root/"other") + "\n")
        with self.assertRaises(TraceError):
            run(self.receipt,self.evidence,self.root,self.run_id)
        self.receipt.write_text(str(self.sd_root)+"\n")
        path=self.guest/"audio-scene-trace-0000.csv"
        path.unlink()
        path.symlink_to(self.receipt)
        with self.assertRaises(TraceError):
            run(self.receipt,self.evidence,self.root,self.run_id)

if __name__=="__main__":
    unittest.main()

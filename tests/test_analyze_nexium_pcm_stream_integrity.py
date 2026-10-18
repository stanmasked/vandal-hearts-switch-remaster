"""Stage299 synthetic PCM continuity indicators and negative integrity tests."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import analyze_nexium_pcm_stream_integrity as s


class VirtualPcmStreamIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir=Path(self.temp.name)
        self.monitor=self.dir/"monitor.pcm"
        self.scenes=self.dir/"scene.pcm"
        self.markers=self.dir/"markers.csv"
        self.write_pcm(self.monitor,[(100,-100)]*960)
        self.write_pcm(self.scenes,[(200,-150)]*1920)
        self.write_events()

    def write_pcm(self,path,frames):
        path.write_bytes(b"".join(struct.pack("<hh",*x) for x in frames))

    def ref(self,path,kind):
        data=path.read_bytes()
        frames=len(data)//4
        if kind=="monitor":
            return {
                "schema":"vh-nexium-pcm-quality/v1",
                "pcm_sha256":hashlib.sha256(data).hexdigest(),
                "format":"s16le stereo 48000 Hz",
                "hardware_status":"HARDWARE NOT TESTED",
                "bytes":len(data),"frames":frames,
                "duration_seconds":round(frames/48000,3),
                "audible_music_confirmed":False,
                "original_soundtrack_confirmed":False,
            }
        return {
            "schema":"vh-nexium-scene-audio/v1",
            "pcm_sha256":hashlib.sha256(data).hexdigest(),
            "format":"s16le stereo 48000 Hz",
            "hardware_status":"HARDWARE NOT TESTED",
            "pcm_duration_seconds":round(frames/48000,3),
            "offset_accuracy":"HOST_BUFFERED_APPROXIMATE_NOT_GUEST_TIMESTAMP",
            "scene_change_proven_causal":False,
            "audible_music_confirmed":False,
        }

    def write_events(self,offsets=(0,384,768,1536,3072)):
        with self.markers.open("w",encoding="ascii",newline="") as stream:
            csv.writer(stream,lineterminator="\n").writerows(
                [["scene","pcm_bytes","epoch_ms"]]+[
                    [scene,offset,10000000+i*10000]
                    for i,(scene,offset) in enumerate(zip(s.SCENES,offsets))
                ])

    def test_two_original_capture_bytes_bound_and_frame_accounting(self):
        report=s.analyze_pair(self.monitor,self.store_report("monitor",self.monitor),
                              self.scenes,self.store_report("scenes",self.scenes),
                              self.markers)
        self.assertEqual(report["result"],"TWO_ORIGINAL_NEXIUM_VIRTUAL_PCM_STREAMS_AUDITED")
        self.assertEqual(report["monitor_capture"]["analysis_blocks"],2)
        self.assertEqual(report["scene_capture"]["analysis_blocks"],4)
        self.assertEqual(report["scene_capture"]["scene_event_markers"][1][
            "approximate_frame_offset"],96)
        self.assertTrue(report["all_stereo_frames_and_10ms_blocks_accounted"])
        self.assertFalse(report["physical_Nintendo_Switch_hardware_tested"])

    def store_report(self,name,path):
        p=self.dir/(name+".json")
        p.write_text(__import__("json").dumps(self.ref(path,name)),encoding="utf-8")
        return p

    def test_exact_zero_runs_and_partial_tail(self):
        frames=[(1000,-1000)]*100+[(0,0)]*600+[(400,-400)]*63
        self.write_pcm(self.monitor,frames)
        doc=s.scan_pcm(self.monitor,self.ref(self.monitor,"monitor"),kind="monitor")
        self.assertEqual(doc["frames"],763)
        self.assertEqual(doc["analysis_blocks"],2)
        self.assertEqual(doc["final_partial_block_frames"],283)
        self.assertEqual(doc["longest_exact_zero_stereo_run_frames"],600)
        self.assertEqual(doc["zero_runs_at_least_10ms"],1)
        self.assertEqual(doc["exact_zero_stereo_frames"],600)

    def test_adjacent_step_not_automatically_dropout(self):
        # A 10ms window is 480 frames, so the first large step
        # is precisely at frame 480, while the second is interior.
        self.write_pcm(self.monitor,[(0,0)]*480+[(20000,-20000)]*2+
                       [(0,0)]*478)
        doc=s.scan_pcm(self.monitor,self.ref(self.monitor,"monitor"),kind="monitor")
        self.assertEqual(doc["adjacent_frame_deltas_ge4096"],2)
        self.assertEqual(doc["ge4096_deltas_at_10ms_block_boundaries"],1)
        self.assertTrue(doc["possible_sample_discontinuities_are_not_verified_dropouts"])
        self.assertTrue(doc["missing_frames_cannot_be_proven_from_pcm_bytes_alone"])

    def test_hash_and_frame_corruption_rejected(self):
        r=self.ref(self.monitor,"monitor")
        original=self.monitor.read_bytes()
        self.monitor.write_bytes(original+b"\x00")
        with self.assertRaises(s.VirtualPcmEvidenceError):
            s.scan_pcm(self.monitor,r,kind="monitor")
        # Exact original length restored, but with one different byte:
        # source SHA-256 must still reject the tampered waveform.
        self.monitor.write_bytes(original[:-1]+b"\x00")
        with self.assertRaises(s.VirtualPcmEvidenceError):
            s.scan_pcm(self.monitor,r,kind="monitor")
        r["pcm_sha256"]="a"*64
        with self.assertRaises(s.VirtualPcmEvidenceError):
            s.scan_pcm(self.monitor,r,kind="monitor")

    def test_scene_marker_tampering_rejected(self):
        ref=self.ref(self.scenes,"scenes")
        for offsets in ((0,384,768,768,3072),
                        (0,384,769,1536,3072),
                        (0,384,768,1536,9000)):
            self.write_events(offsets)
            with self.subTest(offsets=offsets),self.assertRaises(
                    s.VirtualPcmEvidenceError):
                s.scan_pcm(self.scenes,ref,kind="scenes",
                           marker_path=self.markers)

    def test_symlinks_and_prior_report_claims_rejected(self):
        link=self.dir/"linked.pcm"
        link.symlink_to(self.monitor)
        with self.assertRaises(s.VirtualPcmEvidenceError):
            s.scan_pcm(link,self.ref(self.monitor,"monitor"),kind="monitor")
        ref=self.ref(self.scenes,"scenes")
        ref["scene_change_proven_causal"]=True
        with self.assertRaises(s.VirtualPcmEvidenceError):
            s.scan_pcm(self.scenes,ref,kind="scenes",marker_path=self.markers)


if __name__=="__main__":
    unittest.main()

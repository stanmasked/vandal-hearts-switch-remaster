"""Stage300 source-anchored exact silence versus host-scene markers tests."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import analyze_nexium_pcm_scene_silence as stage
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError


class SceneSilenceSynthetic(unittest.TestCase):
    def setUp(self):
        self.rate=1000
        self.frames=32000
        self.positions=[1000,7000,13000,19000,25000]
        self.samples=[(100,-100)]*self.frames
        self.runs=[(0,300),(3300,4000),(6800,7400),(26000,29000)]
        for start,end in self.runs:
            self.samples[start:end]=[(0,0)]*(end-start)
        self.raw=b"".join(struct.pack("<hh",*x) for x in self.samples)
        self.hash=hashlib.sha256(self.raw).hexdigest()
        self.markers=[{"scene":name,"pcm_byte_offset":4*p,
                       "approximate_frame_offset":p,
                       "host_epoch_ms":100000+i*10000}
                      for i,(name,p) in enumerate(zip(stage.SCENES,self.positions))]
        self.stage299={
            "result":"TWO_ORIGINAL_NEXIUM_VIRTUAL_PCM_STREAMS_AUDITED",
            "physical_Nintendo_Switch_hardware_tested":False,
            "dropped_or_duplicated_audio_frames_proven":False,
            "scene_capture":{
                "pcm_sha256":self.hash,
                "pcm_bytes":len(self.raw),
                "frames":self.frames,
                "pinned_prior_report_reconciled":True,
                "scene_event_markers":self.markers,
                "exact_zero_stereo_frames":sum(b-a for a,b in self.runs),
                "exact_zero_stereo_runs":len(self.runs),
                "longest_exact_zero_stereo_run_frames":3000,
            },
        }
        self.scene_report={
            "schema":"vh-nexium-scene-audio/v1",
            "pcm_sha256":self.hash,
            "hardware_status":"HARDWARE NOT TESTED",
            "scene_change_proven_causal":False,
            "intervals":[{"scene":m["scene"],
                          "recorded_host_epoch_ms":m["host_epoch_ms"],
                          "event_offset_seconds":round(
                              m["approximate_frame_offset"]/self.rate,3)}
                         for m in self.markers],
        }

    def classify(self,prev=None,report=None,raw=None):
        return stage.classify_silence(
            self.raw if raw is None else raw,
            self.stage299 if prev is None else prev,
            self.scene_report if report is None else report,
            rate=self.rate)

    def test_silence_across_marker_and_longest_settled_region(self):
        r=self.classify()
        self.assertEqual(r["exact_zero_frames_total"],4600)
        self.assertEqual(r["long_run_count"],4)
        self.assertEqual(r["exact_zero_longest_run_frames"],3000)
        self.assertEqual(r["longest_zero_runs_top20"][0]["start_frame"],26000)
        self.assertEqual(
            sum(v["frames"] for v in r["longest_zero_runs_top20"][0]["zone_overlaps"]),
            3000)
        self.assertTrue(r["all_original_zero_run_frames_partitioned_exactly"])
        self.assertFalse(r["original_soundtrack_or_physical_speaker_output_verified"])
        self.assertFalse(r["scene_input_or_music_transition_causality_proven"])

    def test_source_parts_cover_every_frame_and_zero_frame(self):
        r=self.classify()
        self.assertEqual(sum(z["frames"] for z in r["zones"]),self.frames)
        self.assertEqual(sum(z["exact_zero_frames"] for z in r["zones"]),4600)
        self.assertEqual(sum(z["long_run_zero_frames"] for z in r["zones"]),4600)
        self.assertEqual([z for z in r["zones"] if z["zone"]==
                          "before_first_marker"][0]["exact_zero_frames"],300)
        focus_post=next(z for z in r["zones"] if z["zone"]==
                        "focus_1:post_marker_guard")
        self.assertEqual(focus_post["exact_zero_frames"],400)
        self.assertTrue(r["scene_marker_times_are_host_buffered_estimates"])

    def test_corrupted_pcm_and_invalid_stage299_rejected(self):
        for kind in ("pcm","count","claim","hash"):
            with self.subTest(kind=kind),self.assertRaises(VirtualPcmEvidenceError):
                doc=copy.deepcopy(self.stage299)
                raw=self.raw
                if kind=="pcm":raw=raw[:-4]+struct.pack("<hh",5,5)
                if kind=="count":doc["scene_capture"]["exact_zero_stereo_runs"]+=1
                if kind=="claim":doc["physical_Nintendo_Switch_hardware_tested"]=True
                if kind=="hash":doc["scene_capture"]["pcm_sha256"]="a"*64
                self.classify(prev=doc,raw=raw)

    def test_mismatched_host_marker_or_scene_report_rejected(self):
        for kind in ("shift","ordering","epoch","name"):
            with self.subTest(kind=kind),self.assertRaises(VirtualPcmEvidenceError):
                stage299=copy.deepcopy(self.stage299)
                scene=copy.deepcopy(self.scene_report)
                if kind=="shift":
                    stage299["scene_capture"]["scene_event_markers"][2][
                        "approximate_frame_offset"]+=1
                if kind=="ordering":
                    stage299["scene_capture"]["scene_event_markers"][2]["approximate_frame_offset"] = (
                        stage299["scene_capture"]["scene_event_markers"][1]["approximate_frame_offset"])
                if kind=="epoch":scene["intervals"][0]["recorded_host_epoch_ms"]+=1
                if kind=="name":scene["intervals"][3]["scene"]="field_2"
                self.classify(prev=stage299,report=scene)

    def test_zone_does_not_absorb_missing_settled_scene(self):
        bad=copy.deepcopy(self.markers)
        bad[2]["approximate_frame_offset"]=bad[1][
            "approximate_frame_offset"]+2200
        bad[2]["pcm_byte_offset"]=bad[2]["approximate_frame_offset"]*4
        with self.assertRaises(VirtualPcmEvidenceError):
            stage.zone_partition(bad,self.frames,rate=self.rate)

    def test_reproducibility_and_never_claim_dropouts(self):
        x=self.classify()
        self.assertEqual(x,self.classify())
        self.assertTrue(x["zero_runs_are_not_verified_audio_dropouts"])
        self.assertFalse(x["actual_guest_scheduler_or_DAC_state_measured"])


if __name__=="__main__":
    unittest.main()

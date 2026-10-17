#!/usr/bin/env python3
"""Synthetic controls for ten-scene audit. Never substitutes for real NeXium."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from PIL import Image,ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"tools"))
from decode_nexium_guest_trace_frame import encode_fixture,synthetic_image,decode_packet
from audit_nexium_scene_soak import verify_run,TraceError,bind_current_run_nro

TEST_NRO_SHA = "ab" * 32


def guest_rows(dropped=0,wrong_serial=None):
    events=[(3,1,0,100),(4,1,0,120),(5,1,0,160)]
    for serial in range(1,11):
        scene=2 if serial%2 else 1
        if serial==wrong_serial:
            scene=1 if scene==2 else 2
        base=serial*100_000_000
        for kind,offset in ((1,0),(2,50_000),(3,10_000_000),
                            (4,10_250_000),(5,44_000_000)):
            events.append((kind,scene,serial,base+offset))
    return encode_fixture(events,dropped=dropped)


def fixture(out:Path):
    root=out/"evidence"
    root.mkdir()
    sd_root=out/"vh-nexium-stage268-local"
    destination=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    destination.mkdir(parents=True)
    (root/"soak-sd-root.txt").write_text(str(sd_root)+"\n")
    packet=guest_rows()
    synthetic_image(packet).save(root/"soak-optical-trace.png")
    (destination/"audio-scene-trace-0000.csv").write_text(
        decode_packet(packet)["canonical_guest_csv"],encoding="ascii")
    tones={}
    for hz in (300,530):
        samples=bytearray()
        for j in range(9600):
            v=round(1100*math.sin(2*math.pi*hz*j/48000))
            samples.extend(struct.pack("<hh",v,round(v*.85)))
        tones[hz]=bytes(samples)
    pcm=bytearray()
    with (root/"soak-events.csv").open("w",newline="",encoding="ascii") as f:
        writer=csv.writer(f)
        writer.writerow(("scene","serial","pcm_bytes","epoch_ms"))
        for i in range(11):
            phase="field_initial" if i==0 else f"{'focus' if i%2 else 'field'}_{i}"
            writer.writerow((phase,i,len(pcm),1000+i*5000))
            pcm.extend(tones[530 if i%2 else 300]*19)
            im=Image.new("RGB",(1280,720),(0,0,0))
            draw=ImageDraw.Draw(im)
            if i%2:
                draw.rectangle((1100,605,1135,625),fill=(255,255,255))
            else:
                draw.rectangle((975,605,1010,625),fill=(255,255,255))
            im.save(root/f"soak-scene-{i:02d}.png")
    (root/"soak-monitor-s16le-48k.pcm").write_bytes(pcm)
    return root,sd_root


class TestSceneSoak(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master_tmp=tempfile.TemporaryDirectory()
        cls.master_root,cls.master_sd=fixture(Path(cls.master_tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.master_tmp.cleanup()

    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base=Path(temp.name)
        self.root=base/"evidence"
        self.sd=base/"vh-nexium-stage268-local"
        shutil.copytree(self.master_root,self.root)
        shutil.copytree(self.master_sd,self.sd)
        (self.root/"soak-sd-root.txt").write_text(str(self.sd)+"\n")

    def audit(self):
        return verify_run(self.root,self.sd,nro_sha256=TEST_NRO_SHA,
                          expected_sd_root=self.sd)

    def test_exact_ten_host_and_guest_scenes(self):
        result,encoded=self.audit()
        self.assertEqual(result["result"],
                         "TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED")
        self.assertEqual(result["guest_event_rows"],53)
        self.assertEqual(result["guest_nro_sha256"],TEST_NRO_SHA)
        self.assertEqual(result["guest_trace_dropped"],0)
        self.assertEqual(len(result["guest_internal_events"]),10)
        self.assertEqual(len(result["pcm_settled_1s_windows"]),11)
        self.assertEqual(len(result["visual_scene_assertions"]["label_changed_pixels"]),10)
        self.assertEqual(result["hardware_status"],"HARDWARE NOT TESTED")
        self.assertIsNone(result["input_to_dac_latency_ms"])
        self.assertFalse(result["no_audout_underruns_proven"])
        self.assertTrue(encoded.endswith("\n"))

    def test_nro_provenance_requires_matching_current_workflow(self):
        record = {
            "result": "SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED",
            "nro_filename": "vandal-hearts-prototype.nro",
            "nro_sha256": TEST_NRO_SHA,
            "nro_bytes": 282680,
            "git_sha": "a" * 40,
            "run_id": 65001,
            "run_attempt": 1,
            "scope": "same-workflow traceability only",
            "hardware_status": "HARDWARE NOT TESTED",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"preflight.json"
            def check(**updates):
                doc={**record, **updates}
                path.write_text(json.dumps(doc)+"\n",encoding="ascii")
                return bind_current_run_nro(
                    path,sha="a"*40,run_id=65001,attempt=1)
            self.assertEqual(check(), TEST_NRO_SHA)
            for change in (
                {"git_sha": "b"*40}, {"run_id": 39052705390},
                {"run_attempt": 2}, {"nro_sha256": "bad"},
                {"hardware_status": "HARDWARE TESTED"},
                {"result": "READY_FOR_SD_TRANSFER_REVIEW"},
                {"nro_bytes": 0}, {"fake": "untrusted"},
            ):
                with self.assertRaises(TraceError):
                    check(**change)

    def test_missing_sd_file_and_wrong_root_are_rejected(self):
        (self.sd/"sdmc/switch/vandal-hearts-remake/audio-scene-trace-0000.csv").unlink()
        with self.assertRaises(TraceError):
            self.audit()
        with self.assertRaises(TraceError):
            verify_run(self.root,self.sd,nro_sha256=TEST_NRO_SHA,
                       expected_sd_root=self.sd.parent/"fake")

    def test_mismatched_sd_csv_is_rejected(self):
        p=self.sd/"sdmc/switch/vandal-hearts-remake/audio-scene-trace-0000.csv"
        p.write_bytes(p.read_bytes()+b"EXTRA")
        with self.assertRaises(TraceError):
            self.audit()

    def test_dropped_event_and_wrong_serial_scene_are_rejected(self):
        for changes in ({"dropped":1},{"wrong_serial":3}):
            packet=guest_rows(**changes)
            synthetic_image(packet).save(self.root/"soak-optical-trace.png")
            sd=self.sd/"sdmc/switch/vandal-hearts-remake/audio-scene-trace-0000.csv"
            sd.write_text(decode_packet(packet)["canonical_guest_csv"],encoding="ascii")
            with self.assertRaises(TraceError):
                self.audit()

    def test_tampered_host_markers_or_missing_real_screenshot_fail(self):
        p=self.root/"soak-events.csv"
        content=p.read_text()
        p.write_text(content.replace("focus_1,1","field_1,1"))
        with self.assertRaises(TraceError):
            self.audit()
        p.write_text(content)
        (self.root/"soak-scene-04.png").unlink()
        with self.assertRaises(TraceError):
            self.audit()

    def test_silent_monitor_tail_after_shutdown_is_not_field_silence(self):
        # Host parec outlives guest Plus shutdown. It is incorrect to
        # sample a midpoint in this post-exit, all-zero recording tail.
        file = self.root / "soak-monitor-s16le-48k.pcm"
        with file.open("ab") as stream:
            stream.write(bytes(6*48000*4))
        report, _ = self.audit()
        self.assertEqual(report["result"],
                         "TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED")
        self.assertGreater(report["pcm_duration_seconds"], 45)

    def test_clipped_pcm_rejected_even_if_guest_trace_matches(self):
        with (self.root/"soak-monitor-s16le-48k.pcm").open("r+b") as file:
            file.seek(48000*4*4)
            file.write(struct.pack("<h",32767))
        with self.assertRaises(TraceError):
            self.audit()

    def test_identical_field_and_focus_pcm_are_not_scene_proof(self):
        f=self.root/"soak-monitor-s16le-48k.pcm"
        audio=f.read_bytes()
        one_tone=audio[:9600*4]
        f.write_bytes(one_tone*(len(audio)//len(one_tone)))
        with self.assertRaises(TraceError):
            self.audit()


if __name__=="__main__":
    unittest.main()

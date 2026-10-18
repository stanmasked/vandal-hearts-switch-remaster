"""Stage308: guest-only software clock, authentic optical protocol fixtures."""
from __future__ import annotations

import copy
import io
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from PIL import Image
from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_exit_timeline import (
    parse_exit_csv,UNOBSERVED,
)
from audit_nexium_guest_optical_exit_clock import (
    audit_guest_clocks,BOTH,NO_EXIT,INCOMPLETE,
)
from decode_nexium_guest_trace_frame import (
    encode_fixture,synthetic_image,
)


def optical_fixture():
    rows=[]
    for serial,scene in enumerate((2,1,2,1),start=1):
        for kind in (1,2,3,4,5):
            rows.append((kind,scene,serial,
                         serial*1000000+kind*1000))
    pkt=encode_fixture(rows)
    image=synthetic_image(pkt)
    buf=io.BytesIO()
    image.save(buf,format="PNG")
    return buf.getvalue()


def real_like_guest(*values):
    names=("plus_observed","stop_requested","worker_cleanup_entered",
           "audout_closed","worker_joined")
    text="event,guest_monotonic_ns\n"+"".join(
        f"{name},{value}\n" for name,value in zip(names,values))
    obj=parse_exit_csv(text.encode("ascii"))
    obj["guest_sd_receipt_observed"]=True
    obj["guest_csv_path"]="sdmc/switch/vandal-hearts-remake/audio-exit-timeline-000.csv"
    return obj


class OpticalGuestExitSynthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image=optical_fixture()
        cls.good=real_like_guest(5000000,5000050,5000100,5000200,5000400)

    def test_guest_exit_software_after_optical_music_scenes(self):
        result=audit_guest_clocks(self.image,self.good)
        self.assertEqual(result["result"],BOTH)
        self.assertEqual(result["optical_guest_event_rows"],20)
        self.assertEqual(result["optical_guest_last_scene_event_ns"],4005000)
        self.assertEqual(result["scene_last_event_to_plus_ns"],995000)
        self.assertTrue(result["guest_exit_order_verified"])
        self.assertFalse(result["guest_to_host_PCM_sample_clock_alignment_verified"])
        self.assertFalse(result["physical_Nintendo_Switch_audio_tested"])

    def test_absent_guest_sd_is_never_a_pass(self):
        no={"result":UNOBSERVED,"guest_sd_receipt_observed":False}
        result=audit_guest_clocks(self.image,no)
        self.assertEqual(result["result"],NO_EXIT)
        self.assertIsNone(result["scene_last_event_to_plus_ns"])
        self.assertFalse(result["guest_exit_order_verified"])

    def test_incomplete_observed_exit_not_laundered_to_complete(self):
        guest=real_like_guest(0,0,5000100,5000200,5000400)
        result=audit_guest_clocks(self.image,guest)
        self.assertEqual(result["result"],INCOMPLETE)
        self.assertIsNone(result["guest_exit_plus_observed_ns"])
        self.assertFalse(result["guest_exit_order_verified"])

    def test_exit_plus_before_last_guest_scene_rejected(self):
        guest=real_like_guest(4004000,4004100,4004200,4004300,4004400)
        with self.assertRaises(TraceError):
            audit_guest_clocks(self.image,guest)

    def test_modified_exit_guest_scope_claim_rejected(self):
        guest=copy.deepcopy(self.good)
        guest["host_PCM_to_guest_timestamp_mapping_verified"]=True
        with self.assertRaises(TraceError):
            audit_guest_clocks(self.image,guest)

    def test_claimed_physical_switch_sound_rejected(self):
        guest=copy.deepcopy(self.good)
        guest["physical_Nintendo_Switch_audio_tested"]=True
        with self.assertRaises(TraceError):
            audit_guest_clocks(self.image,guest)

    def test_missing_guest_sd_source_receipt_rejected(self):
        guest=copy.deepcopy(self.good)
        guest["guest_sd_receipt_observed"]=False
        with self.assertRaises(TraceError):
            audit_guest_clocks(self.image,guest)

    def test_unobserved_but_claimed_guest_receipt_rejected(self):
        with self.assertRaises(TraceError):
            audit_guest_clocks(self.image,{
                "result":UNOBSERVED,
                "guest_sd_receipt_observed":True,
            })

    def test_valid_png_with_single_flipped_optical_bit_rejected(self):
        # Remain a valid PNG while corrupting one payload bit. The audit
        # must verify the ORIGINAL guest optical CRC, not image decodability.
        with Image.open(io.BytesIO(self.image)) as source:
            altered=source.copy()
        bit_index=200
        col,row=bit_index % 112,bit_index // 112
        px=250+7+col*7+3
        py=160+7+row*7+3
        original=altered.getpixel((px,py))
        altered.putpixel((px,py),
                         (0,0,0) if min(original)>=177 else (255,255,255))
        buffer=io.BytesIO()
        altered.save(buffer,format="PNG")
        with self.assertRaises(TraceError):
            audit_guest_clocks(buffer.getvalue(),self.good)

    def test_optical_frame_with_only_three_scenes_fails_closed(self):
        rows=[]
        for serial,scene in enumerate((2,1,2),start=1):
            for kind in (1,2,3,4,5):
                rows.append((kind,scene,serial,serial*1000000+kind*1000))
        image=synthetic_image(encode_fixture(rows))
        buffer=io.BytesIO()
        image.save(buffer,format="PNG")
        with self.assertRaises(TraceError):
            audit_guest_clocks(buffer.getvalue(),self.good)

    def test_invalid_or_corrupted_original_optical_png_rejected(self):
        from PIL import UnidentifiedImageError
        with self.assertRaises((TraceError,UnidentifiedImageError,OSError)):
            audit_guest_clocks(b"not-original-PNG",self.good)

    def test_deterministic_optical_guest_relative_software_clock(self):
        self.assertEqual(audit_guest_clocks(self.image,self.good),
                         audit_guest_clocks(self.image,self.good))


if __name__=="__main__":
    unittest.main()

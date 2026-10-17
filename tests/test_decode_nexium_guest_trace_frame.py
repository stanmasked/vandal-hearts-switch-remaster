#!/usr/bin/env python3
"""Synthetic optical-pixel boundary tests; never fabricate emulator evidence."""
import sys
from pathlib import Path
import unittest

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"tools"))
from decode_nexium_guest_trace_frame import (
    TraceError,encode_fixture,decode_packet,synthetic_image,
    extract_packet,analyze_image
)

def rows_four_scenes():
    result=[]
    for serial,scene in enumerate((2,1,2,1),1):
        timestamp=serial*100_000_000
        for kind,offset in ((1,0),(2,100_000),(3,200_000),
                            (4,250_000),(5,8_000_000)):
            result.append((kind,scene,serial,timestamp+offset))
    return result

class TestOpticalFrame(unittest.TestCase):
    def test_full_guest_optical_receipt_from_pixel_values(self):
        rows=rows_four_scenes()
        packet=encode_fixture(rows)
        image=synthetic_image(packet)
        read,geometry=extract_packet(image)
        self.assertEqual(read,packet)
        self.assertEqual(geometry["decoded_bits"],7392)
        report, csv_text=analyze_image(image,require_four_scenes=True)
        self.assertEqual(report["result"],
            "FOUR_GUEST_SCENE_INTERNAL_PHASES_PIXELS_VERIFIED")
        self.assertEqual(len(report["guest_trace_audit"]["complete_scene_serials"]),4)
        self.assertEqual(report["guest_trace_audit"]["dropped"],0)
        self.assertEqual(csv_text.count("\n"),21)
        self.assertIsNone(report["actual_input_to_dac_latency_ms"])
        self.assertEqual(report["hardware_status"],"HARDWARE NOT TESTED")

    def test_scaled_nearest_neighbor_screenshot_recovers_exact_bits(self):
        packet=encode_fixture(rows_four_scenes())
        original=synthetic_image(packet)
        screenshot=original.resize((1250,703),Image.Resampling.NEAREST)
        decoded,_=extract_packet(screenshot)
        self.assertEqual(decoded,packet)

    def test_changed_pixel_breaks_crc_without_forging_guest_timestamp(self):
        packet=encode_fixture(rows_four_scenes())
        image=synthetic_image(packet)
        # Toggle the first byte's first set bit, leaving marker intact.
        px=250+7+7+3
        py=160+7+3
        value=image.getpixel((px,py))
        replacement=(255,255,255) if value==(0,0,0) else (0,0,0)
        for y in range(py-3,py+4):
            for x in range(px-3,px+4):
                image.putpixel((x,y),replacement)
        with self.assertRaises(TraceError):
            analyze_image(image,require_four_scenes=True)

    def test_no_magenta_or_bad_frame_size_fails_closed(self):
        with self.assertRaises(TraceError):
            extract_packet(Image.new("RGB",(1280,720),(0,0,0)))
        with self.assertRaises(TraceError):
            extract_packet(Image.new("RGB",(100,100),(255,0,255)))

    def test_corrupted_packet_crc_and_reserved_bytes_rejected(self):
        packet=bytearray(encode_fixture(rows_four_scenes()))
        packet[13]^=1
        with self.assertRaises(TraceError):
            decode_packet(bytes(packet))
        packet=bytearray(encode_fixture(rows_four_scenes()))
        packet[-1]=1
        with self.assertRaises(TraceError):
            decode_packet(bytes(packet))

    def test_dropped_or_wrong_scene_order_is_not_complete(self):
        packet=encode_fixture(rows_four_scenes(),dropped=1)
        with self.assertRaises(TraceError):
            analyze_image(synthetic_image(packet),require_four_scenes=True)
        wrong=list(rows_four_scenes())
        wrong[10:15]=[(kind,2,3,ns) for kind,scene,serial,ns in wrong[10:15]]
        packet=encode_fixture(wrong)
        with self.assertRaises(TraceError):
            analyze_image(synthetic_image(packet),require_four_scenes=True)

if __name__=="__main__":
    unittest.main()

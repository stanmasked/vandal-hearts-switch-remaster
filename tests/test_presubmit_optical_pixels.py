"""Generated-image regression for the exact NeXium optical grid geometry.

No game assets or screenshots are used. Only the post-join transport format
is tested. These tests run after installing python3-pil in the NeXium CI job.
"""
import importlib.util
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from decode_map02_guest_scene_trace import decode_packet_image

spec=importlib.util.spec_from_file_location(
    "presubmit_decoder",ROOT/"tools/decode_map02_audout_presubmit.py")
decoder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)

LEFT,TOP,MOD,COLS,ROWS=250,160,7,112,66

def packet_fixture():
    p=bytearray(924)
    p[:8]=b"VHPRE001"
    p[8]=8
    for i in range(8):
        struct.pack_into("<IIIQI",p,16+i*24,
                         558 if i%3==2 else 557,
                         1,1,0x123456789abcdef0+i,0x10203040+i)
    struct.pack_into("<I",p,909,zlib.crc32(p[:909]))
    return bytes(p)

def paint_packet(data):
    image=Image.new("RGB",(1280,720),(0,0,0))
    draw=ImageDraw.Draw(image)
    draw.rectangle(
        (LEFT,TOP,LEFT+(COLS+2)*MOD-1,TOP+(ROWS+2)*MOD-1),
        fill=(255,0,255))
    draw.rectangle(
        (LEFT+MOD,TOP+MOD,LEFT+(COLS+1)*MOD-1,TOP+(ROWS+1)*MOD-1),
        fill=(255,255,255))
    for bit in range(len(data)*8):
        if data[bit//8] & (0x80>>(bit%8)):
            col,row=bit%COLS,bit//COLS
            x=LEFT+(col+1)*MOD
            y=TOP+(row+1)*MOD
            draw.rectangle((x,y,x+MOD-1,y+MOD-1),fill=(0,0,0))
    return image

class OpticalPixelsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"frame.png"

    def test_complete_924_byte_pixel_roundtrip(self):
        data=packet_fixture()
        paint_packet(data).save(self.path)
        decoded=decode_packet_image(self.path)
        self.assertEqual(decoded,data)
        report=decoder.decode(decoded)
        self.assertEqual(report["observed_pages"],8)
        self.assertTrue(report["actual_audout_call_observed"])
        self.assertFalse(report["physical_switch_speaker_audio_verified"])

    def test_single_corrupted_module_rejected_by_crc(self):
        img=paint_packet(packet_fixture())
        bit=101
        col,row=bit%COLS,bit//COLS
        x=LEFT+(col+1)*MOD+MOD//2
        y=TOP+(row+1)*MOD+MOD//2
        old=img.getpixel((x,y))
        ImageDraw.Draw(img).rectangle(
            (x-3,y-3,x+3,y+3),
            fill=(255,255,255) if old==(0,0,0) else (0,0,0))
        img.save(self.path)
        altered=decode_packet_image(self.path)
        self.assertNotEqual(altered,packet_fixture())
        with self.assertRaisesRegex(ValueError,"CRC"):
            decoder.decode(altered)

    def test_missing_calibration_border_fails(self):
        img=paint_packet(packet_fixture())
        ImageDraw.Draw(img).rectangle(
            (LEFT,TOP,LEFT+(COLS+2)*MOD-1,TOP+(ROWS+2)*MOD-1),
            fill=(0,0,0))
        img.save(self.path)
        with self.assertRaisesRegex(ValueError,"magenta"):
            decode_packet_image(self.path)

    def test_wrong_screenshot_resolution_fails(self):
        paint_packet(packet_fixture()).resize((640,360)).save(self.path)
        with self.assertRaisesRegex(ValueError,"geometry"):
            decode_packet_image(self.path)

if __name__=="__main__":
    unittest.main()

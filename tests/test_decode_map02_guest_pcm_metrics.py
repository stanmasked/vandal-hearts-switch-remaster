"""Synthetic CRC/ticket tests for quantitative MAP02 guest optical witness."""
import importlib.util
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

MOD=Path(__file__).resolve().parents[1]/"tools/decode_map02_guest_pcm_metrics.py"
spec=importlib.util.spec_from_file_location("map02_guest_pcm_metric",MOD)
import sys
sys.path.insert(0,str(MOD.parent))
metric=importlib.util.module_from_spec(spec)
spec.loader.exec_module(metric)
from PIL import Image,ImageDraw

def packet(tickets=None):
    if tickets is None:
        tickets=[(1,2,1,512,768,1200,100000000,0x1234567890abcdef),
                 (2,1,1,512,700,1000,80000000,0xabcdef1234567890)]
    data=bytearray(924)
    data[:8]=b"VHPCM01A"
    data[8]=2
    for i,row in enumerate(tickets):
        struct.pack_into("<IBBHHHQQ",data,12+i*28,*row)
    struct.pack_into("<I",data,909,zlib.crc32(data[:909]))
    return bytes(data)

def image(path, raw):
    img=Image.new("RGB",(1280,720),(11,11,11))
    draw=ImageDraw.Draw(img)
    draw.rectangle((250,160,1047,635),fill=(255,0,255))
    draw.rectangle((257,167,1040,628),fill=(255,255,255))
    for bit in range(924*8):
        if raw[bit//8] & (128>>(bit%8)):
            x=257+(bit%112)*7
            y=167+(bit//112)*7
            draw.rectangle((x,y,x+6,y+6),fill=(0,0,0))
    img.save(path)

class QuantitativeWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"metric.png"

    def test_valid_metrics_are_ticket_correlated(self):
        result=metric.decode(packet())
        self.assertEqual([x["serial"] for x in result],[1,2])
        self.assertEqual([x["scene"] for x in result],[2,1])
        self.assertEqual(result[0]["nonzero_sample_values"],768)
        self.assertGreater(result[0]["rms_s16"],0)

    def test_optical_roundtrip_and_no_reverb_claim(self):
        image(self.path,packet())
        result=metric.report(self.path,1)
        self.assertEqual(result["result"],"GUEST_FIRST_PAGES_QUANTIFIED")
        self.assertFalse(result["sample_aligned_between_guest_modes"])
        self.assertFalse(result["reverb_tail_causality_proven"])

    def test_nexium_scaled_viewport_remains_decodable(self):
        image(self.path,packet())
        img=Image.open(self.path).convert("RGB")
        transformed=Image.new("RGB",(1280,720),(8,8,8))
        transformed.paste(img.crop((250,160,1048,636)).resize(
            (769,459),Image.Resampling.NEAREST),(264,154))
        transformed.save(self.path)
        self.assertEqual(metric.report(self.path,0)["result"],
                         "GUEST_FIRST_PAGES_QUANTIFIED")

    def test_corrupted_crc_is_rejected(self):
        raw=bytearray(packet())
        raw[27]^=4
        with self.assertRaisesRegex(ValueError,"CRC32"):
            metric.decode(raw)

    def test_wrong_ticket_is_rejected(self):
        rows=[(3,2,1,512,768,1200,100000000,5),
              (2,1,1,512,700,1000,80000000,6)]
        with self.assertRaisesRegex(ValueError,"ticket"):
            metric.decode(packet(rows))

    def test_zero_nonzero_count_is_rejected(self):
        rows=[(1,2,1,512,0,1200,100000000,5),
              (2,1,1,512,700,1000,80000000,6)]
        with self.assertRaisesRegex(ValueError,"bounds"):
            metric.decode(packet(rows))

    def test_impossible_energy_rejected(self):
        rows=[(1,2,1,512,800,10,999999999,5),
              (2,1,1,512,700,1000,80000000,6)]
        with self.assertRaisesRegex(ValueError,"bounds"):
            metric.decode(packet(rows))

    def test_zero_peak_rejected(self):
        rows=[(1,2,1,512,768,0,100000000,5),
              (2,1,1,512,700,1000,80000000,6)]
        with self.assertRaisesRegex(ValueError,"bounds"):
            metric.decode(packet(rows))

    def test_reserved_bytes_must_be_zero(self):
        raw=bytearray(packet())
        raw[71]=1
        struct.pack_into("<I",raw,909,zlib.crc32(raw[:909]))
        with self.assertRaisesRegex(ValueError,"reserved"):
            metric.decode(raw)

if __name__=="__main__":
    unittest.main()

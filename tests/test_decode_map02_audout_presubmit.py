"""Synthetic optical pre-submit packet tests; no NeXium guest claims."""
import importlib.util
import struct
import sys
import unittest
import zlib
from pathlib import Path

F=Path(__file__).resolve().parents[1]/"tools/decode_map02_audout_presubmit.py"
sys.path.insert(0,str(F.parent))
spec=importlib.util.spec_from_file_location("presubmit",F)
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

def fixture(mutate=None):
    p=bytearray(924)
    p[:8]=b"VHPRE001"
    p[8]=8
    for i in range(8):
        struct.pack_into("<IIIQI",p,16+24*i,
                         558 if i%3==2 else 557,
                         1,1,0x123456789abcdef0+i,0x10203040+i)
    if mutate: mutate(p)
    struct.pack_into("<I",p,909,zlib.crc32(p[:909]))
    return p

class PresubmitOpticalTests(unittest.TestCase):
    def test_valid_is_not_speaker_proof(self):
        decoded=tool.decode(fixture())
        self.assertEqual(decoded["observed_pages"],8)
        self.assertEqual(len(decoded["pages"]),8)
        self.assertTrue(decoded["actual_audout_call_observed"])
        self.assertFalse(decoded["live_dac_samples_proven"])
        self.assertFalse(decoded["physical_switch_speaker_audio_verified"])
    def test_corrupt_crc(self):
        p=fixture();p[43]^=128
        with self.assertRaisesRegex(ValueError,"CRC"):
            tool.decode(p)
    def test_wrong_magic(self):
        with self.assertRaisesRegex(ValueError,"identity"):
            tool.decode(fixture(lambda p:p.__setitem__(0,0)))
    def test_one_missing_page(self):
        with self.assertRaisesRegex(ValueError,"count"):
            tool.decode(fixture(lambda p:p.__setitem__(8,7)))
    def test_pending_at_join(self):
        with self.assertRaisesRegex(ValueError,"pending"):
            tool.decode(fixture(lambda p:p.__setitem__(9,1)))
    def test_rejected_mismatch(self):
        with self.assertRaisesRegex(ValueError,"changed"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,12,1)))
    def test_missing_attempt(self):
        with self.assertRaisesRegex(ValueError,"frame/return"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,20,0)))
    def test_missing_descriptor_return(self):
        with self.assertRaisesRegex(ValueError,"frame/return"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,24,0)))
    def test_unreasonable_page_frames(self):
        with self.assertRaisesRegex(ValueError,"frame/return"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,16,513)))
    def test_missing_digest(self):
        with self.assertRaisesRegex(ValueError,"digest"):
            tool.decode(fixture(lambda p:struct.pack_into("<Q",p,28,0)))
    def test_reserved_byte(self):
        with self.assertRaisesRegex(ValueError,"reserved"):
            tool.decode(fixture(lambda p:p.__setitem__(250,1)))
    def test_dangerous_attempt_count(self):
        with self.assertRaisesRegex(ValueError,"frame/return"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,20,100)))
    def test_partial_packet(self):
        with self.assertRaisesRegex(ValueError,"identity"):
            tool.decode(fixture()[:20])

if __name__=="__main__":
    unittest.main()

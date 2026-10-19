"""Generated negative/positive native 48-kHz output receipt cases."""
import importlib.util
import struct
import unittest
import zlib
from pathlib import Path

F=Path(__file__).resolve().parents[1]/"tools/decode_guest_native_48k.py"
import sys
sys.path.insert(0,str(F.parent))
spec=importlib.util.spec_from_file_location("native48",F)
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

def fixture(mutate=None):
    p=bytearray(924)
    p[:8]=b"VH48K001"
    p[8]=1;p[10]=15
    struct.pack_into("<IIIIII",p,12,35665,26750,48,49000,2,0)
    struct.pack_into("<QQQ",p,40,0x1111222233334444,
                     0x9950037014a7e866,0xf5edab31b6802325)
    struct.pack_into("<I",p,64,2)
    if mutate:mutate(p)
    struct.pack_into("<I",p,909,zlib.crc32(p[:909]))
    return p

class Native48GuestTests(unittest.TestCase):
    def test_valid_has_strict_limits_and_no_speaker_claim(self):
        x=tool.decode(fixture())
        self.assertEqual(x["rate_hz"],48000)
        self.assertTrue(x["guest_synthetic_postprocess_causality"])
        self.assertFalse(x["live_audout_music_sample_aligned"])
        self.assertFalse(x["physical_switch_speakers_verified"])
    def test_corrupt_crc_rejected(self):
        p=fixture();p[19]^=8
        with self.assertRaisesRegex(ValueError,"CRC"):tool.decode(p)
    def test_wrong_packet_magic_rejected(self):
        with self.assertRaisesRegex(ValueError,"identity"):
            tool.decode(fixture(lambda p:p.__setitem__(0,0)))
    def test_missing_proof_flag_rejected(self):
        with self.assertRaisesRegex(ValueError,"incomplete"):
            tool.decode(fixture(lambda p:p.__setitem__(10,0)))
    def test_first_page_too_many_bridge_samples_rejected(self):
        with self.assertRaisesRegex(ValueError,"boundary"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,28,3)))
    def test_later_page_reset_residue_rejected(self):
        with self.assertRaisesRegex(ValueError,"boundary"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,32,1)))
    def test_missing_native_page_difference_rejected(self):
        with self.assertRaisesRegex(ValueError,"differences"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,20,47)))
    def test_missing_retained_audio_rejected(self):
        with self.assertRaisesRegex(ValueError,"clocks"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,24,0)))
    def test_mismatched_native_clocks_rejected(self):
        with self.assertRaisesRegex(ValueError,"clocks"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,16,30000)))
    def test_equal_tail_fingerprints_rejected(self):
        with self.assertRaisesRegex(ValueError,"contrast"):
            tool.decode(fixture(lambda p:struct.pack_into("<Q",p,48,0xf5edab31b6802325)))
    def test_not_repeated_rejected(self):
        with self.assertRaisesRegex(ValueError,"replay"):
            tool.decode(fixture(lambda p:struct.pack_into("<I",p,64,1)))
    def test_reserved_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError,"reserved"):
            tool.decode(fixture(lambda p:p.__setitem__(100,1)))

if __name__=="__main__":unittest.main()

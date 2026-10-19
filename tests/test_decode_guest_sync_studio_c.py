"""Synthetic optical binary validity + scientific-claim boundary tests."""
import importlib.util
import struct
import sys
import unittest
import zlib
from pathlib import Path

P=Path(__file__).resolve().parents[1]/"tools/decode_guest_sync_studio_c.py"
sys.path.insert(0,str(P.parent))
spec=importlib.util.spec_from_file_location("guest_sync",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
def payload(change=None):
    p=bytearray(924)
    p[:8]=b"VHSYNC01"
    p[8]=1;p[10]=15
    struct.pack_into("<IIIII",p,12,64,48,48,49128,0)
    struct.pack_into("<QQQ",p,32,0xea424fc357e9ad98,
                     0x9950037014a7e866,0xf5edab31b6802325)
    struct.pack_into("<IIII",p,56,1,0,2,0)
    if change:change(p)
    struct.pack_into("<I",p,909,zlib.crc32(p[:909]))
    return p
class SyncedGuestTests(unittest.TestCase):
    def test_valid_proof_is_explicitly_not_external_guest_audio(self):
        result=m.decode(payload())
        self.assertEqual(result["result"],"GUEST_SYNCHRONIZED_SYNTHETIC_STUDIO_C_TAIL_PROVEN")
        self.assertTrue(result["synchronized_guest_synthetic_dsp_causality"])
        self.assertFalse(result["guest_live_audout_studio_c_causality_proven"])
        self.assertFalse(result["physical_switch_audio_tested"])
    def test_corrupted_crc_rejected(self):
        p=payload();p[22]^=4
        with self.assertRaisesRegex(ValueError,"CRC32"):m.decode(p)
    def test_wrong_magic_rejected(self):
        with self.assertRaisesRegex(ValueError,"identity"):
            m.decode(payload(lambda p:p.__setitem__(0,0)))
    def test_missing_proof_flags_rejected(self):
        with self.assertRaisesRegex(ValueError,"failed"):
            m.decode(payload(lambda p:p.__setitem__(10,7)))
    def test_unaligned_blocks_rejected(self):
        with self.assertRaisesRegex(ValueError,"aligned"):
            m.decode(payload(lambda p:struct.pack_into("<I",p,20,47)))
    def test_reset_has_sound_rejected(self):
        with self.assertRaisesRegex(ValueError,"dry"):
            m.decode(payload(lambda p:struct.pack_into("<I",p,28,10)))
    def test_wet_is_silent_rejected(self):
        with self.assertRaisesRegex(ValueError,"silent"):
            m.decode(payload(lambda p:struct.pack_into("<I",p,24,0)))
    def test_impossible_nonzero_count_rejected(self):
        with self.assertRaisesRegex(ValueError,"aligned"):
            m.decode(payload(lambda p:struct.pack_into("<I",p,24,1000000)))
    def test_different_hash_is_required(self):
        with self.assertRaisesRegex(ValueError,"fingerprint"):
            m.decode(payload(lambda p:struct.pack_into("<Q",p,40,0xf5edab31b6802325)))
    def test_no_new_notes_required(self):
        with self.assertRaisesRegex(ValueError,"note"):
            m.decode(payload(lambda p:struct.pack_into("<I",p,60,1)))
    def test_repeat_determinism_required(self):
        with self.assertRaisesRegex(ValueError,"replay"):
            m.decode(payload(lambda p:struct.pack_into("<I",p,64,1)))
    def test_reserved_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError,"reserved"):
            m.decode(payload(lambda p:p.__setitem__(109,1)))
    def test_explicit_failure_code_rejected(self):
        with self.assertRaisesRegex(ValueError,"failed"):
            m.decode(payload(lambda p:struct.pack_into("<I",p,68,100)))
if __name__=="__main__":unittest.main()

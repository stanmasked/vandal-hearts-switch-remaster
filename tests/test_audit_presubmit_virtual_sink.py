"""ROM-free tests for per-page PCM16LE virtual sink attribution."""
import importlib.util
import math
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "sink",ROOT/"tools/audit_presubmit_virtual_sink.py")
sink=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=sink
spec.loader.exec_module(sink)

def fixture():
    pages=[]
    chunks=[]
    for i in range(8):
        frames=558 if i in (3,7) else 557
        pcm=b"".join(struct.pack("<hh",
           ((j*47+i*139)%60001)-30000,
           ((j*59+i*283)%60001)-30000) for j in range(frames))
        chunks.append(pcm)
        pages.append({"index":i,"frames":frames,"attempts":1,
          "descriptor_released_returns":1,
          "fnv1a64":f"{sink.fnv1a64(pcm):016x}",
          "crc32":f"{zlib.crc32(pcm):08x}"})
    guest={"schema":"vh-map02-presubmit-optical/v1",
           "result":"GUEST_PRESUBMIT_PCM_PAGES_MATCHED",
           "observed_pages":8,"mismatches":0,
           "actual_audout_call_observed":True,"pages":pages}
    return guest,chunks

class VirtualPCMTests(unittest.TestCase):
    def test_exact_chain_with_unknown_initial_latency(self):
        receipt,pages=fixture()
        raw=b"\0"*4*211+b"".join(pages)+b"\0"*4*365
        result=sink.audit(receipt,raw)
        self.assertEqual(result["result"],"EXACT_EIGHT_PAGE_VIRTUAL_SINK_MATCH")
        self.assertEqual(result["first_exact_chain_frame_offset"],211)
        self.assertEqual(result["verified_stereo_frames"],4458)
        self.assertEqual(result["per_page_matches"],[1]*8)
        self.assertTrue(result["all_eight_pages_found_once"])
        self.assertTrue(result["unique_page_order_preserved"])
        self.assertEqual(result["inter_page_gap_frames"],[0]*7)
        self.assertTrue(result["all_pages_contiguous_in_order"])
        self.assertFalse(result["switch_speaker_audio_verified"])
        self.assertFalse(result["sample_aligned_music_cue_proven"])

    def test_positive_gaps_between_individually_matching_pages(self):
        receipt,pages=fixture()
        # This is the strongest positive result available from the first
        # real sink capture: every page is byte-exact, but the full stream
        # has extra monitor frames between guest buffers.
        injected=[13,0,128,0,7,0,23]
        raw=b"\\0"*4*59
        for i,p in enumerate(pages):
            raw+=p
            if i<7:raw+=b"\\0"*4*injected[i]
        result=sink.audit(receipt,raw)
        self.assertEqual(result["result"],"NO_EXACT_EIGHT_PAGE_SINK_MATCH")
        self.assertTrue(result["all_eight_pages_found_once"])
        self.assertTrue(result["unique_page_order_preserved"])
        self.assertEqual(result["unique_page_frame_offsets"][0],59)
        self.assertEqual(result["inter_page_gap_frames"],injected)
        self.assertEqual(result["total_positive_gap_frames"],171)
        self.assertFalse(result["all_pages_contiguous_in_order"])
        self.assertEqual(result["verified_stereo_frames"],0)
        self.assertFalse(result["sample_aligned_music_cue_proven"])

    def test_out_of_order_pages_must_not_imply_order_preserved(self):
        receipt,pages=fixture()
        raw=b"".join([pages[1],pages[0]]+pages[2:])
        result=sink.audit(receipt,raw)
        self.assertTrue(result["all_eight_pages_found_once"])
        self.assertFalse(result["unique_page_order_preserved"])
        self.assertEqual(result["result"],"NO_EXACT_EIGHT_PAGE_SINK_MATCH")
        self.assertLess(result["unique_page_frame_offsets"][1],
                        result["unique_page_frame_offsets"][0])

    def test_one_corrupt_sample_rejects_full_chain(self):
        receipt,pages=fixture()
        raw=bytearray(b"\0"*4*31+b"".join(pages))
        raw[4*31+len(pages[0])+len(pages[1])+9]^=1
        result=sink.audit(receipt,bytes(raw))
        self.assertEqual(result["result"],"NO_EXACT_EIGHT_PAGE_SINK_MATCH")
        self.assertFalse(result["guest_pcm_to_virtual_sink_exact_bytes_verified"])

    def test_one_dropped_frame_destroys_contiguous_chain(self):
        receipt,pages=fixture()
        raw=b"".join(pages[:4])+pages[4][4:]+b"".join(pages[5:])
        result=sink.audit(receipt,raw)
        self.assertEqual(result["result"],"NO_EXACT_EIGHT_PAGE_SINK_MATCH")
        self.assertGreaterEqual(sum(result["per_page_matches"]),7)

    def test_wrong_channel_order_does_not_count_as_identity(self):
        receipt,pages=fixture()
        interleaved=b"".join(pages)
        swapped=b"".join(interleaved[i+2:i+4]+interleaved[i:i+2]
                        for i in range(0,len(interleaved),4))
        result=sink.audit(receipt,swapped)
        self.assertEqual(result["result"],"NO_EXACT_EIGHT_PAGE_SINK_MATCH")

    def test_oversized_and_nonframe_monitor_rejected(self):
        receipt,pages=fixture()
        with self.assertRaisesRegex(ValueError,"stereo frames"):
            sink.audit(receipt,b"123")
        with self.assertRaisesRegex(ValueError,"bounded"):
            sink.audit(receipt,b"\0"*192004,max_seconds=1)

    def test_refuse_malformed_guest(self):
        receipt,pages=fixture()
        receipt["pages"][2]["fnv1a64"]="z"*16
        with self.assertRaisesRegex(ValueError,"fingerprint"):
            sink.audit(receipt,b"".join(pages))
        receipt["pages"][2]["fnv1a64"]="0"*16
        receipt["mismatches"]=1
        with self.assertRaisesRegex(ValueError,"identity"):
            sink.audit(receipt,b"".join(pages))

if __name__=="__main__":
    unittest.main()

#!/usr/bin/env python3
"""v120 private native-GP0 return proof and fail-closed privacy tests."""
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from test_map02_v118_quadruplet_runtime import EMPTY4
from test_map02_v119_quintuplet_runtime import (
    existing_five,quintuplets,EMPTY5
)
from tools.verify_map02_v82_native_trace import Refused
from tools.summarize_map02_v120_real_gp0_return import summarize


PASS=("VH120_GP0_RETURN_PASS commands=5 native_handlers=5 "
      "exact_four_back=1 readbacks=5 erased=1 vblanks=0\n")


def private_baseline():
    previous,raw=existing_five()
    previous+=quintuplets([
        EMPTY5[0],EMPTY5[0],(0,0,0,1,0),EMPTY5[0],EMPTY5[0]
    ])
    return previous,raw


class NativeGP0ReturnFixture(unittest.TestCase):
    def test_synthetic_host_return_passes_with_original_private_witness(self):
        previous,raw=private_baseline()
        report=summarize(previous+PASS,raw)
        self.assertEqual(report["native_gp0_commands_submitted_by_host"],5)
        self.assertEqual(report["native_unai_post_handler_samples"],5)
        self.assertEqual(report["real_native_vram_freeze_readbacks"],5)
        self.assertEqual(report["exact_four_back_returns_observed"],1)
        self.assertTrue(report["original_v119_canonical_journal_revalidated"])
        self.assertTrue(report["native_previous_value_buffers_erased"])
        self.assertTrue(report["the_commands_were_not_executed_by_interpreted_mips"])
        self.assertFalse(report["complete_vram_return_or_physical_frame_verified"])
        self.assertFalse(report["HD_replacement_approved"])

    def test_native_fixture_uses_five_real_gp0_rectangle_commands(self):
        source=(ROOT/"tools/apply_map02_v120_pcsx_rearmed.py").read_text()
        for token in (
            "0x600000ffu","0x6000ff00u","0x60ff0000u",
            "0x6000ffffu","GPU_writeDataMem(packet,3)",
            "GPU_freeze(1,&freeze_state,&native_pixels)",
            "native_pixels[(160u+dy)*1024u+40u+dx]",
            "vh119_get_quintuplet_metrics(&five)",
            "five.returned_to_four_back[0]!=1u",
            "native.handlers!=5u","native.vblank_edges!=0u",
            "vh115_reset()","vh115_sample_cache_erased()",
        ):
            self.assertIn(token,source)
        self.assertIn("canonical private JSONL was published",source)
        self.assertIn("HOST-SUBMITTED GP0 fixture",source)

    def test_original_private_journal_cannot_be_reclassified_as_v120_fixture(self):
        src=(ROOT/"tools/apply_map02_v120_pcsx_rearmed.py").read_text()
        self.assertIn("apply_v119(root)",src)
        self.assertNotIn("vh80_reset();",src)
        self.assertNotIn("VH80_VBLANK",src)
        self.assertNotIn("vh82_publish_private(",src)
        self.assertIn("if(vh104_content_smoke)",src)

    def test_refuse_missing_duplicate_truncated_or_forged_status(self):
        prior,raw=private_baseline()
        for data in (
            "",PASS+PASS,PASS.replace("commands=5","commands=4"),
            PASS.replace("native_handlers=5","native_handlers=4"),
            PASS.replace("exact_four_back=1","exact_four_back=0"),
            PASS.replace("readbacks=5","readbacks=4"),
            PASS.replace("erased=1","erased=0"),
            PASS.replace("vblanks=0","vblanks=1"),
            "VH120_GP0_RETURN_PASS commands=5\n",
            "VH120_NATIVE_RETURN_REFUSED\n"+PASS,
        ):
            with self.subTest(data=data),self.assertRaises(Refused):
                summarize(prior+data,raw)

    def test_refuse_absent_tampered_original_v119_private_trace(self):
        prior,raw=private_baseline()
        with self.assertRaises(Refused):
            summarize(PASS,raw)
        with self.assertRaises(Refused):
            summarize(prior+PASS,raw.replace(b'"kind":"',b'"kind": "',1))

    def test_public_report_excludes_raw_gpu_words_and_pixel_samples(self):
        prior,raw=private_baseline()
        serial=json.dumps(summarize(prior+PASS,raw),sort_keys=True)
        for bad in ('"pixels":','"pixel_value":','"raw_gp0":',
                    "0x600000ff","vram_address","private_runtime_log",
                    '"sha256":','"hash":'):
            self.assertNotIn(bad,serial)

    def test_pinned_emulator_checks_full_native_gpu_fixture(self):
        workflow=(ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        self.assertIn("apply_map02_v120_pcsx_rearmed",workflow)
        self.assertIn("VH120_GP0_RETURN_PASS commands=5",workflow)
        self.assertIn("summarize_map02_v120_real_gp0_return",workflow)
        self.assertIn("v120-real-gp0-return-summary.json",workflow)
        self.assertIn("proof/private/V104_RENDERER_EVENTS.jsonl",workflow)
        self.assertIn("path: proof/public/",workflow)


if __name__=="__main__":
    unittest.main()

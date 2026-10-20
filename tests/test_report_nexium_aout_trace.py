"""Generated-only fail-closed tests for address-free NeXium audout trace."""
import importlib.util
import sys
import unittest
from pathlib import Path

p=Path(__file__).resolve().parents[1]/"tools/report_nexium_aout_trace.py"
spec=importlib.util.spec_from_file_location("aout_trace_report",p)
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)

def evt(n=1,frames=557,nonzero=119,pushed=557):
    return (
        f"2026-10-20 INFO nexium [aout-trace] n={n} session=0xff "
        "tag=0xabcd selected=send:0x123:0x28:0 header=00ffaa "
        f"frames={frames} pcm_nonzero={nonzero} pcm_peak=31000 "
        f"sink_present=true started=true pcm_read=true pushed_frames={pushed} queued=1"
    )

class TraceProofTests(unittest.TestCase):
    def test_valid_first_two_and_discard_addresses(self):
        result=mod.parse("=== NeXium - Nintendo Switch Emulator ===\n"
                         +evt(1)+"\n"+evt(2,558,0,558)+"\n")
        self.assertTrue(result["nexium_file_logger_started"])
        self.assertEqual(result["trace_event_count"],2)
        self.assertEqual(result["total_appended_frames"],1115)
        self.assertTrue(result["has_nonzero_guest_pcm_append"])
        self.assertEqual(result["nonzero_append_count"],1)
        payload=str(result)
        self.assertNotIn("0xabcd",payload)
        self.assertNotIn("0x123",payload)
        self.assertNotIn("header=",payload)
        self.assertFalse(result["actual_physical_switch_audio_proven"])

    def test_initialized_logger_without_appends_is_not_forged(self):
        v=mod.parse("=== NeXium - Nintendo Switch Emulator ===")
        self.assertTrue(v["nexium_file_logger_started"])
        self.assertFalse(v["has_audio_out_append_events"])
        self.assertEqual(v["trace_event_count"],0)

    def test_log_missing_startup_must_not_claim_initialized(self):
        self.assertFalse(mod.parse(evt())["nexium_file_logger_started"])

    def test_duplicate_missing_and_out_of_order_serial_fail_closed(self):
        for text in [evt(1)+"\n"+evt(1),evt(2),evt(1)+"\n"+evt(3)]:
            with self.assertRaisesRegex(ValueError,"serial"):
                mod.parse(text)

    def test_incomplete_and_impossible_samples_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"Incomplete"):
            mod.parse("[aout-trace] n=1 frames=557 pcm_nonzero=10")
        with self.assertRaisesRegex(ValueError,"impossible"):
            mod.parse(evt(1,557,1115))
        with self.assertRaisesRegex(ValueError,"impossible"):
            mod.parse(evt(1,557,119,558))

    def test_never_count_auxiliary_rate_line_as_audio_out_append(self):
        text=("=== NeXium - Nintendo Switch Emulator ===\n"
              "[aout-rate] appends/s=0 total=0\n")
        v=mod.parse(text)
        self.assertEqual(v["trace_event_count"],0)

if __name__=="__main__":
    unittest.main()

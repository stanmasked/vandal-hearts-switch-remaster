#!/usr/bin/env python3
"""Stage359 deterministic non-causal budget analysis counterexamples."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_stage359_exit_tail_time_budget import analyze,main
class Stage359Tests(unittest.TestCase):
    def test_distinguish_sample_duration_and_guest_timeout(self):
        x=analyze()
        self.assertEqual(x["stop_taper_pcm_duration_ns"],2_000_000)
        self.assertEqual(x["unchanged_guest_wait_timeout_ns"],12_000_000)
        self.assertEqual(x["wait_budget_minus_fade_duration_ns"],10_000_000)
    def test_model_cannot_claim_guest_queue_or_scheduler(self):
        x=analyze()
        self.assertFalse(x["real_guest_queue_depth_at_shutdown_known"])
        self.assertFalse(x["actual_scheduler_latency_inferred"])
        self.assertFalse(x["causal_attribution_to_audio_fade_proven"])
        self.assertFalse(x["change_to_production_timeout_recommended"])
    def test_above_below_and_equal_boundaries_are_distinct(self):
        x=analyze()["hypotheses"]
        self.assertTrue(any(p["strictly_below_12ms_budget"] for p in x))
        self.assertTrue(any(p["exactly_on_12ms_boundary"] for p in x))
        self.assertTrue(any(p["beyond_12ms_budget"] for p in x))
        self.assertTrue(all(not p["measured_or_inferred_from_guest"] for p in x))
    def test_same_pcm_time_differs_by_hypothetical_queue(self):
        x=analyze()["hypotheses"]
        a=next(p for p in x if p["case"]=="one_fade_only")
        b=next(p for p in x if p["case"]=="long_queue")
        self.assertTrue(a["strictly_below_12ms_budget"])
        self.assertTrue(b["beyond_12ms_budget"])
    def test_identity_original_failure_but_no_ear_proof(self):
        x=analyze()
        self.assertEqual(x["original_real_timeout_raw_result"],59905)
        self.assertEqual(x["failure_mode_in_original_run"],"KernelError_TimedOut")
        self.assertFalse(x["audible_dropout_or_DAC_verified"])
        self.assertFalse(x["physical_Nintendo_Switch_audio_tested"])
    def test_written_report_exclusive_and_precise(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/"out.json"
            self.assertEqual(main(["--output",str(dest)]),0)
            self.assertEqual(json.loads(dest.read_text()),analyze())
            self.assertEqual(main(["--output",str(dest)]),2)
    def test_source_guard_real_fade_size_and_no_timeout_change(self):
        root=Path(__file__).resolve().parents[1]
        edges=(root/"source"/"vh_audio_output_edges.h").read_text()
        game=(root/"source"/"vh_switch_game_audio.c").read_text()
        self.assertIn("#define VH_AUDIO_STOP_TAIL_FRAMES 96u",edges)
        start=game.index("static int output_tail_submit_bounded(")
        end=game.index("/* Called by the single audio owner;",start)
        tail=game[start:end]
        self.assertEqual(tail.count("audoutWaitPlayFinish("),1)
        self.assertIn("UINT64_C(12000000)",tail)
        self.assertEqual(tail.count("vh_tail357_record("),1)
        self.assertEqual(tail.count("audoutAppendAudioOutBuffer("),1)
if __name__=="__main__":
    unittest.main()

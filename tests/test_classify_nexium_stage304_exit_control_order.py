"""Stage304 archived original host controls postmortem: no relaxed source gate."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from classify_nexium_stage304_exit_control_order import classify_original_host_controls
from audit_nexium_pcm_exit_controls import control_events
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError

def csv_source(bytes_=(10000,10100,10200),times=(100000,100010,100020)):
    return ("event,pcm_bytes,host_epoch_ms\n"+
        "".join(
            f"{event},{size},{ms}\n"
            for event,size,ms in zip(
                ("before_plus_down","after_plus_up","control_sequence_end"),
                bytes_,times)
    )).encode()

class OriginalControlPairPostmortemTests(unittest.TestCase):
    def test_clean_source_has_no_violation(self):
        raw=csv_source()
        out=classify_original_host_controls(raw)
        self.assertFalse(out["reproduces_nonmonotone_exit_control_source_refusal"])
        self.assertEqual(out["archived_control_order_violation_kind"],"NO_ARCHIVED_CONTROL_ORDER_VIOLATION")
        self.assertEqual([x["pcm_file_size_delta_bytes"] for x in out["adjacent_original_host_control_pairs"]],[100,100])
        self.assertEqual([x["host_epoch_delta_ms"] for x in out["adjacent_original_host_control_pairs"]],[10,10])
        self.assertFalse(out["physical_Nintendo_Switch_audio_tested"])
        self.assertEqual(control_events(raw)[0]["pcm_bytes"],10000)

    def test_file_size_regression_is_reported_without_epoch(self):
        raw=csv_source(bytes_=(10000,9996,10200))
        out=classify_original_host_controls(raw)
        self.assertTrue(out["reproduces_nonmonotone_exit_control_source_refusal"])
        self.assertEqual(out["adjacent_original_host_control_pairs"][0]["pcm_file_size_delta_bytes"],-4)
        self.assertTrue(out["adjacent_original_host_control_pairs"][0]["original_buffer_size_decreased"])
        self.assertFalse(out["adjacent_original_host_control_pairs"][0]["host_epoch_was_not_strictly_increasing"])
        with self.assertRaises(VirtualPcmEvidenceError):
            control_events(raw)

    def test_equal_host_millisecond_observations_are_distinct_from_regression(self):
        raw=csv_source(times=(100000,100000,100020))
        out=classify_original_host_controls(raw)
        self.assertTrue(out["adjacent_original_host_control_pairs"][0]["host_epoch_was_not_strictly_increasing"])
        self.assertEqual(out["adjacent_original_host_control_pairs"][0]["host_epoch_delta_ms"],0)
        with self.assertRaises(VirtualPcmEvidenceError):
            control_events(raw)

    def test_host_epoch_backward_step_is_reported(self):
        raw=csv_source(times=(100000,99999,100020))
        out=classify_original_host_controls(raw)
        self.assertEqual(out["adjacent_original_host_control_pairs"][0]["host_epoch_delta_ms"],-1)
        self.assertTrue(out["reproduces_nonmonotone_exit_control_source_refusal"])

    def test_multiple_invariants_are_each_reported(self):
        raw=csv_source(bytes_=(10000,9999,9998),times=(100000,100000,99999))
        out=classify_original_host_controls(raw)
        self.assertEqual(sum(x["original_buffer_size_decreased"] for x in out["adjacent_original_host_control_pairs"]),2)
        self.assertEqual(sum(x["host_epoch_was_not_strictly_increasing"] for x in out["adjacent_original_host_control_pairs"]),2)

    def test_archived_negative_347ms_pattern_is_clock_only(self):
        # Based on confirmed DELTAS from archival replay 39164847668,
        # without copying absolute host timestamps or original audio.
        raw=csv_source(
            bytes_=(100000,159368,978284),
            times=(200000,199653,203867))
        out=classify_original_host_controls(raw)
        self.assertEqual(out["archived_control_order_violation_kind"],"HOST_EPOCH_MOVED_BACKWARD")
        self.assertEqual(out["pcm_size_regression_pair_count"],0)
        self.assertEqual(out["host_epoch_backward_pair_count"],1)
        self.assertEqual(out["host_epoch_equal_pair_count"],0)
        self.assertEqual(
            [(p["pcm_file_size_delta_bytes"],p["host_epoch_delta_ms"])
             for p in out["adjacent_original_host_control_pairs"]],
            [(59368,-347),(818916,4214)])
        with self.assertRaises(VirtualPcmEvidenceError):
            control_events(raw)

    def test_single_equal_clock_and_multiple_violation_labels(self):
        tie=classify_original_host_controls(
            csv_source(times=(100000,100000,100020)))
        self.assertEqual(tie["archived_control_order_violation_kind"],
                         "HOST_EPOCH_EQUAL_ADJACENT")
        both=classify_original_host_controls(
            csv_source(bytes_=(10000,9999,9998),times=(100000,100000,99999)))
        self.assertEqual(both["archived_control_order_violation_kind"],
                         "MULTIPLE_HOST_CONTROL_INVARIANTS")
        size=classify_original_host_controls(
            csv_source(bytes_=(10000,9999,10100)))
        self.assertEqual(size["archived_control_order_violation_kind"],
                         "PCM_FILE_SIZE_DECREASED")

    def test_missing_or_corrupt_original_source_rejected(self):
        raw=csv_source()
        for altered in (
                b"",raw[:-1],raw.replace(b"\n",b"\r\n"),
                raw.replace(b"before_plus_down",b"after_plus_down"),
                raw.replace(b"10100",b"010100"),
                raw.replace(b"pcm_bytes",b"other"),
                raw+b"extra,0,1\n",raw+b"\x00"):
            with self.subTest(data=altered[:65]), self.assertRaises(VirtualPcmEvidenceError):
                classify_original_host_controls(altered)

    def test_never_publish_absolute_epoch_in_diagnostic(self):
        raw=csv_source(times=(1712345678000,1712345678008,1712345678013))
        text=str(classify_original_host_controls(raw))
        self.assertNotIn("1712345678000",text)
        self.assertIn("host_epoch_delta_ms",text)

if __name__=="__main__":
    unittest.main()

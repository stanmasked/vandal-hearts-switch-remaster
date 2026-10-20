"""Generated-only tests of Stage269 measured-buffer ordering. No guest assets."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_map02_observed_buffer_ordering import (
    compare_separation, independently_decode_host_buffer
)
from report_pulse_sink_input_latency import summarize


def row(ms, repeat, latency):
    failed = ms == 21
    return {
        "hint_ms": ms, "repeat": repeat,
        "pulse_buffer_during_us": latency,
        "classification": ("OPTICAL_MISSING_ZERO_VIRTUAL_SINK"
                           if failed else
                           "EIGHT_INDIVIDUAL_PAGES_IN_NONZERO_VIRTUAL_SINK"),
        "stage_name": "ENTERED_PLAYBUFFER" if failed else "CLEANUP_COMPLETED",
        "audout_call_entries": 1 if failed else 485,
        "audout_call_returns": 0 if failed else 485,
        "virtual_monitor_pcm_nonzero_samples": 0 if failed else 539707,
    }


def expected_rows():
    return [row(21, i, 10666) for i in (1, 2, 3)] + [
        row(22, i, value)
        for i, value in enumerate((10333, 11728, 10333), start=1)]


def raw_snapshot(delay):
    # Original Pulse parser requires exact ALSA input identity, not
    # a similar named recorder or the requested latency environment hint.
    return (
        "Sink Input #25\n"
        "    Sample Specification: s16le 2ch 48000Hz\n"
        f"    Buffer Latency: {delay} usec\n"
        "    Sink Latency: 1811 usec\n"
        "    Corked: no\n"
        "    Resample method: copy\n"
        "    Properties:\n"
        "        application.name = \"ALSA plug-in [nexium]\"\n"
        "        media.name = \"ALSA Playback\"\n"
    )


class ObservedBufferOrderingTests(unittest.TestCase):
    def test_three_21_failures_and_three_22_successes_cross_cutoff(self):
        result = compare_separation(expected_rows())
        self.assertEqual(result["failed_observed_buffer_us"], [10666] * 3)
        self.assertEqual(result["successful_observed_buffer_us"],
                         [10333, 10333, 11728])
        self.assertFalse(result["one_cutoff_high_buffer_means_success_compatible"])
        self.assertFalse(result["one_cutoff_low_buffer_means_success_compatible"])
        self.assertFalse(result["cpal_alsa_root_cause_proven"])
        self.assertFalse(result["guest_service_deadlock_proven"])

    def test_true_high_only_cutoff_is_reported_compatible_not_impossible(self):
        samples = [row(21, i, 9000) for i in (1, 2, 3)] + [
            row(22, i, 11000) for i in (1, 2, 3)]
        report = compare_separation(samples)
        self.assertTrue(report["one_cutoff_high_buffer_means_success_compatible"])
        self.assertFalse(report["one_cutoff_low_buffer_means_success_compatible"])

    def test_true_low_only_cutoff_is_reported_compatible_not_impossible(self):
        samples = [row(21, i, 11000) for i in (1, 2, 3)] + [
            row(22, i, 9000) for i in (1, 2, 3)]
        report = compare_separation(samples)
        self.assertTrue(report["one_cutoff_low_buffer_means_success_compatible"])
        self.assertFalse(report["one_cutoff_high_buffer_means_success_compatible"])

    def test_missing_failed_guest_rejected(self):
        with self.assertRaisesRegex(ValueError, "six"):
            compare_separation(expected_rows()[1:])

    def test_duplicate_guest_repeat_rejected(self):
        samples = expected_rows()
        samples[1]["repeat"] = 1
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            compare_separation(samples)

    def test_false_21ms_guest_success_rejected(self):
        samples = expected_rows()
        samples[0]["classification"] = "EIGHT_INDIVIDUAL_PAGES_IN_NONZERO_VIRTUAL_SINK"
        with self.assertRaisesRegex(ValueError, "deviates"):
            compare_separation(samples)

    def test_false_22ms_audio_service_returns_rejected(self):
        samples = expected_rows()
        samples[4]["audout_call_returns"] = 0
        with self.assertRaisesRegex(ValueError, "deviates"):
            compare_separation(samples)

    def test_fake_hint_substituted_for_real_buffer_rejected(self):
        samples = expected_rows()
        samples[4]["pulse_buffer_during_us"] = "22"
        with self.assertRaisesRegex(ValueError, "valid observed"):
            compare_separation(samples)

    def test_pulse_raw_snapshots_must_equal_saved_parser_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            trial = root / "map02-presubmit-nexium-guest-proof-22-r1"
            trial.mkdir()
            during, after = raw_snapshot(10333), raw_snapshot(13333)
            (trial / "pulse-sink-inputs-during.txt").write_text(during)
            (trial / "pulse-sink-inputs-after-input.txt").write_text(after)
            saved = summarize(during, after)
            self.assertTrue(saved["unique_target_each_snapshot"])
            (trial / "pulse-sink-input-observed.json").write_text(
                json.dumps(saved))
            measured = independently_decode_host_buffer(root, 22, 1)
            self.assertEqual(measured["pulse_buffer_during_us"], 10333)
            self.assertTrue(measured["pulse_raw_snapshot_parser_verified"])
            saved["buffer_latency_us"]["during"] = 22000
            (trial / "pulse-sink-input-observed.json").write_text(
                json.dumps(saved))
            with self.assertRaisesRegex(ValueError, "raw pactl snapshots mismatch"):
                independently_decode_host_buffer(root, 22, 1)

    def test_near_miss_pulse_media_client_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            trial = root / "map02-presubmit-nexium-guest-proof-21-r2"
            trial.mkdir()
            raw = raw_snapshot(10666).replace(
                'application.name = "ALSA plug-in [nexium]"',
                'application.name = "ALSA plug-in [parec]"')
            (trial / "pulse-sink-inputs-during.txt").write_text(raw)
            (trial / "pulse-sink-inputs-after-input.txt").write_text(raw)
            saved = summarize(raw, raw)
            (trial / "pulse-sink-input-observed.json").write_text(
                json.dumps(saved))
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                independently_decode_host_buffer(root, 21, 2)


if __name__ == "__main__":
    unittest.main()

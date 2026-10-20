"""Generated-only tests for host PulseAudio sink-input attribute parsing."""
import importlib.util
import sys
import unittest
from pathlib import Path

f=Path(__file__).resolve().parents[1]/"tools/report_pulse_sink_input_latency.py"
spec=importlib.util.spec_from_file_location("pulse_sink",f)
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)

def fixture(latency):
    return f'''Sink Input #2
    Sample Specification: float32le 2ch 48000Hz
    Channel Map: front-left,front-right
    Corked: no
    Buffer Latency: {latency} usec
    Sink Latency: 4100 usec
    Resample method: copy
    Properties:
        media.name = "ALSA Playback"
        application.name = "ALSA plug-in [nexium]"
Sink Input #10
    Sample Specification: float32le 32ch 768000Hz
    Corked: no
    Buffer Latency: 32000 usec
    Sink Latency: 2300 usec
    Resample method: speex-float-1
    Properties:
        media.name = "ALSA Playback"
        application.name = "ALSA plug-in [nexium]"
'''

class PulseSinkInputTests(unittest.TestCase):
    def test_realistic_target_is_2ch48k_not_32ch(self):
        data=mod.summarize(fixture(21103),fixture(24041))
        self.assertTrue(data["unique_target_each_snapshot"])
        self.assertEqual(data["buffer_latency_us"],
                         {"during":21103,"after":24041})
        self.assertEqual(data["sink_latency_us"],
                         {"during":4100,"after":4100})
        self.assertEqual(len(data["observed_client_inputs"]["during"]),2)
        self.assertFalse(data["requested_latency_hint_was_honored_proven"])
        self.assertFalse(data["physical_switch_dac_or_speaker_proven"])

    def test_missing_2ch_client_is_inconclusive(self):
        data=mod.summarize("",fixture(10666))
        self.assertFalse(data["unique_target_each_snapshot"])
        self.assertIsNone(data["buffer_latency_us"]["during"])

    def test_ambiguous_duplicate_clients_are_inconclusive(self):
        data=mod.summarize(fixture(11000)+fixture(20000),fixture(23000))
        self.assertFalse(data["unique_target_each_snapshot"])
        self.assertIsNone(data["buffer_latency_us"]["during"])

    def test_malformed_snapshot_does_not_forge_latency(self):
        data=mod.summarize("Sink Input #8\n Buffer Latency: 1 usec",
                           "Sink Input #1\n Sample Specification: float32le 2ch 48000Hz")
        self.assertFalse(data["unique_target_each_snapshot"])
        self.assertIsNone(data["buffer_latency_us"]["after"])

if __name__=="__main__":
    unittest.main()

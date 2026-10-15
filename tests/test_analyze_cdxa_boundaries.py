"""Tests for non-destructive sector-boundary PCM diagnostics."""
import hashlib
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.analyze_cdxa_boundaries import analyze_boundaries


class XaBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.report, self.payload, self.wav = (root / n for n in ("report.json", "data.bin", "decoded.wav"))
        payload = bytes(2304 * 3)
        self.payload.write_bytes(payload)
        report = {
            "audio_form2_sectors_written": 3,
            "payload_bytes_written": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "coding_info_counts": {"0x01": 3},
            "file_channel_counts": {"1:0": 3},
            "audio_lbas": [5, 7, 9],
            "audio_lba_offsets": [
                {"lba": 5, "payload_offset": 0, "missing_source_sectors_before": 0},
                {"lba": 7, "payload_offset": 2304, "missing_source_sectors_before": 1},
                {"lba": 9, "payload_offset": 4608, "missing_source_sectors_before": 1},
            ],
            "noncontiguous_audio_transitions": 2,
        }
        self.report.write_text(json.dumps(report), encoding="utf-8")

    def write_wav(self, segments):
        with wave.open(str(self.wav), "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(37800)
            for left, right in segments:
                frame = int(left).to_bytes(2, "little", signed=True) + int(right).to_bytes(2, "little", signed=True)
                out.writeframes(frame * 2016)

    def test_detects_single_discontinuity_and_lba_gap(self):
        self.write_wav([(0, 0), (12000, -12000), (12000, -12000)])
        result = analyze_boundaries(self.report, self.payload, self.wav, threshold=10000)
        self.assertEqual(result["boundaries_checked"], 2)
        self.assertEqual(result["boundaries_at_or_above_threshold"], 1)
        self.assertEqual(result["gapped_lba_boundaries"], 2)
        self.assertEqual(result["adjacent_lba_boundaries"], 0)
        self.assertEqual(result["gapped_lba_boundaries_above_threshold"], 1)
        self.assertEqual(result["adjacent_lba_boundaries_above_threshold"], 0)
        self.assertEqual(result["largest_boundaries"][0]["boundary_index"], 1)
        self.assertEqual(result["largest_boundaries"][0]["max_jump"], 12000)
        self.assertEqual(result["largest_boundaries"][0]["local_neighbor_max_jump"], 0)
        self.assertEqual(result["largest_boundaries"][0]["excess_over_local_neighbors"], 12000)
        self.assertEqual(result["largest_boundaries"][0]["missing_source_sectors"], 1)

    def test_no_jump_and_threshold_boundaries(self):
        self.write_wav([(500, 500), (500, 500), (500, 500)])
        result = analyze_boundaries(self.report, self.payload, self.wav, threshold=1, top=1)
        self.assertEqual(result["boundaries_at_or_above_threshold"], 0)
        self.assertEqual(len(result["largest_boundaries"]), 1)
        self.assertEqual(result["largest_boundaries"][0]["max_jump"], 0)

    def test_adjacent_lbas_are_separate_from_gapped_transitions(self):
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["audio_lbas"] = [5, 6, 9]
        report["audio_lba_offsets"] = [
            {"lba": 5, "payload_offset": 0, "missing_source_sectors_before": 0},
            {"lba": 6, "payload_offset": 2304, "missing_source_sectors_before": 0},
            {"lba": 9, "payload_offset": 4608, "missing_source_sectors_before": 2},
        ]
        report["noncontiguous_audio_transitions"] = 1
        self.report.write_text(json.dumps(report), encoding="utf-8")
        self.write_wav([(0, 0), (9000, 0), (20000, 0)])
        result = analyze_boundaries(self.report, self.payload, self.wav, threshold=8192)
        self.assertEqual(result["adjacent_lba_boundaries"], 1)
        self.assertEqual(result["gapped_lba_boundaries"], 1)
        self.assertEqual(result["adjacent_lba_boundaries_above_threshold"], 1)
        self.assertEqual(result["gapped_lba_boundaries_above_threshold"], 1)
        self.assertEqual(result["boundaries_at_or_above_threshold"], 2)

    def test_natural_ramp_has_no_excess_over_nearby_jumps(self):
        # Make a ramp across an adjacent-sector boundary: the same 1000-unit
        # step appears immediately before, at, and immediately after the seam.
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["audio_lbas"] = [5, 6, 7]
        report["audio_lba_offsets"] = [
            {"lba": 5, "payload_offset": 0, "missing_source_sectors_before": 0},
            {"lba": 6, "payload_offset": 2304, "missing_source_sectors_before": 0},
            {"lba": 7, "payload_offset": 4608, "missing_source_sectors_before": 0},
        ]
        report["noncontiguous_audio_transitions"] = 0
        self.report.write_text(json.dumps(report), encoding="utf-8")
        self.write_wav([(0, 0)] * 3)
        with self.wav.open("r+b") as stream:
            # Standard PCM WAV created by wave: first frame begins at 44.
            # Modify local frames without changing the WAV header or size.
            stream.seek(44 + (2016 - 2) * 4)
            for value in (1000, 2000, 3000, 4000):
                frame = value.to_bytes(2, "little", signed=True)
                stream.write(frame + frame)
        result = analyze_boundaries(self.report, self.payload, self.wav, threshold=1000)
        first = next(x for x in result["largest_boundaries"] if x["boundary_index"] == 1)
        self.assertEqual(first["max_jump"], 1000)
        self.assertEqual(first["local_neighbor_max_jump"], 1000)
        self.assertEqual(first["excess_over_local_neighbors"], 0)

    def test_invalid_options_rejected(self):
        self.write_wav([(0, 0)] * 3)
        with self.assertRaisesRegex(ValueError, "threshold"):
            analyze_boundaries(self.report, self.payload, self.wav, threshold=-1)
        with self.assertRaisesRegex(ValueError, "top"):
            analyze_boundaries(self.report, self.payload, self.wav, top=0)

    def test_bad_wav_count_rejected_by_validator(self):
        self.write_wav([(0, 0)] * 2)
        with self.assertRaisesRegex(ValueError, "frame count"):
            analyze_boundaries(self.report, self.payload, self.wav)


if __name__ == "__main__":
    unittest.main()

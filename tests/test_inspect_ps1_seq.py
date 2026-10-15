"""Synthetic PlayStation SEQ regressions; no game sequence is distributed."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_ps1_seq import parse_seq


def header(ppqn=480, tempo=500000):
    return (b"pQES" + bytes(4) + ppqn.to_bytes(2, "big")
            + tempo.to_bytes(3, "big") + bytes(2))


def vlq(number):
    parts = [number & 0x7F]
    number >>= 7
    while number:
        parts.insert(0, (number & 0x7F) | 0x80)
        number >>= 7
    return bytes(parts)


class SeqTests(unittest.TestCase):
    def test_running_status_controls_program_tempo_and_end(self):
        events = (
            bytes([0, 0xC0, 7])
            + bytes([0, 0xB0, 7, 100])
            + bytes([0, 0xB0, 10, 32])
            + bytes([0, 0x90, 60, 100])
            + bytes([0, 64, 70])   # running note-on, same tick
            + vlq(240) + bytes([0x80, 60, 40])
            + bytes([0, 0xFF, 0x51, 0x03, 0xD0, 0x90])
            + vlq(240) + bytes([0x90, 64, 0])  # velocity zero is note-off
            + bytes([0, 0xFF, 0x2F])
        )
        data = header() + events + bytes(7)  # trailing sector/asset padding
        result = parse_seq(data)
        self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["initial_tempo_us_per_quarter"], 500000)
        self.assertEqual(result["ppqn"], 480)
        self.assertEqual(result["total_ticks"], 480)
        self.assertEqual(result["total_frames"], 16537)
        self.assertEqual(result["trailing_bytes"], 7)
        types = [e["type"] for e in result["events"]]
        self.assertEqual(types, [
            "program_change", "control_change", "control_change",
            "note_on", "note_on", "note_off", "tempo", "note_off",
            "end_of_track",
        ])
        self.assertEqual(
            [(e["note"], e["frame"], e["velocity"]) for e in result["events"]
             if e["type"] == "note_on"],
            [(60, 0, 100), (64, 0, 70)]
        )
        self.assertEqual(result["events"][5]["frame"], 11025)
        self.assertEqual(result["events"][6]["tempo_us_per_quarter"], 250000)
        self.assertEqual(result["events"][7]["frame"], 16537)
        self.assertEqual(result["events"][7]["type"], "note_off")
        self.assertEqual(result["events"][-1]["frame"], 16537)

    def test_fallback_header_defaults_and_ignored_channel_payloads(self):
        data = (header(ppqn=0, tempo=0)
                + bytes([0, 0xA0, 60, 5])
                + bytes([0, 0xD1, 22])
                + bytes([0, 0xE0, 5, 7])
                + vlq(480) + bytes([0xFF, 0x2F]))
        result = parse_seq(data)
        self.assertEqual(result["ppqn"], 480)
        self.assertEqual(result["initial_tempo_us_per_quarter"], 500000)
        self.assertEqual(result["total_frames"], 22050)
        self.assertEqual(
            [e["type"] for e in result["events"]],
            ["ignored_channel_event"] * 3 + ["end_of_track"]
        )

    def test_four_byte_vlq_and_rejection_of_fifth(self):
        data = header() + bytes([0x81, 0x80, 0x80, 0x00, 0xFF, 0x2F])
        self.assertEqual(parse_seq(data)["total_ticks"], 1 << 21)
        data = header() + bytes([0x81, 0x80, 0x80, 0x80, 0x00, 0xFF, 0x2F])
        with self.assertRaisesRegex(ValueError, "exceeds four bytes"):
            parse_seq(data)

    def test_malformed_data_rejected_before_any_out_of_bounds_read(self):
        bad = {
            "bad signature": b"MThd" + header()[4:] + bytes([0, 0xFF, 0x2F]),
            "too short": header()[:-1],
            "empty track": header(),
            "missing event": header() + bytes([0]),
            "missing EOT": header() + bytes([0, 0x90, 60, 100]),
            "running without status": header() + bytes([0, 60, 100, 0, 0xFF, 0x2F]),
            "truncated running": header() + bytes([0, 0x90, 60]),
            "invalid MIDI data byte": header() + bytes([0, 0x90, 60, 0xFF]),
            "unsupported meta": header() + bytes([0, 0xFF, 0x01, 0xFF, 0x2F]),
            "truncated tempo": header() + bytes([0, 0xFF, 0x51, 0x07]),
            "unsupported sysex": header() + bytes([0, 0xF0, 0, 0xFF, 0x2F]),
            "truncated VLQ": header() + bytes([0x80]),
        }
        for label, payload in bad.items():
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    parse_seq(payload)
        with self.assertRaisesRegex(ValueError, "256 KiB"):
            parse_seq(header() + bytes(0x40000))
        with self.assertRaises(ValueError):
            parse_seq(bytearray(header() + bytes([0, 0xFF, 0x2F])))

    def test_meta_tempo_has_no_standard_midi_length(self):
        # FF 51 07 A1 20 encodes 500,000 us/quarter, not 'length=7'.
        song = header() + bytes([0, 0xFF, 0x51, 0x07, 0xA1, 0x20,
                                 0, 0x90, 60, 100,
                                 0, 0xFF, 0x2F])
        result = parse_seq(song)
        self.assertEqual(result["events"][0]["tempo_us_per_quarter"], 500000)
        self.assertEqual(result["events"][1]["note"], 60)

    def test_cli_is_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.seq"
            source = header() + bytes([0, 0x90, 60, 120,
                                       0, 0xFF, 0x2F])
            path.write_bytes(source)
            proc = subprocess.run(
                [sys.executable,
                 str(Path(__file__).resolve().parents[1] / "tools/inspect_ps1_seq.py"),
                 str(path)], capture_output=True, text=True, check=True
            )
            report = json.loads(proc.stdout)
            self.assertEqual(report["events"][0]["type"], "note_on")
            self.assertEqual(report["byte_length"], len(source))
            self.assertEqual(path.read_bytes(), source)


if __name__ == "__main__":
    unittest.main()

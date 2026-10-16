"""Exercise extraction of genuine trace-format events from noisy logs."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.extract_map02_trace import (MAX_RAW_LINE_BYTES, TraceByteStream,
                                       extract_trace_bytes, extract_trace_lines,
                                       extract_trace_text)


def entries():
    return [
        {"z": 8, "x": 19, "face": 0, "stage": "post_load", "gfx": 641},
        {"z": 11, "x": 11, "face": 0, "stage": "post_load", "gfx": 643},
        {"z": 8, "x": 19, "face": 0, "stage": "draw", "gfx": 641, "u": 240, "v": 192},
        {"z": 11, "x": 11, "face": 0, "stage": "draw", "gfx": 643, "u": 240, "v": 208},
    ]


def capture(events):
    return "SDL2 booted\n" + "\nPC raster debug...\n".join(json.dumps(e) for e in events) + "\nExit game\n"


class ExtractMap02TraceTests(unittest.TestCase):
    def test_extracts_events_and_keeps_order_and_duplicates(self):
        events = entries() + [dict(entries()[-1])]
        self.assertEqual(extract_trace_text(capture(events)), events)

    def test_chunked_raw_pipe_preserves_event_lines_and_utf8_boundaries(self):
        payload = (b"startup: " + bytes((255, 254)) + b"\n"
                   + capture(entries()).encode("utf-8"))
        reader = TraceByteStream()
        captured = []
        for i in range(0, len(payload), 7):
            captured.extend(reader.feed(payload[i:i + 7]))
        captured.extend(reader.finish())
        self.assertEqual(captured, entries())
        self.assertEqual(reader.line_number, len(payload.splitlines()))

    def test_streaming_sink_keeps_valid_prefix_before_malformed_same_chunk(self):
        saved = []
        reader = TraceByteStream()
        valid = json.dumps(entries()[0]).encode("utf-8")
        broken = b'{"z":8,"x":19,"face":0,"stage":"draw","gfx":\n'
        with self.assertRaisesRegex(ValueError, "line 2"):
            reader.feed(valid + b"\n" + broken, on_event=saved.append)
        self.assertEqual(saved, [entries()[0]])

    def test_final_event_without_newline_and_malformed_trace_line_numbers(self):
        event = json.dumps(entries()[0]).encode("utf-8")
        reader = TraceByteStream()
        self.assertEqual(reader.feed(b"boot log\n" + event[:13]), [])
        self.assertEqual(reader.feed(event[13:]), [])
        self.assertEqual(reader.finish(), [entries()[0]])
        self.assertEqual(reader.finish(), [])
        invalid = TraceByteStream()
        self.assertEqual(invalid.feed(b"boot\nsome noise\n"), [])
        malformed = b'{"z":8,"x":19,"face":0,"stage":"draw","gfx":\n'
        with self.assertRaisesRegex(ValueError, "line 3"):
            invalid.feed(malformed)

    def test_oversized_plain_console_line_is_skipped_without_unbounded_memory(self):
        valid = json.dumps(entries()[0]).encode("utf-8") + b"\n"
        reader = TraceByteStream()
        noise = b"GPU: " + b"x" * (MAX_RAW_LINE_BYTES * 2)
        output = []
        payload = b"startup\n" + noise + b"\n" + valid
        for index in range(0, len(payload), 4093):
            output.extend(reader.feed(payload[index:index + 4093]))
            self.assertLessEqual(len(reader._pending), MAX_RAW_LINE_BYTES)
        output.extend(reader.finish())
        self.assertEqual(output, [entries()[0]])
        self.assertEqual(reader.line_number, 3)

    def test_oversized_no_newline_plain_noise_discarded_on_finish(self):
        reader = TraceByteStream()
        noise = b"unrelated " + b"x" * (MAX_RAW_LINE_BYTES * 2)
        for offset in range(0, len(noise), 65536):
            self.assertEqual(reader.feed(noise[offset:offset + 65536]), [])
            self.assertLessEqual(len(reader._pending), MAX_RAW_LINE_BYTES)
        self.assertEqual(reader.finish(), [])
        self.assertEqual(reader.line_number, 1)

    def test_oversized_json_trace_line_fails_closed_and_retains_valid_prefix(self):
        entry = entries()[0]
        valid = json.dumps(entry).encode("utf-8") + b"\n"
        oversized = b'{"z":8,"x":19,"face":0,"stage":"draw","gfx":' + (
            b"x" * (MAX_RAW_LINE_BYTES + 1)
        )
        saved = []
        reader = TraceByteStream()
        data = valid + oversized
        with self.assertRaisesRegex(ValueError, "malformed Map02 trace object at line 2: oversized"):
            for offset in range(0, len(data), 65536):
                reader.feed(data[offset:offset + 65536], on_event=saved.append)
        self.assertEqual(saved, [entry])
        self.assertLessEqual(len(reader._pending), MAX_RAW_LINE_BYTES)

    def test_oversized_non_trace_json_object_is_rejected_conservatively(self):
        # A huge JSON-looking console line might be a Map02 object whose
        # identifying keys occur later, so do not silently discard it.
        reader = TraceByteStream()
        with self.assertRaisesRegex(ValueError, "line 1: oversized JSON-looking line"):
            reader.feed(b'{"debug":"' + b"x" * (MAX_RAW_LINE_BYTES + 1))

    def test_binary_extractor_skips_oversized_console_and_retains_complete_trace(self):
        event = json.dumps(entries()[0]).encode("utf-8") + b"\n"
        raw = b"GPU:" + b"x" * (MAX_RAW_LINE_BYTES + 100) + b"\n" + event
        chunks = (raw[i:i + 8191] for i in range(0, len(raw), 8191))
        self.assertEqual(extract_trace_bytes(chunks), [entries()[0]])

    def test_standalone_cli_accepts_reentered_map11_full_trace(self):
        load = entries()
        load[2].update({"frame": 8, "path": "normal"})
        load[3].update({"frame": 8, "path": "normal"})
        events = [
            load[0], load[1],
            {"z": 8, "x": 19, "face": 0, "stage": "visit",
             "gfx": 641, "frame": 8, "path": "normal", "face_count": 2},
            load[2],
            {"z": 11, "x": 11, "face": 0, "stage": "visit",
             "gfx": 643, "frame": 8, "path": "normal", "face_count": 2},
            load[3],
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "noisy-game.log"
            payload = b"GPU:" + b"x" * (MAX_RAW_LINE_BYTES + 30) + b"\n"
            payload += b"".join(json.dumps(event).encode("utf-8") + b"\n"
                                for event in events + events)
            path.write_bytes(payload)
            command = [sys.executable, "-m", "tools.extract_map02_trace", str(path),
                       "--require-full-trace", "--require-complete"]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([json.loads(line) for line in result.stdout.splitlines()],
                             events + events)

    def test_ignores_other_json_structures(self):
        ev = entries()[0]
        text = 'noise\n{"kind":"gpu","frame":7}\n' + json.dumps(ev) + '\n'
        self.assertEqual(extract_trace_text(text), [ev])

    def test_rejects_malformed_trace_but_not_malformed_unrelated_json(self):
        text = json.dumps(entries()[0]) + '\n{"z":8,"x":19,"face":0,"stage":"draw","gfx":\n'
        with self.assertRaisesRegex(ValueError, 'line 2'):
            extract_trace_text(text)
        self.assertEqual(extract_trace_text('{bad unrelated json}\n' + json.dumps(entries()[0])), [entries()[0]])

    def test_line_iterator_handles_large_noisy_capture_without_reading_all(self):
        """Reader receives an iterator; unrelated log lines need no buffering."""
        def lines():
            for _ in range(20000):
                yield "GPU diagnostic message\n"
            for event in entries():
                yield json.dumps(event) + "\n"
        self.assertEqual(extract_trace_lines(lines()), entries())

    def test_cli_can_extract_trace_after_invalid_utf8_console_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "mixed.log"
            payload = b"GPU logger: " + bytes((255, 254, 10))
            payload += capture(entries()).encode("utf-8")
            source.write_bytes(payload)
            cmd = [sys.executable, "-m", "tools.extract_map02_trace",
                   str(source), "--require-complete"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([json.loads(line) for line in result.stdout.splitlines()], entries())

    def test_full_trace_cli_requires_preceding_visit_and_protects_output(self):
        events = entries()
        events[2].update({"frame": 7, "path": "normal"})
        events[3].update({"frame": 7, "path": "normal"})
        visits = [
            {"z": 8, "x": 19, "face": 0, "stage": "visit",
             "gfx": 641, "frame": 7, "path": "normal", "face_count": 3},
            {"z": 11, "x": 11, "face": 0, "stage": "visit",
             "gfx": 643, "frame": 7, "path": "normal", "face_count": 3},
        ]
        full = [events[0], events[1], visits[0], events[2], visits[1], events[3]]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "full.log"
            dest = Path(folder) / "filtered.jsonl"
            cmd = [sys.executable, "-m", "tools.extract_map02_trace",
                   str(source), "-o", str(dest), "--require-full-trace"]
            source.write_text(capture(full), encoding="utf-8")
            ok = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual([json.loads(line) for line in dest.read_text().splitlines()], full)
            dest.unlink()
            source.write_text(capture(full[:2] + full[3:]), encoding="utf-8")
            rejected = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("draw without preceding nonempty visit", rejected.stderr)
            self.assertFalse(dest.exists())

    def test_empty_capture_fails(self):
        with self.assertRaisesRegex(ValueError, 'no Map02'):
            extract_trace_text('Launching game\nGame stopped\n')

    def test_cli_outputs_validator_compatible_jsonl(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'capture.log'
            path.write_text(capture(entries()), encoding='utf-8')
            command = [sys.executable, '-m', 'tools.extract_map02_trace', str(path), '--require-complete']
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([json.loads(line) for line in result.stdout.splitlines()], entries())
            output = Path(folder) / 'trace.jsonl'
            command = [sys.executable, '-m', 'tools.extract_map02_trace', str(path), '-o', str(output)]
            self.assertEqual(subprocess.run(command, text=True, capture_output=True).returncode, 0)
            self.assertEqual([json.loads(line) for line in output.read_text().splitlines()], entries())
            self.assertNotEqual(subprocess.run(command, text=True, capture_output=True).returncode, 0)

    def test_require_complete_rejects_partial_without_creating_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'partial.log'
            path.write_text(capture(entries()[:2]), encoding='utf-8')
            target = Path(folder) / 'trace.jsonl'
            cmd = [sys.executable, '-m', 'tools.extract_map02_trace', str(path), '-o', str(target), '--require-complete']
            proc = subprocess.run(cmd, text=True, capture_output=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(target.exists())
            self.assertIn('missing draw', proc.stderr)


if __name__ == '__main__':
    unittest.main()

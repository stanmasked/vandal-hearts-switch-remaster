"""Exercise extraction of genuine trace-format events from noisy logs."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.extract_map02_trace import TraceByteStream, extract_trace_lines, extract_trace_text


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

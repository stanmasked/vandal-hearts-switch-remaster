"""Exercise extraction of genuine trace-format events from noisy logs."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.extract_map02_trace import extract_trace_text


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

    def test_ignores_other_json_structures(self):
        ev = entries()[0]
        text = 'noise\n{"kind":"gpu","frame":7}\n' + json.dumps(ev) + '\n'
        self.assertEqual(extract_trace_text(text), [ev])

    def test_rejects_malformed_trace_but_not_malformed_unrelated_json(self):
        text = json.dumps(entries()[0]) + '\n{"z":8,"x":19,"face":0,"stage":"draw","gfx":\n'
        with self.assertRaisesRegex(ValueError, 'line 2'):
            extract_trace_text(text)
        self.assertEqual(extract_trace_text('{bad unrelated json}\n' + json.dumps(entries()[0])), [entries()[0]])

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

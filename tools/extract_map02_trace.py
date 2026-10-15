#!/usr/bin/env python3
"""Extract Map02 trace JSONL from noisy PC-port stdout/stderr captures.

Only JSON objects with the Map02 observation field signature are retained.
Malformed trace-looking lines are rejected rather than silently discarded.
Input is never modified; output defaults to stdout.
"""
import argparse
import json
import sys
from pathlib import Path

from tools.verify_map02_trace import evaluate_trace

TRACE_FIELDS = frozenset(("z", "x", "face", "stage"))


def parse_trace_line(raw_line: str, lineno: int):
    """Parse one game-output line; return a matching observation or None."""
    line = raw_line.strip()
    if not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        if all('"' + key + '"' in line for key in TRACE_FIELDS):
            raise ValueError(f"malformed Map02 trace object at line {lineno}: {exc.msg}") from exc
        return None
    if isinstance(obj, dict) and TRACE_FIELDS.issubset(obj):
        return obj
    return None


class TraceByteStream:
    """Decode pipe chunks into complete Map02 lines, retaining split UTF-8."""
    def __init__(self):
        self._pending = b""
        self.line_number = 0

    def feed(self, chunk: bytes, on_event=None) -> list:
        if not chunk:
            return []
        pieces = (self._pending + chunk).split(b"\n")
        self._pending = pieces.pop()
        events = []
        for piece in pieces:
            self.line_number += 1
            entry = parse_trace_line(piece.decode("utf-8", errors="replace"), self.line_number)
            if entry is not None:
                if on_event is None:
                    events.append(entry)
                else:
                    on_event(entry)
        return events

    def finish(self) -> list:
        if not self._pending:
            return []
        piece = self._pending
        self._pending = b""
        self.line_number += 1
        entry = parse_trace_line(piece.decode("utf-8", errors="replace"), self.line_number)
        return [entry] if entry is not None else []


def extract_trace_lines(lines) -> list:
    """Extract from a line iterator without materializing the entire raw log."""
    entries = []
    for lineno, raw_line in enumerate(lines, 1):
        entry = parse_trace_line(raw_line, lineno)
        if entry is not None:
            entries.append(entry)
    if not entries:
        raise ValueError("no Map02 trace events found in capture")
    return entries


def extract_trace_text(text: str) -> list:
    """Compatibility wrapper for in-memory captures and existing callers."""
    return extract_trace_lines(text.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", help="full game stdout/stderr capture, or '-' for stdin")
    parser.add_argument("-o", "--output", default="-", help="new JSONL output path, or '-' for stdout")
    parser.add_argument("--require-complete", action="store_true",
                        help="reject traces without both post_load and draw samples for both faces")
    parser.add_argument("--require-full-trace", action="store_true",
                        help="also require a preceding same-frame/path visit for each draw or skip")
    args = parser.parse_args()
    try:
        if args.capture == "-":
            entries = extract_trace_lines(sys.stdin)
        else:
            with Path(args.capture).open("r", encoding="utf-8",
                                         errors="replace") as handle:
                entries = extract_trace_lines(handle)
        if args.require_complete or args.require_full_trace:
            result = evaluate_trace(entries, require_full_trace=args.require_full_trace)
            if result["errors"]:
                raise ValueError("incomplete or invalid Map02 trace: " + "; ".join(result["errors"]))
        payload = "".join(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n" for entry in entries)
        if args.output == "-":
            sys.stdout.write(payload)
        else:
            with Path(args.output).open("x", encoding="utf-8") as out:
                out.write(payload)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Extracted {len(entries)} Map02 events; original capture unchanged.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

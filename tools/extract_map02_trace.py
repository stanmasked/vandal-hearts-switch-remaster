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


def extract_trace_text(text: str) -> list:
    entries = []
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            if all('"' + key + '"' in line for key in TRACE_FIELDS):
                raise ValueError(f"malformed Map02 trace object at line {lineno}: {exc.msg}") from exc
            continue
        if isinstance(obj, dict) and TRACE_FIELDS.issubset(obj):
            entries.append(obj)
    if not entries:
        raise ValueError("no Map02 trace events found in capture")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", help="full game stdout/stderr capture, or '-' for stdin")
    parser.add_argument("-o", "--output", default="-", help="new JSONL output path, or '-' for stdout")
    parser.add_argument("--require-complete", action="store_true",
                        help="reject traces without both post_load and draw samples for both faces")
    args = parser.parse_args()
    try:
        content = sys.stdin.read() if args.capture == "-" else Path(args.capture).read_text(encoding="utf-8")
        entries = extract_trace_text(content)
        if args.require_complete:
            result = evaluate_trace(entries)
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

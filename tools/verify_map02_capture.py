#!/usr/bin/env python3
"""Verify Map02 capture evidence without the original game or game assets.

Checks file fingerprints, independently re-extracts event lines from preserved
raw stdout and recomputes the stored analysis. This is an integrity/consistency
check, not a cryptographic signature or proof of correct rendered pixels.
"""
import argparse
import json
from pathlib import Path

from tools.capture_map02_runtime import sha256_file
from tools.extract_map02_trace import TraceByteStream
from tools.evaluate_map02_session import evaluate_capture_session

EVIDENCE_FILES = (
    ("raw_log", "game_stdout.log"),
    ("trace_jsonl", "map02_trace.jsonl"),
)


def verify_bundle(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("capture path must be a directory")
    report = json.loads((directory / "capture_report.json").read_text(encoding="utf-8"))
    if type(report) is not dict:
        raise ValueError("capture report must be a JSON object")

    for prefix, filename in EVIDENCE_FILES:
        path = directory / filename
        expected_sha = report.get(prefix + "_sha256")
        expected_size = report.get(prefix + "_bytes")
        exists = path.is_file()
        if not exists:
            if expected_sha is not None or expected_size is not None:
                raise ValueError(f"{filename}: missing file declared in report")
            continue
        if (type(expected_sha) is not str or len(expected_sha) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha)):
            raise ValueError(f"{filename}: missing or invalid SHA-256 in report")
        if type(expected_size) is not int or expected_size < 0:
            raise ValueError(f"{filename}: missing or invalid byte count in report")
        if path.stat().st_size != expected_size:
            raise ValueError(f"{filename}: byte count changed since capture")
        if sha256_file(path) != expected_sha:
            raise ValueError(f"{filename}: SHA-256 mismatch; evidence changed since capture")

    raw_path = directory / "game_stdout.log"
    trace_path = directory / "map02_trace.jsonl"
    if trace_path.exists() and not raw_path.exists():
        raise ValueError("derived trace exists without original stdout log")
    if not raw_path.exists() and not report.get("launch_error"):
        raise ValueError("missing raw stdout without recorded game launch failure")

    provenance = report.get("source_provenance")
    if type(provenance) is not dict or provenance.get("trace_mode") not in ("legacy", "full"):
        raise ValueError("capture report has invalid trace mode provenance")
    require_full_trace = provenance["trace_mode"] == "full"

    analysis = report.get("analysis")
    if type(analysis) is not dict or type(analysis.get("errors")) is not list:
        raise ValueError("capture report has invalid analysis")
    if type(report.get("trace_events")) is not int or report["trace_events"] < 0:
        raise ValueError("capture report has invalid trace event count")
    if raw_path.exists() and not trace_path.exists() and not report.get("launch_error"):
        raise ValueError("missing extracted JSONL after game launch")

    count = 0
    malformed = None
    if raw_path.exists() and trace_path.exists():
        with raw_path.open("rb") as raw, trace_path.open("r", encoding="utf-8") as derived:
            decoder = TraceByteStream()

            def compare_event(event):
                nonlocal count
                row = derived.readline()
                if not row:
                    raise ValueError(f"derived trace ends before raw event {count + 1}")
                try:
                    saved = json.loads(row)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON in derived trace line {count + 1}") from exc
                if saved != event:
                    raise ValueError(f"derived trace event {count + 1} does not match raw stdout")
                count += 1

            for chunk in iter(lambda: raw.read(65536), b""):
                try:
                    decoder.feed(chunk, on_event=compare_event)
                except ValueError as exc:
                    if "malformed Map02 trace object" not in str(exc):
                        raise
                    malformed = str(exc)
                    break
            if malformed is None:
                try:
                    for event in decoder.finish():
                        compare_event(event)
                except ValueError as exc:
                    if "malformed Map02 trace object" not in str(exc):
                        raise
                    malformed = str(exc)
            if derived.readline():
                raise ValueError("derived trace has extra events absent from raw stdout")

    if count != report["trace_events"]:
        raise ValueError("reported event count differs from verified JSONL")
    if malformed is not None:
        expected = {"errors": [malformed], "observations": []}
    elif count == 0:
        if report.get("launch_error"):
            expected = {"errors": ["failed to start or capture game process"],
                        "observations": []}
        else:
            expected = {"errors": ["no Map02 trace events found in capture"],
                        "observations": []}
    else:
        with trace_path.open("r", encoding="utf-8") as handle:
            expected = evaluate_capture_session(
                (json.loads(line) for line in handle if line.strip()),
                require_full_trace=require_full_trace,
            )
    if analysis != expected:
        raise ValueError("capture analysis differs from independent replay")

    complete = (not expected["errors"] and not report.get("interrupted", False)
                and report.get("game_exit_code") == 0
                and not report.get("launch_error"))
    return {
        "integrity": "verified",
        "trace_events": count,
        "complete_capture": complete,
        "raw_log_sha256": report.get("raw_log_sha256"),
        "trace_jsonl_sha256": report.get("trace_jsonl_sha256"),
        "warning": "SHA-256 and replay detect inconsistencies, not deliberate coordinated forgery or incorrect visual pixels.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_directory", type=Path,
                        help="directory with capture_report.json and saved trace evidence")
    parser.add_argument("--require-complete", action="store_true",
                        help="fail if evidence is valid but gameplay trace was incomplete")
    args = parser.parse_args()
    try:
        result = verify_bundle(args.capture_directory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return int(args.require_complete and not result["complete_capture"])


if __name__ == "__main__":
    raise SystemExit(main())

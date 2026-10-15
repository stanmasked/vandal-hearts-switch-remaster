#!/usr/bin/env python3
"""Run a locally prepared PC-port build and preserve map02 trace evidence.

The user must supply a runnable instrumented game and their own game assets.
No game data or log is uploaded. Does not infer that a binary matches its
source provenance: it records both provenance and the binary SHA-256.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from tools.extract_map02_trace import extract_trace_text
from tools.verify_map02_trace import evaluate_trace
from tools.prepare_map02_pcport import PINNED_BLOB_SHA1, PINNED_UPSTREAM_REF


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def executable_contains_marker(path: Path, marker: str) -> bool:
    needle = marker.encode("ascii") + b"\0"
    suffix = b""
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            data = suffix + chunk
            if needle in data:
                return True
            suffix = data[-(len(needle) - 1):]
    return False


def capture(executable: Path, trace_directory: Path, output_directory: Path,
            game_args=(), allow_modified_source=False) -> int:
    executable = executable.resolve(strict=True)
    if not executable.is_file():
        raise ValueError("executable must be a file")
    trace_directory = trace_directory.resolve(strict=True)
    provenance_file = trace_directory / "source_provenance.json"
    provenance = json.loads(provenance_file.read_text(encoding="utf-8"))
    if type(provenance) is not dict:
        raise ValueError("source provenance must be a JSON object")
    if provenance.get("trace_mode") not in ("legacy", "full"):
        raise ValueError("unrecognized trace_mode in source provenance")
    if provenance.get("upstream_reference") != PINNED_UPSTREAM_REF:
        raise ValueError("source provenance does not name the pinned upstream revision")
    source_files = provenance.get("source_files")
    if not isinstance(source_files, dict) or set(source_files) != set(PINNED_BLOB_SHA1):
        raise ValueError("source provenance must list the three pinned files")
    if type(provenance.get("allow_modified_source")) is not bool:
        raise ValueError("allow_modified_source must be a boolean in source provenance")
    for relative, expected_blob in PINNED_BLOB_SHA1.items():
        record = source_files[relative]
        if type(record) is not dict:
            raise ValueError(f"{relative}: source provenance must be an object")
        blob = record.get("git_blob_sha1")
        digest = record.get("sha256")
        if (type(blob) is not str or len(blob) != 40
                or any(char not in "0123456789abcdef" for char in blob)):
            raise ValueError(f"{relative}: invalid Git blob SHA-1 in source provenance")
        if (type(digest) is not str or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise ValueError(f"{relative}: invalid source SHA-256 in provenance")
        if record.get("matches_pinned") is not (blob == expected_blob):
            raise ValueError(f"{relative}: matches_pinned disagrees with Git blob SHA-1")
    if not allow_modified_source and (
        provenance["allow_modified_source"]
        or any(not record["matches_pinned"] for record in source_files.values())
    ):
        raise ValueError("source provenance is modified; use --allow-modified-source explicitly")
    generated_files = provenance.get("generated_files")
    expected_names = {"game_setup.trace.c", "graphics.trace.c", "map02_trace.mk"}
    if generated_files is None:
        raise ValueError("source provenance must fingerprint generated files")
    if not isinstance(generated_files, dict) or set(generated_files) != expected_names:
        raise ValueError("generated_files must fingerprint the three diagnostic build inputs")
    for filename, expected_sha256 in generated_files.items():
        if (type(expected_sha256) is not str or len(expected_sha256) != 64
                or any(char not in "0123456789abcdef" for char in expected_sha256)):
            raise ValueError(f"{filename}: invalid generated source SHA-256")
        current_path = trace_directory / filename
        if sha256_file(current_path) != expected_sha256:
            raise ValueError(f"{filename}: generated diagnostic build input changed since preparation")
    binary_sha256_before_launch = sha256_file(executable)
    if provenance["trace_mode"] == "full":
        marker = provenance.get("binary_marker")
        if type(marker) is not str or re.fullmatch(
                r"VH_MAP02_TRACE_BUILD_ID:[0-9a-f]{64}", marker) is None:
            raise ValueError("full trace provenance must include a valid binary marker")
        if not executable_contains_marker(executable, marker):
            raise ValueError("executable missing expected full-trace build marker; wrong or unlinked binary")
        loader_marker = provenance.get("binary_loader_marker")
        if type(loader_marker) is not str or re.fullmatch(
                r"VH_MAP02_TRACE_LOADER_ID:[0-9a-f]{64}", loader_marker) is None:
            raise ValueError("full trace provenance must include a valid loader build marker")
        if loader_marker.split(":", 1)[1] != marker.split(":", 1)[1]:
            raise ValueError("loader and renderer build markers have different identities")
        if not executable_contains_marker(executable, loader_marker):
            raise ValueError("executable missing expected loader trace marker; wrong or unlinked loader")
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError("output directory already exists; refusing to overwrite")
    output_directory.mkdir(parents=True)
    raw_path = output_directory / "game_stdout.log"
    command = [str(executable), *game_args]
    try:
        with raw_path.open("xb") as raw:
            # Preserve original bytes. Decode only when displaying or parsing trace events.
            with subprocess.Popen(command, cwd=executable.parent, stdin=None,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  bufsize=0) as proc:
                echo_output = True
                for chunk in iter(lambda: proc.stdout.read(65536), b""):
                    raw.write(chunk)
                    if echo_output:
                        try:
                            if hasattr(sys.stdout, "buffer"):
                                sys.stdout.buffer.write(chunk)
                                sys.stdout.buffer.flush()
                            else:
                                sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                                sys.stdout.flush()
                        except BrokenPipeError:
                            # The user's output pipe closed; raw evidence must survive.
                            echo_output = False
                returncode = proc.wait()
    except OSError as exc:
        # The output directory already exists: leave a useful report, not an empty folder.
        failure = {
            "binary_sha256": binary_sha256_before_launch,
            "binary": str(executable),
            "game_exit_code": None,
            "launch_error": f"{type(exc).__name__}: {exc}",
            "trace_events": 0,
            "analysis": {"errors": ["failed to start or capture game process"],
                         "observations": []},
            "source_provenance": provenance,
            "warning": "The game did not complete a diagnostic capture.",
        }
        (output_directory / "capture_report.json").write_text(
            json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(f"Map02 game launch/capture failed: {exc}", file=sys.stderr)
        return 1
    summary = {
        "binary_sha256": binary_sha256_before_launch,
        "binary": str(executable),
        "game_exit_code": returncode,
        "source_provenance": provenance,
        "warning": "A matching source manifest does not establish that the binary was compiled from it.",
    }
    try:
        entries = extract_trace_text(raw_path.read_bytes().decode("utf-8", errors="replace"))
    except ValueError as exc:
        summary["trace_events"] = 0
        summary["analysis"] = {"errors": [str(exc)], "observations": []}
    else:
        (output_directory / "map02_trace.jsonl").write_text(
            "".join(json.dumps(entry, separators=(",", ":")) + "\n" for entry in entries),
            encoding="utf-8")
        summary["trace_events"] = len(entries)
        summary["analysis"] = evaluate_trace(entries)
    (output_directory / "capture_report.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    errors = summary["analysis"]["errors"]
    if errors:
        print(f"Map02 trace incomplete/invalid ({len(errors)} issue(s)); see capture_report.json",
              file=sys.stderr)
    else:
        print("Map02 trace complete and internally consistent (not proof of correct pixels).",
              file=sys.stderr)
    if returncode != 0:
        print(f"Game exited with code {returncode}.", file=sys.stderr)
        return 1
    return 2 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, help="instrumented PC-port executable")
    parser.add_argument("trace_directory", type=Path,
                        help="directory generated by prepare_map02_pcport.py")
    parser.add_argument("new_output_directory", type=Path,
                        help="new folder for raw logs and JSON analysis")
    parser.add_argument("--allow-modified-source", action="store_true",
                        help="accept a diagnostic build generated from modified source files")
    parser.add_argument("game_args", nargs=argparse.REMAINDER,
                        help="optional arguments passed verbatim to the game")
    args = parser.parse_args()
    try:
        return capture(args.executable, args.trace_directory, args.new_output_directory,
                       game_args=args.game_args, allow_modified_source=args.allow_modified_source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fail-closed cross-check of a RU MAP02 source receipt and PC trace capture.

Inputs stay on the user's computer. This joins independent *claims* and
hash/replay evidence, not a cryptographically authenticated same-run capture.
In particular, the trace is NOT bound to the opened private disc by this tool.
No original images, texture pixels, or executable payload are published.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from tools.check_map02_ru_receipt import check_receipt
from tools.prepare_map02_pcport import PINNED_BLOB_SHA1, PINNED_UPSTREAM_REF
from tools.verify_map02_capture import verify_bundle

EXPECTED = {
    "PRS": {(8, 19, 0): 641, (11, 11, 0): 643},
    "DAT": {(8, 19, 0): 498, (11, 11, 0): 550},
}
CAPTURE_FILES = ("capture_report.json", "game_stdout.log", "map02_trace.jsonl")
DIGEST = re.compile(r"[0-9a-f]{64}")


def private_file(path, *, max_bytes):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("input must be an ordinary, non-symlink file")
    if not 0 < path.stat().st_size <= max_bytes:
        raise ValueError("input exceeds private evidence size limit")
    return path.read_bytes()


def ensure_analysis(analysis):
    """Require BOTH target faces and one variant in each independent map load."""
    if type(analysis) is not dict or analysis.get("errors") != []:
        raise ValueError("replayed MAP02 analysis contains errors")
    loads = analysis.get("map_loads", [analysis])
    if type(loads) is not list or not loads:
        raise ValueError("no independently evaluated map loads")
    choices = []
    for load in loads:
        if type(load) is not dict or load.get("errors") != []:
            raise ValueError("map-load episode failed replay")
        source = load.get("post_load_overall_variant")
        draw = load.get("draw_overall_variant")
        if source not in EXPECTED or source != draw:
            raise ValueError("load and draw variants are mixed, unknown or inconsistent")
        observations = load.get("observations")
        if type(observations) is not list or len(observations) != 2:
            raise ValueError("each load needs exactly two source-face observations")
        indexed = {}
        for row in observations:
            if type(row) is not dict:
                raise ValueError("malformed source-face observation")
            key = (row.get("z"), row.get("x"), row.get("face"))
            if key in indexed:
                raise ValueError("duplicated target face")
            indexed[key] = row
        if set(indexed) != set(EXPECTED[source]):
            raise ValueError("missing target face")
        for position, expected_gfx in EXPECTED[source].items():
            row = indexed[position]
            for name in ("post_load_gfx", "draw_gfx"):
                value = row.get(name)
                if type(value) is not int or value != expected_gfx:
                    raise ValueError("reported face GFX inconsistent with " + source)
            if row.get("draw_status") != "submitted":
                raise ValueError("face was not submitted to the renderer")
            if type(row.get("visit_observation_count")) is not int or row["visit_observation_count"] < 1:
                raise ValueError("missing full trace renderer visit")
            if type(row.get("draw_observation_count")) is not int or row["draw_observation_count"] < 1:
                raise ValueError("missing rendered-face submission")
        choices.append(source)
    if len(set(choices)) != 1:
        raise ValueError("source variant changed across map-load episodes")
    if (analysis.get("post_load_overall_variant") != choices[0] or
            analysis.get("draw_overall_variant") != choices[0]):
        raise ValueError("aggregate variant disagrees with episodes")
    return choices[0], len(loads)


def check_source_provenance(report):
    provenance = report.get("source_provenance")
    if type(provenance) is not dict:
        raise ValueError("missing PC-port trace provenance")
    if (provenance.get("trace_mode") != "full" or
            provenance.get("allow_modified_source") is not False or
            provenance.get("upstream_reference") != PINNED_UPSTREAM_REF):
        raise ValueError("capture is not the pinned, unmodified full-trace variant")
    source_files = provenance.get("source_files")
    if type(source_files) is not dict or set(source_files) != set(PINNED_BLOB_SHA1):
        raise ValueError("incomplete pinned source file list")
    for name, expected in PINNED_BLOB_SHA1.items():
        row = source_files[name]
        if (type(row) is not dict or row.get("matches_pinned") is not True
                or row.get("git_blob_sha1") != expected):
            raise ValueError("wrong pinned source fingerprint")
    binary = report.get("binary_sha256")
    if type(binary) is not str or DIGEST.fullmatch(binary) is None:
        raise ValueError("missing captured executable SHA-256")
    return binary


def reconcile(receipt, capture_directory):
    receipt_bytes = private_file(receipt, max_bytes=32768)
    check_receipt(json.loads(receipt_bytes.decode("utf-8")))
    directory = Path(capture_directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("capture directory must not be a symbolic link")
    for name in CAPTURE_FILES:
        candidate = directory / name
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("missing or redirected private capture input: " + name)
    # The existing checker reads original saved stdout, replays into the
    # expected JSONL stream, checks hashes and recomputes every map-load result.
    capture = verify_bundle(directory)
    if not capture["complete_capture"] or capture["integrity"] != "verified":
        raise ValueError("capture did not complete its independent replay gate")
    raw_report = private_file(directory / "capture_report.json", max_bytes=8 * 1024 * 1024)
    report = json.loads(raw_report.decode("utf-8"))
    binary = check_source_provenance(report)
    variant, loads = ensure_analysis(report["analysis"])
    return {
        "schema": "vh.map02.ru-source-trace-reconciliation.v1",
        "source_receipt_consistent": True,
        "capture_stdout_independently_replayed": True,
        "pc_trace_consistent_variant": variant,
        "separate_map_loads_checked": loads,
        "target_faces_with_submissions_per_load": 2,
        "source_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "capture_report_sha256": hashlib.sha256(raw_report).hexdigest(),
        "trace_jsonl_sha256": capture["trace_jsonl_sha256"],
        "capture_executable_sha256": binary,
        "same_owned_disc_used_by_executable_proven": False,
        "native_gpu_ft4_and_vram_verified_by_this_tool": False,
        "original_gameplay_authenticated": False,
        "physical_ps1_equivalence_proven": False,
        "warning": "Coherent local reports, not a same-run disc/GPU proof. Synthetic traces can pass.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ru_receipt", type=Path, help="private MAP02 RU JSON from v10.1")
    parser.add_argument("capture_directory", type=Path,
                        help="private PC-port capture with preserved original stdout")
    args = parser.parse_args()
    try:
        result = reconcile(args.ru_receipt, args.capture_directory)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

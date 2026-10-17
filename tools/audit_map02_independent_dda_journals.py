"""Offline envelope audit for *independent* native MAP02 DDA journals.

A rejected-edge candidate is not an executed dda_span call. Both formats
are structurally validated, but neither authenticates the game or hardware.
This intentionally does NOT feed candidate rows into map02_dda_span_join.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.verify_map02_dda_native_spans import parse_native_spans
from tools.verify_map02_dda_rejected_edges import validate as validate_candidates
from tools.verify_map02_native_gpu_capture import verify_capture, LOG as NATIVE_GPU_LOG

SPAN_FILE = "dda-native-spans.jsonl"
CANDIDATE_FILE = "dda-rejected-edge-candidates.jsonl"


def audit(directory: Path, *, native_frame=None):
    """Read available native journals without inventing missing observations."""
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("journal directory is missing or is a symlink")
    inputs = {}
    validated_raw = {}
    for filename, parser in (
        (SPAN_FILE, parse_native_spans),
        (CANDIDATE_FILE, validate_candidates),
    ):
        path = directory / filename
        if path.is_symlink():
            raise ValueError("symlinked journal is not accepted")
        if not path.exists():
            inputs[filename] = {"present": False, "event_count": None, "sha256": None}
            continue
        if not path.is_file():
            raise ValueError("journal must be a regular file")
        raw = path.read_bytes()
        records = parser(raw)  # fail closed on malformed, saturated journals
        validated_raw[filename] = raw
        inputs[filename] = {
            "present": True,
            "event_count": len(records),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        if filename == SPAN_FILE:
            spans = records
        else:
            candidates = records
    if not any(entry["present"] for entry in inputs.values()):
        raise ValueError("no native DDA journals found")
    spans = spans if inputs[SPAN_FILE]["present"] else []
    candidates = candidates if inputs[CANDIDATE_FILE]["present"] else []
    span_keys = {(x.frame, x.primitive_ordinal, x.y) for x in spans}
    candidate_keys = {(x["frame"], x["primitive_ordinal"], x["y"])
                      for x in candidates}
    span_frames = {x.frame for x in spans}
    candidate_frames = {x["frame"] for x in candidates}
    # Both C observers sample the same configured Y in a single target
    # DrawOTag frame. Independently valid files from different sample
    # settings must never be treated as a joint capture.
    sample_keys = {(x.frame, x.y) for x in spans} | {
        (x["frame"], x["y"]) for x in candidates
    }
    if len(sample_keys) != 1:
        raise ValueError("mixed DDA capture frame or selected sample Y")
    # In one drawing area a single row cannot both enter dda_span and be
    # rejected by the outer vertical clip for the same primitive.
    if span_keys & candidate_keys:
        raise ValueError("same DDA primitive row entered and vertically rejected")
    clip_windows = {}
    for frame, ordinal, top, bottom in (
        [(x.frame, x.primitive_ordinal, x.clip_t, x.clip_b) for x in spans]
        + [(x["frame"], x["primitive_ordinal"], x["clip_t"], x["clip_b"])
           for x in candidates]
    ):
        key = (frame, ordinal)
        window = (top, bottom)
        if key in clip_windows and clip_windows[key] != window:
            raise ValueError("conflicting DDA clip window within one primitive")
        clip_windows[key] = window
    gpu_binding = {
        "requested": native_frame is not None,
        "verified": False,
        "frame": None,
        "gpu_events_sha256": None,
        "vram_snapshot_sha256_list_sha256": None,
        "upload_payload_sha256_list_sha256": None,
        "load_pairs_with_verified_payload": None,
        "load_pairs_with_verified_vram_effect": None,
        "load_pairs_without_payload": None,
        "native_gpu_pairs_verified": None,
        "move_pairs_with_verified_vram_effect": None,
        "clear_pairs_with_verified_vram_effect": None,
        "draw_boundary_vram_checks": None,
        "draw_boundary_gpu_state_checks": None,
        "draw_primitives_in_bounded_capture": None,
        "observed_dda_primitive_keys": None,
    }
    if native_frame is not None:
        if type(native_frame) is not int or not 1 <= native_frame <= 0xffffffff:
            raise ValueError("invalid requested native GPU frame")
        # Validates full private 1-MiB VRAM snapshots and contiguous
        # before/after GPU events before comparing any DDA identifiers.
        capture = verify_capture(directory, target_frame=native_frame)
        if capture["record_cap_reached"]:
            raise ValueError("bounded native GPU capture saturated; ordinal scope unknown")
        if any(x.frame != native_frame for x in spans) or any(
                x["frame"] != native_frame for x in candidates):
            raise ValueError("DDA journal frame disagrees with validated GPU capture")
        gpu_log = directory / NATIVE_GPU_LOG
        if gpu_log.is_symlink() or not gpu_log.is_file():
            raise ValueError("native GPU journal must be a regular file")
        native_raw = gpu_log.read_bytes()
        if hashlib.sha256(native_raw).hexdigest() != capture["native_gpu_events_sha256"]:
            raise ValueError("native GPU event bytes changed since full VRAM validation")
        events = [json.loads(line) for line in native_raw.splitlines()]
        draw_packets = [events[i] for i in range(0, len(events), 2)
                        if events[i]["operation"] == "draw"]
        for span in spans:
            if span.primitive_ordinal >= len(draw_packets):
                raise ValueError("executed DDA span ordinal absent from GPU event stream")
            # Span includes primitive_type in its journal; the parser only
            # exposes geometry, so re-read the strictly validated JSONL.
            # Type matching is performed below against that input.
        if inputs[SPAN_FILE]["present"]:
            # Reuse the exact bytes hashed and validated above, rather
            # than re-opening a mutable journal between validation and join.
            span_records = [json.loads(line) for line in
                            validated_raw[SPAN_FILE].splitlines()]
            for span_record in span_records:
                native_type = draw_packets[span_record["primitive_ordinal"]]["primitive_type"]
                if span_record["primitive_type"] != native_type:
                    raise ValueError("entered span primitive type disagrees with GPU packet")
        for candidate in candidates:
            if candidate["primitive_ordinal"] >= len(draw_packets):
                raise ValueError("rejected edge ordinal absent from GPU event stream")
        gpu_binding = {
            "requested": True,
            "verified": True,
            "frame": native_frame,
            "gpu_events_sha256": capture["native_gpu_events_sha256"],
            "vram_snapshot_sha256_list_sha256": capture["vram_snapshot_sha256_list_sha256"],
            "upload_payload_sha256_list_sha256": capture["upload_payload_sha256_list_sha256"],
            "load_pairs_with_verified_payload": capture["load_pairs_with_verified_payload"],
            "load_pairs_with_verified_vram_effect": capture["load_pairs_with_verified_vram_effect"],
            "load_pairs_without_payload": capture["load_pairs_without_payload"],
            "native_gpu_pairs_verified": capture["native_gpu_pairs_verified"],
            "move_pairs_with_verified_vram_effect": capture["move_pairs_with_verified_vram_effect"],
            "clear_pairs_with_verified_vram_effect": capture["clear_pairs_with_verified_vram_effect"],
            "draw_boundary_vram_checks": capture["draw_boundary_vram_checks"],
            "draw_boundary_gpu_state_checks": capture["draw_boundary_gpu_state_checks"],
            "draw_primitives_in_bounded_capture": len(draw_packets),
            "observed_dda_primitive_keys": len({
                x.primitive_ordinal for x in spans
            } | {x["primitive_ordinal"] for x in candidates}),
        }
    return {
        "schema": "map02_independent_dda_journal_audit_v1",
        "files": inputs,
        "shared_frame_ids": sorted(span_frames & candidate_frames),
        "same_primitive_row_keys": len(span_keys & candidate_keys),
        "single_sample_envelope_consistent": True,
        # A missing journal is an absence of recorded evidence, NOT a claim
        # of zero executed or vertically rejected rows.
        "dda_observation_mode": ("both" if spans and candidates else
                                 "entered_only" if spans else "rejected_only"),
        "all_dda_journal_classes_observed": bool(spans and candidates),
        "native_gpu_binding": gpu_binding,
        "notes": [
            "Missing journals mean missing observations, not zero GPU events.",
            "Same row keys do not establish shared rasterizer provenance.",
            "Rejected edge candidates never represent executed dda_span calls.",
            "Native span records cannot recover vertically rejected rows.",
        ],
        "journal_origin_authenticated": False,
        "retail_map02_frame_verified": False,
        "rejected_triangle_pixel_coverage_verified": False,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal_directory", type=Path)
    parser.add_argument("--native-frame", type=int, help="Require full native VRAM evidence for this DrawOTag frame")
    args = parser.parse_args()
    try:
        result = audit(args.journal_directory, native_frame=args.native_frame)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

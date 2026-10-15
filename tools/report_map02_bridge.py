#!/usr/bin/env python3
"""Create a conservative bridge-face review from a verified Map02 capture.

This reviews *runtime observations*, not framebuffer pixels or original disc
textures. Verify the raw stdout / JSONL evidence before trusting the report.
"""
import argparse
import json
from pathlib import Path

from tools.verify_map02_capture import verify_bundle
from tools.verify_map02_trace import TARGETS

FACE_LABELS = {
    (8, 19, 0): "Bridge face A",
    (11, 11, 0): "Bridge face B",
}
GPU_FIELDS = ("u", "v", "clut", "tpage")


def review_capture(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    integrity = verify_bundle(directory)  # Replays original stdout and hashes.
    capture = json.loads((directory / "capture_report.json").read_text(encoding="utf-8"))
    analysis = capture.get("analysis") or {}
    def faces_for(single_analysis):
        by_position = {}
        for entry in single_analysis.get("observations") or []:
            if not isinstance(entry, dict):
                continue
            pos = (entry.get("z"), entry.get("x"), entry.get("face"))
            if pos in TARGETS:
                by_position[pos] = entry

        faces = []
        for pos, (prs_gfx, dat_gfx) in TARGETS.items():
            entry = by_position.get(pos, {})
            metadata = entry.get("draw_metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            faces.append({
                "label": FACE_LABELS[pos],
                "position": {"z": pos[0], "x": pos[1], "face": pos[2]},
                "expected_prs_gfx": prs_gfx,
                "expected_dat_gfx": dat_gfx,
                "post_load_gfx": entry.get("post_load_gfx"),
                "post_load_variant": entry.get("post_load_variant"),
                "draw_gfx": entry.get("draw_gfx"),
                "draw_variant": entry.get("draw_variant"),
                "draw_status": entry.get("draw_status", "not_observed"),
                "draw_submissions": entry.get("draw_observation_count", 0),
                "renderer_visits": entry.get("visit_observation_count", 0),
                "renderer_skips": entry.get("skip_observation_count", 0),
                "paths": entry.get("draw_paths", []),
                "draw_gpu_primitive": {field: metadata.get(field) for field in GPU_FIELDS},
            })
        return faces

    loads = analysis.get("map_loads") or [analysis]
    map_loads = []
    for index, episode in enumerate(loads, 1):
        faces = faces_for(episode)
        map_loads.append({
            "number": index,
            "event_range": episode.get("event_range"),
            "post_load_variant": episode.get("post_load_overall_variant"),
            "draw_variant": episode.get("draw_overall_variant"),
            "errors": episode.get("errors") or [],
            "faces": faces,
        })
    errors = analysis.get("errors") or []
    consistent = integrity["complete_capture"] and not errors
    post_variant = analysis.get("post_load_overall_variant")
    draw_variant = analysis.get("draw_overall_variant")
    agreed = (post_variant in ("PRS", "DAT")
              and post_variant == draw_variant
              and all(not load["errors"] and all(face["draw_submissions"] > 0
                  for face in load["faces"]) for load in map_loads))
    variant = post_variant if consistent and agreed else "undetermined"
    # With repeated map loads, never expose one flattened pair of face values
    # that might silently represent different gameplay episodes.
    faces = map_loads[0]["faces"] if len(map_loads) == 1 else []
    return {
        "kind": "map02_bridge_runtime_review",
        "evidence_integrity": integrity["integrity"],
        "capture_complete": integrity["complete_capture"],
        "runtime_variant": variant,
        "runtime_variant_scope": (
            f"both target faces across {len(map_loads)} independent map load(s): "
            "post-load and AddPrim submission"
            if variant != "undetermined"
            else "insufficient or inconsistent runtime evidence"
        ),
        "source_trace_mode": (capture.get("source_provenance") or {}).get("trace_mode"),
        "binary_sha256": capture.get("binary_sha256"),
        "raw_log_sha256": integrity.get("raw_log_sha256"),
        "trace_jsonl_sha256": integrity.get("trace_jsonl_sha256"),
        "trace_events": integrity["trace_events"],
        "errors": errors,
        "map_load_count": len(map_loads),
        "map_loads": map_loads,
        "faces": faces,
        "pixels_visually_verified": False,
        "caveat": (
            "A draw event proves an instrumented AddPrim submission, not an onscreen pixel. "
            "CLUT and tpage values are GPU primitive IDs, not raw LAND_DT indices. "
            "Do not choose or replace PRS/DAT artwork without actual gameplay comparison."
        ),
    }


def markdown_review(report: dict) -> str:
    lines = [
        "# M_MAP02 bridge — runtime evidence review",
        "",
        "**Evidence:** " + report["evidence_integrity"],
        "**Capture complete:** " + ("yes" if report["capture_complete"] else "no"),
        "**Runtime PRS/DAT identification:** " + report["runtime_variant"],
        "**Scope:** " + report["runtime_variant_scope"],
        "**Visible pixels confirmed:** no",
        f'**Map load episodes:** {report["map_load_count"]}',
    ]
    for load in report["map_loads"]:
        if report["map_load_count"] > 1:
            bounds = load.get("event_range")
            suffix = (f' — JSONL events {bounds["first"]}–{bounds["last"]}'
                      if bounds is not None else "")
            lines.extend(["", f'## Map load {load["number"]}{suffix}',
                          f'Post-load variant: {load["post_load_variant"]}; '
                          f'AddPrim variant: {load["draw_variant"]}'])
        lines.extend([
            "",
            "| Face (z,x,index) | PRS/DAT GFX | Post-load | AddPrim GFX | "
            "Submissions / visits / skips |",
            "| --- | --- | --- | --- | --- |",
        ])
        for face in load["faces"]:
            pos = face["position"]
            coordinate = f'{pos["z"]},{pos["x"]},{pos["face"]}'
            prs_dat = f'{face["expected_prs_gfx"]} / {face["expected_dat_gfx"]}'
            post = str(face["post_load_gfx"]) if face["post_load_gfx"] is not None else "absent"
            draw = str(face["draw_gfx"]) if face["draw_gfx"] is not None else "absent"
            counts = (f'{face["draw_submissions"]} / '
                      f'{face["renderer_visits"]} / {face["renderer_skips"]}')
            lines.append(f'| {face["label"]} ({coordinate}) | {prs_dat} | {post} | {draw} | {counts} |')
        lines.extend(["", "### Submitted GPU primitive fields", ""])
        for face in load["faces"]:
            metadata = face["draw_gpu_primitive"]
            formatted = ", ".join(f"{name}={metadata[name]}" if metadata[name] is not None
                                  else f"{name}=not recorded" for name in GPU_FIELDS)
            lines.append(f'- {face["label"]}: {formatted}; draw paths: '
                         + (", ".join(face["paths"]) or "none"))
    if report["errors"]:
        lines.extend(["", "## Validation errors", ""])
        lines.extend(f"- {error}" for error in report["errors"])
    lines.extend(["", "## Evidence fingerprints", "",
                  f'- Binary: {report["binary_sha256"] or "not recorded"}',
                  f'- Raw stdout: {report["raw_log_sha256"] or "not recorded"}',
                  f'- Extracted JSONL: {report["trace_jsonl_sha256"] or "not recorded"}',
                  "",
                  report["caveat"], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_directory", type=Path)
    parser.add_argument("--markdown", type=Path,
                        help="new output path for a human-readable bridge review")
    parser.add_argument("--json", type=Path, dest="json_output",
                        help="new output path for a machine-readable bridge review")
    parser.add_argument("--require-complete", action="store_true",
                        help="return 1 unless both target faces have verified agreeing draws")
    args = parser.parse_args()
    try:
        result = review_capture(args.capture_directory)
        # Exclusive creation: preserve previously reviewed evidence.
        if args.markdown:
            with args.markdown.open("x", encoding="utf-8") as output:
                output.write(markdown_review(result))
        if args.json_output:
            with args.json_output.open("x", encoding="utf-8") as output:
                json.dump(result, output, ensure_ascii=False, indent=2)
                output.write("\n")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(markdown_review(result))
    return int(args.require_complete and result["runtime_variant"] == "undetermined")


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate captured map-11 (resource M_MAP02) runtime face GFX observations.

Input: JSON array or JSON Lines of objects with integer z,x,face,gfx and string stage.
Stage is 'post_load' or 'draw'. gfx is the *global* index (after +400).
This is an observational consistency checker, not a proof of visual correctness.
"""
import argparse
from collections.abc import Iterable
import json
from pathlib import Path

TARGETS = {(8, 19, 0): (641, 498), (11, 11, 0): (643, 550)}
STAGES = {"post_load", "draw", "skip", "visit"}
DRAW_PATHS = {"normal", "edge", "overhead"}
SKIP_REASONS = {"null_gfx", "backface"}


def evaluate_trace(entries, *, require_full_trace=False):
    if isinstance(entries, (str, bytes, dict)) or not isinstance(entries, Iterable):
        raise ValueError("trace must be a JSON list or iterable of observation objects")
    found = {}
    draw_metadata = {}
    seen_draw_frames = set()
    draw_frame_mode = {}
    draw_path_mode = {}
    draw_paths = {}
    draw_count = {}
    skip_reasons = {}
    skip_count = {}
    visit_count = {}
    visit_paths = {}
    observed_face_counts = {}
    seen_skips = set()
    # Full-trace C hooks record each renderer entry before face submission.
    # Correlate by (face, frame, rendering path), not by frame alone.
    visit_gfx_by_context = {}
    preceding_nonempty_visits = set()
    # A single game frame can contain multiple renderer calls on one tile/path.
    # Number visits so a second real call is not mistaken for a duplicate.
    visit_generation = {}
    latest_visit_nonempty = {}
    latest_visit_gfx = {}
    # A nonempty full-trace visit represents exactly one face-0 decision.
    # Each invocation must terminate as draw or skip, never both.
    pending_visit_outcomes = {}
    terminal_visit_outcomes = set()
    draw_gfx_by_context = {}
    backface_gfx_by_context = {}
    errors = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {i}: expected object")
            continue
        if any(type(entry.get(k)) is not int for k in ("z", "x", "face", "gfx")):
            errors.append(f"entry {i}: z,x,face,gfx must be integers")
            continue
        pos = (entry["z"], entry["x"], entry["face"])
        if pos not in TARGETS:
            continue
        stage = entry.get("stage")
        if type(stage) is not str or stage not in STAGES:
            errors.append(f"entry {i}: invalid stage")
            continue
        if stage == "visit":
            frame = entry.get("frame")
            path = entry.get("path")
            face_count = entry.get("face_count")
            if type(frame) is not int or frame < 0:
                errors.append(f"entry {i}: visit frame must be a non-negative integer")
                continue
            if type(path) is not str or path not in DRAW_PATHS:
                errors.append(f"entry {i}: visit path must be normal, edge, or overhead")
                continue
            if type(face_count) is not int or not 0 <= face_count <= 18:
                errors.append(f"entry {i}: face_count must be an integer from 0 to 18")
                continue
            visit_count[pos] = visit_count.get(pos, 0) + 1
            context = (pos, frame, path)
            visit_generation[context] = visit_generation.get(context, 0) + 1
            latest_visit_nonempty[context] = face_count > 0
            latest_visit_gfx[context] = entry["gfx"] if face_count > 0 else None
            if require_full_trace and face_count > 0:
                pending_visit_outcomes[(context, visit_generation[context])] = i
            if face_count > 0:
                preceding_nonempty_visits.add((pos, frame, path))
                visit_gfx_by_context.setdefault((pos, frame, path), set()).add(entry["gfx"])
            visit_paths.setdefault(pos, set()).add(path)
            observed_face_counts.setdefault(pos, set()).add(face_count)
            if face_count == 0 and entry["gfx"] != 0:
                errors.append(f"entry {i}: zero-face visit must have GFX 0")
            if face_count > 0 and entry["gfx"] not in (*TARGETS[pos], 0):
                errors.append(f"unexpected GFX {entry['gfx']} for {pos} at visit")
            continue
        if stage == "skip":
            frame = entry.get("frame")
            path = entry.get("path")
            reason = entry.get("reason")
            if type(frame) is not int or frame < 0:
                errors.append(f"entry {i}: skip frame must be a non-negative integer")
                continue
            if type(path) is not str or path not in DRAW_PATHS:
                errors.append(f"entry {i}: skip path must be normal, edge, or overhead")
                continue
            if type(reason) is not str or reason not in SKIP_REASONS:
                errors.append(f"entry {i}: invalid skip reason")
                continue
            context = (pos, frame, path)
            if require_full_trace and not latest_visit_nonempty.get(context, False):
                errors.append(
                    f"full trace skip without preceding nonempty visit for {pos}"
                    f" in frame {frame}, path {path}"
                )
                continue
            if require_full_trace and reason == "backface" and entry["gfx"] != latest_visit_gfx[context]:
                errors.append(
                    f"full trace backface GFX mismatch with latest visit for {pos}"
                    f" in frame {frame}, path {path}"
                )
            if require_full_trace and reason == "null_gfx" and latest_visit_gfx[context] != 0:
                errors.append(
                    f"full trace null_gfx GFX mismatch with latest visit for {pos}"
                    f" in frame {frame}, path {path}"
                )
            if require_full_trace and reason == "null_gfx" and path == "edge":
                errors.append(
                    f"full trace edge renderer cannot emit null_gfx skip for {pos}"
                    f" in frame {frame}"
                )
            key = ((pos, frame, path, reason, visit_generation[context])
                   if require_full_trace else (pos, frame, path, reason))
            if key in seen_skips:
                errors.append(f"duplicate skip observation for {pos} in frame {frame}, path {path}")
                continue
            if require_full_trace:
                outcome = (context, visit_generation[context])
                if outcome in terminal_visit_outcomes:
                    errors.append(
                        f"full trace multiple terminal outcomes for {pos}"
                        f" in frame {frame}, path {path}"
                    )
                    continue
                terminal_visit_outcomes.add(outcome)
                pending_visit_outcomes.pop(outcome, None)
            seen_skips.add(key)
            skip_count[pos] = skip_count.get(pos, 0) + 1
            skip_reasons.setdefault(pos, set()).add(reason)
            if reason == "backface":
                backface_gfx_by_context.setdefault((pos, frame, path), set()).add(entry["gfx"])
                if entry["gfx"] not in (*TARGETS[pos], 0):
                    errors.append(f"unexpected GFX {entry['gfx']} for {pos} at skip")
            if reason == "null_gfx" and entry["gfx"] != 0:
                errors.append(f"null_gfx skip must have GFX 0 for {pos}")
            continue
        if stage == "draw":
            framed = "frame" in entry
            tagged_path = "path" in entry
            if tagged_path and (type(entry["path"]) is not str or entry["path"] not in DRAW_PATHS):
                errors.append(f"entry {i}: path must be normal, edge, or overhead")
                continue
            # Reject invalid frames before mutating per-face framing state.
            # Otherwise an invalid sample can falsely poison the next valid draw.
            if framed and (type(entry["frame"]) is not int or entry["frame"] < 0):
                errors.append(f"entry {i}: frame must be a non-negative integer")
                continue
            if require_full_trace:
                if not framed or not tagged_path:
                    errors.append(f"entry {i}: full trace draw requires frame and path")
                    continue
                context = (pos, entry["frame"], entry["path"])
                if not latest_visit_nonempty.get(context, False):
                    errors.append(
                        f"full trace draw without preceding nonempty visit for {pos}"
                        f" in frame {entry['frame']}, path {entry['path']}"
                    )
                    continue
                if entry["gfx"] != latest_visit_gfx[context]:
                    errors.append(
                        f"full trace draw GFX mismatch with latest visit for {pos}"
                        f" in frame {entry['frame']}, path {entry['path']}"
                    )
            if pos in draw_frame_mode and draw_frame_mode[pos] != framed:
                errors.append(f"mixed framed and unframed draw observations for {pos}")
                continue
            if pos in draw_path_mode and draw_path_mode[pos] != tagged_path:
                errors.append(f"mixed annotated and unannotated draw paths for {pos}")
                continue
            draw_frame_mode[pos] = framed
            draw_path_mode[pos] = tagged_path
        if stage == "draw" and "frame" in entry:
            frame = entry["frame"]
            key = ((pos, frame, entry["path"], visit_generation[(pos, frame, entry["path"])])
                   if require_full_trace else
                   (pos, frame, entry.get("path", "unspecified")))
            if key in seen_draw_frames:
                errors.append(f"duplicate draw observation for {pos} in frame {frame}")
                continue
            if require_full_trace:
                context = (pos, frame, entry["path"])
                outcome = (context, visit_generation[context])
                if outcome in terminal_visit_outcomes:
                    errors.append(
                        f"full trace multiple terminal outcomes for {pos}"
                        f" in frame {frame}, path {entry['path']}"
                    )
                    continue
                terminal_visit_outcomes.add(outcome)
                pending_visit_outcomes.pop(outcome, None)
            seen_draw_frames.add(key)
            if tagged_path:
                draw_gfx_by_context.setdefault((pos, frame, entry["path"]), set()).add(entry["gfx"])
            draw_paths.setdefault(pos, set()).add(entry.get("path", "unspecified"))
            draw_count[pos] = draw_count.get(pos, 0) + 1
            if (pos, stage) in found:
                if found[(pos, stage)] != entry["gfx"]:
                    errors.append(f"GFX changed across frames for {pos}")
                if entry["gfx"] not in TARGETS[pos]:
                    errors.append(f"unexpected GFX {entry['gfx']} for {pos} at {stage}")
                for field, limit in (("u", 255), ("v", 255), ("clut", 65535), ("tpage", 65535)):
                    if field in entry:
                        value = entry[field]
                        if type(value) is not int or not 0 <= value <= limit:
                            errors.append(f"entry {i}: {field} must be an integer from 0 to {limit}")
                        elif field in draw_metadata.get(pos, {}) and draw_metadata[pos][field] != value:
                            errors.append(f"{field} changed across frames for {pos}")
                        else:
                            draw_metadata.setdefault(pos, {}).setdefault(field, value)
                continue
        elif (pos, stage) in found:
            errors.append(f"duplicate observation for {pos} at {stage}")
            continue
        elif stage == "draw":
            draw_paths.setdefault(pos, set()).add(entry.get("path", "unspecified"))
            draw_count[pos] = draw_count.get(pos, 0) + 1
        found[(pos, stage)] = entry["gfx"]
        if stage == "draw":
            metadata = {}
            for field, limit in (("u", 255), ("v", 255), ("clut", 65535), ("tpage", 65535)):
                if field in entry:
                    value = entry[field]
                    if type(value) is not int or not 0 <= value <= limit:
                        errors.append(f"entry {i}: {field} must be an integer from 0 to {limit}")
                    else:
                        metadata[field] = value
            draw_metadata[pos] = metadata
        if entry["gfx"] not in TARGETS[pos]:
            errors.append(f"unexpected GFX {entry['gfx']} for {pos} at {stage}")
    # A full renderer pass with face 0 must terminate, even if a later
    # invocation of the same tile/path drew successfully.
    if require_full_trace:
        for (context, generation), entry_index in pending_visit_outcomes.items():
            pos, frame, path = context
            errors.append(
                f"full trace nonempty visit without draw or skip for {pos}"
                f" in frame {frame}, path {path}, invocation {generation}"
                f" (entry {entry_index})"
            )
    # A visit and its subsequent draw/backface rejection sample the same
    # tile face. In the full trace they must agree within that frame/path.
    context_matches = {pos: {"draw": 0, "backface": 0} for pos in TARGETS}
    for context, visited in visit_gfx_by_context.items():
        pos, frame, path = context
        if len(visited) > 1:
            errors.append(
                f"GFX changed among visits for {pos} in frame {frame}, path {path}"
            )
        for label, samples in (("draw", draw_gfx_by_context),
                               ("backface", backface_gfx_by_context)):
            if context not in samples:
                continue
            context_matches[pos][label] += 1
            if samples[context] != visited:
                errors.append(
                    f"GFX mismatch between visit and {label} for {pos}"
                    f" in frame {frame}, path {path}:"
                    f" visited {sorted(visited)}, observed {sorted(samples[context])}"
                )
    rows = []
    for pos, (prs, dat) in TARGETS.items():
        after = found.get((pos, "post_load"))
        drawn = found.get((pos, "draw"))
        if after is None:
            errors.append(f"missing post_load observation for {pos}")
        if drawn is None:
            errors.append(f"missing draw observation for {pos}")
        rows.append({
            "z": pos[0], "x": pos[1], "face": pos[2],
            "prs_gfx": prs, "dat_gfx": dat,
            "post_load_gfx": after, "draw_gfx": drawn,
            "draw_metadata": draw_metadata.get(pos, {}),
            "draw_observation_count": draw_count.get(pos, 0),
            "draw_paths": sorted(draw_paths.get(pos, set())),
            "skip_observation_count": skip_count.get(pos, 0),
            "skip_reasons": sorted(skip_reasons.get(pos, set())),
            "visit_observation_count": visit_count.get(pos, 0),
            "visit_paths": sorted(visit_paths.get(pos, set())),
            "observed_face_counts": sorted(observed_face_counts.get(pos, set())),
            "visit_draw_contexts_checked": context_matches[pos]["draw"],
            "visit_backface_contexts_checked": context_matches[pos]["backface"],
            "draw_status": ("submitted" if drawn is not None else
                            "skipped_in_observed_passes" if skip_count.get(pos, 0) else
                            "no_faces_in_observed_passes" if observed_face_counts.get(pos) == {0} else
                            "visited_without_submission" if visit_count.get(pos, 0) else
                            "no_renderer_observation"),
            "post_load_variant": "PRS" if after == prs else "DAT" if after == dat else None,
            "draw_variant": "PRS" if drawn == prs else "DAT" if drawn == dat else None,
        })
        if after is not None and drawn is not None and after != drawn:
            errors.append(f"GFX changed between loading and drawing for {pos}")
    post_variants = [row["post_load_variant"] for row in rows]
    draw_variants = [row["draw_variant"] for row in rows]
    def combined_variant(variants):
        if any(value is None for value in variants):
            return "incomplete_or_unknown"
        return variants[0] if len(set(variants)) == 1 else "mixed"
    return {"observations": rows, "errors": errors,
            "post_load_overall_variant": combined_variant(post_variants),
            "draw_overall_variant": combined_variant(draw_variants),
            "warning": "Visit proves renderer entry, skip a face rejection, draw an AddPrim submission; none guarantees visible pixels. Missing draw events still fail validation."}



def parse_trace_text(text):
    """Accept a JSON array or a JSON Lines stream of observation objects."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        entries = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON Lines entry at line {line_number}: {exc.msg}") from exc
        if not entries:
            raise ValueError("trace contains no observations")
        data = entries
    if isinstance(data, dict):
        data = [data]  # A single JSONL observation is also valid JSON.
    if not isinstance(data, list):
        raise ValueError("trace must be a JSON array or JSON Lines objects")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="JSON array of captured runtime observations")
    parser.add_argument("--require-uniform-variant", action="store_true",
                        help="fail if the two target faces are not uniformly PRS or DAT at both stages")
    parser.add_argument("--require-full-trace", action="store_true",
                        help="require each framed draw/skip to have a preceding same-frame/path nonempty visit")
    args = parser.parse_args()
    try:
        result = evaluate_trace(
            parse_trace_text(args.trace.read_text(encoding="utf-8")),
            require_full_trace=args.require_full_trace,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    uniform = (result["post_load_overall_variant"] in ("PRS", "DAT") and
               result["post_load_overall_variant"] == result["draw_overall_variant"])
    return int(bool(result["errors"]) or (args.require_uniform_variant and not uniform))


if __name__ == "__main__":
    raise SystemExit(main())

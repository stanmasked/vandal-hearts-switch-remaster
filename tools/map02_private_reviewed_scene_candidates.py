#!/usr/bin/env python3
"""Owner-private review shortlist from two complete BK2 screenshot capture sets.

Source BK2 -> canonical private plan -> two Lua logs -> PNG CRC/IDAT/SHA ->
decoded RGB two-capture comparison is checked BEFORE human annotations are
read or report output is created. Human category labels and matching screen
pixels are never evidence that MAP02 gameplay or a real emulator was run.

No owner file contents, raw frame indices, screenshots, filenames or labels
are printed to stdout or sent to GitHub. Review-group numbers in the JSON
are private and should not be published either.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from io import StringIO
import json
from pathlib import Path

from tools.map02_private_dual_capture_rgb_repeatability import (
    verify as verify_dual, ROLES,
)
from tools.map02_private_human_review_ledger import (
    checked_positions, evaluate as audit_manual_labels, HEADER, LABELS,
    MAX_REVIEW_BYTES, write_private_new,
)
from tools.validate_map02_private_replay_markers import _read_regular
from tools.verify_map02_private_neutral_capture_chain import parse_plan, PLAN_LIMIT
from tools.verify_map02_private_visual_candidates import read_png_private
from tools.map02_private_png_visual_diff import decode_private_rgb8

SCHEMA = "vh.map02.private-reviewed-scene-candidates.v3"
STATES = frozenset((
    "requires_pixel_replay",
    "awaiting_manual_classification",
    "human_labels_disagree",
    "requires_game_state_witness",
    "no_observed_intra_group_pixel_change",
    "not_candidate_in_selected_frames",
))


def _intra_group_visual_changes(plan: Path, image_root: Path) -> dict[int, bool]:
    """Validate real in-group decoded RGB changes, not just human labels.

    The caller first audits the source BK2, plan, marker log and all images,
    including pixel-repeatability across supplied sets. We reject size drift
    within the same before/middle/after group.
    """
    _, rows = parse_plan(plan)
    grouped: dict[int, dict[str, tuple[int, int, bytes]]] = {}
    for group, role, input_index, _ in rows:
        filename = "vh_review_w%02d_%s_counter_%07d.png" % (
            group, role, input_index + 1)
        group_images = grouped.setdefault(group, {})
        if role in group_images:
            raise ValueError("duplicate frame role in visual-diff audit")
        group_images[role] = decode_private_rgb8(
            read_png_private(image_root, filename))
    result = {}
    for group, images in grouped.items():
        if set(images) != set(ROLES):
            raise ValueError("missing before/middle/after visual frames")
        b, m, a = (images[role] for role in ROLES)
        if b[:2] != m[:2] or b[:2] != a[:2]:
            raise ValueError("within-group frame dimensions disagree")
        result[group] = b[2] != m[2] and b[2] != a[2]
    return result


def shortlist(positions: list[tuple[int, str]], proof: dict,
              annotation_csv: Path, visual_changes: dict[int, bool], *,
              source_plan_sha256: str) -> dict:
    if (type(source_plan_sha256) is not str or len(source_plan_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in source_plan_sha256)):
        raise ValueError("invalid canonical source plan SHA-256")
    # The upstream annotation CSV checker enforces exact header, roles,
    # bounded labels, full coverage and absence of duplicate/foreign rows.
    annotation_audit = audit_manual_labels(positions, annotation_csv)
    if (annotation_audit["map02_scene_authenticated"] is not False
            or annotation_audit["complete_screenshot_position_coverage"] is not True):
        raise ValueError("human review report overclaims scene authentication")

    reader = csv.reader(
        StringIO(_read_regular(annotation_csv, MAX_REVIEW_BYTES)), strict=True)
    if tuple(next(reader, ())) != HEADER:
        raise ValueError("owner annotation header changed during audit")
    raw_labels = {}
    for row in reader:
        if len(row) != 4 or not row[0].isdecimal():
            raise ValueError("malformed owner annotation row")
        key = (int(row[0]), row[1])
        if (key in raw_labels or key not in positions
                or row[2] not in LABELS or row[3] not in LABELS):
            raise ValueError("owner annotation changed during audit")
        raw_labels[key] = (row[2], row[3])
    if set(raw_labels) != set(positions):
        raise ValueError("annotation coverage changed during audit")

    rows = proof.get("matches_and_differences_by_review_position")
    if (not isinstance(rows, list) or len(rows) != len(positions)
            or proof.get("map02_start_frame_identified") is not False
            or proof.get("two_actual_octoshock_runs_authenticated") is not False
            or proof.get("independent_replay_executions_authenticated") is not False
            or proof.get("source_native_gpu_vram_verified") is not False):
        raise ValueError("source RGB witness overclaims or is incomplete")
    pixel_matches = {}
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("malformed cross-capture RGB row")
        key = (item.get("review_group"), item.get("frame_role"))
        same = item.get("same_decoded_rgb_pixels")
        if (key not in positions or key in pixel_matches or type(same) is not bool):
            raise ValueError("cross-capture RGB positions do not match source plan")
        pixel_matches[key] = same
    if set(pixel_matches) != set(positions):
        raise ValueError("missing decoded image comparisons")

    groups = sorted({g for g, _ in positions})
    if (set(visual_changes) != set(groups)
            or any(type(value) is not bool for value in visual_changes.values())):
        raise ValueError("incomplete source-validated within-group pixel evidence")
    details = []
    for group in groups:
        labels = [raw_labels[group, role] for role in ROLES]
        exact = [pixel_matches[group, role] for role in ROLES]
        has_unreviewed_labels = any(
            label in ("unreviewed", "uncertain")
            for pair in labels for label in pair
        )
        if not all(exact):
            state = "requires_pixel_replay"
        elif has_unreviewed_labels:
            state = "awaiting_manual_classification"
        elif any(a != b for a, b in labels):
            state = "human_labels_disagree"
        elif (labels[0][0] != "tactical_board"
              and labels[1][0] == "tactical_board"
              and labels[2][0] == "tactical_board"):
            state = ("requires_game_state_witness" if visual_changes[group]
                     else "no_observed_intra_group_pixel_change")
        else:
            state = "not_candidate_in_selected_frames"
        if state not in STATES:
            raise ValueError("unrecognized human-review state")
        details.append({
            "review_group": group,
            "state": state,
            "all_three_positions_exact_rgb_equal_across_supplied_sets": all(exact),
            "manual_transition_pattern": (
                not has_unreviewed_labels
                and labels[0][0] != "tactical_board"
                and labels[1][0] == labels[2][0] == "tactical_board"
                and all(a == b for a, b in labels)
            ),
            "intra_group_visual_change_confirmed": visual_changes[group],
            "actual_map02_scene_authenticated": False,
        })

    return {
        "schema": SCHEMA,
        "source_plan_sha256": source_plan_sha256,
        "private_review_group_count": len(groups),
        "fully_reviewed_position_pairs": annotation_audit["fully_categorized_position_pairs"],
        "matching_human_label_pairs": annotation_audit["matching_human_label_pairs"],
        "conflicting_human_label_pairs": annotation_audit["conflicting_human_label_pairs"],
        "review_groups_requiring_game_state_witness":
            sum(item["state"] == "requires_game_state_witness" for item in details),
        "review_groups_with_pixel_disagreements":
            sum(item["state"] == "requires_pixel_replay" for item in details),
        "review_groups_awaiting_manual_classification":
            sum(item["state"] == "awaiting_manual_classification" for item in details),
        "review_groups_with_label_conflicts":
            sum(item["state"] == "human_labels_disagree" for item in details),
        "review_groups_without_intra_group_pixel_change":
            sum(item["state"] == "no_observed_intra_group_pixel_change"
                for item in details),
        "groups": details,
        "source_capture_chains_revalidated": True,
        "two_capture_sets_independently_authenticated": False,
        "independent_human_reviewers_authenticated": False,
        "input_to_video_alignment_verified": False,
        "original_ps1_game_authenticated": False,
        "actual_map02_start_authenticated": False,
        "game_state_or_gpu_vram_witness_available": False,
        "private_bk2_images_labels_or_frame_coordinates_uploaded": False,
    }


def verify(
    movie: Path, plan: Path, log1: Path, images1: Path,
    log2: Path, images2: Path, annotations: Path, *,
    minimum: int = 180, maximum: int = 1800,
    after: int = 1663, before: int = 933949,
) -> dict:
    plan_snapshot = _read_regular(plan, PLAN_LIMIT)
    try:
        plan_bytes = plan_snapshot.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("private capture plan is not ASCII") from exc
    plan_digest = hashlib.sha256(plan_bytes).hexdigest()
    source = verify_dual(
        movie, plan, log1, images1, log2, images2,
        minimum=minimum, maximum=maximum, after=after, before=before,
        pixel_threshold=0,
    )
    positions = checked_positions(plan, source)
    visual_changes = _intra_group_visual_changes(plan, images1)
    if _read_regular(plan, PLAN_LIMIT) != plan_snapshot:
        raise ValueError("private capture plan changed during audit")
    return shortlist(
        positions, source, annotations, visual_changes,
        source_plan_sha256=plan_digest,
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_bk2", type=Path)
    p.add_argument("private_plan", type=Path)
    p.add_argument("run_one_log", type=Path)
    p.add_argument("run_one_png_directory", type=Path)
    p.add_argument("run_two_log", type=Path)
    p.add_argument("run_two_png_directory", type=Path)
    p.add_argument("--private-annotations", required=True, type=Path)
    p.add_argument("--private-report-output", required=True, type=Path)
    p.add_argument("--min-neutral-frames", type=int, default=180)
    p.add_argument("--max-neutral-frames", type=int, default=1800)
    p.add_argument("--after-input-frame", type=int, default=1663)
    p.add_argument("--before-input-frame", type=int, default=933949)
    a = p.parse_args()
    try:
        report = verify(
            a.private_bk2, a.private_plan,
            a.run_one_log, a.run_one_png_directory,
            a.run_two_log, a.run_two_png_directory,
            a.private_annotations,
            minimum=a.min_neutral_frames, maximum=a.max_neutral_frames,
            after=a.after_input_frame, before=a.before_input_frame,
        )
        write_private_new(
            a.private_report_output,
            json.dumps(report, sort_keys=True, indent=2) + "\n", ".json",
        )
    except (OSError, ValueError, TypeError, UnicodeError, csv.Error):
        p.error("private human-reviewed scene shortlist unavailable")
    print("VH_MAP02_PRIVATE_SHORTLIST_READY groups=%d "
          "scene_authenticated=0 private_uploaded=0"
          % report["private_review_group_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

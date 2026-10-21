#!/usr/bin/env python3
"""Owner-only MAP02 screenshot observation ledger (not PS1 scene proof).

PREPARE makes a private CSV of manual labels for both supplied screenshot
runs. AUDIT first rechecks BOTH source BK2->capture plan->Lua log->PNG/RGB
bundles, then checks all filled labels against the canonical frame roles.
No image, private frame index, note, filename or annotation CSV is uploaded
or printed. Matching manual observations do not authenticate MAP02.
"""
from __future__ import annotations

import argparse
import csv
from io import StringIO
import json
import os
from pathlib import Path
import stat

from tools.map02_private_dual_capture_rgb_repeatability import verify as verify_dual, ROLES
from tools.verify_map02_private_neutral_capture_chain import parse_plan
from tools.validate_map02_private_replay_markers import _read_regular

SCHEMA = "vh.map02.private-human-review-ledger.v1"
HEADER = ("review_group", "frame_role", "run_1_label", "run_2_label")
LABELS = frozenset((
    "unreviewed", "uncertain", "menu", "dialogue", "travel",
    "tactical_board", "transition", "other",
))
MAX_REVIEW_BYTES = 8192
MAX_GROUPS = 10


def safe_private_new_path(path: Path, expected_extension: str) -> Path:
    p = Path(path)
    if not p.is_absolute() or p.suffix.lower() != expected_extension:
        raise ValueError("private output needs an absolute path with requested extension")
    if p.exists() or p.is_symlink():
        raise ValueError("private output already exists or is a symlink")
    parent = p.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("private output directory missing or directly symlinked")
    # Canonical system ancestors such as macOS /var -> /private/var are
    # allowed, but both lexical and resolved ancestors must be outside Git.
    canonical = parent.resolve(strict=True)
    if any(
        x.name == ".git" or (x / ".git").exists()
        for root in (parent, canonical) for x in (root, *root.parents)
    ):
        raise ValueError("private output inside Git checkout forbidden")
    return p


def write_private_new(path: Path, text: str, ext: str) -> None:
    p = safe_private_new_path(path, ext)
    if len(text.encode("utf-8")) > MAX_REVIEW_BYTES:
        raise ValueError("private report too large")
    flags = os.O_WRONLY | os.O_EXCL | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        if not stat.S_ISREG(p.stat().st_mode):
            raise ValueError("private report output is not a regular file")
    except BaseException:
        p.unlink(missing_ok=True)
        raise


def checked_positions(plan: Path, proof: dict) -> list[tuple[int, str]]:
    if (proof.get("both_source_bk2_capture_chains_passed_integrity_audit") is not True
            or proof.get("no_local_capture_inode_reused") is not True
            or proof.get("map02_start_frame_identified") is not False
            or proof.get("independent_replay_executions_authenticated") is not False):
        raise ValueError("source capture audit did not pass conservative provenance")
    _, frames = parse_plan(plan)
    if (len(frames) != proof.get("compared_screenshot_positions")
            or not 3 <= len(frames) <= MAX_GROUPS * 3):
        raise ValueError("capture plan and source audit counts disagree")
    by_group = {}
    for group, role, frame, held in frames:
        if (type(group) is not int or not 1 <= group <= MAX_GROUPS
                or role not in ROLES or type(frame) is not int or frame < 0
                or held not in ("neutral", "held")):
            raise ValueError("malformed capture plan position")
        roles = by_group.setdefault(group, set())
        if role in roles:
            raise ValueError("duplicate frame-role position")
        roles.add(role)
    if any(set(ROLES) != roles for roles in by_group.values()):
        raise ValueError("capture plan lacks a complete three-role group")
    return [(group, role) for group in sorted(by_group) for role in ROLES]


def _source_positions(
    movie: Path, plan: Path, log1: Path, images1: Path,
    log2: Path, images2: Path, *, minimum: int, maximum: int,
    after: int, before: int,
) -> list[tuple[int, str]]:
    result = verify_dual(
        movie, plan, log1, images1, log2, images2,
        minimum=minimum, maximum=maximum, after=after, before=before,
        pixel_threshold=0,
    )
    return checked_positions(plan, result)


def prepare(positions: list[tuple[int, str]], destination: Path) -> dict:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(HEADER)
    for group, role in positions:
        writer.writerow((group, role, "unreviewed", "unreviewed"))
    write_private_new(destination, stream.getvalue(), ".csv")
    return {"schema": SCHEMA, "review_positions_prepared": len(positions),
            "manual_observations_entered": False,
            "map02_scene_authenticated": False, "private_review_uploaded": False}


def evaluate(positions: list[tuple[int, str]], label_file: Path) -> dict:
    file_path = Path(label_file)
    if not file_path.is_absolute():
        raise ValueError("annotation CSV must be owner-local absolute path")
    raw = _read_regular(file_path, MAX_REVIEW_BYTES)
    reader = csv.reader(StringIO(raw), strict=True)
    if tuple(next(reader, ())) != HEADER:
        raise ValueError("private observation CSV header invalid")
    expected = set(positions)
    found = {}
    for row in reader:
        if len(row) != len(HEADER):
            raise ValueError("review record must have four fields")
        number, role, first, second = row
        if not number.isdecimal() or str(int(number)) != number:
            raise ValueError("invalid review group identifier")
        key = (int(number), role)
        if key not in expected or key in found:
            raise ValueError("unknown or duplicate review position")
        if first not in LABELS or second not in LABELS:
            raise ValueError("invalid manually assigned scene category")
        found[key] = (first, second)
    if set(found) != expected:
        raise ValueError("incomplete private screenshot annotation table")
    reviewed = 0
    matches = 0
    conflicts = 0
    tactical_pairs = 0
    uncertain = 0
    for labels in found.values():
        if "unreviewed" in labels:
            uncertain += 1
        elif "uncertain" in labels:
            uncertain += 1
        else:
            reviewed += 1
            if labels[0] == labels[1]:
                matches += 1
                tactical_pairs += int(labels[0] == "tactical_board")
            else:
                conflicts += 1
    return {
        "schema": SCHEMA,
        "capture_positions_from_revalidated_source": len(positions),
        "fully_categorized_position_pairs": reviewed,
        "uncertain_or_unreviewed_position_pairs": uncertain,
        "matching_human_label_pairs": matches,
        "conflicting_human_label_pairs": conflicts,
        "manual_tactical_board_label_pairs": tactical_pairs,
        "complete_screenshot_position_coverage": True,
        "source_bk2_dual_capture_chain_rechecked": True,
        "labels_supplied_by_human_not_by_game_state": True,
        "independent_human_reviewers_authenticated": False,
        "two_real_ps1_emulator_runs_authenticated": False,
        "actual_ps1_game_disc_authenticated": False,
        "input_to_video_frame_offset_authenticated": False,
        "map02_scene_authenticated": False,
        "gpu_vram_parity_authenticated": False,
        "private_observations_uploaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "audit"))
    parser.add_argument("private_bk2", type=Path)
    parser.add_argument("private_plan", type=Path)
    parser.add_argument("run_one_log", type=Path)
    parser.add_argument("run_one_png_directory", type=Path)
    parser.add_argument("run_two_log", type=Path)
    parser.add_argument("run_two_png_directory", type=Path)
    parser.add_argument("--private-annotations", required=True, type=Path)
    parser.add_argument("--private-report-output", type=Path)
    parser.add_argument("--min-neutral-frames", default=180, type=int)
    parser.add_argument("--max-neutral-frames", default=1800, type=int)
    parser.add_argument("--after-input-frame", default=1663, type=int)
    parser.add_argument("--before-input-frame", default=933949, type=int)
    a = parser.parse_args()
    try:
        if ((a.mode == "audit") != (a.private_report_output is not None)):
            raise ValueError("audit mode requires a report output, prepare must omit it")
        positions = _source_positions(
            a.private_bk2, a.private_plan,
            a.run_one_log, a.run_one_png_directory,
            a.run_two_log, a.run_two_png_directory,
            minimum=a.min_neutral_frames, maximum=a.max_neutral_frames,
            after=a.after_input_frame, before=a.before_input_frame,
        )
        if a.mode == "prepare":
            result = prepare(positions, a.private_annotations)
        else:
            result = evaluate(positions, a.private_annotations)
            write_private_new(
                a.private_report_output,
                json.dumps(result, sort_keys=True, indent=2) + "\n", ".json",
            )
    except (OSError, ValueError, TypeError, UnicodeError, csv.Error):
        parser.error("owner-private manual frame review verification unavailable")
    print(
        "VH_MAP02_HUMAN_REVIEW_LEDGER_OK mode=%s positions=%d "
        "game_auth=0 scene_auth=0 private_upload=0"
        % (a.mode, len(positions))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

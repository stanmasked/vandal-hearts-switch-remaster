#!/usr/bin/env python3
"""Build an OWNER-LOCAL six-panel RGB contact sheet for human BK2 review.

First independently verify BOTH full owner-private BK2 -> plan -> Lua log ->
PNG bundles using PR #429's fail-closed source and RGB audit. Render
before/middle/after from two supplied captures next to each other. This is
a PRIVATE screenshot-derived artifact, not a scene classifier or public CI
artifact. The original BK2, PNGs, indices and resulting image MUST stay off
GitHub.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat

from PIL import Image, ImageDraw, UnidentifiedImageError

from tools.map02_private_dual_capture_rgb_repeatability import (
    verify as verify_dual, ROLES,
)
from tools.verify_map02_private_neutral_capture_chain import parse_plan
from tools.verify_map02_private_visual_candidates import read_png_private
from tools.map02_private_png_visual_diff import decode_private_rgb8

SCHEMA = "vh.map02.private-owner-rgb-contact-sheet.v1"
MAX_GROUPS = 10
CELL_WIDTH = 304
CELL_HEIGHT = 194
CELL_GAP = 12
GROUP_HEADER = 34
OUTER = 16
TOP_HEADER = 82
MAX_SHEET_PIXELS = 6_000_000


def _output_path_safely_uncreated(path: Path) -> Path:
    destination = Path(path)
    if not destination.is_absolute() or destination.suffix.lower() != ".png":
        raise ValueError("contact sheet needs an absolute private PNG output path")
    if destination.exists() or destination.is_symlink():
        raise ValueError("refusing to overwrite or follow an existing private output")
    parent = destination.parent
    if (not parent.is_dir() or parent.is_symlink()
            or parent.resolve(strict=True) != parent):
        raise ValueError("private output directory must be real and not symlinked")
    if any(
        p.name == ".git" or (p / ".git").exists()
        for p in (parent, *parent.parents)
    ):
        raise ValueError("private screenshots cannot be written inside a Git checkout")
    return destination


def _checked_groups(plan: Path) -> list[tuple[int, dict]]:
    _, frames = parse_plan(plan)
    group_map: dict[int, dict] = {}
    for group, role, input_index, _ in frames:
        if (type(group) is not int or not 1 <= group <= MAX_GROUPS
                or role not in ROLES or type(input_index) is not int
                or input_index < 0):
            raise ValueError("invalid capture plan for visual layout")
        parts = group_map.setdefault(group, {})
        if role in parts:
            raise ValueError("repeated visual role within capture group")
        parts[role] = input_index
    if (not 1 <= len(group_map) <= MAX_GROUPS
            or any(set(group) != set(ROLES) for group in group_map.values())
            or len(frames) != len(group_map) * len(ROLES)):
        raise ValueError("incomplete private before/middle/after captures")
    return sorted(group_map.items())


def _paste_frame(
    canvas: Image.Image, root: Path, group: int, role: str, input_index: int,
    x: int, y: int, *, run_number: int, pixels_equal: bool,
) -> None:
    filename = "vh_review_w%02d_%s_counter_%07d.png" % (
        group, role, input_index + 1,
    )
    # The preceding exact-source dual verifier already checked the same
    # screenshot against the BK2 and required CRC/IDAT/inode safety.
    rgb = decode_private_rgb8(read_png_private(root, filename))
    width, height, samples = rgb
    if width <= 0 or height <= 0:
        raise ValueError("empty captured frame")
    with Image.frombytes("RGB", (width, height), samples) as decoded:
        decoded.thumbnail((CELL_WIDTH - 18, CELL_HEIGHT - 66),
                          Image.Resampling.LANCZOS)
        left = x + (CELL_WIDTH - decoded.width) // 2
        top = y + 32 + (CELL_HEIGHT - 64 - decoded.height) // 2
        canvas.paste(decoded, (left, top))

    drawer = ImageDraw.Draw(canvas)
    drawer.rectangle((x, y, x + CELL_WIDTH - 1, y + CELL_HEIGHT - 1),
                     outline=(100, 110, 130), width=2)
    status = "MATCH" if pixels_equal else "DIFF"
    drawer.text(
        (x + 8, y + 8),
        "RUN %d / %s / %s" % (run_number, role.upper(), status),
        fill=(237, 238, 243),
    )
    # The exact movie-input index is printed ONLY inside the local
    # restrictive PNG image, never to CI logs or the terminal.
    drawer.text(
        (x + 10, y + CELL_HEIGHT - 16),
        "input %d / display sync UNVERIFIED" % input_index,
        fill=(190, 197, 211),
    )


def render(
    private_bk2: Path, private_plan: Path,
    log_one: Path, root_one: Path,
    log_two: Path, root_two: Path,
    output: Path, *, minimum: int = 180, maximum: int = 1800,
    after: int = 1663, before: int = 933949,
) -> dict:
    # Refuse obviously unsafe destination BEFORE processing potentially
    # expensive owner-private source data. Never write a partial sheet.
    destination = _output_path_safely_uncreated(output)
    proof = verify_dual(
        private_bk2, private_plan, log_one, root_one, log_two, root_two,
        minimum=minimum, maximum=maximum, after=after, before=before,
        pixel_threshold=0,
    )
    if (proof.get("both_source_bk2_capture_chains_passed_integrity_audit") is not True
            or proof.get("no_local_capture_inode_reused") is not True
            or proof.get("source_native_gpu_vram_verified") is not False
            or proof.get("map02_start_frame_identified") is not False
            or proof.get("independent_replay_executions_authenticated") is not False):
        raise ValueError("unverifiable private source or overclaimed provenance")
    groups = _checked_groups(private_plan)
    if proof.get("compared_screenshot_positions") != 3 * len(groups):
        raise ValueError("full source audit and capture groups do not match")
    rows = proof.get("matches_and_differences_by_review_position")
    if not isinstance(rows, list) or len(rows) != 3 * len(groups):
        raise ValueError("incomplete two-bundle RGB comparison")
    matches = {}
    for item in rows:
        key = (item["review_group"], item["frame_role"])
        if key in matches or type(item["same_decoded_rgb_pixels"]) is not bool:
            raise ValueError("duplicate or invalid RGB comparison evidence")
        matches[key] = item["same_decoded_rgb_pixels"]
    if set(matches) != {
        (group, role) for group, _ in groups for role in ROLES
    }:
        raise ValueError("misaligned private comparison and capture plan")

    columns = len(ROLES)
    canvas_width = 2 * OUTER + columns * CELL_WIDTH + (columns - 1) * CELL_GAP
    group_height = GROUP_HEADER + 2 * CELL_HEIGHT + CELL_GAP + 2 * CELL_GAP
    canvas_height = TOP_HEADER + len(groups) * group_height + OUTER
    if canvas_width * canvas_height > MAX_SHEET_PIXELS:
        raise ValueError("contact sheet exceeds bounded pixel capacity")
    canvas = Image.new("RGB", (canvas_width, canvas_height), (24, 27, 36))
    drawer = ImageDraw.Draw(canvas)
    drawer.rectangle((0, 0, canvas_width - 1, TOP_HEADER - 1),
                     fill=(55, 21, 22))
    drawer.text((OUTER, 13),
                "OWNER-PRIVATE / DO NOT UPLOAD / UNVERIFIED PS1 DISPLAY",
                fill=(255, 228, 215))
    drawer.text((OUTER, 32),
                "UNVERIFIED - NOT MAP02 PROOF / NOT TWO EMULATOR ATTESTATIONS",
                fill=(255, 217, 177))
    drawer.text((OUTER, 54),
                "Pixel matching may be UI, menu, animation or wrong frame",
                fill=(228, 216, 216))
    for group_position, (group, indices) in enumerate(groups):
        y = TOP_HEADER + group_position * group_height
        drawer.text(
            (OUTER, y + 10),
            "REVIEW GROUP %02d / before - neutral middle - after / UNVERIFIED" % group,
            fill=(239, 241, 246),
        )
        for column, role in enumerate(ROLES):
            x = OUTER + column * (CELL_WIDTH + CELL_GAP)
            for run_number, root in ((1, root_one), (2, root_two)):
                cy = y + GROUP_HEADER + (run_number - 1) * (CELL_HEIGHT + CELL_GAP)
                _paste_frame(canvas, root, group, role, indices[role], x, cy,
                             run_number=run_number,
                             pixels_equal=matches[(group, role)])

    # POSIX-style exclusive owner-only output; no overwriting or network.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as target:
            canvas.save(target, format="PNG", optimize=True)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    if not stat.S_ISREG(destination.stat().st_mode):
        raise ValueError("private screenshot contact sheet must be regular")
    return {
        "schema": SCHEMA,
        "private_review_groups": len(groups),
        "paired_screenshot_positions": len(matches),
        "decoded_rgb_mismatches": sum(not value for value in matches.values()),
        "both_owner_supplied_capture_chains_revalidated": True,
        "private_owner_only_png_created": True,
        "actual_ps1_emulation_authenticated": False,
        "two_independent_emulator_processes_authenticated": False,
        "input_to_video_offset_verified": False,
        "map02_scene_identified": False,
        "ps1_gpu_vram_parity_verified": False,
        "private_media_uploaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_private_plan", type=Path)
    parser.add_argument("run_one_private_log", type=Path)
    parser.add_argument("run_one_png_directory", type=Path)
    parser.add_argument("run_two_private_log", type=Path)
    parser.add_argument("run_two_png_directory", type=Path)
    parser.add_argument("--owner-private-output", required=True, type=Path)
    parser.add_argument("--min-neutral-frames", type=int, default=180)
    parser.add_argument("--max-neutral-frames", type=int, default=1800)
    parser.add_argument("--after-input-frame", type=int, default=1663)
    parser.add_argument("--before-input-frame", type=int, default=933949)
    args = parser.parse_args()
    try:
        result = render(
            args.owner_private_bk2, args.owner_private_plan,
            args.run_one_private_log, args.run_one_png_directory,
            args.run_two_private_log, args.run_two_png_directory,
            args.owner_private_output,
            minimum=args.min_neutral_frames, maximum=args.max_neutral_frames,
            after=args.after_input_frame, before=args.before_input_frame,
        )
    except (OSError, ValueError, TypeError, UnidentifiedImageError):
        parser.error("owner-private source-checked screenshot contact sheet unavailable")
    print(
        "VH_MAP02_PRIVATE_CONTACT_SHEET_READY groups=%d comparisons=%d "
        "rgb_mismatches=%d ps1_emulated=0 map02_identified=0"
        % (result["private_review_groups"], result["paired_screenshot_positions"],
           result["decoded_rgb_mismatches"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

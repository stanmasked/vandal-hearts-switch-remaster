#!/usr/bin/env python3
"""Owner-only read-only check of ONE saved MAP02 EmuHawk capture.

No emulator is started, no screenshot/ROM/BK2 leaves the workstation and no
two-run/cold-boot/real MAP02 assertion is made. All receipts are editable;
the audit validates structural consistency, not cryptographic provenance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.map02_private_bizhawk_poweron_launch import AUTO_WITNESS_NAME
from tools.map02_private_core_witness_audit import read_witness
from tools.map02_private_disc_movie_preflight import _resolve_private_file
from tools.map02_private_process_witness_binding import (
    NAME as PROCESS_RECEIPT_NAME, read_started_process,
)
from tools.map02_private_two_capture_audit import _private_root
from tools.map02_private_two_replay_runner import PLAN_NAME, RUN_NAMES
from tools.verify_map02_private_neutral_capture_chain import parse_plan, verify

SCHEMA = "vh.map02.owner-one-capture-offline-reaudit.v1"


def review_first_capture(private_movie: Path, private_workspace: Path,
                         manual_core_witness: Path | None = None) -> dict:
    """Re-read source BK2, plan, log, PNG and in-process PSX identity locally.

    A valid report confirms ONLY that the supplied owner-local *files* have
    the expected structure. It never infers an authentic original game frame.
    """
    root = _private_root(private_workspace)
    first = _private_root(root / RUN_NAMES[0])
    if first.parent != root:
        raise ValueError("private first-capture folder outside its workspace")
    second = root / RUN_NAMES[1]
    if second.exists() or second.is_symlink():
        raise ValueError("offline one-run auditor refuses a two-run workspace")
    plan = root / PLAN_NAME
    if (plan.is_symlink() or not plan.is_file()
            or plan.resolve(strict=True).parent != root):
        raise ValueError("private plan must be a local regular workspace file")
    movie = _resolve_private_file(private_movie)
    _, rows = parse_plan(plan)
    if not rows or len(rows) > 30:
        raise ValueError("private first-capture plan has no valid snapshots")

    chain = verify(movie, plan, first / "vh_private_capture.log", first)
    count = chain.get("screenshot_count")
    if (type(count) is not int or count != len(rows)
            or chain.get("private_plan_rebuilt_from_direct_bk2") is not True
            or chain.get("capture_logs_match_each_planned_input_and_counter") is not True
            or chain.get("owner_launcher_reports_successful_process_exit") is not True
            or chain.get("owner_log_reports_psx_core_fallback_disabled") is not True
            or chain.get("all_png_crc_zlib_scanlines_pass") is not True):
        raise ValueError("owner-private one-run capture chain incomplete")

    is_auto = manual_core_witness is None
    marker = chain.get("owner_log_reports_auto_core_witness_before_first_png")
    if type(marker) is not bool or marker is not is_auto:
        raise ValueError("one-run core witness mode differs from captured Lua log")

    witness = (first / AUTO_WITNESS_NAME if is_auto
               else _resolve_private_file(manual_core_witness))
    started = read_started_process(first / PROCESS_RECEIPT_NAME)
    observed = read_witness(witness)
    if observed[:2] != started:
        raise ValueError("one-run core identity does not match launch PID/birth time")

    first_counter = rows[0][2] + 1
    if is_auto and observed[2] > first_counter:
        raise ValueError("automatic core witness frame later than first PNG")

    return {
        "schema": SCHEMA,
        "owner_private_capture_attempts_reaudited": 1,
        "capture_screenshot_count": count,
        "private_bk2_plan_lua_and_png_chain_passed": True,
        "owner_log_reports_core_fallback_blocked": True,
        "owner_log_reports_automatic_witness_before_first_png": is_auto,
        "private_octoshock_core_witness_matches_launched_pid_and_birth": True,
        "auto_core_frame_not_later_than_first_png": is_auto,
        "two_run_repeatability_audited": False,
        "original_ps1_disc_or_bios_authenticated": False,
        "bk2_controller_delivery_authenticated": False,
        "independent_cold_boot_authenticated": False,
        "authentic_map02_scene_identified": False,
        "switch_renderer_parity_verified": False,
        "private_paths_ids_hashes_or_pixels_published": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_private_one_run_workspace", type=Path)
    parser.add_argument("--manual-core-witness", type=Path,
                        help="Use one owner-exported PSX witness instead of automatic mode")
    args = parser.parse_args()
    try:
        report = review_first_capture(
            args.owner_private_bk2, args.owner_private_one_run_workspace,
            args.manual_core_witness,
        )
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RuntimeError):
        parser.error("private first-run offline audit rejected")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

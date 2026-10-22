#!/usr/bin/env python3
"""Owner-only, read-only joining gate for two private MAP02 capture attempts.

Reaudit the original BK2/plan/Lua/PNG chains, then require each manually
exported PSX core witness to match its OWN EmuHawk launch PID + creation time.
All data stay owner-local; the JSON report never contains path/ID/hash/pixels.
Text receipts remain editable and do NOT cryptographically prove provenance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.map02_private_process_witness_binding import (
    NAME as PROCESS_RECEIPT_NAME,
    bind_owner_private_replays,
)
from tools.map02_private_two_capture_audit import _private_root, audit_pair
from tools.map02_private_bizhawk_poweron_launch import AUTO_WITNESS_NAME
from tools.map02_private_core_witness_audit import read_witness

SCHEMA = "vh.map02.owner-paired-capture-core-png-gate.v1"
RUN_NAMES = ("vh-map02-cold-01", "vh-map02-cold-02")


def review_owner_capture(movie: Path, plan: Path, workspace: Path,
                         first_core: Path | None = None,
                         second_core: Path | None = None) -> dict:
    """Recheck separate private captures and locally matched core witnesses.

    Re-reading the full paired PNG chain is deliberate: do not accept a stale
    JSON success report from a different run. Even passing this gate cannot
    establish the emulator's mounted disc, exact BIOS, gameplay or MAP02 scene.
    """
    root = _private_root(workspace)
    first, second = (root / name for name in RUN_NAMES)
    first = _private_root(first)
    second = _private_root(second)
    if first == second or first.parent != root or second.parent != root:
        raise ValueError("two independently named private capture directories required")

    paired = audit_pair(movie, plan, first, second)
    if paired.get("two_private_capture_chains_passed") is not True:
        raise ValueError("both private capture chains must pass independent re-audit")
    if paired.get("both_runs_reported_psx_core_fallback_disabled") is not True:
        raise ValueError("private runtime fallback policy was not proven blocked")
    count = paired.get("screenshot_pairs_checked")
    if type(count) is not int or not 1 <= count <= 30:
        raise ValueError("invalid private screenshot pair count")
    equal = paired.get("decoded_pixel_equal_pairs")
    different = paired.get("decoded_pixel_different_pairs")
    unsupported = paired.get("decoded_pixel_unsupported_pairs")
    if any(type(value) is not int or value < 0 for value in
           (equal, different, unsupported)):
        raise ValueError("invalid private pixel comparison counters")
    if equal + different + unsupported != count:
        raise ValueError("private pixel comparison counts inconsistent")
    pixel_match = different == 0 and unsupported == 0
    if paired.get("all_supported_png_pixel_content_equal") is not pixel_match:
        raise ValueError("private pixel comparison summary inconsistent")

    if (first_core is None) != (second_core is None):
        raise ValueError("paired automatic/manual witness mode must be consistent")
    auto = first_core is None
    if auto and paired.get("both_owner_logs_report_auto_core_witness_before_first_png") is not True:
        raise ValueError("automatic core witness not independently observed before first PNG")
    if auto:
        first_core = first / AUTO_WITNESS_NAME
        second_core = second / AUTO_WITNESS_NAME
        earliest = paired.get("first_capture_counter")
        if type(earliest) is not int or earliest < 1 or earliest > 933949:
            raise ValueError("private plan first capture frame not independently audited")
        for owner_witness in (first_core, second_core):
            if read_witness(owner_witness)[2] > earliest:
                raise ValueError("automatic witness core frame claims a later time than first PNG")
    bound = bind_owner_private_replays(
        first / PROCESS_RECEIPT_NAME, first_core,
        second / PROCESS_RECEIPT_NAME, second_core,
    )
    if bound.get("runtime_core_witnesses_bound_to_launched_process_identity") is not True:
        raise ValueError("manual core witnesses not linked to launched emulator processes")
    if bound.get("reported_emuhawk_processes_distinct") is not True:
        raise ValueError("private emulator processes not distinct")

    return {
        "schema": SCHEMA,
        "owner_private_capture_chains_reaudited": 2,
        "manual_psx_octoshock_core_witnesses_process_matched": 0 if auto else 2,
        "auto_psx_octoshock_core_witnesses_process_matched": 2 if auto else 0,
        "owner_logs_confirm_auto_core_receipt_before_png": auto,
        "auto_core_frame_no_later_than_first_capture_counter": auto,
        "reported_emuhawk_processes_distinct": True,
        "psx_core_fallback_reported_blocked_for_both_replays": True,
        "screenshot_pairs_checked": count,
        "decoded_pixel_equal_pairs": equal,
        "decoded_pixel_different_pairs": different,
        "decoded_pixel_unsupported_pairs": unsupported,
        "all_reviewed_decoded_png_pixels_equal": pixel_match,
        "manual_visual_map02_identification_required": True,
        "editable_witness_provenance_cryptographically_authenticated": False,
        "actual_emuhawk_loaded_bios_authenticated": False,
        "actual_emuhawk_mounted_disc_authenticated": False,
        "original_bk2_controller_delivery_authenticated": False,
        "independent_cold_boots_authenticated": False,
        "authentic_map02_scene_identified": False,
        "switch_renderer_parity_authenticated": False,
        "private_paths_hashes_process_ids_or_pixels_published": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_private_plan", type=Path)
    parser.add_argument("owner_private_capture_workspace", type=Path)
    parser.add_argument("first_owner_private_core_witness", nargs="?", type=Path)
    parser.add_argument("second_owner_private_core_witness", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        report = review_owner_capture(
            args.owner_private_bk2, args.owner_private_plan,
            args.owner_private_capture_workspace,
            args.first_owner_private_core_witness,
            args.second_owner_private_core_witness,
        )
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RuntimeError):
        parser.error("owner-private paired runtime/capture acceptance rejected")
    print(json.dumps(report, indent=2, sort_keys=True))
    # A pixel discrepancy is a review finding, not authenticated parity.
    return 0 if report["all_reviewed_decoded_png_pixels_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

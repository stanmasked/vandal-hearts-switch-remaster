"""Synthetic Windows NTFS integration test for private first-capture audit.

This file never reads an original game, movie, BIOS, or pixel. The fixture
is owner-isolated and reports only a fixed pass marker from PowerShell.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.map02_private_first_run_audit import review_first_capture


def main() -> int:
    base = os.environ.get("VH_MAP02_FIRST_CAPTURE_WIN_FAKE_ROOT", "")
    if os.name != "nt" or not base or len(sys.argv) != 2:
        raise ValueError("Windows private fixture requires synthetic test inputs")
    workspace = Path(base) / "owner-private"
    movie = Path(base) / "fake-movie.bk2"
    chain = {
        "screenshot_count": 3,
        "private_plan_rebuilt_from_direct_bk2": True,
        "capture_logs_match_each_planned_input_and_counter": True,
        "owner_launcher_reports_successful_process_exit": True,
        "owner_log_reports_psx_core_fallback_disabled": True,
        "all_png_crc_zlib_scanlines_pass": True,
        "owner_log_reports_auto_core_witness_before_first_png": True,
    }
    rows = [
        (1, "before", 3000, "held"),
        (1, "middle", 3100, "neutral"),
        (1, "after", 3200, "held"),
    ]
    with patch(
        "tools.map02_private_first_run_audit.parse_plan",
        return_value=("synthetic", rows),
    ), patch(
        "tools.map02_private_first_run_audit.verify",
        return_value=chain,
    ):
        if sys.argv[1] == "owner":
            report = review_first_capture(movie, workspace)
            if (report["owner_private_capture_attempts_reaudited"] != 1
                    or not report["private_octoshock_core_witness_matches_launched_pid_and_birth"]
                    or not report["auto_core_frame_not_later_than_first_png"]
                    or report["authentic_map02_scene_identified"]):
                raise ValueError("private synthetic first-run report invalid")
            return 0
        if sys.argv[1] == "everyone":
            try:
                review_first_capture(movie, workspace)
            except ValueError as exc:
                if "ACL" in str(exc):
                    return 0
                raise ValueError("synthetic negative fixture failed for another reason") from None
            raise ValueError("Everyone-readable output was accepted")
    raise ValueError("unexpected synthetic NTFS fixture mode")


if __name__ == "__main__":
    raise SystemExit(main())

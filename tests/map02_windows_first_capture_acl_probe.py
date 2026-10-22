"""No-media Windows NTFS fixture for Stage513's real owner ACL re-audit path.

Runs only on synthetic CUE/BK2 names and fake core/PID text. Entirely public
safe: no original image, firmware, movie, screenshot or owner identifiers.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import patch

from tools.map02_private_first_run_audit import review_first_capture

def main() -> int:
    workspace_path = os.environ.get("VH_MAP02_FIRST_CAPTURE_WIN_FAKE_ROOT", "")
    if os.name != "nt" or not workspace_path or len(sys.argv) != 2:
        raise ValueError("Windows synthetic fixture requires owner-local test directory")
    workspace = Path(workspace_path) / "owner-private"
    movie = Path(workspace_path) / "fake-movie.bk2"
    chain = {
        "screenshot_count": 3,
        "private_plan_rebuilt_from_direct_bk2": True,
        "capture_logs_match_each_planned_input_and_counter": True,
        "owner_launcher_reports_successful_process_exit": True,
        "owner_log_reports_psx_core_fallback_disabled": True,
        "all_png_crc_zlib_scanlines_pass": True,
        "owner_log_reports_auto_core_witness_before_first_png": True,
    }
    rows = [(1, "before", 3000, "held"),
            (1, "middle", 3100, "neutral"),
            (1, "after", 3200, "held")]
    with patch(
        "tools.map02_private_first_run_audit.parse_plan",
        return_value=("synthetic", rows),
    ), patch(
        "tools.map02_private_first_run_audit.verify",
        return_value=chain,
    ):
        if sys.argv[1] == "owner":
            result = review_first_capture(movie, workspace)
            if (result["owner_private_capture_attempts_reaudited"] != 1
                    or not result["private_octoshock_core_witness_matches_launched_pid_and_birth"]
                    or not result["auto_core_frame_not_later_than_first_png"]
                    or result["authentic_map02_scene_identified"]):
                raise ValueError("synthetic protected first-run report invalid")
            return 0
        if sys.argv[1] == "everyone":
            try:
                review_first_capture(movie, workspace)
            except ValueError as e:
                if "ACL" in str(e):
                    return 0
                raise ValueError("synthetic negative ACL fixture failed for a different reason") from None
            raise ValueError("Everyone-readable fixture unexpectedly accepted")
        raise ValueError("unknown synthetic Windows ACL fixture case")


if __name__ == "__main__":
    raise SystemExit(main())

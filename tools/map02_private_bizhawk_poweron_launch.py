#!/usr/bin/env python3
"""Owner-local BizHawk boot launcher for an original PRIVATE BK2 replay.

Never invokes a shell, prints private path arguments, changes the original
BK2, or passes owner files to GitHub Actions. This is a launcher only:
it cannot authenticate real PS1 execution or an Octoshock GPU frame.

Default is a non-launching preflight. --launch explicitly opens EmuHawk
with its documented --movie= and --lua= options and positional disc path.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess

from tools.map02_private_bk2_capture_plan import plan_lines
from tools.verify_map02_private_neutral_capture_chain import parse_plan

MOVIE_LENGTH = 933949
SCRIPT = Path(__file__).with_name("map02_bizhawk_private_neutral_capture.lua")


def _resolve_private_file(path: Path) -> Path:
    original = Path(path)
    if not original.is_absolute() or original.is_symlink() or not original.is_file():
        raise ValueError("private input requires an absolute regular local file")
    real = original.resolve(strict=True)
    if not stat.S_ISREG(real.stat().st_mode):
        raise ValueError("private source must be regular")
    _reject_git(real)
    return real


def _reject_git(path: Path) -> None:
    real = Path(path).resolve(strict=True)
    for part in (real, *real.parents):
        marker = part / ".git"
        if marker.exists() or marker.is_symlink():
            raise ValueError("never open owner-private BK2/disc/plan/images inside Git checkout")


def build_launch(private_emuhawk: Path, private_disc: Path,
                 private_bk2: Path, private_plan: Path,
                 private_png_root: Path, *,
                 script: Path = SCRIPT,
                 minimum: int = 180, maximum: int = 1800,
                 after: int = 1663, before: int = MOVIE_LENGTH):
    """Return argv/env without starting EmuHawk or exposing paths to stdout."""
    executable = Path(private_emuhawk)
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("EmuHawk executable requires a real absolute file path")
    executable = executable.resolve(strict=True)
    lua = Path(script)
    if not lua.is_absolute() or not lua.is_file():
        raise ValueError("capture Lua script requires an existing absolute path")
    lua = lua.resolve(strict=True)
    disc = _resolve_private_file(private_disc)
    movie = _resolve_private_file(private_bk2)
    plan = _resolve_private_file(private_plan)
    root = Path(private_png_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("PNG output must be an existing private absolute directory")
    root = root.resolve(strict=True)
    _reject_git(root)

    # Re-derive the *exact* owner-private capture plan directly from the
    # current source BK2, before launching an emulator. No input export.
    canonical, positions = parse_plan(plan)
    source = plan_lines(
        movie, limit=len(positions) // 3,
        minimum=minimum, maximum=maximum, after=after, before=before)
    if canonical != "\n".join(source) + "\n":
        raise ValueError("private capture plan does not match current source BK2")
    for group, role, frame, _ in positions:
        filename = "vh_review_w%02d_%s_counter_%07d.png" % (
            group, role, frame + 1)
        if (root / filename).exists() or (root / filename).is_symlink():
            raise ValueError("planned PNG filename already exists: no overwrite")

    args = [
        str(executable),
        "--movie=" + str(movie),
        "--lua=" + str(lua),
        str(disc),  # BizHawk expects the ROM/disc as final positional argument.
    ]
    env = os.environ.copy()
    env["VH_PRIVATE_CAPTURE_PLAN"] = str(plan)
    env["VH_PRIVATE_PNG_DIR"] = str(root)
    return args, env, len(positions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("absolute_emuhawk_executable", type=Path)
    parser.add_argument("owner_private_ps1_disc", type=Path)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_private_capture_plan", type=Path)
    parser.add_argument("owner_private_png_directory", type=Path)
    parser.add_argument("--capture-lua", type=Path, default=SCRIPT)
    parser.add_argument("--min-neutral-frames", type=int, default=180)
    parser.add_argument("--max-neutral-frames", type=int, default=1800)
    parser.add_argument("--after-input-frame", type=int, default=1663)
    parser.add_argument("--before-input-frame", type=int, default=MOVIE_LENGTH)
    parser.add_argument("--launch", action="store_true",
                        help="open BizHawk locally; without this, validate only")
    args = parser.parse_args()
    try:
        command, env, count = build_launch(
            args.absolute_emuhawk_executable, args.owner_private_ps1_disc,
            args.owner_private_bk2, args.owner_private_capture_plan,
            args.owner_private_png_directory, script=args.capture_lua,
            minimum=args.min_neutral_frames, maximum=args.max_neutral_frames,
            after=args.after_input_frame, before=args.before_input_frame)
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        parser.error("private BizHawk power-on launch preflight failed")
    if not args.launch:
        print("VH_PRIVATE_BIZHAWK_LAUNCH_PREFLIGHT_OK planned_png=%d "
              "emulator_started=0 original_ps1_authenticated=0" % count)
        return 0
    # No shell, no echo of arguments, no capture/upload of private output.
    # EmuHawk startup, core, firmware, movie and actual PNGs still require
    # independent observation; exit status alone proves none of those.
    result = subprocess.run(command, env=env, shell=False, check=False)
    print("VH_PRIVATE_BIZHAWK_LOCAL_PROCESS_EXITED "
          "exit_success=%d original_ps1_authenticated=0 map02_identified=0" %
          (result.returncode == 0))
    return int(result.returncode != 0)


if __name__ == "__main__":
    raise SystemExit(main())

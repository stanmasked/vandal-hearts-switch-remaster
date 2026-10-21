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
    # The PNGs are copyrighted source-derived captures. Protect the directory
    # itself so even a permissive process umask cannot expose newly saved PNGs.
    # Windows ACLs are not represented reliably by POSIX mode bits.
    if os.name != "nt":
        root_info = root.stat()
        if root_info.st_uid != os.geteuid():
            raise ValueError("PNG output directory must be owned by current user")
        if stat.S_IMODE(root_info.st_mode) & 0o077:
            raise ValueError("PNG output directory must be owner-only (mode 0700)")

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
    log_path = root / "vh_private_capture.log"
    process_log_path = root / "vh_emuhawk_process.log"
    if log_path.exists() or log_path.is_symlink():
        raise ValueError("private capture log already exists: no overwrite")
    if process_log_path.exists() or process_log_path.is_symlink():
        raise ValueError("private EmuHawk process log already exists: no overwrite")

    args = [
        str(executable),
        "--movie=" + str(movie),
        "--lua=" + str(lua),
        str(disc),  # BizHawk expects the ROM/disc as final positional argument.
    ]
    env = os.environ.copy()
    env["VH_PRIVATE_CAPTURE_PLAN"] = str(plan)
    env["VH_PRIVATE_PNG_DIR"] = str(root)
    env["VH_PRIVATE_CAPTURE_LOG"] = str(log_path)
    env["VH_PRIVATE_PROCESS_LOG"] = str(process_log_path)
    return args, env, len(positions)


def _append_private_log(path: Path, line: str) -> None:
    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("private capture log must remain a regular file")
        os.write(fd, (line + "\n").encode("ascii"))
    finally:
        os.close(fd)


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
    # Create the structured log before EmuHawk starts, with restrictive
    # permissions and exclusive creation. Lua appends only sanitized marker
    # lines; the owner can feed this file directly to the private auditor.
    log_path = Path(env["VH_PRIVATE_CAPTURE_LOG"])
    process_log_path = Path(env["VH_PRIVATE_PROCESS_LOG"])
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    created = []
    try:
        for private_log in (log_path, process_log_path):
            fd = os.open(private_log, flags, 0o600)
            os.close(fd)
            created.append(private_log)
    except OSError:
        for private_log in created:
            try:
                private_log.unlink()
            except OSError:
                pass
        parser.error("private logs could not be created safely")
    # BizHawk logs parsed command-line arguments (including absolute private
    # paths) to stderr. Redirect both streams to a separate mode-0600 local
    # file, never the terminal or CI. Keep the structured Lua audit log apart.
    try:
        process_flags = os.O_WRONLY | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            process_flags |= os.O_NOFOLLOW
        process_fd = os.open(process_log_path, process_flags)
        if not stat.S_ISREG(os.fstat(process_fd).st_mode):
            os.close(process_fd)
            raise OSError("private process log is not regular")
        with os.fdopen(process_fd, "ab") as private_output:
            result = subprocess.run(
                command, env=env, shell=False, check=False,
                stdout=private_output, stderr=subprocess.STDOUT)
    except OSError:
        try:
            _append_private_log(log_path,
                "VH_PRIVATE_BIZHAWK_LAUNCH_ERROR process_started=0 original_ps1_authenticated=0")
        except OSError:
            pass
        print("VH_PRIVATE_BIZHAWK_LOCAL_PROCESS_EXITED exit_success=0 "
              "original_ps1_authenticated=0 map02_identified=0")
        return 1
    success = result.returncode == 0
    try:
        _append_private_log(log_path,
            "VH_PRIVATE_BIZHAWK_LOCAL_PROCESS_EXITED exit_success=%d "
            "original_ps1_authenticated=0 map02_identified=0" % success)
    except OSError:
        print("VH_PRIVATE_BIZHAWK_LOCAL_PROCESS_EXITED exit_success=0 "
              "private_log_write_success=0 original_ps1_authenticated=0")
        return 1
    print("VH_PRIVATE_BIZHAWK_LOCAL_PROCESS_EXITED "
          "exit_success=%d original_ps1_authenticated=0 map02_identified=0" %
          success)
    return int(not success)


if __name__ == "__main__":
    raise SystemExit(main())

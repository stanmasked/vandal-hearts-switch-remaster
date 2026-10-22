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
from tools.map02_private_disc_movie_preflight import (
    inspect_pair, read_private_full_bin_sha256,
)
from tools.map02_private_process_group import run_owned_process
from tools.map02_windows_private_output_acl import require_windows_private_output
from tools.map02_private_process_witness_binding import (
    NAME as OWNER_PROCESS_RECEIPT_NAME, record_started_process,
    read_started_process,
)
from tools.map02_private_core_witness_audit import read_witness

AUTO_WITNESS_NAME = "vh-map02-runtime-core-auto.txt"
AUTO_WITNESS_ENV = "VH_MAP02_CORE_AUTOWRITE_PRIVATE_DIR"
from tools.verify_map02_private_neutral_capture_chain import parse_plan

MOVIE_LENGTH = 933949
# A full owner movie has 933,949 input frames: capture must not be allowed to
# hang forever after the final frame or on a missing/incompatible boot.
# This is a safety ceiling, not an estimate of normal execution duration.
MIN_EMULATOR_TIMEOUT_SECONDS = 300
MAX_EMULATOR_TIMEOUT_SECONDS = 86400
DEFAULT_EMULATOR_TIMEOUT_SECONDS = 28800
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



def require_matching_core_plugin(emuhawk: Path, plugin: Path) -> Path:
    """Require the sole owner-installed external tool next to this EmuHawk."""
    emulator = Path(emuhawk)
    candidate = Path(plugin)
    if (not emulator.is_absolute() or not emulator.is_file()
            or emulator.is_symlink() or not candidate.is_absolute()
            or candidate.is_symlink() or not candidate.is_file()
            or candidate.name != "VhMap02CoreWitness.dll"
            or candidate.parent.name != "ExternalTools"
            or candidate.parent.is_symlink()
            or candidate.parent.parent.resolve(strict=True)
               != emulator.parent.resolve(strict=True)):
        raise ValueError(
            "owner private automatic core witness DLL is not a matching installed external tool")
    _reject_git(candidate)
    return candidate.resolve(strict=True)


def build_launch(private_emuhawk: Path, private_disc: Path,
                 private_bk2: Path, private_plan: Path,
                 private_png_root: Path, *,
                 script: Path = SCRIPT,
                 minimum: int = 180, maximum: int = 1800,
                 after: int = 1663, before: int = MOVIE_LENGTH,
                 private_full_bin_sha256_file: Path | None = None,
                 auto_core_witness_plugin: Path | None = None):
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
    if disc.suffix.lower() == ".cue":
        try:
            cue_text = disc.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise ValueError("CUE descriptor is not readable text") from exc
        cue_root = disc.parent.resolve(strict=True)
        track_count = 0
        for line in cue_text.splitlines():
            fields = line.strip().split(None, 1)
            if not fields or fields[0].upper() != "FILE":
                continue
            if len(fields) != 2:
                raise ValueError("malformed CUE FILE directive")
            payload = fields[1].strip()
            if payload.startswith('"'):
                closing = payload.find('"', 1)
                if closing < 1:
                    raise ValueError("malformed quoted CUE track filename")
                filename = payload[1:closing]
                file_type = payload[closing + 1:].strip()
                if not file_type or '"' in file_type:
                    raise ValueError("malformed CUE track type")
            else:
                tokens = payload.split()
                if len(tokens) != 2:
                    raise ValueError("malformed unquoted CUE FILE directive")
                filename, file_type = tokens
            relative = Path(filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("CUE track path must remain under descriptor directory")
            candidate = cue_root / relative
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise ValueError("CUE track file is missing") from exc
            if not resolved.is_relative_to(cue_root):
                raise ValueError("CUE track path escapes descriptor directory")
            _resolve_private_file(candidate)
            track_count += 1
        if track_count == 0:
            raise ValueError("CUE descriptor has no FILE tracks")
    movie = _resolve_private_file(private_bk2)
    plan = _resolve_private_file(private_plan)
    root = Path(private_png_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("PNG output must be an existing private absolute directory")
    root = root.resolve(strict=True)
    _reject_git(root)
    # On POSIX, require a private output directory independently of the
    # caller's umask; Windows ACLs are not represented by POSIX mode bits.
    if os.name != "nt":
        root_info = root.stat()
        if root_info.st_uid != os.geteuid():
            raise ValueError("PNG output directory must be owned by current user")
        if stat.S_IMODE(root_info.st_mode) & 0o077:
            raise ValueError("PNG output directory must be owner-only (mode 0700)")

    require_windows_private_output(root)

    # Validate the known disc/MAP02 resource profile and BK2 metadata before
    # deriving a plan or allowing the caller to launch EmuHawk.
    if private_full_bin_sha256_file is not None:
        expected = read_private_full_bin_sha256(private_full_bin_sha256_file)
        media = inspect_pair(
            disc, movie, verify_full_bin_sha256=True,
            expected_bin_sha256=expected,
        )
    else:
        media = inspect_pair(disc, movie)
    if not media["media_preflight_ready_for_owner_replay"]:
        raise ValueError("disc/movie media preflight did not match audited profile")

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

    plugin = None
    if auto_core_witness_plugin is not None:
        plugin = require_matching_core_plugin(executable, auto_core_witness_plugin)
        target = root / AUTO_WITNESS_NAME
        if target.exists() or target.is_symlink():
            raise ValueError("owner private automatic core witness already exists")

    args = [
        str(executable),
        "--movie=" + str(movie),
        "--lua=" + str(lua),
        *(["--open-ext-tool-dll=VhMap02CoreWitness.dll"] if plugin is not None else []),
        str(disc),  # BizHawk expects the ROM/disc as final positional argument.
    ]
    env = os.environ.copy()
    # Environment inheritance alone MUST NOT enable sensitive file writes.
    env.pop(AUTO_WITNESS_ENV, None)
    if plugin is not None:
        env[AUTO_WITNESS_ENV] = str(root)
    env["VH_PRIVATE_CAPTURE_PLAN"] = str(plan)
    env["VH_PRIVATE_PNG_DIR"] = str(root)
    env["VH_PRIVATE_CAPTURE_LOG"] = str(log_path)
    env["VH_PRIVATE_PROCESS_LOG"] = str(process_log_path)
    # Lua must cross-check the movie that *actually* opened in EmuHawk,
    # not just movie length and inputs of any pre-existing GUI instance.
    env["VH_PRIVATE_EXPECTED_MOVIE"] = str(movie)
    return args, env, len(positions)


def verify_private_auto_witness(root: Path) -> None:
    """Reject an absent/stale auto-witness before accepting the local process."""
    source = Path(root)
    witness = read_witness(source / AUTO_WITNESS_NAME)
    launch = read_started_process(source / OWNER_PROCESS_RECEIPT_NAME)
    if witness[:2] != launch:
        raise ValueError("private automatic core witness does not match launched process")


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
    parser.add_argument(
        "--emulator-timeout-seconds", type=int,
        default=DEFAULT_EMULATOR_TIMEOUT_SECONDS,
        help="Limit a launched local EmuHawk process to 300..86400 seconds",
    )
    parser.add_argument(
        "--private-full-bin-sha256-file", type=Path,
        help="Privately hash the entire BIN against a user-local 0600 digest file",
    )
    parser.add_argument("--auto-core-witness-plugin", type=Path,
                        help="Owner opt-in: installed BizHawk 2.11 external DLL creates one private early PSX core-only receipt")
    parser.add_argument(
        "--record-process-identity", action="store_true",
        help="Windows only: create a private 0600 actual EmuHawk PID/start-time receipt",
    )
    parser.add_argument("--launch", action="store_true",
                        help="open BizHawk locally; without this, validate only")
    args = parser.parse_args()
    if not MIN_EMULATOR_TIMEOUT_SECONDS <= args.emulator_timeout_seconds <= MAX_EMULATOR_TIMEOUT_SECONDS:
        parser.error("EmuHawk timeout seconds must be within a bounded range")
    if args.auto_core_witness_plugin is not None:
        if not args.record_process_identity:
            parser.error("automatic witness requires matching Windows process identity receipt")
        if args.launch and os.name != "nt":
            parser.error("automatic witness execution requires Windows")
    try:
        command, env, count = build_launch(
            args.absolute_emuhawk_executable, args.owner_private_ps1_disc,
            args.owner_private_bk2, args.owner_private_capture_plan,
            args.owner_private_png_directory, script=args.capture_lua,
            minimum=args.min_neutral_frames, maximum=args.max_neutral_frames,
            after=args.after_input_frame, before=args.before_input_frame,
            private_full_bin_sha256_file=args.private_full_bin_sha256_file,
            auto_core_witness_plugin=args.auto_core_witness_plugin)
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        parser.error("private BizHawk power-on launch preflight failed")
    if args.record_process_identity and args.launch:
        if os.name != "nt":
            parser.error("private EmuHawk process identity is supported on Windows only")
        output = Path(env["VH_PRIVATE_PNG_DIR"]) / OWNER_PROCESS_RECEIPT_NAME
        if output.exists() or output.is_symlink():
            parser.error("private emulator process identity receipt already exists")
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
            extras = {}
            if args.record_process_identity:
                private_dir = Path(env["VH_PRIVATE_PNG_DIR"])
                extras["on_started"] = (
                    lambda pid: record_started_process(pid, private_dir)
                )
            result = run_owned_process(
                command, env=env, stdout=private_output,
                timeout=args.emulator_timeout_seconds, **extras)
    except subprocess.TimeoutExpired:
        # On POSIX, the owned emulator process group has been sent TERM then
        # KILL, including descendants that remained in the session. A
        # daemonized child or new-session grandchild may still survive.
        try:
            _append_private_log(
                log_path,
                "VH_PRIVATE_BIZHAWK_LAUNCH_ERROR process_started=1 "
                "reason=emulator_timeout original_ps1_authenticated=0",
            )
        except OSError:
            pass
        print("VH_PRIVATE_BIZHAWK_LOCAL_PROCESS_EXITED exit_success=0 "
              "reason=timeout original_ps1_authenticated=0 map02_identified=0")
        return 1
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
    if success and args.auto_core_witness_plugin is not None:
        # Never accept a zero process exit without the receipt from THIS
        # exact EmuHawk PID + native process-birth time.
        try:
            verify_private_auto_witness(Path(env["VH_PRIVATE_PNG_DIR"]))
        except (OSError, ValueError, TypeError, RuntimeError):
            success = False
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

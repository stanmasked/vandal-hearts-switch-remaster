#!/usr/bin/env python3
"""Opt-in Linux launcher: match a live child /proc/PID/exe to prepared MAP02 PC binary.

Execute a single user-owned instrumented PC-port binary WITHOUT a shell.
Read /proc/<child PID>/exe while it is alive; require its kernel-reported
device, inode and SHA-256 to match the pre-run plan and binary. On successful
exit, verify full native GPU window/PutPixel/BlendG1/VRAM observation with its
fresh in-process nonce, then exclusively publish a private execution receipt.

This is bounded OS process observation, not secure attestation: it does NOT
prove executable bytes are immutable during execution, prevent another
execve, prove that an opened image was read, or demonstrate genuine retail MAP02.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

from tools.map02_local_capture_handoff import (
    PLAN, _sha, _sha_file, _publish, _validate_plan, verify_pinned_upstream,
)
from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_window_scoped_join import verify_window_scoped_join

RECEIPT = "gpu-local-executed-process.json"
SCHEMA = "vh.map02.local-executed-process.v2"
RGB24_SCHEMA = "vh.map02.local-executed-process.v3"
RGB24_RECEIPT_FIELDS = (
    "pc_preoverlay_image_sha256", "pc_preoverlay_receipt_sha256",
    "pc_preoverlay_capture_session_bound",
)

# Source-bound cycle launch does not inherit arbitrary environment variables:
# a prefix denylist misses loader/plugin controls such as GLIBC_TUNABLES,
# GCONV_PATH, SDL_DYNAMIC_API, QT_PLUGIN_PATH and GIO_EXTRA_MODULES.
# Pass only the ambient display/audio/session fields needed by the PC backend;
# original game and capture settings are supplied explicitly below.
_CYCLE_ALLOWED_INHERITED_ENV = frozenset({
    "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE",
    "LC_MESSAGES", "TZ", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
    "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER",
    "PIPEWIRE_REMOTE", "SDL_AUDIODRIVER", "SDL_VIDEODRIVER",
})
REQUIRED = (
    "schema", "gpu_draw_frame", "local_plan_sha256",
    "kernel_observed_executable_sha256", "kernel_executable_device",
    "kernel_executable_inode", "observed_pid",
    "pc_process_exit_code", "capture_session_sha256",
    "game_image_fd_observed", "kernel_game_image_device",
    "kernel_game_image_inode",
    "native_window_all_files_sha256",
    "selected_pixel_x", "selected_pixel_y",
    "kernel_executable_matched_plan", "same_process_gpu_scoped_nonce_checked",
    "game_image_consumption_proven", "retail_gameplay_authenticated",
    "physical_ps1_equivalence_proven",
)


def _executable_identity(info):
    """Metadata for the exact source-bound ELF inode, not merely its hash."""
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _open_pinned_cycle_exec_fd(binary, expected_sha256, planned_stat):
    """Keep the verified ELF inode open until execve, avoiding a pathname race.

    Hash twice on the actual descriptor that Linux will execute. The caller
    passes this descriptor through Popen(pass_fds) to /proc/self/fd/N and
    closes it immediately after Popen finishes the exec handoff.
    """
    from tools.check_map02_linked_font_elf import MAX_ELF
    try:
        fd = os.open(binary, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise ValueError("source-bound MAP02 executable could not be opened") from None
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid() or before.st_nlink != 1
                or not (before.st_mode & stat.S_IXUSR)
                or not 0 < before.st_size <= MAX_ELF
                or _executable_identity(before) != _executable_identity(planned_stat)):
            raise ValueError("source-bound MAP02 executable inode changed before exec")

        def digest_pass():
            sha = hashlib.sha256()
            for offset in range(0, before.st_size, 1 << 20):
                length = min(1 << 20, before.st_size - offset)
                block = os.pread(fd, length, offset)
                if len(block) != length:
                    raise ValueError("source-bound MAP02 executable short read")
                sha.update(block)
            return sha.hexdigest()

        first = digest_pass()
        if _executable_identity(os.fstat(fd)) != _executable_identity(before):
            raise ValueError("source-bound MAP02 executable changed during fd verification")
        second = digest_pass()
        if first != second or first != expected_sha256:
            raise ValueError("source-bound MAP02 executable fd digest differs from plan")
        if (_executable_identity(os.fstat(fd)) != _executable_identity(before)
                or _executable_identity(os.stat(binary, follow_symlinks=False))
                != _executable_identity(before)):
            raise ValueError("source-bound MAP02 executable path changed before exec")
        return fd
    except OSError:
        os.close(fd)
        raise ValueError("source-bound MAP02 executable fd verification unavailable") from None
    except BaseException:
        os.close(fd)
        raise


def _stable_owned_cycle_image(path, *, retain_fd=False):
    """Verify private disc bytes twice; optionally retain the checked inode.

    Strict cycle launch passes the verified FD through /proc/self/fd/N to
    the original PC CdMount. The named pathname is checked again after exit.
    An inherited descriptor alone is NOT proof the child opened or read it.
    """
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise ValueError("private MAP02 game-image input unavailable") from None
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid() or before.st_nlink != 1
                or before.st_mode & 0o077 or before.st_size <= 0):
            raise ValueError("private MAP02 game-image input is not exclusively owned")

        def digest_pass():
            digest = hashlib.sha256()
            for offset in range(0, before.st_size, 1 << 20):
                count = min(1 << 20, before.st_size - offset)
                block = os.pread(fd, count, offset)
                if len(block) != count:
                    raise ValueError("private MAP02 game-image input short read")
                digest.update(block)
            return digest.hexdigest()

        first = digest_pass()
        if _executable_identity(os.fstat(fd)) != _executable_identity(before):
            raise ValueError("private MAP02 game-image changed during hashing")
        second = digest_pass()
        if first != second:
            raise ValueError("private MAP02 game-image bytes changed between read passes")
        if (_executable_identity(os.fstat(fd)) != _executable_identity(before)
                or _executable_identity(os.stat(path, follow_symlinks=False))
                != _executable_identity(before)):
            raise ValueError("private MAP02 game-image pathname changed during hashing")
        proof = (_executable_identity(before), first)
        if retain_fd:
            result_fd, fd = fd, -1
            return proof, result_fd
        return proof
    except OSError:
        raise ValueError("private MAP02 game-image verification unavailable") from None
    finally:
        if fd >= 0:
            os.close(fd)


def _fingerprint_kernel_exe(pid):
    """Read kernel procfs link for our live child. Fail closed if unavailable."""
    path = f"/proc/{pid}/exe"
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("kernel process executable is not regular")
        sha = hashlib.sha256()
        with os.fdopen(os.dup(fd), "rb") as stream:
            while True:
                chunk = stream.read(1 << 20)
                if not chunk:
                    break
                sha.update(chunk)
        after = os.fstat(fd)
        if (before.st_dev != after.st_dev or
                before.st_ino != after.st_ino or
                before.st_size != after.st_size or
                before.st_mtime_ns != after.st_mtime_ns):
            raise ValueError("process executable changed during kernel observation")
        return before.st_dev, before.st_ino, sha.hexdigest()
    finally:
        os.close(fd)


def _kernel_observes_game_fd(pid, expected, *, excluded_fd=None):
    """Observe an independent disc FD opened by the real child process.

    The cycle launcher deliberately inherits a verified descriptor through
    execve. That inherited descriptor must not be counted as child CdMount.
    This remains FD-level evidence, NOT proof of sector consumption.
    """
    try:
        descriptors = os.scandir(f"/proc/{pid}/fd")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return False
    with descriptors as listing:
        for entry in listing:
            if not entry.name.isdecimal() or (excluded_fd is not None and
                    entry.name == str(excluded_fd)):
                continue
            try:
                observed = entry.stat(follow_symlinks=True)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
            if (stat.S_ISREG(observed.st_mode) and
                    (observed.st_dev, observed.st_ino, observed.st_size) ==
                    expected):
                return True
    return False


def _validate_receipt(raw):
    record = raw if type(raw) is dict else parse_json(raw, RECEIPT)
    schema = record.get("schema") if type(record) is dict else None
    if schema == RGB24_SCHEMA:
        fields(record, REQUIRED + RGB24_RECEIPT_FIELDS, RECEIPT)
    else:
        fields(record, REQUIRED, RECEIPT)
    if (schema not in (SCHEMA, RGB24_SCHEMA) or
            record["kernel_executable_matched_plan"] is not True or
            record["same_process_gpu_scoped_nonce_checked"] is not True or
            record["game_image_fd_observed"] is not True or
            record["game_image_consumption_proven"] is not False or
            record["retail_gameplay_authenticated"] is not False or
            record["physical_ps1_equivalence_proven"] is not False):
        raise ValueError("unsupported or overstated MAP02 process evidence")
    if (schema == RGB24_SCHEMA and
            record["pc_preoverlay_capture_session_bound"] is not True):
        raise ValueError("unverified PC pre-overlay process capture binding")
    for key in (("local_plan_sha256", "kernel_observed_executable_sha256",
                 "capture_session_sha256", "native_window_all_files_sha256") +
                (RGB24_RECEIPT_FIELDS[:2] if schema == RGB24_SCHEMA else ())):
        value = record[key]
        if (type(value) is not str or len(value) != 64 or
                any(c not in "0123456789abcdef" for c in value)):
            raise ValueError("invalid process receipt digest " + key)
    for key, low, high in (
        ("gpu_draw_frame", 1, 2**32 - 1),
        ("kernel_executable_device", 0, 2**64 - 1),
        ("kernel_executable_inode", 1, 2**64 - 1),
        ("kernel_game_image_device", 0, 2**64 - 1),
        ("kernel_game_image_inode", 1, 2**64 - 1),
        ("observed_pid", 1, 2**32 - 1),
        ("pc_process_exit_code", 0, 0),
        ("selected_pixel_x", 0, 1023),
        ("selected_pixel_y", 0, 511),
    ):
        number(record[key], key, low, high)
    return record


def launch_observed_pc(handoff_dir, native_dir, scoped_dir, pc_binary,
                       owned_game, *, upstream, x, y, timeout=900,
                       arguments=(), cycle_dir=None,
                       build_receipt_dir=None, build_bundle_dir=None,
                       krom_source=None, pc_preoverlay_dir=None,
                       stop_after_present=False,
                       source_capture_dir=None, native_preview_dir=None,
                       require_complete_preflight=False):
    """Run the given PC binary directly; never run a shell or create game data."""
    if not sys.platform.startswith("linux") or not Path("/proc/self/exe").exists():
        raise ValueError("observed executable launch requires Linux /proc")
    handoff, native, scoped = (_private_directory(p) for p in
                               (handoff_dir, native_dir, scoped_dir))
    cycle = _private_directory(cycle_dir) if cycle_dir is not None else None
    preoverlay = (_private_directory(pc_preoverlay_dir)
                  if pc_preoverlay_dir is not None else None)
    if preoverlay is not None and cycle is None:
        raise ValueError("private RGB24 capture requires a source-bound cycle")
    if type(stop_after_present) is not bool:
        raise ValueError("MAP02 stop-after-present must be boolean")
    if type(require_complete_preflight) is not bool:
        raise ValueError("MAP02 strict full preflight option must be boolean")
    if require_complete_preflight and (
            source_capture_dir is None or native_preview_dir is None or
            cycle is None or preoverlay is None or
            build_receipt_dir is None or build_bundle_dir is None):
        raise ValueError(
            "strict MAP02 full preflight requires source, preview, cycle, RGB24 and build provenance")
    if stop_after_present and (cycle is None or preoverlay is None):
        raise ValueError("MAP02 clean stop requires cycle and private RGB24 capture")
    checked_dirs = ((handoff, native, scoped) +
                    ((cycle,) if cycle is not None else ()) +
                    ((preoverlay,) if preoverlay is not None else ()))
    roots = tuple(p.resolve() for p in checked_dirs)
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(roots) for b in roots[i + 1:]):
        raise ValueError("execution evidence folders must be separate and nonnested")
    if any(any(p.iterdir()) for p in (native, scoped) +
           ((cycle,) if cycle is not None else ()) +
           ((preoverlay,) if preoverlay is not None else ())):
        raise ValueError("native GPU, scoped and cycle capture folders must start empty")
    if (handoff / RECEIPT).exists() or (handoff / RECEIPT).is_symlink():
        raise ValueError("local execution receipt already exists")
    # The full end-to-end capture involves two more private directories:
    # source/GTE evidence and the eventual native VRAM PNG. An explicitly
    # requested full-layout audit must run BEFORE any executable is started
    # and must not silently accept only one of those two paths.
    if (source_capture_dir is None) != (native_preview_dir is None):
        raise ValueError("full MAP02 prelaunch audit requires both source and preview directories")
    if source_capture_dir is not None:
        if cycle is None or preoverlay is None:
            raise ValueError("full MAP02 prelaunch audit requires cycle and RGB24 capture")
        from tools.check_map02_private_launch_layout import inspect_private_launch_layout
        inspected = inspect_private_launch_layout(
            source_capture_dir, native, scoped, handoff, cycle,
            native_preview_dir, preoverlay)
        if inspected["prelaunch_layout_ready"] is not True:
            raise ValueError("full MAP02 prelaunch layout was not verified")
    if require_complete_preflight:
        # Lazy import: the independent readiness audit reuses this launcher's
        # pinned-image logic, so an eager import would create a module cycle.
        from tools.check_map02_private_cycle_readiness import verify_private_cycle_readiness
        readiness = verify_private_cycle_readiness(
            source_capture_dir, native, scoped, handoff, cycle,
            native_preview_dir, preoverlay,
            pc_binary=pc_binary, owned_game_image=owned_game,
            upstream_checkout=upstream,
            build_receipt_dir=build_receipt_dir,
            build_bundle_dir=build_bundle_dir, krom_source=krom_source)
        if readiness["ready_for_controlled_local_launch"] is not True:
            raise ValueError("strict source-bound MAP02 preflight not confirmed")
    plan_raw, plan_identity = private_file(
        handoff, PLAN, max_bytes=4096, _with_identity=True)
    plan = _validate_plan(plan_raw)
    x = number(x, "sample X", 0, 1023)
    y = number(y, "sample Y", 0, 511)
    timeout = number(timeout, "execution timeout seconds", 1, 86400)
    arguments = tuple(arguments)
    if any(type(arg) is not str or not arg or "\x00" in arg for arg in arguments):
        raise ValueError("invalid PC-port executable argument")
    # Forwarded argv can override the source-bound environment through
    # undocumented switches; a strict cycle launch must not accept it.
    if cycle is not None and arguments:
        raise ValueError("source-bound cycle launch forbids forwarded executable arguments")
    game_image = Path(owned_game).absolute()
    # The strict cycle uses the same complete game-image inode/bytes proof
    # before the child and after it exits. Legacy no-cycle behavior is kept.
    game_proof = (_stable_owned_cycle_image(game_image)
                  if cycle is not None else None)
    image_digest = (game_proof[1] if game_proof is not None
                    else _sha_file(owned_game, private=True))
    binary = Path(pc_binary).absolute()
    if binary.is_symlink() or not binary.is_file():
        raise ValueError("PC binary missing or linked")
    info = os.stat(binary)
    if not stat.S_ISREG(info.st_mode) or not (info.st_mode & stat.S_IXUSR):
        raise ValueError("PC binary is not owner-executable")
    if cycle is not None:
        from tools.check_map02_linked_font_elf import stable_owned_elf_sha256
        executable_digest = stable_owned_elf_sha256
    else:
        executable_digest = _sha_file
    if (verify_pinned_upstream(upstream) !=
            plan["pinned_upstream_source_identity_sha256"] or
            executable_digest(binary) != plan["pc_executable_sha256"] or
            image_digest != plan["owned_game_image_sha256"]):
        raise ValueError("original PC source, binary or game input differs from plan")
    if cycle is not None:
        # A complete source-pinned CD/GPU capture needs an actual linked ELF,
        # not a minimal synthetic child or an ld -r partial object.
        from tools.check_map02_cycle_elf import audit_cycle_elf
        audit_cycle_elf(binary)
        # An exported symbol is not source/build provenance. For strong
        # opt-in CD -> GPU cycle claims, require the private full-link
        # receipt from the local builder AND independently re-audit its
        # pinned Make graph and actual ELF bytes before any exec.
        if build_receipt_dir is None or build_bundle_dir is None:
            raise ValueError("cycle launch requires both private build receipt and source bundle")
        from tools.map02_cycle_build_provenance import verify_build_receipt
        verified_build = verify_build_receipt(
            build_receipt_dir, binary, upstream, build_bundle_dir,
            krom_source=krom_source)
        if verified_build["source_pinned_full_elf_bytes_checked"] is not True:
            raise ValueError("source-pinned original MAP02 ELF could not be confirmed")
    elif (build_receipt_dir is not None or build_bundle_dir is not None or
          krom_source is not None):
        raise ValueError("build receipt options require --cycle-dir")

    if game_proof is not None:
        identity, _ = game_proof
        expected_game_fd = (identity[0], identity[1], identity[5])
    else:
        game_stat = os.stat(game_image)
        expected_game_fd = (game_stat.st_dev, game_stat.st_ino, game_stat.st_size)
    frame = plan["target_gpu_draw_frame"]
    # Legacy observation preserves caller settings except capture overrides.
    # The source-bound cycle uses an allowlist, not an incomplete denylist.
    env = {key: value for key, value in os.environ.items()
           if (key in _CYCLE_ALLOWED_INHERITED_ENV if cycle is not None
               else not key.startswith("VH_MAP02_"))}
    env.update({
        "VH_DISC_IMAGE": str(game_image),
        "VH_MAP02_GPU_CAPTURE_DIR": str(native),
        "VH_MAP02_GPU_CAPTURE_FRAME": str(frame),
        "VH_MAP02_GPU_CAPTURE_WINDOW_COUNT": "2",
        "VH_MAP02_PROBE_OUTPUT_DIR": str(scoped),
        "VH_MAP02_PROBE_FRAME": str(frame),
        "VH_MAP02_PROBE_X": str(x),
        "VH_MAP02_PROBE_Y": str(y),
    })
    if cycle is not None:
        # Explicit original-region and source path are from the pinned
        # checkout, not from any inherited executable/region override.
        env["VH_REGION"] = "us"
        env["VH_PSX_EXE"] = str(Path(upstream).absolute() / "SLUS_004.47")
        # Exact-source HD detection otherwise auto-enables installed packs,
        # while an explicit VH_HD_PACK / VH_HD_VIDEOS override bypasses
        # the pack toggle. Empty values prevent the original ini loader
        # from restoring an incompatible local preference.
        env.update({
            "VH_HDPACK": "0",
            "VH_HD_PACK": "",
            "VH_HD_VIDEOS": "",
            "VH_LANG": "",
            "VH_LANGPACK": "",
            "VH_INTERNAL_SCALE": "1",
            "VH_ACCURATE": "1",
            "VH_RASTER_THREADS": "1",
        })
        # The inherited VH_MAP02_* environment was cleared above: opt-in
        # directories must only come from validated launcher arguments.
        env["VH_MAP02_CYCLE_OUTPUT_DIR"] = str(cycle)
        if preoverlay is not None:
            env["VH_MAP02_PC_PREOVERLAY_OUTPUT_DIR"] = str(preoverlay)
        if stop_after_present:
            env["VH_MAP02_STOP_AFTER_PRESENT"] = "1"
    process = None
    observed = None
    game_fd_observed = False
    try:
        exec_fd = None
        image_fd = None
        extra_exec_args = {}
        try:
            if cycle is not None:
                # Bind BOTH actual exec and CdMount to audited inodes; a
                # between-checks pathname swap must not redirect either open.
                exec_fd = _open_pinned_cycle_exec_fd(
                    binary, plan["pc_executable_sha256"], info)
                ready_image_proof, image_fd = _stable_owned_cycle_image(
                    game_image, retain_fd=True)
                if ready_image_proof != game_proof:
                    raise ValueError("private MAP02 game-image changed before spawn")
                env["VH_DISC_IMAGE"] = f"/proc/self/fd/{image_fd}"
                extra_exec_args = {
                    "executable": f"/proc/self/fd/{exec_fd}",
                    "pass_fds": (exec_fd, image_fd),
                }
            process = subprocess.Popen(
                [str(binary), *arguments], shell=False,
                env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True, **extra_exec_args)
        finally:
            if exec_fd is not None:
                os.close(exec_fd)
            if image_fd is not None:
                os.close(image_fd)
        # A very short-lived program may exit before /proc can be sampled.
        # This must fail closed; it is NOT reason to synthesize an observation.
        deadline = time.monotonic() + min(5, timeout)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                candidate = _fingerprint_kernel_exe(process.pid)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                time.sleep(0.01)
                continue
            if candidate == (info.st_dev, info.st_ino,
                             plan["pc_executable_sha256"]):
                observed = candidate
                break
            # During Popen fork->exec, /proc may still point at parent's
            # interpreter. Give exec a small chance to complete.
            time.sleep(0.01)
        if observed is None:
            raise ValueError("kernel child executable identity was not confirmed")
        # Continue sampling the mounted image descriptor while the child
        # executes its CD / game bootstrap and DrawOTag path. A launch which
        # only matched the ELF but never opened the planned image is rejected.
        # Poll is bounded by the user's timeout, not a fixed boot duration.
        end = time.monotonic() + timeout
        while process.poll() is None:
            if _kernel_observes_game_fd(
                    process.pid, expected_game_fd, excluded_fd=image_fd):
                game_fd_observed = True
            if time.monotonic() >= end:
                raise ValueError("instrumented PC process timeout during disc observation")
            time.sleep(0.02)
        if process.returncode != 0:
            raise ValueError("instrumented PC-port process exited unsuccessfully")
        if not game_fd_observed:
            raise ValueError("process never opened the planned game-image file")
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
    if cycle is not None:
        # Even a same-byte replacement of the private game-image pathname
        # is not the same file observed by the running child.
        if _stable_owned_cycle_image(game_image) != game_proof:
            raise ValueError("private MAP02 game-image identity changed during run")
        # Equal bytes on a replacement inode are not the same source-bound
        # executable. A pathname substitution during the child is refused.
        try:
            same_path_inode = (_executable_identity(
                os.stat(binary, follow_symlinks=False)) ==
                _executable_identity(info))
        except OSError:
            same_path_inode = False
        if not same_path_inode:
            raise ValueError("source-bound MAP02 executable pathname replaced during run")
    if (executable_digest(binary) != plan["pc_executable_sha256"] or
            (game_proof[1] if game_proof is not None
             else _sha_file(owned_game, private=True)) != plan["owned_game_image_sha256"] or
            verify_pinned_upstream(upstream) !=
            plan["pinned_upstream_source_identity_sha256"] or
            private_file(handoff, PLAN, max_bytes=4096,
                         _with_identity=True) != (plan_raw, plan_identity)):
        raise ValueError("original PC executable, owned input or plan changed during run")
    if cycle is not None:
        # Re-audit AFTER the actual child exits. A same-owner edit of
        # the receipt, source bundle or Make graph during execution must
        # not turn a pre-run check into a false final process receipt.
        after_build = verify_build_receipt(
            build_receipt_dir, binary, upstream, build_bundle_dir,
            krom_source=krom_source)
        if after_build != verified_build:
            raise ValueError("MAP02 source-bound PC build receipt changed during run")
    checked = verify_window_scoped_join(native, scoped, target_frame=frame)
    if checked["capture_session_linked"] is not True:
        raise ValueError("original GPU/scoped process session not linked")
    if cycle is not None:
        # This is a pre-publication gate, not a replacement for the full
        # source/image/CD/GPU/process verification done by the final join.
        # The original CdRead CRC, returned CRC and process nonce must all
        # match the completed same-process order observer.
        from tools.verify_map02_cycle_cd_gpu_join import _cycle_cd_pair
        cycle_cd_proof = _cycle_cd_pair(
            scoped, cycle, frame, checked["capture_session_sha256"])
    if preoverlay is not None:
        from tools.verify_map02_pc_preoverlay_session import verify_preoverlay_session
        preoverlay_proof = verify_preoverlay_session(
            preoverlay, cycle, frame=frame,
            expected_session_sha256=checked["capture_session_sha256"])
    receipt_data = {
        "schema": RGB24_SCHEMA if preoverlay is not None else SCHEMA,
        "gpu_draw_frame": frame,
        "local_plan_sha256": _sha(plan_raw),
        "kernel_observed_executable_sha256": observed[2],
        "kernel_executable_device": observed[0],
        "kernel_executable_inode": observed[1],
        "observed_pid": process.pid,
        "pc_process_exit_code": 0,
        "game_image_fd_observed": True,
        "kernel_game_image_device": expected_game_fd[0],
        "kernel_game_image_inode": expected_game_fd[1],
        "capture_session_sha256": checked["capture_session_sha256"],
        "native_window_all_files_sha256":
            checked["all_native_window_file_bytes_sha256"],
        "selected_pixel_x": x, "selected_pixel_y": y,
        "kernel_executable_matched_plan": True,
        "same_process_gpu_scoped_nonce_checked": True,
        "game_image_consumption_proven": False,
        "retail_gameplay_authenticated": False,
        "physical_ps1_equivalence_proven": False,
    }
    if preoverlay is not None:
        receipt_data.update({
            "pc_preoverlay_capture_session_bound": True,
            "pc_preoverlay_image_sha256": preoverlay_proof["pc_rgb24_image_sha256"],
            "pc_preoverlay_receipt_sha256": preoverlay_proof["pc_rgb24_receipt_sha256"],
        })
    receipt = _validate_receipt(receipt_data)
    raw = (json.dumps(receipt, sort_keys=True, separators=(",", ":"))
           + "\n").encode("utf-8")
    if cycle is not None and _cycle_cd_pair(
            scoped, cycle, frame, checked["capture_session_sha256"]
    ) != cycle_cd_proof:
        raise ValueError("cycle/CD observer receipts changed before process publication")
    if preoverlay is not None and verify_preoverlay_session(
            preoverlay, cycle, frame=frame,
            expected_session_sha256=checked["capture_session_sha256"]
    ) != preoverlay_proof:
        raise ValueError("PC pre-overlay process capture changed before publication")
    # Publication must still refer to the original prepared plan inode.
    # Stable bytes alone cannot exclude an equal-content pathname swap.
    if private_file(handoff, PLAN, max_bytes=4096,
                    _with_identity=True) != (plan_raw, plan_identity):
        raise ValueError("private MAP02 plan inode changed before process receipt publication")
    _publish(handoff, RECEIPT, raw)
    result = {
        "private_process_receipt_sha256": _sha(raw),
        "kernel_executable_hash_matched": True,
        "game_image_fd_observed": True,
        "gpu_draws_checked": checked["global_draw_ordinals_checked"],
        "same_process_gpu_scoped_nonce_checked": True,
        "game_image_consumption_proven": False,
        "original_gameplay_authenticated": False,
        "physical_ps1_equivalence_proven": False,
    }
    if preoverlay is not None:
        result["pc_preoverlay_capture_session_bound"] = True
        result["pc_preoverlay_image_sha256"] = preoverlay_proof["pc_rgb24_image_sha256"]
        result["pc_preoverlay_receipt_sha256"] = preoverlay_proof["pc_rgb24_receipt_sha256"]
    return result


def verify_observed_process(handoff_dir, native_dir, scoped_dir, pc_binary,
                            owned_game, *, upstream):
    handoff, native, scoped = (_private_directory(p) for p in
                               (handoff_dir, native_dir, scoped_dir))
    # This late audit must not accept a byte-identical replacement inode
    # while it re-verifies native GPU/scoped output. Check both process
    # receipt and its source plan through double-read pinned descriptors.
    # Import lazily to avoid verifier/witness module import cycles.
    from tools.verify_map02_cycle_cd_gpu_join import _private_evidence_snapshot
    raw, receipt_identity = _private_evidence_snapshot(
        handoff, RECEIPT, max_bytes=4096)
    receipt = _validate_receipt(raw)
    plan_raw, plan_identity = _private_evidence_snapshot(
        handoff, PLAN, max_bytes=4096)
    plan = _validate_plan(plan_raw)
    if (receipt["gpu_draw_frame"] != plan["target_gpu_draw_frame"] or
            receipt["local_plan_sha256"] != _sha(plan_raw) or
            receipt["kernel_observed_executable_sha256"] !=
            plan["pc_executable_sha256"] or
            _sha_file(pc_binary) != plan["pc_executable_sha256"] or
            _sha_file(owned_game, private=True) !=
            plan["owned_game_image_sha256"] or
            verify_pinned_upstream(upstream) !=
            plan["pinned_upstream_source_identity_sha256"]):
        raise ValueError("kernel process receipt differs from local capture plan")
    game_stat = os.stat(Path(owned_game).absolute())
    if (receipt["kernel_game_image_device"] != game_stat.st_dev or
            receipt["kernel_game_image_inode"] != game_stat.st_ino):
        raise ValueError("kernel-observed game image inode differs from current input")
    observed = verify_window_scoped_join(
        native, scoped, target_frame=receipt["gpu_draw_frame"])
    if (receipt["capture_session_sha256"] != observed["capture_session_sha256"] or
            receipt["native_window_all_files_sha256"] !=
            observed["all_native_window_file_bytes_sha256"]):
        raise ValueError("process receipt differs from captured GPU/scoped streams")
    if (_private_evidence_snapshot(handoff, RECEIPT, max_bytes=4096)
            != (raw, receipt_identity) or
            _private_evidence_snapshot(handoff, PLAN, max_bytes=4096)
            != (plan_raw, plan_identity)):
        raise ValueError("process receipt or plan identity changed during re-verification")
    return {"private_process_receipt_sha256": _sha(raw),
            "kernel_executable_hash_matched": True,
            "game_image_fd_observed": True,
            "same_process_gpu_scoped_nonce_checked": True,
            "game_image_consumption_proven": False,
            "original_gameplay_authenticated": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("run", "verify"))
    p.add_argument("private_handoff_dir", type=Path)
    p.add_argument("private_native_windows", type=Path)
    p.add_argument("private_scoped_capture", type=Path)
    p.add_argument("--pc-binary", type=Path, required=True)
    p.add_argument("--owned-game-image", type=Path, required=True)
    p.add_argument("--upstream-checkout", type=Path, required=True)
    p.add_argument("--x", type=int)
    p.add_argument("--y", type=int)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--cycle-dir", type=Path,
                   help="optional private empty 0700 directory for in-process CD->GPU order")
    p.add_argument("--pc-preoverlay-dir", type=Path,
                   help="separate empty 0700 native RGB24 capture directory, valid only with --cycle-dir")
    p.add_argument("--source-capture-dir", type=Path,
                   help="opt-in prelaunch seven-directory audit: prepared private source/GTE evidence")
    p.add_argument("--native-preview-dir", type=Path,
                   help="opt-in prelaunch seven-directory audit: empty private VRAM PNG directory")
    p.add_argument("--require-complete-preflight", action="store_true",
                   help="fail closed until full original PC ELF, disc, build receipt and seven folders pass no-exec readiness")
    p.add_argument("--stop-after-target-present", action="store_true",
                   help="opt-in clean process exit after selected native PC Present; requires cycle and RGB24")
    p.add_argument("--build-receipt-dir", type=Path,
                   help="private local full-ELF build receipt directory")
    p.add_argument("--build-bundle-dir", type=Path,
                   help="source-pinned private diagnostic Make overlay bundle")
    p.add_argument("--krom-source", type=Path,
                   help="original user-owned PsyQ KROMDAT.BIN or PS1 BIOS")
    a, forwarded = p.parse_known_args()
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    try:
        if a.operation == "run":
            if a.x is None or a.y is None:
                raise ValueError("run requires explicit --x and --y")
            result = launch_observed_pc(
                a.private_handoff_dir, a.private_native_windows,
                a.private_scoped_capture, a.pc_binary, a.owned_game_image,
                upstream=a.upstream_checkout, x=a.x, y=a.y,
                timeout=a.timeout, arguments=forwarded,
                cycle_dir=a.cycle_dir,
                build_receipt_dir=a.build_receipt_dir,
                build_bundle_dir=a.build_bundle_dir,
                krom_source=a.krom_source,
                pc_preoverlay_dir=a.pc_preoverlay_dir,
                stop_after_present=a.stop_after_target_present,
                source_capture_dir=a.source_capture_dir,
                native_preview_dir=a.native_preview_dir,
                require_complete_preflight=a.require_complete_preflight)
        else:
            if (a.cycle_dir is not None or a.build_receipt_dir is not None or
                    a.build_bundle_dir is not None or
                    a.krom_source is not None or a.pc_preoverlay_dir is not None or
                    a.source_capture_dir is not None or
                    a.native_preview_dir is not None or
                    a.require_complete_preflight or
                    a.stop_after_target_present):
                raise ValueError("verify original cycle via separate private witness verifier")
            if forwarded:
                raise ValueError("verify does not accept executable arguments")
            result = verify_observed_process(
                a.private_handoff_dir, a.private_native_windows,
                a.private_scoped_capture, a.pc_binary, a.owned_game_image,
                upstream=a.upstream_checkout)
    except ValueError as exc:
        p.error(str(exc))
    except (OSError, subprocess.TimeoutExpired):
        # Native launch failures can expose a private executable, disc or
        # SDK filename via OSError.filename or TimeoutExpired.cmd/output.
        p.error("private MAP02 process launch filesystem or execution unavailable")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

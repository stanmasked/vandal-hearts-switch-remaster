#!/usr/bin/env python3
"""Experimental Linux ELF -> child stdout -> private BGR555 frame capture.

A SHA-pinned ELF is observed using /proc/<pid>/exe before it receives a
one-byte start signal. Bytes arrive over the launcher's bounded stdout pipe.
The channel is real, but the payload is not proven to be game-rendered, to
originate from an original disc, or to match PlayStation hardware.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import struct
import subprocess
import sys
import time

from tools.map02_linux_elf_process_image import (
    observe_live_elf_image, require_elf_image,
)
from tools.audit_map02_joint_gpu_frame import audit as audit_joint_gpu
from tools.map02_linux_child_journal_fd import observe_child_gpu_journal_fd

MAGIC = b"VHM2FRM1"
HEADER = struct.Struct("<8sIII")
SCHEMA = "vh.map02.live-child-pipe-bgr555.v1"
MAX_BYTES = 2 * 1024 * 1024


def _fingerprint_fd(fd):
    digest = hashlib.sha256()
    offset = 0
    while True:
        chunk = os.pread(fd, 65536, offset)
        if not chunk:
            break
        digest.update(chunk)
        offset += len(chunk)
    return offset, digest.hexdigest()


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _read_bounded_stdout(pipe, limit, deadline):
    output = bytearray()
    fd = pipe.fileno()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("native frame pipe timed out")
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            raise ValueError("native frame pipe timed out")
        chunk = os.read(fd, min(65536, limit + 1 - len(output)))
        if not chunk:
            return bytes(output)
        output.extend(chunk)
        if len(output) > limit:
            raise ValueError("native frame pipe exceeded exact frame size")


def _write_exclusive(directory_fd, name, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        os.unlink(name, dir_fd=directory_fd)
        raise


def capture(executable, output_dir, *, frame, width, height,
            executable_sha256, timeout=10, args=(), gpu_journal_dir=None):
    """Read exactly one framed child stream after live ELF observation.

    The producer protocol is: block reading stdin until a single 0x01;
    write <8sIII> magic/frame/width/height and width*height*2 BGR555 bytes
    to stdout; close stdout and exit with status 0. Other output is forbidden.
    """
    if sys.platform != "linux" or not Path("/proc/self/fd").is_dir():
        raise ValueError("live frame capture requires Linux procfs")
    if (type(frame) is not int or not 0 <= frame <= 0xffffffff
            or type(width) is not int or not 1 <= width <= 1024
            or type(height) is not int or not 1 <= height <= 1024
            or width * height * 2 > MAX_BYTES):
        raise ValueError("invalid bounded BGR555 frame geometry")
    if (type(timeout) not in (int, float) or not 0 < timeout <= 60
            or type(executable_sha256) is not str
            or len(executable_sha256) != 64
            or any(c not in "0123456789abcdef" for c in executable_sha256)
            or not isinstance(args, (tuple, list))
            or any(type(arg) is not str or "\x00" in arg for arg in args)):
        raise ValueError("invalid process capture arguments")
    exe = Path(executable).absolute()
    directory = Path(output_dir).absolute()
    journal_path = (Path(gpu_journal_dir).absolute()
                    if gpu_journal_dir is not None else None)
    journal_fd = None

    # A pinned directory FD prevents a later pathname swap from redirecting
    # private image publication. Never traverse an output-directory symlink.
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        st = os.fstat(directory_fd)
        if (not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode) & 0o077
                or os.listdir(directory_fd)):
            raise ValueError("private output directory must be empty and owner-only")
        if journal_path is not None:
            if frame == 0 or (width, height) != (1024, 512):
                raise ValueError("joint GPU journal requires full native VRAM frame")
            journal_fd = os.open(journal_path,
                                 os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            jstat = os.fstat(journal_fd)
            if (not stat.S_ISDIR(jstat.st_mode)
                    or stat.S_IMODE(jstat.st_mode) & 0o077
                    or os.listdir(journal_fd)
                    or (jstat.st_dev, jstat.st_ino) == (st.st_dev, st.st_ino)):
                raise ValueError("joint GPU journal must be separate, empty and owner-only")
        fd = os.open(exe, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except BaseException:
        if journal_fd is not None:
            os.close(journal_fd)
        os.close(directory_fd)
        raise
    proc = None
    try:
        original = os.fstat(fd)
        if not stat.S_ISREG(original.st_mode) or not original.st_mode & 0o111:
            raise ValueError("native capture executable must be a regular ELF file")
        require_elf_image(fd)
        size, digest = _fingerprint_fd(fd)
        if size != original.st_size or digest != executable_sha256:
            raise ValueError("native capture executable SHA-256 mismatch")
        if _identity(os.stat(exe, follow_symlinks=False)) != _identity(original):
            raise ValueError("native executable path changed before launch")
        deadline = time.monotonic() + timeout
        child_env = {"LC_ALL": "C",
                     "VH_MAP02_PRIVATE_FRAME_PIPE_FRAME": str(frame)}
        if journal_path is not None:
            child_env.update({
                "VH_MAP02_GPU_CAPTURE_FRAME": str(frame),
                # Pin journal writes to this inherited directory descriptor;
                # the child must not resolve the caller\'s mutable pathname.
                "VH_MAP02_GPU_CAPTURE_DIR": f"/proc/self/fd/{journal_fd}",
            })
        proc = subprocess.Popen(
            [str(exe), *args], executable=f"/proc/self/fd/{fd}",
            pass_fds=((fd, journal_fd) if journal_fd is not None
                      else (fd,)), cwd=exe.parent,
            env=child_env, umask=0o077,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False,
        )
        observe_live_elf_image(proc.pid, fd)
        journal_child_fd_observed = False
        observed_journal_inode = None
        if journal_fd is not None:
            # The joint C recorder keeps the JSONL FILE* writable and
            # open before DrawOTag waits for the terminal stdout gate.
            # Independently inspect the REAL child /proc fd table before
            # sending that release, rather than trusting an env label.
            observed_journal_inode = observe_child_gpu_journal_fd(
                proc.pid, journal_fd, proc, deadline)
            journal_child_fd_observed = True
            observe_live_elf_image(proc.pid, fd)
        proc.stdin.write(b"\x01")
        proc.stdin.close()
        expected = width * height * 2
        data = _read_bounded_stdout(proc.stdout, HEADER.size + expected, deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0 or proc.wait(timeout=remaining) != 0:
            raise ValueError("native frame producer failed or timed out")
        if len(data) != HEADER.size + expected:
            raise ValueError("native frame pipe truncated or extra bytes")
        magic, observed_frame, observed_width, observed_height = HEADER.unpack(
            data[:HEADER.size])
        if (magic != MAGIC or observed_frame != frame
                or observed_width != width or observed_height != height):
            raise ValueError("native frame pipe header does not match requested frame")
        if (_identity(os.fstat(fd)) != _identity(original)
                or _identity(os.stat(exe, follow_symlinks=False)) != _identity(original)
                or _fingerprint_fd(fd) != (size, digest)):
            raise ValueError("native executable changed during frame capture")
        pixels = data[HEADER.size:]
        journal = None
        if journal_fd is not None:
            from tools.verify_map02_native_gpu_capture import LOG
            def check_kernel_observed_journal_inode():
                info = os.stat(LOG, dir_fd=journal_fd,
                               follow_symlinks=False)
                if ((info.st_dev, info.st_ino) != observed_journal_inode
                        or not stat.S_ISREG(info.st_mode)):
                    raise ValueError(
                        "MAP02 GPU journal inode changed after child fd observation")
            check_kernel_observed_journal_inode()
            journal = audit_joint_gpu(journal_path, frame=frame,
                                      final_pixels=pixels)
            check_kernel_observed_journal_inode()
            for info in (os.fstat(journal_fd),
                         os.stat(journal_path, follow_symlinks=False)):
                if (info.st_dev, info.st_ino) != (jstat.st_dev, jstat.st_ino):
                    raise ValueError("joint GPU journal directory replaced during capture")
        receipt = {
            "schema": SCHEMA,
            "frame": frame, "width": width, "height": height,
            "pixel_format": "bgr555_le",
            "image_sha256": hashlib.sha256(pixels).hexdigest(),
            "executable_sha256": digest,
            "kernel_observed_pinned_elf_before_stream": True,
            "child_stdout_pipe_frame_received": True,
            "retail_gameplay_authenticated": False,
            "ps1_reference_capture_authenticated": False,
            "native_renderer_origin_authenticated": False,
            "hd_replacement_authorized": False,
        }
        if journal is not None:
            receipt.update({
                "schema": "vh.map02.live-child-pipe-bgr555-gpu.v1",
                "gpu_journal_sha256": journal["gpu_journal_sha256"],
                "terminal_gpu_after_vram_sha256":
                    journal["terminal_gpu_after_vram_sha256"],
                "gpu_journal_pairs_verified": journal["gpu_pairs_verified"],
                "terminal_after_vram_matched": True,
                "gpu_journal_same_elf_launch_requested": True,
                "child_writable_gpu_journal_fd_observed": journal_child_fd_observed,
                "gpu_journal_writer_kernel_authenticated": False,
            })
        wrote_image = False
        wrote_receipt = False
        try:
            _write_exclusive(directory_fd, "process-frame.bgr555", pixels)
            wrote_image = True
            _write_exclusive(directory_fd, "process-frame.json",
                             (json.dumps(receipt, sort_keys=True) + "\n").encode())
            wrote_receipt = True
            os.fsync(directory_fd)
        except BaseException:
            if wrote_receipt:
                os.unlink("process-frame.json", dir_fd=directory_fd)
            if wrote_image:
                os.unlink("process-frame.bgr555", dir_fd=directory_fd)
            raise
        return receipt
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if proc.stdin is not None:
                proc.stdin.close()
            if proc.stdout is not None:
                proc.stdout.close()
        os.close(fd)
        if journal_fd is not None:
            os.close(journal_fd)
        os.close(directory_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--executable-sha256", required=True)
    parser.add_argument("--frame", required=True, type=int)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--gpu-journal-dir", type=Path)
    ns = parser.parse_args()
    try:
        result = capture(
            ns.executable, ns.output_dir, frame=ns.frame,
            width=ns.width, height=ns.height,
            executable_sha256=ns.executable_sha256, timeout=ns.timeout,
            gpu_journal_dir=ns.gpu_journal_dir,
        )
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Prepare a local BGR555 reference pair from a replayed, real Linux ELF frame.

Never labels the claimed reference as authenticated PS1 hardware evidence.
Both raw images and the manifest remain in an existing empty 0700 directory.
Only bounded aggregate hashes are printed; game assets never enter GitHub.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.compare_map02_private_bgr555_frames import (
    SCHEMA as PAIR_SCHEMA, compare,
)
from tools.replay_map02_live_frame_receipt import replay

WIDTH, HEIGHT = 1024, 512
FRAME_BYTES = WIDTH * HEIGHT * 2
SCHEMA = "vh.map02.private-pair-from-verified-live-gpu.v1"
REPLAY_SCHEMA = "vh.map02.live-child-pipe-gpu-replayed.v1"
NAMES = ("reference.bgr555", "candidate.bgr555", "frames.json")


def _directory(path, *, empty=False):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY |
                 os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        routed = os.stat(path, follow_symlinks=False)
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) & 0o077
                or (st.st_dev, st.st_ino) != (routed.st_dev, routed.st_ino)
                or (empty and os.listdir(fd))):
            raise ValueError("MAP02 private directory invalid or not empty")
        return fd, (st.st_dev, st.st_ino, st.st_uid,
                    stat.S_IMODE(st.st_mode))
    except BaseException:
        os.close(fd)
        raise


def _check_directory(fd, path, identity):
    st = os.fstat(fd)
    routed = os.stat(path, follow_symlinks=False)
    actual = (st.st_dev, st.st_ino, st.st_uid, stat.S_IMODE(st.st_mode))
    if (actual != identity
            or (routed.st_dev, routed.st_ino) != identity[:2]):
        raise ValueError("MAP02 private input/output directory replaced")


def _private_raw(fd, name):
    raw_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW |
                     os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
    try:
        before = os.fstat(raw_fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_nlink != 1
                or before.st_size != FRAME_BYTES):
            raise ValueError("MAP02 original or candidate raw BGR555 invalid")
        chunks = []
        left = FRAME_BYTES
        while left:
            piece = os.read(raw_fd, min(65536, left))
            if not piece:
                raise ValueError("MAP02 private raw BGR555 truncated")
            chunks.append(piece)
            left -= len(piece)
        after = os.fstat(raw_fd)
        routed = os.stat(name, dir_fd=fd, follow_symlinks=False)
        def identity(st):
            return (st.st_dev, st.st_ino, st.st_uid, st.st_mode,
                    st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        if identity(before) != identity(after) or identity(before) != identity(routed):
            raise ValueError("MAP02 original or candidate BGR555 changed")
        return b"".join(chunks), identity(before)
    finally:
        os.close(raw_fd)


def _publish(fd, name, data):
    created = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
    try:
        with os.fdopen(created, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        os.unlink(name, dir_fd=fd)
        raise


def prepare(reference_file, live_dir, gpu_journal_dir, executable, pair_dir):
    """Make a claimed PS1-vs-verified-PC frame pair; fail closed on mutation."""
    reference_file = Path(reference_file).absolute()
    reference_parent = reference_file.parent
    live_dir = Path(live_dir).absolute()
    gpu_journal_dir = Path(gpu_journal_dir).absolute()
    pair_dir = Path(pair_dir).absolute()
    fds = []
    written = []
    try:
        directory_roles = []
        for folder, empty in (
            (reference_parent, False), (live_dir, False),
            (gpu_journal_dir, False), (pair_dir, True),
        ):
            fd, identity = _directory(folder, empty=empty)
            fds.append(fd)
            directory_roles.append((folder, identity))
        if len({identity[:2] for _, identity in directory_roles}) != 4:
            raise ValueError("MAP02 private source/destination directory roles overlap")
        reference_fd, live_fd, journal_fd, output_fd = fds
        reference, reference_id = _private_raw(reference_fd, reference_file.name)

        first = replay(live_dir, executable=executable,
                       gpu_journal_dir=gpu_journal_dir)
        if (first.get("schema") != REPLAY_SCHEMA
                or (first.get("width"), first.get("height"))
                   != (WIDTH, HEIGHT)
                or type(first.get("frame")) is not int
                or first["frame"] < 1
                or first.get("gpu_terminal_frame_equal") is not True
                or first.get("child_writable_gpu_journal_fd_observed") is not True
                or first.get("same_launcher_gpu_journal_operationally_checked") is not True
                or first.get("gpu_journal_writer_kernel_authenticated") is not False
                or first.get("hd_replacement_authorized") is not False):
            raise ValueError("MAP02 original live GPU/frame replay is incomplete")
        candidate, candidate_id = _private_raw(live_fd, "process-frame.bgr555")
        ref_sha = hashlib.sha256(reference).hexdigest()
        cand_sha = hashlib.sha256(candidate).hexdigest()
        if (cand_sha != first["image_sha256"]
                or first["terminal_gpu_after_vram_sha256"] != cand_sha):
            raise ValueError("MAP02 live candidate does not match GPU final VRAM")

        frame = first["frame"]
        meta = {
            "schema": PAIR_SCHEMA, "frame": frame, "width": WIDTH,
            "height": HEIGHT, "pixel_format": "bgr555_le",
            "images": {
                "reference.bgr555": {"sha256": ref_sha, "frame": frame,
                                    "origin": "ps1_reference_claimed"},
                "candidate.bgr555": {"sha256": cand_sha, "frame": frame,
                                    "origin": "pc_port_candidate_claimed"},
            },
        }
        manifest = (json.dumps(meta, sort_keys=True) + "\n").encode("utf-8")
        for name, data in (("reference.bgr555", reference),
                           ("candidate.bgr555", candidate),
                           ("frames.json", manifest)):
            _publish(output_fd, name, data)
            written.append(name)
        os.fsync(output_fd)
        differential = compare(pair_dir)
        second = replay(live_dir, executable=executable,
                        gpu_journal_dir=gpu_journal_dir)
        reread_ref, same_reference_id = _private_raw(
            reference_fd, reference_file.name)
        reread_live, same_candidate_id = _private_raw(
            live_fd, "process-frame.bgr555")
        if (second != first or reference_id != same_reference_id
                or candidate_id != same_candidate_id
                or reread_ref != reference or reread_live != candidate
                or differential["reference_sha256"] != ref_sha
                or differential["candidate_sha256"] != cand_sha
                or differential["frame"] != frame
                or set(os.listdir(output_fd)) != set(NAMES)):
            raise ValueError("MAP02 private reference or native candidate changed")

        for fd, (path, identity) in zip(fds, directory_roles):
            _check_directory(fd, path, identity)
        return {
            "schema": SCHEMA,
            "frame": frame, "width": WIDTH, "height": HEIGHT,
            "claimed_reference_sha256": ref_sha,
            "verified_live_candidate_sha256": cand_sha,
            "frame_pair_manifest_sha256": differential["manifest_sha256"],
            "same_launch_gpu_journal_sha256": first["gpu_journal_sha256"],
            "same_launch_gpu_terminal_vram_sha256":
                first["terminal_gpu_after_vram_sha256"],
            "different_bgr555_pixels": differential["different_bgr555_pixels"],
            "exact_bgr555_pixel_matches":
                differential["exact_bgr555_pixel_matches"],
            "verified_live_frame_twice_replayed": True,
            "original_reference_ps1_hardware_authenticated": False,
            "same_process_original_gameplay_authenticated": False,
            "hd_replacement_authorized": False,
            "private_pixel_bytes_or_paths_emitted": False,
        }
    except BaseException:
        if fds:
            output_fd = fds[-1] if len(fds) == 4 else None
            if output_fd is not None:
                for name in reversed(written):
                    os.unlink(name, dir_fd=output_fd)
        raise
    finally:
        for fd in reversed(fds):
            os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference-bgr555", type=Path, required=True)
    p.add_argument("--live-frame", type=Path, required=True)
    p.add_argument("--gpu-journal-dir", type=Path, required=True)
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--frame-pair-dir", type=Path, required=True)
    ns = p.parse_args()
    try:
        result = prepare(
            ns.reference_bgr555, ns.live_frame, ns.gpu_journal_dir,
            ns.executable, ns.frame_pair_dir)
    except (OSError, ValueError):
        p.error("MAP02 private frame pair preparation failed")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

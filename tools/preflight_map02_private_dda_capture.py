"""Preflight private MAP02 PC GPU/DDA recorder configuration before launch.

Does not run the game, create any capture files, or authenticate a binary.
Reports only non-sensitive readiness fields; never echoes paths or sample X/Y.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

DIR_KEYS = ("VH_MAP02_GPU_CAPTURE_DIR", "VH_MAP02_PUTPIXEL_DIR")
FRAME_KEYS = ("VH_MAP02_GPU_CAPTURE_FRAME", "VH_MAP02_PUTPIXEL_FRAME")
X_KEY, Y_KEY = "VH_MAP02_PUTPIXEL_X", "VH_MAP02_PUTPIXEL_Y"
X2_KEY, Y2_KEY = "VH_MAP02_PUTPIXEL_X2", "VH_MAP02_PUTPIXEL_Y2"
# C instrumented recorders use a fixed 1024-byte stack path buffer.
LONGEST_CAPTURE_FILENAME = "dda-rejected-edge-candidates.jsonl"


def _decimal(environ, key, upper):
    value = environ.get(key)
    if (type(value) is not str or not value or not value.isascii()
            or not value.isdecimal()):
        raise ValueError(f"{key}: require ASCII decimal integer")
    number = int(value)
    if number > upper:
        raise ValueError(f"{key}: outside instrumented GPU range")
    return number


def _executable_fingerprint(path):
    """Fingerprint a readable regular executable; do not infer its build origin."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("executable cannot be a symlink")
    try:
        # Do not block if an executable pathname is swapped for a FIFO.
        # O_NONBLOCK has no effect on normal executable regular files.
        flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_size <= 0
                    or before.st_size > 1024 * 1024 * 1024
                    or not before.st_mode & 0o111):
                raise ValueError("executable must be a nonempty regular executable under 1 GiB")
            digest = hashlib.sha256()
            size = 0
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
            after = os.fstat(handle.fileno())
            keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if (size != before.st_size
                    or any(getattr(before, key) != getattr(after, key) for key in keys)):
                raise ValueError("executable changed during SHA-256 calculation")
            current = os.stat(path)
            if any(getattr(before, key) != getattr(current, key) for key in keys):
                raise ValueError("executable was replaced during SHA-256 calculation")
        return {"executable_sha256": digest.hexdigest(), "executable_bytes": size}
    except OSError as exc:
        raise ValueError("cannot securely read the local executable") from exc



def _require_outside_git_checkout(path):
    """Refuse native GPU/VRAM output anywhere inside a Git worktree.

    Check the literal absolute path AND its resolved destination because
    linked worktrees can use a .git FILE rather than a directory. This is
    an accidental-publication guard, not a full filesystem sandbox.
    """
    for candidate in (Path(path).absolute(), Path(path).resolve(strict=True)):
        for parent in (candidate, *candidate.parents):
            if parent.name == ".git":
                raise ValueError("native capture directory is in a Git worktree")
            try:
                os.lstat(parent / ".git")
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise ValueError(
                    "native capture Git boundary cannot be verified"
                ) from exc
            raise ValueError("native capture directory is in a Git worktree")


def preflight(environ, *, executable=None):
    """Require synchronized native capture selectors and fresh private output."""
    if not hasattr(os, "getuid"):
        raise ValueError("private POSIX capture permissions cannot be checked")
    for key in DIR_KEYS:
        value = environ.get(key)
        if type(value) is not str or not value or "\x00" in value:
            raise ValueError(f"{key}: missing or invalid directory")
        if not Path(value).is_absolute():
            raise ValueError(f"{key}: directory must be absolute")
    first, second = (Path(environ[key]) for key in DIR_KEYS)
    if first.is_symlink() or second.is_symlink():
        raise ValueError("native capture directory cannot be a symlink")
    try:
        root = first.resolve(strict=True)
        second_resolved = second.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("native capture directory is unavailable") from exc
    if root != second_resolved:
        raise ValueError("GPU and DDA output directories must match")
    # The older single-session native capture has the same private-data
    # publication hazard as the newer two-live-run capture. Reject both
    # ordinary and linked Git worktrees before any GPU file is written.
    _require_outside_git_checkout(first)
    _require_outside_git_checkout(second)
    if not root.is_dir():
        raise ValueError("native capture path is not a directory")
    mode = root.stat()
    if mode.st_uid != os.getuid():
        raise ValueError("native capture directory has another owner")
    if (not stat.S_ISDIR(mode.st_mode)
            or stat.S_IMODE(mode.st_mode) & 0o077
            or stat.S_IMODE(mode.st_mode) & 0o300 != 0o300):
        raise ValueError("native capture directory must be owner-writable and private")
    if any(root.iterdir()):
        raise ValueError("native capture directory must be empty for a fresh session")
    # Check the *literal environment values*, not only their normalized
    # resolved directory: the C snprintf recorders use the supplied string.
    # '/capture/././...' can be much longer than Path.resolve() suggests.
    for key in DIR_KEYS:
        if len(os.fsencode(environ[key])) + 1 + len(LONGEST_CAPTURE_FILENAME) + 1 > 1024:
            raise ValueError("native capture path exceeds original C recorder buffer")
    gpu_frame = _decimal(environ, FRAME_KEYS[0], 0xffffffff)
    pixel_frame = _decimal(environ, FRAME_KEYS[1], 0xffffffff)
    if gpu_frame == 0 or pixel_frame != gpu_frame:
        raise ValueError("GPU and PutPixel target DrawOTag frames must match and be positive")
    primary = (_decimal(environ, X_KEY, 1023),
               _decimal(environ, Y_KEY, 511))
    # The synchronized two-word native observer requires both second
    # coordinates or neither. A partial pair silently disables its
    # recording in the original C recorder, so reject it before launch.
    if X2_KEY in environ or Y2_KEY in environ:
        secondary = (_decimal(environ, X2_KEY, 1023),
                     _decimal(environ, Y2_KEY, 511))
        if primary == secondary:
            raise ValueError("native PutPixel sample coordinates must differ")
    fingerprint = (_executable_fingerprint(executable)
                   if executable is not None else
                   {"executable_sha256": None, "executable_bytes": None})
    return {
        "schema": "map02_private_native_dda_preflight_v1",
        "executable_fingerprinted": executable is not None,
        **fingerprint,
        "capture_frame": gpu_frame,
        "private_empty_directory": True,
        "gpu_and_dda_directory_match": True,
        "gpu_and_pixel_frame_match": True,
        "sample_coordinate_in_vram": True,
        "binary_instrumentation_verified": False,
        "gameplay_capture_verified": False,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path,
                        help="Optionally record SHA-256 and size of the local instrumented binary")
    args = parser.parse_args()
    try:
        result = preflight(os.environ, executable=args.executable)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

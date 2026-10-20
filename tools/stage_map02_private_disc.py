#!/usr/bin/env python3
"""Stage a mounted, owned RU v1.6 BIN/CUE into a private local directory.

Sources are read-only and never chmodded/renamed. This does not authenticate
gameplay, retail US executable identity, or any MAP02 original GPU frame.
Only the private Mac user's destination receives copied image bytes.
"""
import argparse
import ctypes
import hashlib
import sys
import os
from pathlib import Path
import re
import secrets
import stat

from tools.check_map02_local_disc_receipt import RAW_BYTES

BIN_NAME = "Vandal_Hearts_(RU)_v1.6.bin"
CUE_NAME = "Vandal_Hearts_(RU)_v1.6.cue"
SECTOR_BYTES = 2352
STAGE_NAME = "vh-map02-private"
CHUNK = 1024 * 1024
MAX_CUE = 4096
PRIVATE_FREE_MARGIN = 128 * 1024 * 1024  # Reserve room for receipt and other local operations.
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


def _stamp(info):
    return tuple(getattr(info, key) for key in (
        "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
        "st_mode", "st_uid", "st_nlink",
    ))


def _open_source(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_CLOEXEC", 0))
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink < 1:
        os.close(fd)
        raise ValueError("mounted source must be a regular non-symlink file")
    return fd, info


def _check_unchanged(fd, initial, path):
    if (_stamp(initial) != _stamp(os.fstat(fd)) or
            _stamp(initial) != _stamp(path.lstat())):
        raise ValueError("mounted source changed during local copy")


def _read_cue(path):
    fd, info = _open_source(path)
    try:
        if not 0 < info.st_size <= MAX_CUE:
            raise ValueError("invalid mounted CUE size")
        original = os.read(fd, MAX_CUE + 1)
        _check_unchanged(fd, info, path)
    finally:
        os.close(fd)
    try:
        normalized = original.decode("ascii").replace("\r\n", "\n")
    except UnicodeError as exc:
        raise ValueError("mounted CUE must be ASCII") from exc
    expected = (f'FILE "{BIN_NAME}" BINARY\n'
                '  TRACK 01 MODE2/2352\n'
                '    INDEX 01 00:00:00\n')
    if normalized.strip() != expected.strip():
        raise ValueError("mounted CUE does not match pinned MODE2/2352 BIN")
    return original


def _write_all(fd, chunk):
    pos = 0
    while pos < len(chunk):
        written = os.write(fd, chunk[pos:])
        if written <= 0:
            raise OSError("private copy write made no progress")
        pos += written


def _copy_image(source, stagedfd, *, expected_bytes=RAW_BYTES):
    fd, info = _open_source(source)
    try:
        if info.st_size != expected_bytes or info.st_size % SECTOR_BYTES:
            raise ValueError("mounted BIN size or sector count mismatch")
        outfd = os.open(BIN_NAME, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                        | getattr(os, "O_NOFOLLOW", 0), 0o600,
                        dir_fd=stagedfd)
        try:
            os.fchmod(outfd, 0o600)
            observed = hashlib.sha256()
            copied = 0
            while True:
                chunk = os.read(fd, CHUNK)
                if not chunk:
                    break
                _write_all(outfd, chunk)
                observed.update(chunk)
                copied += len(chunk)
            if copied != expected_bytes:
                raise ValueError("private image copy truncated")
            os.fsync(outfd)
        finally:
            os.close(outfd)
        _check_unchanged(fd, info, source)
        return observed.hexdigest()
    finally:
        os.close(fd)


def _verify_staged_copy(stagedfd, expected_sha256, expected_bytes, cue_bytes):
    """Read back the private on-disk image and CUE before publishing directory.

    This deliberately hashes written bytes independently of the source stream;
    the hash computed during copy alone cannot detect a bad destination write.
    """
    staged = os.fstat(stagedfd)
    if (not stat.S_ISDIR(staged.st_mode)
            or staged.st_uid != os.geteuid()
            or stat.S_IMODE(staged.st_mode) != 0o700):
        raise ValueError("staged directory must remain private 0700")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    for name, expected_size in ((BIN_NAME, expected_bytes),
                                (CUE_NAME, len(cue_bytes))):
        fd = os.open(name, flags, dir_fd=stagedfd)
        try:
            old = os.fstat(fd)
            if (not stat.S_ISREG(old.st_mode) or old.st_uid != os.geteuid()
                    or stat.S_IMODE(old.st_mode) != 0o600
                    or old.st_nlink != 1 or old.st_size != expected_size):
                raise ValueError("staged file metadata mismatch: " + name)
            if name == BIN_NAME:
                sha = hashlib.sha256()
                total = 0
                while True:
                    block = os.read(fd, CHUNK)
                    if not block:
                        break
                    sha.update(block)
                    total += len(block)
                if total != expected_size or sha.hexdigest() != expected_sha256:
                    raise ValueError("staged BIN sha256 mismatch")
            else:
                readback = os.read(fd, MAX_CUE + 1)
                if readback != cue_bytes:
                    raise ValueError("staged CUE byte mismatch")
            now = os.fstat(fd)
            named = os.stat(name, dir_fd=stagedfd, follow_symlinks=False)
            if _stamp(old) != _stamp(now) or _stamp(old) != _stamp(named):
                raise ValueError("staged file changed during readback: " + name)
        finally:
            os.close(fd)


def _assert_local_only_destination(parent, image, cue):
    """Reject output in the source tree or macOS cloud-synchronized storage.

    Google Drive for desktop's File Provider root normally lives beneath
    ~/Library/CloudStorage. Refusing it prevents an accidental second
    upload of the full raw BIN. This is conservative path preflight, not
    proof that every third-party folder is unsynchronized.
    """
    checked_parent = parent.resolve(strict=True)
    user_cloud = (Path.home() / "Library" / "CloudStorage").resolve(strict=False)
    for candidate in (parent, checked_parent):
        if candidate.is_relative_to(user_cloud):
            raise ValueError("private destination must not be in macOS CloudStorage")
        for input_path in (image, cue):
            source_dir = input_path.parent.resolve(strict=True)
            if candidate.is_relative_to(source_dir):
                raise ValueError("private destination must be outside mounted source folder")


def _rename_no_replace(dirfd, pending, final):
    """Atomically publish a directory without replacing an existing name.

    os.rename() is NOT sufficient: after an existence preflight, a second
    process can create an empty destination which plain rename then replaces.
    Fail closed when the local OS/filesystem lacks the exclusive primitive.
    """
    if sys.platform == "darwin":
        symbol, exclusive_flag = "renameatx_np", 0x00000004  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        symbol, exclusive_flag = "renameat2", 0x00000001  # RENAME_NOREPLACE
    else:
        raise OSError("atomic no-replace directory rename unsupported on this OS")

    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename_fn = getattr(libc, symbol)
    except AttributeError as exc:
        raise OSError("atomic no-replace rename is unavailable") from exc
    rename_fn.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                          ctypes.c_char_p, ctypes.c_uint)
    rename_fn.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = rename_fn(dirfd, os.fsencode(pending), dirfd,
                       os.fsencode(final), exclusive_flag)
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), final)


def _require_private_disk_capacity(parentfd, expected_bytes):
    """Fail before copying when destination space is plainly insufficient.

    f_bavail counts only available blocks for an unprivileged Mac user.
    This is a preflight, not a reservation: concurrent writes may still
    exhaust capacity. We intentionally avoid any sparse-file assumptions.
    """
    if type(expected_bytes) is not int or expected_bytes <= 0:
        raise ValueError("private BIN expected size must be positive")
    fs = os.fstatvfs(parentfd)
    if (type(fs.f_frsize) is not int or type(fs.f_bavail) is not int
            or fs.f_frsize <= 0 or fs.f_bavail < 0):
        raise ValueError("untrustworthy destination filesystem capacity")
    remaining = fs.f_frsize * fs.f_bavail
    minimum = expected_bytes + PRIVATE_FREE_MARGIN
    if remaining < minimum:
        raise ValueError(
            "insufficient private destination space: need full BIN plus "
            "128 MiB reserve before copying"
        )


def stage_disc(bin_path, cue_path, destination_parent, *,
               stage_name=STAGE_NAME, expected_bytes=RAW_BYTES):
    """Return (private_dir, image_sha256) after complete, atomic directory handoff.

    Source files can have Drive-defined read-only permissions; no source chmod,
    writes, cloud uploads, executable extraction, or raw-byte logging occurs.
    """
    source = Path(bin_path).absolute()
    cue = Path(cue_path).absolute()
    parent = Path(destination_parent).absolute()
    if source.name != BIN_NAME or cue.name != CUE_NAME:
        raise ValueError("unexpected private disc source filenames")
    if (not _SAFE_NAME.fullmatch(stage_name) or stage_name in (".", "..")
            or stage_name.endswith(".pending")):
        raise ValueError("unsafe destination directory name")
    _assert_local_only_destination(parent, source, cue)
    # Pin both mounted file identities before lengthy source and staged reads.
    # Any File Provider replacement must fail closed before publication.
    source_initial = source.lstat()
    cue_initial = cue.lstat()
    cue_bytes = _read_cue(cue)
    if _stamp(cue_initial) != _stamp(cue.lstat()):
        raise ValueError("mounted CUE changed while opening source")
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_CLOEXEC", 0))
    parentfd = os.open(parent, flags)
    try:
        ancestor = os.fstat(parentfd)
        if (not stat.S_ISDIR(ancestor.st_mode)
                or ancestor.st_uid != os.geteuid()
                or stat.S_IMODE(ancestor.st_mode) != 0o700):
            raise ValueError("private destination parent must be owner-only 0700")
        try:
            os.stat(stage_name, dir_fd=parentfd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("private destination already exists")

        # A killed or interrupted earlier invocation may leave a partial
        # owner-private image in a hidden .pending folder. Never silently
        # start another ~665-MB copy beside it. No pending folder is opened,
        # deleted or printed; require deliberate, private owner inspection.
        prefix = "." + stage_name + "."
        if any(name.startswith(prefix) and name.endswith(".pending")
               for name in os.listdir(parentfd)):
            raise ValueError(
                "unfinished private disc staging directory exists; "
                "inspect it locally before retrying (no automatic deletion)"
            )

        # Evaluate filesystem capacity through the already pinned private
        # directory descriptor. No original disc blocks have been read yet.
        _require_private_disk_capacity(parentfd, expected_bytes)

        pending = "." + stage_name + "." + secrets.token_hex(12) + ".pending"
        os.mkdir(pending, 0o700, dir_fd=parentfd)
        moved = False
        stagedfd = None
        try:
            stagedfd = os.open(pending, flags, dir_fd=parentfd)
            copied_sha = _copy_image(source, stagedfd, expected_bytes=expected_bytes)
            # A Drive File Provider CUE could change while the large image is
            # streamed. Reopen it with O_NOFOLLOW and compare BOTH bytes and
            # original inode/metadata. A change must fail before publication.
            cue_after = _read_cue(cue)
            if (cue_after != cue_bytes or
                    _stamp(cue_initial) != _stamp(cue.lstat())):
                raise ValueError("mounted CUE changed during BIN copy")
            cuefd = os.open(CUE_NAME, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                            | getattr(os, "O_NOFOLLOW", 0), 0o600,
                            dir_fd=stagedfd)
            try:
                os.fchmod(cuefd, 0o600)
                _write_all(cuefd, cue_bytes)
                os.fsync(cuefd)
            finally:
                os.close(cuefd)
            os.mkdir("receipt", 0o700, dir_fd=stagedfd)
            # A successful source stream hash is not sufficient. Re-read the
            # actual copied bytes under their anchored private directory FDs.
            _verify_staged_copy(stagedfd, copied_sha, expected_bytes, cue_bytes)
            os.fsync(stagedfd)
            # Local SHA-256 readback can also take substantial time. Catch a
            # Drive replacement during that window immediately before publish.
            # This is an identity/metadata guard, not a second source hash.
            sourcefd, _ = _open_source(source)
            try:
                _check_unchanged(sourcefd, source_initial, source)
            finally:
                os.close(sourcefd)
            cue_final = _read_cue(cue)
            if (cue_final != cue_bytes or
                    _stamp(cue_initial) != _stamp(cue.lstat())):
                raise ValueError("mounted CUE changed before private publication")
            now = parent.lstat()
            stable = lambda info: (info.st_dev, info.st_ino,
                                   info.st_uid, info.st_mode)
            # Creating pending child entries legitimately updates mtime/ctime.
            if (not stat.S_ISDIR(now.st_mode)
                    or stable(ancestor) != stable(os.fstat(parentfd))
                    or stable(ancestor) != stable(now)):
                raise ValueError("private parent changed during staging")
            # The private parent is 0700; refuse preexisting destinations.
            try:
                os.stat(stage_name, dir_fd=parentfd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError("private destination created during staging")
            # The preflight above is advisory only; this syscall MUST enforce
            # exclusivity against a destination created during the race.
            _rename_no_replace(parentfd, pending, stage_name)
            moved = True
            os.fsync(parentfd)
            return parent / stage_name, copied_sha
        finally:
            if stagedfd is not None:
                os.close(stagedfd)
            if not moved:
                # Clean up ONLY this newly-created pending directory. Do not
                # touch any preexisting final destination or the Drive image.
                try:
                    tempfd = os.open(pending, flags, dir_fd=parentfd)
                except FileNotFoundError:
                    pass
                else:
                    try:
                        for name in (BIN_NAME, CUE_NAME):
                            try:
                                os.unlink(name, dir_fd=tempfd)
                            except FileNotFoundError:
                                pass
                        try:
                            os.rmdir("receipt", dir_fd=tempfd)
                        except FileNotFoundError:
                            pass
                    finally:
                        os.close(tempfd)
                    os.rmdir(pending, dir_fd=parentfd)
    finally:
        os.close(parentfd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mounted_bin", type=Path)
    parser.add_argument("--cue", required=True, type=Path)
    parser.add_argument("--private-parent", required=True, type=Path)
    args = parser.parse_args()
    try:
        path, _digest = stage_disc(args.mounted_bin, args.cue,
                                   args.private_parent)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Private local disc copy prepared (no original Drive data changed).")
    print("Local folder:", path)


if __name__ == "__main__":
    main()

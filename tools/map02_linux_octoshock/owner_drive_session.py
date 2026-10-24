#!/usr/bin/env python3
"""Stage541 owner-private one-command backup session for an EXISTING pinned runtime.

No PS1 disc, BIOS, BK2, captures, OAuth secrets or actual owner files enter CI.
The CLI uses actual rclone only when executed in an owner-private environment.
It NEVER generates its own manifest trust anchor: the owner must independently
establish and retain the trusted manifest SHA-256 before running this command.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
from functools import wraps
from inspect import signature
import os
from pathlib import Path
import signal
import stat
import tempfile

from tools.map02_linux_octoshock.archive_owner_runtime import _root
from tools.map02_linux_octoshock.private_runtime_drive import (
    _call_rclone, _remote_name, archive_to_private_drive,
    SESSION_PATTERN,
)
from tools.map02_linux_octoshock.private_runtime_reaudit import (
    audit_independent_readback,
)
from tools.map02_linux_octoshock.private_runtime_tar import (
    _hash_file, _outside, _pin, pack_runtime,
)
from tools.map02_linux_octoshock.verify_owner_runtime import verify_runtime
from tools.map02_linux_octoshock.owner_session_preflight import verify_owner_backup_readiness


class PrivateOwnerSessionError(ValueError):
    pass


def _fail() -> None:
    raise PrivateOwnerSessionError("owner-private archive session not verified")


def _raise_on_stop_signal(signum: int, _frame: object) -> None:
    """Unwind safely and ignore either stop signal until cleanup completes."""
    # Ignore BOTH signals before unwinding: a different second signal must not
    # interrupt the cleanup triggered by the first one. main() restores both
    # previous handlers in its finally.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise SystemExit(128 + signum)


def _discard_incomplete_owner_pin(path: Path | None) -> None:
    """Discard only the original private pin file from this unfinished session.

    Atomically quarantine before deletion so a concurrent replacement between
    lstat and unlink is preserved rather than mistaken for our output.
    """
    if path is None:
        return
    try:
        details = path.lstat()
    except FileNotFoundError:
        return
    if (not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.geteuid()
            or stat.S_IMODE(details.st_mode) != 0o600):
        _fail()
    identity = (details.st_dev, details.st_ino)
    quarantine_dir: Path | None = None
    try:
        quarantine_dir = Path(tempfile.mkdtemp(
            prefix=".map02-pin-cleanup-", dir=str(path.parent),
        ))
        quarantined = quarantine_dir / "payload"
        try:
            os.rename(path, quarantined)
        except FileNotFoundError:
            pass
        else:
            current = quarantined.lstat()
            if (stat.S_ISREG(current.st_mode)
                    and current.st_uid == os.geteuid()
                    and stat.S_IMODE(current.st_mode) == 0o600
                    and (current.st_dev, current.st_ino) == identity):
                quarantined.unlink()
            else:
                # The designated path changed after the initial lstat. Never
                # delete the replacement; restore it only if the original name
                # remains free, otherwise preserve it in quarantine.
                try:
                    path.lstat()
                except FileNotFoundError:
                    os.rename(quarantined, path)
        try:
            quarantine_dir.rmdir()
        except OSError:
            # A non-matching object is deliberately retained if it cannot be
            # restored without overwriting another path.
            pass
    except OSError:
        if quarantine_dir is not None:
            try:
                quarantine_dir.rmdir()
            except OSError:
                pass
        raise


def _reject_unresolved_pin_quarantine(
    receipt_pin: Path, tar_pin_out: Path | None,
) -> None:
    """Reject a new session while any output-parent cleanup marker remains."""
    for pin_output in (receipt_pin, tar_pin_out):
        if (pin_output is not None and any(
                pin_output.parent.glob(".map02-pin-cleanup-*"))):
            _fail()


@contextmanager
def _owner_session_lock(private_folder_map: Path):
    """Hold a persistent owner-only flock for this Drive folder configuration.

    Never unlink the lock file: unlink/recreate would allow two lock inodes.
    The kernel releases the advisory lock when the owning process exits, even
    after SIGKILL. This coordinates cooperative users of this owner workflow.
    """
    parent = Path(private_folder_map).absolute().parent
    try:
        before = parent.lstat()
        if (not stat.S_ISDIR(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o700):
            _fail()
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        directory_fd = os.open(parent, flags)
    except (OSError, ValueError, AttributeError):
        _fail()
    file_fd = None
    try:
        current_dir = os.fstat(directory_fd)
        if ((current_dir.st_dev, current_dir.st_ino)
                != (before.st_dev, before.st_ino)):
            _fail()
        file_fd = os.open(
            ".map02-owner-session.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=directory_fd,
        )
        details = os.fstat(file_fd)
        if (not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.geteuid()
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_nlink != 1):
            _fail()
        fcntl.flock(file_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Check the live path against the locked descriptor at sensitive
        # boundaries. An unlink/recreate could otherwise split lock holders
        # across two inodes even while this descriptor stays flocked.
        def verify_current_lock():
            try:
                parent_now = parent.lstat()
                dir_now = os.fstat(directory_fd)
                held_now = os.fstat(file_fd)
                named_now = os.stat(
                    ".map02-owner-session.lock", dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except OSError:
                _fail()
            if (not stat.S_ISDIR(parent_now.st_mode)
                    or parent_now.st_uid != os.geteuid()
                    or stat.S_IMODE(parent_now.st_mode) != 0o700
                    or (parent_now.st_dev, parent_now.st_ino)
                       != (before.st_dev, before.st_ino)
                    or (dir_now.st_dev, dir_now.st_ino)
                       != (before.st_dev, before.st_ino)
                    or not stat.S_ISREG(held_now.st_mode)
                    or held_now.st_uid != os.geteuid()
                    or stat.S_IMODE(held_now.st_mode) != 0o600
                    or held_now.st_nlink != 1
                    or not stat.S_ISREG(named_now.st_mode)
                    or (named_now.st_dev, named_now.st_ino)
                       != (held_now.st_dev, held_now.st_ino)):
                _fail()
        verify_current_lock()
    except (OSError, ValueError):
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)
        _fail()
    try:
        yield verify_current_lock
    finally:
        # Preserve the inode on disk for safe acquisition by later sessions.
        os.close(file_fd)
        os.close(directory_fd)


def _serialize_owner_session(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        bound = signature(fn).bind(*args, **kwargs)
        receipt = Path(bound.arguments["independently_retained_receipt_pin"])
        archive = bound.arguments.get("independent_archive_pin_output")
        # Stage590's stale-quarantine refusal remains side-effect free.
        _reject_unresolved_pin_quarantine(
            receipt, Path(archive) if archive is not None else None,
        )
        # The same private folder-map location serializes different session
        # names and independent pin output names used by this owner.
        if "_session_lock_check" in kwargs:
            _fail()
        with _owner_session_lock(
            Path(bound.arguments["private_folder_map"]),
        ) as check_lock:
            kwargs["_session_lock_check"] = check_lock
            return fn(*args, **kwargs)
    return guarded


@_serialize_owner_session
def complete_owner_archive_session(
    runtime: Path,
    trusted_manifest_pin: Path,
    private_folder_map: Path,
    owner_session_root: Path,
    independently_retained_receipt_pin: Path,
    builds_remote: str,
    manifests_remote: str,
    session: str,
    *,
    independent_archive_pin_output: Path | None = None,
    invoke=_call_rclone,
    _session_lock_check=None,
) -> dict[str, object]:
    """Pack, upload, download and source-free re-audit in one fail-closed run.

    The pre-existing trusted manifest pin MUST have been established through
    an independent owner-controlled process. A CI-created pin is not valid
    evidence of independent owner provenance.
    """
    cleanup_receipt: Path | None = None
    cleanup_archive: Path | None = None
    try:
        if _session_lock_check is None:
            _fail()
        _session_lock_check()
        source = _root(runtime)
        builds = _remote_name(builds_remote)
        manifests = _remote_name(manifests_remote)
        if (builds == manifests or not isinstance(session, str)
                or SESSION_PATTERN.fullmatch(session) is None):
            _fail()

        root = _outside(owner_session_root, source, nonexistent=True)
        receipt_pin = _outside(
            independently_retained_receipt_pin, source, nonexistent=True,
        )
        manifest_pin = _outside(trusted_manifest_pin, source)
        folder_map = _outside(private_folder_map, source)
        tar_pin_out = None
        if independent_archive_pin_output is not None:
            tar_pin_out = _outside(
                independent_archive_pin_output, source, nonexistent=True,
            )
        distinct = {str(root), str(receipt_pin), str(manifest_pin),
                    str(folder_map)}
        if tar_pin_out is not None:
            distinct.add(str(tar_pin_out))
        if (len(distinct) != (5 if tar_pin_out is not None else 4) or
                receipt_pin == root or receipt_pin.is_relative_to(root) or
                manifest_pin.is_relative_to(root) or folder_map.is_relative_to(root)
                or (tar_pin_out is not None and
                    (tar_pin_out == root or tar_pin_out.is_relative_to(root)))):
            _fail()
        # A previous interrupted cleanup can intentionally leave a quarantined
        # replacement when another writer claimed the original pin path. Do
        # not start another owner session beside unresolved pin data.
        _reject_unresolved_pin_quarantine(receipt_pin, tar_pin_out)
        for p in (manifest_pin, folder_map):
            if (not p.is_file() or p.is_symlink()
                    or stat.S_IMODE(p.stat().st_mode) != 0o600):
                _fail()

        check = verify_runtime(
            source, trusted_manifest_pin_file=manifest_pin,
            require_trusted_pin=True,
        )
        if (check.get("verified") is not True
                or check.get("trusted_manifest_pin_verified") is not True
                or check.get("capture_ready") is not False):
            _fail()

        readiness = verify_owner_backup_readiness(
            source, manifest_pin, folder_map, root, receipt_pin,
            builds, manifests, session, invoke=invoke,
        )
        if (readiness["writes_performed"] is not False
                or readiness["cloud_names_available"] is not True
                or readiness["capture_ready"] is not False):
            _fail()

        # Readiness can take time. Recheck the quarantine gate immediately
        # before creating any new session files so a marker left by a
        # concurrent interrupted owner process cannot slip past preflight.
        _reject_unresolved_pin_quarantine(receipt_pin, tar_pin_out)

        _session_lock_check()
        # At this point the owner-only files are new and the no-write
        # preflight has succeeded. Mark them as disposable from THIS
        # attempt, not before: older trust anchors are never removed.
        cleanup_receipt = receipt_pin
        cleanup_archive = tar_pin_out
        # Never delete failed session content or partly uploaded cloud bytes:
        # they are forensic evidence and require a new session name.
        root.mkdir(mode=0o700)
        # A concurrent interrupted owner process may leave a quarantine
        # between the post-readiness check and this first mkdir. Keep the
        # failed session directory for review, but refuse before packing,
        # uploading, or creating any output pins.
        _reject_unresolved_pin_quarantine(receipt_pin, tar_pin_out)
        archive_folder = root / "archive"
        upload_folder = root / "upload"
        audit_folder = root / "independent-reaudit"
        for folder in (archive_folder, upload_folder, audit_folder):
            folder.mkdir(mode=0o700)
        stem = "map02-runtime-" + session
        tar = archive_folder / (stem + ".tar")
        tar_digest = archive_folder / (stem + ".tar.sha256")
        packed = pack_runtime(source, manifest_pin, tar, tar_digest)
        if (packed["files"] <= 0 or packed["bytes"] <= 0
                or packed.get("drive_upload_authenticated") is not False):
            _fail()
        _session_lock_check()
        # Packing may take enough time for another interrupted owner process
        # to leave a new quarantine. Refuse before any cloud upload if that
        # happened, retaining the local session archive for investigation.
        _reject_unresolved_pin_quarantine(receipt_pin, tar_pin_out)
        uploaded = archive_to_private_drive(
            source, manifest_pin, tar, tar_digest, upload_folder / "new-copy",
            builds, manifests, session, folder_map,
            owner_receipt_pin_output=receipt_pin, invoke=invoke,
        )
        if (not uploaded["drive_download_bytes_verified"]
                or not uploaded["owner_receipt_pin_written"]
                or uploaded["objects_read_back"] != 5
                or uploaded["capture_ready"] is not False):
            _fail()
        _session_lock_check()
        # Stage596: cloud transfer is a long-running boundary. Another
        # interrupted owner process may leave cleanup quarantine while we
        # upload and read back objects. Never endorse that transfer until the
        # output-parent quarantine has been checked again.
        _reject_unresolved_pin_quarantine(receipt_pin, tar_pin_out)
        receipt_sha = _pin(receipt_pin)
        independent = audit_independent_readback(
            folder_map, manifest_pin, tar_digest, receipt_pin,
            audit_folder / "new-copy", builds, manifests, session,
            invoke=invoke,
        )
        if (_pin(receipt_pin) != receipt_sha
                or independent["files"] != packed["files"]
                or independent["bytes"] != packed["bytes"]
                or independent["objects_read_back"] != 5
                or not independent["independent_receipt_pin_verified"]
                or independent["original_runtime_required"] is not False
                or independent["capture_ready"] is not False):
            _fail()
        _session_lock_check()
        # Stage544: preserve the third trust reference OUTSIDE the disposable
        # session. Export only after a complete source-free cloud re-audit.
        # Incomplete uploads must never produce an endorsed owner archive pin.
        if tar_pin_out is not None:
            digest = _pin(tar_digest)
            if _hash_file(tar) != digest:
                _fail()
            fd = os.open(tar_pin_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write((digest + "\n").encode("ascii"))
            if _pin(tar_pin_out) != digest or _hash_file(tar) != digest:
                _fail()
        # Recheck after writing both endorsed pins; if the lock path changed,
        # the existing failure handler discards only this session's new pins.
        _session_lock_check()
        return {
            "runtime_files": independent["files"],
            "runtime_bytes": independent["bytes"],
            "cloud_objects_retrieved": 5,
            "full_private_restore_audited": True,
            # A synthetic CI transport is NEVER owner cloud evidence.
            "authenticated_owner_rclone_invoked": invoke is _call_rclone,
            "trusted_owner_manifest_pin_required": True,
            "owner_receipt_pin_created": True,
            "owner_archive_pin_written": tar_pin_out is not None,
            "original_game_media_used": False,
            "capture_ready": False,
        }
    except (OSError, ValueError, RuntimeError, TypeError, KeyError):
        try:
            _discard_incomplete_owner_pin(cleanup_archive)
            _discard_incomplete_owner_pin(cleanup_receipt)
        except (OSError, ValueError):
            _fail()
        _fail()
    except BaseException:
        # A stop signal must not leave a newly written owner pin looking like
        # accepted trust evidence. Keep the failed session tree for forensics,
        # discard only the session's designated new pin paths, then propagate
        # KeyboardInterrupt/SystemExit or the original unexpected exception.
        try:
            _discard_incomplete_owner_pin(cleanup_archive)
            _discard_incomplete_owner_pin(cleanup_receipt)
        except (OSError, ValueError):
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--trusted-manifest-pin", required=True, type=Path)
    parser.add_argument("--private-folder-map", required=True, type=Path)
    parser.add_argument("--new-session-root", required=True, type=Path)
    parser.add_argument("--new-owner-receipt-pin", required=True, type=Path)
    parser.add_argument("--new-owner-archive-pin", required=True, type=Path,
                        help="separate 0600 pin outside the disposable session")
    parser.add_argument("--builds-remote", required=True)
    parser.add_argument("--manifests-remote", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    stop_signals = (signal.SIGINT, signal.SIGTERM)
    previous_stop_handlers = {
        signum: signal.getsignal(signum) for signum in stop_signals
    }
    for signum in stop_signals:
        signal.signal(signum, _raise_on_stop_signal)
    try:
        try:
            result = complete_owner_archive_session(
                args.runtime, args.trusted_manifest_pin, args.private_folder_map,
                args.new_session_root, args.new_owner_receipt_pin,
                args.builds_remote, args.manifests_remote, args.session,
                independent_archive_pin_output=args.new_owner_archive_pin,
            )
        except PrivateOwnerSessionError:
            print("VH_MAP02_STAGE541_OWNER_DRIVE_SESSION_REJECTED capture_ready=0")
            return 1
        if (not result["authenticated_owner_rclone_invoked"]
                or not result["owner_archive_pin_written"]):
            print("VH_MAP02_STAGE541_OWNER_DRIVE_SESSION_REJECTED capture_ready=0")
            return 1
        print(
            "VH_MAP02_STAGE541_OWNER_DRIVE_SESSION_PASS "
            "runtime_files=%d runtime_bytes=%d verified_objects=5 "
            "real_rclone_invoked=1 original_game_media=0 capture_ready=0" %
            (result["runtime_files"], result["runtime_bytes"])
        )
        return 0
    finally:
        for signum, handler in previous_stop_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())

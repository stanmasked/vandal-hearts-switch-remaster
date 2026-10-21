#!/usr/bin/env python3
"""Owner-local bootstrap of a private, pinned full-image BIN SHA-256 reference.

Never uploads, prints, or commits the raw game, digest, or source paths.
An independently trusted reference must be obtained separately if authentic
disc provenance is required: self-hashing does NOT authenticate the original.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from tools.map02_private_disc_movie_preflight import (
    EXPECTED_BIN_BYTES, EXPECTED_MAP02_SHA256, SCHEMA as SOURCE_SCHEMA,
    _assert_stable, _disc_profile, _full_image_sha256, _open_stable,
    _parse_cue, _read_cue, _reject_git, _resolve_private_file,
    read_private_full_bin_sha256,
)
from tools.map02_private_two_replay_runner import (
    _disc_source_snapshot, _require_disc_unchanged,
)

SCHEMA = "vh.map02.private-bin-digest-reference-bootstrap.v1"


def _private_new_reference(value: Path) -> Path:
    """Require a brand-new file in an owner-private directory outside Git."""
    output = Path(value)
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise ValueError("private digest destination must be a new absolute path")
    parent = output.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("private digest destination parent must be a real directory")
    parent = parent.resolve(strict=True)
    _reject_git(parent)
    info = parent.stat()
    if os.name != "nt" and (
            info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError("digest destination directory must be owner-only")
    return parent / output.name


def create_private_reference(private_cue: Path, reference_file: Path) -> dict:
    """Stream exactly the audited BIN into a private new 0600 digest file.

    Existing targets are never overwritten. No hash or filename is returned.
    The source is rechecked after the full streaming read and before/after
    writing the reference file.
    """
    target = _private_new_reference(reference_file)
    disc_snapshot = _disc_source_snapshot(private_cue)
    cue = _resolve_private_file(private_cue)
    bin_path = _resolve_private_file(cue.parent / _parse_cue(_read_cue(cue)))

    volume, resource, size, _ = _disc_profile(
        bin_path, EXPECTED_MAP02_SHA256,
    )
    if not (volume and resource and size):
        raise ValueError("private source BIN does not match audited MAP02 profile")

    fd, initial = _open_stable(bin_path)
    try:
        if initial.st_size != EXPECTED_BIN_BYTES:
            raise ValueError("private source BIN size is not the expected complete image")
        digest = _full_image_sha256(fd, initial.st_size)
        _assert_stable(fd, bin_path, initial)
    finally:
        os.close(fd)
    _require_disc_unchanged(private_cue, disc_snapshot)

    # Exclusive create prevents accidental overwrite, including dangling links.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    new_fd = None
    created = False
    try:
        new_fd = os.open(target, flags, 0o600)
        created = True
        try:
            with os.fdopen(new_fd, "wb") as stream:
                new_fd = None
                stream.write((digest + "\n").encode("ascii"))
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            if new_fd is not None:
                os.close(new_fd)
        if read_private_full_bin_sha256(target) != digest:
            raise ValueError("private reference verification failed")
        _require_disc_unchanged(private_cue, disc_snapshot)
    except BaseException:
        if created:
            try:
                target.unlink()
            except OSError:
                pass
        raise

    return {
        "schema": SCHEMA,
        "source_media_profile_schema": SOURCE_SCHEMA,
        "audited_disc_profile_matches": True,
        "complete_expected_bin_size_checked": True,
        "full_bin_sha256_streamed": True,
        "new_owner_only_digest_reference_created": True,
        "private_reference_readback_checked": True,
        "cue_and_sampled_sectors_stable_during_bootstrap": True,
        "digest_printed_or_uploaded": False,
        "independently_trusted_disc_provenance_authenticated": False,
        "movie_replay_or_map02_scene_authenticated": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("owner_private_cue", type=Path)
    p.add_argument("new_private_digest_reference_file", type=Path)
    args = p.parse_args()
    try:
        report = create_private_reference(
            args.owner_private_cue, args.new_private_digest_reference_file,
        )
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        p.error("owner-private full BIN digest reference bootstrap failed")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

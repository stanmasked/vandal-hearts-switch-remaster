#!/usr/bin/env python3
"""Owner-local, redacted preflight for the audited MAP02 disc profile and BK2 metadata.

This checks a small known MAP02 resource range, not the full disc. It cannot
prove that the movie will replay correctly, that the BIOS/core is authentic,
or that a captured frame is MAP02. Never upload the source assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import zipfile

from tools.inspect_map02_private_bk2 import (
    MAX_FRAMES, MAX_FRAME_LENGTH, MAX_INPUT_BYTES, check_logkey, parse_header, parse_sync,
    read_frame, read_small, safe_members,
)

SECTOR_BYTES = 2352
USER_DATA_OFFSET = 24
USER_DATA_BYTES = 2048
PVD_LBA = 16
MAP02_LBA = 7116
MAP02_BYTES = 22783
# Owner-local RU v1.6 image length from the independent disc inventory.
# A valid MAP02 sector range alone does not establish a complete disc image.
EXPECTED_BIN_BYTES = 664849248
# Full-image comparison uses a user-private local reference file; never
# publish an owner-specific full-image digest in source, stdout or CI.
FULL_HASH_CHUNK_BYTES = 1024 * 1024
EXPECTED_VOLUME_ID = "SLUS_00447"
EXPECTED_MAP02_SHA256 = "c370660f7f13e6d6e76f4126a45418bc9c64c747de8309ca946d37b502516387"
MAX_CUE_BYTES = 64 * 1024
SCHEMA = "vh.map02.private-disc-movie-preflight.v1"
EXPECTED_MOVIE_FRAMES = 933949


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _reject_git(path: Path) -> None:
    for parent in (path, *path.parents):
        marker = parent / ".git"
        if marker.exists() or marker.is_symlink():
            raise ValueError("private media must stay outside Git checkouts")


def _resolve_private_file(value: Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("private media must be absolute regular nonsymlink files")
    real = path.resolve(strict=True)
    if not stat.S_ISREG(real.stat().st_mode):
        raise ValueError("private media must be regular files")
    _reject_git(real)
    return real


def _open_stable(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    info = os.fstat(fd)
    named = os.stat(path, follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(named.st_mode)
            or _identity(info) != _identity(named)):
        os.close(fd)
        raise ValueError("private source changed while opening")
    return fd, info


def _assert_stable(fd: int, path: Path, before: os.stat_result) -> None:
    after = os.fstat(fd)
    named = os.stat(path, follow_symlinks=False)
    if (not stat.S_ISREG(named.st_mode)
            or _identity(after) != _identity(before)
            or _identity(named) != _identity(after)):
        raise ValueError("private source changed during preflight")


def _read_at(fd: int, offset: int, size: int) -> bytes:
    chunks = []
    total = 0
    while total < size:
        if hasattr(os, "pread"):
            piece = os.pread(fd, size - total, offset + total)
        else:
            os.lseek(fd, offset + total, os.SEEK_SET)
            piece = os.read(fd, size - total)
        if not piece:
            break
        chunks.append(piece)
        total += len(piece)
    return b"".join(chunks)


def _read_cue(path: Path) -> str:
    fd, before = _open_stable(path)
    try:
        if before.st_size <= 0 or before.st_size > MAX_CUE_BYTES:
            raise ValueError("CUE file outside bounded size")
        raw = _read_at(fd, 0, before.st_size)
        _assert_stable(fd, path, before)
    finally:
        os.close(fd)
    if len(raw) != before.st_size:
        raise ValueError("incomplete CUE read")
    return raw.decode("ascii")


def _parse_cue(cue_text: str) -> str:
    files = []
    tracks = []
    indexes = []
    for raw in cue_text.splitlines():
        line = raw.strip()
        if not line or line.upper().startswith("REM "):
            continue
        match = re.fullmatch(r'FILE\s+"([^"]+)"\s+BINARY', line, re.IGNORECASE)
        if match:
            files.append(match.group(1))
            continue
        match = re.fullmatch(r"TRACK\s+(\d+)\s+(MODE2/2352)", line, re.IGNORECASE)
        if match:
            tracks.append((match.group(1), match.group(2).upper()))
            continue
        match = re.fullmatch(r"INDEX\s+01\s+(\d{2}:\d{2}:\d{2})", line, re.IGNORECASE)
        if match:
            indexes.append(match.group(1))
            continue
        raise ValueError("unsupported CUE layout")
    if (len(files) != 1 or len(tracks) != 1 or tracks[0][0] != "01"
            or len(indexes) != 1 or indexes[0] != "00:00:00"):
        raise ValueError("expected one MODE2/2352 track beginning at index zero")
    name = files[0]
    if (Path(name).is_absolute() or Path(name).name != name
            or "/" in name or "\\" in name or name in (".", "..")):
        raise ValueError("CUE must reference one sibling BIN by filename")
    return name


def _bcd(number: int) -> int:
    if not 0 <= number <= 99:
        raise ValueError("CD sector MSF component out of range")
    return ((number // 10) << 4) | number % 10


def _expected_msf(lba: int) -> bytes:
    # Raw PS1 CD track sectors encode absolute MM:SS:FF after 150 pregap
    # sectors. A copied payload at another LBA is not the expected sector.
    frames = lba + 150
    return bytes((
        _bcd(frames // (75 * 60)),
        _bcd((frames // 75) % 60),
        _bcd(frames % 75),
    ))


def _raw_sector(fd: int, lba: int, file_size: int) -> bytes:
    offset = lba * SECTOR_BYTES
    if offset + SECTOR_BYTES > file_size:
        raise ValueError("disc image is shorter than required MAP02 sectors")
    sector = _read_at(fd, offset, SECTOR_BYTES)
    if (len(sector) != SECTOR_BYTES
            or sector[:12] != b"\x00" + b"\xff" * 10 + b"\x00"
            or sector[15] != 2):
        raise ValueError("raw CD sector sync/mode validation failed")
    if sector[12:15] != _expected_msf(lba):
        raise ValueError("raw CD sector MSF address does not match expected LBA")
    # ISO9660 PVD and MAP02 game resource use 2048-byte Mode 2 Form 1
    # user data at +24. In a real CD-XA sector the four-byte subheader
    # must occur twice. Form 2 instead contains a different payload
    # layout and must not be interpreted as 2048-byte Form 1 data.
    if sector[16:20] != sector[20:24]:
        raise ValueError("raw CD-XA repeated subheader mismatch")
    if sector[18] & 0x20:
        raise ValueError("raw CD-XA Form 2 sector is not Mode 2 Form 1")
    return sector


def _full_image_sha256(fd: int, file_size: int) -> str:
    """Read a bounded block at a time; never expose raw image data or hash."""
    digest = hashlib.sha256()
    offset = 0
    while offset < file_size:
        chunk = _read_at(fd, offset, min(FULL_HASH_CHUNK_BYTES, file_size - offset))
        if not chunk:
            raise ValueError("incomplete private BIN during full image hashing")
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _disc_profile(bin_path: Path, expected_map02_sha256: str, *,
                  verify_full_bin_sha256: bool = False,
                  expected_bin_sha256: str | None = None
                  ) -> tuple[bool, bool, bool, bool | None]:
    fd, before = _open_stable(bin_path)
    try:
        if before.st_size <= 0 or before.st_size % SECTOR_BYTES:
            raise ValueError("BIN is not aligned to 2352-byte raw sectors")
        # Do not accept a truncated image containing only the probed PVD and
        # MAP02 resource, or a differently-sized image with those bytes copied.
        size_match = before.st_size == EXPECTED_BIN_BYTES
        required_sectors = MAP02_LBA + (MAP02_BYTES + USER_DATA_BYTES - 1) // USER_DATA_BYTES
        if before.st_size < required_sectors * SECTOR_BYTES:
            raise ValueError("BIN is too short for audited MAP02 resource")
        pvd_sector = _raw_sector(fd, PVD_LBA, before.st_size)
        pvd = pvd_sector[USER_DATA_OFFSET:USER_DATA_OFFSET + USER_DATA_BYTES]
        if len(pvd) != USER_DATA_BYTES or pvd[0] != 1 or pvd[1:6] != b"CD001" or pvd[6] != 1:
            raise ValueError("ISO9660 primary volume descriptor is invalid")
        volume_id = pvd[40:72].decode("ascii").strip()
        payload = bytearray()
        remaining = MAP02_BYTES
        sector_count = (MAP02_BYTES + USER_DATA_BYTES - 1) // USER_DATA_BYTES
        for lba in range(MAP02_LBA, MAP02_LBA + sector_count):
            sector = _raw_sector(fd, lba, before.st_size)
            data = sector[USER_DATA_OFFSET:USER_DATA_OFFSET + USER_DATA_BYTES]
            take = min(remaining, len(data))
            payload.extend(data[:take])
            remaining -= take
        full_match = None
        if verify_full_bin_sha256:
            # Reject nonmatching lengths without traversing an arbitrarily
            # large untrusted file. A request to verify still fails closed.
            full_match = (
                _full_image_sha256(fd, before.st_size) == expected_bin_sha256
                if size_match else False
            )
        _assert_stable(fd, bin_path, before)
    finally:
        os.close(fd)
    if remaining:
        raise ValueError("incomplete MAP02 resource read")
    resource_match = hashlib.sha256(payload).hexdigest() == expected_map02_sha256
    volume_match = volume_id == EXPECTED_VOLUME_ID
    return volume_match, resource_match, size_match, full_match


def _movie_metadata(movie_path: Path, expected_movie_frames: int
                    ) -> tuple[bool, bool, bool, bool]:
    fd, before = _open_stable(movie_path)
    with os.fdopen(fd, "rb") as handle:
        if before.st_size <= 0 or before.st_size > 8 * 1024 * 1024:
            raise ValueError("BK2 archive outside bounded size")
        with zipfile.ZipFile(handle) as archive:
            safe_members(archive)
            raw_header = read_small(archive, "Header.txt")
            try:
                header = parse_header(raw_header)
                header_match = (
                    header.get("Platform") == "PSX"
                    and header.get("GameName") == "Vandal Hearts (USA)"
                    and header.get("Core") == "Octoshock"
                )
                # BizHawk treats StartsFromSavestate presence as an anchor;
                # its value (even "False") is not reliable proof of power-on.
                # Refuse all save-anchored header variants. safe_members()
                # separately rejects a CoreState/SaveRAM ZIP member.
                poweron_declared = not any(
                    key.casefold().startswith("startsfromsave")
                    for key in header
                )
            except ValueError:
                header_match = False
                poweron_declared = False
            try:
                sync = parse_sync(read_small(archive, "SyncSettings.json"))
                sync_match = (
                    sync.get("single_controller") is True
                    and sync.get("memory_cards") is False
                    and sync.get("multitap") is False
                )
            except ValueError:
                sync_match = False
            # Check the entire BK2 controller stream. Header/sync metadata alone
            # can be copied into a movie with malformed or truncated inputs.
            with archive.open("Input Log.txt") as raw:
                if raw.readline(256).strip() != b"[Input]":
                    raise ValueError("BK2 input block missing")
                check_logkey(raw.readline(2048).rstrip(b"\r\n"))
                frames = 0
                bytes_read = 0
                ended = False
                while True:
                    # A malformed BK2 may contain a single giant line.
                    # Never allocate that line before the size check.
                    raw_line = raw.readline(MAX_FRAME_LENGTH + 3)
                    if not raw_line:
                        break
                    if (not raw_line.endswith(b"\n")
                            and raw_line != b"[/Input]"):
                        raise ValueError("BK2 input line exceeds bounded length")
                    bytes_read += len(raw_line)
                    if bytes_read > MAX_INPUT_BYTES:
                        raise ValueError("BK2 input expansion limit exceeded")
                    line = raw_line.rstrip(b"\r\n")
                    if line == b"[/Input]":
                        ended = True
                        break
                    read_frame(line)
                    frames += 1
                    if frames > MAX_FRAMES:
                        raise ValueError("BK2 input frame limit exceeded")
                if not ended or raw.read(1):
                    raise ValueError("BK2 input end marker missing or extra bytes")
            input_match = frames == expected_movie_frames
        _assert_stable(handle.fileno(), movie_path, before)
        return header_match, sync_match, input_match, poweron_declared


def inspect_pair(cue_path: Path, movie_path: Path, *,
                 expected_map02_sha256: str = EXPECTED_MAP02_SHA256,
                 verify_full_bin_sha256: bool = False,
                 expected_bin_sha256: str | None = None,
                 expected_movie_frames: int = EXPECTED_MOVIE_FRAMES) -> dict:
    if (not isinstance(expected_map02_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_map02_sha256)):
        raise ValueError("expected MAP02 profile digest must be lowercase SHA-256")
    if (type(expected_movie_frames) is not int
            or not 1 <= expected_movie_frames <= MAX_FRAMES):
        raise ValueError("expected BK2 frame count is outside bounded range")
    if type(verify_full_bin_sha256) is not bool:
        raise ValueError("full BIN verification flag must be boolean")
    if verify_full_bin_sha256 and (
            not isinstance(expected_bin_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_bin_sha256)):
        raise ValueError("full BIN verification requires a private lowercase SHA-256")
    if not verify_full_bin_sha256 and expected_bin_sha256 is not None:
        raise ValueError("private full BIN digest provided without verification")
    cue = _resolve_private_file(cue_path)
    movie = _resolve_private_file(movie_path)
    cue_text = _read_cue(cue)
    bin_name = _parse_cue(cue_text)
    bin_path = _resolve_private_file(cue.parent / bin_name)
    volume_match, resource_match, size_match, full_match = _disc_profile(
        bin_path, expected_map02_sha256,
        verify_full_bin_sha256=verify_full_bin_sha256,
        expected_bin_sha256=expected_bin_sha256,
    )
    (movie_header_match, movie_sync_match, movie_input_match,
     movie_declares_poweron) = _movie_metadata(movie, expected_movie_frames)
    profile_match = (
        volume_match and resource_match and size_match
        and (not verify_full_bin_sha256 or full_match is True)
    )
    ready = (profile_match and movie_header_match and movie_sync_match
             and movie_input_match and movie_declares_poweron)
    return {
        "schema": SCHEMA,
        "cue_single_mode2_2352_track": True,
        "iso9660_pvd_valid": True,
        "disc_volume_id_matches_audited_profile": volume_match,
        "disc_size_matches_audited_profile": size_match,
        "full_bin_sha256_requested": verify_full_bin_sha256,
        "full_bin_sha256_verified": full_match,
        "map02_prs_matches_expected_profile": resource_match,
        "movie_header_matches_vandal_hearts_usa_psx_octoshock": movie_header_match,
        "movie_sync_matches_one_controller_no_cards": movie_sync_match,
        "movie_input_log_matches_expected_frame_count": movie_input_match,
        "movie_has_no_declared_save_anchor": movie_declares_poweron,
        "media_preflight_ready_for_owner_replay": ready,
        "exact_disc_movie_compatibility_verified": False,
        "bios_configuration_verified": False,
        "actual_octoshock_playback_verified": False,
        "map02_scene_identity_verified": False,
        "private_asset_paths_or_hashes_reported": False,
        "private_assets_uploaded": False,
        "manual_scene_and_input_display_alignment_review_required": True,
    }


def read_private_full_bin_sha256(path: Path) -> str:
    """Load a private pinned digest without exposing it in CLI or JSON output."""
    private_ref = _resolve_private_file(path)
    if os.name != "nt":
        info = private_ref.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("full-BIN digest reference must be user-private")
    fd, before = _open_stable(private_ref)
    try:
        if before.st_size not in (64, 65):
            raise ValueError("private full-BIN digest must be exactly 64 hex digits")
        raw = _read_at(fd, 0, before.st_size)
        _assert_stable(fd, private_ref, before)
    finally:
        os.close(fd)
    try:
        reference = raw.decode("ascii").strip()
    except UnicodeError as exc:
        raise ValueError("private full-BIN digest is not ASCII") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", reference):
        raise ValueError("private full-BIN digest must be lowercase SHA-256")
    return reference


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_cue", type=Path)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument(
        "--private-full-bin-sha256-file", type=Path,
        help="Read a 64-hex full-BIN SHA-256 reference from an owner-local private file",
    )
    args = parser.parse_args()
    try:
        expected_digest = (
            read_private_full_bin_sha256(args.private_full_bin_sha256_file)
            if args.private_full_bin_sha256_file is not None else None
        )
        report = inspect_pair(
            args.owner_private_cue, args.owner_private_bk2,
            verify_full_bin_sha256=expected_digest is not None,
            expected_bin_sha256=expected_digest,
        )
    except (OSError, ValueError, UnicodeError, KeyError, zipfile.BadZipFile,
            RuntimeError, TypeError):
        parser.error("owner-private disc/movie compatibility preflight unavailable")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["media_preflight_ready_for_owner_replay"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

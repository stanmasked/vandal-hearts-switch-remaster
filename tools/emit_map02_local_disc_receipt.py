#!/usr/bin/env python3
"""Create a digest-only receipt from an owned, private RU v1.6 BIN/CUE.

No original sectors, executable data or frame pixels are emitted. Report
fields are observations, NOT independent retail-game or hardware attestation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.check_map02_owned_disc_extent import (
    BOOT_LBA_US, SECTOR_RAW, USER_DATA_START, USER_DATA_BYTES, _raw_sector,
)
from tools.check_map02_local_disc_receipt import (
    RAW_BYTES, MAP02_LBA, MAP02_SECTORS, MAP02_PRS_BYTES,
    MAP02_PRS_SHA256, SCHEMA, validate_receipt, verify_receipt_file,
)

RECEIPT = "vh-map02-local-disc-digest-receipt.json"
MAX_CUE_BYTES = 4096


def identity(st):
    return tuple(getattr(st, key) for key in (
        "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns",
        "st_mode", "st_uid", "st_nlink",
    ))


def open_owned(path):
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_CLOEXEC", 0))
    fd = os.open(path, flags)
    st = os.fstat(fd)
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
            or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1):
        os.close(fd)
        raise ValueError("source must be owner-private 0600 regular single-link")
    return fd, st


def check_cue(path, image_name):
    if (not image_name or "/" in image_name or "\\" in image_name
            or "\n" in image_name or "\r" in image_name):
        raise ValueError("unsafe CUE referenced image name")
    path = Path(path).absolute()
    fd, original = open_owned(path)
    try:
        if not 0 < original.st_size <= MAX_CUE_BYTES:
            raise ValueError("CUE size invalid")
        raw = os.read(fd, MAX_CUE_BYTES + 1)
        if (identity(original) != identity(os.fstat(fd))
                or identity(original) != identity(path.lstat())):
            raise ValueError("CUE changed while reading")
    finally:
        os.close(fd)
    try:
        lines = raw.decode("ascii").replace("\r\n", "\n")
    except UnicodeError as exc:
        raise ValueError("CUE must contain ASCII text") from exc
    expected = (f'FILE "{image_name}" BINARY\n'
                '  TRACK 01 MODE2/2352\n'
                '    INDEX 01 00:00:00\n')
    if lines.strip() != expected.strip():
        raise ValueError("CUE must describe exactly one Mode2/2352 data track")


def inspect(image, cue, *, expected_bytes=RAW_BYTES,
            expected_prs_sha256=MAP02_PRS_SHA256):
    """Hash a local owned image, then verify boot and 12 MAP02 XA sectors."""
    image = Path(image).absolute()
    if cue is None:
        raise ValueError("original BIN must have matching CUE")
    check_cue(cue, image.name)
    fd, original = open_owned(image)
    try:
        if original.st_size != expected_bytes or original.st_size % SECTOR_RAW:
            raise ValueError("owned BIN size/2352-byte layout mismatch")
        digest = hashlib.sha256()
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        boot = _raw_sector(fd, BOOT_LBA_US)
        if boot[USER_DATA_START:USER_DATA_START + 8] != b"PS-X EXE":
            raise ValueError("US-layout PS-X EXE boot signature missing")
        payload = b"".join(
            _raw_sector(fd, lba)[USER_DATA_START:USER_DATA_START + USER_DATA_BYTES]
            for lba in range(MAP02_LBA, MAP02_LBA + MAP02_SECTORS)
        )
        if (identity(original) != identity(os.fstat(fd))
                or identity(original) != identity(image.lstat())):
            raise ValueError("owned BIN changed during hashing")
        declared = int.from_bytes(payload[:4], "little")
        if declared != MAP02_PRS_BYTES - 4:
            raise ValueError("MAP02 compressed length differs from prior audit")
        prs = payload[:declared + 4]
        observed_prs = hashlib.sha256(prs).hexdigest()
        if observed_prs != expected_prs_sha256:
            raise ValueError("MAP02 PRS SHA-256 differs from prior RU v1.6 audit")
        return {
            "schema": SCHEMA,
            "raw_image_bytes": original.st_size,
            "raw_image_sectors": original.st_size // SECTOR_RAW,
            "raw_image_sha256": digest.hexdigest(),
            "cue_single_mode2_2352": True,
            "checked_xa_form1_sectors": 1 + MAP02_SECTORS,
            "map02_prs_lba": MAP02_LBA,
            "map02_prs_sectors": MAP02_SECTORS,
            "map02_prs_bytes": len(prs),
            "map02_prs_sha256": observed_prs,
            "map02_matches_prior_ru_audit": True,
            "byte_exact_original_us_executable_proven": False,
            "real_gameplay_capture_proven": False,
            "physical_ps1_pixel_parity_proven": False,
            "game_bytes_in_receipt": False,
        }
    finally:
        os.close(fd)


def publish(report, directory):
    """Exclusively publish a 0600 JSON beneath a pinned 0700 directory."""
    root = Path(directory).absolute()
    data = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("ascii")
    if not 0 < len(data) <= 4096:
        raise ValueError("invalid receipt byte count")
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_CLOEXEC", 0))
    dirfd = os.open(root, flags)
    try:
        original = os.fstat(dirfd)
        if (not stat.S_ISDIR(original.st_mode)
                or original.st_uid != os.geteuid()
                or stat.S_IMODE(original.st_mode) != 0o700):
            raise ValueError("private output directory must be 0700")
        if os.listdir(dirfd):
            raise ValueError("private output directory must be initially empty")
        file_flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                      | getattr(os, "O_NOFOLLOW", 0)
                      | getattr(os, "O_CLOEXEC", 0))
        fd = os.open(RECEIPT, file_flags, 0o600, dir_fd=dirfd)
        created = os.fstat(fd)
        completed = False
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(dirfd)
            now = root.lstat()
            if (not stat.S_ISDIR(now.st_mode)
                    or (original.st_dev, original.st_ino,
                        original.st_uid, original.st_mode) !=
                    (now.st_dev, now.st_ino, now.st_uid, now.st_mode)):
                raise ValueError("private output directory changed")
            completed = True
        finally:
            if not completed:
                try:
                    now = os.stat(RECEIPT, dir_fd=dirfd, follow_symlinks=False)
                    if (stat.S_ISREG(now.st_mode)
                            and (now.st_dev, now.st_ino) ==
                            (created.st_dev, created.st_ino)):
                        os.unlink(RECEIPT, dir_fd=dirfd)
                except FileNotFoundError:
                    pass
        return root / RECEIPT
    finally:
        os.close(dirfd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_owned_ru_bin", type=Path)
    parser.add_argument("--cue", required=True, type=Path)
    parser.add_argument("--output-private-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = inspect(args.private_owned_ru_bin, args.cue)
        validate_receipt((json.dumps(report, sort_keys=True) + "\n").encode("ascii"))
        receipt = publish(report, args.output_private_dir)
        verify_receipt_file(receipt)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print("Private digest-only receipt created:", receipt.name)


if __name__ == "__main__":
    main()

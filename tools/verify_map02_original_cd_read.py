#!/usr/bin/env python3
"""Compare observed original CdRead/loader CRC32+SHA256 with owned raw US disc.

Runs the independently checked same-process native GPU/PutPixel/BlendG1/VRAM
join AND validates the private 12-sector original CD read against the actual
user-owned disc data. CRC32 detects accidental changes; native raw/returned user bytes now also
carry a SHA-256 digest independently checked against the owned disc.
Never infers retail gameplay authenticity or actual PS1 hardware parity.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zlib
import stat

from tools.check_map02_owned_disc_extent import (
    SECTOR_RAW, USER_DATA_START, USER_DATA_BYTES, _raw_sector,
    _disc_file_identity,
    verify_map02_disc_extent,
)
from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_window_scoped_join import (
    CD_READ, verify_window_scoped_join,
)

LBA = 0x1bcc
COUNT = 12


def _verify_cd_receipt_claims(raw, checked):
    """Independently validate the observed CdRead identity and transfer claims.

    The GPU scoped verifier also checks these fields; this CD verifier must
    reject contradictory receipts even if the upstream scoped result is stale.
    """
    if raw.count(b"\n") != 1 or not raw.endswith(b"\n") or b"\r" in raw:
        raise ValueError("noncanonical original MAP02 CD receipt JSONL")
    event = parse_json(raw[:-1], CD_READ)
    keys = (
        "schema", "capture_session", "source", "cdf", "lba", "sectors",
        "bytes", "raw_user_crc32", "returned_user_crc32",
        "raw_user_sha256", "returned_user_sha256", "loader_completed",
    )
    fields(event, keys, CD_READ)
    if (event["schema"] != "vh.map02.original-cd-read.v2" or
            event["source"] != "original-CdRead-and-ContinueLoadingCdFile" or
            event["cdf"] != "CDF_M_MAP02_PRS" or
            number(event["lba"], "original MAP02 LBA", 0, LBA) != LBA or
            number(event["sectors"], "MAP02 sector count", 1, COUNT) != COUNT or
            number(event["bytes"], "MAP02 user-data size", 1, COUNT * USER_DATA_BYTES)
            != COUNT * USER_DATA_BYTES or
            event["loader_completed"] is not True):
        raise ValueError("original MAP02 CD receipt extent or loader claim differs")
    token = event["capture_session"]
    if (type(token) is not str or len(token) != 32 or
            any(ch not in "0123456789abcdef" for ch in token) or
            hashlib.sha256(token.encode("ascii")).hexdigest()
            != checked["capture_session_sha256"]):
        raise ValueError("original MAP02 CD receipt session differs from GPU witness")
    for key, length in (
        ("raw_user_crc32", 8), ("returned_user_crc32", 8),
        ("raw_user_sha256", 64), ("returned_user_sha256", 64),
    ):
        value = event[key]
        if (type(value) is not str or len(value) != length or
                any(ch not in "0123456789abcdef" for ch in value)):
            raise ValueError("invalid original MAP02 CD checksum encoding")
    if (event["raw_user_crc32"] != event["returned_user_crc32"] or
            event["raw_user_sha256"] != event["returned_user_sha256"]):
        raise ValueError("original MAP02 CD transfer differs from raw sector data")
    return event


def _private_cd_receipt_snapshot(directory):
    """Read the owned CD receipt twice from one 0600 inode and pin its identity.

    A byte-identical replacement file is not the same observed process artifact.
    Keep inode *and* timestamps across the independent disc and GPU audit.
    """
    path = directory / CD_READ
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise ValueError("private MAP02 CD receipt unavailable") from None
    try:
        def identity(st):
            return (st.st_dev, st.st_ino, st.st_uid, st.st_mode,
                    st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

        before = os.fstat(fd)
        prior = identity(before)
        if (not stat.S_ISREG(before.st_mode) or
                before.st_uid != os.geteuid() or before.st_nlink != 1 or
                stat.S_IMODE(before.st_mode) != 0o600 or
                not 0 < before.st_size <= 2048):
            raise ValueError("private MAP02 CD receipt must be a single-link 0600 file")
        first = os.pread(fd, before.st_size, 0)
        second = os.pread(fd, before.st_size, 0)
        if len(first) != before.st_size or first != second:
            raise ValueError("private MAP02 CD receipt changed while reading")
        if (identity(os.fstat(fd)) != prior or
                identity(os.stat(path, follow_symlinks=False)) != prior):
            raise ValueError("private MAP02 CD receipt identity changed while reading")
        return first, prior
    except OSError:
        raise ValueError("private MAP02 CD receipt verification unavailable") from None
    finally:
        os.close(fd)


def verify_map02_original_cd_read(scoped_dir, native_dir, owned_image,
                                   upstream, *, frame):
    checked = verify_window_scoped_join(native_dir, scoped_dir,
                                        target_frame=frame)
    if checked["original_map02_cd_read_receipt_present"] is not True:
        raise ValueError("missing actual original MAP02 CdRead and loader completion")
    scoped = _private_directory(scoped_dir)
    raw, receipt_inode = _private_cd_receipt_snapshot(scoped)
    if checked["original_map02_cd_read_receipt_sha256"] != hashlib.sha256(raw).hexdigest():
        raise ValueError("original MAP02 CD receipt differs from GPU witness digest")
    event = _verify_cd_receipt_claims(raw, checked)
    image = Path(owned_image).absolute()
    # Preserve the SAME original image inode across the two independent
    # full-disc SHA/sector audits and our separate original CdRead CRC read.
    # Equal hashes on replacement pathname inodes are not equivalent input.
    original_inode = _disc_file_identity(os.stat(image, follow_symlinks=False))
    extent = verify_map02_disc_extent(image, upstream)
    if _disc_file_identity(os.stat(image, follow_symlinks=False)) != original_inode:
        raise ValueError("owned MAP02 raw disc identity changed before CdRead comparison")
    if (extent["resource_lba"] != LBA or
            extent["resource_sector_count"] != COUNT):
        raise ValueError("pinned source MAP02 file extent differs")

    # Independent checksum of the same 12 raw CD payload sectors. Source
    # images remain local: do not store, print or upload any raw payload.
    fd = os.open(image, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if _disc_file_identity(os.fstat(fd)) != original_inode:
            raise ValueError("owned MAP02 raw disc inode differs before CdRead comparison")
        crc = 0
        data_sha = hashlib.sha256()
        for lba in range(LBA, LBA + COUNT):
            raw_sector = _raw_sector(fd, lba)
            block = raw_sector[USER_DATA_START:
                               USER_DATA_START + USER_DATA_BYTES]
            crc = zlib.crc32(block, crc)
            data_sha.update(block)
        if (_disc_file_identity(os.fstat(fd)) != original_inode or
                _disc_file_identity(os.stat(image, follow_symlinks=False))
                != original_inode):
            raise ValueError("owned MAP02 raw disc identity changed during CdRead comparison")
    finally:
        os.close(fd)
    if (f"{crc:08x}" != event["raw_user_crc32"] or
            f"{crc:08x}" != event["returned_user_crc32"] or
            extent["resource_user_data_sha256"] != data_sha.hexdigest() or
            event["raw_user_sha256"] != data_sha.hexdigest() or
            event["returned_user_sha256"] != data_sha.hexdigest()):
        raise ValueError("actual original CdRead payload differs from owned MAP02 CD sectors")
    if (verify_map02_disc_extent(image, upstream) != extent or
            _disc_file_identity(os.stat(image, follow_symlinks=False))
            != original_inode):
        raise ValueError("owned MAP02 image changed while verifying actual CdRead")
    final_checked = verify_window_scoped_join(native_dir, scoped_dir,
                                               target_frame=frame)
    if (final_checked != checked or
            _private_cd_receipt_snapshot(scoped) != (raw, receipt_inode)):
        raise ValueError("original CD receipt or GPU capture changed during verification")
    return {
        "original_map02_cd_read_observed": True,
        "original_game_loader_completion_observed": True,
        "original_cd_payload_crc32_matches_owned_image": True,
        "original_cd_payload_sha256_matches_owned_image": True,
        "native_gpu_process_session_sha256": checked["capture_session_sha256"],
        "original_cd_receipt_sha256": checked[
            "original_map02_cd_read_receipt_sha256"],
        "owned_disc_image_sha256": extent["owned_raw_image_sha256"],
        "original_map02_user_data_sha256":
            extent["resource_user_data_sha256"],
        "original_map02_resource_lba": LBA,
        "original_map02_resource_sector_count": COUNT,
        "original_map02_gameplay_frame_authenticated": False,
        "physical_ps1_equivalence_proven": False,
        "raw_game_bytes_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_native_windows", type=Path)
    p.add_argument("private_scoped_capture", type=Path)
    p.add_argument("private_owned_us_disc_bin", type=Path)
    p.add_argument("--upstream-checkout", required=True, type=Path)
    p.add_argument("--frame", required=True, type=int)
    args = p.parse_args()
    try:
        report = verify_map02_original_cd_read(
            args.private_scoped_capture, args.private_native_windows,
            args.private_owned_us_disc_bin, args.upstream_checkout,
            frame=args.frame)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

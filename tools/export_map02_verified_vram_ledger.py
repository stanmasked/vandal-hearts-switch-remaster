#!/usr/bin/env python3
"""Privately export a validated MAP02 GPU transfer ledger for the C renderer.

Requires the full existing timeline + write-ledger verification FIRST. Writes
one binary packet with metadata and optional LoadImage pixel payloads. The
packet therefore CONTAINS game-derived bytes and MUST remain on the owner's
machine; never upload, publish or commit it to GitHub.

Validation proves internal consistency of user-supplied captures with the
pinned PC transfer semantics, NOT authentic gameplay or PS1 GPU accuracy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

from tools.verify_map02_frame_bundle import (
    safe_file_max, sha_check,
)
from tools.verify_map02_gpu_write_ledger import (
    MAX_EVENT_BYTES, load_transfer_events, verify_write_ledger,
)

MAGIC = b"VHMAPGL1"
HEADER = struct.Struct("<8sIIII8s")
RECORD = struct.Struct("<13i")
OPS = {"load": 1, "move": 2, "clear": 3}
MAX_PACKET_BYTES = HEADER.size + 512 * (RECORD.size + 32768)


def pack_verified_events(frame: int, submissions: int, events) -> bytes:
    """Canonical LE v1 format shared with source/map02_vram4_transfer_import.h."""
    if type(frame) is not int or not 1 <= frame <= 0xffffffff:
        raise ValueError("frame outside uint32 range")
    if type(submissions) is not int or not 2 <= submissions <= 32:
        raise ValueError("submission count outside supported range")
    if len(events) > 512:
        raise ValueError("too many GPU transfer events")
    output = bytearray(HEADER.size)
    for index, (event, payload) in enumerate(events):
        op = event["op"]
        x, y, w, h = event["rect"]
        if event["step"] != index or not 1 <= event["before_submission"] < submissions:
            raise ValueError("invalid event order or submission boundary")
        dest_x = dest_y = red = green = blue = 0
        if op == "move":
            dest_x, dest_y = event["dest"]
        elif op == "clear":
            red, green, blue = event["rgb"]
        elif op != "load":
            raise ValueError("unsupported GPU transfer operation")
        if op == "load":
            if type(payload) is not bytes or len(payload) != w * h * 2:
                raise ValueError("incorrect LoadImage payload")
        elif payload is not None:
            raise ValueError("unexpected payload on a non-LoadImage event")
        output.extend(RECORD.pack(
            event["step"], event["before_submission"], OPS[op],
            x, y, w, h, dest_x, dest_y, red, green, blue,
            len(payload) if payload is not None else 0))
        if payload is not None:
            output.extend(payload)
        if len(output) > MAX_PACKET_BYTES:
            raise ValueError("transfer packet exceeds maximum length")
    output[:HEADER.size] = HEADER.pack(
        MAGIC, frame, submissions, len(events), len(output), bytes(8))
    return bytes(output)


def export_verified_ledger(folder: Path, output: Path, *, compiler="gcc"):
    """Verify on the local computer; create an exclusive, private output file."""
    folder = Path(folder).absolute()
    output = Path(output).absolute()
    report = verify_write_ledger(folder, compiler=compiler)
    raw = safe_file_max(folder, "gpu-writes.jsonl", MAX_EVENT_BYTES)
    sha_check(raw, report["gpu_writes_sha256"], "GPU transfer event stream")
    events = load_transfer_events(
        folder, raw, report["submitted_faces_checked"] - 1)
    if len(events) != report["gpu_transfer_events_replayed"]:
        raise ValueError("verified transfer count changed during export")
    packet = pack_verified_events(
        report["frame"], report["submitted_faces_checked"], events)
    if output.is_dir() or not output.parent.is_dir():
        raise ValueError("output parent must be an existing local directory")
    # The packet may contain unredistributable LoadImage bytes. Never
    # write one beneath a Git worktree (including a symlink to one), where
    # an accidental git add could publish private game-derived resources.
    # A worktree may have either a .git directory OR a .git pointer file.
    actual_parent = output.parent.resolve(strict=True)
    if any((parent / ".git").exists() or (parent / ".git").is_symlink()
           for parent in (actual_parent, *actual_parent.parents)):
        raise ValueError("private MAP02 packet output must be outside a Git worktree")
    # O_EXCL rejects replacing files and symlink targets, including a
    # previously exported packet. Exclusive mode 0600 keeps bytes private.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(packet)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {
        "schema": "vh.map02.transfer-packet.v1",
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "frame": report["frame"],
        "submitted_faces_checked": report["submitted_faces_checked"],
        "gpu_transfer_events_replayed": len(events),
        "changed_vram_words_explained": report["changed_vram_words_explained"],
        "private_payload_bytes": len(packet),
        "pc_gameplay_authenticated": False,
        "ps1_hardware_pixels_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path,
                        help="local directory containing verified timeline and ledger")
    parser.add_argument("--output", type=Path, required=True,
                        help="new private output path outside any public repository")
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        result = export_verified_ledger(
            args.directory,args.output,compiler=args.compiler)
    except (OSError,ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

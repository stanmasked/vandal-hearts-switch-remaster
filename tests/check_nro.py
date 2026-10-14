#!/usr/bin/env python3
"""Basic structural sanity check for a packaged Nintendo Switch NRO."""

import pathlib
import struct
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {pathlib.Path(sys.argv[0]).name} PATH_TO_NRO", file=sys.stderr)
        return 2

    path = pathlib.Path(sys.argv[1])
    data = path.read_bytes()
    # The NRO header is preceded by a 0x10-byte startup stub. Its magic is
    # followed by version, declared NRO size, and flags.
    header_offset = 0x10
    size_offset = 0x18
    if len(data) < 0x20:
        print(f"FAIL: {path} is too small to contain an NRO header ({len(data)} bytes)")
        return 1
    if data[header_offset:header_offset + 4] != b"NRO0":
        print(f"FAIL: {path} does not contain NRO0 magic at offset 0x10")
        return 1

    declared_size = struct.unpack_from("<I", data, size_offset)[0]
    if declared_size < 0x20:
        print(f"FAIL: invalid declared NRO size: {declared_size}")
        return 1
    if declared_size > len(data):
        print(
            f"FAIL: header declares {declared_size} bytes but file has only {len(data)}",
        )
        return 1

    print(
        f"PASS: {path} has an NRO0 header; "
        f"declared binary size={declared_size} bytes, file size={len(data)} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

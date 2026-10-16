#!/usr/bin/env python3
"""Write *generated* PS1-format SEQ/VH/VB fixtures to a private NeXium SD tree.

Never reads, copies, uploads, or overwrites original music. The output files
exist only in the caller's isolated CI/emulator data directory.
"""
import argparse
import json
from pathlib import Path

AUDIO_RELATIVE = Path("sdmc/switch/vandal-hearts-remake/audio")
SEQ = bytes([
    0x70, 0x51, 0x45, 0x53, 0, 0, 0, 0,
    0x01, 0xE0, 0x07, 0xA1, 0x20, 0, 0,
    0, 0xC0, 7, 0, 0xB0, 7, 127, 0, 0xB0, 10, 64,
    0, 0x90, 60, 110, 0x81, 0x70, 0x80, 60, 0,
    0x81, 0x70, 0xFF, 0x2F,
])


def make_synthetic_files() -> dict[str, bytes]:
    """Synthetic bank matching the verified tests/test_vh_audio_assets.c map."""
    vh = bytearray(32 + 128 * 16 + 512 + 512)
    vb = bytearray(48)
    vh[:4] = b"pBAV"
    vh[18] = 8
    vh[20] = 1
    vh[22] = 1
    vh[24] = 127
    program = 32 + 7 * 16
    vh[program] = 1
    vh[program + 1] = 127
    vh[program + 4] = 64
    tone = 32 + 128 * 16
    vh[tone + 2] = 127
    vh[tone + 3] = 64
    vh[tone + 4] = 60
    vh[tone + 6] = 40
    vh[tone + 7] = 100
    vh[tone + 16] = 15
    vh[tone + 20] = 7
    vh[tone + 22] = 1
    vh[tone + 512] = 2
    vh[tone + 514] = 4
    vb[16:18] = b"\x02\x04"
    vb[18:32] = b"\x22" * 14
    vb[32:34] = b"\x02\x03"
    vb[34:48] = b"\xEE" * 14
    return {"music.seq": SEQ, "music.vh": bytes(vh), "music.vb": bytes(vb)}


def populate(root: Path, mode: str) -> dict:
    if mode not in ("empty", "full", "partial"):
        raise ValueError("fixture mode must be empty, full or partial")
    if not root.is_dir():
        raise ValueError("existing isolated NeXium root directory required")
    target = root / AUDIO_RELATIVE
    # Reject symlink parents to avoid writing outside the intended directory.
    relative = Path()
    for part in AUDIO_RELATIVE.parts:
        relative /= part
        path = root / relative
        if path.is_symlink():
            raise ValueError("fixture directory contains a symlink")
    target.mkdir(parents=True, exist_ok=True)
    names = [] if mode == "empty" else (["music.seq"] if mode == "partial"
                                         else ["music.seq", "music.vh", "music.vb"])
    contents = make_synthetic_files()
    if any((target / name).exists() for name in contents):
        raise FileExistsError("audio fixture directory already contains a music file")
    for name in names:
        with (target / name).open("xb") as stream:
            stream.write(contents[name])
    return {
        "fixture_mode": mode,
        "synthetic_only": True,
        "files_created": names,
        "expected_audio_source": {
            "empty": "synthetic", "full": "user_files", "partial": "invalid_or_partial",
        }[mode],
        "expected_audout_status": (
            "unavailable_or_error" if mode == "partial" else "initialized"
        ),
        "original_audio_verified": False,
        "audible_audio_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("isolated_nexium_root", type=Path)
    parser.add_argument("--mode", choices=("empty", "full", "partial"), required=True)
    args = parser.parse_args()
    try:
        result = populate(args.isolated_nexium_root, args.mode)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Inspect user-private BizHawk PSX BK2 input without original PS1 game data.

Streams an input movie to a sanitized aggregate JSON report. An explicit,
bounded frame interval may be exported to an owner-local mode-0600 CSV.
No gameplay scene, MAP02 start, PS1 VRAM or GPU frame is inferred.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import stat
import zipfile

MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_INPUT_BYTES = 96 * 1024 * 1024
MAX_FRAMES = 1_500_000
MAX_FRAME_LENGTH = 192
MAX_WINDOW_FRAMES = 24_000
MEMBERS = frozenset((
    "Header.txt", "Input Log.txt", "SyncSettings.json",
    "Comments.txt", "Subtitles.txt",
))
BUTTONS = (
    "Up", "Down", "Left", "Right", "Select", "Start", "Square",
    "Triangle", "Circle", "Cross", "L1", "R1", "L2", "R2",
    "L3", "R3", "MODE",
)
AXES = ("P1 LStick X", "P1 LStick Y", "P1 RStick X", "P1 RStick Y")
SCHEMA = "vh.psx.bizhawk.private-bk2-input-inspection.v1"


def safe_members(archive: zipfile.ZipFile) -> None:
    items = archive.infolist()
    if not items or len(items) > len(MEMBERS):
        raise ValueError("unexpected BK2 member count")
    seen = set()
    for member in items:
        if member.filename not in MEMBERS or member.filename in seen:
            raise ValueError("unexpected or duplicate BK2 entry")
        if member.is_dir() or member.flag_bits & 1:
            raise ValueError("BK2 directory or encrypted member refused")
        mode = member.external_attr >> 16
        if (member.create_system == 3 and mode
                and stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
            raise ValueError("nonregular BK2 member refused")
        bound = MAX_INPUT_BYTES if member.filename == "Input Log.txt" else MAX_METADATA_BYTES
        if member.file_size > bound:
            raise ValueError("BK2 member exceeds bounded size")
        seen.add(member.filename)
    if not {"Header.txt", "Input Log.txt", "SyncSettings.json"}.issubset(seen):
        raise ValueError("required BK2 input/header/sync missing")


def read_small(archive: zipfile.ZipFile, member: str) -> str:
    with archive.open(member) as source:
        data = source.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError("BK2 metadata too large")
    return data.decode("utf-8-sig")


def parse_header(raw: str) -> dict:
    fields = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(" ")
        if not sep or key in fields:
            raise ValueError("malformed BizHawk header")
        fields[key] = value.strip()
    if (fields.get("Platform") != "PSX"
            or fields.get("GameName") != "Vandal Hearts (USA)"
            or fields.get("Core") != "Octoshock"):
        raise ValueError("movie is not Vandal Hearts USA / PSX / Octoshock")
    return fields


def parse_sync(raw: str) -> dict:
    config = json.loads(raw)
    root = config.get("o") if isinstance(config, dict) else None
    fio = root.get("FIOConfig") if isinstance(root, dict) else None
    if not isinstance(fio, dict):
        raise ValueError("Octoshock synchronization settings missing")
    if (fio.get("Devices8") != [2, 0, 0, 0, 0, 0, 0, 0]
            or fio.get("Memcards") != [False, False]
            or fio.get("Multitaps") != [False, False]):
        raise ValueError("movie differs from one-controller/no-card setup")
    return {
        "single_controller": True,
        "memory_cards": False,
        "multitap": False,
    }


def check_logkey(line: bytes) -> None:
    if not line.startswith(b"LogKey:"):
        raise ValueError("BK2 Input Log has no LogKey")
    keys = line[7:].decode("ascii").strip().split("|")
    expected = (
        ["#Disc Select", "Open", "Close", "Reset", "#" + AXES[0]]
        + list(AXES[1:])
        + ["P1 " + button for button in BUTTONS]
        + [""]
    )
    if keys != expected:
        raise ValueError("unexpected controller button order")


def read_frame(line: bytes) -> tuple[tuple[int, ...], frozenset[str]]:
    if (len(line) > MAX_FRAME_LENGTH or not line.startswith(b"|")
            or not line.endswith(b"|")):
        raise ValueError("malformed BK2 frame")
    cells = line.split(b"|")
    if len(cells) != 4 or cells[0] or cells[-1]:
        raise ValueError("BK2 frame cell layout changed")
    if cells[1].strip() != b"1,...":
        raise ValueError("disc/reset/controller change requires playback review")
    items = cells[2].split(b",", 4)
    if len(items) != 5:
        raise ValueError("analog/button arity changed")
    axes = []
    for item in items[:4]:
        value = item.strip()
        if not value.isdigit() or not 0 <= int(value) <= 255:
            raise ValueError("invalid analog input")
        axes.append(int(value))
    digital = items[4]
    if (len(digital) != len(BUTTONS)
            or any(c != 46 and not (33 <= c <= 126 and c not in (44, 124))
                   for c in digital)):
        raise ValueError("invalid button record")
    held = frozenset(name for index, name in enumerate(BUTTONS)
                     if digital[index] != 46)
    return tuple(axes), held


def inspect(movie_path: Path, start: int = 0, length: int = 0,
            event_path: Path | None = None) -> dict:
    movie_path = Path(movie_path)
    if (start < 0 or length < 0
            or (event_path is not None and not 0 < length <= MAX_WINDOW_FRAMES)):
        raise ValueError("local CSV requires bounded 1..24000-frame window")
    if movie_path.is_symlink() or not movie_path.is_file():
        raise ValueError("BK2 input must be a nonsymlinked regular file")
    stat_info = movie_path.stat()
    if not stat.S_ISREG(stat_info.st_mode) or not 0 < stat_info.st_size <= 8 * 1024 * 1024:
        raise ValueError("BK2 archive outside bounded file size")

    with zipfile.ZipFile(movie_path) as archive:
        safe_members(archive)
        header = parse_header(read_small(archive, "Header.txt"))
        controller = parse_sync(read_small(archive, "SyncSettings.json"))
        frame_count = 0
        transitions = 0
        press_count = 0
        active_frames = 0
        analog_frames = 0
        previous = frozenset()
        neutral_start = 0
        longest_neutral = (0, 0)
        by_button: Counter[str] = Counter()
        selected = []
        total_log_bytes = 0
        ended = False
        with archive.open("Input Log.txt") as raw:
            if raw.readline().strip() != b"[Input]":
                raise ValueError("BK2 input block missing")
            check_logkey(raw.readline())
            for raw_line in raw:
                total_log_bytes += len(raw_line)
                if total_log_bytes > MAX_INPUT_BYTES:
                    raise ValueError("input log exceeds expansion cap")
                line = raw_line.rstrip(b"\r\n")
                if line == b"[/Input]":
                    ended = True
                    break
                axes, held = read_frame(line)
                if frame_count >= MAX_FRAMES:
                    raise ValueError("BK2 frame count exceeds limit")
                if start <= frame_count < start + length:
                    if held != previous or frame_count == start:
                        selected.append((
                            frame_count,
                            "+".join(sorted(held - previous)),
                            "+".join(sorted(previous - held)),
                            "+".join(sorted(held)),
                        ))
                if held:
                    active_frames += 1
                    if not previous and frame_count - neutral_start >= longest_neutral[1]:
                        longest_neutral = (neutral_start, frame_count - neutral_start)
                elif previous:
                    neutral_start = frame_count
                if axes != (128, 128, 128, 128):
                    analog_frames += 1
                if held != previous:
                    transitions += 1
                    for button in held - previous:
                        by_button[button] += 1
                        press_count += 1
                previous = held
                frame_count += 1
            if not ended or raw.read(1):
                raise ValueError("BK2 input end marker missing or extra bytes")
        if not frame_count:
            raise ValueError("BK2 input log empty")
        if not previous and frame_count - neutral_start >= longest_neutral[1]:
            longest_neutral = (neutral_start, frame_count - neutral_start)

    if event_path is not None:
        event_path = Path(event_path)
        if event_path.exists() or event_path.is_symlink():
            raise ValueError("will not overwrite private event output")
        if not event_path.parent.is_dir() or event_path.parent.is_symlink():
            raise ValueError("private output must have real parent directory")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(event_path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            csv_file = csv.writer(output)
            csv_file.writerow((
                "frame_zero_based", "buttons_pressed",
                "buttons_released", "held_buttons",
            ))
            csv_file.writerows(selected)
    return {
        "schema": SCHEMA,
        "platform": header["Platform"],
        "game": header["GameName"],
        "core": header["Core"],
        "input_log_frame_count": frame_count,
        "button_state_change_frames": transitions,
        "button_press_onsets": press_count,
        "active_button_frames": active_frames,
        "nonneutral_analog_frames": analog_frames,
        "pressed_button_counts": dict(sorted(by_button.items())),
        "longest_no_button_span": {
            "start_frame": longest_neutral[0], "frames": longest_neutral[1],
        },
        "window": {
            "start_frame": start, "length_requested": length,
            "changes_exported": len(selected),
        },
        "controller_sync": controller,
        "original_ps1_game_image_authenticated": False,
        "map02_scene_frame_identified": False,
        "ps1_gpu_captures_read": False,
        "raw_bk2_uploaded_to_github": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_bk2", type=Path)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--window-frames", type=int, default=0)
    parser.add_argument("--private-events-csv", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(
            args.private_bk2, args.start_frame, args.window_frames,
            args.private_events_csv,
        )
    except (OSError, ValueError, UnicodeError, KeyError, zipfile.BadZipFile):
        # User's BK2 and private filesystem paths must not appear in errors.
        parser.error("private Vandal Hearts PSX BK2 inspection unavailable")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

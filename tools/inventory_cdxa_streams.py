#!/usr/bin/env python3
"""Read-only inventory of CD-XA audio streams in a local raw 2352-byte BIN.

Groups by XA file number and channel. Sector ranges are absolute disc LBAs.
This does not extract, decode, or identify playback timing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.extract_cdxa_payload import SECTOR_SIZE, MODE_OFFSET, SUBHEADER_OFFSET, SYNC


def inventory_streams(source: Path, *, start_lba: int = 0,
                      sector_count: int | None = None) -> dict[str, object]:
    size = source.stat().st_size
    if size == 0 or size % SECTOR_SIZE:
        raise ValueError("source must be a nonempty raw 2352-byte sector BIN")
    total = size // SECTOR_SIZE
    if type(start_lba) is not int or not 0 <= start_lba < total:
        raise ValueError("start LBA is outside source")
    if sector_count is not None and (
        type(sector_count) is not int or sector_count <= 0
        or start_lba + sector_count > total
    ):
        raise ValueError("sector count must be positive and within source")
    scanned = total - start_lba if sector_count is None else sector_count
    streams: dict[tuple[int, int], dict[str, object]] = {}
    skipped_subheaders = 0
    unsupported_coding_sectors = 0
    with source.open("rb") as stream:
        stream.seek(start_lba * SECTOR_SIZE)
        for lba in range(start_lba, start_lba + scanned):
            sector = stream.read(SECTOR_SIZE)
            if len(sector) != SECTOR_SIZE:
                raise ValueError(f"raw BIN truncated at LBA {lba}")
            if sector[:12] != SYNC or sector[MODE_OFFSET] != 2:
                continue
            first = sector[SUBHEADER_OFFSET:SUBHEADER_OFFSET + 4]
            if first != sector[SUBHEADER_OFFSET + 4:SUBHEADER_OFFSET + 8]:
                skipped_subheaders += 1
                continue
            file_no, channel, submode, coding = first
            if not (submode & 0x04 and submode & 0x20):
                continue
            key = (file_no, channel)
            if key not in streams:
                streams[key] = {
                    "file_number": file_no, "channel": channel,
                    "audio_sectors": 0, "first_lba": lba, "last_lba": lba,
                    "contiguous_runs": 0, "max_gap_sectors": 0,
                    "coding_counts": {},
                    "end_of_record_sectors": 0,
                    "end_of_file_sectors": 0,
                }
            item = streams[key]
            gap = lba - item["last_lba"] - 1 if item["audio_sectors"] else 0
            if gap:
                item["max_gap_sectors"] = max(item["max_gap_sectors"], gap)
            if gap or item["audio_sectors"] == 0:
                item["contiguous_runs"] += 1
            item["audio_sectors"] += 1
            item["last_lba"] = lba
            coding_key = f"0x{coding:02X}"
            item["coding_counts"][coding_key] = item["coding_counts"].get(coding_key, 0) + 1
            if coding != 0x01:
                unsupported_coding_sectors += 1
            item["end_of_record_sectors"] += int(bool(submode & 0x01))
            item["end_of_file_sectors"] += int(bool(submode & 0x80))
    ordered = [streams[key] for key in sorted(streams)]
    for item in ordered:
        # The current decoder accepts only coding byte 0x01. A mixed-profile
        # stream must not be auto-selected even when most sectors are valid.
        supported = set(item["coding_counts"]) == {"0x01"}
        item["decoder_profile_supported"] = supported
        item["expected_pcm_frames"] = item["audio_sectors"] * 2016 if supported else None
    return {
        "start_lba": start_lba, "sectors_scanned": scanned,
        "audio_sectors": sum(item["audio_sectors"] for item in ordered),
        "decodable_stream_count": sum(1 for item in ordered if item["decoder_profile_supported"]),
        "decodable_audio_sectors": sum(item["audio_sectors"] for item in ordered
                                      if item["decoder_profile_supported"]),
        "streams": ordered,
        "invalid_duplicate_subheaders": skipped_subheaders,
        "unsupported_coding_sectors": unsupported_coding_sectors,
        "warning": (
            "Stream inventory is metadata-only. Interleaved streams create gaps; "
            "LBA adjacency does not prove playback boundaries or correct audio."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--start-lba", type=int, default=0)
    parser.add_argument("--sector-count", type=int)
    args = parser.parse_args()
    try:
        result = inventory_streams(args.source, start_lba=args.start_lba,
                                   sector_count=args.sector_count)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

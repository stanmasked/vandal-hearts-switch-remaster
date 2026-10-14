#!/usr/bin/env python3
"""Extract CD-XA audio sector payloads from a raw 2352-byte BIN.

This utility is intentionally a payload extractor, not an ADPCM decoder. It
writes the 2304-byte CD-XA sound-group area from Mode 2 Form 2 sectors for sectors whose duplicated subheader
marks them as audio. The report records sector positions and gaps so callers
can assess timing before decoding.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SECTOR_SIZE = 2352
PAYLOAD_START = 24
PAYLOAD_END = 2328  # 2304 bytes of sound groups; exclude 20 trailing padding bytes
MODE_OFFSET = 15
SUBHEADER_OFFSET = 16
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def extract_audio_payloads(
    source: Path,
    destination: Path,
    start_lba: int = 0,
    sector_count: int | None = None,
    channel: int | None = None,
    file_number: int | None = None,
    report_path: Path | None = None,
) -> dict[str, object]:
    size = source.stat().st_size
    if size == 0:
        raise ValueError("Input file is empty.")
    if size % SECTOR_SIZE:
        raise ValueError(f"Input size {size} is not divisible by {SECTOR_SIZE}; expected raw 2352-byte sectors.")
    total = size // SECTOR_SIZE
    if start_lba < 0 or start_lba >= total:
        raise ValueError(f"Start LBA {start_lba} is outside the input ({total} sectors).")
    if sector_count is not None and sector_count <= 0:
        raise ValueError("Sector count must be positive.")
    count = total - start_lba if sector_count is None else sector_count
    if start_lba + count > total:
        raise ValueError(f"Requested sector range ends at {start_lba + count}, beyond input ({total} sectors).")
    if channel is not None and not 0 <= channel <= 255:
        raise ValueError("Channel must be between 0 and 255.")
    if file_number is not None and not 0 <= file_number <= 255:
        raise ValueError("File number must be between 0 and 255.")
    if source.resolve() == destination.resolve():
        raise ValueError("Output must not overwrite the source image.")
    if report_path is not None and report_path.resolve() in {source.resolve(), destination.resolve()}:
        raise ValueError("Report path must differ from source and output paths.")

    audio_lbas: list[int] = []
    selected = mode2 = valid_subheaders = 0
    submodes: dict[int, int] = {}
    coding_info: dict[int, int] = {}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("wb") as out:
        src.seek(start_lba * SECTOR_SIZE)
        for lba in range(start_lba, start_lba + count):
            sector = src.read(SECTOR_SIZE)
            if len(sector) != SECTOR_SIZE:
                raise ValueError(f"Unexpected end of file at LBA {lba}.")
            if sector[MODE_OFFSET] != 2:
                continue
            mode2 += 1
            first = sector[SUBHEADER_OFFSET:SUBHEADER_OFFSET + 4]
            second = sector[SUBHEADER_OFFSET + 4:SUBHEADER_OFFSET + 8]
            if first != second:
                continue
            valid_subheaders += 1
            file_no, channel_no, submode, coding = first
            submodes[submode] = submodes.get(submode, 0) + 1
            if not (submode & 0x04) or not (submode & 0x20):
                continue
            if channel is not None and channel_no != channel:
                continue
            if file_number is not None and file_no != file_number:
                continue
            out.write(sector[PAYLOAD_START:PAYLOAD_END])
            audio_lbas.append(lba)
            coding_info[coding] = coding_info.get(coding, 0) + 1
            selected += 1

    gaps = sum(1 for a, b in zip(audio_lbas, audio_lbas[1:]) if b != a + 1)
    report: dict[str, object] = {
        "source": str(source),
        "output": str(destination),
        "start_lba": start_lba,
        "sectors_scanned": count,
        "mode2_sectors": mode2,
        "matching_subheaders": valid_subheaders,
        "audio_form2_sectors_written": selected,
        "payload_bytes_written": selected * (PAYLOAD_END - PAYLOAD_START),
        "noncontiguous_audio_transitions": gaps,
        "first_audio_lba": audio_lbas[0] if audio_lbas else None,
        "last_audio_lba": audio_lbas[-1] if audio_lbas else None,
        "submode_counts": {f"0x{k:02X}": v for k, v in sorted(submodes.items())},
        "coding_info_counts": {f"0x{k:02X}": v for k, v in sorted(coding_info.items())},
        "warning": "Payload extraction only; not decoded PCM. Removing non-audio sectors may lose timing/gap information.",
    }
    if report_path is not None:
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="raw BIN with 2352-byte sectors")
    parser.add_argument("output", type=Path, help="output payload stream; must not be the input image")
    parser.add_argument("--start-lba", type=int, default=0)
    parser.add_argument("--sector-count", type=int)
    parser.add_argument("--channel", type=int, help="only include this XA channel number")
    parser.add_argument("--file-number", type=int, help="only include this XA file number")
    parser.add_argument("--report", type=Path, help="optional JSON report path")
    args = parser.parse_args()
    try:
        report = extract_audio_payloads(
            args.input, args.output, args.start_lba, args.sector_count,
            args.channel, args.file_number, args.report,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    for key, value in report.items():
        if key not in {"submode_counts", "coding_info_counts", "warning"}:
            print(f"{key}: {value}")
    print(report["warning"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

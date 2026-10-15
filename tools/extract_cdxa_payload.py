#!/usr/bin/env python3
"""Extract CD-XA audio sector payloads from a raw 2352-byte BIN.

This utility is intentionally a payload extractor, not an ADPCM decoder. It
writes the 2304-byte CD-XA sound-group area from Mode 2 Form 2 sectors for sectors whose duplicated subheader
marks them as audio. The report records sector positions and gaps so callers
can assess timing before decoding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
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
    source_resolved = source.resolve()
    destination_resolved = destination.resolve()
    if source_resolved == destination_resolved or (
        destination.exists() and source.exists() and destination.samefile(source)
    ):
        raise ValueError("Output must not overwrite the source image.")
    if report_path is not None:
        report_resolved = report_path.resolve()
        report_aliases_source = report_resolved == source_resolved or (
            report_path.exists() and source.exists() and report_path.samefile(source)
        )
        report_aliases_destination = report_resolved == destination_resolved or (
            report_path.exists() and destination.exists() and report_path.samefile(destination)
        )
        if report_aliases_source or report_aliases_destination:
            raise ValueError("Report path must differ from source and output paths.")

    payload_digest = hashlib.sha256()
    audio_lbas: list[int] = []
    selected = mode2 = valid_subheaders = 0
    submodes: dict[int, int] = {}
    coding_info: dict[int, int] = {}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_payload: Path | None = None
    temp_report: Path | None = None
    previous_payload: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.", suffix=".tmp",
            dir=destination.parent, delete=False,
        ) as staged_payload:
            temp_payload = Path(staged_payload.name)

        with source.open("rb") as src, temp_payload.open("wb") as out:
            src.seek(start_lba * SECTOR_SIZE)
            for lba in range(start_lba, start_lba + count):
                sector = src.read(SECTOR_SIZE)
                if len(sector) != SECTOR_SIZE:
                    raise ValueError(f"Unexpected end of file at LBA {lba}.")
                if sector[:12] != SYNC:
                    continue
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
                audio_groups = sector[PAYLOAD_START:PAYLOAD_END]
                out.write(audio_groups)
                payload_digest.update(audio_groups)
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
            "payload_sha256": payload_digest.hexdigest(),
            "noncontiguous_audio_transitions": gaps,
            "first_audio_lba": audio_lbas[0] if audio_lbas else None,
            "last_audio_lba": audio_lbas[-1] if audio_lbas else None,
            "audio_lbas": audio_lbas,
            "audio_lba_offsets": [
                {
                    "lba": lba,
                    "payload_offset": index * (PAYLOAD_END - PAYLOAD_START),
                    "missing_source_sectors_before": (
                        0 if index == 0 else max(0, lba - audio_lbas[index - 1] - 1)
                    ),
                }
                for index, lba in enumerate(audio_lbas)
            ],
            "submode_counts": {f"0x{k:02X}": v for k, v in sorted(submodes.items())},
            "coding_info_counts": {f"0x{k:02X}": v for k, v in sorted(coding_info.items())},
            "warning": "Payload extraction only; not decoded PCM. Removing non-audio sectors may lose timing/gap information.",
        }

        # Stage the optional report before publishing either output. This keeps
        # extraction/read/report-write failures from exposing a partial payload.
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n",
                prefix=f".{report_path.name}.", suffix=".tmp",
                dir=report_path.parent, delete=False,
            ) as staged_report:
                temp_report = Path(staged_report.name)
                staged_report.write(json.dumps(report, indent=2) + "\n")
                staged_report.flush()
                os.fsync(staged_report.fileno())

        # Reject an existing directory before publishing the payload: replacing
        # the report with a file would fail and leave mismatched outputs.
        if report_path is not None and report_path.is_dir():
            raise IsADirectoryError(f"Report destination is a directory: {report_path}")

        # Preserve the previous payload until the report is published.
        # If publishing the report fails, restore the previous complete payload.
        # This is best-effort rollback, not an atomic two-file transaction.
        if temp_report is not None and destination.exists():
            with tempfile.NamedTemporaryFile(
                prefix=f".{destination.name}.", suffix=".tmp",
                dir=destination.parent, delete=False,
            ) as backup:
                previous_payload = Path(backup.name)
                with destination.open("rb") as existing:
                    shutil.copyfileobj(existing, backup)
                backup.flush()
                os.fsync(backup.fileno())

        os.replace(temp_payload, destination)
        temp_payload = None
        if temp_report is not None and report_path is not None:
            try:
                os.replace(temp_report, report_path)
                temp_report = None
            except OSError:
                if previous_payload is not None:
                    try:
                        os.replace(previous_payload, destination)
                    except OSError as rollback_error:
                        # Do not delete the only remaining copy of the old
                        # payload if restoring it also fails.
                        backup_path = previous_payload
                        previous_payload = None
                        raise OSError(
                            f"Report publication failed, and payload rollback failed. "
                            f"Previous payload preserved at: {backup_path}"
                        ) from rollback_error
                    previous_payload = None
                else:
                    destination.unlink()
                raise
    finally:
        for temporary in (temp_payload, temp_report, previous_payload):
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
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

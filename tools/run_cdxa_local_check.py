#!/usr/bin/env python3
"""Run a local-only CD-XA extract, source verification, decode and WAV comparison.

No game assets are uploaded. The output directory must not already exist.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.compare_cdxa_wavs import compare_wavs, sha256_file
from tools.analyze_cdxa_wav_quality import analyze_wav
from tools.decode_cdxa_adpcm import decode_payload_file
from tools.extract_cdxa_payload import extract_audio_payloads
from tools.validate_cdxa_extraction import validate_extraction


def run_local_check(
    source: Path, output_dir: Path, *, file_number: int, channel: int,
    start_lba: int = 0, sector_count: int | None = None,
    reference_wav: Path | None = None,
    reference_decoder: str | None = None,
    reference_command: str | None = None,
) -> dict[str, object]:
    """Create only new outputs; fail if source and reference cannot be verified."""
    if not source.is_file():
        raise ValueError("source must be an existing raw BIN file")
    if type(file_number) is not int or not 0 <= file_number <= 255:
        raise ValueError("file number must be in 0..255")
    if type(channel) is not int or not 0 <= channel <= 255:
        raise ValueError("channel must be in 0..255")
    if type(start_lba) is not int or start_lba < 0:
        raise ValueError("start LBA must be a nonnegative integer")
    if sector_count is not None and (type(sector_count) is not int or sector_count < 1):
        raise ValueError("sector count must be positive")
    if reference_wav is not None and not reference_wav.is_file():
        raise ValueError("reference WAV must exist before processing")
    for label, value in (("reference decoder", reference_decoder),
                         ("reference command", reference_command)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{label} must be a nonempty string")
    if reference_wav is None and (reference_decoder is not None or reference_command is not None):
        raise ValueError("reference provenance requires --reference-wav")
    # Refuse an existing path, even if it is empty, to avoid overwrites.
    # Also refuse an output path nested inside the input file's parent when
    # it resolves to the input itself; exclusive mkdir is the final guard.
    output_dir.mkdir(parents=True, exist_ok=False)
    payload = output_dir / "audio-groups.bin"
    report = output_dir / "extraction.json"
    decoded = output_dir / "decoded.wav"
    audit_path = output_dir / "audit-result.json"
    try:
        extracted = extract_audio_payloads(
            source, payload, start_lba=start_lba, sector_count=sector_count,
            channel=channel, file_number=file_number, report_path=report,
        )
        validated = validate_extraction(report, payload, source_bin=source)
        decoded_info = decode_payload_file(payload, decoded, extracted_groups=True)
        validate_extraction(report, payload, wav_path=decoded, source_bin=source)
        result: dict[str, object] = {
            "status": "decoded_and_source_verified",
            "file_number": file_number, "channel": channel,
            "scan_start_lba": extracted["start_lba"],
            "sectors_scanned": extracted["sectors_scanned"],
            "selected_lbas": extracted["audio_lbas"],
            "pcm_frames": decoded_info["frames"],
            "payload": str(payload), "report": str(report), "wav": str(decoded),
            "source_verified_sectors": validated["audio_sectors"],
            "source_bin_bytes": source.stat().st_size,
            "source_bin_sha256": sha256_file(source),
            "extraction_report_sha256": sha256_file(report),
            "payload_sha256": extracted["payload_sha256"],
            "decoded_wav_sha256": sha256_file(decoded),
            "pcm_signal_diagnostics": analyze_wav(decoded),
        }
        if reference_wav is not None:
            comparison = compare_wavs(decoded, reference_wav)
            result["comparison"] = comparison
            result["reference_provenance"] = {
                "decoder": reference_decoder,
                "command": reference_command,
                "status": "user_supplied_not_independently_verified",
            }
            if not comparison["exact_match"]:
                result["status"] = "reference_pcm_mismatch"
                audit_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
                raise ValueError(
                    "decoded PCM differs from reference WAV; output files kept for diagnosis: "
                    + str(output_dir)
                )
            result["status"] = "exact_reference_pcm_match"
        audit_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    except Exception:
        # Preserve non-overwritten diagnostics for later inspection. The
        # directory was created exclusively by this invocation.
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="locally owned raw 2352-byte BIN")
    parser.add_argument("output_dir", type=Path, help="new directory for generated files")
    parser.add_argument("--file-number", type=int, required=True)
    parser.add_argument("--channel", type=int, required=True)
    parser.add_argument("--start-lba", type=int, default=0)
    parser.add_argument("--sector-count", type=int)
    parser.add_argument("--reference-wav", type=Path, help="optional WAV from an independently run decoder")
    parser.add_argument("--reference-decoder", help="user-provided reference decoder name and version")
    parser.add_argument("--reference-command", help="user-provided command used to create the WAV")
    args = parser.parse_args()
    try:
        result = run_local_check(
            args.source, args.output_dir, file_number=args.file_number,
            channel=args.channel, start_lba=args.start_lba,
            sector_count=args.sector_count, reference_wav=args.reference_wav,
            reference_decoder=args.reference_decoder, reference_command=args.reference_command,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

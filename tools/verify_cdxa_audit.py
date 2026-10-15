#!/usr/bin/env python3
"""Recheck a saved local CD-XA audit against files without extracting or decoding.

The original raw BIN must be supplied explicitly. For previously compared
WAVs, also supply the original reference file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.compare_cdxa_wavs import compare_wavs, sha256_file
from tools.validate_cdxa_extraction import validate_extraction


def verify_audit(audit_file: Path, source_bin: Path,
                 reference_wav: Path | None = None) -> dict[str, object]:
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    if not isinstance(audit, dict):
        raise ValueError("audit must be a JSON object")
    for key in ("report", "payload", "wav"):
        if not isinstance(audit.get(key), str) or not audit[key]:
            raise ValueError(f"audit missing path: {key}")
    report = Path(audit["report"])
    payload = Path(audit["payload"])
    wav = Path(audit["wav"])
    # Existing local-run paths are often relative to the original working
    # directory; allow a moved audit directory when files sit next to it.
    for key, path in (("report", report), ("payload", payload), ("wav", wav)):
        if not path.is_file():
            alternate = audit_file.parent / path.name
            if not alternate.is_file():
                raise ValueError(f"audit {key} file is unavailable: {path}")
            if key == "report":
                report = alternate
            elif key == "payload":
                payload = alternate
            else:
                wav = alternate

    if type(audit.get("source_bin_bytes")) is not int or source_bin.stat().st_size != audit["source_bin_bytes"]:
        raise ValueError("source BIN byte count differs from saved audit")
    expected = {
        "source_bin_sha256": (sha256_file(source_bin),),
        "payload_sha256": (sha256_file(payload),),
        "decoded_wav_sha256": (sha256_file(wav),),
    }
    for key, (actual,) in expected.items():
        if audit.get(key) != actual:
            raise ValueError(f"{key} differs from saved audit")
    verified = validate_extraction(report, payload, wav_path=wav, source_bin=source_bin)
    if verified["audio_sectors"] != audit.get("source_verified_sectors"):
        raise ValueError("selected sector count differs from saved audit")
    if type(audit.get("pcm_frames")) is not int or audit["pcm_frames"] != verified["pcm_frames"]:
        raise ValueError("PCM frame count differs from saved audit")
    extraction = json.loads(report.read_text(encoding="utf-8"))
    if audit.get("selected_lbas") != extraction.get("audio_lbas"):
        raise ValueError("selected LBAs differ from saved audit")
    streams = extraction.get("file_channel_counts")
    expected_stream = f"{audit.get('file_number')}:{audit.get('channel')}"
    if (type(audit.get("file_number")) is not int
            or type(audit.get("channel")) is not int
            or not isinstance(streams, dict)
            or streams != {expected_stream: verified["audio_sectors"]}):
        raise ValueError("file/channel selection differs from saved audit")
    # File hashes alone do not authenticate an editable audit's verdict.
    # Re-derive it from the exact PCM comparison instead.
    if "comparison" in audit:
        if reference_wav is None:
            raise ValueError("reference WAV required to recheck saved comparison")
        saved = audit["comparison"]
        if not isinstance(saved, dict):
            raise ValueError("invalid saved WAV comparison")
        current = compare_wavs(wav, reference_wav)
        if current != saved:
            raise ValueError("saved WAV comparison differs from current files")
        expected_status = ("exact_reference_pcm_match" if current["exact_match"]
                           else "reference_pcm_mismatch")
        if audit.get("status") != expected_status:
            raise ValueError("saved audit status contradicts WAV comparison")
        provenance = audit.get("reference_provenance")
        if (not isinstance(provenance, dict)
                or provenance.get("status") != "user_supplied_not_independently_verified"):
            raise ValueError("saved reference provenance status is invalid")
    else:
        if reference_wav is not None:
            raise ValueError("audit has no reference comparison to recheck")
        if audit.get("status") != "decoded_and_source_verified":
            raise ValueError("saved audit status contradicts source-only verification")
        if "reference_provenance" in audit:
            raise ValueError("source-only audit cannot claim reference provenance")
    return {
        "status": "audit_files_verified",
        "source_bin_sha256": expected["source_bin_sha256"][0],
        "decoded_wav_sha256": expected["decoded_wav_sha256"][0],
        "reference_comparison_rechecked": "comparison" in audit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_file", type=Path)
    parser.add_argument("--source-bin", type=Path, required=True)
    parser.add_argument("--reference-wav", type=Path)
    args = parser.parse_args()
    try:
        result = verify_audit(args.audit_file, args.source_bin, args.reference_wav)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Recheck a saved local CD-XA audit against files without extraction; optional WAV regeneration verifies the PCM.

The original raw BIN must be supplied explicitly. For previously compared
WAVs, also supply the original reference file.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.compare_cdxa_wavs import compare_wavs, sha256_file
from tools.analyze_cdxa_wav_quality import analyze_wav
from tools.validate_cdxa_extraction import validate_extraction
from tools.decode_cdxa_adpcm import decode_payload_file


def verify_audit(audit_file: Path, source_bin: Path,
                 reference_wav: Path | None = None,
                 redecode: bool = False) -> dict[str, object]:
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    if not isinstance(audit, dict):
        raise ValueError("audit must be a JSON object")
    for key in ("report", "payload", "wav"):
        if not isinstance(audit.get(key), str) or not audit[key]:
            raise ValueError(f"audit missing path: {key}")
    # The runner creates all three artefacts alongside audit-result.json.
    # Audit JSON is user-editable, so do not follow arbitrary paths or links
    # embedded in it. Standard basenames also support a moved audit folder.
    directory = audit_file.resolve().parent
    expected_names = {
        "report": "extraction.json",
        "payload": "audio-groups.bin",
        "wav": "decoded.wav",
    }
    local_files = {}
    for key, name in expected_names.items():
        recorded = Path(audit[key])
        if recorded.name != name:
            raise ValueError(f"audit {key} path has unexpected filename")
        target = directory / name
        if target.is_symlink() or not target.is_file() or target.resolve().parent != directory:
            raise ValueError(f"audit {key} must be a regular file in audit directory")
        local_files[key] = target
    report = local_files["report"]
    payload = local_files["payload"]
    wav = local_files["wav"]

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
    # Recalculate all saved signal statistics, not just file fingerprints.
    # A valid unchanged WAV must not make a tampered diagnostic credible.
    if audit.get("pcm_signal_diagnostics") != analyze_wav(wav):
        raise ValueError("saved PCM signal diagnostics differ from decoded WAV")
    extraction = json.loads(report.read_text(encoding="utf-8"))
    if (type(audit.get("scan_start_lba")) is not int
            or audit["scan_start_lba"] != extraction.get("start_lba")
            or type(audit.get("sectors_scanned")) is not int
            or audit["sectors_scanned"] != extraction.get("sectors_scanned")):
        raise ValueError("scanned LBA range differs from saved audit")
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
    if redecode:
        # Leave the original audit files intact; decoded output is temporary.
        with tempfile.TemporaryDirectory(prefix="xa-audit-redecode-") as directory:
            regenerated = Path(directory) / "regenerated.wav"
            decoded = decode_payload_file(payload, regenerated, extracted_groups=True)
            if decoded["frames"] != verified["pcm_frames"]:
                raise ValueError("redecoded XA frame count differs from extraction report")
            if not compare_wavs(regenerated, wav)["exact_match"]:
                raise ValueError("saved WAV PCM differs from redecoded XA payload")
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
        "payload_redecoded": redecode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_file", type=Path)
    parser.add_argument("--source-bin", type=Path, required=True)
    parser.add_argument("--reference-wav", type=Path)
    parser.add_argument("--redecode", action="store_true", help="verify WAV by redecoding payload into temporary storage")
    args = parser.parse_args()
    try:
        result = verify_audit(args.audit_file, args.source_bin, args.reference_wav, args.redecode)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

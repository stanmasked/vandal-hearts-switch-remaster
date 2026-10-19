"""Cross-check a local native MAP02 capture against the pre-launch fingerprint.

This validates saved hashes, GPU VRAM and DDA identities; it cannot prove
which executable actually ran or authenticate retail MAP02 resources.
Do not upload a private capture directory to GitHub.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.preflight_map02_private_dda_capture import _executable_fingerprint
from tools.audit_map02_independent_dda_journals import audit

PREFLIGHT_FIELDS = frozenset((
    "schema", "capture_frame", "private_empty_directory",
    "gpu_and_dda_directory_match", "gpu_and_pixel_frame_match",
    "sample_coordinate_in_vram", "executable_fingerprinted",
    "executable_sha256", "executable_bytes", "binary_instrumentation_verified",
    "gameplay_capture_verified", "hd_replacement_authorized",
))


def _unique_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate preflight field")
        result[key] = value
    return result


def verify_session(directory, *, native_frame, preflight_report, executable):
    """Check immutable evidence relationships; never launch or modify binary."""
    if type(native_frame) is not int or not 1 <= native_frame <= 0xffffffff:
        raise ValueError("invalid target GPU frame")
    report_path = Path(preflight_report)
    if report_path.is_symlink() or not report_path.is_file():
        raise ValueError("preflight report is missing or a symlink")
    raw = report_path.read_bytes()
    if not raw or len(raw) > 4096 or b"\x00" in raw:
        raise ValueError("invalid preflight report size")
    try:
        report = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                ValueError("nonfinite preflight number")))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("malformed preflight report") from exc
    if type(report) is not dict or report.keys() != PREFLIGHT_FIELDS:
        raise ValueError("wrong preflight report schema")
    if report["schema"] != "map02_private_native_dda_preflight_v1":
        raise ValueError("unrecognized preflight version")
    for name in ("private_empty_directory", "gpu_and_dda_directory_match",
                 "gpu_and_pixel_frame_match", "sample_coordinate_in_vram",
                 "executable_fingerprinted"):
        if report[name] is not True:
            raise ValueError("preflight readiness is absent")
    for name in ("binary_instrumentation_verified", "gameplay_capture_verified",
                 "hd_replacement_authorized"):
        if report[name] is not False:
            raise ValueError("preflight falsely claims verified game provenance")
    if type(report["capture_frame"]) is not int or report["capture_frame"] != native_frame:
        raise ValueError("preflight and native GPU frame disagree")
    hash_value = report["executable_sha256"]
    if (type(hash_value) is not str or len(hash_value) != 64
            or any(ch not in "0123456789abcdef" for ch in hash_value)
            or type(report["executable_bytes"]) is not int
            or report["executable_bytes"] <= 0):
        raise ValueError("preflight executable fingerprint absent or malformed")
    fingerprint = _executable_fingerprint(executable)
    if (hash_value != fingerprint["executable_sha256"]
            or report["executable_bytes"] != fingerprint["executable_bytes"]):
        raise ValueError("capture executable changed since private preflight")
    checked = audit(directory, native_frame=native_frame)
    return {
        "schema": "map02_private_capture_session_check_v1",
        "frame": native_frame,
        "preflight_report_sha256": hashlib.sha256(raw).hexdigest(),
        "executable_sha256": hash_value,
        "executable_bytes": fingerprint["executable_bytes"],
        "native_gpu_binding": checked["native_gpu_binding"],
        "dda_journal_fingerprints": checked["files"],
        "dda_observation_mode": checked["dda_observation_mode"],
        "all_dda_journal_classes_observed": checked["all_dda_journal_classes_observed"],
        "vram_snapshot_sha256_list_sha256":
            checked["native_gpu_binding"]["vram_snapshot_sha256_list_sha256"],
        "upload_payload_sha256_list_sha256":
            checked["native_gpu_binding"]["upload_payload_sha256_list_sha256"],
        "load_pairs_with_verified_payload":
            checked["native_gpu_binding"]["load_pairs_with_verified_payload"],
        "load_pairs_with_verified_vram_effect":
            checked["native_gpu_binding"]["load_pairs_with_verified_vram_effect"],
        "load_pairs_without_payload":
            checked["native_gpu_binding"]["load_pairs_without_payload"],
        "native_gpu_pairs_verified":
            checked["native_gpu_binding"]["native_gpu_pairs_verified"],
        "draw_boundary_vram_checks":
            checked["native_gpu_binding"]["draw_boundary_vram_checks"],
        "draw_boundary_gpu_state_checks":
            checked["native_gpu_binding"]["draw_boundary_gpu_state_checks"],
        "move_pairs_with_verified_vram_effect":
            checked["native_gpu_binding"]["move_pairs_with_verified_vram_effect"],
        "clear_pairs_with_verified_vram_effect":
            checked["native_gpu_binding"]["clear_pairs_with_verified_vram_effect"],
        "single_sample_envelope_consistent": checked["single_sample_envelope_consistent"],
        "executable_bytes_match_preflight": True,
        "executable_actually_launched_verified": False,
        "binary_instrumentation_verified": False,
        "retail_map02_frame_verified": False,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_capture_directory", type=Path)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_session(args.private_capture_directory,
                                native_frame=args.frame,
                                preflight_report=args.preflight_report,
                                executable=args.executable)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Recheck an unsigned physical-AV pixel report against its exact PNG bytes.

The match proves only that stored text agrees with the provided PNGs
and the current pixel reader. It is NOT a device or sound attestation.
"""
import argparse
import hmac
import json
import re
from pathlib import Path

from inspect_native_av_physical_screenshots import inspect


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate report JSON member: " + key)
        result[key] = value
    return result


def reject_nonfinite(number):
    raise ValueError("non-finite JSON number rejected: " + number)


def canonical(value):
    # Serialized comparison is type-aware: True must not equal JSON 1.
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def verify(report_path, before_path, after_path, *,
           require_focus_pixels=False, require_x_return_pixels=False,
           require_y_return_pixels=False, nro_path=None,
           expected_nro_sha256=None):
    # A digest supplied separately from the report can cross-check a
    # published build fingerprint. Never derive it from the same report.
    if expected_nro_sha256 is not None:
        if nro_path is None:
            raise ValueError("independent NRO SHA-256 requires --nro")
        if (not isinstance(expected_nro_sha256, str) or
                re.fullmatch(r"[0-9a-fA-F]{64}", expected_nro_sha256) is None):
            raise ValueError("expected NRO SHA-256 must be 64 hexadecimal characters")
    stored = json.loads(Path(report_path).read_text(encoding="utf-8"),
                        object_pairs_hook=unique_json_object,
                        parse_constant=reject_nonfinite)
    if type(stored) is not dict:
        raise ValueError("pixel report must be a JSON object")
    expected_format = ("vh-av-physical-screenshot-pixel-observation-v3"
                       if nro_path is not None else
                       "vh-av-physical-screenshot-pixel-observation-v2")
    if stored.get("format") != expected_format:
        raise ValueError("pixel report format does not match requested NRO binding")
    observed = inspect(before_path, after_path, bind_png_hashes=True,
                       nro_path=nro_path)
    if stored.keys() != observed.keys() or canonical(stored) != canonical(observed):
        raise ValueError("pixel report does not match exact PNG bytes and observations")
    if (expected_nro_sha256 is not None and
            not hmac.compare_digest(observed["source_nro_sha256"],
                                    expected_nro_sha256.lower())):
        raise ValueError("NRO SHA-256 does not match independent expected digest")
    # A structurally correct report is not automatically evidence of an
    # operator-requested event. Assert that specific pixel gate afresh.
    gates = observed["difference"]
    for required, field in (
        (require_focus_pixels, "new_focus_cycle_pixels"),
        (require_x_return_pixels, "new_x_return_pixels"),
        (require_y_return_pixels, "new_y_return_pixels"),
    ):
        if required and gates[field] is not True:
            raise ValueError("required reverified screenshot condition not observed: " + field)
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--require-focus-pixels", action="store_true",
                        help="require recomputed Background/Foreground/PCM pixel cycle")
    parser.add_argument("--require-x-return-pixels", action="store_true",
                        help="require a recomputed yellow-to-blue X marker transition")
    parser.add_argument("--require-y-return-pixels", action="store_true",
                        help="require a recomputed yellow-to-blue Y marker transition")
    parser.add_argument("--nro", type=Path,
                        help="require the original diagnostic NRO bound into the v3 report")
    parser.add_argument("--expected-nro-sha256",
                        help="independent 64-hex digest from a separately obtained build manifest (requires --nro)")
    args = parser.parse_args()
    try:
        report = verify(
            args.report, args.before, args.after,
            require_focus_pixels=args.require_focus_pixels,
            require_x_return_pixels=args.require_x_return_pixels,
            require_y_return_pixels=args.require_y_return_pixels,
            nro_path=args.nro,
            expected_nro_sha256=args.expected_nro_sha256)
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "verification": "recomputed_png_pixel_report_match",
        "source_png_sha256": report["source_png_sha256"],
        "source_nro_sha256": report.get("source_nro_sha256"),
        "independent_nro_digest_matched": args.expected_nro_sha256 is not None,
        "required_pixel_conditions_reverified": [
            name for required, name in (
                (args.require_focus_pixels, "new_focus_cycle_pixels"),
                (args.require_x_return_pixels, "new_x_return_pixels"),
                (args.require_y_return_pixels, "new_y_return_pixels"),
            ) if required
        ],
        "physical_hardware_verified": False,
        "home_event_verified": False,
        "audible_audio_verified": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Recheck an unsigned physical-AV pixel report against its exact PNG bytes.

The match proves only that stored text agrees with the provided PNGs
and the current pixel reader. It is NOT a device or sound attestation.
"""
import argparse
import json
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
           require_y_return_pixels=False):
    stored = json.loads(Path(report_path).read_text(encoding="utf-8"),
                        object_pairs_hook=unique_json_object,
                        parse_constant=reject_nonfinite)
    if type(stored) is not dict:
        raise ValueError("pixel report must be a JSON object")
    if stored.get("format") != "vh-av-physical-screenshot-pixel-observation-v2":
        raise ValueError("pixel report must be an unsigned v2 PNG-bound report")
    observed = inspect(before_path, after_path, bind_png_hashes=True)
    if stored.keys() != observed.keys() or canonical(stored) != canonical(observed):
        raise ValueError("pixel report does not match exact PNG bytes and observations")
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
    args = parser.parse_args()
    try:
        report = verify(
            args.report, args.before, args.after,
            require_focus_pixels=args.require_focus_pixels,
            require_x_return_pixels=args.require_x_return_pixels,
            require_y_return_pixels=args.require_y_return_pixels)
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "verification": "recomputed_png_pixel_report_match",
        "source_png_sha256": report["source_png_sha256"],
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

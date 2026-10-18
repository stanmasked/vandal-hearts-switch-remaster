#!/usr/bin/env python3
"""Read, not attest, physical-Switch AV diagnostic framebuffer pixels.

Only accepts unscaled 1280x720 PNGs. This does not prove that a
screenshot came from a physical Switch, that HOME was pressed, that
audout resumed, or that audio could be heard.
"""
import argparse
import json
from pathlib import Path

from PIL import Image

WIDTH, HEIGHT = 1280, 720
BLUE = (86, 190, 244)
YELLOW = (255, 219, 102)
RED = (250, 108, 90)
BACKGROUND = (17, 23, 39)
TOLERANCE = 25
LABELS = ("N", "B", "F", "P", "R")


def near(a, b):
    return max(abs(x-y) for x, y in zip(a, b)) <= TOLERANCE


def marker_color(pixel):
    if near(pixel, BLUE):
        return "blue"
    if near(pixel, YELLOW):
        return "yellow"
    if near(pixel, RED):
        return "red"
    if near(pixel, BACKGROUND):
        return "not_present"
    return "unknown"


def load_frame(path):
    with Image.open(path) as source:
        if source.format != "PNG" or source.size != (WIDTH, HEIGHT):
            raise ValueError("expected an unscaled 1280x720 PNG diagnostic frame")
        if source.mode not in ("RGB", "RGBA"):
            raise ValueError("expected an RGB/RGBA PNG diagnostic frame")
        return source.convert("RGB")


def observe_frame(frame):
    states = {
        label: marker_color(frame.getpixel((1020 + i*48, 645)))
        for i, label in enumerate(LABELS)
    }
    # All five focus indicators are always rendered by both diagnostic
    # NROs. Missing/unknown core tiles cannot be silently interpreted as
    # a valid baseline, even if both manual X/Y tiles are absent.
    if states["N"] not in ("blue", "red"):
        raise ValueError("missing or ambiguous N notification indicator")
    for label in ("B", "F", "P", "R"):
        if states[label] not in ("blue", "yellow"):
            raise ValueError("missing or ambiguous " + label + " focus indicator")
    states["X"] = marker_color(frame.getpixel((1125, 702)))
    states["Y"] = marker_color(frame.getpixel((1180, 702)))
    # The focus observer has no X/Y tiles. The manual NRO MUST have
    # both. Pixel-only inspection does not prove either came from HW,
    # but mixed/missing tiles cannot be treated as one continuous run.
    manual_colors = ("blue", "yellow", "red")
    if states["X"] == states["Y"] == "not_present":
        variant = "focus"
    elif states["X"] in manual_colors and states["Y"] in manual_colors:
        variant = "focus_manual"
    else:
        raise ValueError("incomplete or ambiguous X/Y diagnostic variant")
    tallies = {}
    for tile, label in ((1, "B"), (2, "F"), (4, "R")):
        strokes = []
        for n in range(5):
            pixel=frame.getpixel((1005+tile*48+n*7, 671))
            if near(pixel, BLUE):
                strokes.append(True)
            elif near(pixel, BACKGROUND):
                strokes.append(False)
            else:
                raise ValueError("ambiguous " + label + " tally stroke")
        if strokes != ([True] * sum(strokes) + [False] * (5-sum(strokes))):
            raise ValueError("non-contiguous " + label + " event strokes")
        tallies[label] = sum(strokes)
        if states[label] == "blue" and not tallies[label]:
            raise ValueError(label + " is blue without any event strokes")
        if states[label] == "yellow" and tallies[label]:
            raise ValueError(label + " is yellow despite event strokes")
    # A paired foreground return cannot outnumber backgrounds in the
    # instrumented focus state machine. For saturated counts (5 means
    # 5+), the precise order is unknown and this check is inconclusive.
    if tallies["B"] < 5 and tallies["F"] > tallies["B"]:
        raise ValueError("foreground tally exceeds background tally")
    if states["P"] == "blue" and (
        states["B"] != "blue" or states["F"] != "blue"
    ):
        raise ValueError("post-return PCM marker has no B/F pair")
    return {
        "variant_pixels": variant,
        "indicators": states,
        "tallies_capped_at_five": tallies,
    }


def comparison(before, after):
    if before["variant_pixels"] != after["variant_pixels"]:
        raise ValueError("cannot compare different focus NRO variants")
    a, b = before["tallies_capped_at_five"], after["tallies_capped_at_five"]
    for label in ("B", "F", "R"):
        if b[label] < a[label]:
            raise ValueError(label + " tally decreased between sequential frames")
    increment = {
        label: ("observed" if b[label] > a[label]
                else "saturated_or_unchanged" if a[label] == 5
                else "not_observed")
        for label in ("B", "F", "R")
    }
    return {
        "increment": increment,
        "new_focus_cycle_pixels": (
            before["indicators"]["N"] == "blue" and
            after["indicators"]["N"] == "blue" and
            increment["B"] == "observed" and
            increment["F"] == "observed" and
            after["indicators"]["P"] == "blue"
        ),
        # Manual worker failures are sticky for the lifetime of the
        # diagnostic NRO. Red -> blue would require a new session or
        # impossible state transition, not a recovered X/Y trial.
        "new_x_return_pixels": (
            before["indicators"]["X"] == "yellow" and
            after["indicators"]["X"] == "blue"),
        "new_y_return_pixels": (
            before["indicators"]["Y"] == "yellow" and
            after["indicators"]["Y"] == "blue"),
    }


def inspect(before_path, after_path):
    before = observe_frame(load_frame(before_path))
    after = observe_frame(load_frame(after_path))
    return {
        "format": "vh-av-physical-screenshot-pixel-observation-v1",
        "before": before,
        "after": after,
        "difference": comparison(before, after),
        "physical_hardware_verified": False,
        "home_event_verified": False,
        "audible_audio_verified": False,
        "note": "Pixel interpretation only; user must independently record physical actions and listening results",
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before",type=Path)
    parser.add_argument("after",type=Path)
    parser.add_argument("--require-focus-pixels",action="store_true",
                        help="require changed B/F tally plus latest P blue")
    parser.add_argument("--require-x-return-pixels",action="store_true")
    parser.add_argument("--require-y-return-pixels",action="store_true")
    args=parser.parse_args()
    try:
        result=inspect(args.before,args.after)
        diff=result["difference"]
        for required,field in (
            (args.require_focus_pixels,"new_focus_cycle_pixels"),
            (args.require_x_return_pixels,"new_x_return_pixels"),
            (args.require_y_return_pixels,"new_y_return_pixels"),
        ):
            if required and not diff[field]:
                raise ValueError("required screenshot condition not observed: "+field)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))


if __name__=="__main__":
    main()

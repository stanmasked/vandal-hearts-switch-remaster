#!/usr/bin/env python3
"""Check two emulator screenshots of the independent native AV NRO.

This checks graphics and animation only. A green audout status is a
synchronous initialization/worker indicator, never proof of heard audio.
"""
import argparse
import json
from pathlib import Path
from PIL import Image

WIDTH, HEIGHT = 1280, 720
HERO = (86, 190, 244)
AUDIO_OK = (60, 211, 138)
AUDIO_FAIL = (250, 108, 90)


def near(color, expected, tolerance=25):
    return max(abs(a-b) for a,b in zip(color, expected)) <= tolerance


def inspect_zr_marker(image: Image.Image) -> str:
    """CI-only returned-PCM witness; deliberately not an audio claim."""
    zr_pixel=image.convert('RGB').getpixel((1050, 455))
    zr_red,zr_green,zr_blue=zr_pixel
    if near(zr_pixel,AUDIO_OK) or (
        zr_green>=155 and zr_green>zr_red+70 and zr_green>zr_blue+40
    ):
        zr_recovery="confirmed"
    elif near(zr_pixel,AUDIO_FAIL) or (
        zr_red>=145 and zr_red>zr_green+40 and zr_red>zr_blue+40
    ):
        zr_recovery="error"
    elif zr_red>180 and zr_green>150 and zr_blue<160 and zr_red>zr_blue+70:
        zr_recovery="pending"
    else:
        zr_recovery="not_observed"
    return zr_recovery


def inspect_images(first: Image.Image, second: Image.Image) -> dict:
    first = first.convert("RGB")
    second = second.convert("RGB")
    if first.size != (WIDTH, HEIGHT) or second.size != (WIDTH, HEIGHT):
        raise ValueError("unexpected emulator screenshot dimensions")
    center = first.getpixel((452, 296))
    if not near(center, HERO):
        raise ValueError(f"hero marker absent at expected grid coordinate: {center}")
    # Audio status moved to the right of NeXium's top-left OSD.
    # Guest content is vertically scaled into the 694-pixel viewport.
    audio_sample = first.getpixel((1050, 160))
    red, green, blue = audio_sample
    # Some emulator capture paths transform the blue component of the
    # libnx RGBA8 status fill (one observed green pixel was 60,212,91).
    # Recognize the intended green-vs-red signal by channel dominance,
    # without accepting dark backgrounds, grayscale, or arbitrary colors.
    green_signal = (green >= 155 and green > red + 70
                    and green > blue + 40)
    red_signal = (red >= 145 and red > green + 40
                  and red > blue + 40)
    status = ("initialized" if green_signal else
              "unavailable_or_error" if red_signal else "unknown")
    if status == "unknown":
        raise ValueError(f"audio-service status marker absent: {audio_sample}")

    # Dedicated SEQ/VH/VB source marker, outside the NeXium OSD.
    # The recorded fixture frame in CI previously sampled (83,100,119)
    # here; unlike audout status this says WHERE the content came from.
    source_pixel = first.getpixel((1050, 218))
    sr, sg, sb = source_pixel
    if near(source_pixel, AUDIO_OK) or (sg > sr + 70 and sg > sb + 40):
        source = "user_files"
    elif near(source_pixel, AUDIO_FAIL) or (sr >= 145 and sr > sg + 40
                                            and sr > sb + 40):
        source = "invalid_or_partial"
    elif sr > 180 and sg > 150 and sb < 160 and sr > sb + 70:
        source = "sd_unavailable"
    elif near(source_pixel, (83, 100, 119), tolerance=30):
        source = "synthetic"
    else:
        raise ValueError(f"audio-source status marker absent: {source_pixel}")

    # Runtime-generated PCM and audout return progress, represented by a
    # different guest rectangle from the simple service startup marker.
    # Green means >=16 DSP blocks AND >=16 completed audout buffers;
    # amber is a potential stalled device, red is unavailable/error.
    progress_pixel = first.getpixel((1050, 280))
    pr, pg, pb = progress_pixel
    if near(progress_pixel, AUDIO_OK) or (
        pg >= 155 and pg > pr + 70 and pg > pb + 40
    ):
        pipeline = "buffers_returned"
    elif near(progress_pixel, AUDIO_FAIL) or (
        pr >= 145 and pr > pg + 40 and pr > pb + 40
    ):
        pipeline = "inactive_or_error"
    elif pr > 180 and pg > 150 and pb < 160 and pr > pb + 70:
        pipeline = "not_yet_confirmed"
    else:
        raise ValueError(f"audio pipeline status marker absent: {progress_pixel}")

    # Fourth indicator: synthetic cue transition progress. It proves only
    # that the guest audio worker executed transactional SEQ switches.
    # Test fixtures from older revisions may have no indicator at all.
    switch_pixel = first.getpixel((1050, 322))
    tr, tg, tb = switch_pixel
    if near(switch_pixel, AUDIO_OK) or (tg >= 155 and tg > tr + 70
                                        and tg > tb + 40):
        synthetic_switches = "confirmed"
    elif tr > 180 and tg > 150 and tb < 160 and tr > tb + 70:
        synthetic_switches = "pending"
    elif near(switch_pixel, AUDIO_FAIL) or (
            tr >= 145 and tr > tg + 40 and tr > tb + 40):
        synthetic_switches = "error"
    elif near(switch_pixel, (83, 100, 119), tolerance=30):
        synthetic_switches = "not_applicable"
    else:
        synthetic_switches = "not_observed"

    # FIFTH indicator is present ONLY in the separate CI-compiled ZR
    # auto-injection NRO, not in the standard user-facing AV NRO.
    # A confirmed green tile can only be published by the guest worker
    # after an actual audout descriptor return, a virtual pre-service
    # failure, and the SAME PCM/musical state surviving a restart.
    # The indicator is a guest-software witness, NOT an audio recording.
    zr_recovery=inspect_zr_marker(first)

    # Sample only the heartbeat; animated bar is separate from the cursor,
    # so its change demonstrates video-loop progress without emulated input.
    # Native framebuffer y=610 maps to about y=588 in a 1280x694
    # guest viewport above NeXium's bottom 26-pixel status bar.
    # Use a bounded band away from the tile grid and emulator OSD.
    before = first.crop((70, 565, 870, 640))
    after = second.crop((70, 565, 870, 640))
    changed = sum(1 for a,b in zip(before.getdata(), after.getdata())
                  if max(abs(x-y) for x,y in zip(a,b)) > 20)
    if changed < 16:
        raise ValueError(f"framebuffer heartbeat did not advance: changed={changed}")
    return {
        "video_framebuffer": "observed",
        "grid_hero_marker": "observed",
        "heartbeat_changed_pixels": changed,
        "audout_status": status,
        "audio_source": source,
        "audio_pipeline_progress": pipeline,
        "synthetic_scene_switches": synthetic_switches,
        "guest_zr_recovery": zr_recovery,
        "guest_zr_is_not_physical_button": True,
        "user_music_identity_verified": False,
        "audible_audio_verified": False,
        "actual_gameplay_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--require-synthetic-source", action="store_true",
                        help="legacy empty SD fixture check")
    parser.add_argument("--require-audio-source",
                        choices=("synthetic", "user_files", "invalid_or_partial",
                                 "sd_unavailable"),
                        help="require evidence of this exact guest SD loading outcome")
    parser.add_argument("--require-audout-status",
                        choices=("initialized", "unavailable_or_error"),
                        help="require this exact audout service status")
    parser.add_argument("--require-audio-pipeline",
                        choices=("buffers_returned", "inactive_or_error",
                                 "not_yet_confirmed"),
                        help="require worker DSP + audout returned-buffer evidence")
    parser.add_argument("--require-synthetic-scene-switches",
                        action="store_true",
                        help="require two completed synthetic SEQ transitions")
    parser.add_argument("--require-guest-zr-recovery", action="store_true",
                        help="require CI-only guest auto-ZR returned-PCM witness")
    parser.add_argument("--require-no-synthetic-switches",
                        action="store_true",
                        help="require neutral scene indicator for user-owned music")
    args = parser.parse_args()
    try:
        with Image.open(args.before) as first, Image.open(args.after) as second:
            report = inspect_images(first, second)
        expected_source = ("synthetic" if args.require_synthetic_source
                           else args.require_audio_source)
        if expected_source and report["audio_source"] != expected_source:
            raise ValueError("expected audio source " + expected_source
                             + ", got " + report["audio_source"])
        if (args.require_audout_status
                and report["audout_status"] != args.require_audout_status):
            raise ValueError("expected audout status "
                             + args.require_audout_status + ", got "
                             + report["audout_status"])
        if (args.require_audio_pipeline
                and report["audio_pipeline_progress"] != args.require_audio_pipeline):
            raise ValueError("expected audio pipeline "
                             + args.require_audio_pipeline + ", got "
                             + report["audio_pipeline_progress"])
        if (args.require_synthetic_scene_switches
                and report["synthetic_scene_switches"] != "confirmed"):
            raise ValueError("synthetic scene-switch marker not confirmed: "
                             + report["synthetic_scene_switches"])
        if (args.require_no_synthetic_switches
                and report["synthetic_scene_switches"] != "not_applicable"):
            raise ValueError("unexpected synthetic scene-switch indicator: "
                             + report["synthetic_scene_switches"])
        if args.require_guest_zr_recovery:
            with Image.open(args.after) as image_after:
                after_zr = inspect_zr_marker(image_after)
            if (report["guest_zr_recovery"] != "confirmed" or
                    after_zr != "confirmed" or
                    report["audio_pipeline_progress"] != "buffers_returned" or
                    report["audio_source"] != "synthetic"):
                raise ValueError("guest ZR recovery not confirmed on both frames")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

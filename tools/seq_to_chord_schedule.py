#!/usr/bin/env python3
"""Convert a local Sony PS1 SEQ into the bounded dry stereo-chord voice format.

This conversion models PC-port channel program/volume/pan state at NOTE ON,
NOTE OFF, retriggers and all-sounds-off. It is not a faithful runtime
sequencer: no real-time voice stealing, reverb, CC dynamics on held voices,
repeat playback or block-quantized audio scheduling.

Input SEQ and output JSON remain local; the output is never overwritten.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.inspect_ps1_seq import MAX_SEQ_BYTES, parse_seq
from tools.mix_spu_stereo import MAX_FRAMES, MAX_VOICES


def seq_to_schedule(report: dict[str, object], *, release_frames: int = 4410
                    ) -> dict[str, object]:
    """Return {"voices": [...]} accepted by render_vab_chord.py.

    Each event's frame is a floor of its exact tempo-integrated position.
    In this simplified offline converter, same-frame NoteOn/NoteOff
    becomes a one-output-frame hold (instead of a zero-length voice).
    """
    if type(release_frames) is not int or not 0 <= release_frames <= 44100:
        raise ValueError("release_frames must be an integer in 0..44100")
    if report.get("format") != "PS1 SEQ":
        raise ValueError("requires a validated PS1 SEQ report")
    states = [
        {"program": 0, "volume": 127, "pan": 64}
        for _ in range(16)
    ]
    playing: dict[tuple[int, int], dict[str, int]] = {}
    scheduled: list[dict[str, int]] = []

    def release(channel: int, note: int, frame: int) -> None:
        candidate = playing.pop((channel, note), None)
        if candidate is None:
            return
        candidate["hold_frames"] = max(1, frame - candidate["start_frame"])
        candidate["tail_frames"] = release_frames

    for event in report["events"]:
        kind = event["type"]
        frame = event["frame"]
        if type(frame) is not int or frame < 0 or frame > MAX_FRAMES:
            raise ValueError("SEQ event exceeds 20-second schedule safety limit")
        channel = event.get("channel", 0)
        if kind == "program_change":
            states[channel]["program"] = event["program"]
        elif kind == "control_change":
            control, value = event["controller"], event["value"]
            if control in (0x07, 0x0B):
                states[channel]["volume"] = value
            elif control == 0x0A:
                states[channel]["pan"] = value
            elif control in (0x78, 0x7B):
                for (ch, note) in tuple(playing):
                    if ch == channel:
                        release(ch, note, frame)
        elif kind == "note_on":
            note = event["note"]
            release(channel, note, frame)  # retrigger clears prior ownership
            if len(scheduled) >= MAX_VOICES:
                raise ValueError("SEQ exceeds 32-note offline schedule limit")
            state = states[channel]
            sample = {
                "program": state["program"], "note": note,
                "velocity": event["velocity"],
                "channel_volume": state["volume"],
                "channel_pan": state["pan"],
                "start_frame": frame, "hold_frames": 1,
                "tail_frames": release_frames,
            }
            scheduled.append(sample)
            playing[(channel, note)] = sample
        elif kind == "note_off":
            release(channel, event["note"], frame)
        elif kind == "end_of_track":
            for ch, note in tuple(playing):
                release(ch, note, frame)
        # Tempo events already affected each absolute frame position.
        # Ignored channel events have no key-on/voice parameter effect.

    if not scheduled:
        raise ValueError("SEQ contains no note-on events to render")
    if playing:
        raise ValueError("SEQ must terminate with end-of-track")
    for idx, voice in enumerate(scheduled):
        final = (voice["start_frame"] + voice["hold_frames"]
                 + voice["tail_frames"])
        if final > MAX_FRAMES:
            raise ValueError(
                f"note {idx}: requested release exceeds 20-second render limit"
            )
    return {"voices": scheduled}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seq", type=Path, help="local source .seq")
    parser.add_argument("output", type=Path, help="new JSON schedule path")
    parser.add_argument("--release-frames", type=int, default=4410,
                        help="ADSR release tail at 44100 Hz; default 0.1 s")
    args = parser.parse_args()
    try:
        if args.seq.resolve() == args.output.resolve():
            raise ValueError("output cannot overwrite source SEQ")
        if args.seq.stat().st_size > MAX_SEQ_BYTES:
            raise ValueError("SEQ exceeds 256 KiB")
        parsed = parse_seq(args.seq.read_bytes())
        schedule = seq_to_schedule(parsed, release_frames=args.release_frames)
        with args.output.open("xb") as destination:
            destination.write(
                (json.dumps(schedule, indent=2) + "\n").encode("utf-8")
            )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({
        "source_sha256": parsed["sha256"],
        "voice_count": len(schedule["voices"]),
        "seq_end_frame": parsed["total_frames"],
        "schedule_last_frame": max(
            v["start_frame"] + v["hold_frames"] + v["tail_frames"]
            for v in schedule["voices"]
        ),
        "output": str(args.output),
        "warning": "Offline voice schedule only, not faithful real-time SEQ playback.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

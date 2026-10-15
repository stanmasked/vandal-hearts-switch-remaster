#!/usr/bin/env python3
"""Convert a local Sony PS1 SEQ into the bounded dry stereo-chord voice format.

This conversion models 20 SEQ voice slots, reallocation and round-robin
stealing, with channel program/volume/pan snapshots. It is not a faithful
runtime sequencer: ADSR liveness is approximated, with no reverb,
repeats, or block-quantized audio scheduling.

Input SEQ and output JSON remain local; the output is never overwritten.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_ps1_seq import MAX_SEQ_BYTES, parse_seq
from tools.mix_spu_stereo import MAX_FRAMES


# The reference PC port reserves slots 0..19 for SEQ (20..23 for SFX).
SEQ_VOICE_COUNT = 20
MAX_SEQ_NOTES = 2048  # bounded offline memory, not a simultaneous voice cap


def seq_to_schedule(report: dict[str, object], *, release_frames: int = 4410
                    ) -> dict[str, object]:
    """Build a time-bounded note schedule with 20 reusable SEQ voice slots.

    The source port takes the lowest free slot, otherwise steals the next
    slot round-robin. Note-off only releases its currently owned voice.
    ADSR release occupation is approximated by the diagnostic tail length:
    this is NOT hardware-accurate voice liveness or SEQ block timing.
    """
    if type(release_frames) is not int or not 0 <= release_frames <= 44100:
        raise ValueError("release_frames must be an integer in 0..44100")
    if report.get("format") != "PS1 SEQ":
        raise ValueError("requires a validated PS1 SEQ report")
    states = [{"program": 0, "volume": 127, "pan": 64}
              for _ in range(16)]
    # Each slot holds the current scheduled note, including its release tail.
    # Held notes have _released=False and remain busy until note-off.
    slots: list[dict | None] = [None] * SEQ_VOICE_COUNT
    held: dict[tuple[int, int], dict] = {}
    scheduled: list[dict] = []
    steal_round_robin = 0

    def release(channel: int, note: int, frame: int) -> None:
        entry = held.pop((channel, note), None)
        if entry is None:
            return
        entry["hold_frames"] = max(1, frame - entry["start_frame"])
        entry["tail_frames"] = release_frames
        entry["_released"] = True

    def end(entry: dict) -> int:
        if not entry["_released"]:
            return MAX_FRAMES + 1
        return (entry["start_frame"] + entry["hold_frames"]
                + entry["tail_frames"])

    def allocate(frame: int) -> int:
        nonlocal steal_round_robin
        for slot, old in enumerate(slots):
            if old is None or end(old) <= frame:
                return slot
        # All 20 SEQ voices are still busy (held or releasing). The source
        # code's RR index advances ONLY when every voice is busy.
        slot = steal_round_robin
        steal_round_robin = (steal_round_robin + 1) % SEQ_VOICE_COUNT
        old = slots[slot]
        if not old["_released"]:
            key = old["_channel"], old["note"]
            if held.get(key) is old:
                del held[key]  # stale later note-off must not stop new owner
            elapsed = frame - old["start_frame"]
            if elapsed > 0:
                old["hold_frames"] = elapsed
                old["tail_frames"] = 0
            else:
                old["_dropped"] = True  # stolen before first output frame
        else:
            if frame <= old["start_frame"]:
                # A same-frame note-on/off never reached an output tick.
                # The earlier one-frame minimum cannot survive a steal.
                old["_dropped"] = True
            else:
                old["tail_frames"] = max(
                    0, frame - old["start_frame"] - old["hold_frames"]
                )
        old["_released"] = True
        return slot

    for event in report["events"]:
        kind = event["type"]
        frame = event["frame"]
        if type(frame) is not int or not 0 <= frame <= MAX_FRAMES:
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
                for ch, note in tuple(held):
                    if ch == channel:
                        release(ch, note, frame)
        elif kind == "note_on":
            note = event["note"]
            release(channel, note, frame)  # retrigger: release prior owner
            if len(scheduled) >= MAX_SEQ_NOTES:
                raise ValueError("SEQ exceeds 2048-note offline safety limit")
            slot = allocate(frame)
            state = states[channel]
            entry = {
                "program": state["program"], "note": note,
                "velocity": event["velocity"],
                "channel_volume": state["volume"],
                "channel_pan": state["pan"],
                "start_frame": frame, "hold_frames": 1,
                "tail_frames": release_frames,
                "voice_slot": slot,
                "_channel": channel, "_released": False,
            }
            scheduled.append(entry)
            slots[slot] = entry
            held[(channel, note)] = entry
        elif kind == "note_off":
            release(channel, event["note"], frame)
        elif kind == "end_of_track":
            for ch, note in tuple(held):
                release(ch, note, frame)

    if not scheduled:
        raise ValueError("SEQ contains no note-on events to render")
    if held:
        raise ValueError("SEQ must terminate with end-of-track")
    voices = []
    for idx, entry in enumerate(scheduled):
        if entry.get("_dropped"):
            continue
        final = end(entry)
        if final > MAX_FRAMES:
            raise ValueError(
                f"note {idx}: requested release exceeds 20-second render limit"
            )
        voices.append({k: v for k, v in entry.items()
                       if not k.startswith("_")})
    if not voices:
        raise ValueError("all same-frame notes were stolen before playback")
    return {"voices": voices}


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

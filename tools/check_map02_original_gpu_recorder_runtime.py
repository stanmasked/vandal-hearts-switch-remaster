#!/usr/bin/env python3
"""Run real pinned original-PC GPU recorder and audit its terminal receipt.

No real game content. The original libgpu.c and pc_raster.c execute a
handmade DR_MODE/F4/FT4 ordering table; 34 raster draws plus one
state-only DR_MODE create 35 native event pairs in overflow mode. These are
synthetic. The capture is temporary and never uploaded as a CI artifact.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from tools.check_map02_original_drawotag_runtime import HARNESS
from tools.instrument_map02_gpu_native_events import instrument
from tools.verify_map02_native_gpu_capture import (
    STATUS, LOG, verify_capture, verify_capture_receipt,
)
from tools.verify_map02_native_gpu_windows import verify_native_windows



def require_original_ot_pairs(events, expected_types):
    """Audit ordered native BEFORE/AFTER pairs including state-only DR_MODE.

    This checks the synthetic source's exact primitive order, not genuine
    MAP02 gameplay or raster/PS1 parity. The full VRAM validator runs
    separately and is not replaced by these bounded metadata assertions.
    """
    if len(events) != 2 * len(expected_types):
        raise ValueError("original GPU event-pair count mismatch")
    for ordinal, expected_type in enumerate(expected_types):
        before, after = events[2 * ordinal:2 * ordinal + 2]
        if (before.get("operation") != "draw" or
                after.get("operation") != "draw" or
                before.get("primitive_type") != expected_type or
                after.get("primitive_type") != expected_type or
                before.get("phase") != "before" or
                after.get("phase") != "after"):
            raise ValueError("original GPU event-pair order/phase mismatch")
    return len(expected_types)


def execute_real_recorder(upstream, *, cc="cc"):
    pc = Path(upstream).resolve() / "platform" / "pc"
    raster = pc / "src" / "pc_raster.c"
    walker = pc / "src" / "libgpu.c"
    patched = instrument(walker.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="vh-map02-recorder-") as tmp:
        root = Path(tmp)
        patched_path = root / "libgpu.c"
        patched_path.write_text(patched, encoding="utf-8")
        for label, extra_draws in (
                ("closed", 0), ("overflow", 32), ("windowed", 32)):
            fixture = HARNESS
            if extra_draws:
                fixture = fixture.replace("    int u, v;",
                                          "    int u, v, k;\n    POLY_F4 extras[32];")
                fixture = fixture.replace(
                    "    AddPrim(&ot[0], &mode);",
                    """    AddPrim(&ot[0], &mode);
    for (k = 0; k < 32; ++k) {
        SetPolyF4(&extras[k]);
        setRGB0(&extras[k], 96, 0, 0);
        setXYWH(&extras[k], 9, 9, 6, 6);
        AddPrim(&ot[0], &extras[k]);
    }""")
            harness = root / (label + ".c")
            harness.write_text(fixture, encoding="utf-8")
            executable = root / (label + ".bin")
            command = [
                cc, "-std=gnu99", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-missing-field-initializers",
                "-ffunction-sections", "-fdata-sections", "-DVH_REGION_US",
                "-DVH_MAP02_GPU_CAPTURE",
                *(["-DVH_MAP02_POSIX_CAPTURE_WINDOWS"] if
                  label == "windowed" else []),
                "-I", str(pc / "include"),
                "-I", str(pc / "src"), str(patched_path), str(raster),
                str(harness), "-Wl,--gc-sections", "-lm", "-pthread",
                "-o", str(executable),
            ]
            compiled = subprocess.run(command, text=True, capture_output=True,
                                      timeout=120)
            if compiled.returncode:
                raise ValueError("original GPU recorder compile: "
                                 + compiled.stderr[-3500:])
            private = root / (label + "-private")
            private.mkdir(mode=0o700)
            env = dict(os.environ,
                       VH_MAP02_GPU_CAPTURE_DIR=str(private),
                       VH_MAP02_GPU_CAPTURE_FRAME="1",
                       VH_ACCURATE="1", VH_INTERNAL_SCALE="1")
            if label == "windowed":
                env["VH_MAP02_GPU_CAPTURE_WINDOW_COUNT"] = "2"
            executed = subprocess.run([str(executable)], env=env,
                                      text=True, capture_output=True, timeout=90)
            if executed.returncode:
                raise ValueError("original GPU recorder runtime: "
                                 + executed.stderr[-3500:])
            if label == "windowed":
                result = verify_native_windows(private, target_frame=1)
                # 32 extra F4 + 2 original raster draws + 1 state-only
                # DR_MODE = 35 native event pairs, with 70 BEFORE/AFTER
                # snapshots in two windows. The recorder must NOT drop the
                # DR_MODE state transition at the 64/65 boundary.
                if (result["recorded_windows"] != 2 or
                        result["globally_ordered_native_gpu_events"] != 70 or
                        result["native_draw_pairs"] != 35 or
                        result["vram_bridge_checks"] != 34 or
                        result["whole_original_gameplay_frame_proven"]):
                    raise ValueError("native GPU windows did not preserve original OT")
                second = private / "window-001"
                rows = [json.loads(row) for row in
                        (second / LOG).read_bytes().splitlines()]
                require_original_ot_pairs(rows, (5, 1, 2))
                # Real-byte mutation of ALL second-window snapshots at
                # off-primitive (0,0) preserves every local BEFORE/AFTER
                # transition. Only the cross-window VRAM continuity guard
                # can reject it; we must exercise that guard independently.
                for local_step in range(6):
                    snapshot = second / f"gpu-{local_step:04d}-vram.bin"
                    with snapshot.open("r+b") as fh:
                        initial = fh.read(1)
                        if len(initial) != 1:
                            raise ValueError("missing boundary VRAM byte")
                        fh.seek(0)
                        fh.write(bytes([initial[0] ^ 1]))
                try:
                    verify_native_windows(private, target_frame=1)
                except ValueError as exc:
                    if "continuity broken" not in str(exc):
                        raise
                else:
                    raise ValueError("tampered original GPU VRAM bridge was accepted")
                continue
            status = json.loads((private / STATUS).read_bytes())
            events = [json.loads(row) for row in (private / LOG).read_bytes().splitlines()]
            # The PR #55 strict auditor captures DR_MODE for GPU-state
            # provenance. It consumes one event pair but never a PutPixel
            # raster draw ordinal. The original fixture has 2 raster draws.
            expected_pairs = 3 + extra_draws
            if (status["gpu_draw_frame"] != 1 or
                    status["draw_before_hooks"] != expected_pairs or
                    status["observed_hooks"] != 2 * expected_pairs):
                raise ValueError("original DrawOTag did not report all GPU hooks")
            if extra_draws:
                # AddPrim is LIFO: the 32 extra F4 exhaust the 64-event
                # recorder, so DR_MODE + two older draws remain unrecorded.
                if not status["limit_reached"]:
                    raise ValueError("original GPU recorder overflow did not surface")
                require_original_ot_pairs(events, (1,) * 32)
                try:
                    verify_capture_receipt(private, target_frame=1, events=events)
                except ValueError as exc:
                    if not any(word in str(exc) for word in
                               ("incomplete", "count/log divergence")):
                        raise
                else:
                    raise ValueError("overfull native GPU capture was accepted")
            else:
                require_original_ot_pairs(events, (5, 1, 2))
                proof = verify_capture_receipt(private, target_frame=1,
                                               events=events)
                if not proof["capture_window_closed_without_detected_loss"]:
                    raise ValueError("closed synthetic frame failed recorder receipt")
                # Receipt accounting alone cannot prove DR_MODE kept VRAM
                # invariant. Validate complete pre/post BGR555 snapshots.
                checked = verify_capture(private, target_frame=1)
                if (checked["native_gpu_pairs_verified"] != 3 or
                        checked["draw_otag_primitive_pairs"] != 3):
                    raise ValueError("closed original OT GPU snapshot replay failed")
        return ("closed", "overflow-rejected", "two-windows-bridged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_upstream", type=Path)
    args = parser.parse_args()
    try:
        modes = execute_real_recorder(args.pinned_upstream)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print("Pinned original PC GPU capture receipt:", ", ".join(modes))
    print("No original gameplay content or PS1 hardware proof.")


if __name__ == "__main__":
    main()

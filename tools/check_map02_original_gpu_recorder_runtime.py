#!/usr/bin/env python3
"""Run real pinned original-PC GPU recorder and audit its terminal receipt.

No real game content. The original libgpu.c and pc_raster.c execute a
handmade DR_MODE/F4/FT4 ordering table; 34-draw overflow is deliberately
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
    STATUS, LOG, verify_capture_receipt,
)
from tools.verify_map02_native_gpu_windows import verify_native_windows


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
                if (result["recorded_windows"] != 2 or
                        result["globally_ordered_native_gpu_events"] != 68 or
                        result["native_draw_pairs"] != 34 or
                        result["vram_bridge_checks"] != 33 or
                        result["whole_original_gameplay_frame_proven"]):
                    raise ValueError("native GPU windows did not preserve original OT")
                continue
            status = json.loads((private / STATUS).read_bytes())
            events = [json.loads(row) for row in (private / LOG).read_bytes().splitlines()]
            if status["gpu_draw_frame"] != 1 or (
                    status["draw_before_hooks"] != (34 if extra_draws else 2)):
                raise ValueError("original DrawOTag did not report all draw hooks")
            if any(e["primitive_type"] == 5 for e in events):
                raise ValueError("DR_MODE should never consume a native draw slot")
            if extra_draws:
                if (len(events) != 64 or status["observed_hooks"] != 68 or
                        not status["limit_reached"]):
                    raise ValueError("original GPU recorder overflow did not surface")
                try:
                    verify_capture_receipt(private, target_frame=1, events=events)
                except ValueError:
                    pass
                else:
                    raise ValueError("overfull native GPU capture was accepted")
            else:
                if len(events) != 4:
                    raise ValueError("DR_MODE incorrectly counted as a draw event")
                proof = verify_capture_receipt(private, target_frame=1,
                                               events=events)
                if not proof["capture_window_closed_without_detected_loss"]:
                    raise ValueError("closed synthetic frame failed recorder receipt")
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

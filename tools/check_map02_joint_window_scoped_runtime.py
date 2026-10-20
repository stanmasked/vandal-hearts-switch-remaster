#!/usr/bin/env python3
"""Exercise ALL native MAP02 observers together in pinned original PC GPU.

A single original DrawOTag execution yields two native GPU event windows
and three scoped selected-pixel witness logs. 32 synthetic F4 draws do NOT
touch the chosen pixel; the final F4+FT4 do, across the 64-event boundary.
No retail game input or original PlayStation proof is used.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from tools.check_map02_original_drawotag_runtime import HARNESS
from tools.instrument_map02_gpu_native_events import instrument as native_probe
from tools.instrument_map02_drawotag_scope import instrument as scoped_probe
from tools.instrument_map02_scoped_blend import instrument as raster_probe
from tools.verify_map02_window_scoped_join import verify_window_scoped_join
from tools.map02_local_capture_handoff import prepare_local_capture
from tools.map02_verified_process_launch import (
    launch_observed_pc, verify_observed_process,
)


HARNESS_DRAWS = HARNESS[:HARNESS.index("int main(void) {")] + r"""
int main(void) {
    unsigned int ot[2];
    DR_MODE mode;
    POLY_F4 f4, extras[32];
    POLY_FT4 ft4;
    DRAWENV env;
    DISPENV disp;
    unsigned short (*vram)[1024] = PC_GpuVram();
    int u, v, k;
    ResetGraph(0);
    SetDefDrawEnv(&env, 0, 0, 320, 240);
    SetDefDispEnv(&disp, 0, 0, 320, 240);
    PutDrawEnv(&env);
    PutDispEnv(&disp);
    for (v = 0; v < 8; ++v) for (u = 0; u < 8; ++u)
        vram[v][640 + u] = 0x8010;
    vram[10][10] = 1;

    SetPolyF4(&f4);
    setRGB0(&f4, 200, 0, 0);
    setXYWH(&f4, 9, 9, 6, 6);
    SetSemiTrans(&f4, 1);
    SetPolyFT4(&ft4);
    setRGB0(&ft4, 128, 128, 128);
    setXYWH(&ft4, 9, 9, 6, 6);
    setUVWH(&ft4, 0, 0, 6, 6);
    ft4.tpage = GetTPage(2, 2, 640, 0);
    ft4.clut = 0;
    SetSemiTrans(&ft4, 1);
    SetDrawMode(&mode, 0, 0, GetTPage(2, 1, 640, 0), NULL);
    ClearOTag(ot, 2);
    AddPrim(&ot[0], &ft4);
    AddPrim(&ot[0], &f4);
    AddPrim(&ot[0], &mode);
    for (k = 0; k < 32; ++k) {
        SetPolyF4(&extras[k]);
        setRGB0(&extras[k], 96, 0, 0);
        setXYWH(&extras[k], 30, 30, 6, 6);
        AddPrim(&ot[0], &extras[k]);
    }
    /* 32 non-touching F4s, DR_MODE, F4 and FT4. Raster ordinals
     * 0..33, but GPU event stream also captures state-only DR_MODE.
     * Window 000 stores 32 F4 (64 hooks); window 001 stores DR_MODE
     * then F4/FT4 (6 hooks). Private pixel witness has no DR_MODE edge. */
    DrawOTag(ot);
#ifdef VH_MAP02_VRAM_EDGE_PROBE
    verify_edges_against_putpixel();
    assert(vh_map02_edges_count() == 34);
#endif
    assert(vram[10][10] != 1);
    return 0;
}
"""


def check_joint_original_gpu(upstream, *, compiler="cc"):
    pc = Path(upstream).resolve() / "platform" / "pc"
    walker = pc / "src/libgpu.c"
    raster = pc / "src/pc_raster.c"
    if not walker.is_file() or not raster.is_file():
        raise FileNotFoundError("pinned original PC GPU translation units missing")
    # Exact-source anchoring by BOTH independently maintained generators.
    native = native_probe(walker.read_text(encoding="utf-8"))
    combined = scoped_probe(native)
    pixel = raster_probe(raster.read_text(encoding="utf-8"))
    tools = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="vh-map02-dual-gpu-") as tmp:
        root = Path(tmp)
        (root / "libgpu.c").write_text(combined, encoding="utf-8")
        (root / "pc_raster.c").write_text(pixel, encoding="utf-8")
        (root / "harness.c").write_text(HARNESS_DRAWS, encoding="utf-8")
        executable = root / "dual-original-gpu"
        args = [
            compiler, "-std=gnu99", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-parameter", "-Wno-missing-field-initializers",
            "-ffunction-sections", "-fdata-sections", "-DVH_REGION_US",
            "-DVH_MAP02_GPU_CAPTURE", "-DVH_MAP02_POSIX_CAPTURE_WINDOWS",
            "-DVH_MAP02_SCOPED_BLEND_PROBE", "-DVH_MAP02_VRAM_EDGE_PROBE",
            "-DVH_MAP02_POSIX_STAGE", "-DVH_MAP02_CAPTURE_SESSION",
            "-I", str(pc / "include"), "-I", str(pc / "src"),
            "-I", str(tools), str(root / "libgpu.c"),
            str(root / "pc_raster.c"), str(root / "harness.c"),
            str(tools / "map02_scoped_blend_sink.c"),
            str(tools / "map02_scoped_blend_stage.c"),
            str(tools / "map02_vram_edges.c"),
            str(tools / "map02_capture_session.c"),
            "-Wl,--gc-sections", "-lm", "-pthread", "-o", str(executable),
        ]
        built = subprocess.run(args, capture_output=True, text=True,
                               timeout=120)
        if built.returncode:
            raise ValueError("combined original GPU build: " + built.stderr[-4400:])
        native_dir, scoped_dir = root / "native-windows", root / "scoped"
        native_dir.mkdir(mode=0o700)
        scoped_dir.mkdir(mode=0o700)
        env = dict(os.environ, VH_ACCURATE="1", VH_INTERNAL_SCALE="1",
                   VH_MAP02_GPU_CAPTURE_FRAME="1",
                   VH_MAP02_GPU_CAPTURE_DIR=str(native_dir),
                   VH_MAP02_GPU_CAPTURE_WINDOW_COUNT="2",
                   VH_MAP02_PROBE_FRAME="1", VH_MAP02_PROBE_X="10",
                   VH_MAP02_PROBE_Y="10",
                   VH_MAP02_PROBE_OUTPUT_DIR=str(scoped_dir))
        finished = subprocess.run([str(executable)], env=env,
                                  capture_output=True, text=True, timeout=90)
        if finished.returncode:
            raise ValueError("combined original DrawOTag runtime: "
                             + finished.stderr[-4000:])
        result = verify_window_scoped_join(
            native_dir, scoped_dir, target_frame=1)
        if (result["global_draw_ordinals_checked"] != 34 or
                result["global_event_indices_of_first_and_last_draw"] !=
                [0, 68] or
                result["unchanged_draws_at_selected_pixel"] != 32 or
                result["selected_pixel_putpixel_events"] < 2 or
                result["selected_pixel_blendg1_events"] < 2 or
                result["capture_session_linked"] is not True or
                not result["capture_session_sha256"] or
                result["source_gte_subsequence_verified"]):
            raise ValueError("combined GPU-scoped bridge missed a draw/pixel")
        # Re-execute the exact same real original PC code in another OS
        # process with identical synthetic geometry. It produces the same
        # VRAM and packet order, but must NOT be joinable to the first run.
        other_native = root / "native-second-process"
        other_scoped = root / "scoped-second-process"
        other_native.mkdir(mode=0o700)
        other_scoped.mkdir(mode=0o700)
        other_env = dict(
            env, VH_MAP02_GPU_CAPTURE_DIR=str(other_native),
            VH_MAP02_PROBE_OUTPUT_DIR=str(other_scoped))
        second = subprocess.run(
            [str(executable)], env=other_env,
            capture_output=True, text=True, timeout=90)
        if second.returncode:
            raise ValueError("second original DrawOTag session failed: "
                             + second.stderr[-3000:])
        second_report = verify_window_scoped_join(
            other_native, other_scoped, target_frame=1)
        if (second_report["capture_session_sha256"] ==
                result["capture_session_sha256"]):
            raise ValueError("two original PC executions reused a capture session")
        for wrong_native, wrong_scoped in (
            (native_dir, other_scoped), (other_native, scoped_dir)
        ):
            try:
                verify_window_scoped_join(
                    wrong_native, wrong_scoped, target_frame=1)
            except ValueError as error:
                if "mixed-session" not in str(error):
                    raise
            else:
                raise ValueError(
                    "two independent original GPU process captures were joined")
        # Exercise the REAL pinned original PC GPU with a launcher that
        # observes Linux /proc/PID/exe while the child process is alive.
        # This extra one-second sleep is synthetic test scaffolding only.
        # An uninstrumented or substituted process cannot gain a receipt.
        held = root / "harness-observed.c"
        tail = "    assert(vram[10][10] != 1);\\n    return 0;"
        if tail.replace("\\n", "\n") not in HARNESS_DRAWS:
            raise ValueError("real original GPU harness terminator changed")
        held.write_text(
            "#include <unistd.h>\n#include <stdio.h>\n#include <stdlib.h>\n" +
            HARNESS_DRAWS.replace(
                tail.replace("\\n", "\n"),
                "    assert(vram[10][10] != 1);\n"
                "    { FILE *disc = fopen(getenv(\"VH_DISC_IMAGE\"), \"rb\");\n"
                "      if (!disc) return 7;\n"
                "      sleep(1);\n"
                "      if (fclose(disc) != 0) return 8; }\n"
                "    return 0;"),
            encoding="utf-8")
        held_exe = root / "original-gpu-kernel-observed"
        held_build = [
            str(held) if arg == str(root / "harness.c") else
            str(held_exe) if arg == str(executable) else arg
            for arg in args
        ]
        built = subprocess.run(
            held_build, capture_output=True, text=True, timeout=120)
        if built.returncode:
            raise ValueError("original GPU kernel-observed build: "
                             + built.stderr[-3000:])
        owned_synthetic = root / "fake-owned-game-image"
        owned_synthetic.write_bytes(b"asset-free CI fixture; NOT retail game")
        owned_synthetic.chmod(0o600)
        handoff = root / "local-handoff"
        held_native = root / "kernel-observed-windows"
        held_scoped = root / "kernel-observed-scoped"
        for private_dir in (handoff, held_native, held_scoped):
            private_dir.mkdir(mode=0o700)
        prepare_local_capture(
            handoff, held_exe, owned_synthetic, frame=1, upstream=upstream)
        observed_run = launch_observed_pc(
            handoff, held_native, held_scoped, held_exe,
            owned_synthetic, upstream=upstream, x=10, y=10, timeout=15)
        observed_recheck = verify_observed_process(
            handoff, held_native, held_scoped,
            held_exe, owned_synthetic, upstream=upstream)
        if (not observed_run["kernel_executable_hash_matched"] or
                observed_run["private_process_receipt_sha256"] !=
                observed_recheck["private_process_receipt_sha256"]):
            raise ValueError("original GPU process executable audit mismatch")
        # Mutating just the scoped receipt must be detected even though
        # PutPixel/BlendG1/native VRAM still match all original GPU bytes.
        session_file = scoped_dir / "gpu-scoped-session.json"
        clean_session = session_file.read_bytes()
        foreign = json.loads(clean_session)
        foreign["capture_session"] = "ba" * 16
        session_file.write_text(json.dumps(foreign) + "\n")
        try:
            verify_window_scoped_join(native_dir, scoped_dir, target_frame=1)
        except ValueError as error:
            if "mixed-session" not in str(error):
                raise
        else:
            raise ValueError("foreign GPU process session was accepted")
        session_file.write_bytes(clean_session)
        # A syntactically valid, coherent C capture with a wrong selected
        # VRAM edge still must fail direct full-snapshot join.
        edge_file = scoped_dir / "vram-edges-native-events.pending.jsonl"
        edges = [json.loads(r) for r in edge_file.read_bytes().splitlines()]
        edges[0]["after"] = 17
        edge_file.write_bytes(b"".join(
            (json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n").encode()
            for r in edges))
        try:
            verify_window_scoped_join(native_dir, scoped_dir, target_frame=1)
        except ValueError:
            pass
        else:
            raise ValueError("tampered native VRAM boundary was accepted")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_original_pc_repo", type=Path)
    a = p.parse_args()
    try:
        result = check_joint_original_gpu(a.pinned_original_pc_repo)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps({
        "global_draw_ordinals_checked": result["global_draw_ordinals_checked"],
        "selected_pixel_putpixel_events":
            result["selected_pixel_putpixel_events"],
        "selected_pixel_blendg1_events":
            result["selected_pixel_blendg1_events"],
        "independent_vram_edges":
            result["independently_sampled_draw_edges"],
        "source_gte_subsequence_verified": False,
        "retail_gameplay_proven": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

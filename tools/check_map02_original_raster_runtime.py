#!/usr/bin/env python3
"""Run a REAL pinned original-PC rasterizer on synthetic in-memory geometry.

No game assets, PlayStation EXE, private frame, or screenshots involved.
Compiles actual platform/pc/src/pc_raster.c source, NOT a substitute
BlendG1/WritePixel implementation. External HD-pack and language dependencies
are stubbed OFF, because this smoke test exercises the native VRAM path only.
The full original DrawOTag runtime is a separate, still-pending objective.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

from tools.instrument_map02_scoped_blend import instrument

HARNESS = r"""
#include <assert.h>
#include <stddef.h>
#include <string.h>
#include "pc_gpu_internal.h"
#include "pc_lang.h"
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
#include "map02_scoped_blend_sink.h"
#endif

/* Non-raster dependencies are intentionally inactive in this headless,
 * no-content test. Do not substitute these stubs in the actual game build. */
const char *PC_LangBgDir(void) { return NULL; }
int HdRegionCount(void) { return 0; }
int HdReplaceCount(void) { return 0; }
int HdAnyActive(void) { return 0; }
const char *HdDumpDir(void) { return NULL; }
void HdMaybeDump(int tp, int cl, int x0, int x1, int y0, int y1) {
    (void)tp; (void)cl; (void)x0; (void)x1; (void)y0; (void)y1;
    assert(!"unexpected HD dump");
}
HdRegion *HdFindTriRegion(int tp, int x0, int x1, int y0, int y1) {
    (void)tp; (void)x0; (void)x1; (void)y0; (void)y1;
    assert(!"unexpected HD region lookup");
    return NULL;
}

int main(void) {
    RenderCtx rc;
    RVert a = {9, 9, 0, 0}, b = {14, 9, 0, 0};
    RVert c = {9, 14, 0, 0}, d = {14, 14, 0, 0};
    unsigned short (*vram)[PC_GPU_VRAM_W] = PC_GpuVram();
    unsigned short before = 0x001f;
    unsigned short after;
    memset(&rc, 0, sizeof(rc));
    rc.clipW = PC_GPU_VRAM_W;
    rc.clipH = PC_GPU_VRAM_H;
    rc.scale = 1;
    rc.target = 0; /* never sample the hi-res renderer */
    vram[10][10] = before;
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    VHMap02BlendEvent witness;
    unsigned i, blends = 0;
    assert(vh_map02_scope_begin_frame(1, 10, 10));
    assert(vh_map02_scope_begin_primitive(0, PC_GPU_PRIM_POLY_F4));
#endif
    /* ORIGINAL FillQuad -> FillTriangleDDA -> PutPixel -> BlendG1 */
    FillQuad(&rc, a, b, c, d, 200, 0, 0, 0, 0, 0, 1, 1);
    after = vram[10][10];
    assert(after != before);
#ifdef VH_MAP02_SCOPED_BLEND_PROBE
    assert(vh_map02_scope_end_primitive());
    assert(vh_map02_scope_end_frame());
    assert(!vh_map02_scope_failed());
    assert(vh_map02_scope_count() > 0);
    for (i = 0; i < vh_map02_scope_count(); i++) {
        assert(vh_map02_scope_copy(i, &witness));
        assert(witness.frame == 1);
        assert(witness.ordinal == 0);
        assert(witness.primitive_type == PC_GPU_PRIM_POLY_F4);
        assert(witness.x == 10 && witness.y == 10);
        assert(witness.semi && witness.accurate);
        assert(witness.has_blend);
        assert(witness.blend_fg == (unsigned short)(witness.front | 0x8000u));
        assert(witness.blend_bg == witness.before);
        assert(witness.blend_result == witness.after);
        if (i == 0) assert(witness.before == before);
        if (i + 1u == vh_map02_scope_count())
            assert(witness.after == after);
        blends++;
    }
    assert(blends >= 1);
#endif
    return 0;
}
"""


def runtime_check(upstream, *, cc="cc"):
    base = Path(upstream).resolve() / "platform" / "pc"
    original = base / "src" / "pc_raster.c"
    if not original.is_file():
        raise FileNotFoundError("missing pinned original PC rasterizer")
    patched = instrument(original.read_text(encoding="utf-8"))
    include = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="vh-map02-original-raster-runtime-") as tmp:
        root = Path(tmp)
        src = root / "pc_raster.instrumented.c"
        harness = root / "raster_runtime.c"
        src.write_text(patched, encoding="utf-8")
        harness.write_text(HARNESS, encoding="utf-8")
        for name, defines in (
            ("ordinary", []),
            ("scoped", ["-DVH_MAP02_SCOPED_BLEND_PROBE"]),
        ):
            exe = root / name
            cmd = [
                cc, "-std=gnu99", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-missing-field-initializers",
                "-ffunction-sections", "-fdata-sections",
                "-DVH_REGION_US", *defines,
                "-I", str(base / "include"), "-I", str(base / "src"),
                "-I", str(include), str(src), str(harness),
            ]
            if defines:
                cmd.append(str(include / "map02_scoped_blend_sink.c"))
            cmd += ["-Wl,--gc-sections", "-lm", "-pthread", "-o", str(exe)]
            compiled = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=90, check=False)
            if compiled.returncode:
                raise ValueError(name + " real rasterizer link failed: "
                                 + compiled.stderr[-3200:])
            executed = subprocess.run(
                [str(exe)], capture_output=True, text=True,
                timeout=30, check=False, env={
                    "VH_ACCURATE": "1",
                    "VH_INTERNAL_SCALE": "1",
                })
            if executed.returncode:
                raise ValueError(name + " real rasterizer smoke failed: "
                                 + executed.stderr[-2200:])
    return ("ordinary", "scoped")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_upstream_repo", type=Path)
    args = parser.parse_args()
    try:
        modes = runtime_check(args.pinned_upstream_repo)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print("Pinned original GPU raster runtime: " + ", ".join(modes))
    print("Synthetic geometry only; MAP02 gameplay and hardware fidelity unverified.")


if __name__ == "__main__":
    main()

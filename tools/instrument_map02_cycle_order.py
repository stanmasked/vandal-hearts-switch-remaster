#!/usr/bin/env python3
"""Generate three copied, source-pinned PC units with an opt-in CD -> OT order gate.

Existing original CdRead, scoped DrawOTag, native VRAM and pixel observers are preserved. The new
gate only checks order of IN-PROCESS calls when all three translation units
link against one map02_cycle_order.c. It never claims a MAP02 scene was drawn.
No game assets or binary are read by the generator.
"""
import argparse
from pathlib import Path

from tools.instrument_map02_cd_read import instrument_core_cd, instrument_libcd
from tools.instrument_map02_drawotag_scope import instrument as instrument_gpu_scope
from tools.instrument_map02_gpu_native_events import instrument as instrument_gpu_native
from tools.instrument_map02_scoped_blend import instrument as instrument_raster_scope
from tools.instrument_map02_gpu_native_events import PINNED_SOURCE as GPU_SOURCE
from tools.prepare_map02_pcport import git_blob_sha1


def inject(src, old, new):
    if src.count(old) != 1:
        raise ValueError("pinned MAP02 cycle hook missing or ambiguous: " + old[:80])
    return src.replace(old, new, 1)


def patch_core(original):
    src = instrument_core_cd(original)  # pinned blob and state 7 anchor verified
    src = inject(src, '#include "map02_cd_read_probe.h"\n#endif',
                 '#include "map02_cd_read_probe.h"\n#endif\n'
                 '#ifdef VH_MAP02_CYCLE_ORDER\n#include "map02_cycle_order.h"\n#endif')
    src = inject(src,
        '       gCdFiles[cdfIdx].startingSector, gCdFiles[cdfIdx].sectorCt);\n#endif',
        '       gCdFiles[cdfIdx].startingSector, gCdFiles[cdfIdx].sectorCt);\n#endif\n'
        '#ifdef VH_MAP02_CYCLE_ORDER\n'
        '   vh_map02_cycle_load(cdfIdx, CDF_M_MAP02_PRS,\n'
        '       gCdFiles[cdfIdx].startingSector, gCdFiles[cdfIdx].sectorCt);\n'
        '#endif')
    src = inject(src,
        '          CDF_M_MAP02_PRS, gCdLoader.state);\n#endif',
        '          CDF_M_MAP02_PRS, gCdLoader.state);\n#endif\n'
        '#ifdef VH_MAP02_CYCLE_ORDER\n'
        '      vh_map02_cycle_loader_complete(gCdLoader.cdf,\n'
        '          CDF_M_MAP02_PRS, gCdLoader.state);\n'
        '#endif')
    return src


def patch_libcd(original):
    src = instrument_libcd(original)  # pinned blob verified
    src = inject(src, '#include "map02_cd_read_probe.h"\n#endif',
                 '#include "map02_cd_read_probe.h"\n#endif\n'
                 '#ifdef VH_MAP02_CYCLE_ORDER\n#include "map02_cycle_order.h"\n#endif')
    src = inject(src, '    vh_map02_cd_read_start(s_targetLBA, sectors);\n#endif',
                 '    vh_map02_cd_read_start(s_targetLBA, sectors);\n#endif\n'
                 '#ifdef VH_MAP02_CYCLE_ORDER\n'
                 '    vh_map02_cycle_read_start(s_targetLBA, sectors);\n#endif')
    src = inject(src,
                 '    vh_map02_cd_read_finish(s_targetLBA, sectors, out);\n#endif',
                 '    vh_map02_cd_read_finish(s_targetLBA, sectors, out);\n#endif\n'
                 '#ifdef VH_MAP02_CYCLE_ORDER\n'
                 '    vh_map02_cycle_read_finish(s_targetLBA, sectors);\n#endif')
    return src


def patch_gpu(original):
    if git_blob_sha1(original.encode("utf-8")) != GPU_SOURCE:
        raise ValueError("pinned original PC libgpu.c SHA-1 differs")
    # The jointly tested original GPU composition is native first, scoped
    # second; both use distinct pinned anchors and a shared DrawOTag walker.
    src = instrument_gpu_scope(instrument_gpu_native(original))
    src = inject(src, 'void DrawOTag(unsigned int *p) {',
                 '#ifdef VH_MAP02_CYCLE_ORDER\n'
                 '#include "map02_cycle_order.h"\n#endif\n'
                 'void DrawOTag(unsigned int *p) {')
    src = inject(src, '    s_drawFrame++;',
                 '    s_drawFrame++;\n#ifdef VH_MAP02_CYCLE_ORDER\n'
                 '    vh_map02_cycle_draw_start(s_drawFrame);\n#endif')
    src = inject(src, '    TrcFrameEnd();',
                 '#ifdef VH_MAP02_CYCLE_ORDER\n'
                 '    vh_map02_cycle_draw_finish(s_drawFrame, nextTok == 0);\n'
                 '#endif\n    TrcFrameEnd();')
    return src


def patch_raster(original):
    return instrument_raster_scope(original)


def generate(checkout: Path, output: Path):
    # Check the provided path before resolve() erases the symlink itself.
    if output.is_symlink():
        raise ValueError("refusing symlinked output directory")
    checkout = checkout.resolve()
    output = output.resolve()
    if output == checkout or checkout in output.parents:
        raise ValueError("refusing to write into original pinned checkout")
    sources = {
        "core_cd.c": (checkout / "src/core/cd.c", patch_core),
        "libcd.c": (checkout / "platform/pc/src/libcd.c", patch_libcd),
        "libgpu.c": (checkout / "platform/pc/src/libgpu.c", patch_gpu),
        "pc_raster.c": (checkout / "platform/pc/src/pc_raster.c", patch_raster),
    }
    if output.exists() and (output.is_symlink() or any(output.iterdir())):
        raise ValueError("output directory must be empty and not a symlink")
    rendered = {name: patch(path.read_text(encoding="utf-8"))
                for name, (path, patch) in sources.items()}
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, src in rendered.items():
        with (output / name).open("x", encoding="utf-8") as stream:
            stream.write(src)
    return sorted(rendered)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pc_checkout", type=Path)
    parser.add_argument("empty_output_directory", type=Path)
    args = parser.parse_args()
    try:
        names = generate(args.pinned_pc_checkout, args.empty_output_directory)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Generated pinned opt-in single-process hooks: " + ", ".join(names))
    print("Must link CD, cycle, session, GPU scoped sink/stage and VRAM edge observers")
    print("No real MAP02 gameplay or rendering was executed.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Exact-source opt-in original CD read + game loader instrumentation (US).

Never turns a static CD extent check into a claim of executed MAP02 gameplay.
Under VH_MAP02_CD_READ_PROBE, hooks originate inside the original libcd.c
CdRead sector copy and core/cd.c LoadCdFile/ContinueLoadingCdFile state machine.
Only observed, successful MAP02-specific calls can complete the witness.
"""
import argparse
from pathlib import Path

from tools.prepare_map02_pcport import git_blob_sha1

SOURCE_CD = "30d43504c8becadaca4c475abce9d40b0bc9dc2b"
SOURCE_LIBCD = "1300664537c49f33bbbace1fe0fb58d2463bd627"
MACRO = "VH_MAP02_CD_READ_PROBE"


def once(src, anchor, substitute):
    if src.count(anchor) != 1:
        raise ValueError(f"original pinned CD source anchor missing or ambiguous: {anchor[:90]}")
    return src.replace(anchor, substitute)


def instrument_libcd(source):
    if git_blob_sha1(source.encode("utf-8")) != SOURCE_LIBCD:
        raise ValueError("original pinned libcd.c source hash differs")
    source = once(source, '#include "PsyQ/libcd.h"',
                  '#include "PsyQ/libcd.h"\n#ifdef VH_MAP02_CD_READ_PROBE\n'
                  '#include "map02_cd_read_probe.h"\n#endif')
    anchor = '    unsigned char *out = (unsigned char *)buf;\n'
    source = once(source, anchor,
                  anchor + '#ifdef VH_MAP02_CD_READ_PROBE\n'
                  '    vh_map02_cd_read_start(s_targetLBA, sectors);\n#endif\n')
    anchor = '        memcpy(out + (size_t)i * SECTOR_DATA_SIZE, raw + SECTOR_DATA_OFFSET, SECTOR_DATA_SIZE);\n'
    source = once(source, anchor, anchor
                  + '#ifdef VH_MAP02_CD_READ_PROBE\n'
                  '        vh_map02_cd_read_sector(lba, raw + SECTOR_DATA_OFFSET);\n#endif\n')
    anchor = '    PC_LangPatchRead(s_targetLBA, sectors, out);\n'
    source = once(source, anchor, anchor
                  + '#ifdef VH_MAP02_CD_READ_PROBE\n'
                  '    vh_map02_cd_read_finish(s_targetLBA, sectors, out);\n#endif\n')
    return source


def instrument_core_cd(source):
    if git_blob_sha1(source.encode("utf-8")) != SOURCE_CD:
        raise ValueError("original pinned src/core/cd.c source hash differs")
    anchor = 'void LoadCdFile(s32 cdfIdx, s32 showLoadingScreen) {\n'
    source = once(source, anchor,
                  '#ifdef VH_MAP02_CD_READ_PROBE\n'
                  '#include "map02_cd_read_probe.h"\n#endif\n'
                  + anchor)
    anchor = ('   gCdLoader.sectorsToRead = gCdFiles[cdfIdx].sectorCt;\n'
              '   gCdLoader.sector = gCdFiles[cdfIdx].startingSector;\n')
    source = once(source, anchor, anchor
                  + '#ifdef VH_MAP02_CD_READ_PROBE\n'
                  '   vh_map02_cd_loader_claim(cdfIdx, CDF_M_MAP02_PRS,\n'
                  '       gCdFiles[cdfIdx].startingSector, gCdFiles[cdfIdx].sectorCt);\n'
                  '#endif\n')
    # The only terminal state transition for a non-VAB file is under case 7.
    anchor = '       } else {\n          gCdLoader.state = 99;\n       }\n       break;\n'
    source = once(source, anchor,
                  '       } else {\n          gCdLoader.state = 99;\n       }\n'
                  '#ifdef VH_MAP02_CD_READ_PROBE\n'
                  '       vh_map02_cd_loader_complete(gCdLoader.cdf,\n'
                  '           CDF_M_MAP02_PRS, gCdLoader.state);\n'
                  '#endif\n'
                  '       break;\n')
    return source


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pc_checkout", type=Path)
    p.add_argument("output_dir", type=Path)
    args = p.parse_args()
    root = args.pinned_pc_checkout
    output = args.output_dir
    if output.is_relative_to(root):
        p.error("instrumented originals must be written outside pinned source checkout")
    originals = {
        "libcd.c": (root / "platform/pc/src/libcd.c", instrument_libcd),
        "core_cd.c": (root / "src/core/cd.c", instrument_core_cd),
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, (path, instrumenter) in originals.items():
        (output / name).write_text(instrumenter(path.read_text(encoding="utf-8")),
                                   encoding="utf-8")
    print("Pinned original CD read/loader hooks emitted (opt-in only)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compose v69 PCSX patch with opt-in MIPS synthetic PS-X EXE CPU smoke.

Never runs retail games. Requires a unique self-authored marker in EXE
header, interpreter mode and a bounded MIPS block ending at exact
expected PC. Verifies a CPU-authored RAM completion marker after GPU
port stores. Actual GPU plugin dispatch traces audited separately.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v69_pcsx_rearmed import apply as v69_apply,once

def apply(root:Path):
    evidence=v69_apply(root)
    path=root.resolve()/"frontend/main.c"
    source=path.read_text()
    source=once(source,
        '#include "revision.h"\n',
        '#include "revision.h"\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '#include "../libpcsxcore/r3000a.h"\n'
        '#endif\n',"CPU interpreter header")
    source=once(source,
        '\tint vh69_core_smoke = 0;\n',
        '\tint vh69_core_smoke = 0;\n'
        '\tint vh70_exe_smoke = 0;\n',"v70 diagnostic option state")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh69-core-smoke"))\n'
        '\t\t\tvh69_core_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh69-core-smoke"))\n'
        '\t\t\tvh69_core_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh70-exe-smoke"))\n'
        '\t\t\tvh70_exe_smoke = 1;\n',"v70 diagnostic CLI argument")
    smoke=r"""#ifdef VH_MAP02_V66_PCSX_PROBE
	if (vh70_exe_smoke) {
		/* Diagnostics-only: don't accept unknown PS-X EXEs. */
		const unsigned int loop_expected = 0x8001004cu;
		const unsigned int ram_offset = 0x11000u;
		const unsigned int expected = 0x70000001u;
		unsigned char tag[8] = {0};
		FILE *exe = file[0] ? fopen(file, "rb") : NULL;
		int correct_tag = 0;
		if (exe != NULL) {
			if (fseek(exe, 0x4c, SEEK_SET)==0 &&
			    fread(tag, 1, sizeof(tag), exe)==sizeof(tag) &&
			    memcmp(tag, "VH70SYN!", 8)==0)
				correct_tag = 1;
			fclose(exe);
		}
		if (!correct_tag || !ready_to_go || Config.Cpu!=1 ||
		    psxRegs.pc != 0x80010000u) {
			SysPrintf("VH70_SYNTHETIC_EXE_REFUSED\n");
			ClosePlugins(); SysClose(); menu_finish(); plat_finish();
			return 2;
		}
		/* The test EXE executes its first branch (jump-to-self).
		 * Interpreter ExecuteBlock returns after that control transfer.
		 * The external runner also bounds the process with timeout. */
		psxCpu->ExecuteBlock(&psxRegs, EXEC_CALLER_OTHER);
		unsigned char *raw = (unsigned char *)psxRegs.ptrs.psxM;
		unsigned int observed =
		    (unsigned int)raw[ram_offset] |
		    ((unsigned int)raw[ram_offset+1] << 8) |
		    ((unsigned int)raw[ram_offset+2] << 16) |
		    ((unsigned int)raw[ram_offset+3] << 24);
		if (psxRegs.pc!=loop_expected || observed!=expected) {
			SysPrintf("VH70_MIPS_EXEC_REFUSED\n");
			ClosePlugins(); SysClose(); menu_finish(); plat_finish();
			return 3;
		}
		SysPrintf("VH70_MIPS_EXEC_PASS SYNTHETIC_GP0_GP1_CPU_EXE\n");
		ClosePlugins(); SysClose(); menu_finish(); plat_finish();
		return 0;
	}
#endif
"""
    source=once(source,
        '\tif (loadst_f) {\n',
        smoke+'\n\tif (loadst_f) {\n',
        "bounded MIPS CPU EXE smoke after Load")
    path.write_text(source)
    return dict(evidence,synthetic_mips_exe_runtime_gate_source_installed=True,
                actual_retail_game_boot_verified=False,
                plugin_pixel_output_verified=False,
                original_retail_MAP02_verified=False,
                HD_replacement_approved=False)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    a=p.parse_args()
    print(apply(a.checkout))
    return 0
if __name__=="__main__":raise SystemExit(main())

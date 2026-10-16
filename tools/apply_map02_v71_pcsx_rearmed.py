#!/usr/bin/env python3
"""Pin v70 source patch, append opt-in VRAM oracle for original MIPS v71 EXE."""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v70_pcsx_rearmed import apply as apply_v70
from .apply_map02_v69_pcsx_rearmed import once

CHECK_CODE=r"""#ifdef VH_MAP02_V66_PCSX_PROBE
	if (vh71_vram_smoke) {
		/* The original emulator executes only a tagged, self-authored
		 * 4-KiB PS-X EXE through its MIPS interpreter. */
		const unsigned int end_pc=0x800100e0u;
		const unsigned int marker_at=0x11000u;
		unsigned char tag[8]={0};
		FILE *exe=file[0] ? fopen(file,"rb") : NULL;
		int valid=0;
		if(exe!=NULL) {
			if(fseek(exe,0x4c,SEEK_SET)==0 &&
			   fread(tag,1,sizeof(tag),exe)==sizeof(tag) &&
			   memcmp(tag,"VH71SYN!",8)==0) valid=1;
			fclose(exe);
		}
		if(!valid || !ready_to_go || Config.Cpu!=1 ||
		   psxRegs.pc!=0x80010000u || !GPU_freeze) {
			SysPrintf("VH71_EXE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();
			return 2;
		}
		psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
		unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
		unsigned int marker=(unsigned int)ram[marker_at] |
			((unsigned int)ram[marker_at+1]<<8) |
			((unsigned int)ram[marker_at+2]<<16) |
			((unsigned int)ram[marker_at+3]<<24);
		if(psxRegs.pc!=end_pc || marker!=0x70000001u) {
			SysPrintf("VH71_MIPS_MARKER_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();
			return 3;
		}
		/* GPUfreeze SAVE flushes gpulib's pending command list and
		 * synchronizes the rasterizer. The returned pointer is
		 * native 1024x512 VRAM, *not* a screen/window pixel buffer. */
		GPUFreeze_t freeze={0};
		uint16_t *vram=NULL;
		if(GPU_freeze(1,&freeze,&vram)!=1 || vram==NULL) {
			SysPrintf("VH71_GPU_FREEZE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();
			return 4;
		}
		unsigned int checked=0,incorrect=0;
		for(unsigned int y=15;y<=21;y++) {
			for(unsigned int x=15;x<=29;x++) {
				uint16_t expected=0;
				if(y>=16 && y<20) {
					if(x>=16 && x<20)expected=0x001f;
					if(x>=24 && x<28)expected=0xfc00;
				}
				if(vram[y*1024+x]!=expected)incorrect++;
				checked++;
			}
		}
		if(incorrect!=0 || checked!=105) {
			SysPrintf("VH71_VRAM_ORACLE_REFUSED checked=%u mismatches=%u\n",
			    checked,incorrect);
			ClosePlugins();SysClose();menu_finish();plat_finish();
			return 5;
		}
		SysPrintf("VH71_VRAM_ORACLE_PASS checked=%u red=16 masked_blue=16 guard=73\n",checked);
		ClosePlugins();SysClose();menu_finish();plat_finish();
		return 0;
	}
#endif
"""
def apply(root:Path):
    info=apply_v70(root)
    frontend=root.resolve()/"frontend/main.c"
    source=frontend.read_text()
    source=once(source,'#include "../libpcsxcore/r3000a.h"\n',
        '#include "../libpcsxcore/r3000a.h"\n'
        '#include "../libpcsxcore/gpu.h"\n',"PS1 GPU freeze definition")
    source=once(source,'\tint vh70_exe_smoke = 0;\n',
        '\tint vh70_exe_smoke = 0;\n\tint vh71_vram_smoke = 0;\n',
        "diagnostic VRAM oracle option variable")
    source=once(source,'\t\telse if (!strcmp(argv[i], "--vh70-exe-smoke"))\n'
        '\t\t\tvh70_exe_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh70-exe-smoke"))\n'
        '\t\t\tvh70_exe_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh71-vram-smoke"))\n'
        '\t\t\tvh71_vram_smoke = 1;\n',"VRAM oracle diagnostic CLI flag")
    source=once(source,'#endif\n\n\tif (loadst_f) {\n',
        '#endif\n\n'+CHECK_CODE+'\n\tif (loadst_f) {\n',
        "bounded real GPU VRAM verification in diagnostic path")
    frontend.write_text(source)
    return dict(info,synthetic_gpu_vram_oracle_hook_installed=True,
        retail_gpu_hardware_parity_verified=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    a=p.parse_args()
    print(apply(a.checkout))
if __name__=="__main__":main()

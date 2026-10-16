#!/usr/bin/env python3
"""Add opt-in v75 actual GPU VRAM oracle to the pinned PCSX source adapter."""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v74_pcsx_rearmed import apply as apply_v74
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v75_indexed_stp_e2v_exe import build
def oracle_source(loop:int):
    return r"""#ifdef VH_MAP02_V66_PCSX_PROBE
	if(vh75_stp_e2v_smoke) {
		const unsigned int end_pc=VH75_END_PC;
		unsigned char tag[8]={0};
		FILE *input=file[0] ? fopen(file,"rb") : NULL;
		int tagged=0;
		if(input) {
			if(fseek(input,0x4c,SEEK_SET)==0 && fread(tag,1,8,input)==8 &&
			   memcmp(tag,"VH75SYN!",8)==0)tagged=1;
			fclose(input);
		}
		if(!tagged || !ready_to_go || Config.Cpu!=1 ||
		   psxRegs.pc!=0x80010000u || !GPU_freeze) {
			SysPrintf("VH75_EXE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 2;
		}
		psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
		unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
		unsigned int done=(unsigned int)ram[0x11000] |
		   ((unsigned int)ram[0x11001]<<8) |
		   ((unsigned int)ram[0x11002]<<16) |
		   ((unsigned int)ram[0x11003]<<24);
		if(psxRegs.pc!=end_pc || done!=0x70000001u) {
			SysPrintf("VH75_CPU_MARKER_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 3;
		}
		GPUFreeze_t state={0};
		uint16_t *vram=NULL;
		if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
			SysPrintf("VH75_GPU_FREEZE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 4;
		}
		const uint16_t colors[5]={0xbc0f,0x03e0,0xfc1f,0x7c00,0x03ff};
		const unsigned int xstarts[5]={40,56,72,88,104};
		unsigned int bad[6]={0},checked=0,wrong=0;
		for(unsigned int y=103;y<=109;y++) {
			for(unsigned int x=39;x<=111;x++) {
				uint16_t expected=0;
				unsigned int region=5;
				if(y>=104 && y<108) {
					for(unsigned int j=0;j<5;j++) {
						if(x>=xstarts[j] && x<xstarts[j]+4) {
							expected=colors[j];
							region=j;break;
						}
					}
				}
				if(vram[y*1024+x]!=expected) {
					wrong++;
					bad[region]++;
				}
				checked++;
			}
		}
		if(checked!=511 || wrong) {
			SysPrintf("VH75_VRAM_REFUSED checked=%u mismatches=%u stp4=%u nonstp=%u abr1=%u zero=%u e2v=%u guard=%u\n",
			          checked,wrong,bad[0],bad[1],bad[2],bad[3],bad[4],bad[5]);
			ClosePlugins();SysClose();menu_finish();plat_finish();return 5;
		}
		SysPrintf("VH75_VRAM_PASS checked=511 stp4=16 nonstp=16 abr1=16 zero=16 e2v=16 guard=431\n");
		ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
	}
#endif
""".replace("VH75_END_PC",f"0x{loop:08x}u")
def apply(root:Path):
    proof=apply_v74(root)
    frontend=root.resolve()/"frontend/main.c"
    src=frontend.read_text()
    src=once(src,"\tint vh74_indexed_smoke = 0;\n",
        "\tint vh74_indexed_smoke = 0;\n\tint vh75_stp_e2v_smoke = 0;\n",
        "v75 diagnostic control declaration")
    src=once(src,
        '\t\telse if (!strcmp(argv[i], "--vh74-indexed-clut-smoke"))\n'
        '\t\t\tvh74_indexed_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh74-indexed-clut-smoke"))\n'
        '\t\t\tvh74_indexed_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh75-stp-e2v-smoke"))\n'
        '\t\t\tvh75_stp_e2v_smoke = 1;\n',
        "v75 opt-in CLI")
    _,end,_=build()
    src=once(src,"#endif\n\n\tif (loadst_f) {\n",
        "#endif\n\n"+oracle_source(end)+"\n\tif (loadst_f) {\n",
        "native indexed STP ABR/E2V VRAM readback")
    frontend.write_text(src)
    return dict(proof,synthetic_indexed_stp_abr_e2v_pixel_oracle_source_installed=True,
                retail_ps1_pixel_parity_verified=False,
                original_retail_MAP02_verified=False,
                HD_replacement_approved=False)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    options=p.parse_args()
    print(apply(options.checkout))
    return 0
if __name__=="__main__":raise SystemExit(main())

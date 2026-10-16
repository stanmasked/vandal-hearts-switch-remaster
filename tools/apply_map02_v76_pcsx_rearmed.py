#!/usr/bin/env python3
"""Extend pinned real PCSX with ordered FT4/CLUT and GP0(E1/E2/E6) VRAM oracle."""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v75_pcsx_rearmed import apply as apply_v75
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v76_gpu_state_order_exe import build,REGIONS
def oracle_source(loop:int):
    expected=",".join(f"0x{color:04x}" for _,x,color in REGIONS)
    xcoords=",".join(str(x) for _,x,color in REGIONS)
    return r"""#ifdef VH_MAP02_V66_PCSX_PROBE
	if(vh76_gpu_state_smoke) {
		const unsigned int end_pc=VH76_END_PC;
		unsigned char tag[8]={0};
		FILE *prog=file[0] ? fopen(file,"rb") : NULL;
		int valid=0;
		if(prog) {
			if(fseek(prog,0x4c,SEEK_SET)==0 &&
			   fread(tag,1,8,prog)==8 &&
			   memcmp(tag,"VH76SYN!",8)==0)valid=1;
			fclose(prog);
		}
		if(!valid || !ready_to_go || Config.Cpu!=1 ||
		   psxRegs.pc!=0x80010000u || !GPU_freeze) {
			SysPrintf("VH76_EXE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 2;
		}
		psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
		unsigned char *mem=(unsigned char *)psxRegs.ptrs.psxM;
		unsigned int marker=(unsigned int)mem[0x11000] |
		  ((unsigned int)mem[0x11001]<<8) |
		  ((unsigned int)mem[0x11002]<<16) |
		  ((unsigned int)mem[0x11003]<<24);
		if(psxRegs.pc!=end_pc || marker!=0x70000001u) {
			SysPrintf("VH76_CPU_MARKER_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 3;
		}
		GPUFreeze_t freeze={0};
		uint16_t *vram=NULL;
		if(GPU_freeze(1,&freeze,&vram)!=1 || !vram) {
			SysPrintf("VH76_FREEZE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 4;
		}
		const uint16_t colors[11]={VH76_EXPECTED_COLORS};
		const unsigned int starts[11]={VH76_X_COORDS};
		unsigned int failures[12]={0},total_bad=0,checked=0;
		for(unsigned int y=127;y<=133;y++) {
			for(unsigned int x=39;x<=204;x++) {
				unsigned int region=11;
				uint16_t wanted=0;
				if(y>=128 && y<132) {
					for(unsigned int i=0;i<11;i++) {
						if(x>=starts[i] && x<starts[i]+4) {
							region=i;
							wanted=colors[i];
							break;
						}
					}
				}
				if(vram[y*1024+x]!=wanted) {
					failures[region]++;
					total_bad++;
				}
				checked++;
			}
		}
		if(checked!=1162 || total_bad) {
			SysPrintf("VH76_VRAM_REFUSED checked=%u mismatches=%u order_rg=%u order_gr=%u clutA=%u clutB=%u e2set=%u e2reset=%u e6mask=%u e6reset=%u e1abr0=%u e1abr1=%u e1reset=%u guard=%u\n",
			 checked,total_bad,failures[0],failures[1],failures[2],failures[3],
			 failures[4],failures[5],failures[6],failures[7],failures[8],
			 failures[9],failures[10],failures[11]);
			ClosePlugins();SysClose();menu_finish();plat_finish();return 5;
		}
		SysPrintf("VH76_VRAM_PASS checked=1162 regions=11 region_pixels=176 guard=986\n");
		ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
	}
#endif
""".replace("VH76_END_PC",f"0x{loop:08x}u").replace(
    "VH76_EXPECTED_COLORS",expected).replace("VH76_X_COORDS",xcoords)
def apply(root:Path):
    proof=apply_v75(root)
    f=root.resolve()/"frontend/main.c"
    s=f.read_text()
    s=once(s,"\tint vh75_stp_e2v_smoke = 0;\n",
           "\tint vh75_stp_e2v_smoke = 0;\n\tint vh76_gpu_state_smoke = 0;\n",
           "diagnostic option storage")
    s=once(s,
        '\t\telse if (!strcmp(argv[i], "--vh75-stp-e2v-smoke"))\n'
        '\t\t\tvh75_stp_e2v_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh75-stp-e2v-smoke"))\n'
        '\t\t\tvh75_stp_e2v_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh76-gpu-state-smoke"))\n'
        '\t\t\tvh76_gpu_state_smoke = 1;\n',
        "GPU state smoke CLI")
    _,end,_=build()
    s=once(s,"#endif\n\n\tif (loadst_f) {\n",
           "#endif\n\n"+oracle_source(end)+"\n\tif (loadst_f) {\n",
           "real GPU E1 E2 E6 ordered state oracle")
    f.write_text(s)
    return dict(proof,synthetic_gp0_ordered_state_vram_oracle_installed=True,
                actual_retail_map02_output_verified=False,
                original_retail_MAP02_verified=False,
                HD_replacement_approved=False)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    a=p.parse_args()
    print(apply(a.checkout))
    return 0
if __name__=="__main__":raise SystemExit(main())

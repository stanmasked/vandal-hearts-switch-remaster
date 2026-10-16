#!/usr/bin/env python3
"""Install v73 genuine CPU+GPU VRAM oracle on pinned PCSX ReARMed."""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v72_pcsx_rearmed import apply as apply_v72
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v73_uv_tpage_mips_exe import build

def oracle_source(loop:int):
    return r"""#ifdef VH_MAP02_V66_PCSX_PROBE
	if(vh73_uv_diagonal_smoke) {
		const unsigned int end_pc=VH73_END_PC;
		unsigned char tag[8]={0};
		FILE *input=file[0] ? fopen(file,"rb") : NULL;
		int trusted_fixture=0;
		if(input) {
			if(fseek(input,0x4c,SEEK_SET)==0 && fread(tag,1,8,input)==8 &&
			   memcmp(tag,"VH73SYN!",8)==0) trusted_fixture=1;
			fclose(input);
		}
		if(!trusted_fixture || !ready_to_go || Config.Cpu!=1 ||
		   psxRegs.pc!=0x80010000u || !GPU_freeze) {
			SysPrintf("VH73_EXE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 2;
		}
		psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
		unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
		unsigned int observed=(unsigned int)ram[0x11000] |
		  ((unsigned int)ram[0x11001]<<8) |
		  ((unsigned int)ram[0x11002]<<16) |
		  ((unsigned int)ram[0x11003]<<24);
		if(psxRegs.pc!=end_pc || observed!=0x70000001u) {
			SysPrintf("VH73_CPU_MARKER_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 3;
		}
		GPUFreeze_t gpu_state={0};
		uint16_t *vram=NULL;
		if(GPU_freeze(1,&gpu_state,&vram)!=1 || !vram) {
			SysPrintf("VH73_GPU_FREEZE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 4;
		}
		const uint16_t stripes[4]={0x001f,0x7c00,0x001f,0x7c00};
		const uint16_t second_page[4]={0x03ff,0x7fe0,0x7c1f,0x4210};
		unsigned int mismatch=0,first=0,second=0,seam=0,guard=0,checked=0;
		for(unsigned int y=55;y<=61;y++) {
			for(unsigned int x=39;x<=95;x++) {
				uint16_t expected=0;
				unsigned int region=0;
				if(y>=56 && y<60) {
					if(x>=40 && x<44){expected=stripes[x-40];region=1;}
					if(x>=72 && x<76){expected=second_page[x-72];region=2;}
					if(x>=88 && x<92){expected=0xbc0f;region=3;}
				}
				if(vram[y*1024+x]!=expected) {
					mismatch++;
					if(region==1)first++;
					else if(region==2)second++;
					else if(region==3)seam++;
					else guard++;
				}
				checked++;
			}
		}
		if(checked!=399 || mismatch) {
			SysPrintf("VH73_VRAM_REFUSED checked=%u mismatches=%u uv=%u tpage=%u diagonal=%u guard=%u\n",
			          checked,mismatch,first,second,seam,guard);
			ClosePlugins();SysClose();menu_finish();plat_finish();return 5;
		}
		SysPrintf("VH73_VRAM_PASS checked=399 uv=16 tpage=16 diagonal=16 guard=351\n");
		ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
	}
#endif
""".replace("VH73_END_PC",f"0x{loop:08x}u")

def apply(root:Path):
    evidence=apply_v72(root)
    path=root.resolve()/"frontend/main.c"
    s=path.read_text()
    s=once(s,"\tint vh72_ft4_smoke = 0;\n",
        "\tint vh72_ft4_smoke = 0;\n\tint vh73_uv_diagonal_smoke = 0;\n",
        "v73 CLI flag")
    s=once(s,
        '\t\telse if (!strcmp(argv[i], "--vh72-ft4-smoke"))\n'
        '\t\t\tvh72_ft4_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh72-ft4-smoke"))\n'
        '\t\t\tvh72_ft4_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh73-uv-diagonal-smoke"))\n'
        '\t\t\tvh73_uv_diagonal_smoke = 1;\n',
        "v73 GPU diagnostics option")
    _,loop,_=build()
    s=once(s,"#endif\n\n\tif (loadst_f) {\n",
           "#endif\n\n"+oracle_source(loop)+"\n\tif (loadst_f) {\n",
           "native renderer UV/tpage/seam readback")
    path.write_text(s)
    return dict(evidence,synthetic_uv_tpage_ft3_vram_oracle_source_installed=True,
                authentic_ps1_retail_pixel_parity_verified=False,
                original_retail_MAP02_verified=False,
                HD_replacement_approved=False)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    a=p.parse_args()
    print(apply(a.checkout))
    return 0
if __name__=="__main__":
    raise SystemExit(main())

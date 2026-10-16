#!/usr/bin/env python3
"""Extend pinned v73 PCSX with true 4bpp/8bpp CLUT/E2 GPU VRAM pixel oracle."""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v73_pcsx_rearmed import apply as apply_v73
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v74_indexed_clut_exe import build
def oracle_source(loop:int):
    return r"""#ifdef VH_MAP02_V66_PCSX_PROBE
	if(vh74_indexed_smoke) {
		const unsigned int expected_pc=VH74_END_PC;
		unsigned char tag[8]={0};
		FILE *exe=file[0] ? fopen(file,"rb") : NULL;
		int match=0;
		if(exe) {
			if(fseek(exe,0x4c,SEEK_SET)==0 && fread(tag,1,8,exe)==8 &&
			   memcmp(tag,"VH74SYN!",8)==0)match=1;
			fclose(exe);
		}
		if(!match || !ready_to_go || Config.Cpu!=1 ||
		   psxRegs.pc!=0x80010000u || !GPU_freeze) {
			SysPrintf("VH74_EXE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 2;
		}
		psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
		unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
		unsigned int marker=(unsigned int)ram[0x11000] |
		  ((unsigned int)ram[0x11001]<<8) |
		  ((unsigned int)ram[0x11002]<<16) |
		  ((unsigned int)ram[0x11003]<<24);
		if(psxRegs.pc!=expected_pc || marker!=0x70000001u) {
			SysPrintf("VH74_MIPS_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 3;
		}
		GPUFreeze_t snapshot={0};
		uint16_t *vram=NULL;
		if(GPU_freeze(1,&snapshot,&vram)!=1 || !vram) {
			SysPrintf("VH74_FREEZE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 4;
		}
		const uint16_t clut4[4]={0x001f,0x03e0,0x7c00,0x7fff};
		const uint16_t clut8[4]={0x4210,0x7c1f,0x7fe0,0x03ff};
		const uint16_t window[4]={0x03ff,0x7fe0,0x7c1f,0x4210};
		const uint16_t transparent[4]={0x7c00,0x001f,0x03e0,0x7c00};
		unsigned int wrong=0,checked=0;
		unsigned int wrong4=0,wrong8=0,wrongwin=0,wrongtrans=0,wrongguard=0;
		for(unsigned int y=79;y<=85;y++) {
			for(unsigned int x=39;x<=95;x++) {
				uint16_t expected=0;
				unsigned int zone=0;
				if(y>=80 && y<84) {
					if(x>=40 && x<44){expected=clut4[x-40];zone=1;}
					if(x>=56 && x<60){expected=clut8[x-56];zone=2;}
					if(x>=72 && x<76){expected=window[x-72];zone=3;}
					if(x>=88 && x<92){expected=transparent[x-88];zone=4;}
				}
				if(vram[y*1024+x]!=expected) {
					wrong++;
					switch(zone) {
						case 1:wrong4++;break;
						case 2:wrong8++;break;
						case 3:wrongwin++;break;
						case 4:wrongtrans++;break;
						default:wrongguard++;break;
					}
				}
				checked++;
			}
		}
		if(wrong || checked!=399) {
			SysPrintf("VH74_VRAM_REFUSED checked=%u mismatches=%u clut4=%u clut8=%u window=%u transparent=%u guard=%u\n",
			          checked,wrong,wrong4,wrong8,wrongwin,wrongtrans,wrongguard);
			ClosePlugins();SysClose();menu_finish();plat_finish();return 5;
		}
		SysPrintf("VH74_VRAM_PASS checked=399 clut4=16 clut8=16 window=16 transparent=16 guard=335\n");
		ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
	}
#endif
""".replace("VH74_END_PC",f"0x{loop:08x}u")
def apply(root:Path):
    evidence=apply_v73(root)
    main=root.resolve()/"frontend/main.c"
    s=main.read_text()
    s=once(s,"\tint vh73_uv_diagonal_smoke = 0;\n",
        "\tint vh73_uv_diagonal_smoke = 0;\n\tint vh74_indexed_smoke = 0;\n",
        "v74 local diagnostic flag")
    s=once(s,
        '\t\telse if (!strcmp(argv[i], "--vh73-uv-diagonal-smoke"))\n'
        '\t\t\tvh73_uv_diagonal_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh73-uv-diagonal-smoke"))\n'
        '\t\t\tvh73_uv_diagonal_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh74-indexed-clut-smoke"))\n'
        '\t\t\tvh74_indexed_smoke = 1;\n',
        "v74 opt-in CLI selection")
    _,pc,_=build()
    s=once(s,"#endif\n\n\tif (loadst_f) {\n",
        "#endif\n\n"+oracle_source(pc)+"\n\tif (loadst_f) {\n",
        "real indexed-CLUT GPU VRAM readback")
    main.write_text(s)
    return dict(evidence,synthetic_4bpp_8bpp_clut_and_e2_gpu_pixel_oracle_source_installed=True,
                authentic_retail_gpu_pixel_parity_verified=False,
                original_retail_MAP02_verified=False,
                HD_replacement_approved=False)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    options=p.parse_args()
    print(apply(options.checkout))
if __name__=="__main__":raise SystemExit(main())

#!/usr/bin/env python3
"""v72 pinned PCSX ReARMed source patch: real MIPS GP0(A0)+FT4 VRAM oracle."""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v71_pcsx_rearmed import apply as apply_v71
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v72_ft4_mips_exe import build,START,MAGIC

def oracle_source(loop:int):
    return r"""#ifdef VH_MAP02_V66_PCSX_PROBE
	if (vh72_ft4_smoke) {
		const unsigned int last_pc=V72_EXPECTED_LOOP_PC;
		const unsigned int marker_addr=0x11000u;
		const unsigned int marker_value=0x70000001u;
		unsigned char tag[8]={0};
		FILE *program=file[0] ? fopen(file,"rb") : NULL;
		int tagged=0;
		if(program!=NULL) {
			if(fseek(program,0x4c,SEEK_SET)==0 &&
			   fread(tag,1,8,program)==8 &&
			   memcmp(tag,"VH72SYN!",8)==0)tagged=1;
			fclose(program);
		}
		if(!tagged || !ready_to_go || Config.Cpu!=1 ||
		   psxRegs.pc!=0x80010000u || !GPU_freeze) {
			SysPrintf("VH72_EXE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();
			return 2;
		}
		/* Actual original PCSX emulator MIPS interpreter execution. */
		psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
		unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
		unsigned int marker=(unsigned int)ram[marker_addr] |
		  ((unsigned int)ram[marker_addr+1]<<8) |
		  ((unsigned int)ram[marker_addr+2]<<16) |
		  ((unsigned int)ram[marker_addr+3]<<24);
		if(psxRegs.pc!=last_pc || marker!=marker_value) {
			SysPrintf("VH72_MIPS_MARKER_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();
			return 3;
		}
		/* GPUfreeze SAVE synchronizes GPU pipeline and gives the actual
		 * original gpulib 1024x512 native 16-bit VRAM pointer. */
		GPUFreeze_t snapshot={0};
		uint16_t *vram=NULL;
		if(GPU_freeze(1,&snapshot,&vram)!=1 || !vram) {
			SysPrintf("VH72_GPU_FREEZE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();
			return 4;
		}
		unsigned int checked=0,wrong=0;
		unsigned int opaque_bad=0,stp0_bad=0,no_stp_bad=0,stp1_bad=0;
		for(unsigned int y=31;y<=37;y++) {
			for(unsigned int x=63;x<=116;x++) {
				uint16_t expected=0;
				unsigned int zone=0;
				if(y>=32 && y<36) {
					if(x>=64 && x<68){expected=0x001fu;zone=1;}
					if(x>=80 && x<84){expected=0xbc0fu;zone=2;}
					if(x>=96 && x<100){expected=0x001fu;zone=3;}
					if(x>=112 && x<116){expected=0xfc1fu;zone=4;}
				}
				if(vram[y*1024+x]!=expected) {
					wrong++;
					if(zone==1)opaque_bad++;
					if(zone==2)stp0_bad++;
					if(zone==3)no_stp_bad++;
					if(zone==4)stp1_bad++;
				}
				checked++;
			}
		}
		if(checked!=378 || wrong) {
			SysPrintf("VH72_FT4_VRAM_REFUSED checked=%u mismatches=%u opaque=%u abr0=%u no_stp=%u abr1=%u\n",
			          checked,wrong,opaque_bad,stp0_bad,no_stp_bad,stp1_bad);
			ClosePlugins();SysClose();menu_finish();plat_finish();
			return 5;
		}
		SysPrintf("VH72_FT4_VRAM_PASS checked=378 opaque=16 abr0=16 no_stp=16 abr1=16 guard=314\n");
		ClosePlugins();SysClose();menu_finish();plat_finish();
		return 0;
	}
#endif
""".replace("V72_EXPECTED_LOOP_PC",f"0x{loop:08x}u")

def apply(root:Path):
    evidence=apply_v71(root)
    source_path=root.resolve()/"frontend/main.c"
    source=source_path.read_text()
    source=once(source,"\tint vh71_vram_smoke = 0;\n",
        "\tint vh71_vram_smoke = 0;\n\tint vh72_ft4_smoke = 0;\n",
        "v72 diagnostics flag declaration")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh71-vram-smoke"))\n'
        '\t\t\tvh71_vram_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh71-vram-smoke"))\n'
        '\t\t\tvh71_vram_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh72-ft4-smoke"))\n'
        '\t\t\tvh72_ft4_smoke = 1;\n',"v72 diagnostics CLI")
    _,loop,_=build()
    source=once(source,"#endif\n\n\tif (loadst_f) {\n",
        "#endif\n\n"+oracle_source(loop)+"\n\tif (loadst_f) {\n",
        "native GP0 FT4 texture/ABR pixel oracle")
    source_path.write_text(source)
    return dict(evidence,synthetic_ft4_vram_oracle_source_installed=True,
                authentic_retail_gpu_pixel_parity_verified=False,
                original_retail_MAP02_verified=False,
                HD_replacement_approved=False)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    args=p.parse_args()
    print(apply(args.checkout))
    return 0
if __name__=="__main__":
    raise SystemExit(main())

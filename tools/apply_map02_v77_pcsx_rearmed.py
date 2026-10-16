#!/usr/bin/env python3
"""Install four bounded in-process MIPS CPU phases and native PCSX VRAM checks."""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v76_pcsx_rearmed import apply as apply_v76
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v77_gpu_multiphase_exe import build

def oracle_source(stops):
    positions=",".join(f"0x{p:08x}u" for p in stops)
    return r"""#ifdef VH_MAP02_V66_PCSX_PROBE
	if(vh77_multiphase_smoke) {
		const uint32_t stop_pc[4]={VH77_STOP_PCS};
		const uint32_t marker[4]={
			0x77010001u,0x77010002u,0x77010003u,0x77010004u
		};
		const uint32_t expect_reg[4][3]={
			{0xe1000020u,0xe2000401u,0xe6000001u},
			{0xe1000020u,0xe2000401u,0xe6000001u},
			{0xe1000020u,0xe2000401u,0xe6000001u},
			{0xe1000000u,0xe2000000u,0xe6000000u}
		};
		const uint16_t colors[4][6]={
			{0x7c00,0x7c00,0x7c00,0x7c00,0x7c00,0x7c00},
			{0xfc1f,0x801f,0x7c00,0x7c00,0x7c00,0x7c00},
			{0xfc1f,0x801f,0xfc1f,0x801f,0x7c00,0x7c00},
			{0xfc1f,0x801f,0xfc1f,0x801f,0xbde0,0x001f}
		};
		const uint32_t xbase[6]={40,56,72,88,104,120};
		unsigned char tag[8]={0};
		FILE *exe=file[0] ? fopen(file,"rb") : NULL;
		int signed_fixture=0;
		if(exe) {
			if(fseek(exe,0x4c,SEEK_SET)==0 &&
			   fread(tag,1,8,exe)==8 &&
			   memcmp(tag,"VH77SYN!",8)==0)signed_fixture=1;
			fclose(exe);
		}
		if(!signed_fixture || !ready_to_go || Config.Cpu!=1 ||
		   psxRegs.pc!=0x80010000u || !GPU_freeze) {
			SysPrintf("VH77_EXE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 2;
		}
		unsigned int total_samples=0,frame_count=0;
		unsigned int observed_register_mismatches=0;
		/* Four separate ExecuteBlock() calls in this SAME emulator
		 * process. No SysReset, game reload or renderer replacement
		 * between the captures. NOT a hardware VBlank assertion. */
		for(unsigned int phase=0;phase<4;phase++) {
			psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
			unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
			unsigned int at=0x11000+4*phase;
			uint32_t got=(uint32_t)ram[at] |
			  ((uint32_t)ram[at+1]<<8) |
			  ((uint32_t)ram[at+2]<<16) |
			  ((uint32_t)ram[at+3]<<24);
			if(psxRegs.pc!=stop_pc[phase] || got!=marker[phase]) {
				SysPrintf("VH77_MIPS_PHASE_REFUSED phase=%u\n",phase);
				ClosePlugins();SysClose();menu_finish();plat_finish();return 3;
			}
			GPUFreeze_t state={0};
			uint16_t *vram=NULL;
			if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
				SysPrintf("VH77_GPU_FREEZE_REFUSED phase=%u\n",phase);
				ClosePlugins();SysClose();menu_finish();plat_finish();return 4;
			}
			unsigned int mismatches[7]={0},checked=0,wrong=0;
			for(unsigned int y=159;y<=165;y++) {
				for(unsigned int x=39;x<=123;x++) {
					uint16_t expected=0;
					unsigned int region=6;
					if(y>=160 && y<164) {
						for(unsigned int i=0;i<6;i++) {
							if(x>=xbase[i] && x<xbase[i]+4) {
								expected=colors[phase][i];
								region=i;
								break;
							}
						}
					}
					if(vram[y*1024+x]!=expected) {
						mismatches[region]++;
						wrong++;
					}
					checked++;
				}
			}
			/* Pixel-level check takes precedence over state-register
			 * assertions so mutated GP1 writes cannot pass a test
			 * merely because their trace has the expected shape. */
			if(checked!=595 || wrong) {
				SysPrintf("VH77_VRAM_REFUSED phase=%u checked=%u mismatches=%u sprite1=%u tile1=%u sprite2=%u tile2=%u sprite3=%u tile3=%u guard=%u\n",
				  phase,checked,wrong,mismatches[0],mismatches[1],
				  mismatches[2],mismatches[3],mismatches[4],
				  mismatches[5],mismatches[6]);
				ClosePlugins();SysClose();menu_finish();plat_finish();return 5;
			}
			const unsigned int ids[3]={0xe1,0xe2,0xe6};
			for(unsigned int i=0;i<3;i++) {
				if(state.ulControl[ids[i]]!=expect_reg[phase][i]) {
					/* Retain a proof of register differences, but first
					 * expose their consequence in a later VRAM sample. */
					observed_register_mismatches++;
					SysPrintf("VH77_GPU_STATE_OBSERVED_MISMATCH phase=%u reg=%u\n",
					  phase,ids[i]);
				}
			}
			SysPrintf("VH77_PHASE_PASS phase=%u checked=595 guard=499\n",phase);
			total_samples+=checked;
			frame_count++;
		}
		if(frame_count!=4 || total_samples!=2380) {
			SysPrintf("VH77_AGGREGATE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 7;
		}
		if(observed_register_mismatches!=0) {
			SysPrintf("VH77_GPU_STATE_REFUSED count=%u\n",observed_register_mismatches);
			ClosePlugins();SysClose();menu_finish();plat_finish();return 6;
		}
		SysPrintf("VH77_MULTIPHASE_PASS phases=4 samples=2380 gpu_fifo_reset_kept_state=1 gpu_full_reset_cleared_state=1\n");
		ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
	}
#endif
""".replace("VH77_STOP_PCS",positions)

def apply(root:Path):
    previous=apply_v76(root)
    path=root.resolve()/"frontend/main.c"
    source=path.read_text()
    source=once(source,"\tint vh76_gpu_state_smoke = 0;\n",
        "\tint vh76_gpu_state_smoke = 0;\n\tint vh77_multiphase_smoke = 0;\n",
        "v77 diagnostic flag")
    source=once(source,
        '\t\telse if (!strcmp(argv[i], "--vh76-gpu-state-smoke"))\n'
        '\t\t\tvh76_gpu_state_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh76-gpu-state-smoke"))\n'
        '\t\t\tvh76_gpu_state_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh77-multiphase-smoke"))\n'
        '\t\t\tvh77_multiphase_smoke = 1;\n',
        "v77 runtime argument")
    _,stops,_,_=build()
    source=once(source,"#endif\n\n\tif (loadst_f) {\n",
        "#endif\n\n"+oracle_source(stops)+"\n\tif (loadst_f) {\n",
        "v77 in-process frame-like CPU/GPU oracle")
    path.write_text(source)
    return dict(previous,multiphase_gpu_state_and_vram_test_installed=True,
                physical_gpu_vblank_boundaries_observed=False,
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

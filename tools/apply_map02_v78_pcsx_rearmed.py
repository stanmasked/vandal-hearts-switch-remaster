#!/usr/bin/env python3
"""Instrument real pinned PCSX rcnt VBlank callbacks and compare VRAM per event.

Uses the exact SOURCE sites of GPU_vBlank(1,0) and GPU_vBlank(0,field),
never calls psxRcntUpdate()/GPU_vBlank() from a diagnostic. MIPS execution
drives the native emulator scheduler. This is **emulated** VBlank only.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v77_pcsx_rearmed import apply as apply_v77
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v77_gpu_multiphase_exe import build

def vblank_source(stops):
    last=stops[-1]
    return r"""#ifdef VH_MAP02_V66_PCSX_PROBE
/* Core's real psxRcntUpdate calls this only after a genuine GPU_vBlank.
 * This source-only optional diagnostic does not synthesize timer events.
 * The bounded ring drops nothing; an overflow is a hard failure. */
static unsigned int vh78_rcnt_events=0;
static unsigned int vh78_rcnt_cycle[8]={0};
static unsigned int vh78_rcnt_hsync[8]={0};
static unsigned int vh78_rcnt_type[8]={0};
static int vh78_rcnt_overflow=0;
void vh78_rcnt_vblank_observe(unsigned int cycle,
                              unsigned int hsync, unsigned int start)
{
    unsigned int n=vh78_rcnt_events;
    if(n>=8) { vh78_rcnt_overflow=1; return; }
    vh78_rcnt_cycle[n]=cycle;
    vh78_rcnt_hsync[n]=hsync;
    vh78_rcnt_type[n]=start;
    vh78_rcnt_events=n+1;
}
#endif

"""

def smoke_source(stops):
    return r"""#ifdef VH_MAP02_V66_PCSX_PROBE
	if(vh78_rcnt_vblank_smoke) {
		const unsigned int finish_pc=VH78_LAST_PC;
		const unsigned int expected_marker=0x77010004u;
		const uint16_t expected_rgb[6]={
			0xfc1f,0x801f,0xfc1f,0x801f,0xbde0,0x001f
		};
		const unsigned int xstarts[6]={40,56,72,88,104,120};
		unsigned char tag[8]={0};
		FILE *input=file[0]?fopen(file,"rb"):NULL;
		int tagged=0;
		if(input) {
			if(fseek(input,0x4c,SEEK_SET)==0 &&
			   fread(tag,1,8,input)==8 &&
			   memcmp(tag,"VH77SYN!",8)==0)tagged=1;
			fclose(input);
		}
		if(!tagged || !ready_to_go || Config.Cpu!=1 ||
		   psxRegs.pc!=0x80010000u || !GPU_freeze) {
			SysPrintf("VH78_EXE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 2;
		}
		/* Run all four source-authored v77 MIPS phases once, normally;
		 * then let the LAST MIPS branch-to-self execute further, so
		 * PS1 cycles actually advance into the core's scheduler. */
		for(unsigned int phase=0;phase<4;phase++) {
			psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
		}
		unsigned char *ram=(unsigned char *)psxRegs.ptrs.psxM;
		uint32_t got=(uint32_t)ram[0x1100c] |
		  ((uint32_t)ram[0x1100d]<<8) |
		  ((uint32_t)ram[0x1100e]<<16) |
		  ((uint32_t)ram[0x1100f]<<24);
		if(psxRegs.pc!=finish_pc || got!=expected_marker) {
			SysPrintf("VH78_MIPS_PRECONDITION_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 3;
		}
		/* Before VBlank: freeze must match known native PCSX scene.
		 * Afterwards, 4 actual scheduler callbacks must leave all
		 * 595 pixels and E1/E2/E6 GPU state untouched. */
		vh78_rcnt_events=0;
		vh78_rcnt_overflow=0;
		unsigned int checked=0,previous_cycle=psxRegs.cycle;
		for(unsigned int checkpoint=0;checkpoint<=4;checkpoint++) {
			if(checkpoint>0) {
				const unsigned int budget=vh78_short_budget?1000:800000;
				unsigned int steps=0;
				while(vh78_rcnt_events<checkpoint && steps<budget) {
					psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
					steps++;
				}
				if(vh78_rcnt_events!=checkpoint || vh78_rcnt_overflow ||
				   psxRegs.pc!=finish_pc) {
					SysPrintf("VH78_VBLANK_MISSING_REFUSED event=%u seen=%u\n",
					  checkpoint,vh78_rcnt_events);
					ClosePlugins();SysClose();menu_finish();plat_finish();return 4;
				}
				const unsigned int n=checkpoint-1;
				unsigned int expected_type=(n%2==0)?1:0;
				unsigned int expected_hsync=expected_type?240:0;
				unsigned int cycle=vh78_rcnt_cycle[n];
				unsigned int observed_hsync=vh78_rcnt_hsync[n];
				if(vh78_rcnt_type[n]!=expected_type ||
				   observed_hsync!=expected_hsync ||
				   cycle<=previous_cycle ||
				   (unsigned int)(psxRegs.cycle-cycle)>4096u) {
					SysPrintf("VH78_VBLANK_ORDER_REFUSED event=%u\n",n);
					ClosePlugins();SysClose();menu_finish();plat_finish();return 5;
				}
				previous_cycle=cycle;
				SysPrintf("VH78_VBLANK_OBSERVED ordinal=%u edge=%u hsync=%u cycle=%u\n",
				  n,expected_type,observed_hsync,cycle);
			}
			GPUFreeze_t state={0};
			uint16_t *vram=NULL;
			if(GPU_freeze(1,&state,&vram)!=1 || !vram) {
				SysPrintf("VH78_GPU_FREEZE_REFUSED checkpoint=%u\n",checkpoint);
				ClosePlugins();SysClose();menu_finish();plat_finish();return 6;
			}
			unsigned int bad=0,local=0;
			for(unsigned int y=159;y<=165;y++) {
				for(unsigned int x=39;x<=123;x++) {
					uint16_t expect=0;
					if(y>=160 && y<164) {
						for(unsigned int k=0;k<6;k++) {
							if(x>=xstarts[k] && x<xstarts[k]+4) {
								expect=expected_rgb[k];break;
							}
						}
					}
					if(vram[y*1024+x]!=expect)bad++;
					local++;
				}
			}
			if(local!=595 || bad) {
				SysPrintf("VH78_VRAM_REFUSED checkpoint=%u checked=%u mismatches=%u\n",
				  checkpoint,local,bad);
				ClosePlugins();SysClose();menu_finish();plat_finish();return 7;
			}
			if(state.ulControl[0xe1]!=0xe1000000u ||
			   state.ulControl[0xe2]!=0xe2000000u ||
			   state.ulControl[0xe6]!=0xe6000000u) {
				SysPrintf("VH78_STATE_REFUSED checkpoint=%u\n",checkpoint);
				ClosePlugins();SysClose();menu_finish();plat_finish();return 8;
			}
			checked+=local;
			SysPrintf("VH78_VRAM_CHECKPOINT_PASS checkpoint=%u checked=595\n",checkpoint);
		}
		if(checked!=2975 || vh78_rcnt_events!=4 || vh78_rcnt_overflow) {
			SysPrintf("VH78_AGGREGATE_REFUSED\n");
			ClosePlugins();SysClose();menu_finish();plat_finish();return 9;
		}
		SysPrintf("VH78_REAL_SCHEDULER_PASS vblank_starts=2 vblank_ends=2 snapshots=5 pixels=2975\n");
		ClosePlugins();SysClose();menu_finish();plat_finish();return 0;
	}
#endif
""".replace("VH78_LAST_PC",f"0x{stops[-1]:08x}u")

def apply(root:Path):
    result=apply_v77(root)
    repo=root.resolve()
    counter_file=repo/"libpcsxcore/psxcounters.c"
    src=counter_file.read_text()
    src=once(src,'#include "psxcounters.h"\n',
      '#include "psxcounters.h"\n'
      '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
      'extern void vh78_rcnt_vblank_observe(unsigned int cycle,\n'
      '                                      unsigned int hsync, unsigned int start);\n'
      '#endif\n',"scheduler hook guarded declaration")
    src=once(src,"            GPU_vBlank( 1, 0 );\n",
       "            GPU_vBlank( 1, 0 );\n"
       "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
       "            vh78_rcnt_vblank_observe(psxRegs.cycle,(unsigned int)hSyncCount,1);\n"
       "#endif\n","real VBlank rising edge after plugin callback")
    src=once(src,"            GPU_vBlank(0, field);\n",
       "            GPU_vBlank(0, field);\n"
       "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
       "            vh78_rcnt_vblank_observe(psxRegs.cycle,(unsigned int)hSyncCount,0);\n"
       "#endif\n","real VBlank falling edge after plugin callback")
    counter_file.write_text(src)
    main=repo/"frontend/main.c"
    frontend=main.read_text()
    frontend=once(frontend,
      '#include "revision.h"\\n',
      '#include "revision.h"\\n'+vblank_source(build()[1]),
      "frontend receipt hook symbol and monotonic bounded ring")
    frontend=once(frontend,
      "\tint vh77_multiphase_smoke = 0;\n",
      "\tint vh77_multiphase_smoke = 0;\n"
      "\tint vh78_rcnt_vblank_smoke = 0;\n"
      "\tint vh78_short_budget = 0;\n",
      "v78 CLI diagnostic selection")
    frontend=once(frontend,
       '\t\telse if (!strcmp(argv[i], "--vh77-multiphase-smoke"))\n'
       '\t\t\tvh77_multiphase_smoke = 1;\n',
       '\t\telse if (!strcmp(argv[i], "--vh77-multiphase-smoke"))\n'
       '\t\t\tvh77_multiphase_smoke = 1;\n'
       '\t\telse if (!strcmp(argv[i], "--vh78-rcnt-vblank-smoke"))\n'
       '\t\t\tvh78_rcnt_vblank_smoke = 1;\n'
       '\t\telse if (!strcmp(argv[i], "--vh78-short-budget-negative"))\n'
       '\t\t\tvh78_short_budget = 1;\n',
       "v78 user-invoked test switch")
    frontend=once(frontend,"#endif\n\n\tif (loadst_f) {\n",
       "#endif\n\n"+smoke_source(build()[1])+"\n\tif (loadst_f) {\n",
       "emulated scheduler true VBlank events and post-event native VRAM oracle")
    main.write_text(frontend)
    return dict(result,
        native_psxcounters_vblank_hook_source_installed=True,
        synthetic_rcnt_vblank_edge_and_vram_oracle_installed=True,
        authentic_physical_ps1_vblank_verified=False,
        retail_MAP02_frame_timing_verified=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("checkout",type=Path)
    args=parser.parse_args()
    print(apply(args.checkout))
    return 0
if __name__=="__main__":raise SystemExit(main())

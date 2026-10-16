#!/usr/bin/env python3
"""Attach a read-only genuine psxcounters.c VBlank entry observer to v77.

The observed event is *inside* the original psxRcntUpdate() VBlankStart
branch immediately after the real GPU_vBlank(1,0) callback. CPU time
advances exclusively by executing hand-authored MIPS instructions in
the emulator; no cycle counter, interrupt or VBlank is host-forged.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from .apply_map02_v77_pcsx_rearmed import apply as apply_v77,oracle_source as v77_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v78_vblank_mips_exe import build

def vblank_hook():
    return r"""#ifdef VH_MAP02_V66_PCSX_PROBE
/* Increments ONLY in the pinned original psxRcntUpdate()
 * branch where GPU_vBlank(1,0) was really invoked. */
unsigned int vh78_vblank_observed_count;
unsigned int vh78_vblank_last_cycle;
unsigned int vh78_vblank_last_frame;
unsigned int vh78_vblank_last_hsync;
#endif

"""

def oracle_source(stops,wait_pc):
    source=v77_oracle(stops)
    a='if(vh77_multiphase_smoke) {'
    source=once(source,a,'if(vh78_vblank_smoke) {',"v78 handler")
    source=once(source,'memcmp(tag,"VH77SYN!",8)==0','memcmp(tag,"VH78SYN!",8)==0',"v78 EXE tag")
    # Move all owned status tokens to v78; the inherited v77 path
    # remains a different, independently executable opt-in mode.
    source=source.replace("VH77_","VH78_")
    source=once(source,
        'unsigned int total_samples=0,frame_count=0;',
        'unsigned int total_samples=0,frame_count=0;\n'
        '\t\tunsigned int previous_vblank_frame=0;\n'
        '\t\tunsigned int initial_vblank_count=vh78_vblank_observed_count;',
        "real VBlank phase tracker")
    src_wait=r"""
			/* Only the actual interpreted CPU NOP wait loop is
			 * allowed to advance the emulated counter. This is
			 * no artificial VBlank call, psxRegs.cycle mutation,
			 * or manipulation of hSyncCount / PS1 IRQ flags. */
			unsigned int entry_count=vh78_vblank_observed_count;
			unsigned int start_cycle=psxRegs.cycle;
			unsigned int next_stage_pc=psxRegs.pc;
			unsigned int loops=0;
			while(vh78_vblank_observed_count==entry_count && loops<8000) {
				psxRegs.pc=VH78_WAIT_PC;
				psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);
				if(psxRegs.pc!=VH78_WAIT_PC) {
					SysPrintf("VH78_WAIT_CPU_REFUSED phase=%u\n",phase);
					ClosePlugins();SysClose();menu_finish();plat_finish();return 8;
				}
				loops++;
			}
			psxRegs.pc=next_stage_pc;
			if(vh78_vblank_observed_count!=entry_count+1 ||
			   vh78_vblank_last_cycle<=start_cycle ||
			   vh78_vblank_last_hsync==0 ||
			   (phase>0 && vh78_vblank_last_frame!=previous_vblank_frame+1)) {
				SysPrintf("VH78_VBLANK_REFUSED phase=%u loops=%u\n",phase,loops);
				ClosePlugins();SysClose();menu_finish();plat_finish();return 9;
			}
			previous_vblank_frame=vh78_vblank_last_frame;
			/* Only native VRAM readback can verify raster output. */
""".replace("VH78_WAIT_PC",f"0x{wait_pc:08x}u")
    source=once(source,'\t\t\tGPUFreeze_t state={0};',src_wait+'\t\t\tGPUFreeze_t state={0};',"vblank before VRAM")
    source=once(source,'\t\t\tSysPrintf("VH78_PHASE_PASS phase=%u checked=595 guard=499\\n",phase);',
        '\t\t\tSysPrintf("VH78_VBLANK_OBSERVED phase=%u event=%u frame=%u loops=%u\\n",\n'
        '\t\t\t  phase,vh78_vblank_observed_count-initial_vblank_count,\n'
        '\t\t\t  vh78_vblank_last_frame,loops);\n'
        '\t\t\tSysPrintf("VH78_PHASE_PASS phase=%u checked=595 guard=499\\n",phase);',
        "event count diagnostic")
    source=once(source,'\t\tif(frame_count!=4 || total_samples!=2380) {',
        '\t\tif(frame_count!=4 || total_samples!=2380 ||\n'
        '\t\t   vh78_vblank_observed_count!=initial_vblank_count+4) {',
        "require four genuine event transitions")
    source=once(source,
        'VH78_MULTIPHASE_PASS phases=4 samples=2380 gpu_fifo_reset_kept_state=1 gpu_full_reset_cleared_state=1',
        'VH78_VBLANK_VRAM_PASS vblanks=4 phases=4 samples=2380 gpu_fifo_reset_kept_state=1 gpu_full_reset_cleared_state=1',
        "v78 only post-event result")
    return source

def apply(root:Path):
    proof=apply_v77(root)
    base=root.resolve()
    counters=base/"libpcsxcore/psxcounters.c"
    front=base/"frontend/main.c"
    cs=counters.read_text()
    fs=front.read_text()
    # Original source-only hook: no change to VBlank triggering or GPU.
    cs=once(cs,'unsigned int frame_counter = 0;\n',
        'unsigned int frame_counter = 0;\n'+vblank_hook(),
        "original vblank counter declaration")
    cs=once(cs,'            GPU_vBlank( 1, 0 );\n',
        '            GPU_vBlank( 1, 0 );\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '            vh78_vblank_observed_count++;\n'
        '            vh78_vblank_last_cycle=psxRegs.cycle;\n'
        '            vh78_vblank_last_frame=frame_counter;\n'
        '            vh78_vblank_last_hsync=hSyncCount;\n'
        '#endif\n',
        "real psxRcntUpdate GPU_vBlank edge")
    fs=once(fs,'\tint vh77_multiphase_smoke = 0;\n',
        '\tint vh77_multiphase_smoke = 0;\n'
        '\tint vh78_vblank_smoke = 0;\n',
        "v78 opt-in state")
    fs=once(fs,
        '\t\telse if (!strcmp(argv[i], "--vh77-multiphase-smoke"))\n'
        '\t\t\tvh77_multiphase_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh77-multiphase-smoke"))\n'
        '\t\t\tvh77_multiphase_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh78-vblank-smoke"))\n'
        '\t\t\tvh78_vblank_smoke = 1;\n',
        "v78 CLI option")
    fs=once(fs,
        '#include "../libpcsxcore/r3000a.h"\n',
        '#include "../libpcsxcore/r3000a.h"\n'
        'extern unsigned int vh78_vblank_observed_count;\n'
        'extern unsigned int vh78_vblank_last_cycle;\n'
        'extern unsigned int vh78_vblank_last_frame;\n'
        'extern unsigned int vh78_vblank_last_hsync;\n',
        "read-only VBlank counters")
    _,stops,starts,wait_pc,_=build()
    fs=once(fs,"#endif\n\n\tif (loadst_f) {\n",
        "#endif\n\n"+oracle_source(stops,wait_pc)+"\n\tif (loadst_f) {\n",
        "native observed VBlank VRAM scene")
    counters.write_text(cs)
    front.write_text(fs)
    return dict(proof,emulator_vblank_start_hook_installed=True,
                source_vblank_signal="original psxRcntUpdate GPU_vBlank(1,0)",
                physical_ps1_vblank_verified=False,
                retail_video_frame_correspondence_proven=False,
                original_retail_MAP02_verified=False,
                HD_replacement_approved=False)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    args=p.parse_args()
    print(apply(args.checkout))
if __name__=="__main__":raise SystemExit(main())

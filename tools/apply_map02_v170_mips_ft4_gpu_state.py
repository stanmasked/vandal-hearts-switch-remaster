#!/usr/bin/env python3
"""v170: guest MIPS source PCs bind layered FT4, CLUT/E1/E2/E6 to native VRAM.

Read-only native MMIO witness of all 202 source-authored guest-MIPS GP0 SW
instructions and one GP1 FIFO reset; independently reuse v76 real-Unai
1162-pixel oracle of eleven 4x4 regions, 12 FT4s and 3 textured sprites.
No retail Vandal Hearts program, texture, or host-created GP0 packet.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v169_mips_stp_e2v_vram import apply as apply_v169
from .apply_map02_v76_pcsx_rearmed import oracle_source as v76_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v76_gpu_state_order_exe import (
    build,GP0_SEQUENCE,MAGIC,HEADER_SIZE,REGIONS
)
from .make_map02_v70_synthetic_psx_exe import START,lui,ori,sw

MEM_DECL="void vh140_mmio_enable(unsigned mutate_expected) {\n"
MEM_OBSERVE="    vh138_pc_observe(regs,mem,value);\n"
FRONT_FLAG="\tint vh169_stp_e2v_smoke = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh169-mips-stp-e2v-vram"))\n'
ORACLE_POSITION="\tif (loadst_f) {\n"


def expected_order_source():
    image,stop,ins=build()
    words=tuple(GP0_SEQUENCE)
    if (len(image)!=HEADER_SIZE+4096 or image[:8]!=b"PS-X EXE" or
        image[0x4c:0x54]!=MAGIC or MAGIC!=b"VH76SYN!" or
        len(words)!=202 or ins[4]!=sw(9,0,8) or len(REGIONS)!=11):
        raise ValueError("source-authored v76 layered FT4 program changed")
    pcs=[]
    for i,w in enumerate(words):
        n=8+3*i
        if (ins[n-2]!=lui(9,w>>16) or
            ins[n-1]!=ori(9,9,w&0xffff) or
            ins[n]!=sw(9,0,8)):
            raise ValueError("GP0 command not written by source MIPS SW")
        pcs.append(START+4*n)
    if len(set(pcs))!=202:
        raise ValueError("duplicate GPU-command MIPS instruction PC")
    if (words[126]!=0xe2000401 or words[136]!=0xe2000000 or
        words[146]!=0xe6000001 or words[156]!=0xe6000002 or
        words[166]!=0xe6000000 or words[185]!=0xe1000000 or
        words[190]!=0xe1000020 or words[195]!=0xe1000000 or
        words[200]!=0xe2000000 or words[201]!=0xe6000000):
        raise ValueError("E1/E2/E6 source-authored state transition order changed")
    if (sum((w>>24) in (0x2d,0x2f) for w in words)!=12 or
        words.count(0x67ffffff)!=3 or
        words.count(0x60ff0000)!=11 or
        words.count(0xa0000000)!=3):
        raise ValueError("expected 12 FT4, 3 sprites, 11 tiles and 3 uploads")
    return START+4*4,tuple(pcs),words,stop


def gpu_state_mmio_c():
    gp1,pcs,words,stop=expected_order_source()
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Exact self-authored program MIPS PC + SW opcode + words.
 * No MMIO mutation: independent Unai VRAM oracle remains unchanged. */
static const u32 vh170_source_pc[] = {VH170_PC_DATA};
static const u32 vh170_source_word[] = {VH170_WORD_DATA};
#define VH170_WORDS (sizeof(vh170_source_word)/sizeof(vh170_source_word[0]))
typedef char vh170_same_shape[(sizeof(vh170_source_pc)==sizeof(vh170_source_word))?1:-1];
static unsigned vh170_active,vh170_seen,vh170_gp1,vh170_faults;
int vh170_arm_state_source(void) {
    if(vh170_active)return -1;
    vh170_active=1u;vh170_seen=vh170_gp1=vh170_faults=0u;
    return 0;
}
static void vh170_observe_state_mips_sw(psxRegisters *regs,u32 addr,u32 value) {
    u32 physical=addr&0x1fffffffu;
    if(!vh170_active)return;
    /* Ignore normal RAM stores, e.g., the MIPS completion marker. */
    if(physical!=0x1f801810u && physical!=0x1f801814u)return;
    if(!regs || regs->code!=0xad090000u){vh170_faults++;return;}
    if(physical==0x1f801814u) {
        if(vh170_gp1!=0u || vh170_seen!=0u ||
           regs->pc!=VH170_GP1_PC_PLUS4 || value!=0x01000000u)
            vh170_faults++;
        else vh170_gp1++;
        return;
    }
    if(vh170_gp1!=1u || vh170_seen>=VH170_WORDS ||
       regs->pc!=vh170_source_pc[vh170_seen]+4u ||
       value!=vh170_source_word[vh170_seen]){
        vh170_faults++;
        return;
    }
    vh170_seen++;
}
unsigned vh170_state_gp0_seen(void){return vh170_seen;}
unsigned vh170_state_gp1_seen(void){return vh170_gp1;}
unsigned vh170_state_fault_count(void){return vh170_faults;}
int vh170_disarm_state_source(void) {
    if(!vh170_active)return -1;
    vh170_active=0u;
    return 0;
}
#endif

""".replace("VH170_PC_DATA",",".join(f"0x{x:08x}u" for x in pcs)).replace(
    "VH170_WORD_DATA",",".join(f"0x{x:08x}u" for x in words)
).replace("VH170_GP1_PC_PLUS4",f"0x{gp1+4:08x}u")


def patch_memory(source: str):
    if "vh170_observe_state_mips_sw" in source:
        raise ValueError("duplicate v170 source watcher")
    source=once(source,MEM_DECL,gpu_state_mmio_c()+MEM_DECL,
                "native GP0/GP1 MIPS layered state watcher declarations")
    return once(source,MEM_OBSERVE,
                "    if(vh170_active) vh170_observe_state_mips_sw(regs,mem,value);\n"
                +MEM_OBSERVE,
                "native unchanged MMIO write observation before v138 diagnostics")


def layered_oracle():
    gp1,pcs,words,stop=expected_order_source()
    s=v76_oracle(stop).replace("vh76_gpu_state_smoke","vh170_gpu_state_smoke")
    execute="\t\tpsxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"
    if s.count(execute)!=1:
        raise ValueError("original v76 guest execution anchor changed")
    s=s.replace(execute,
        '\t\tif(vh170_arm_state_source()!=0){\n'
        '\t\t\tSysPrintf("VH170_STATE_ARM_REFUSED\\n");\n'
        '\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 76;\n'
        '\t\t}\n'
        +execute+'\n'
        '\t\tunsigned int words=vh170_state_gp0_seen();\n'
        '\t\tunsigned int gp1_count=vh170_state_gp1_seen();\n'
        '\t\tunsigned int faults=vh170_state_fault_count();\n'
        '\t\tint disarmed=vh170_disarm_state_source();\n'
        '\t\tif(disarmed!=0 || words!=202u || gp1_count!=1u || faults!=0u){\n'
        '\t\t\tSysPrintf("VH170_MIPS_GPU_STATE_REFUSED words=%u gp1=%u faults=%u\\n",'
        'words,gp1_count,faults);\n'
        '\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 76;\n'
        '\t\t}\n')
    marker='\t\tSysPrintf("VH76_VRAM_PASS checked=1162 regions=11 region_pixels=176 guard=986\\n");'
    if s.count(marker)!=1:
        raise ValueError("original v76 independent Unai 1162-pixel oracle changed")
    s=s.replace(marker,
        '\t\tSysPrintf("VH170_GUEST_MIPS_GPU_STATE_VRAM_PASS"'
        '" gp0_words=202 gp1_words=1 ft4=12 sprites=3"'
        '" regions=11 pixels_checked=1162 colored=176 guard=986"'
        '" original_retail=0\\n");\n'+marker)
    return s


def patch_frontend(source: str):
    if "vh170_gpu_state_smoke" in source:
        raise ValueError("duplicate layered FT4 state mode")
    source=once(source,FRONT_FLAG,FRONT_FLAG+
                "\tint vh170_gpu_state_smoke = 0;\n"
                "\textern int vh170_arm_state_source(void);\n"
                "\textern unsigned vh170_state_gp0_seen(void);\n"
                "\textern unsigned vh170_state_gp1_seen(void);\n"
                "\textern unsigned vh170_state_fault_count(void);\n"
                "\textern int vh170_disarm_state_source(void);\n",
                "synthetic v170 CPU-sourced FT4 order and E1/E2/E6 option")
    source=once(source,FRONT_CLI,
                '\t\telse if (!strcmp(argv[i], "--vh170-mips-ft4-gpu-state"))\n'
                '\t\t\tvh170_gpu_state_smoke=1;\n'+FRONT_CLI,
                "opt-in GPU mode for original v76 signed synthetic code")
    return once(source,ORACLE_POSITION,layered_oracle()+"\n"+ORACLE_POSITION,
                "retain independent v76 11-region actual Unai pixel oracle")


def apply(root: Path):
    result=apply_v169(root)
    base=root.resolve()
    mem=base/"libpcsxcore/psxmem.c"
    front=base/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    front.write_text(patch_frontend(front.read_text()))
    return dict(result,
        v170_guest_mips_exact_gp0_sw_words=202,
        v170_source_gpu_ft4_quads=12,
        v170_source_gpu_textured_sprites=3,
        v170_independent_native_vram_pixels=1162,
        v170_original_retail_map02_verified=False,
        v170_switch_gpu_parity_verified=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))

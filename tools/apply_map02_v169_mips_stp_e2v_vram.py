#!/usr/bin/env python3
"""v169 source-verified guest MIPS indexed STP/ABR and E2 vertical Unai VRAM.

Use the existing self-authored v75 PS-X EXE with 4/8bpp CLUT palettes and
5 FT4 draws. Observe every MIPS GP0/GP1 MMIO word and source PC before
independently running the pinned native v75 511-pixel STP/ABR/E2 oracle.
Neither original retail Vandal Hearts nor host-drawn GPU packets are used.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v168_mips_clut_uv_vram import apply as apply_v168
from .apply_map02_v75_pcsx_rearmed import oracle_source as v75_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v75_indexed_stp_e2v_exe import (
    build,GP0_SEQUENCE,MAGIC,HEADER_SIZE,E2_VERTICAL,REGIONS
)
from .make_map02_v70_synthetic_psx_exe import START,lui,ori,sw

MEM_DECL="void vh140_mmio_enable(unsigned mutate_expected) {\n"
MEM_OBSERVE="    vh138_pc_observe(regs,mem,value);\n"
FRONT_FLAG="\tint vh168_clut_uv_smoke = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh168-mips-clut-uv-vram"))\n'
ORACLE_POSITION="\tif (loadst_f) {\n"


def expected_stp_source():
    image,end,program=build()
    words=tuple(GP0_SEQUENCE)
    if len(image)!=HEADER_SIZE+4096 or image[:8]!=b"PS-X EXE" or \
       image[0x4c:0x54]!=MAGIC or MAGIC!=b"VH75SYN!" or \
       len(words)!=236 or program[4]!=sw(9,0,8):
        raise ValueError("self-authored v75 MIPS indexed STP/E2V program changed")
    pcs=[]
    for i,word in enumerate(words):
        j=8+3*i
        if program[j-2]!=lui(9,word>>16) or \
           program[j-1]!=ori(9,9,word&0xffff) or \
           program[j]!=sw(9,0,8):
            raise ValueError("GP0 word lacks source-authored MIPS SW triplet")
        pcs.append(START+4*j)
    starts=tuple(i for i,w in enumerate(words) if w in (0x2f000000,0x2d000000))
    if starts!=(189,198,207,216,226) or \
       tuple(words[i] for i in starts)!=(0x2f000000,)*4+(0x2d000000,) or \
       words[225]!=E2_VERTICAL or E2_VERTICAL!=0xe2008020 or \
       words[235]!=0xe2000000 or words.count(0xa0000000)!=4 or \
       len(REGIONS)!=5 or len(set(pcs))!=236:
        raise ValueError("indexed FT4 ABR/STP/E2V packet boundaries changed")
    # The indexed and texture-window semantics are deliberately source-gated.
    if (words[191]>>16,words[200]>>16,words[209]>>16,
        words[218]>>16,words[228]>>16)!=(32,32,33,33,32):
        raise ValueError("expected CLUT banks do not match guest FT4 words")
    if (words[211]>>16,words[220]>>16)!=(0x0a1,0x081):
        raise ValueError("8bpp ABR1 and nonblended indexed texture pages changed")
    return START+16,tuple(pcs),words,starts,end


def native_mmio_c():
    gp1,pcs,words,starts,end=expected_stp_source()
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Only watches independently authored guest MIPS SW instructions.
 * No writes to guest CPU, GPU commands, palettes, clocks or raster data. */
static const u32 vh169_expected_pc[] = {VH169_PCS};
static const u32 vh169_expected_word[] = {VH169_WORDS};
#define VH169_GP0_LENGTH (sizeof(vh169_expected_word)/sizeof(vh169_expected_word[0]))
typedef char vh169_source_words_same_shape[
    (sizeof(vh169_expected_pc)==sizeof(vh169_expected_word))?1:-1];
static unsigned vh169_active,vh169_seen,vh169_gp1,vh169_faults;
int vh169_arm_stp_e2v_origin(void){
    if(vh169_active)return -1;
    vh169_active=1u;vh169_seen=vh169_gp1=vh169_faults=0u;
    return 0;
}
static void vh169_note_stp_e2v_mips_sw(psxRegisters *regs,u32 addr,u32 val){
    u32 physical=addr&0x1fffffffu;
    if(!vh169_active)return;
    /* Guest RAM completion marker is not another GPU command. */
    if(physical!=0x1f801810u && physical!=0x1f801814u)return;
    if(!regs || regs->code!=0xad090000u){vh169_faults++;return;}
    if(physical==0x1f801814u){
        if(vh169_gp1!=0u || vh169_seen!=0u ||
           regs->pc!=VH169_GP1_PC_PLUS4 || val!=0x01000000u)
            vh169_faults++;
        else vh169_gp1++;
        return;
    }
    if(vh169_gp1!=1u || vh169_seen>=VH169_GP0_LENGTH ||
       regs->pc!=vh169_expected_pc[vh169_seen]+4u ||
       val!=vh169_expected_word[vh169_seen]){
        vh169_faults++;
        return;
    }
    vh169_seen++;
}
unsigned vh169_stp_e2v_gp0_seen(void){return vh169_seen;}
unsigned vh169_stp_e2v_gp1_seen(void){return vh169_gp1;}
unsigned vh169_stp_e2v_faults(void){return vh169_faults;}
int vh169_disarm_stp_e2v_origin(void){
    if(!vh169_active)return -1;
    vh169_active=0u;
    return 0;
}
#endif

""".replace("VH169_PCS",",".join(f"0x{n:08x}u" for n in pcs)
).replace("VH169_WORDS",",".join(f"0x{n:08x}u" for n in words)
).replace("VH169_GP1_PC_PLUS4",f"0x{gp1+4:08x}u")


def patch_memory(source: str):
    if "vh169_note_stp_e2v_mips_sw" in source:
        raise ValueError("refuse duplicate v169 MMIO watcher")
    source=once(source,MEM_DECL,native_mmio_c()+MEM_DECL,
                "236 source-authored MIPS writes to real GPU MMIO port")
    return once(source,MEM_OBSERVE,
                "    if(vh169_active) vh169_note_stp_e2v_mips_sw(regs,mem,value);\n"
                +MEM_OBSERVE,
                "source-PC STP/ABR E2 vertical watch before inactive v138 observer")


def stp_e2v_oracle():
    gp1,pcs,words,starts,end=expected_stp_source()
    src=v75_oracle(end).replace("vh75_stp_e2v_smoke","vh169_stp_e2v_smoke")
    execute="\t\tpsxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"
    if src.count(execute)!=1:
        raise ValueError("original v75 interpreter execution marker changed")
    src=src.replace(execute,
        '\t\tif(vh169_arm_stp_e2v_origin()!=0){\n'
        '\t\t\tSysPrintf("VH169_STP_ARM_REFUSED\\n");\n'
        '\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 75;\n'
        '\t\t}\n'
        +execute+'\n'
        '\t\tunsigned int seen=vh169_stp_e2v_gp0_seen();\n'
        '\t\tunsigned int gp1_count=vh169_stp_e2v_gp1_seen();\n'
        '\t\tunsigned int faults=vh169_stp_e2v_faults();\n'
        '\t\tint disarmed=vh169_disarm_stp_e2v_origin();\n'
        '\t\tif(disarmed!=0 || seen!=236u || gp1_count!=1u || faults!=0u){\n'
        '\t\t\tSysPrintf("VH169_STP_E2V_MIPS_GP0_REFUSED words=%u gp1=%u faults=%u\\n",'
        'seen,gp1_count,faults);\n'
        '\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 75;\n'
        '\t\t}\n')
    marker='\t\tSysPrintf("VH75_VRAM_PASS checked=511 stp4=16 nonstp=16 abr1=16 zero=16 e2v=16 guard=431\\n");'
    if src.count(marker)!=1:
        raise ValueError("independent original v75 511-pixel Unai oracle changed")
    src=src.replace(marker,
        '\t\tSysPrintf("VH169_GUEST_MIPS_STP_E2V_VRAM_PASS"'
        '" gp0_words=236 gp1_words=1 a0_uploads=4 ft4=5"'
        '" pixels_checked=511 stp4=16 nonstp=16 abr1=16"'
        '" transparent=16 e2_vertical=16 guard=431 original_retail=0\\n");\n'
        +marker)
    return src


def patch_frontend(source: str):
    if "vh169_stp_e2v_smoke" in source:
        raise ValueError("v169 guest STP/E2V mode already installed")
    source=once(source,FRONT_FLAG,FRONT_FLAG+
                "\tint vh169_stp_e2v_smoke = 0;\n"
                "\textern int vh169_arm_stp_e2v_origin(void);\n"
                "\textern unsigned vh169_stp_e2v_gp0_seen(void);\n"
                "\textern unsigned vh169_stp_e2v_gp1_seen(void);\n"
                "\textern unsigned vh169_stp_e2v_faults(void);\n"
                "\textern int vh169_disarm_stp_e2v_origin(void);\n",
                "self-authored signed v75 STP/ABR and E2V MIPS opt-in")
    source=once(source,FRONT_CLI,
                '\t\telse if (!strcmp(argv[i], "--vh169-mips-stp-e2v-vram"))\n'
                '\t\t\tvh169_stp_e2v_smoke=1;\n'+FRONT_CLI,
                "separate opt-in signed synthetic MIPS VRAM oracle mode")
    return once(source,ORACLE_POSITION,stp_e2v_oracle()+"\n"+ORACLE_POSITION,
                "preserve full original v75 511 pixel STP/E2V native Unai oracle")


def apply(root: Path):
    proof=apply_v168(root)
    base=root.resolve()
    memory=base/"libpcsxcore/psxmem.c"
    frontend=base/"frontend/main.c"
    memory.write_text(patch_memory(memory.read_text()))
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(proof,
        v169_source_authored_gp0_words=236,
        v169_source_authored_gp1_reset=1,
        v169_guest_mips_ft4_quads=5,
        v169_independent_unai_pixels=511,
        v169_no_retail_MAP02_executed=True,
        v169_nintendo_switch_graphics_verified=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))

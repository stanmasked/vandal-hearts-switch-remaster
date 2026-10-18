#!/usr/bin/env python3
"""v167: full self-authored MIPS GP0(A0)/FT4/STP/ABR source-PC + VRAM proof.

Retains pinned v166 original emulator/Unai observers and adds a SEPARATE
guest-interpreted v72 program. Each original GP0 write must agree with exact
authored MIPS SW opcode, source PC and 32-bit value before the existing
independent 378-pixel FT4 native Unai readback can be credited.
No retail MAP02, images, textures or Switch output are represented.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v166_mips_pc_gp0_vram import apply as apply_v166
from .apply_map02_v69_pcsx_rearmed import once
from .apply_map02_v72_pcsx_rearmed import oracle_source as ft4_v72_oracle
from .make_map02_v72_ft4_mips_exe import (
    build,GP0_SEQUENCE,MAGIC,START,lui,ori,sw
)

MEM_DECL="void vh140_mmio_enable(unsigned mutate_expected) {\n"
MEM_OBSERVE="    vh138_pc_observe(regs,mem,value);\n"
FRONT_FLAG="\tint vh166_mips_pc_gp0_vram_chain = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh166-mips-pc-gp0-vram-chain")) {\n'
ORACLE_POSITION="\tif (loadst_f) {\n"


def expected_ft4_source():
    image,loop,words=build()
    sequence=tuple(GP0_SEQUENCE)
    if len(image)!=4096 or image[:8]!=b"PS-X EXE" or \
       image[0x4c:0x54]!=MAGIC or MAGIC!=b"VH72SYN!" or \
       len(sequence)!=72 or len(words)<222:
        raise ValueError("source-authored v72 FT4 program changed")
    if words[4]!=sw(9,0,8):
        raise ValueError("source-authored GP1 FIFO reset SW missing")
    pc1=START+4*4
    pcs=[]
    for i,word in enumerate(sequence):
        idx=8+3*i
        if (words[idx-2]!=lui(9,word>>16) or
            words[idx-1]!=ori(9,9,word&0xffff) or
            words[idx]!=sw(9,0,8)):
            raise ValueError("MIPS GP0 source opcode and packet mismatch")
        pcs.append(START+4*idx)
    if len(set(pcs))!=len(pcs):
        raise ValueError("nonunique guest FT4 GP0 PC")
    starts=tuple(i for i,c in enumerate(sequence) if c in (0x2d000000,0x2f000000))
    if len(starts)!=4 or any(
         tuple(sequence[i:i+9])[0] not in (0x2d000000,0x2f000000)
         for i in starts
    ) or starts != (36,45,54,63):
        raise ValueError("unexpected guest textured FT4 primitive boundaries")
    return pc1,tuple(pcs),sequence,starts,loop


def ft4_mmio_c():
    pc1,pcs,words,starts,loop=expected_ft4_source()
    pc_data=",".join("0x%08xu"%p for p in pcs)
    gp0_data=",".join("0x%08xu"%w for w in words)
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* All positions/values generated from independent synthetic MIPS source.
 * Observer never modifies GPU FIFO, CPU state, FT4, VRAM or renderer. */
static const u32 vh167_source_gp0_pc[] = {VH167_PCS};
static const u32 vh167_source_gp0_words[] = {VH167_WORDS};
#define VH167_GP0_WORDS (sizeof(vh167_source_gp0_words)/sizeof(vh167_source_gp0_words[0]))
typedef char vh167_expected_same_shape[
    (sizeof(vh167_source_gp0_pc)==sizeof(vh167_source_gp0_words))?1:-1];
static unsigned vh167_active,vh167_gp1_seen,vh167_gp0_seen,vh167_fault;
int vh167_arm_ft4_origin(void) {
    if(vh167_active) return -1;
    vh167_active=1u;vh167_gp1_seen=0u;
    vh167_gp0_seen=vh167_fault=0u;
    return 0;
}
static void vh167_observe_ft4_origin(psxRegisters *regs,u32 addr,u32 val) {
    u32 physical=addr&0x1fffffffu;
    if(!vh167_active) return;
    if(physical!=0x1f801810u && physical!=0x1f801814u) return;
    if(!regs || regs->code!=0xad090000u) {vh167_fault++;return;}
    if(physical==0x1f801814u) {
        if(vh167_gp1_seen!=0u || vh167_gp0_seen!=0u ||
           regs->pc!=VH167_GP1_PC_PLUS_4 || val!=0x01000000u) {
            vh167_fault++;
        } else vh167_gp1_seen++;
        return;
    }
    if(vh167_gp1_seen!=1u || vh167_gp0_seen>=VH167_GP0_WORDS ||
       regs->pc!=vh167_source_gp0_pc[vh167_gp0_seen]+4u ||
       val!=vh167_source_gp0_words[vh167_gp0_seen]) {
        vh167_fault++;
        return;
    }
    vh167_gp0_seen++;
}
unsigned vh167_ft4_gp0_seen(void){return vh167_gp0_seen;}
unsigned vh167_ft4_gp1_seen(void){return vh167_gp1_seen;}
unsigned vh167_ft4_faults(void){return vh167_fault;}
int vh167_disarm_ft4_origin(void) {
    if(!vh167_active)return -1;
    vh167_active=0u;
    return 0;
}
#endif

""".replace("VH167_PCS",pc_data).replace("VH167_WORDS",gp0_data).replace(
  "VH167_GP1_PC_PLUS_4","0x%08xu"%(pc1+4))


def patch_memory(source: str) -> str:
    if "vh167_observe_ft4_origin" in source:
        raise ValueError("v167 FT4 MIPS origin watcher already installed")
    source=once(source,MEM_DECL,ft4_mmio_c()+MEM_DECL,
                "self-authored 72-word FT4 source-PC native MMIO observer")
    return once(source,MEM_OBSERVE,
        "    if(vh167_active) vh167_observe_ft4_origin(regs,mem,value);\n"+
        MEM_OBSERVE,
        "native MIPS GP0+GP1 word capture before inactive v138 path")


def ft4_oracle():
    _,pcs,words,starts,loop=expected_ft4_source()
    src=ft4_v72_oracle(loop).replace("vh72_ft4_smoke","vh167_ft4_mips_smoke")
    run="\t\tpsxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"
    if src.count(run)!=1:
        raise ValueError("v72 FT4 guest ExecuteBlock anchor changed")
    src=src.replace(run,
        '\t\tif(vh167_arm_ft4_origin()!=0) {\n'
        '\t\t\tSysPrintf("VH167_FT4_ARM_REFUSED\\n");\n'
        '\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 72;\n'
        '\t\t}\n'
        +run+'\n'
        '\t\tunsigned int gp0_words=vh167_ft4_gp0_seen();\n'
        '\t\tunsigned int gp1_words=vh167_ft4_gp1_seen();\n'
        '\t\tunsigned int gp0_faults=vh167_ft4_faults();\n'
        '\t\tint disarmed=vh167_disarm_ft4_origin();\n'
        '\t\tif(disarmed!=0 || gp0_words!=72u || gp1_words!=1u || gp0_faults!=0u) {\n'
        '\t\t\tSysPrintf("VH167_FT4_MIPS_GP0_REFUSED words=%u gp1=%u faults=%u\\n",'
        'gp0_words,gp1_words,gp0_faults);\n'
        '\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 72;\n'
        '\t\t}\n')
    marker='\t\tSysPrintf("VH72_FT4_VRAM_PASS checked=378 opaque=16 abr0=16 no_stp=16 abr1=16 guard=314\\n");'
    if src.count(marker)!=1:
        raise ValueError("v72 independent VRAM oracle anchor changed")
    src=src.replace(marker,
        '\t\tSysPrintf("VH167_GUEST_MIPS_FT4_VRAM_PASS"'
        '" gp0_words=72 gp1_words=1 ft4=4 texture_upload=1"'
        '" pixels_checked=378 opaque=16 abr0=16 no_stp=16 abr1=16"'
        '" guard=314 original_retail=0\\n");\n'+marker)
    return src


def patch_frontend(source: str) -> str:
    if "vh167_ft4_mips_smoke" in source:
        raise ValueError("v167 FT4 guest mode already installed")
    source=once(source,FRONT_FLAG,FRONT_FLAG+
        "\tint vh167_ft4_mips_smoke = 0;\n"
        "\textern int vh167_arm_ft4_origin(void);\n"
        "\textern unsigned vh167_ft4_gp0_seen(void);\n"
        "\textern unsigned vh167_ft4_gp1_seen(void);\n"
        "\textern unsigned vh167_ft4_faults(void);\n"
        "\textern int vh167_disarm_ft4_origin(void);\n",
        "opt-in FT4 mode and read-only native MIPS origin declarations")
    source=once(source,FRONT_CLI,
        '\t\telse if (!strcmp(argv[i], "--vh167-mips-ft4-texture-vram"))\n'
        '\t\t\tvh167_ft4_mips_smoke=1;\n'+FRONT_CLI,
        "separate signed MIPS FT4 guest mode")
    return once(source,ORACLE_POSITION,ft4_oracle()+"\n"+ORACLE_POSITION,
        "original independent 378 pixel native FT4/STP/ABR oracle with provenance")


def apply(root: Path):
    report=apply_v166(root)
    base=root.resolve()
    mem=base/"libpcsxcore/psxmem.c"
    main=base/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    main.write_text(patch_frontend(main.read_text()))
    return dict(report,
        v167_source_authored_mips_gpu_gp0_words=72,
        v167_source_authored_gpu_gp1_fifo_resets=1,
        v167_native_ft4_textured_quads=4,
        v167_native_ft4_vram_pixels_checked=378,
        v167_original_retail_map02_frame_verified=False,
        v167_switch_hd_renderer_verified=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))

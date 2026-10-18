#!/usr/bin/env python3
"""v168: independently authored guest MIPS 4/8bpp CLUT + UV/E2 → native Unai VRAM.

Stacked on v167's successful source-authored FT4 origin-to-raster witness.
Read-only MMIO observer ties every v74 GP0(A0) texture/CLUT upload and FT4
word to its actual synthetic MIPS SW PC/opcode. v74's independent 399-pixel
oracle stays unchanged. Never runs, embeds or publishes retail game assets.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v167_mips_ft4_texture_vram import apply as apply_v167
from .apply_map02_v74_pcsx_rearmed import oracle_source as v74_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v74_indexed_clut_exe import build,GP0_SEQUENCE,MAGIC,HEADER_SIZE
from .make_map02_v70_synthetic_psx_exe import START,lui,ori,sw

MEM_DECL="void vh140_mmio_enable(unsigned mutate_expected) {\n"
MEM_OBSERVE="    vh138_pc_observe(regs,mem,value);\n"
FRONT_FLAG="\tint vh167_ft4_mips_smoke = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh167-mips-ft4-texture-vram"))\n'
ORACLE_POSITION="\tif (loadst_f) {\n"


def expected_clut_source():
    image,end,program=build()
    words=tuple(GP0_SEQUENCE)
    if len(image)!=HEADER_SIZE+4096 or image[:8]!=b"PS-X EXE" or \
       image[0x4c:0x54]!=MAGIC or MAGIC!=b"VH74SYN!" or \
       len(words)!=211 or program[4]!=sw(9,0,8):
        raise ValueError("self-authored v74 indexed texture source changed")
    pcs=[]
    for index,word in enumerate(words):
        offset=8+3*index
        if program[offset-2]!=lui(9,word>>16) or \
           program[offset-1]!=ori(9,9,word&0xffff) or \
           program[offset]!=sw(9,0,8):
            raise ValueError("GP0 word not issued by expected MIPS SW opcode")
        pcs.append(START+4*offset)
    starts=tuple(i for i,w in enumerate(words) if w==0x2d000000)
    if starts!=(170,179,189,202) or \
       words[188]!=0xe2000401 or words[198]!=0xe2000000 or \
       words.count(0xa0000000)!=4 or \
       len(set(pcs))!=211:
        raise ValueError("unexpected CLUT FT4, E2 window or A0 upload positions")
    # Explicit 4bpp and 8bpp CLUT addresses, texture page and UV words.
    if not (words[172]>>16==32 and words[176]>>16==0 and
            words[181]>>16==33 and words[183]>>16==0x081 and
            words[191]>>16==32 and words[204]>>16==32):
        raise ValueError("indexed FT4 CLUT, TPage or UV anchors changed")
    return START+4*4,tuple(pcs),words,starts,end


def native_mmio_source():
    gp1,pcs,words,starts,end=expected_clut_source()
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Source-authored MIPS SW PCs / GP0 words. Never changes the guest,
 * emulator, GPU command queue, texture upload or Unai VRAM. */
static const u32 vh168_expected_gp0_pc[] = {VH168_PC_DATA};
static const u32 vh168_expected_gp0_word[] = {VH168_WORD_DATA};
#define VH168_LENGTH (sizeof(vh168_expected_gp0_word)/sizeof(vh168_expected_gp0_word[0]))
typedef char vh168_same_packet_shape[
    (sizeof(vh168_expected_gp0_pc)==sizeof(vh168_expected_gp0_word))?1:-1];
static unsigned vh168_active,vh168_gp0_count,vh168_gp1_count,vh168_fault;
int vh168_arm_clut_origin(void) {
    if(vh168_active) return -1;
    vh168_active=1u;
    vh168_gp0_count=vh168_gp1_count=vh168_fault=0u;
    return 0;
}
static void vh168_note_clut_mips_sw(psxRegisters *regs,u32 address,u32 value) {
    u32 physical=address&0x1fffffffu;
    if(!vh168_active)return;
    /* Guest also stores one CPU completion marker to ordinary RAM. */
    if(physical!=0x1f801810u && physical!=0x1f801814u)return;
    if(!regs || regs->code!=0xad090000u) {vh168_fault++;return;}
    if(physical==0x1f801814u){
        if(vh168_gp1_count!=0u || vh168_gp0_count!=0u ||
           regs->pc!=VH168_GP1_PC_PLUS4 || value!=0x01000000u)
            vh168_fault++;
        else vh168_gp1_count++;
        return;
    }
    if(vh168_gp1_count!=1u || vh168_gp0_count>=VH168_LENGTH ||
       regs->pc!=vh168_expected_gp0_pc[vh168_gp0_count]+4u ||
       value!=vh168_expected_gp0_word[vh168_gp0_count]) {
        vh168_fault++;
        return;
    }
    vh168_gp0_count++;
}
unsigned vh168_clut_gp0_count(void){return vh168_gp0_count;}
unsigned vh168_clut_gp1_count(void){return vh168_gp1_count;}
unsigned vh168_clut_fault_count(void){return vh168_fault;}
int vh168_disarm_clut_origin(void) {
    if(!vh168_active) return -1;
    vh168_active=0u;
    return 0;
}
#endif

""".replace("VH168_PC_DATA",",".join(f"0x{x:08x}u" for x in pcs)).replace(
    "VH168_WORD_DATA",",".join(f"0x{x:08x}u" for x in words)
).replace("VH168_GP1_PC_PLUS4",f"0x{gp1+4:08x}u")


def patch_memory(source: str):
    if "vh168_note_clut_mips_sw" in source:
        raise ValueError("duplicate v168 native MMIO watcher")
    source=once(source,MEM_DECL,native_mmio_source()+MEM_DECL,
                "self-authored v74 211-word MIPS/CLUT origin watcher")
    return once(source,MEM_OBSERVE,
                "    if(vh168_active) vh168_note_clut_mips_sw(regs,mem,value);\n"
                +MEM_OBSERVE,
                "existing real MMIO path, read-only source origin witness")


def clut_oracle():
    gp1,pcs,words,starts,end=expected_clut_source()
    s=v74_oracle(end).replace("vh74_indexed_smoke","vh168_clut_uv_smoke")
    execute="\t\tpsxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"
    if s.count(execute)!=1:
        raise ValueError("v74 actual interpreter execution anchor changed")
    s=s.replace(execute,
        '\t\tif(vh168_arm_clut_origin()!=0) {\n'
        '\t\t\tSysPrintf("VH168_CLUT_ARM_REFUSED\\n");\n'
        '\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 74;\n'
        '\t\t}\n'
        +execute+'\n'
        '\t\tunsigned int gp0_count=vh168_clut_gp0_count();\n'
        '\t\tunsigned int gp1_count=vh168_clut_gp1_count();\n'
        '\t\tunsigned int faults=vh168_clut_fault_count();\n'
        '\t\tint disarmed=vh168_disarm_clut_origin();\n'
        '\t\tif(disarmed!=0 || gp0_count!=211u || gp1_count!=1u || faults!=0u) {\n'
        '\t\t\tSysPrintf("VH168_CLUT_MIPS_GP0_REFUSED words=%u gp1=%u faults=%u\\n",'
        'gp0_count,gp1_count,faults);\n'
        '\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 74;\n'
        '\t\t}\n')
    marker='\t\tSysPrintf("VH74_VRAM_PASS checked=399 clut4=16 clut8=16 window=16 transparent=16 guard=335\\n");'
    if s.count(marker)!=1:
        raise ValueError("v74 independent CLUT/UV VRAM oracle marker changed")
    s=s.replace(marker,
        '\t\tSysPrintf("VH168_GUEST_MIPS_CLUT_UV_VRAM_PASS"'
        '" gp0_words=211 gp1_words=1 a0_uploads=4 ft4=4"'
        '" pixels_checked=399 clut4=16 clut8=16 e2_window=16"'
        '" transparent=16 guard=335 original_retail=0\\n");\n'+marker)
    return s


def patch_frontend(source: str):
    if "vh168_clut_uv_smoke" in source:
        raise ValueError("duplicate v168 CLUT/UV frontend mode")
    source=once(source,FRONT_FLAG,FRONT_FLAG+
                "\tint vh168_clut_uv_smoke = 0;\n"
                "\textern int vh168_arm_clut_origin(void);\n"
                "\textern unsigned vh168_clut_gp0_count(void);\n"
                "\textern unsigned vh168_clut_gp1_count(void);\n"
                "\textern unsigned vh168_clut_fault_count(void);\n"
                "\textern int vh168_disarm_clut_origin(void);\n",
                "v168 opt-in CLUT/UV and native MMIO witness API")
    source=once(source,FRONT_CLI,
                '\t\telse if (!strcmp(argv[i], "--vh168-mips-clut-uv-vram"))\n'
                '\t\t\tvh168_clut_uv_smoke=1;\n'+FRONT_CLI,
                "explicit signed v74 guest MIPS index-color mode")
    return once(source,ORACLE_POSITION,clut_oracle()+"\n"+ORACLE_POSITION,
                "actual v74 native Unai independent 399-pixel oracle")


def apply(root: Path):
    report=apply_v167(root)
    base=root.resolve()
    mem=base/"libpcsxcore/psxmem.c"
    front=base/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    front.write_text(patch_frontend(front.read_text()))
    return dict(report,
        v168_guest_mips_clut_gp0_words=211,
        v168_guest_mips_clut_a0_texture_palette_uploads=4,
        v168_guest_mips_clut_ft4_quads=4,
        v168_unai_indexed_clut_uv_pixel_samples=399,
        v168_original_retail_map02_verified=False,
        v168_nintendo_switch_renderer_verified=False)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(parser.parse_args().pinned_pcsx_checkout))

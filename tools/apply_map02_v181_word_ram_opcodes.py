#!/usr/bin/env python3
"""v181: true interpreted aligned 32-bit non-GPU MIPS LW/SW RAM provenance.

Extend fully verified v180 without changing its modes. Observe actual pinned
psxMemRead32 AND psxMemWrite32 callbacks, requiring live guest opcode and PC
at the signed v78 wait instruction and the exact data address in 4 VBlanks.
Unmodified and incorrect-opcode guests fail before false pixel success.
No original retail code or game data.
"""
from __future__ import annotations
from pathlib import Path
from struct import pack
from .apply_map02_v180_nongpu_opcode_provenance import apply as apply_v180
from .apply_map02_v176_narrow_gpu_mmio import narrow_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v179_nongpu_mips_exes import originals
from .make_map02_v78_vblank_mips_exe import build
from .make_map02_v70_synthetic_psx_exe import START

# (operation name, exact native opcode, aligned physical RAM address, write)
CASES = (
    ("LW_RAM0",0x8c000000,0x00000000,0),
    ("LW_RAM4",0x8c000004,0x00000004,0),
    ("SW_RAM0",0xac000000,0x00000000,1),
    ("SW_RAM4",0xac000004,0x00000004,1),
)
PROBE_ANCHOR="unsigned vh173_wait_mmio_faults(void) {return vh173_wait_bad;}\n"
READ_ANCHOR="    vh180_observe_nongpu(regs,mem,2u,0u);\n"
WRITE_ANCHOR="    if(vh173_wait_active) vh173_observe_wait_mmio(mem);\n"
FLAG="\tint vh180_nongpu_verified_id=-1;\n"
CLI='\t\telse if (!strcmp(argv[i], "--vh180-nongpu-mips-0"))\n'
ORACLE="\tif (loadst_f) {\n"

def make_variants():
    image,index=originals()
    src,stops,starts,pc,ops=build()
    if image!=src or pc!=START+index*4 or tuple(ops[index:index+512])!=(0,)*512:
        raise ValueError("v181 expected the exact signed v179 wait NOP fixture")
    off=2048+4*index
    variants={}
    for name,word,addr,writing in CASES:
        changed=bytearray(image)
        changed[off:off+4]=pack("<I",word)
        data=bytes(changed)
        if (data[0x4c:0x54]!=b"VH78SYN!" or
            data[:off]!=image[:off] or data[off+4:]!=image[off+4:]):
            raise ValueError("v181 word MIPS mutation escapes private single NOP")
        variants[name]=data
    return variants

def write_private(out_dir:Path):
    if not out_dir.is_dir() or out_dir.is_symlink():
        raise ValueError("require existing private directory")
    result=[]
    for name,blob in make_variants().items():
        target=out_dir/("V181_"+name+".EXE")
        if target.exists() or target.is_symlink():
            raise ValueError("refuse overwrite signed variant")
        target.write_bytes(blob);target.chmod(0o600)
        result.append(target)
    return result

def witness():
    image,stops,starts,pc,ops=build()
    expected_words=", ".join(f"0x{case[1]:08x}u" for case in CASES)
    expected_addrs=", ".join(f"0x{case[2]:08x}u" for case in CASES)
    expected_writes=", ".join(f"{case[3]}u" for case in CASES)
    return r"""
/* v181: passive real interpreter 32-bit RAM memory-access observer. */
static const u32 vh181_expected_word[4]={WORDS};
static const u32 vh181_expected_addr[4]={ADDRS};
static const unsigned vh181_expected_write[4]={WRITES};
static unsigned vh181_active,vh181_case,vh181_phase,vh181_seen,vh181_bad;
int vh181_arm(unsigned kind,unsigned phase) {
    if(kind>=4u || phase>=4u || vh181_active || !vh176_active ||
       vh176_phase!=phase || !vh175_port_armed || !vh173_wait_active)
        return -1;
    vh181_active=1u;vh181_case=kind;vh181_phase=phase;
    vh181_seen=0u;vh181_bad=0u;return 0;
}
static void vh181_observe(psxRegisters *regs,u32 addr,unsigned writing) {
    unsigned physical=addr&0x1fffffffu;
    if(!vh181_active || !vh176_active || !vh173_wait_active ||
       regs->pc!=WAIT_NEXT_PC || regs->code!=vh181_expected_word[vh181_case])
        return;
    if(vh181_expected_addr[vh181_case]==physical &&
       vh181_expected_write[vh181_case]==writing) vh181_seen++;
    else vh181_bad++;
}
unsigned vh181_count(void) {return vh181_seen;}
unsigned vh181_faults(void) {return vh181_bad;}
int vh181_disarm(unsigned kind,unsigned phase) {
    if(!vh181_active || vh181_case!=kind || vh181_phase!=phase ||
       !vh176_active || !vh175_port_armed || !vh173_wait_active)
        return -1;
    vh181_active=0u;return 0;
}
""".replace("WORDS",expected_words).replace("ADDRS",expected_addrs)\
     .replace("WRITES",expected_writes)\
     .replace("WAIT_NEXT_PC",f"0x{pc+4:08x}u")

def patch_memory(source:str):
    if "vh181_observe(" in source:
        raise ValueError("v181 32-bit RAM witness already inserted")
    s=once(source,PROBE_ANCHOR,witness()+PROBE_ANCHOR,
           "install read-only original PSX 32-bit interpreter RAM witness")
    s=once(s,"static void vh180_observe_nongpu(psxRegisters*,u32,unsigned,unsigned);\n",
           "static void vh180_observe_nongpu(psxRegisters*,u32,unsigned,unsigned);\n"
           "static void vh181_observe(psxRegisters*,u32,unsigned);\n",
           "declare v181 passive C observer before native memory accessors")
    s=once(s,READ_ANCHOR,
           "    vh181_observe(regs,mem,0u);\n"+READ_ANCHOR,
           "true guest 32-bit RAM LW observation before original PCSX read")
    return once(s,WRITE_ANCHOR,
           "    vh181_observe(regs,mem,1u);\n"+WRITE_ANCHOR,
           "true guest 32-bit RAM SW observation before original PCSX write")

def original_native_oracle():
    s=narrow_oracle()
    s=once(s,"if(vh176_mips_vblank_narrow_mmio_smoke) {",
           "if(vh181_nongpu_word_id>=0) {",
           "v181 new separate diagnostic mode reusing exact v176 VBlank pixel oracle")
    arm="unsigned int entry_count=vh78_vblank_observed_count;"
    s=once(s,arm,
       "if(vh181_arm((unsigned)vh181_nongpu_word_id,phase)!=0){\n"
       '                SysPrintf("VH181_NATIVE_WORD_ARM_REFUSED phase=%u\\n",phase);\n'
       "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 84;\n"
       "\t\t\t}\n\t\t\t"+arm,
       "arm original native 32-bit RAM opcode observer inside genuine wait")
    disarm="int vh176_disarmed=vh176_disarm_narrow(phase);"
    s=once(s,disarm,
       "unsigned int vh181_phase_count=vh181_count();\n"
       "\t\t\tunsigned int vh181_phase_faults=vh181_faults();\n"
       "\t\t\tint vh181_disarmed=vh181_disarm((unsigned)vh181_nongpu_word_id,phase);\n"
       "\t\t\t"+disarm,
       "disarm true RAM word observer before inherited GPU sentinels")
    gate="if(vh176_disarmed!=0 || vh176_total!=0u){"
    s=once(s,gate,
       "if(vh181_disarmed!=0 || vh181_phase_count==0u || vh181_phase_faults!=0u){\n"
       '                SysPrintf("VH181_NATIVE_WORD_UNOBSERVED_REFUSED kind=%d phase=%u count=%u faults=%u\\n",vh181_nongpu_word_id,phase,vh181_phase_count,vh181_phase_faults);\n'
       "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 84;\n"
       "\t\t\t}\n\t\t\tvh181_windows++;\n"
       "\t\t\tvh181_total+=vh181_phase_count;\n"
       "\t\t\t"+gate,
       "fail before unrelated pixel marker if real MIPS LW/SW wasn't executed")
    decl="unsigned int vh176_narrow_windows=0u;"
    s=once(s,decl,decl+
        "\n\t\tunsigned int vh181_windows=0u,vh181_total=0u;",
        "require exactly four verified interpreter MIPS LW/SW windows")
    marker='SysPrintf("VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS'
    return once(s,marker,
       "if(vh181_windows!=4u || vh181_total<4u){\n"
       '            SysPrintf("VH181_NATIVE_WORD_WINDOWS_REFUSED windows=%u count=%u\\n",vh181_windows,vh181_total);\n'
       "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 84;\n"
       "\t\t}\n"
       '        SysPrintf("VH181_NATIVE_GUEST_WORD_RAM_PASS kind=%d windows=4 observed=%u pc_opcode_addr=1 vblanks=4 samples=2380 original_retail=0\\n",vh181_nongpu_word_id,vh181_total);\n'
       "\t\t"+marker,
       "report positive only after all 4 native VBlank visits and pixel checks")

def patch_frontend(source:str):
    if "vh181_nongpu_word_id" in source:
        raise ValueError("already contains v181 mode")
    s=once(source,FLAG,FLAG+
       "\tint vh181_nongpu_word_id=-1;\n"
       "\textern int vh181_arm(unsigned,unsigned);\n"
       "\textern unsigned vh181_count(void);\n"
       "\textern unsigned vh181_faults(void);\n"
       "\textern int vh181_disarm(unsigned,unsigned);\n",
       "new independently selected v181 guest word modes")
    cli="".join(
        '\t\telse if (!strcmp(argv[i], "--vh181-nongpu-word-'+str(i)+'"))\n'
        "\t\t\tvh181_nongpu_word_id="+str(i)+";\n"
        for i in range(4)
    )
    s=once(s,CLI,cli+CLI,
           "read-only native MIPS word proof opt-in cli")
    return once(s,ORACLE,original_native_oracle()+"\n"+ORACLE,
                "attach independent native LW/SW provenance oracle")

def apply(root:Path):
    result=apply_v180(root)
    mem=root.resolve()/"libpcsxcore/psxmem.c"
    main=root.resolve()/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    main.write_text(patch_frontend(main.read_text()))
    return dict(result,v181_word_ram_mips_types=4,
                v181_original_retail_executed=False,
                v181_native_unai_pixel_samples_per_case=2380)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generate-private",type=Path)
    p.add_argument("pinned_pcsx_checkout",type=Path,nargs="?")
    args=p.parse_args()
    if args.generate_private is not None:
        written=write_private(args.generate_private)
        print(f"VH181_WORD_RAM_VARIANTS_PASS count={len(written)} single_signed_mips_word=1 original_retail=0")
    elif args.pinned_pcsx_checkout:
        print(apply(args.pinned_pcsx_checkout))
    else:p.error("provide a pinned PCSX source directory or --generate-private")

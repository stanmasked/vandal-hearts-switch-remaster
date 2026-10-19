#!/usr/bin/env python3
"""MAP02 v183: actual guest SW→LW data dependency across real PCSX VBlank waits.

Synthesized PS-X EXE only. Prove final *memory values*, not just addresses:
guest stores 0x51a7c3d9 to scratch RAM, destroys its source register, loads
the word with a MIPS-I load-delay NOP, XORs it and stores 0x51a73c26.
Frontend seeds different sentinels before every phase, then reads the real
PCSX RAM through psxMemRead32; missing SW or LW must exit 85.
No original Vandal Hearts retail assets, Nintendo Switch hardware or GPU
injection. VBlank and Unai pixel observations are inherited from v176.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from struct import pack_into

from .apply_map02_v181_word_ram_opcodes import apply as apply_v181
from .apply_map02_v176_narrow_gpu_mmio import narrow_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v78_vblank_mips_exe import build as v78_build
from .make_map02_v70_synthetic_psx_exe import START, lui, ori, sw

RAM_ADDRESS=0x001e0000  # reserved scratch near end of synthetic PS1 2 MB RAM
VALUE=0x51a7c3d9
XOR_MASK=0xffff
TRANSFORMED=VALUE^XOR_MASK
SEED0=0x1478295a
SEED1=0xd15ea5ed
BASE=22  # synthetic-only s6
DATA=23  # synthetic-only s7
MUTATIONS=("CORRECT","MISSING_SW","MISSING_LW")
FLAG="\tint vh181_nongpu_word_id=-1;\n"
CLI='\t\telse if (!strcmp(argv[i], "--vh181-nongpu-word-0"))\n'
INSERT="\tif (loadst_f) {\n"

def lw(rt,offset,rs):
    return (0x23<<26)|(rs<<21)|(rt<<16)|(offset&0xffff)

def xori(rt,rs,imm):
    return (0x0e<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)

def signed_sequence():
    words=(
        lui(BASE,RAM_ADDRESS>>16),               # scratch base
        lui(DATA,VALUE>>16),                     # nonzero authored value
        ori(DATA,DATA,VALUE&0xffff),
        sw(DATA,0,BASE),                         # real guest RAM write
        ori(DATA,0,0x00ff),                      # clobber prior to load
        lw(DATA,0,BASE),                         # real guest RAM read
        0,                                       # mandatory MIPS load-delay slot
        xori(DATA,DATA,XOR_MASK),                # depend on the load result
        sw(DATA,4,BASE),                         # store computed RAM value
    )
    assert len(words)==9 and TRANSFORMED==0x51a73c26
    return words

def make_variants():
    image,_,_,wait_pc,ops=v78_build()
    index=(wait_pc-START)//4
    if (image[:8]!=b"PS-X EXE" or image[0x4c:0x54]!=b"VH78SYN!" or
        len(image)!=10240 or tuple(ops[index:index+512])!=(0,)*512 or
        RAM_ADDRESS&3 or RAM_ADDRESS+4>=0x00200000):
        raise ValueError("v183 rejects noncanonical signed 512-NOP guest wait")
    seq=signed_sequence()
    offset=2048+index*4
    result={}
    for label in MUTATIONS:
        words=list(seq)
        if label=="MISSING_SW":words[3]=0
        elif label=="MISSING_LW":words[5]=0
        exe=bytearray(image)
        for i,w in enumerate(words):pack_into("<I",exe,offset+i*4,w)
        new=bytes(exe)
        if (new[0x4c:0x54]!=b"VH78SYN!" or
            new[:offset]!=image[:offset] or
            new[offset+len(words)*4:]!=image[offset+len(words)*4:]):
            raise ValueError("v183 mutations escaped nine signed guest wait NOPs")
        result[label]=new
    return result

def write_private(out:Path):
    if not out.is_dir() or out.is_symlink():
        raise ValueError("require an existing private output directory")
    blobs=make_variants()
    for label in MUTATIONS:
        path=out/("V183_RAM_"+label+".EXE")
        if path.exists() or path.is_symlink():
            raise ValueError("refuse overwrite or symlink in private fixture directory")
    for label in MUTATIONS:
        target=out/("V183_RAM_"+label+".EXE")
        # Existing workspace's output directory must be mode 0700.
        import os
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as file:file.write(blobs[label])
    return len(blobs)

def native_value_oracle():
    code=narrow_oracle()
    code=once(code,
        "if(vh176_mips_vblank_narrow_mmio_smoke) {",
        "if(vh183_guest_ram_values) {",
        "v183 diagnostic-only 4 real VBlank windows and true Unai oracle")
    anchor="unsigned int entry_count=vh78_vblank_observed_count;"
    code=once(code,anchor,
        "/* Explicit fixture seeding is host-owned only before guest executes;\n"
        " * it cannot create the guest's final two nonzero values. */\n"
        f"\t\t\tpsxMemWrite32(&psxRegs,0x{RAM_ADDRESS:08x}u,0x{SEED0:08x}u);\n"
        f"\t\t\tpsxMemWrite32(&psxRegs,0x{RAM_ADDRESS+4:08x}u,0x{SEED1:08x}u);\n"
        "\t\t\t"+anchor,
        "seed deterministic RAM in isolated synthetic emulator process")
    disarm="int vh176_disarmed=vh176_disarm_narrow(phase);"
    code=once(code,disarm,
        f"unsigned int vh183_first=psxMemRead32(&psxRegs,0x{RAM_ADDRESS:08x}u);\n"
        f"\t\t\tunsigned int vh183_second=psxMemRead32(&psxRegs,0x{RAM_ADDRESS+4:08x}u);\n"
        f"\t\t\tif(vh183_first!=0x{VALUE:08x}u || vh183_second!=0x{TRANSFORMED:08x}u){{\n"
        '                SysPrintf("VH183_NATIVE_RAM_VALUE_REFUSED phase=%u first_ok=%u derived_ok=%u\\n",phase,'
        f'vh183_first==0x{VALUE:08x}u,vh183_second==0x{TRANSFORMED:08x}u);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 85;\n"
        "\t\t\t}\n\t\t\tvh183_ram_windows++;\n"
        "\t\t\t"+disarm,
        "check actual RAM after real interpreted guest LW and SW before GPU oracles")
    decl="unsigned int vh176_narrow_windows=0u;"
    code=once(code,decl,decl+"\n\t\tunsigned int vh183_ram_windows=0u;",
              "record four distinct complete PSX RAM data-dependency checks")
    mark='SysPrintf("VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS'
    code=once(code,mark,
        'if(vh183_ram_windows!=4u){\n'
        '            SysPrintf("VH183_RAM_WINDOWS_REFUSED windows=%u\\n",vh183_ram_windows);\n'
        "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 85;\n"
        "\t\t}\n"
        '        SysPrintf("VH183_NATIVE_GUEST_RAM_VALUES_PASS windows=4 guest_sw_lw_dependency=1'
        ' real_memory_readback=1 vblanks=4 samples=2380 original_retail=0\\n");\n'
        "\t\t"+mark,
        "native RAM values and inherited GPU quiet observed before positive")
    return code

def patch_frontend(source:str):
    if "vh183_guest_ram_values" in source:
        raise ValueError("v183 frontend already modified")
    s=once(source,FLAG,FLAG+"\tint vh183_guest_ram_values=0;\n",
           "independent RAM data dependency mode")
    s=once(s,CLI,
        '\t\telse if (!strcmp(argv[i], "--vh183-guest-ram-values"))\n'
        '\t\t\tvh183_guest_ram_values=1;\n'+CLI,
        "synthetic-only native RAM readback CLI")
    return once(s,INSERT,native_value_oracle()+"\n"+INSERT,
                "genuine four-VBlank guest RAM value and pixel oracle")

def apply(root:Path):
    report=apply_v181(root)
    file=root.resolve()/"frontend/main.c"
    file.write_text(patch_frontend(file.read_text()))
    return dict(report,
        v183_source_authored_ram_expected_values=2,
        v183_guest_mips_load_store_dependency=True,
        v183_real_ram_recheck_per_vblank=4,
        v183_original_retail_executed=False,
        v183_physical_switch_output_verified=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generate-private",type=Path)
    p.add_argument("pinned_pcsx_checkout",type=Path,nargs="?")
    args=p.parse_args()
    if args.generate_private is not None:
        count=write_private(args.generate_private)
        print(f"VH183_SYNTHETIC_RAM_VALUE_VARIANTS_PASS count={count} guest_wait_words=9 original_retail=0")
    elif args.pinned_pcsx_checkout:
        print(apply(args.pinned_pcsx_checkout))
    else:
        p.error("provide --generate-private or pinned PCSX checkout")
if __name__=="__main__":
    main()

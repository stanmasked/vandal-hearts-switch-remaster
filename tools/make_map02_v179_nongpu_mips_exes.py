#!/usr/bin/env python3
"""Self-authored MIPS wait-pad variants exercising NON-GPU memory accesses.

Complements v173-v178 fail-closed GP0/GP1 tests with genuine interpreted
MIPS exclusion witnesses. All 8 variants mutate exactly one NOP, retain
the exact self-authored VH78SYN! header, and must still render all 2380
Unai pixel samples during four emulator-internal VBlank events.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from struct import pack
from .make_map02_v78_vblank_mips_exe import build, MAGIC
from .make_map02_v70_synthetic_psx_exe import START

# (opcode, rs/base register, 16-bit signed offset).
# $zero destination for loads prevents modification of staged GPU registers.
# Adjacent MMIO READS are at 0x1f80180f, 0x1f80180c, 0x1f801818.
# WRITES target unmapped-from-program normal guest RAM at address 0..2.
MUTANTS = {
    "LB_BELOW_GP0": (0x20, 8, -1),  # LB zero,-1(t0): byte 0x1f80180f
    "LHU_ABOVE_GP1": (0x25, 8, 8), # LHU zero,8(t0): 0x1f801818
    "LWL_BELOW_GP0": (0x22, 8, -1),# LWL zero,-1(t0): align 0x1f80180c
    "LWR_ABOVE_GP1": (0x26, 8, 8), # LWR zero,8(t0): align 0x1f801818
    "SB_RAM0": (0x28, 0, 0),       # SB zero,0(zero): ordinary RAM
    "SH_RAM2": (0x29, 0, 2),       # SH zero,2(zero): ordinary RAM
    "SWL_RAM2": (0x2a, 0, 2),      # SWL zero,2(zero): write16+8 RAM
    "SWR_RAM1": (0x2e, 0, 1),      # SWR zero,1(zero): write8+16 RAM
}
OUTPUT_PREFIX = "V179_NONGPU_"

def mips_word(opcode: int, base: int, offset: int) -> int:
    if not (0 <= opcode < 64 and 0 <= base < 32 and -32768 <= offset < 32768):
        raise ValueError("invalid bounded source-authored instruction")
    return (opcode << 26) | (base << 21) | (offset & 0xffff)

def originals():
    data, stops, starts, wait_pc, ops = build()
    index = (wait_pc - START) // 4
    if (data[:8] != b"PS-X EXE" or data[0x4c:0x54] != MAGIC or
        len(stops) != 4 or ops[index:index + 512] != (0,) * 512 or
        len(data) != 2048 + 8192):
        raise ValueError("signed v78 source/original NOP region changed")
    return data, index

def generate() -> dict[str,bytes]:
    original, index = originals()
    off = 2048 + index * 4
    variants: dict[str,bytes] = {}
    for label,(opcode,base,offset) in MUTANTS.items():
        word=mips_word(opcode,base,offset)
        changed=bytearray(original)
        changed[off:off + 4]=pack("<I",word)
        data=bytes(changed)
        if (data[:2048] != original[:2048] or
            data[:off] != original[:off] or
            data[off+4:] != original[off+4:] or
            data[off:off+4] == original[off:off+4]):
            raise ValueError("more than one synthetic wait-pad word changed")
        variants[label]=data
    return variants

def write_private(out_dir: Path) -> list[Path]:
    if out_dir.is_symlink() or not out_dir.is_dir():
        raise ValueError("destination must be an existing private directory")
    created=[]
    for label,data in generate().items():
        target=out_dir/(OUTPUT_PREFIX+label+".EXE")
        if target.is_symlink() or target.exists():
            raise ValueError(f"refusing to overwrite {target.name}")
        target.write_bytes(data)
        target.chmod(0o600)
        created.append(target)
    return created

def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir",type=Path,required=True)
    args=ap.parse_args()
    written=write_private(args.output_dir)
    print(f"VH179_NONGPU_SYNTHETIC_VARIANTS_PASS count={len(written)} one_wait_word_each=1 signed_source=1 original_retail=0")

if __name__=="__main__":
    main()

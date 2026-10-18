#!/usr/bin/env python3
"""Conservative PS1 MIPS-I delay-slot aware static GPU/DMA candidate auditor.

A branch or jump executes its NEXT instruction before transferring control.
The original v131 linear pass invalidated known bases too early and could
under-count plausible SW sites in delay slots. This audit preserves those
pre-branch constants for precisely one delay-slot instruction, then drops
all speculative state before reading the following linear instruction.
No guessed MIPS execution or GPU command value enters a public report.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from .analyze_map02_v131_private_mips_mmio import (
    MMIO, NAME_ORDER, Refused, _canonical_mmio, _signed16,
    parse_psx_text, read_private_exe
)

SCHEMA="vh.map02.private-mips-delay-slot-static-candidates.v1"
# Branch-likely opcodes belong to MIPS II and are reserved on PS1 R3000A.
RESERVED_LIKELY_OPS=(0x14,0x15,0x16,0x17)
CONTROL_OPS=(0x01,0x02,0x03,0x04,0x05,0x06,0x07,
             0x14,0x15,0x16,0x17)

def _reset():
    registers=[None]*32
    registers[0]=0
    return registers

def _get(regs,reg):
    return 0 if reg==0 else regs[reg]

def analyze_delay_aware_text(text):
    if type(text) is not bytes or not text or len(text)%4:
        raise Refused("invalid aligned MIPS instruction stream")
    counts={name:0 for name in NAME_ORDER}
    counts["dma2_linked_list_chcr_literal"]=0
    metadata={
        "control_flow_delay_slots":0,
        "constant_proven_sw_in_delay_slots":0,
        "unsupported_mips_ii_branch_likely_opcode_sites":0,
        "ambiguous_control_in_delay_slot":0,
    }
    regs=_reset()
    pending=None
    for (word,) in struct.iter_unpack("<I",text):
        old_pending=pending
        pending=None
        opcode=word>>26
        rs=(word>>21)&31
        rt=(word>>16)&31
        imm=word&0xffff
        is_jr=opcode==0 and (word&0x3f) in (0x08,0x09)
        is_cop_branch=(opcode in (0x10,0x11,0x12,0x13) and rs==0x08)
        controls=(opcode in CONTROL_OPS or is_jr or is_cop_branch)
        # A control transfer inside a delay slot is architecturally
        # ambiguous. Never infer register values from such a word.
        if old_pending is not None and controls:
            metadata["ambiguous_control_in_delay_slot"]+=1
            regs=_reset()
            continue
        if old_pending is not None:
            metadata["control_flow_delay_slots"]+=1
        # MIPS II BEQL/BNEL/BLEZL/BGTZL and REGIMM/COP likely variants
        # are NOT runnable branch-likely instructions on PS1 R3000A.
        # Treat their bytes as unsupported, invalidate all constants,
        # and never credit a GPU/DMA SW in their following word.
        unsupported_likely=(
            opcode in RESERVED_LIKELY_OPS or
            (opcode==0x01 and rt in (2,3,18,19)) or
            (is_cop_branch and rt in (2,3))
        )
        if unsupported_likely:
            metadata["unsupported_mips_ii_branch_likely_opcode_sites"]+=1
            regs=_reset()
            continue
        val=_get(regs,rs)
        if word==0: # No-op does not clobber any register.
            pass
        elif opcode==0x0f:
            if rt:regs[rt]=imm<<16
        elif opcode==0x0d:
            if rt:regs[rt]=(val|imm)&0xffffffff if val is not None else None
        elif opcode in (0x08,0x09):
            if rt:regs[rt]=(val+_signed16(imm))&0xffffffff if val is not None else None
        elif opcode==0x0c:
            if rt:regs[rt]=(val&imm) if val is not None else None
        elif opcode==0x0e:
            if rt:regs[rt]=(val^imm) if val is not None else None
        elif opcode==0x2b:
            if val is not None:
                address=_canonical_mmio((val+_signed16(imm))&0xffffffff)
                if address in MMIO:
                    kind=MMIO[address]
                    counts[kind]+=1
                    if kind=="dma2_chcr" and _get(regs,rt)==0x01000401:
                        counts["dma2_linked_list_chcr_literal"]+=1
                    if old_pending is not None:
                        metadata["constant_proven_sw_in_delay_slots"]+=1
        elif opcode in (0x28,0x29,0x2a,0x2e):
            pass
        elif opcode in (0x20,0x21,0x22,0x23,0x24,0x25,0x26,0x27,
                      0x30,0x31,0x32,0x33,0x34,0x35,0x36,0x37):
            if rt:regs[rt]=None
        elif opcode==0:
            rd=(word>>11)&31
            funct=word&0x3f
            rhs=_get(regs,rt)
            if funct in (0x20,0x21):
                if rd:regs[rd]=(val+rhs)&0xffffffff if val is not None and rhs is not None else None
            elif funct==0x25:
                if rd:regs[rd]=(val|rhs) if val is not None and rhs is not None else None
            elif funct==0x09: # JALR also overwrites its link-register GPR.
                if rd:regs[rd]=None
            elif not is_jr:
                if rd:regs[rd]=None
        elif opcode in CONTROL_OPS:
            if opcode==0x03 or (opcode==0x01 and rt in (0x10,0x11,0x12,0x13)):
                regs[31]=None # Link register changes before delay slot.
        else:
            # Coprocessor/non-modeled instruction: unknown next GPR state.
            regs=_reset()
        if controls:
            pending="ordinary"
        if old_pending is not None:
            regs=_reset()
    if pending is not None:
        # An isolated control word without its required delay instruction
        # must never be accepted as a complete MIPS text section.
        raise Refused("MIPS instruction text ends inside a branch delay slot")
    return counts,metadata


def audit_private_exe(path):
    text=parse_psx_text(read_private_exe(path))
    counts,control=analyze_delay_aware_text(text)
    return {
        "schema":SCHEMA,
        "input_kind":"local_private_user_owned_psx_exe",
        "candidate_sw_instruction_counts":counts,
        "static_delay_slot_candidate_counts":control,
        "analysis_kind":"conservative_linear_mips_delay_slot_candidate_inventory",
        "did_not_execute_mips":True,
        "ps1_r3000a_mips_ii_branch_likely_not_credited":True,
        "delay_slot_control_transfer_is_ambiguous_and_not_proven":True,
        "candidate_mmio_not_proof_of_executed_dma":True,
        "private_program_bytes_exported":False,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_psx_exe",type=Path)
    args=parser.parse_args()
    try:
        report=audit_private_exe(args.private_psx_exe)
    except (Refused,OSError,ValueError,struct.error):
        parser.exit(2,"VH132_PRIVATE_MIPS_DELAY_SLOT_REFUSED\n")
    print(json.dumps(report,sort_keys=True,separators=(",",":")))


if __name__=="__main__":
    main()

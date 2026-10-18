#!/usr/bin/env python3
"""Local-only original US executable/MIPS ELF *code-section* provenance.

Unlike v135's broad PS-X payload scan, static MIPS GPU/DMA candidates are
taken ONLY from byte-identical SHF_ALLOC|SHF_EXECINSTR PROGBITS in the
independently extracted ELF. Data/rodata are never interpreted as instructions.
This remains a static, unexecuted candidate inventory, not a retail scene.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from .analyze_map02_v131_private_mips_mmio import Refused,read_private_exe,parse_psx_text
from .analyze_map02_v132_mips_delay_slots import analyze_delay_aware_text
from .analyze_map02_v135_original_us_elf_pair import (
    ANCHORS,PINNED_LOAD,PINNED_US_EXE_MD5,
    compare_original_data_anchors,read_private_elf,parse_loaded_mips_elf_sections
)

SCHEMA="vh.map02.private-us-exe-elf-executable-code-section-candidates.v1"
MAX_CODE_BYTES=2*1024*1024


def _elf_exec_sections(raw):
    """Require a real, unique ELF32 MIPS file-backed executable section map."""
    # Reuse the stricter original ELF header / table validation before inspect.
    parse_loaded_mips_elf_sections(raw)
    shoff=struct.unpack_from("<I",raw,32)[0]
    entsize,count=struct.unpack_from("<HH",raw,46)
    code=[]
    for index in range(count):
        base=shoff+index*entsize
        kind,flags,address,offset,size=struct.unpack_from("<IIIII",raw,base+4)
        if not (flags&4):
            continue
        if (kind!=1 or not flags&2 or not size or
                address&3 or size&3 or offset&3 or
                size>MAX_CODE_BYTES or offset+size>len(raw) or
                address+size>0x100000000):
            raise Refused("invalid executable MIPS ELF section boundaries")
        code.append((address,address+size,offset))
    if not code:
        raise Refused("no MIPS ELF executable loaded code sections")
    code.sort()
    if any(code[i][1]>code[i+1][0] for i in range(len(code)-1)):
        raise Refused("overlapping executable MIPS ELF address sections")
    return code


def original_code_sections(exe,elf):
    """Return verified private source code slices only, never copy to report."""
    code_data=parse_psx_text(exe)
    if struct.unpack_from("<I",exe,0x18)[0]!=PINNED_LOAD:
        raise Refused("unexpected pinned US PS-X executable load address")
    code_sections=_elf_exec_sections(elf)
    mapped=[]
    size=0
    for address,end,offset in code_sections:
        local=address-PINNED_LOAD
        length=end-address
        if local<0 or local+length>len(code_data):
            raise Refused("extracted executable MIPS code outside PS-X image")
        # A genuine .text section must never overlap source-pinned original
        # data anchors (MAP32, MAP35, font). This prevents classifying
        # already-proven DATA as executable MIPS instructions.
        if any(address<addr+n and addr<end for _,addr,n in ANCHORS):
            raise Refused("MIPS ELF code section overlaps original data anchor")
        original=code_data[local:local+length]
        if original!=elf[offset:offset+length]:
            raise Refused("extracted executable MIPS instructions mismatch")
        mapped.append(original)
        size+=length
        if size>MAX_CODE_BYTES:
            raise Refused("too many original executable MIPS bytes")
    return mapped


def compare_static_code_candidate_counts(exe,elf):
    sections=original_code_sections(exe,elf)
    counts=None
    delay_counts={
        "control_flow_delay_slots":0,
        "constant_proven_sw_in_delay_slots":0,
        "unsupported_mips_ii_branch_likely_opcode_sites":0,
        "ambiguous_control_in_delay_slot":0,
    }
    for source in sections:
        profile,delays=analyze_delay_aware_text(source)
        if counts is None:
            counts=dict.fromkeys(profile,0)
        if set(profile)!=set(counts) or set(delays)!=set(delay_counts):
            raise Refused("MIPS code analysis result shape mismatch")
        for k,val in profile.items():
            counts[k]+=val
        for k,val in delays.items():
            delay_counts[k]+=val
    return len(sections),sum(len(s)//4 for s in sections),counts,delay_counts


def analyze_source_verified_pair(exe_path,elf_path):
    exe=read_private_exe(exe_path)
    elf=read_private_elf(elf_path)
    # The MD5 is a historical selector from PR #91, NOT robust
    # cryptographic retail proof or full code authenticity.
    if hashlib.md5(exe).hexdigest()!=PINNED_US_EXE_MD5:
        raise Refused("private US retail selector did not match")
    anchors=compare_original_data_anchors(exe,elf)
    section_count,words,counts,delays=compare_static_code_candidate_counts(exe,elf)
    # Check the actual same input bytes once more after all data/code work.
    if read_private_exe(exe_path)!=exe or read_private_elf(elf_path)!=elf:
        raise Refused("private original EXE / MIPS ELF changed during analysis")
    return {
        "schema":SCHEMA,
        "scope":"locally_selected_original_us_psx_exe_and_extracted_mips_elf",
        "historical_us_retail_md5_selector_matched":True,
        "md5_is_not_collision_resistant_provenance":True,
        "original_data_anchor_labels":anchors,
        "original_data_anchors_byte_identical":len(anchors),
        "executable_sections_byte_identical":section_count,
        "source_verified_executable_mips_instruction_words":words,
        "executable_code_only_candidate_sw_counts":counts,
        "executable_code_only_delay_slot_counts":delays,
        "full_original_executable_code_equivalence_proven":False,
        "instruction_reachability_or_execution_proven":False,
        "original_map02_gameplay_or_rendering_verified":False,
        "physical_ps1_equivalence_verified":False,
        "switch_hd_graphics_parity_verified":False,
        "game_bytes_or_private_hashes_exported":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_owned_us_psx_exe",type=Path)
    p.add_argument("private_extracted_mips_elf",type=Path)
    args=p.parse_args()
    try:
        report=analyze_source_verified_pair(
            args.private_owned_us_psx_exe,args.private_extracted_mips_elf)
    except (Refused,ValueError,OSError,struct.error):
        p.exit(2,"VH136_ORIGINAL_MIPS_CODE_SECTION_REFUSED\n")
    print(json.dumps(report,sort_keys=True,separators=(",",":")))


if __name__=="__main__":
    main()

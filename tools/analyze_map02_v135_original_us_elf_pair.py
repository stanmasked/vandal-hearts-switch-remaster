#!/usr/bin/env python3
"""Bind *local* US PS-X MIPS candidates to pinned original extraction anchors.

The public pinned retail MD5 is used ONLY as a legacy identity selector, not
a collision-resistant signature. Byte-exact data-anchor comparisons between
the private PS-X executable and private extracted MIPS ELF are independent.
Neither file, individual hash, private path, nor source MIPS instruction is
ever printed, committed or uploaded by this program. No retail data in CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

from .analyze_map02_v131_private_mips_mmio import (
    Refused,_open_private_exe_dirfd,_snapshot,_read_exact,
    read_private_exe,parse_psx_text
)
from .analyze_map02_v132_mips_delay_slots import analyze_delay_aware_text

SCHEMA="vh.map02.private-us-psx-exe-mips-elf-static-candidates.v1"
PINNED_US_EXE_MD5="596bb082a2de5f1fe977dd3d7e160b03"
PINNED_LOAD=0x80010000
ELF_MAX_BYTES=64*1024*1024
ANCHORS=(
    ("original_map32_data",0x801009bc,32),
    ("original_map35_data",0x80100e9c,32),
    ("original_ascii_font_bitmap",0x801012e4,128*9),
)


def read_private_elf(path):
    """Two-pass, private descriptor-anchored read of an ELF, no extra opens."""
    fd=_open_private_exe_dirfd(path)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
                or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600
                or not 52<=info.st_size<=ELF_MAX_BYTES):
            raise Refused("private MIPS ELF metadata or size refused")
        snap=_snapshot(info)
        first=_read_exact(fd,info.st_size)
        if _snapshot(os.fstat(fd))!=snap:
            raise Refused("private MIPS ELF changed during read")
        os.lseek(fd,0,os.SEEK_SET)
        second=_read_exact(fd,info.st_size)
        if (hashlib.sha256(first).digest()!=hashlib.sha256(second).digest()
                or _snapshot(os.fstat(fd))!=snap):
            raise Refused("private MIPS ELF changed during two-pass read")
        return first
    except OSError:
        raise Refused("private MIPS ELF read refused") from None
    finally:
        os.close(fd)


def parse_loaded_mips_elf_sections(raw):
    """Only unique ELF32 MIPS little-endian SHF_ALLOC PROGBITS are usable."""
    if (type(raw) is not bytes or not 52<=len(raw)<=ELF_MAX_BYTES or
            raw[:4]!=b"\x7fELF" or raw[4]!=1 or raw[5]!=1 or
            raw[6]!=1 or struct.unpack_from("<H",raw,18)[0]!=8):
        raise Refused("original extracted ELF must be MIPS ELF32 little-endian")
    if struct.unpack_from("<H",raw,16)[0] not in (2,3):
        raise Refused("MIPS ELF must be executable or shared object")
    shoff=struct.unpack_from("<I",raw,32)[0]
    entsize,count=struct.unpack_from("<HH",raw,46)
    if (shoff<52 or entsize<40 or count<1 or count>512 or
            shoff+entsize*count>len(raw)):
        raise Refused("MIPS ELF section header table refused")
    sections=[]
    for idx in range(count):
        section=shoff+idx*entsize
        kind,flags,address,offset,size=struct.unpack_from("<IIIII",raw,section+4)
        if kind==1 and (flags & 0x2) and size:
            if offset+size>len(raw) or address+size>0x100000000:
                raise Refused("MIPS ELF file-backed allocated section overflows")
            sections.append((address,address+size,offset))
    return sections


def compare_original_data_anchors(exe,elf):
    """Compare exact original-data bytes, not pixel/GP0 samples or whole code."""
    if type(exe) is not bytes:
        raise Refused("invalid original PS-X image")
    text=parse_psx_text(exe)
    load=struct.unpack_from("<I",exe,0x18)[0]
    if load!=PINNED_LOAD:
        raise Refused("private US PS-X EXE has wrong pinned load address")
    sections=parse_loaded_mips_elf_sections(elf)
    names=[]
    for name,addr,length in ANCHORS:
        position=0x800+addr-PINNED_LOAD
        if position<0x800 or position+length>0x800+len(text):
            raise Refused("original data anchor outside private PS-X text")
        match=[(start,offset) for start,end,offset in sections
               if start<=addr and addr+length<=end]
        if len(match)!=1:
            raise Refused("original extracted MIPS ELF data anchor nonunique")
        start,offset=match[0]
        if exe[position:position+length]!=elf[
                offset+addr-start:offset+addr-start+length]:
            raise Refused("original EXE and MIPS ELF data anchors differ")
        names.append(name)
    return names


def analyze_pinned_original_pair(exe_path,elf_path):
    # File names/path strings never enter a printed result or a public artifact.
    exe=read_private_exe(exe_path)
    elf=read_private_elf(elf_path)
    if hashlib.md5(exe).hexdigest()!=PINNED_US_EXE_MD5:
        raise Refused("owned executable does not match pinned US retail selector")
    names=compare_original_data_anchors(exe,elf)
    source= parse_psx_text(exe)
    counts,delays=analyze_delay_aware_text(source)
    # Detect in-place changes during analysis, including no-length changes.
    # The original and extracted ELF remain private, including checksums.
    if (read_private_exe(exe_path)!=exe or read_private_elf(elf_path)!=elf):
        raise Refused("private extraction pair changed during source analysis")
    return {
        "schema":SCHEMA,
        "scope":"local_user_owned_us_psx_exe_and_extracted_mips_elf",
        "legacy_original_us_md5_selector_matched":True,
        "private_exe_elf_data_anchor_names":names,
        "private_exe_elf_data_anchors_identical":len(names),
        "candidate_sw_instruction_counts":counts,
        "static_delay_slot_candidate_counts":delays,
        "legacy_md5_is_not_collision_resistant_authentication":True,
        "extracted_mips_elf_full_code_equivalence_proven":False,
        "actual_mips_instructions_executed":False,
        "map02_gameplay_or_rendering_verified":False,
        "physical_ps1_equivalence_verified":False,
        "nintendo_switch_hd_parity_verified":False,
        "game_bytes_or_private_hashes_exported":False,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_owned_us_psx_exe",type=Path)
    parser.add_argument("private_extracted_mips_elf",type=Path)
    args=parser.parse_args()
    try:
        result=analyze_pinned_original_pair(
            args.private_owned_us_psx_exe,args.private_extracted_mips_elf)
    except (Refused,OSError,ValueError,struct.error):
        parser.exit(2,"VH135_PRIVATE_ORIGINAL_MIPS_ELF_BINDING_REFUSED\n")
    print(json.dumps(result,sort_keys=True,separators=(",",":")))


if __name__=="__main__":
    main()

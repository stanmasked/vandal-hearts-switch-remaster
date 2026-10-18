#!/usr/bin/env python3
"""Private original PS-X EXE -> bounded PS1 RAM / entry boot-plan preflight.

NO original EXE bytes are published. NO retail instructions run here. A
successful local preflight validates the historical US edition selector,
source-matched extracted ELF code, source data anchors, executable entry
mapping, PS1 2 MiB RAM layout, register header and a deterministic guest
RAM copy. It creates a NEW mode-0600 private manifest for a later isolated
native loader stage, not a runnable game or MAP02 frame.

Public GCC/Clang tests call the pure validator with synthetic EXE/ELF while
the CLI ALWAYS requires the pinned original US MD5 selector and refuses it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import stat

from .analyze_map02_v131_private_mips_mmio import (
    Refused,read_private_exe,parse_psx_text,RAM_BYTES,
)
from .analyze_map02_v135_original_us_elf_pair import (
    PINNED_LOAD,PINNED_US_EXE_MD5,read_private_elf,
    compare_original_data_anchors,
)
from .analyze_map02_v136_original_code_sections import (
    original_code_sections,_elf_exec_sections,
)
from .run_map02_v146_verified_fd_native import _open_private_dirfd
from .verify_map02_v141_private_original_mmio_claims import (
    read_private_exact_mmio_trace,
)

SCHEMA="vh.map02.private-original-us-guest-boot-plan.v1"
MANIFEST_LEAF="vh148-private-original-boot-plan.json"
MAX_MANIFEST_BYTES=4096


def _sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def derive_guest_boot_plan(exe:bytes,elf:bytes,*,require_original:bool=True):
    """Pure source-consistency and RAM-layout validator, does not execute code."""
    if require_original and hashlib.md5(exe).hexdigest()!=PINNED_US_EXE_MD5:
        raise Refused("pinned original US executable edition selector refused")
    text=parse_psx_text(exe)
    anchors=compare_original_data_anchors(exe,elf)
    matched=original_code_sections(exe,elf)
    sections=_elf_exec_sections(elf)
    if len(anchors)!=3 or not matched or len(matched)!=len(sections):
        raise Refused("original code and asset source mapping incomplete")
    entry,gp,load,size=struct.unpack_from("<IIII",exe,0x10)
    bss,bss_bytes,sp_base,sp_offset=struct.unpack_from("<IIII",exe,0x28)
    if load!=PINNED_LOAD or size!=len(text):
        raise Refused("private original US executable load or size mismatch")
    if (not any(start<=entry and entry+4<=end for start,end,_ in sections)
            or entry%4 or entry+4>0x100000000):
        raise Refused("guest entry is outside source-matched executable code")
    physical_load=load&0x1fffffff
    if (physical_load+size>RAM_BYTES or
            (entry&0x1fffffff)+4>RAM_BYTES or
            (entry&0x1fffffff)<physical_load):
        raise Refused("guest code cannot fit PS1 2 MiB RAM")
    # BSS may be omitted; a nonempty BSS must be mapped and never overlap
    # file-backed code. This preflight refuses ambiguous placement.
    if bss_bytes:
        if (bss&0xe0000000) not in (0x80000000,0xa0000000):
            raise Refused("guest BSS unmapped alias")
        physical_bss=bss&0x1fffffff
        if (physical_bss+ bss_bytes>RAM_BYTES or
                not (physical_bss>=physical_load+size or
                     physical_bss+bss_bytes<=physical_load)):
            raise Refused("guest BSS outside RAM or overlaps executable image")
    # GP and SP are optional header registers. Non-zero virtual addresses
    # must still refer to normal kuseg/kseg0/kseg1 or known 2 MiB RAM.
    for raw in (gp,(sp_base+sp_offset)&0xffffffff if sp_base else 0):
        if raw and ((raw&0xe0000000) not in (0,0x80000000,0xa0000000)
                    or (raw&0x1fffffff)>=RAM_BYTES):
            raise Refused("guest initial GP/SP points beyond normal PS1 RAM")
    ram=bytearray(RAM_BYTES)
    ram[physical_load:physical_load+size]=text
    if bss_bytes:
        # ram is initialized zero; explicit guarded range retained.
        assert ram[physical_bss:physical_bss+bss_bytes]==b"\x00"*bss_bytes
    entry_at=(entry&0x1fffffff)
    entry_word=bytes(ram[entry_at:entry_at+4])
    section_words=sum(len(chunk)//4 for chunk in matched)
    if len(entry_word)!=4 or section_words<1:
        raise Refused("guest entry word absent")
    # Digest the populated load segment rather than publishing guest RAM.
    return {
        "schema":SCHEMA,
        "scope":"source_verified_guest_load_plan_not_executed",
        "edition": "original_us_legacy_md5" if require_original else "synthetic_fixture_only",
        "exe_sha256":_sha(exe),
        "extracted_elf_sha256":_sha(elf),
        "text_sha256":_sha(text),
        "entry_instruction_sha256":_sha(entry_word),
        "ram_load_sha256":_sha(bytes(ram[physical_load:physical_load+size])),
        "load_virtual":load,
        "entry_virtual":entry,
        "loaded_text_bytes":size,
        "verified_exec_sections":len(matched),
        "verified_exec_words":section_words,
        "verified_source_data_anchors":len(anchors),
        "bss_bytes":bss_bytes,
        "gp_nonzero":bool(gp),
        "sp_nonzero":bool(sp_base),
        "ps1_ram_bytes":RAM_BYTES,
        "retail_guest_code_executed":False,
        "disc_and_bios_runtime_ready":False,
        "original_map02_rendered":False,
        "nintendo_switch_hd_parity_verified":False,
    }


def _canonical(plan):
    return (json.dumps(plan,sort_keys=True,separators=(",",":"))+"\n").encode()


def prepare_private_original_boot_plan(exe_path,elf_path,private_directory):
    exe=read_private_exe(exe_path)
    elf=read_private_elf(elf_path)
    plan=derive_guest_boot_plan(exe,elf,require_original=True)
    directory_fd=-1
    fd=-1
    created=False
    committed=False
    try:
        directory_fd=_open_private_dirfd(private_directory)
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
        fd=os.open(MANIFEST_LEAF,flags,0o600,dir_fd=directory_fd)
        created=True
        payload=_canonical(plan)
        if len(payload)>MAX_MANIFEST_BYTES:
            raise Refused("boot plan exceeds private manifest size")
        offset=0
        while offset<len(payload):
            n=os.write(fd,payload[offset:])
            if n<=0:
                raise Refused("private boot plan incomplete")
            offset+=n
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid()
                or st.st_nlink!=1 or stat.S_IMODE(st.st_mode)!=0o600):
            raise Refused("private boot manifest filesystem metadata invalid")
        os.fsync(fd)
        os.close(fd)
        fd=-1
        os.fsync(directory_fd)
        # Reject a changed original input or extracted code after publication.
        if (read_private_exe(exe_path)!=exe or
                read_private_elf(elf_path)!=elf or
                read_private_boot_plan(Path(private_directory)/MANIFEST_LEAF)!=plan):
            raise Refused("private original assets changed during boot planning")
        committed=True
        return plan
    except OSError:
        raise Refused("private original boot plan could not be safely saved") from None
    finally:
        if fd>=0: os.close(fd)
        if directory_fd>=0:
            if created and not committed:
                try: os.unlink(MANIFEST_LEAF,dir_fd=directory_fd)
                except OSError: pass
            os.close(directory_fd)


def read_private_boot_plan(path):
    raw=read_private_exact_mmio_trace(path)
    if not raw or len(raw)>MAX_MANIFEST_BYTES:
        raise Refused("private guest boot plan size invalid")
    try:
        pairs=[]
        def unique(items):
            obj={}
            for key,value in items:
                if key in obj: raise Refused("duplicate guest boot plan key")
                obj[key]=value
            return obj
        plan=json.loads(raw,object_pairs_hook=unique)
    except (UnicodeError,ValueError,TypeError):
        raise Refused("malformed private guest boot plan") from None
    if (type(plan) is not dict or plan.get("schema")!=SCHEMA or
            plan.get("retail_guest_code_executed") is not False or
            raw!=_canonical(plan)):
        raise Refused("private guest boot plan changed or made executable")
    return plan


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_original_us_psx_exe",type=Path)
    p.add_argument("private_extracted_mips_elf",type=Path)
    p.add_argument("private_output_directory",type=Path)
    args=p.parse_args()
    try:
        plan=prepare_private_original_boot_plan(
            args.private_original_us_psx_exe,args.private_extracted_mips_elf,
            args.private_output_directory)
    except (Refused,OSError,ValueError,struct.error):
        p.exit(2,"VH148_PRIVATE_ORIGINAL_BOOT_PLAN_REFUSED\n")
    print("VH148_PRIVATE_ORIGINAL_ENTRY_PREFLIGHT_PASS "
          "source_bound_sections=%d runtime_executed=0 "
          "map02_rendered=0 private_bytes_exported=0"
          %plan["verified_exec_sections"])


if __name__=="__main__":
    main()

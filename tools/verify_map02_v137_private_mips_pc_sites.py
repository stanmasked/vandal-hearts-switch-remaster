#!/usr/bin/env python3
"""Privately correlate claimed MIPS MMIO PCs with byte-verified original code.

A caller supplies a separate 0600 JSONL of *claimed* MMIO events. Acceptance
means only that each supplied PC and register CLASS corresponds to a possible
static MIPS SW candidate in source-bound ELF executable sections. It does NOT
authenticate who produced the observations, establish branch reachability,
prove DMA ran or attest original retail MAP02 gameplay.

Never print original program PCs, instruction words, event PCs, file names,
private hashes, source instructions, content bytes or an event-by-event trace.
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
    NAME_ORDER,Refused,_open_private_exe_dirfd,_snapshot,_read_exact,
    read_private_exe,
)
from .analyze_map02_v132_mips_delay_slots import analyze_delay_aware_text
from .analyze_map02_v135_original_us_elf_pair import (
    PINNED_US_EXE_MD5,compare_original_data_anchors,read_private_elf,
)
from .analyze_map02_v136_original_code_sections import (
    _elf_exec_sections,original_code_sections,compare_static_code_candidate_counts,
)

SCHEMA="vh.map02.private-source-pc-static-candidate-correlation.v1"
EVENT_SCHEMA="vh.map02.private-mmio-pc-claim.v1"
MAX_CLAIM_BYTES=16*1024
MAX_CLAIMS=256
MAX_STATIC_SITES=65536


def read_private_claims(path):
    """Two-pass, same-fd, no-symlink, 0600 regular JSONL receipt read."""
    fd=_open_private_exe_dirfd(path)
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid()
                or st.st_nlink!=1 or stat.S_IMODE(st.st_mode)!=0o600
                or not 1<=st.st_size<=MAX_CLAIM_BYTES):
            raise Refused("private MMIO PC claim file metadata refused")
        snap=_snapshot(st)
        first=_read_exact(fd,st.st_size)
        if _snapshot(os.fstat(fd))!=snap:
            raise Refused("private MMIO PC claims changed during initial read")
        os.lseek(fd,0,os.SEEK_SET)
        second=_read_exact(fd,st.st_size)
        if (first!=second or _snapshot(os.fstat(fd))!=snap):
            raise Refused("private MMIO PC claims changed during second read")
        return first
    except OSError:
        raise Refused("private MMIO PC claims could not be safely read") from None
    finally:
        os.close(fd)


def _unique_object(pairs):
    record={}
    for key,value in pairs:
        if key in record:
            raise Refused("duplicate private MMIO PC claim field")
        record[key]=value
    return record


def parse_pc_claims(raw):
    if (type(raw) is not bytes or not raw or len(raw)>MAX_CLAIM_BYTES
            or not raw.endswith(b"\n") or b"\r" in raw):
        raise Refused("noncanonical private MMIO PC claim JSONL")
    lines=raw.split(b"\n")[:-1]
    if not 1<=len(lines)<=MAX_CLAIMS:
        raise Refused("wrong private MMIO PC claim count")
    allowed=set(NAME_ORDER)
    claims=[]
    for line in lines:
        try:
            item=json.loads(line,object_pairs_hook=_unique_object)
        except (ValueError,UnicodeError):
            raise Refused("malformed private MMIO PC claim JSONL") from None
        if (type(item) is not dict
                or set(item)!={"schema","pc","kind"}
                or item["schema"]!=EVENT_SCHEMA
                or type(item["pc"]) is not int
                or not 0<=item["pc"]<=0xffffffff
                or type(item["kind"]) is not str
                or item["kind"] not in allowed
                or json.dumps(item,sort_keys=True,separators=(",",":")).encode()!=line):
            raise Refused("noncanonical private MMIO PC claim fields")
        claims.append((item["pc"],item["kind"]))
    return claims


def source_bound_pc_sites(exe,elf):
    """Private per-word PC allowlist from exactly v136's verified .text bytes."""
    code=original_code_sections(exe,elf)
    sections=_elf_exec_sections(elf)
    if len(code)!=len(sections):
        raise Refused("original ELF executable region count disagrees")
    pcs={}
    totals={name:0 for name in NAME_ORDER}
    totals["dma2_linked_list_chcr_literal"]=0
    for (start,end,_offset),source in zip(sections,code):
        if len(source)!=(end-start):
            raise Refused("private executable MIPS section address mismatch")
        def record(offset,kind,linked):
            if offset%4 or not 0<=offset<len(source):
                raise Refused("invalid executable MIPS instruction offset")
            pc=start+offset
            if pc in pcs or len(pcs)>=MAX_STATIC_SITES:
                raise Refused("duplicate or excessive executable PC sites")
            pcs[pc]=(kind,linked)
            totals[kind]+=1
            if linked:
                if kind!="dma2_chcr":
                    raise Refused("linked list literal on non-CHCR instruction")
                totals["dma2_linked_list_chcr_literal"]+=1
        analyze_delay_aware_text(source,site_sink=record)
    _section_count,_word_count,prior, _delays=compare_static_code_candidate_counts(
        exe,elf)
    if totals!=prior or not pcs:
        raise Refused("static MMIO PC site reconciliation mismatch")
    return pcs,totals


def correlate_pc_claims(exe,elf,claims):
    """Untrusted external PC list; matching static sites does not attest execution."""
    if type(claims) is not list or not 1<=len(claims)<=MAX_CLAIMS:
        raise Refused("invalid private MMIO PC claim series")
    pcs,source_counts=source_bound_pc_sites(exe,elf)
    counts={name:0 for name in NAME_ORDER}
    observed=set()
    for record in claims:
        if (type(record) is not tuple or len(record)!=2
                or type(record[0]) is not int
                or type(record[1]) is not str):
            raise Refused("invalid private MMIO PC claim shape")
        pc,kind=record
        if (pc not in pcs or kind!=pcs[pc][0]):
            raise Refused("claimed MMIO PC absent from verified original code")
        observed.add(pc)
        counts[kind]+=1
    return {
        "schema":SCHEMA,
        "private_claims_matching_static_code_candidates":len(claims),
        "private_unique_source_pc_sites_matched":len(observed),
        "private_static_candidate_site_count":len(pcs),
        "claimed_mmio_register_class_counts":counts,
        "source_verified_code_only_candidate_counts":source_counts,
        "claim_producer_authenticated":False,
        "execution_or_reachability_proven":False,
        "dma_or_gpu_runtime_execution_proven":False,
        "original_map02_frame_or_rendering_proven":False,
        "physical_ps1_equivalence_proven":False,
        "nintendo_switch_hd_parity_proven":False,
        "raw_pcs_instructions_paths_or_private_hashes_exported":False,
    }


def audit_private_pair_and_pc_claims(exe_path,elf_path,claim_path):
    # Historical selector and original data anchors gate the production path.
    exe=read_private_exe(exe_path)
    elf=read_private_elf(elf_path)
    raw=read_private_claims(claim_path)
    if hashlib.md5(exe).hexdigest()!=PINNED_US_EXE_MD5:
        raise Refused("original US retail selector did not match")
    if len(compare_original_data_anchors(exe,elf))!=3:
        raise Refused("source-pinned original MIPS data anchors incomplete")
    result=correlate_pc_claims(exe,elf,parse_pc_claims(raw))
    if (read_private_exe(exe_path)!=exe or
            read_private_elf(elf_path)!=elf or
            read_private_claims(claim_path)!=raw):
        raise Refused("private original code or MMIO PC claims changed")
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_owned_us_psx_exe",type=Path)
    p.add_argument("private_extracted_mips_elf",type=Path)
    p.add_argument("private_mmio_pc_claims_jsonl",type=Path)
    args=p.parse_args()
    try:
        result=audit_private_pair_and_pc_claims(
            args.private_owned_us_psx_exe,
            args.private_extracted_mips_elf,args.private_mmio_pc_claims_jsonl)
    except (Refused,ValueError,OSError,struct.error):
        p.exit(2,"VH137_PRIVATE_MMIO_PC_CORRELATION_REFUSED\n")
    print(json.dumps(result,sort_keys=True,separators=(",",":")))


if __name__=="__main__":
    main()

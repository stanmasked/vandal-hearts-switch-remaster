#!/usr/bin/env python3
"""Local-only source binding of *claimed* original MIPS MMIO execution tuples.

This checks byte-identical original EXE/ELF executable instructions against a
private bounded claimed trace of (sequence, PC, instruction word, effective
MMIO address, stored value). The trace's producer is NOT authenticated.
Matching static code is not proof of execution, MAP02, PS1 or Switch parity.

Never print a PC, MIPS word, MMIO address, stored value, filename or hash.
Public CI must use ONLY source-generated synthetic PS-X and MIPS ELF images.
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
    MMIO,NAME_ORDER,Refused,_canonical_mmio,_open_private_exe_dirfd,
    _snapshot,_read_exact,read_private_exe,
)
from .analyze_map02_v135_original_us_elf_pair import (
    PINNED_US_EXE_MD5,compare_original_data_anchors,read_private_elf,
)
from .analyze_map02_v136_original_code_sections import (
    _elf_exec_sections,original_code_sections,
)
from .verify_map02_v137_private_mips_pc_sites import (
    source_bound_pc_sites,_unique_object,
)

SCHEMA="vh.map02.private-source-exact-mmio-claims.v1"
EVENT_SCHEMA="vh.map02.private-exact-mmio-claim.v1"
MAX_TRACE_BYTES=524288
MAX_TRACE_EVENTS=4096
U32=0xffffffff


def read_private_exact_mmio_trace(path):
    """Descriptor-bound 0600 regular private JSONL: same inode, two reads."""
    fd=_open_private_exe_dirfd(path)
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid()
                or st.st_nlink!=1 or stat.S_IMODE(st.st_mode)!=0o600
                or not 1<=st.st_size<=MAX_TRACE_BYTES):
            raise Refused("private MMIO trace metadata or size refused")
        snap=_snapshot(st)
        first=_read_exact(fd,st.st_size)
        if _snapshot(os.fstat(fd))!=snap:
            raise Refused("private MMIO trace metadata changed")
        os.lseek(fd,0,os.SEEK_SET)
        second=_read_exact(fd,st.st_size)
        if (first!=second or _snapshot(os.fstat(fd))!=snap):
            raise Refused("private MMIO trace changed during protected read")
        return first
    except OSError:
        raise Refused("private MMIO trace safely inaccessible") from None
    finally:
        os.close(fd)


def parse_exact_mmio_trace(raw):
    """Canonical numeric-only JSONL with strictly contiguous event sequence."""
    if (type(raw) is not bytes or not 1<=len(raw)<=MAX_TRACE_BYTES
            or not raw.endswith(b"\n") or b"\r" in raw):
        raise Refused("invalid private exact MMIO trace format")
    lines=raw.split(b"\n")[:-1]
    if not 1<=len(lines)<=MAX_TRACE_EVENTS:
        raise Refused("private exact MMIO trace size invalid")
    events=[]
    keys={"schema","seq","pc","word","address","value"}
    for sequence,line in enumerate(lines):
        try:
            event=json.loads(line,object_pairs_hook=_unique_object)
        except (UnicodeError,ValueError,TypeError):
            raise Refused("invalid private exact MMIO trace record") from None
        if (type(event) is not dict or set(event)!=keys
                or event["schema"]!=EVENT_SCHEMA
                or any(type(event[k]) is not int or not 0<=event[k]<=U32
                       for k in ("seq","pc","word","address","value"))
                or event["seq"]!=sequence
                or json.dumps(event,sort_keys=True,
                              separators=(",",":")).encode()!=line):
            raise Refused("noncanonical or out-of-order MMIO observation")
        events.append((event["pc"],event["word"],
                       event["address"],event["value"]))
    return events


def verify_source_bound_exact_mmio_claims(exe,elf,events):
    """Require every untrusted claim to be consistent with source MIPS bytes."""
    if (type(events) is not list or not 1<=len(events)<=MAX_TRACE_EVENTS):
        raise Refused("invalid exact MMIO claim series")
    sites,static_counts=source_bound_pc_sites(exe,elf)
    sections=_elf_exec_sections(elf)
    code=original_code_sections(exe,elf)
    if len(sections)!=len(code):
        raise Refused("source-aligned original MIPS section count changed")
    pc_words={}
    for (start,end,_),source in zip(sections,code):
        for pc in sites:
            if start<=pc<end:
                offset=pc-start
                if offset%4 or offset+4>len(source) or pc in pc_words:
                    raise Refused("original executable MIPS word lookup refused")
                pc_words[pc]=struct.unpack_from("<I",source,offset)[0]
    if len(pc_words)!=len(sites):
        raise Refused("original executable MIPS site lookup incomplete")
    counts={name:0 for name in NAME_ORDER}
    selected=set()
    linked_starts=0
    zero_register_stores=0
    aliases={0:0,0x80000000:0,0xa0000000:0}
    for record in events:
        if (type(record) is not tuple or len(record)!=4
                or any(type(v) is not int or not 0<=v<=U32
                       for v in record)):
            raise Refused("invalid private exact MMIO event")
        pc,word,address,value=record
        expected=sites.get(pc)
        physical=_canonical_mmio(address)
        if (expected is None or pc_words.get(pc)!=word
                or word>>26!=0x2b or physical is None
                or MMIO[physical]!=expected[0]):
            raise Refused("private MMIO event not bound to executable MIPS SW")
        # MIPS register $zero ALWAYS contains zero, independent of state.
        if ((word>>16)&31)==0:
            if value!=0:
                raise Refused("MIPS zero-register store claimed nonzero value")
            zero_register_stores+=1
        if expected[1]:
            if expected[0]!="dma2_chcr" or value!=0x01000401:
                raise Refused("statically proven DMA2 linked-list literal changed")
            linked_starts+=1
        counts[expected[0]]+=1
        aliases[address&0xe0000000]+=1
        selected.add(pc)
    return {
        "schema":SCHEMA,
        "scope":"private_us_exe_elf_source_matched_mmio_claims",
        "source_bound_candidate_events":len(events),
        "source_bound_distinct_mips_sw_sites":len(selected),
        "source_bound_total_static_sw_sites":len(sites),
        "claimed_mmio_register_class_counts":counts,
        "statically_bound_linked_list_start_claims":linked_starts,
        "zero_register_store_claims":zero_register_stores,
        "kuseg_address_claims":aliases[0],
        "kseg0_address_claims":aliases[0x80000000],
        "kseg1_address_claims":aliases[0xa0000000],
        "source_verified_static_mmio_site_counts":static_counts,
        "full_mips_instruction_word_compared":True,
        "effective_mmio_register_class_compared":True,
        "mmio_value_compared_to_full_cpu_state":False,
        "trace_producer_authenticated":False,
        "mips_execution_or_reachability_proven":False,
        "original_map02_loaded_or_rendered":False,
        "physical_ps1_parity_verified":False,
        "nintendo_switch_hd_parity_verified":False,
        "private_pcs_values_paths_or_hashes_exported":False,
    }


def audit_private_source_and_claimed_effects(exe_path,elf_path,trace_path):
    exe=read_private_exe(exe_path)
    elf=read_private_elf(elf_path)
    raw=read_private_exact_mmio_trace(trace_path)
    # Historical MD5 is only a pinned US edition SELECTOR, not modern
    # collision-resistant authentication or original gameplay attestation.
    if hashlib.md5(exe).hexdigest()!=PINNED_US_EXE_MD5:
        raise Refused("private PS-X EXE does not match original US selector")
    if len(compare_original_data_anchors(exe,elf))!=3:
        raise Refused("private original PS1 data anchors incomplete")
    result=verify_source_bound_exact_mmio_claims(
        exe,elf,parse_exact_mmio_trace(raw))
    if (read_private_exe(exe_path)!=exe or
            read_private_elf(elf_path)!=elf or
            read_private_exact_mmio_trace(trace_path)!=raw):
        raise Refused("private original inputs changed during MMIO correlation")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_owned_us_psx_exe",type=Path)
    parser.add_argument("private_original_extracted_mips_elf",type=Path)
    parser.add_argument("private_mmio_runtime_claims_jsonl",type=Path)
    args=parser.parse_args()
    try:
        report=audit_private_source_and_claimed_effects(
            args.private_owned_us_psx_exe,args.private_original_extracted_mips_elf,
            args.private_mmio_runtime_claims_jsonl)
    except (Refused,OSError,ValueError,TypeError,struct.error):
        parser.exit(2,"VH141_PRIVATE_EXACT_ORIGINAL_MMIO_REFUSED\n")
    print(json.dumps(report,sort_keys=True,separators=(",",":")))


if __name__=="__main__":
    main()

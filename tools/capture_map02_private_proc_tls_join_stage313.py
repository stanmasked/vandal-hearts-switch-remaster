#!/usr/bin/env python3
"""Stage313 private TID join of /proc task aliases and CPAL/ALSA TLS aliases.

Real TIDs are read only inside a temporary private NeXium/observer shared mmap.
They NEVER enter the sanitized CSV, logs, user-visible result, process argv,
environment or uploaded artifacts. The existing Stage302 collector supplies
independently anonymized per-run task aliases from /proc (tid, start-time).
Joining is scoped to the exact same live NeXium process and sample instant.
"""
import argparse
import csv
import mmap
import os
from pathlib import Path
import signal
import struct
import time

from capture_map02_linux_task_samples_stage302 import (
    MAX_SAMPLES,INTERVAL,collect)

MM_SIZE=65536
TLS_SLOTS=64
PRIVATE_TID_OFFSET=53760
CPAL_MARK_OFFSET=32768
ORIGINAL_HEADER=("sample","observed_ns","task_alias","name_hint",
                 "linux_state","cpu_ticks","wait_bucket")
JOINED_HEADER=("sample","observed_ns","anonymous_proc_task_alias",
               "anonymous_tls_alias","cpal_tag_cumulative")
class Halt(Exception):pass

def raw_alias_view(mm):
    require=struct.unpack_from("<8sQ",mm,0)
    if require[0]!=b"VH305AL1" or not 0<=require[1]<=TLS_SLOTS:
        raise ValueError("Private Stage313 mmap wrong schema or invalid TLS capacity")
    tid_to_tls={}
    tls_tag={}
    for alias in range(require[1]):
        tid=struct.unpack_from("<Q",mm,PRIVATE_TID_OFFSET+alias*8)[0]
        tag=struct.unpack_from("<Q",mm,CPAL_MARK_OFFSET+alias*8)[0]
        if tid:
            if tid in tid_to_tls:
                raise ValueError("Two TLS aliases claim the same live native TID")
            tid_to_tls[tid]=alias
            tls_tag[alias]=tag
    return tid_to_tls,tls_tag

def observe(pid,source,output,joined,ready,sample_limit=MAX_SAMPLES):
    paths=[source,output,joined,ready]
    if pid<=1 or not 4<=sample_limit<=MAX_SAMPLES:
        raise ValueError("Unsafe PID or monitoring interval")
    if any(not p.is_absolute() or p.is_symlink() for p in paths):
        raise ValueError("Required absolute private source and sanitized regular outputs")
    if len(set(paths))!=4 or ready.parent!=output.parent or joined.parent!=output.parent:
        raise ValueError("Distinct same-directory scoped observer paths required")
    output.parent.mkdir(parents=True,exist_ok=True)
    def stop(_s,_f):raise Halt()
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    aliases={}
    with source.open("rb") as private:
        if os.fstat(private.fileno()).st_size!=MM_SIZE:
            raise ValueError("Private Stage313 map must be 65536 bytes")
        with mmap.mmap(private.fileno(),MM_SIZE,access=mmap.ACCESS_READ) as memory, \
             output.open("w",encoding="ascii",newline="") as raw, \
             joined.open("w",encoding="ascii",newline="") as sanitized:
            raw_write=csv.writer(raw,lineterminator="\n")
            join_write=csv.writer(sanitized,lineterminator="\n")
            raw_write.writerow(ORIGINAL_HEADER);join_write.writerow(JOINED_HEADER)
            raw.flush();sanitized.flush()
            raw_alias_view(memory)
            ready.write_text(str(time.monotonic_ns())+"\n",encoding="ascii")
            try:
                for i in range(sample_limit):
                    now=time.monotonic_ns()
                    rows=collect(pid,aliases)
                    native_to_tls,marks=raw_alias_view(memory)
                    # Intermediate raw TID is NEVER serialized.
                    native_by_proc_alias={v:tid for (tid,_start),v in aliases.items()}
                    if not rows:
                        raw_write.writerow((i,now,0,"NO_TASKS","X",0,"UNKNOWN"))
                        raw.flush();sanitized.flush()
                        break
                    for proc_alias,hint,state,cpu,wait in rows:
                        tid=native_by_proc_alias[proc_alias]
                        tls_alias=native_to_tls.get(tid,-1)
                        raw_write.writerow((i,now,proc_alias,hint,state,cpu,wait))
                        join_write.writerow((i,now,proc_alias,tls_alias,
                                            marks.get(tls_alias,0)))
                    raw.flush();sanitized.flush()
                    time.sleep(INTERVAL)
            except Halt:pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pid",required=True,type=int)
    p.add_argument("--source-private",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--joined",required=True,type=Path)
    p.add_argument("--ready",required=True,type=Path)
    p.add_argument("--sample-limit",type=int,default=MAX_SAMPLES)
    a=p.parse_args()
    observe(a.pid,a.source_private,a.output,a.joined,a.ready,a.sample_limit)

if __name__=="__main__":main()

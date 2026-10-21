#!/usr/bin/env python3
"""Stage310 paired ALSA exported-call and actual tagged CPAL TLS source sampler.

Read-only process-external mmap sampling; no new callback operations.
Rows in two sanitized CSVs share the exact same monotonic snapshot marker.
Never serialize PIDs, TIDs, addresses, audio data, private mmap, or host paths.
"""
import argparse
import csv
import mmap
import os
from pathlib import Path
import signal
import struct
import time

from capture_map02_alsa_userspace_stage305 import (
    SIZE,SLOTS,MAGIC,KINDS,OPS,snapshot)

CPAL_MARKER_OFFSET=32768
PHASE_OFFSET=33792
PHASE_OPS=("avail_delay","prepare","recover","status","start","drop",
           "pause","writei","readi","wait","avail","avail_update","poll_descriptors")
PHASE_ROW_BYTES=3*8
PHASE_HEADER=("kind","monotonic_ns","anonymous_tls_alias","operation",
              "begun","returned","negative_returned")
MARKER_HEADER=("kind","monotonic_ns","anonymous_tls_alias",
               "cpal_callback_mark_entries")
ALSА_HEADER=("kind","monotonic_ns","anonymous_alias","operation",*KINDS)

class Halt(Exception):pass

def observe(source,alsa_csv,tag_csv,phase_csv,ready):
    paths=(source,alsa_csv,tag_csv,phase_csv,ready)
    if any(not p.is_absolute() or p.is_symlink() for p in paths):
        raise ValueError("Absolute private mmap and sanitized outputs required")
    if len(set(paths))!=len(paths):
        raise ValueError("Source/outputs must have distinct paths")
    with source.open("rb") as f:
        if os.fstat(f.fileno()).st_size!=SIZE:
            raise ValueError("Shared mmap storage not exactly source-pinned 65536")
        with mmap.mmap(f.fileno(),SIZE,access=mmap.ACCESS_READ) as mm:
            def stop(_s,_f):raise Halt()
            signal.signal(signal.SIGTERM,stop)
            signal.signal(signal.SIGINT,stop)
            with alsa_csv.open("w",encoding="ascii",newline="") as a, \
                 tag_csv.open("w",encoding="ascii",newline="") as t, \
                 phase_csv.open("w",encoding="ascii",newline="") as ph:
                aw=csv.writer(a,lineterminator="\n")
                tw=csv.writer(t,lineterminator="\n")
                pw=csv.writer(ph,lineterminator="\n")
                aw.writerow(ALSА_HEADER);tw.writerow(MARKER_HEADER)
                pw.writerow(PHASE_HEADER)
                a.flush();t.flush();ph.flush()
                ready.write_text(str(time.monotonic_ns())+"\n",encoding="ascii")
                try:
                    for _ in range(260):
                        now=time.monotonic_ns()
                        count,rows=snapshot(mm)
                        marks=[struct.unpack_from("<Q",mm,CPAL_MARKER_OFFSET+8*i)[0]
                               for i in range(min(count,SLOTS))]
                        aw.writerow(("P",now,-1,"sample",count,0,0,0,0,0))
                        for alias,op,*values in rows:
                            aw.writerow(("S",now,alias,op,*values))
                        tw.writerow(("P",now,-1,count))
                        pw.writerow(("P",now,-1,"sample",count,0,0))
                        for alias,number in enumerate(marks):
                            if number:
                                tw.writerow(("C",now,alias,number))
                        for alias in range(min(count,SLOTS)):
                            for opidx,op in enumerate(PHASE_OPS):
                                where=PHASE_OFFSET+(alias*len(PHASE_OPS)+opidx)*PHASE_ROW_BYTES
                                begun,returned,negative=struct.unpack_from("<QQQ",mm,where)
                                if begun or returned or negative:
                                    pw.writerow(("B",now,alias,op,begun,returned,negative))
                        a.flush();t.flush();ph.flush()
                        time.sleep(0.2)
                except Halt:
                    pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--alsa",type=Path,required=True)
    p.add_argument("--tag",type=Path,required=True)
    p.add_argument("--phase",type=Path,required=True)
    p.add_argument("--ready",type=Path,required=True)
    a=p.parse_args()
    observe(a.source,a.alsa,a.tag,a.phase,a.ready)

if __name__=="__main__":main()

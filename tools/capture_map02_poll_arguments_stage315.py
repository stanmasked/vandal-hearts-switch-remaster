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
LIBC_WAIT_OFFSET=54784
POLL_META_OFFSET=60928
POLL_META_FIELDS=("last_timeout_plus_one","last_nfds_capped",
                  "timeout_infinite_entries","timeout_immediate_entries",
                  "timeout_finite_entries","returned_ready","returned_zero",
                  "returned_negative","timeout_invalid_negative_entries")
POLL_META_HEADER=("kind","monotonic_ns","anonymous_tls_alias",*POLL_META_FIELDS)
LIBC_WAIT_NAMES=("poll","ppoll","epoll_wait","epoll_pwait")
LIBC_WAIT_HEADER=("kind","monotonic_ns","anonymous_tls_alias","function","entered","returned","negative_returned")
PHASE_HEADER=("kind","monotonic_ns","anonymous_tls_alias","operation",
              "begun","returned","negative_returned")
MARKER_HEADER=("kind","monotonic_ns","anonymous_tls_alias",
               "cpal_callback_mark_entries")
ALSА_HEADER=("kind","monotonic_ns","anonymous_alias","operation",*KINDS)

class Halt(Exception):pass

def observe(source,alsa_csv,tag_csv,phase_csv,libc_csv,meta_csv,ready):
    paths=(source,alsa_csv,tag_csv,phase_csv,libc_csv,meta_csv,ready)
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
                 phase_csv.open("w",encoding="ascii",newline="") as ph, \
                 libc_csv.open("w",encoding="ascii",newline="") as lc, \
                 meta_csv.open("w",encoding="ascii",newline="") as pm:
                aw=csv.writer(a,lineterminator="\n")
                tw=csv.writer(t,lineterminator="\n")
                pw=csv.writer(ph,lineterminator="\n")
                lw=csv.writer(lc,lineterminator="\n")
                mw=csv.writer(pm,lineterminator="\n")
                aw.writerow(ALSА_HEADER);tw.writerow(MARKER_HEADER)
                pw.writerow(PHASE_HEADER)
                lw.writerow(LIBC_WAIT_HEADER)
                mw.writerow(POLL_META_HEADER)
                a.flush();t.flush();ph.flush();lc.flush();pm.flush()
                ready.write_text(str(time.monotonic_ns())+"\n",encoding="ascii")
                try:
                    for _ in range(260):
                        now=time.monotonic_ns()
                        # Original Stage305 userspace counters are individual
                        # relaxed atomics, not an atomic group snapshot. If a
                        # wrapper increments total before its return category,
                        # one read can observe impossible intermediate sums.
                        # The reader retries genuine shared mmap values; it
                        # does NOT synthesize, clamp or patch counters.
                        for attempt in range(32):
                            try:
                                count,rows=snapshot(mm)
                                break
                            except ValueError as ex:
                                if "Counter categories exceed call count" not in str(ex):
                                    raise
                                if attempt==31:
                                    raise
                                time.sleep(0.001)
                        marks=[struct.unpack_from("<Q",mm,CPAL_MARKER_OFFSET+8*i)[0]
                               for i in range(min(count,SLOTS))]
                        aw.writerow(("P",now,-1,"sample",count,0,0,0,0,0))
                        for alias,op,*values in rows:
                            aw.writerow(("S",now,alias,op,*values))
                        tw.writerow(("P",now,-1,count))
                        pw.writerow(("P",now,-1,"sample",count,0,0))
                        lw.writerow(("P",now,-1,"sample",count,0,0))
                        mw.writerow(("P",now,-1,count,*([0]*(len(POLL_META_FIELDS)-1))))
                        for alias,number in enumerate(marks):
                            if number:
                                tw.writerow(("C",now,alias,number))
                        for alias in range(min(count,SLOTS)):
                            for opidx,op in enumerate(PHASE_OPS):
                                where=PHASE_OFFSET+(alias*len(PHASE_OPS)+opidx)*PHASE_ROW_BYTES
                                begun,returned,negative=struct.unpack_from("<QQQ",mm,where)
                                if begun or returned or negative:
                                    pw.writerow(("B",now,alias,op,begun,returned,negative))
                        for alias in range(min(count,SLOTS)):
                            for opidx,op in enumerate(LIBC_WAIT_NAMES):
                                loc=LIBC_WAIT_OFFSET+(alias*len(LIBC_WAIT_NAMES)+opidx)*PHASE_ROW_BYTES
                                entered,returned,negative=struct.unpack_from("<QQQ",mm,loc)
                                if entered or returned or negative:
                                    lw.writerow(("B",now,alias,op,entered,returned,negative))
                        for alias in range(min(count,SLOTS)):
                            position=POLL_META_OFFSET+(alias*len(POLL_META_FIELDS))*8
                            values=struct.unpack_from("<"+"Q"*len(POLL_META_FIELDS),
                                                      mm,position)
                            if any(values):
                                mw.writerow(("M",now,alias,*values))
                        a.flush();t.flush();ph.flush();lc.flush();pm.flush()
                        time.sleep(0.2)
                except Halt:
                    pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--alsa",type=Path,required=True)
    p.add_argument("--tag",type=Path,required=True)
    p.add_argument("--phase",type=Path,required=True)
    p.add_argument("--libc",type=Path,required=True)
    p.add_argument("--meta",type=Path,required=True)
    p.add_argument("--ready",type=Path,required=True)
    a=p.parse_args()
    observe(a.source,a.alsa,a.tag,a.phase,a.libc,a.meta,a.ready)

if __name__=="__main__":main()

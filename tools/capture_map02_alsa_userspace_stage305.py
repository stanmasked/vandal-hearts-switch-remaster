#!/usr/bin/env python3
"""Stage305 private mmap counter creator and NON-callback timestamp observer.

The shim records no samples, paths, identities, Linux PIDs/TIDs or filenames.
S rows describe ephemeral anonymous TLS aliases, not proven CPAL threads.
Only the sanitized CSV is eligible for artifact upload; raw mmap stays private.
"""
import argparse
import csv
import mmap
import os
from pathlib import Path
import signal
import struct
import time

MAGIC=b"VH305AL1"
SIZE=65536
SLOTS=64
OPS=("avail_delay","prepare","recover","status","start","drop",
     "pause","writei","readi")
KINDS=("total","success","eio","epipe","eagain","other_negative")
ROW_BYTES=8*len(KINDS)
BASE=16

def initialize(path):
    path=Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("Private absolute shared memory file required")
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        os.ftruncate(fd,SIZE)
        os.write(fd,MAGIC)
    finally:
        os.close(fd)

def snapshot(m):
    if m[:8]!=MAGIC:
        raise ValueError("Source mmap magic mismatch")
    slots_used=struct.unpack_from("<Q",m,8)[0]
    if slots_used>100000:
        raise ValueError("Counter slots header corrupted")
    result=[]
    for slot in range(min(slots_used,SLOTS)):
        for op in range(len(OPS)):
            vals=struct.unpack_from("<"+"Q"*len(KINDS),
                      m,BASE+((slot*len(OPS)+op)*ROW_BYTES))
            if vals[0]:
                if sum(vals[1:])>vals[0]:
                    raise ValueError("Counter categories exceed call count")
                result.append((slot,OPS[op],*vals))
    return slots_used,result

class Halt(Exception):
    pass

def observe(source,out,ready):
    for path in (source,out,ready):
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("Source and output must be non-symlink absolute paths")
    with source.open("rb") as f:
        if f.stat().st_size!=SIZE:
            raise ValueError("Shared mmap file changed size")
        with mmap.mmap(f.fileno(),SIZE,access=mmap.ACCESS_READ) as mm:
            def stop(_sig,_frame): raise Halt()
            signal.signal(signal.SIGTERM,stop)
            signal.signal(signal.SIGINT,stop)
            with out.open("w",encoding="ascii",newline="") as stream:
                writer=csv.writer(stream,lineterminator="\n")
                writer.writerow(("kind","monotonic_ns","anonymous_alias","operation",
                                 *KINDS))
                stream.flush()
                ready.write_text(str(time.monotonic_ns())+"\n",encoding="ascii")
                try:
                    for tick in range(260):
                        when=time.monotonic_ns()
                        n,rows=snapshot(mm)
                        writer.writerow(("P",when,-1,"sample",n,0,0,0,0,0))
                        for row in rows:
                            alias,op,*values=row
                            writer.writerow(("S",when,alias,op,*values))
                        stream.flush()
                        time.sleep(0.2)
                except Halt:
                    pass

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",required=True,type=Path)
    ap.add_argument("--init",action="store_true")
    ap.add_argument("--output",type=Path)
    ap.add_argument("--ready",type=Path)
    a=ap.parse_args()
    if a.init:
        initialize(a.source)
    else:
        if a.output is None or a.ready is None:
            ap.error("--output and --ready required for sampling")
        observe(a.source,a.output,a.ready)
if __name__=="__main__":main()

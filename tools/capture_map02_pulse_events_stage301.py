#!/usr/bin/env python3
"""Stage301 opt-in Pulse subscribe receipt clock (not a Pulse event clock).

Only sanitize sink-input new/remove/change IDs. Timestamp is when the
subscriber READS the notification via pipe, not when Pulse generated it.
No game code, CPAL callback or upstream host modification.
"""
import argparse
import csv
import os
from pathlib import Path
import re
import signal
import subprocess
import time

EVENT=re.compile(r"^Event '([a-z]+)' on sink-input #(\d+)\s*$")
TYPES={"new","remove","change"}
MAX_EVENTS=20_000

def sanitize(line):
    m=EVENT.fullmatch(line.strip())
    if m and m[1] in TYPES:
        value=int(m[2])
        if value<=2**32-1:
            return m[1],value
    return None

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--output",type=Path,required=True)
    a.add_argument("--ready",type=Path,required=True)
    args=a.parse_args()
    out,ready=args.output,args.ready
    if not out.is_absolute() or not ready.is_absolute():
        raise SystemExit("Stage301 output and ready markers must be absolute")
    if out.parent!=ready.parent or out.is_symlink() or ready.is_symlink():
        raise SystemExit("Stage301 source paths invalid")
    out.parent.mkdir(parents=True,exist_ok=True)
    count=0
    class MonitorStopped(Exception):
        pass
    def stop(_signal,_frame):
        raise MonitorStopped()
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    child=None
    with out.open("w",encoding="ascii",newline="") as handle:
        writer=csv.writer(handle,lineterminator="\n")
        def stamp(kind,identifier):
            writer.writerow((kind,time.monotonic_ns(),identifier))
            handle.flush()
        try:
            child=subprocess.Popen(["pactl","subscribe"],stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL,text=True,
                                   encoding="utf8",bufsize=1)
            stamp("S","monitor_started")
            ready.write_text(str(time.monotonic_ns())+"\n",encoding="ascii")
            for line in child.stdout:
                event=sanitize(line)
                if event:
                    kind,identifier=event
                    stamp(kind,identifier)
                    count+=1
                    if count>=MAX_EVENTS:
                        stamp("S","event_limit_reached")
                        break
        except MonitorStopped:
            pass
        finally:
            stamp("S","monitor_stopped")
            if child is not None:
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    return 0

if __name__=="__main__":
    raise SystemExit(main())

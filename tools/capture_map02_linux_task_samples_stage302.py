#!/usr/bin/env python3
"""Stage302 read-only /proc task sampler for actual NeXium guest process.

Samples Linux task state, cumulative user/system CPU ticks and bounded *bucketed*
wait channels. Emits per-run sequential anonymous task aliases (NOT real TIDs,
command lines, filenames, process PIDs or environment variables). Thread name is
never emitted, and AUDIO_NAMED means a name substring only, not proven CPAL owner.
No ptrace, LD_PRELOAD, realtime callback hook, privileged access or game changes.
"""
import argparse
import csv
import os
from pathlib import Path
import signal
import time

MAX_SAMPLES=220
INTERVAL=0.25
BUCKETS=("futex","ep_poll","poll","hrtimer","schedule","io_schedule",
         "wait_woken","pipe_read","sock_recv")
STATES="RSDTtZXI"

class Stopped(Exception):
    pass

def parsed_stat(value):
    """Linux /proc/<pid>/task/<tid>/stat has a parenthesized comm field."""
    right=value.rfind(")")
    if right<2 or not value[:value.find("(")].strip().isdigit():
        raise ValueError("Malformed proc task stat PID")
    cols=value[right+1:].split()
    if len(cols)<20:
        raise ValueError("Missing proc task stat fields")
    state=cols[0]
    if state not in STATES:
        raise ValueError("Unknown Linux task state")
    utime=int(cols[11]);stime=int(cols[12]);starttime=int(cols[19])
    if min(utime,stime,starttime)<0:
        raise ValueError("Negative process time")
    return state,utime+stime,starttime

def bucket(wchan):
    value=wchan.strip().lower()
    if not value or value=="0":
        return "UNKNOWN"
    for term in BUCKETS:
        if term in value:
            return term
    return "OTHER"

def audio_hint(comm):
    value=comm.strip().lower()
    return "AUDIO_NAMED" if any(x in value for x in ("alsa","cpal","audio")) else "UNATTRIBUTED"

def collect(pid,aliases):
    root=Path("/proc")/str(pid)/"task"
    output=[]
    try:
        names=sorted((p for p in root.iterdir() if p.name.isdigit()),
                     key=lambda x:int(x.name))
    except OSError:
        return []
    for task in names:
        try:
            state,cpu_ticks,start=parsed_stat((task/"stat").read_text())
            comm=(task/"comm").read_text(encoding="utf-8",errors="replace")
            wchan=(task/"wchan").read_text(encoding="ascii",errors="replace")
        except (OSError,ValueError,UnicodeError):
            # Task exited during the read. Never infer an absent Linux thread.
            continue
        key=(int(task.name),start)
        if key not in aliases:
            aliases[key]=len(aliases)+1
        output.append((aliases[key],audio_hint(comm),state,cpu_ticks,bucket(wchan)))
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pid",required=True,type=int)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--ready",required=True,type=Path)
    p.add_argument("--sample-limit",type=int,default=MAX_SAMPLES)
    a=p.parse_args()
    if a.pid<=1 or not 4<=a.sample_limit<=MAX_SAMPLES:
        raise SystemExit("Invalid bounded monitor parameters")
    if not a.output.is_absolute() or a.ready.parent!=a.output.parent or not a.ready.is_absolute():
        raise SystemExit("Expected bounded absolute output and marker paths")
    if a.output.is_symlink() or a.ready.is_symlink():
        raise SystemExit("Refuse symlinked monitor paths")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    def stop(_sig,_frame):raise Stopped()
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    aliases={}
    with a.output.open("w",encoding="ascii",newline="") as f:
        writer=csv.writer(f,lineterminator="\n")
        writer.writerow(("sample","observed_ns","task_alias","name_hint",
                         "linux_state","cpu_ticks","wait_bucket"))
        f.flush()
        a.ready.write_text(str(time.monotonic_ns())+"\n",encoding="ascii")
        try:
            for sample in range(a.sample_limit):
                stamp=time.monotonic_ns()
                tasks=collect(a.pid,aliases)
                if not tasks:
                    # Preserve last observer sample without claiming the cause.
                    writer.writerow((sample,stamp,0,"NO_TASKS","X",0,"UNKNOWN"))
                    f.flush()
                    break
                for alias,hint,state,ticks,wait in tasks:
                    writer.writerow((sample,stamp,alias,hint,state,ticks,wait))
                f.flush()
                time.sleep(INTERVAL)
        except Stopped:
            pass
    return 0

if __name__=="__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage304 non-invasive userspace ALSA probe preparation.

Resolve installed libasound public symbols from the actual Linux runner and
record whether uprobe/perf tracing can be enabled. Do not falsely equate
strace's kernel ioctls with userspace ALSA APIs. This is a *capability probe*,
not evidence that any particular snd_pcm function was called.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SCHEMA="vh-map02-stage304-alsa-public-symbol-preflight/v1"
SYMBOLS=("snd_pcm_avail_delay","snd_pcm_writei","snd_pcm_readi",
         "snd_pcm_prepare","snd_pcm_recover","snd_pcm_start",
         "snd_pcm_drop","snd_pcm_pause","snd_pcm_status")
def checked_output(argv):
    return subprocess.run(argv,text=True,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,check=True,timeout=12).stdout

def inspect(path):
    p=Path(path).resolve(strict=True)
    if not p.is_file() or p.is_symlink() or not p.name.startswith("libasound.so"):
        raise ValueError("Not a real libasound shared object")
    if not str(p).startswith(("/usr/lib/","/lib/")):
        raise ValueError("Unexpected library root")
    raw=p.read_bytes()
    if raw[:4]!=b"\x7fELF" or len(raw)>30_000_000:
        raise ValueError("Invalid bounded ELF library")
    dyn=checked_output(["nm","-D","--defined-only",str(p)])
    present={}
    for name in SYMBOLS:
        matches=[line for line in dyn.splitlines()
                 if re.search(r"\b"+re.escape(name)+r"(?:@@?\S+)?$",line)]
        present[name]=len(matches)>0
    if not any(present.values()):
        raise ValueError("No actual expected ALSA PCM public exports")
    return {"library_filename":p.name,"library_elf_sha256":hashlib.sha256(raw).hexdigest(),
            "public_symbol_exports":present}

def run(output):
    # Read-only probing; no ptrace and no instrumentation of guest code.
    lib=checked_output(["ldconfig","-p"])
    paths=re.findall(r"libasound\.so\.2 \([^\n]*\) => (/\S+)",lib)
    if not paths: raise ValueError("libasound.so.2 not registered")
    original=Path(paths[0])
    library=inspect(original)
    try:
        paranoid=int(Path("/proc/sys/kernel/perf_event_paranoid").read_text().strip())
    except (OSError,ValueError):
        paranoid=None
    tracing_path=Path("/sys/kernel/tracing/uprobe_events")
    try:
        usable=tracing_path.exists() and os.access(tracing_path,os.W_OK)
    except PermissionError:
        # An unprivileged Actions runner may not even stat tracefs.
        usable=False
    result={"schema":SCHEMA,
            "result":"REAL_RUNNER_ALSA_SYMBOL_EXPORTS_SOURCE_VERIFIED",
            "libasound":library,
            "perf_event_paranoid":paranoid,
            "uprobe_events_write_access":usable,
            "actual_snd_pcm_invocations_observed":False,
            "actual_alsa_error_return_values_observed":False,
            "guest_or_production_audio_fixed":False,
            "sensitive_host_paths_or_raw_kernel_addresses_exported":False}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try:
        result=run(args.output)
    except (ValueError,FileNotFoundError,subprocess.CalledProcessError,
            subprocess.TimeoutExpired,OSError) as err:
        result={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(err),
                "actual_snd_pcm_invocations_observed":False}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(json.dumps(result,sort_keys=True))
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())

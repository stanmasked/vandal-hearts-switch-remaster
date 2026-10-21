#!/usr/bin/env python3
"""Stage303 bounded strace analysis without uploading process IDs or arguments.

Strace -f follows a child emulator process but traces only selected ioctl,
polling and socket IPC syscalls, which may alter its scheduling. Raw trace
is private to the CI runner, not uploaded. strace -ttt times use CLOCK_REALTIME,
while NeXium P/L/guest markers are monotonic: bridge via two independently
bracketed realtime/monotonic pairs. This is an approximate ordering, NOT an
exact CPAL callback or kernel ALSA timestamp.
"""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

from audit_map02_pulse_event_clocks_stage301 import audit as audit_stage301

SCHEMA="vh-map02-stage303-real-strace-sanitized-alsa-syscall-audit/v1"
HOST_SHA="fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a"
NRO_SHA="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
ALLOWED={"ioctl","poll","ppoll","epoll_wait","epoll_pwait","sendmsg","recvmsg"}
TRACE_RE=re.compile(r"^(?:\\[pid +\\d+\\] +)?(\\d{10}\\.\\d{6,9}) +"
                    r"(ioctl|poll|ppoll|epoll_wait|epoll_pwait|sendmsg|recvmsg)\\(")
ERR_RE=re.compile(r"= -1 ([A-Z][A-Z0-9_]+)(?: |$)")
PCM_RE=re.compile(r"\\bSNDRV_PCM_IOCTL_[A-Z0-9_]+")
MAX_BYTES=90_000_000
MAX_LINES=1_000_000
# 1 second of tolerance on event alignment; strace and clock bridge are
# perturbed by tracing and independent processes.
WINDOW_TOLERANCE_NS=1_000_000_000

def require(ok,reason):
    if not ok:raise ValueError(reason)

def clockbridge(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),"Clock bridge file missing")
    payload=json.loads(path.read_text())
    require(set(payload)=={"wall_before_ns","monotonic_ns","wall_after_ns"},
            "Clock bridge schema unexpected")
    a,b,c=(payload[k] for k in
           ("wall_before_ns","monotonic_ns","wall_after_ns"))
    require(all(type(v) is int and 0<v<2**64 for v in (a,b,c))
            and a<=c and c-a<50_000_000,
            "Wall/monotonic sampling uncertainty excessive")
    return {
        "offset_low_ns":a-b,"offset_high_ns":c-b,
        "paired_wall_uncertainty_ns":c-a,
        "pair_monotonic_ns":b,
    }

def parse_raw_strace(rawpath,old_clock,new_clock,first_input_ns,last_marker_ns):
    path=Path(rawpath)
    require(path.is_file() and not path.is_symlink(),"Private raw strace file missing")
    size=path.stat().st_size
    require(100<size<=MAX_BYTES,"Raw strace missing or size limit exceeded")
    with path.open("r",encoding="ascii",errors="replace") as f:
        counts=Counter()
        error_codes=Counter()
        categories=Counter()
        classified=Counter()
        total=0
        prev_clock=None
        first_clock=None
        last_clock=None
        omitted=0
        for line in f:
            total+=1
            require(total<=MAX_LINES,"Trace exceeds bounded source line maximum")
            m=TRACE_RE.match(line)
            if not m:
                omitted+=1
                continue
            clock,syscall=m.groups()
            try:
                wall_ns=int(Decimal(clock)*Decimal(1_000_000_000))
            except InvalidOperation as e:
                raise ValueError("Invalid strace realtime stamp") from e
            if prev_clock is not None:
                require(wall_ns>=prev_clock-2_000_000_000,
                        "Strace realtime timestamp regressed > 2 seconds")
            prev_clock=wall_ns
            first_clock=wall_ns if first_clock is None else min(first_clock,wall_ns)
            last_clock=wall_ns if last_clock is None else max(last_clock,wall_ns)
            counts[syscall]+=1
            request=bool(PCM_RE.search(line)) if syscall=="ioctl" else False
            if request:
                categories["recognized_kernel_alsa_pcm_ioctl"]+=1
            err=ERR_RE.search(line)
            if err and err.group(1) in ("EIO","EPIPE","EAGAIN","ETIMEDOUT",
                                        "ENODEV","EBADF","EINTR","EINVAL"):
                error_codes[err.group(1)]+=1
                if request:
                    categories["recognized_kernel_alsa_pcm_ioctl_error"]+=1
            # Approximate realtime -> monotonic ordering, only if event is
            # outside one full second around a guest marker.
            offset=(old_clock["offset_low_ns"]+
                    old_clock["offset_high_ns"]+
                    new_clock["offset_low_ns"]+
                    new_clock["offset_high_ns"])//4
            mid=wall_ns-offset
            if mid<first_input_ns-WINDOW_TOLERANCE_NS:
                label="CLEARLY_BEFORE_GUEST_INPUT"
            elif first_input_ns+WINDOW_TOLERANCE_NS<=mid<=last_marker_ns-WINDOW_TOLERANCE_NS:
                label="WELL_INSIDE_GUEST_WINDOW"
            elif mid>last_marker_ns+WINDOW_TOLERANCE_NS:
                label="CLEARLY_AFTER_GUEST_WINDOW"
            else:
                label="NEAR_MARKER_OR_UNCERTAIN"
            classified[f"{syscall}:{label}"]+=1
        require(sum(counts.values())>=10 and first_clock is not None,
                "No useful actual selected syscalls were traced")
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "raw_trace_sha256":digest,
        "raw_trace_size_bytes":size,
        "raw_trace_is_uploaded":False,
        "original_trace_lines":total,
        "raw_trace_unparsed_lines":omitted,
        "selected_syscall_counts":dict(sorted(counts.items())),
        "selected_error_code_counts":dict(sorted(error_codes.items())),
        "audio_kernel_ioctl_categories":dict(sorted(categories.items())),
        "approximate_guest_window_syscall_counts":dict(sorted(classified.items())),
        "first_selected_syscall_wall_ns":first_clock,
        "last_selected_syscall_wall_ns":last_clock,
    }

def audit(evidence,raw_trace,hint,run_id):
    root=Path(evidence)
    prior=audit_stage301(root,hint,run_id)
    require(prior["result"]=="REAL_STAGE301_GUEST_CPAL_PULSE_RECEIPT_CLOCKS_REPARSED"
            and prior["exact_compiled_neXium_elf_sha256"]==HOST_SHA
            and prior["exact_generated_research_nro_sha256"]==NRO_SHA,
            "Stage303 original ELF/NRO/guest CPAL trace provenance mismatch")
    saved=json.loads((root/"stage301-pulse-subscribe-verified.json").read_text())
    require(saved==prior,"Independent Stage301 source truth was not rechecked")
    old_clock=clockbridge(root/"strace-clock-before.json")
    new_clock=clockbridge(root/"strace-clock-after.json")
    clock_shift=abs(
        (old_clock["offset_low_ns"]+old_clock["offset_high_ns"])//2-
        (new_clock["offset_low_ns"]+new_clock["offset_high_ns"])//2)
    require(clock_shift<200_000_000,
            "Real-time to monotonic clock offset drifted too far")
    require(old_clock["pair_monotonic_ns"]<
            prior["guest_first_input_monotonic_ns"]<
            prior["guest_last_observation_monotonic_ns"]<
            new_clock["pair_monotonic_ns"],
            "Clock bridges did not bound actual NeXium guest")
    trace=parse_raw_strace(raw_trace,old_clock,new_clock,
                           prior["guest_first_input_monotonic_ns"],
                           prior["guest_last_observation_monotonic_ns"])
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE303_PINNED_GUEST_SELECTED_LINUX_SYSCALLS_REPARSED",
        "requested_pulse_hint_ms":hint,
        "real_actions_run_id":run_id,
        "exact_stage298_host_elf_sha256":HOST_SHA,
        "unchanged_generated_rom_free_nro_sha256":NRO_SHA,
        "source_guest_cpal_post_input_entries":
            prior["host_guest_window_cpal_callback_entries"],
        "source_guest_8_page_optical_crc":
            prior["guest_final_8_page_crc_verified"],
        "source_virtual_pcm_nonzero_samples":prior["virtual_pcm_nonzero_samples"],
        "stage301_original_audit_sha256":hashlib.sha256(
            (root/"stage301-pulse-subscribe-verified.json").read_bytes()).hexdigest(),
        "first_clock_sample_bounds_ns":[old_clock["offset_low_ns"],
                                        old_clock["offset_high_ns"]],
        "final_clock_sample_bounds_ns":[new_clock["offset_low_ns"],
                                        new_clock["offset_high_ns"]],
        "clock_offset_drift_bound_ns":clock_shift,
        **trace,
        "trace_tool_child_ptrace_changes_guest_scheduling":True,
        "unix_syscall_ioctl_is_not_equivalent_to_alsa_library_function_call":True,
        "no_recognized_SNDRV_ioctl_does_not_prove_no_ALSA_work":True,
        "strace_clock_is_realtime_not_host_guest_monotonic":True,
        "bounded_classification_not_exact_guest_or_backend_event_clock":True,
        "no_original_ps1_soundtrack_or_game_ROM_used":True,
        "no_permanent_guest_deadlock_or_physical_switch_dac_proven":True,
        "no_ALSA_root_cause_or_production_audio_fix_proven":True,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--raw-trace",type=Path,required=True)
    p.add_argument("--hint",type=int,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        result=audit(a.evidence,a.raw_trace,a.hint,a.run_id)
        code=0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,
            json.JSONDecodeError) as e:
        result={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
                "no_ALSA_root_cause_or_production_audio_fix_proven":True}
        code=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return code

if __name__=="__main__":
    raise SystemExit(main())

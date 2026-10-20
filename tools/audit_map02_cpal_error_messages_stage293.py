#!/usr/bin/env python3
"""Stage293: compare source-authenticated 21/22-ms host CPAL log *messages*.

Input: original unmodified Stage290 and corrected Stage291 guest artifacts.
The live CPAL L-counters are independently re-parsed by the Stage292 auditor.
Host stdout has NO proven mapping from each line to monotonic guest-input time.
A textual CPAL warning alone is not a root-cause diagnosis.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from audit_map02_cpal_lifecycle_paired_21_22 import (
    check_trial, compare, HOST_SHA, NRO_SHA, RUNS, require,
)

SCHEMA="vh-map02-stage293-real-cpal-error-log-inventory/v1"
LIMIT_BYTES=16*1024*1024
MAX_LINES=200_000
CPAL_PATTERN=re.compile(r"cpal stream error:\s*(.+)", re.IGNORECASE)
OTHER_AUDIO_PATTERN=re.compile(
    r"(Audio output disabled:|stream\.play:|build_output_stream|"
    r"cpal.*(warn|error))",re.IGNORECASE,
)
ANSI_PATTERN=re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
PATH_PATTERN=re.compile(r"(?<!\w)/(?:[-.\w]+/){1,}[-.\w]+")
HEX_PATTERN=re.compile(r"0x[0-9a-fA-F]+")
NUMBER_PATTERN=re.compile(r"\b\d+\b")


def normalize_reason(raw):
    """Log exemplars are sanitized; preserve meaning, not arbitrary host paths."""
    text=ANSI_PATTERN.sub("",raw.strip())
    text=PATH_PATTERN.sub("<path>",text)
    text=HEX_PATTERN.sub("<address>",text)
    text=NUMBER_PATTERN.sub("#",text)
    return " ".join(text.split())[:240]


def descriptive_tags(reason):
    """Nonexclusive lexical descriptors ONLY; never inferred causal categories."""
    t=reason.lower()
    tags=[]
    for label,words in (
        ("xrun_or_underrun_token",("xrun","underrun","overrun")),
        ("alsa_token",("alsa","snd_pcm","pcm_")),
        ("device_token",("device","disconnected","unavailable")),
        ("backend_token",("backend","backend-specific","backendspecific")),
        ("buffer_token",("buffer","frame")),
        ("timeout_token",("timeout","timed out")),
    ):
        if any(w in t for w in words): tags.append(label)
    return tags or ["no_predefined_keyword"]


def scan_host_log(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),"Original host stdout missing or symlinked")
    raw=path.read_bytes()
    require(0<len(raw)<=LIMIT_BYTES,"Original host stdout empty or unexpectedly large")
    text=raw.decode("utf-8","replace")
    lines=text.splitlines()
    require(len(lines)<=MAX_LINES,"Host log line count exceeds bounded audit maximum")
    reasons=[]
    other=0
    for line in lines:
        plain=ANSI_PATTERN.sub("",line)
        m=CPAL_PATTERN.search(plain)
        if m:
            reasons.append(normalize_reason(m.group(1)))
        elif OTHER_AUDIO_PATTERN.search(plain):
            other+=1
    counts=Counter(reasons)
    groups=[]
    for normalized,n in sorted(counts.items(),key=lambda item:(-item[1],item[0])):
        groups.append({
            "normalized_message":normalized,
            "times_in_entire_stdout":n,
            "lexical_tokens_not_diagnosis":descriptive_tags(normalized),
            "normalized_message_sha256":hashlib.sha256(normalized.encode("utf8")).hexdigest(),
        })
    return {
        "original_stdout_sha256":hashlib.sha256(raw).hexdigest(),
        "original_stdout_bytes":len(raw),
        "original_stdout_line_count":len(lines),
        "cpal_stream_error_log_line_count_all_times":len(reasons),
        "distinct_sanitized_cpal_error_messages":len(groups),
        "other_audio_warning_line_count_all_times":other,
        "sanitized_error_message_groups":groups[:32],
        "error_groups_truncated":len(groups)>32,
        "stdout_has_no_per_event_monotonic_guest_clock":True,
        "full_run_log_count_cannot_equal_window_delta_by_assumption":True,
    }


def inventory(root,ms):
    root=Path(root)
    # Recheck real guest optical PNG CRC, actual raw PCM, CPAL lifecycle L-CSV
    # and exact source/run/attempt SHA, not saved JSON values alone.
    proof=check_trial(root,ms)
    require(proof["actual_raw_png_pcm_cpal_evidence_redecoded"] is True,
            "Original raw guest/CPAL/PCM re-decode not verified")
    observed=scan_host_log(root/"nexium-guest-stdout.log")
    observed.update({
        "requested_pulse_hint_ms":ms,
        "source_run_id":RUNS[ms],
        "exact_compiled_nexium_elf_sha256":proof["compiled_host_sha256"],
        "exact_generated_only_nro_sha256":proof["generated_research_nro_sha256"],
        "post_input_cpal_error_callback_counter_delta":proof["cpal_error_callbacks_after_input"],
        "post_input_cpal_callback_entry_delta":proof["cpal_entries_after_input"],
        "post_input_cpal_callback_return_delta":proof["cpal_returns_after_input"],
        "post_input_audioout_appends":proof["audioout_appends_after_input"],
        "guest_optical_result":proof["guest_final_optical_result"],
        "raw_nonzero_virtual_pcm16_samples":proof["actual_nonzero_pcm16_samples"],
        "final_lifecycle_state":proof["cpal_lifecycle_final_state"],
    })
    return proof,observed


def compare_logs(record21,record22,pair_result):
    require(record21["requested_pulse_hint_ms"]==21 and
            record22["requested_pulse_hint_ms"]==22,
            "Wrong requested Pulse hints")
    require(record21["source_run_id"]==RUNS[21] and
            record22["source_run_id"]==RUNS[22],
            "Actual original guest run ID mismatch")
    require(all(r["exact_compiled_nexium_elf_sha256"]==HOST_SHA and
                r["exact_generated_only_nro_sha256"]==NRO_SHA
                for r in (record21,record22)),
            "Not identical Stage287 ELF and ROM-free guest NRO")
    require(pair_result=="ONE_NEW_ELF_21_22_GUEST_CONTRAST_VERIFIED",
            "Cannot attribute host error messages to a verified one-pair guest contrast")
    require(record21["post_input_cpal_error_callback_counter_delta"]==0,
            "21ms actual post-input CPAL error callback delta changed")
    require(record22["post_input_cpal_error_callback_counter_delta"]>0,
            "22ms actual CPAL callback error delta absent")
    require(record21["post_input_cpal_callback_entry_delta"]==0 and
            record22["post_input_cpal_callback_entry_delta"]>0,
            "21/22 host callback observation does not match source evidence")
    return {
        "schema":SCHEMA,
        "result":"REAL_MATCHED_CPAL_HOST_ERROR_LOGS_AND_L_COUNTERS_INVENTORIED",
        "same_compiled_lifecycle_nexium_elf_sha256":HOST_SHA,
        "same_rom_free_opt_in_guest_nro_sha256":NRO_SHA,
        "actual_21ms_and_22ms_guest_raw_evidence_redecoded":True,
        "strict_existing_new_host_guest_contrast_verified":True,
        "cpal_message_reason_visibility":(
            "MESSAGE_TEXT_PRESENT_IN_AT_LEAST_ONE_HOST_LOG"
            if (record21["cpal_stream_error_log_line_count_all_times"]+
                record22["cpal_stream_error_log_line_count_all_times"])>0
            else "NO_CPAL_ERROR_MESSAGE_TEXT_EMITTED_TO_CAPTURED_STDOUT"),
        "stdout_error_lines_cannot_be_precisely_mapped_to_guest_window":True,
        "cpal_error_callback_count_alone_does_not_prove_failed_guest_audio":True,
        "life_state_3_is_prior_play_success_not_current_running_proof":True,
        "requested_latency_hint_is_not_measured_hardware_period":True,
        "no_per_error_event_clock_or_alsa_stack_trace":True,
        "no_cpal_root_cause_or_permanent_guest_deadlock_proven":True,
        "original_game_rom_or_audio_used":False,
        "physical_nintendo_switch_dac_proven":False,
        "trials":[record21,record22],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run21",type=Path,required=True)
    p.add_argument("--run22",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        t21,r21=inventory(a.run21,21)
        t22,r22=inventory(a.run22,22)
        pair=compare(t21,t22)
        result=compare_logs(r21,r22,pair["result"])
        status=0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,
            OverflowError,json.JSONDecodeError) as exc:
        result={
            "schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
            "no_cpal_root_cause_or_permanent_guest_deadlock_proven":True,
            "physical_nintendo_switch_dac_proven":False,
        }
        status=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return status


if __name__=="__main__":
    raise SystemExit(main())

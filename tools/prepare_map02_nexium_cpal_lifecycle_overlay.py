#!/usr/bin/env python3
"""Stage286: opt-in CPAL stream lifecycle/error counters for exact Stage274 overlay.

Run only AFTER prepare_map02_nexium_cpal_overlay.py on immutable upstream
nexium-emu/nexium@089562567a0a8760dfdd8420e1f57c35159a9219.
This never mutates the production Switch game or historical ELF.

The CPAL error callback increments ONE relaxed atomic only; no syscall/file
I/O, allocation or logging is newly introduced on real-time audio callbacks.
A non-real-time reporter samples lifecycle state under CLOCK_MONOTONIC.
Reporter clock bounds error arrival to a sample window, NOT exact event time.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_map02_nexium_cpal_overlay import RUNNER,UPSTREAM,once

SCHEMA="vh-map02-stage286-cpal-lifecycle-source-overlay/v1"
COUNTERS=("INIT","DEVICE_MISSING","CONFIG_FAILED","BUILD_ATTEMPT",
          "BUILD_FAILED","BUILD_OK","PLAY_FAILED","PLAY_OK",
          "ERROR_CALLBACK","STREAM_DROPPED")

LIFECYCLE="// Stage286 standalone research-only CPAL lifecycle samples.\n// The existing Stage274 callback counter CSV format remains untouched.\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_REPORTER_STARTED: std::sync::atomic::AtomicBool =\n    std::sync::atomic::AtomicBool::new(false);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_INIT: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_DEVICE_MISSING: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_CONFIG_FAILED: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_BUILD_ATTEMPT: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_BUILD_FAILED: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_BUILD_OK: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_PLAY_FAILED: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_PLAY_OK: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_ERROR_CALLBACK: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_STREAM_DROPPED: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_BUILD_START_NS: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_PLAY_OK_NS: AtomicU64 = AtomicU64::new(0);\n#[cfg(target_os = \"linux\")]\nstatic MAP02_LIFE_DROP_NS: AtomicU64 = AtomicU64::new(0);\n\n#[cfg(target_os = \"linux\")]\nfn map02_life_now_ns() -> u64 {\n    let mut stamp = libc::timespec { tv_sec: 0, tv_nsec: 0 };\n    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut stamp) } != 0\n        || stamp.tv_sec < 0 || stamp.tv_nsec < 0 {\n        return 0;\n    }\n    (stamp.tv_sec as u64).saturating_mul(1_000_000_000)\n        .saturating_add(stamp.tv_nsec as u64)\n}\n\n#[cfg(target_os = \"linux\")]\nfn map02_start_cpal_lifecycle_reporter() {\n    use std::io::Write;\n    let Ok(path) = std::env::var(\"VH_MAP02_CPAL_LIFECYCLE_PATH\") else { return; };\n    if path.len() > 800 || !std::path::Path::new(&path).is_absolute() { return; }\n    if MAP02_LIFE_REPORTER_STARTED.compare_exchange(\n        false,true,Ordering::Relaxed,Ordering::Relaxed).is_err() { return; }\n    let _ = std::thread::Builder::new()\n        .name(\"map02-cpal-lifecycle\".into())\n        .spawn(move || {\n            for _ in 0..240 {\n                std::thread::sleep(std::time::Duration::from_millis(200));\n                let nanos = map02_life_now_ns();\n                if nanos == 0 { continue; }\n                // This file is written ONLY from this non-real-time thread.\n                if let Ok(mut f) = std::fs::OpenOptions::new()\n                    .create(true).append(true).open(&path) {\n                    let _ = writeln!(f,\n                        \"L,{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\",\n                        nanos,\n                        MAP02_LIFE_INIT.load(Ordering::Relaxed),\n                        MAP02_LIFE_DEVICE_MISSING.load(Ordering::Relaxed),\n                        MAP02_LIFE_CONFIG_FAILED.load(Ordering::Relaxed),\n                        MAP02_LIFE_BUILD_ATTEMPT.load(Ordering::Relaxed),\n                        MAP02_LIFE_BUILD_FAILED.load(Ordering::Relaxed),\n                        MAP02_LIFE_BUILD_OK.load(Ordering::Relaxed),\n                        MAP02_LIFE_PLAY_FAILED.load(Ordering::Relaxed),\n                        MAP02_LIFE_PLAY_OK.load(Ordering::Relaxed),\n                        MAP02_LIFE_ERROR_CALLBACK.load(Ordering::Relaxed),\n                        MAP02_LIFE_STREAM_DROPPED.load(Ordering::Relaxed),\n                        MAP02_LIFE_BUILD_START_NS.load(Ordering::Relaxed),\n                        MAP02_LIFE_PLAY_OK_NS.load(Ordering::Relaxed),\n                        MAP02_LIFE_DROP_NS.load(Ordering::Relaxed));\n                }\n            }\n        });\n}\n\n#[cfg(target_os = \"linux\")]\nstruct Map02HeldStream(cpal::Stream);\n#[cfg(target_os = \"linux\")]\nimpl Drop for Map02HeldStream {\n    fn drop(&mut self) {\n        MAP02_LIFE_STREAM_DROPPED.fetch_add(1, Ordering::Relaxed);\n        MAP02_LIFE_DROP_NS.store(map02_life_now_ns(), Ordering::Relaxed);\n    }\n}\n#[cfg(not(target_os = \"linux\"))]\ntype Map02HeldStream = cpal::Stream;\n\n"

def patch_runner(source: str) -> str:
    if "MAP02_LIFE_PLAY_OK" in source:
        raise ValueError("Stage286 lifecycle overlay already installed")
    if not all(marker in source for marker in (
            "MAP02_CPAL_ENTER","map02_start_cpal_reporter(sink);",
            'libc::CLOCK_MONOTONIC')):
        raise ValueError("Apply exact Stage274 CPAL/AudioOut overlay first")
    statics_anchor=(
        '#[cfg(target_os = "linux")]\n'
        'static MAP02_CPAL_ENTER: AtomicU64 = AtomicU64::new(0);')
    updated=once(source,statics_anchor,LIFECYCLE+statics_anchor,
                 "lifecycle collector declaration")
    begin="fn init_host_audio_on_thread(preferred_device: Option<&str>, initial_volume: f32) {"
    updated=once(updated,begin,begin+'''
    #[cfg(target_os = "linux")]
    {
        map02_start_cpal_lifecycle_reporter();
        MAP02_LIFE_INIT.fetch_add(1, Ordering::Relaxed);
    }''',"initial lifecycle probe")
    updated=once(updated,
        '''        log::warn!("Audio output disabled: no output device available");
        return;''',
        '''        #[cfg(target_os = "linux")]
        MAP02_LIFE_DEVICE_MISSING.fetch_add(1, Ordering::Relaxed);
        log::warn!("Audio output disabled: no output device available");
        return;''',"device missing event")
    updated=once(updated,
        '''            log::warn!("Audio output disabled: {}", e);
            return;''',
        '''            #[cfg(target_os = "linux")]
            MAP02_LIFE_CONFIG_FAILED.fetch_add(1, Ordering::Relaxed);
            log::warn!("Audio output disabled: {}", e);
            return;''',"config failure event")
    updated=once(updated,
        '''    let err_cb = |e| log::error!("cpal stream error: {}", e);''',
        '''    let err_cb = |e| {
        // No new I/O, syscalls or allocations on CPAL's real-time callback.
        #[cfg(target_os = "linux")]
        MAP02_LIFE_ERROR_CALLBACK.fetch_add(1, Ordering::Relaxed);
        log::error!("cpal stream error: {}", e);
    };''',"real CPAL error callback")
    updated=once(updated,
        '''    let stream_result = match sample_format {''',
        '''    #[cfg(target_os = "linux")]
    {
        MAP02_LIFE_BUILD_ATTEMPT.fetch_add(1, Ordering::Relaxed);
        MAP02_LIFE_BUILD_START_NS.store(map02_life_now_ns(), Ordering::Relaxed);
    }
    let stream_result = match sample_format {''',"stream build attempt")
    updated=once(updated,
        '''    let stream = match stream_result {
        Ok(s) => s,
        Err(e) => {
            log::warn!("Audio output disabled: build_output_stream: {}", e);''',
        '''    let stream = match stream_result {
        Ok(s) => {
            #[cfg(target_os = "linux")]
            MAP02_LIFE_BUILD_OK.fetch_add(1, Ordering::Relaxed);
            s
        }
        Err(e) => {
            #[cfg(target_os = "linux")]
            MAP02_LIFE_BUILD_FAILED.fetch_add(1, Ordering::Relaxed);
            log::warn!("Audio output disabled: build_output_stream: {}", e);''',
        "stream build returned")
    updated=once(updated,
        '''    if let Err(e) = stream.play() {
        log::warn!("Audio output disabled: stream.play: {}", e);
        return;
    }''',
        '''    if let Err(e) = stream.play() {
        #[cfg(target_os = "linux")]
        MAP02_LIFE_PLAY_FAILED.fetch_add(1, Ordering::Relaxed);
        log::warn!("Audio output disabled: stream.play: {}", e);
        return;
    }
    #[cfg(target_os = "linux")]
    {
        MAP02_LIFE_PLAY_OK.fetch_add(1, Ordering::Relaxed);
        MAP02_LIFE_PLAY_OK_NS.store(map02_life_now_ns(), Ordering::Relaxed);
    }''',
        "stream.play result")
    updated=once(updated,
        "std::cell::RefCell<Option<cpal::Stream>>",
        "std::cell::RefCell<Option<Map02HeldStream>>",
        "thread-local stream guard type")
    updated=once(updated,
        "    AUDIO_STREAM.with(|s| *s.borrow_mut() = Some(stream));",
        '''    #[cfg(target_os = "linux")]
    let held_stream = Map02HeldStream(stream);
    #[cfg(not(target_os = "linux"))]
    let held_stream = stream;
    AUDIO_STREAM.with(|s| *s.borrow_mut() = Some(held_stream));''',
        "stream guard placement")
    return updated


def apply(root: Path,expected_source: str=UPSTREAM) -> dict:
    if expected_source!=UPSTREAM:
        raise ValueError("Unknown upstream NeXium source")
    target=root/RUNNER
    raw=target.read_bytes()
    content=raw.decode("utf-8").replace("\r\n","\n")
    amended=patch_runner(content)
    if b"\r\n" in raw:
        amended=amended.replace("\n","\r\n")
    updated=amended.encode("utf-8")
    target.write_bytes(updated)
    return {
        "schema":SCHEMA,
        "result":"RESEARCH_ONLY_CPAL_STREAM_LIFECYCLE_SOURCE_PATCHED",
        "pinned_upstream_source_sha":UPSTREAM,
        "source_path":RUNNER,
        "stage274_overlay_required":True,
        "source_sha256_before":hashlib.sha256(raw).hexdigest(),
        "source_sha256_after":hashlib.sha256(updated).hexdigest(),
        "error_callback_new_operations":"relaxed_atomic_increment_only",
        "lifecycle_reporter_has_per_event_error_clock":False,
        "non_realtime_build_play_timestamp_ns_recorded":True,
        "stream_drop_count_instrumented":True,
        "no_existing_cpal_counter_reporter_modified":True,
        "new_compiled_executable_proven":False,
        "guest_audio_21ms_root_cause_proven":False,
        "physical_switch_audio_proven":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream",required=True,type=Path)
    p.add_argument("--receipt",required=True,type=Path)
    a=p.parse_args()
    head=subprocess.check_output(["git","-C",str(a.upstream),"rev-parse","HEAD"],
                                 text=True).strip()
    if head!=UPSTREAM:
        raise SystemExit("UNVERIFIED upstream commit "+head)
    try:
        receipt=apply(a.upstream,head)
    except (OSError,ValueError,UnicodeError) as e:
        raise SystemExit("UNVERIFIED Stage286 lifecycle overlay: "+str(e))
    a.receipt.parent.mkdir(parents=True,exist_ok=True)
    a.receipt.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    print(json.dumps(receipt,sort_keys=True,indent=2))

if __name__=="__main__":
    main()

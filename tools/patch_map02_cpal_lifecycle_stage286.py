#!/usr/bin/env python3
"""Stage286 research-only patch on TOP of Stage274 instrumented NeXium audio.rs.

Records lifecycle transitions using bounded monotonic-time *atomic state*,
sampled by the existing reporter. No data or locks in the audio callback.
The patch does not represent actual tested CPAL events until Rust cargo check
and a new SHA-pinned instrumented NeXium host build succeed.
"""
import argparse
from pathlib import Path

STATE="""// Stage286 opt-in CPAL stream lifecycle state: sampled, not callback-locked.
#[cfg(target_os = "linux")]
static MAP02_CPAL_LIFECYCLE: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "linux")]
static MAP02_CPAL_ERROR_COUNT: AtomicU64 = AtomicU64::new(0);
"""
# State codes 1=attempting build, 2=built, 3=play returned success,
# 4=build failed, 5=play failed, 6=unsupported format/device.
def once(s,old,new):
    if s.count(old)!=1:
        raise ValueError(f"Missing or ambiguous upstream stage-274 anchor: {old[:70]}")
    return s.replace(old,new,1)

def patch(s):
    if "MAP02_CPAL_LIFECYCLE" in s:
        raise ValueError("Lifecycle overlay already present")
    if "MAP02_CPAL_ENTER" not in s or "map02_start_cpal_reporter" not in s:
        raise ValueError("Stage274 CPAL callback counters must already be present")
    s=once(s,"static MAP02_CPAL_FRAMES: AtomicU64 = AtomicU64::new(0);",
        "static MAP02_CPAL_FRAMES: AtomicU64 = AtomicU64::new(0);\n"+STATE.rstrip())
    s=once(s,
        'let err_cb = |e| log::error!("cpal stream error: {}", e);',
        '''let err_cb = |e| {
        #[cfg(target_os = "linux")]
        MAP02_CPAL_ERROR_COUNT.fetch_add(1, Ordering::Relaxed);
        log::error!("cpal stream error: {}", e);
    };
    #[cfg(target_os = "linux")]
    MAP02_CPAL_LIFECYCLE.store(1, Ordering::Relaxed);''')
    s=once(s,
        '    let stream = match stream_result {\n        Ok(s) => s,\n        Err(e) => {',
        '''    let stream = match stream_result {
        Ok(s) => {
            #[cfg(target_os = "linux")]
            MAP02_CPAL_LIFECYCLE.store(2, Ordering::Relaxed);
            s
        },
        Err(e) => {
            #[cfg(target_os = "linux")]
            MAP02_CPAL_LIFECYCLE.store(4, Ordering::Relaxed);''')
    s=once(s,
        '    if let Err(e) = stream.play() {\n        log::warn!("Audio output disabled: stream.play: {}", e);',
        '''    if let Err(e) = stream.play() {
        #[cfg(target_os = "linux")]
        MAP02_CPAL_LIFECYCLE.store(5, Ordering::Relaxed);
        log::warn!("Audio output disabled: stream.play: {}", e);''')
    s=once(s,
        '    let device_name = device\n        .description()',
        '''    #[cfg(target_os = "linux")]
    MAP02_CPAL_LIFECYCLE.store(3, Ordering::Relaxed);

    let device_name = device
        .description()''')
    s=once(s,
        '            let calls = MAP02_CPAL_ENTER.load(Ordering::Relaxed);',
        '''            let lifecycle = MAP02_CPAL_LIFECYCLE.load(Ordering::Relaxed);
            let errors = MAP02_CPAL_ERROR_COUNT.load(Ordering::Relaxed);
            let calls = MAP02_CPAL_ENTER.load(Ordering::Relaxed);''')
    s=once(s,
        'writeln!(output, "T,{nanos},{calls},{returns},{frames},{consumed},{appends},{pushed},{released}");',
        'writeln!(output, "L,{nanos},{lifecycle},{errors},{calls},{returns},{frames},{consumed},{appends},{pushed},{released}");')
    return s

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    opt=ap.parse_args()
    source=opt.input.read_text(encoding="utf-8")
    output=patch(source)
    opt.output.parent.mkdir(parents=True,exist_ok=True)
    opt.output.write_text(output,encoding="utf-8")
    print("Created Stage286 research-only lifecycle instrumented audio.rs")
if __name__=="__main__":
    main()

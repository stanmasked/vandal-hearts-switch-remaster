#!/usr/bin/env python3
"""Source-anchored Stage298 *host-only* CPAL event timestamps, after 274+286.

Opt-in P CSV is written by existing NON-real-time reporter. Never add a clock
syscall, log, lock, allocation or file operation to CPAL data callbacks.
P timestamps describe build/play/drop paths; callback entries are ONLY an
atomic counter snapshot and cannot be assigned precise event timestamps.
"""
import argparse
from pathlib import Path

MARKERS="""// Stage298: Linux opt-in source-pinned non-RT CPAL lifetime timestamps.
#[cfg(target_os = "linux")]
static MAP02_S298_BUILD_BEGIN_NS: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "linux")]
static MAP02_S298_BUILD_OK_NS: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "linux")]
static MAP02_S298_BUILD_FAIL_NS: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "linux")]
static MAP02_S298_PLAY_BEGIN_NS: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "linux")]
static MAP02_S298_PLAY_OK_NS: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "linux")]
static MAP02_S298_PLAY_FAIL_NS: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "linux")]
static MAP02_S298_DROP_NS: AtomicU64 = AtomicU64::new(0);

#[cfg(target_os = "linux")]
fn map02_s298_monotonic_ns() -> u64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    let success = unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) } == 0;
    if !success || ts.tv_sec < 0 || ts.tv_nsec < 0 {
        return 0;
    }
    (ts.tv_sec as u64).saturating_mul(1_000_000_000)
        .saturating_add(ts.tv_nsec as u64)
}

#[cfg(target_os = "linux")]
struct Map02S298RetainedStream(cpal::Stream);
#[cfg(target_os = "linux")]
impl Drop for Map02S298RetainedStream {
    fn drop(&mut self) {
        MAP02_S298_DROP_NS.store(map02_s298_monotonic_ns(), Ordering::Relaxed);
    }
}
#[cfg(target_os = "linux")]
type Map02S298StreamSlot = Map02S298RetainedStream;
#[cfg(not(target_os = "linux"))]
type Map02S298StreamSlot = cpal::Stream;
"""

def once(s,anchor,replacement,reason):
    n=s.count(anchor)
    if n!=1:
        raise ValueError(f"{reason}: expected exactly one anchor, found {n}")
    return s.replace(anchor,replacement,1)

def patch(s):
    if "MAP02_S298_BUILD_BEGIN_NS" in s:
        raise ValueError("Stage298 probe already installed")
    for key in ("MAP02_CPAL_LIFECYCLE","MAP02_CPAL_ERROR_COUNT",
                "map02_start_cpal_reporter","MAP02_CPAL_ENTER"):
        if key not in s:
            raise ValueError("Missing required Stage274/286 counters: "+key)
    marker='static MAP02_CPAL_ERROR_COUNT: AtomicU64 = AtomicU64::new(0);'
    s=once(s,marker,marker+"\n"+MARKERS,"Stage286 static state")
    start='    let _ = std::thread::Builder::new().name("map02-cpal-counts".into()).spawn(move || {'
    s=once(s,start,
        '''    let stage298_path = std::env::var("VH_MAP02_CPAL_LIFETIME_PATH").ok().filter(
        |s| s.len() <= 800 && std::path::Path::new(s).is_absolute()
    );
'''+start,"Reporter opt-in path")
    report='''                let _ = writeln!(output, "L,{nanos},{lifecycle},{errors},{calls},{returns},{frames},{consumed},{appends},{pushed},{released}");
            }'''
    report2=report+'''
            // P records are emitted only by this NON-RT reporter, never a CPAL callback.
            // The P row's latest count is NOT a timestamp of the callback itself.
            if let Some(ref target) = stage298_path {
                let build_begin = MAP02_S298_BUILD_BEGIN_NS.load(Ordering::Relaxed);
                let build_ok = MAP02_S298_BUILD_OK_NS.load(Ordering::Relaxed);
                let build_fail = MAP02_S298_BUILD_FAIL_NS.load(Ordering::Relaxed);
                let play_begin = MAP02_S298_PLAY_BEGIN_NS.load(Ordering::Relaxed);
                let play_ok = MAP02_S298_PLAY_OK_NS.load(Ordering::Relaxed);
                let play_fail = MAP02_S298_PLAY_FAIL_NS.load(Ordering::Relaxed);
                let drop_ns = MAP02_S298_DROP_NS.load(Ordering::Relaxed);
                if let Ok(mut second) = std::fs::OpenOptions::new()
                    .create(true).append(true).open(target)
                {
                    let _ = writeln!(second,
                        "P,{nanos},{build_begin},{build_ok},{build_fail},{play_begin},{play_ok},{play_fail},{drop_ns},{calls}");
                }
            }'''
    s=once(s,report,report2,"Separate P reporter after unchanged L schema")
    start='    MAP02_CPAL_LIFECYCLE.store(1, Ordering::Relaxed);'
    s=once(s,start,start+'''
    #[cfg(target_os = "linux")]
    MAP02_S298_BUILD_BEGIN_NS.store(map02_s298_monotonic_ns(), Ordering::Relaxed);''',"Build start stamp")
    for state,name in [(2,"BUILD_OK"),(4,"BUILD_FAIL"),(5,"PLAY_FAIL"),(3,"PLAY_OK")]:
        old=f"MAP02_CPAL_LIFECYCLE.store({state}, Ordering::Relaxed);"
        s=once(s,old,old+f'''
            #[cfg(target_os = "linux")]
            MAP02_S298_{name}_NS.store(map02_s298_monotonic_ns(), Ordering::Relaxed);''',f"Lifecycle {state} precise stamp")
    play='    if let Err(e) = stream.play() {'
    s=once(s,play,'''    #[cfg(target_os = "linux")]
    MAP02_S298_PLAY_BEGIN_NS.store(map02_s298_monotonic_ns(), Ordering::Relaxed);
'''+play,"Play call begin time")
    old='''static AUDIO_STREAM: std::cell::RefCell<Option<cpal::Stream>> ='''
    s=once(s,old,'''static AUDIO_STREAM: std::cell::RefCell<Option<Map02S298StreamSlot>> =''',"Source-pinned retained-stream drop guard type")
    last='    AUDIO_STREAM.with(|s| *s.borrow_mut() = Some(stream));'
    s=once(s,last,'''    #[cfg(target_os = "linux")]
    let stream = Map02S298RetainedStream(stream);
'''+last,"Retained stream guard")
    # The upstream has no stream.pause() call: do not fabricate one.
    # No new statement in F32 or I16 real-time callback closures.
    require=["MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);",
             "MAP02_CPAL_RETURN.fetch_add(1, Ordering::Relaxed);"]
    for key in require:
        if s.count(key)!=2:
            raise ValueError("Unexpected callback changes: "+key)
    if 'stream.pause()' in s:
        raise ValueError("Stage298 cannot claim no pause when source calls pause")
    if s.count('writeln!(output, "L,{nanos}')!=1 or s.count('writeln!(second,')!=1:
        raise ValueError("Old L reporter must be preserved and new P reporter singular")
    return s

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--input",type=Path,required=True)
    a.add_argument("--output",type=Path,required=True)
    v=a.parse_args()
    source=v.input.read_text(encoding="utf-8")
    changed=patch(source)
    v.output.parent.mkdir(parents=True,exist_ok=True)
    v.output.write_text(changed,encoding="utf-8")
    print("Stage298 research source overlay applied; original 11-column L telemetry unchanged")

if __name__=="__main__":
    main()

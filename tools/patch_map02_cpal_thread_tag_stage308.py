#!/usr/bin/env python3
"""Stage308 source-anchored opt-in CPAL callback / ALSA same-TLS-slot probe.

Apply ONLY after frozen NeXium source overlay Stage274, Stage286 and Stage298.
Source change is limited to upstream/nexium-runner/src/audio.rs in an isolated
new research-only ELF. No game, Nintendo Switch build, existing Stage298 ELF,
guest NRO or upstream NeXium branch modifications are made.

The callback only reads one atomic pre-resolved *function pointer*, then calls
the preloaded C shim; the shim increments one relaxed atomic per anonymous TLS
slot. No thread ID, kernel system call, timestamp, allocation, audio payload,
logging or file I/O in a callback. C shim MUST be preloaded before NeXium starts.
"""
import argparse
from pathlib import Path

MARKERS = r'''// Stage308: opt-in same-TLS-slot marker: CPAL callbacks and exported ALSA
// calls update the same process-local shim, not Linux PIDs or real thread IDs.
#[cfg(target_os = "linux")]
static MAP02_S308_CALLBACK_HOOK: std::sync::atomic::AtomicUsize =
    std::sync::atomic::AtomicUsize::new(0);

#[cfg(target_os = "linux")]
fn map02_s308_prepare_callback_hook() {
    // Executed on stream build path, NEVER on real-time data callbacks.
    if std::env::var("VH_MAP02_STAGE308_CALLBACK_TAG").as_deref() != Ok("1") {
        return;
    }
    let symbol = b"vh_map02_stage308_cpal_callback_mark\0";
    let pointer = unsafe {
        libc::dlsym(libc::RTLD_DEFAULT, symbol.as_ptr() as *const libc::c_char)
    };
    if !pointer.is_null() {
        MAP02_S308_CALLBACK_HOOK.store(
            pointer as usize, Ordering::Release);
    }
}

#[cfg(target_os = "linux")]
#[inline(always)]
fn map02_s308_callback_tag_only() {
    let pointer = MAP02_S308_CALLBACK_HOOK.load(Ordering::Relaxed);
    if pointer != 0 {
        // Signature is provided by the source-reviewed Stage308 C shim.
        let marker: unsafe extern "C" fn() =
            unsafe { std::mem::transmute(pointer) };
        unsafe { marker() };
    }
}
'''


def once(s,anchor,replacement):
    n=s.count(anchor)
    if n!=1:
        raise ValueError(f"Ambiguous Stage308 source anchor ({n}): {anchor[:90]}")
    return s.replace(anchor,replacement,1)


def patch(source):
    s=source
    if "MAP02_S308_CALLBACK_HOOK" in s:
        raise ValueError("Stage308 marker already present")
    for item in ("MAP02_S298_BUILD_BEGIN_NS","MAP02_S298_PLAY_OK_NS",
                 "MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);",
                 "map02_start_cpal_reporter"):
        if item not in s:
            raise ValueError("Missing source-verified NeXium Stage298 anchor: "+item)
    # No modifications to existing P or L reporter and no logging in callbacks.
    static='static MAP02_S298_DROP_NS: AtomicU64 = AtomicU64::new(0);'
    s=once(s,static,static+"\n"+MARKERS)
    build='    MAP02_CPAL_LIFECYCLE.store(1, Ordering::Relaxed);'
    s=once(s,build,build+'''
    #[cfg(target_os = "linux")]
    map02_s308_prepare_callback_hook();''')
    old='MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);'
    if s.count(old)!=2:
        raise ValueError("Expected both exact F32 and I16 source callbacks")
    s=s.replace(old,old+'''
                #[cfg(target_os = "linux")]
                map02_s308_callback_tag_only();''')
    for original,qty in (
        ('MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);',2),
        ('MAP02_CPAL_RETURN.fetch_add(1, Ordering::Relaxed);',2),
        ('map02_s308_callback_tag_only();',2),
        ('map02_s308_prepare_callback_hook();',1),
        ('writeln!(output, "L,{nanos}',1),
        ('writeln!(second,',1),
    ):
        if s.count(original)!=qty:
            raise ValueError(f"Stage308 source mutation invalid {original}: "
                             f"{s.count(original)} != {qty}")
    if "stream.pause()" in s:
        raise ValueError("Stage308 source contains unwanted stream.pause")
    return s


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    content=patch(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(content,encoding="utf-8")
    print("Patched ONLY isolated opt-in NeXium source audio.rs; not upstream")


if __name__=="__main__":
    main()


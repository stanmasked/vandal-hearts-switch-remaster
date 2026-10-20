#!/usr/bin/env python3
"""Stage274: fail-closed opt-in Rust CPAL/AudioOut source instrumentation.

Use ONLY on immutable nexium-emu/nexium source 08956256..., in a separate
experimental build. This is NOT the archived nightly NeXium host executable.
Outputs are counters, not licensed game PCM, samples, addresses or assets.

Real-time CPAL callbacks get only relaxed atomics; a dedicated non-RT
reporter reads them every 200ms and reports Linux CLOCK_MONOTONIC timestamps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

UPSTREAM="089562567a0a8760dfdd8420e1f57c35159a9219"
SCHEMA="vh-map02-nexium-cpal-source-overlay/v1"
RUNNER="nexium-runner/src/audio.rs"
KERNEL="nexium-kernel/src/services/audio_out/handlers.rs"
TRACE_SCHEMA="vh-map02-cpal-and-audout-counters/v1"


def once(data: str, old: str, new: str, label: str) -> str:
    n=data.count(old)
    if n!=1:
        raise ValueError(f"{label}: expected exactly one source anchor, found {n}")
    return data.replace(old,new,1)


def instrument_callback(segment: str, kind: str, render: str) -> str:
    anchor=f"move |out: &mut [{kind}], _info: &cpal::OutputCallbackInfo| {{"
    segment=once(segment,anchor,anchor+
        "\n                    MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);",
        f"{kind} callback entrance")
    ending="""                        &mut prebuf,
                    );
                },"""
    insertion="""                        &mut prebuf,
                    );
                    MAP02_CPAL_RETURN.fetch_add(1, Ordering::Relaxed);
                    MAP02_CPAL_FRAMES.fetch_add((out.len() / dev_ch) as u64, Ordering::Relaxed);
                },"""
    return once(segment,ending,insertion,render)


def patch_runner(original: str) -> str:
    if "MAP02_CPAL_ENTER" in original:
        raise ValueError("Overlay already installed; refusing double instrumentation")
    const="const RENDER_SR: u32 = 48_000;"
    prefix="""// Stage274 experimental Linux-host counters; no audio bytes are logged.
#[cfg(target_os = "linux")]
static MAP02_CPAL_ENTER: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "linux")]
static MAP02_CPAL_RETURN: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "linux")]
static MAP02_CPAL_FRAMES: AtomicU64 = AtomicU64::new(0);

#[cfg(target_os = "linux")]
fn map02_start_cpal_reporter(sink: Arc<HostAudioSink>) {
    use std::io::Write;
    let Ok(path) = std::env::var("VH_MAP02_CPAL_TRACE_PATH") else { return; };
    if path.len() > 800 || !std::path::Path::new(&path).is_absolute() {
        return;
    }
    let _ = std::thread::Builder::new().name("map02-cpal-counts".into()).spawn(move || {
        for _ in 0..240 {
            std::thread::sleep(std::time::Duration::from_millis(200));
            let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
            let ok = unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) } == 0;
            if !ok || ts.tv_sec < 0 || ts.tv_nsec < 0 { continue; }
            let nanos = (ts.tv_sec as u64).saturating_mul(1_000_000_000)
                       .saturating_add(ts.tv_nsec as u64);
            let calls = MAP02_CPAL_ENTER.load(Ordering::Relaxed);
            let returns = MAP02_CPAL_RETURN.load(Ordering::Relaxed);
            let frames = MAP02_CPAL_FRAMES.load(Ordering::Relaxed);
            let consumed = sink.consumed.load(Ordering::Relaxed);
            let appends = nexium_kernel::services::audio_out::handlers::MAP02_AOUT_APPENDS
                .load(Ordering::Relaxed);
            let pushed = nexium_kernel::services::audio_out::handlers::MAP02_AOUT_PUSHED_FRAMES
                .load(Ordering::Relaxed);
            let released = nexium_kernel::services::audio_out::handlers::MAP02_AOUT_RELEASED
                .load(Ordering::Relaxed);
            if let Ok(mut output) = std::fs::OpenOptions::new()
                .create(true).append(true).open(&path)
            {
                let _ = writeln!(output, "T,{nanos},{calls},{returns},{frames},{consumed},{appends},{pushed},{released}");
            }
        }
    });
}

"""
    # Keep non-Linux targets unmodified; the callbacks contain Linux-only
    # counter references and must remain compilable on macOS/Windows.
    runner=once(original,const,prefix+const,"runner statics and reporter")
    beginning="        SampleFormat::F32 => {"
    middle="        SampleFormat::I16 => {"
    ending="        other => {"
    if runner.count(beginning)!=1 or runner.count(middle)!=1 or runner.count(ending)!=1:
        raise ValueError("Unsupported NeXium audio sample-format dispatch")
    head,rest=runner.split(beginning,1)
    f32,rest=rest.split(middle,1)
    i16,tail=rest.split(ending,1)
    f32=instrument_callback(f32,"f32","F32")
    i16=instrument_callback(i16,"i16","I16")
    runner=head+beginning+f32+middle+i16+ending+tail

    # Both sample-format callback closures are present on non-Linux too, so
    # ensure cfg-limited atomics don't cause cross-platform name failures:
    # use an inline cfg block around the metric increments.
    for snippet in [
        "                    MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);",
        "                    MAP02_CPAL_RETURN.fetch_add(1, Ordering::Relaxed);",
        "                    MAP02_CPAL_FRAMES.fetch_add((out.len() / dev_ch) as u64, Ordering::Relaxed);",
    ]:
        if runner.count(snippet)!=2:
            raise ValueError("Expected identical callback instrumentation in F32 + I16")
        runner=runner.replace(snippet,
            "                    #[cfg(target_os = \"linux\")]\n"+snippet)

    runner=once(
        runner,
        "    let sink_dyn: Arc<dyn HostPcmSink> = sink;\n"
        "    set_host_audio_sink(sink_dyn);\n\n"
        "    std::thread_local! {",
        "    let sink_dyn: Arc<dyn HostPcmSink> = sink.clone();\n"
        "    set_host_audio_sink(sink_dyn);\n"
        "    #[cfg(target_os = \"linux\")]\n"
        "    map02_start_cpal_reporter(sink);\n\n"
        "    std::thread_local! {",
        "reporter startup after host sink publication"
    )
    return runner


def patch_kernel(original: str) -> str:
    if "MAP02_AOUT_APPENDS" in original:
        raise ValueError("Kernel instrumentation already installed")
    at="const MAX_REGISTERED_BUFFERS: usize = 4;"
    globals="""// Stage274 experimental signal counters: no guest pointer or PCM is logged.
pub static MAP02_AOUT_APPENDS: std::sync::atomic::AtomicU64 =
    std::sync::atomic::AtomicU64::new(0);
pub static MAP02_AOUT_PUSHED_FRAMES: std::sync::atomic::AtomicU64 =
    std::sync::atomic::AtomicU64::new(0);
pub static MAP02_AOUT_RELEASED: std::sync::atomic::AtomicU64 =
    std::sync::atomic::AtomicU64::new(0);

"""
    kernel=once(original,at,globals+at,"AudioOut metrics")
    kernel=once(
        kernel,
        "        state.released.push_back(buffer.buffer.tag);\n        released += 1;",
        "        state.released.push_back(buffer.buffer.tag);\n"
        "        MAP02_AOUT_RELEASED.fetch_add(1, std::sync::atomic::Ordering::Relaxed);\n"
        "        released += 1;",
        "actual buffer-release counter"
    )
    kernel=once(
        kernel,
        "        pushed_frames += accepted_samples / 2;",
        "        pushed_frames += accepted_samples / 2;\n"
        "        MAP02_AOUT_PUSHED_FRAMES.fetch_add(\n"
        "            (accepted_samples / 2) as u64, std::sync::atomic::Ordering::Relaxed);",
        "accepted audio_out PCM frame counter"
    )
    kernel=once(
        kernel,
        "        state.appended.push_back(AudioOutBufferState {\n"
        "            tag: client_ptr,\n"
        "            samples,\n"
        "            frames,\n"
        "        });",
        "        state.appended.push_back(AudioOutBufferState {\n"
        "            tag: client_ptr,\n"
        "            samples,\n"
        "            frames,\n"
        "        });\n"
        "        MAP02_AOUT_APPENDS.fetch_add(1, std::sync::atomic::Ordering::Relaxed);",
        "accepted guest AudioOut append counter"
    )
    return kernel


def patch_manifest(source: str) -> str:
    # A direct libc dependency is gated to Linux: no difference to any
    # production game, other platforms or historical NeXium executables.
    needle="[target.'cfg(not(target_vendor = \"sony\"))'.dependencies]\ncpal = \"0.18\""
    return once(source,needle,needle+
        "\n\n[target.'cfg(target_os = \"linux\")'.dependencies]\nlibc = \"0.2\"",
        "nexium-runner Linux libc dependency")


def apply(repo: Path, expected_head: str=UPSTREAM) -> dict:
    if expected_head!=UPSTREAM:
        raise ValueError("Refusing to instrument an unknown upstream source revision")
    paths=[RUNNER,KERNEL,"nexium-runner/Cargo.toml"]
    data={p:(repo/p).read_bytes() for p in paths}
    sha={p:hashlib.sha256(blob).hexdigest() for p,blob in data.items()}
    def normalize(blob: bytes) -> str:
        return blob.decode("utf-8").replace("\r\n","\n")
    runner=patch_runner(normalize(data[RUNNER]))
    kernel=patch_kernel(normalize(data[KERNEL]))
    manifest=patch_manifest(normalize(data["nexium-runner/Cargo.toml"]))
    raw_changes={RUNNER:runner,KERNEL:kernel,"nexium-runner/Cargo.toml":manifest}
    # Preserve each upstream file's original newline style. Otherwise
    # upstream CRLF Rust files would appear to be rewritten wholesale.
    changes={
        path: updated.replace("\n","\r\n") if b"\r\n" in data[path] else updated
        for path,updated in raw_changes.items()
    }
    # No partial upstream edits if any anchor fails.
    for path,updated in changes.items():
        (repo/path).write_text(updated,encoding="utf-8")
    return {
        "schema":SCHEMA,
        "upstream_git_sha_expected":expected_head,
        "compiled_instrumented_emulator_verified":False,
        "historical_nightly_build_source_sha_verified":False,
        "research_only":True,
        "host_callback_only_relaxed_atomic":True,
        "host_reporter_interval_ms":200,
        "host_linux_monotonic_clock":"CLOCK_MONOTONIC",
        "guest_service_accepted_append_count_added":True,
        "accepted_audioout_frames_counter_added":True,
        "guest_released_buffers_counter_added":True,
        "source_files":[
            {"path":path,"sha256_before":sha[path],
             "sha256_after":hashlib.sha256(changes[path].encode()).hexdigest()}
            for path in paths
        ],
        "raw_game_audio_or_rom_content_collected":False,
        "actual_nintendo_switch_dac_verified":False,
        "guest_audout_permanent_deadlock_proven":False
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream",required=True,type=Path)
    parser.add_argument("--manifest",required=True,type=Path)
    options=parser.parse_args()
    root=options.upstream
    actual=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],
                                   text=True).strip()
    if actual!=UPSTREAM:
        raise SystemExit(f"UNVERIFIED upstream revision: {actual}")
    if subprocess.check_output(["git","-C",str(root),"status","--porcelain"],
                               text=True).strip():
        raise SystemExit("Refuse to overlay dirty upstream tree")
    try:
        receipt=apply(root,actual)
    except (OSError,UnicodeError,ValueError) as err:
        raise SystemExit(f"UNVERIFIED source anchors: {err}")
    options.manifest.parent.mkdir(parents=True,exist_ok=True)
    options.manifest.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps(receipt,indent=2,sort_keys=True))

if __name__=="__main__":
    main()

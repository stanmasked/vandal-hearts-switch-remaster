"""ROM-free source-patch tests for immutable upstream NeXium CPAL/AudioOut.

These tests do NOT claim the new emulator is compiled or replaces nightly.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from prepare_map02_nexium_cpal_overlay import (
    UPSTREAM, RUNNER, KERNEL, apply, patch_runner, patch_kernel,
    patch_manifest
)

RUNNER_SOURCE="""use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
const RENDER_SR: u32 = 48_000;
struct HostAudioSink;
fn sink() {
    let stream_result = match sample_format {
        SampleFormat::F32 => {
            device.build_output_stream(
                config.clone(),
                move |out: &mut [f32], _info: &cpal::OutputCallbackInfo| {
                    drain_stereo_to(
                        &mut consumer,
                        out,
                        dev_ch,
                        resample_ratio,
                        &consumed_cb,
                        &vol,
                        &audio_out_cb,
                        &underrun_cb,
                        &mut prebuf,
                    );
                },
                err_cb,
                None,
            )
        }
        SampleFormat::I16 => {
            device.build_output_stream(
                config.clone(),
                move |out: &mut [i16], _info: &cpal::OutputCallbackInfo| {
                    drain_stereo_to_i16(
                        &mut consumer,
                        out,
                        dev_ch,
                        resample_ratio,
                        &consumed_cb,
                        &vol,
                        &audio_out_cb,
                        &underrun_cb,
                        &mut prebuf,
                    );
                },
                err_cb,
                None,
            )
        }
        other => { return; }
    };
    let sink_dyn: Arc<dyn HostPcmSink> = sink;
    set_host_audio_sink(sink_dyn);

    std::thread_local! {
        static AUDIO_STREAM: std::cell::RefCell<Option<cpal::Stream>> =
            std::cell::RefCell::new(None);
    }
}
"""
KERNEL_SOURCE="""use std::time::Instant;
const MAX_REGISTERED_BUFFERS: usize = 4;
fn release_completed_buffers() {
        let buffer = state.registered.pop_front().unwrap();
        state.released.push_back(buffer.buffer.tag);
        released += 1;
}
fn pump_registered_buffers() {
        pushed_frames += accepted_samples / 2;
}
fn append_audio_out_buffer() {
        state.appended.push_back(AudioOutBufferState {
            tag: client_ptr,
            samples,
            frames,
        });
}
"""
MANIFEST_SOURCE="""[package]
name = "nexium-runner"

[target.'cfg(not(target_vendor = "sony"))'.dependencies]
cpal = "0.18"
"""


class OverlayTests(unittest.TestCase):
    def test_two_cpal_formats_have_entry_and_exit_counts_only_inside_callbacks(self):
        patched=patch_runner(RUNNER_SOURCE)
        self.assertEqual(patched.count("MAP02_CPAL_ENTER.fetch_add"),2)
        self.assertEqual(patched.count("MAP02_CPAL_RETURN.fetch_add"),2)
        self.assertEqual(patched.count("MAP02_CPAL_FRAMES.fetch_add"),2)
        self.assertEqual(patched.count("move |out: &mut [f32]"),1)
        self.assertEqual(patched.count("move |out: &mut [i16]"),1)
        self.assertIn("map02_start_cpal_reporter(sink);",patched)
        self.assertEqual(patched.count("map02_start_cpal_reporter(sink);"),1)
        self.assertIn("std::thread_local!",patched)
        self.assertIn("CLOCK_MONOTONIC",patched)
        self.assertIn("VH_MAP02_CPAL_TRACE_PATH",patched)
        self.assertIn("200)",patched)
        self.assertNotIn("println!",patched.split("move |out: &mut [f32]")[1]
                              .split("other =>")[0])

    def test_kernel_counts_real_append_push_release_sites_only(self):
        patched=patch_kernel(KERNEL_SOURCE)
        self.assertEqual(patched.count("MAP02_AOUT_APPENDS.fetch_add"),1)
        self.assertEqual(patched.count("MAP02_AOUT_RELEASED.fetch_add"),1)
        self.assertEqual(patched.count("MAP02_AOUT_PUSHED_FRAMES.fetch_add"),1)
        self.assertNotIn("log::info!",patched)

    def test_linux_only_libc_dependency(self):
        result=patch_manifest(MANIFEST_SOURCE)
        self.assertEqual(result.count('libc = "0.2"'),1)
        self.assertIn("""[target.'cfg(target_os = "linux")'.dependencies]""",result)

    def test_missing_cpal_return_anchor_fails_closed(self):
        source=RUNNER_SOURCE.replace("                        &mut prebuf,\n","",1)
        with self.assertRaisesRegex(ValueError,"F32"):
            patch_runner(source)

    def test_double_application_rejected(self):
        with self.assertRaisesRegex(ValueError,"already installed"):
            patch_runner(patch_runner(RUNNER_SOURCE))
        with self.assertRaisesRegex(ValueError,"already installed"):
            patch_kernel(patch_kernel(KERNEL_SOURCE))

    def test_failure_is_atomic_and_does_not_half_patch_repo(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for file,content in [
                (RUNNER,RUNNER_SOURCE),
                (KERNEL,KERNEL_SOURCE.replace("        pushed_frames += accepted_samples / 2;","")),
                ("nexium-runner/Cargo.toml",MANIFEST_SOURCE),
            ]:
                p=root/file
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(content)
            raw=(root/RUNNER).read_bytes()
            with self.assertRaisesRegex(ValueError,"accepted audio_out"):
                apply(root,UPSTREAM)
            self.assertEqual((root/RUNNER).read_bytes(),raw)

    def test_receipt_pins_source_and_preserves_crlf(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for file,content in [
                (RUNNER,RUNNER_SOURCE),
                (KERNEL,KERNEL_SOURCE),
                ("nexium-runner/Cargo.toml",MANIFEST_SOURCE)
            ]:
                p=root/file
                p.parent.mkdir(parents=True,exist_ok=True)
                original=content.replace("\n","\r\n") if file==KERNEL else content
                p.write_bytes(original.encode())
            receipt=apply(root,UPSTREAM)
            self.assertEqual(receipt["schema"],"vh-map02-nexium-cpal-source-overlay/v1")
            self.assertEqual(receipt["upstream_git_sha_expected"],UPSTREAM)
            self.assertEqual(len(receipt["source_files"]),3)
            self.assertFalse(receipt["compiled_instrumented_emulator_verified"])
            self.assertFalse(receipt["historical_nightly_build_source_sha_verified"])
            kernel_raw=(root/KERNEL).read_bytes()
            self.assertIn(b"\r\n",kernel_raw)
            self.assertNotIn(b"\n",kernel_raw.replace(b"\r\n",b""))
            self.assertIn(b"MAP02_AOUT_RELEASED.fetch_add",kernel_raw)

    def test_foreign_upstream_revision_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"unknown upstream"):
                apply(Path(d),"a"*40)


if __name__=="__main__":
    unittest.main()

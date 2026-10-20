"""Stage286 ROM-free fail-closed source overlay tests.

These tests do not run NeXium, a game NRO or CPAL; separate native Cargo
compilation and future guest experiments remain mandatory.
"""
import tempfile
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))
from test_prepare_map02_nexium_cpal_overlay import RUNNER_SOURCE
from prepare_map02_nexium_cpal_overlay import patch_runner as patch_stage274, UPSTREAM
from prepare_map02_nexium_cpal_lifecycle_overlay import (
    patch_runner,apply,LIFECYCLE,SCHEMA,COUNTERS
)


class LifecycleSourceTests(unittest.TestCase):
    def setUp(self):
        # Include genuine Stage274 callback anchor structure as well as the
        # exact NeXium stream constructor/play/status statements. The old
        # Stage274 fixture ended before actual lifecycle code existed.
        fixture=RUNNER_SOURCE.replace(
            "fn sink() {",
            """fn init_host_audio_on_thread(preferred_device: Option<&str>, initial_volume: f32) {
    let Some(device) = resolve_output_device(preferred_device) else {
        log::warn!("Audio output disabled: no output device available");
        return;
    };
    let (config, sample_format) = match pick_config(&device) {
        Ok(c) => c,
        Err(e) => {
            log::warn!("Audio output disabled: {}", e);
            return;
        }
    };
    let err_cb = |e| log::error!("cpal stream error: {}", e);""")
        fixture=fixture.replace(
            "    let sink_dyn: Arc<dyn HostPcmSink> = sink;",
            """    let stream = match stream_result {
        Ok(s) => s,
        Err(e) => {
            log::warn!("Audio output disabled: build_output_stream: {}", e);
            return;
        }
    };
    if let Err(e) = stream.play() {
        log::warn!("Audio output disabled: stream.play: {}", e);
        return;
    }
    let sink_dyn: Arc<dyn HostPcmSink> = sink;""")
        fixture=fixture.replace(
            "    }\n}",
            "    }\n    AUDIO_STREAM.with(|s| *s.borrow_mut() = Some(stream));\n}")
        self.stage274=patch_stage274(fixture)

    def test_collector_preserves_two_old_rt_callback_count_sites(self):
        updated=patch_runner(self.stage274)
        self.assertEqual(updated.count("MAP02_CPAL_ENTER.fetch_add"),2)
        self.assertEqual(updated.count("MAP02_CPAL_RETURN.fetch_add"),2)
        self.assertEqual(updated.count("MAP02_CPAL_FRAMES.fetch_add"),2)
        self.assertIn("map02_start_cpal_reporter(sink);",updated)
        self.assertIn("VH_MAP02_CPAL_LIFECYCLE_PATH",updated)
        self.assertIn("map02-cpal-lifecycle",updated)
        self.assertNotIn("VH_MAP02_CPAL_TRACE_PATH = ",updated)

    def test_cpal_error_callback_gains_only_one_relaxed_atomic_operation(self):
        updated=patch_runner(self.stage274)
        section=updated.split("let err_cb = |e| {",1)[1].split("};",1)[0]
        self.assertEqual(section.count("MAP02_LIFE_ERROR_CALLBACK.fetch_add"),1)
        self.assertNotIn("map02_life_now_ns",section)
        self.assertNotIn("writeln!",section)
        self.assertNotIn("OpenOptions",section)
        self.assertIn('log::error!("cpal stream error: {}", e);',section)

    def test_stream_build_play_and_drop_are_counted(self):
        s=patch_runner(self.stage274)
        self.assertIn("MAP02_LIFE_BUILD_ATTEMPT.fetch_add",s)
        self.assertIn("MAP02_LIFE_BUILD_FAILED.fetch_add",s)
        self.assertIn("MAP02_LIFE_BUILD_OK.fetch_add",s)
        self.assertIn("MAP02_LIFE_PLAY_OK.fetch_add",s)
        self.assertIn("MAP02_LIFE_PLAY_FAILED.fetch_add",s)
        self.assertIn("MAP02_LIFE_STREAM_DROPPED.fetch_add",s)
        self.assertIn("impl Drop for Map02HeldStream",s)
        self.assertIn("Some(held_stream)",s)
        self.assertIn("std::cell::RefCell<Option<Map02HeldStream>>",s)
        self.assertEqual(s.count("MAP02_LIFE_ERROR_CALLBACK.fetch_add"),1)

    def test_reporter_is_separate_and_can_only_use_absolute_optin_path(self):
        s=patch_runner(self.stage274)
        self.assertEqual(s.count('let Ok(path) = std::env::var("VH_MAP02_CPAL_LIFECYCLE_PATH")'),1)
        self.assertIn("Path::new(&path).is_absolute()",s)
        self.assertIn("compare_exchange(",s)
        self.assertIn('name("map02-cpal-lifecycle".into())',s)
        self.assertIn("Duration::from_millis(200)",s)
        self.assertNotIn("raw_pcm",s)

    def test_build_and_play_monotonic_timestamp_only_outside_callback(self):
        s=patch_runner(self.stage274)
        self.assertIn("MAP02_LIFE_BUILD_START_NS.store(map02_life_now_ns()",s)
        self.assertIn("MAP02_LIFE_PLAY_OK_NS.store(map02_life_now_ns()",s)
        self.assertIn("MAP02_LIFE_DROP_NS.store(map02_life_now_ns()",s)
        self.assertNotIn("map02_life_now_ns()",s.split("let err_cb = |e| {",1)[1].split("};",1)[0])

    def test_missing_exact_stage274_overlay_rejected(self):
        with self.assertRaisesRegex(ValueError,"Stage274"):
            patch_runner(RUNNER_SOURCE)

    def test_repeat_overlay_rejected(self):
        twice=patch_runner(self.stage274)
        with self.assertRaisesRegex(ValueError,"already installed"):
            patch_runner(twice)

    def test_missing_stream_play_anchor_is_rejected(self):
        invalid=self.stage274.replace("    if let Err(e) = stream.play() {","    stream.play().ok();")
        with self.assertRaisesRegex(ValueError,"stream.play result"):
            patch_runner(invalid)

    def test_crlf_source_retained_and_manifest_has_nonruntime_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            p=root/"nexium-runner/src/audio.rs"
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(self.stage274.replace("\n","\r\n").encode())
            r=apply(root,UPSTREAM)
            self.assertEqual(r["schema"],SCHEMA)
            self.assertTrue(r["stage274_overlay_required"])
            self.assertFalse(r["new_compiled_executable_proven"])
            self.assertFalse(r["guest_audio_21ms_root_cause_proven"])
            self.assertEqual(r["error_callback_new_operations"],"relaxed_atomic_increment_only")
            self.assertIn(b"\r\n",p.read_bytes())
            self.assertNotIn(b"\n",p.read_bytes().replace(b"\r\n",b""))

    def test_bad_upstream_version_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"Unknown upstream"):
                apply(Path(temp),"0"*40)

    def test_explicit_lifecycle_counters_and_no_game_data(self):
        self.assertEqual(len(COUNTERS),10)
        self.assertIn("ERROR_CALLBACK",COUNTERS)
        self.assertIn("STREAM_DROPPED",COUNTERS)
        self.assertNotIn("GUEST_PCM",LIFECYCLE)


if __name__=="__main__":
    unittest.main()

"""Source-only Stage298 host lifecycle instrumentation safety and exact-anchor tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from patch_map02_cpal_stream_timestamps_stage298 import patch

def source():
    return '''use std::sync::atomic::{AtomicU64,Ordering};
static MAP02_CPAL_ERROR_COUNT: AtomicU64 = AtomicU64::new(0);
static MAP02_CPAL_LIFECYCLE: AtomicU64 = AtomicU64::new(0);
static MAP02_CPAL_ENTER: AtomicU64 = AtomicU64::new(0);
static MAP02_CPAL_RETURN: AtomicU64 = AtomicU64::new(0);
fn map02_start_cpal_reporter() {
    let _ = std::thread::Builder::new().name("map02-cpal-counts".into()).spawn(move || {
            if let Ok(mut output) = std::fs::OpenOptions::new()
                .create(true).append(true).open(&path)
            {
                let _ = writeln!(output, "L,{nanos},{lifecycle},{errors},{calls},{returns},{frames},{consumed},{appends},{pushed},{released}");
            }
    });
}
fn initialize_stream() {
    MAP02_CPAL_LIFECYCLE.store(1, Ordering::Relaxed);
    let stream = match stream_result {
        Ok(s) => {
            MAP02_CPAL_LIFECYCLE.store(2, Ordering::Relaxed);
            s
        },
        Err(e) => {
            MAP02_CPAL_LIFECYCLE.store(4, Ordering::Relaxed);
        }
    };
    if let Err(e) = stream.play() {
        MAP02_CPAL_LIFECYCLE.store(5, Ordering::Relaxed);
    }
    MAP02_CPAL_LIFECYCLE.store(3, Ordering::Relaxed);
    MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);
    MAP02_CPAL_RETURN.fetch_add(1, Ordering::Relaxed);
    MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);
    MAP02_CPAL_RETURN.fetch_add(1, Ordering::Relaxed);
    std::thread_local! {
        static AUDIO_STREAM: std::cell::RefCell<Option<cpal::Stream>> =
            std::cell::RefCell::new(None);
    }
    AUDIO_STREAM.with(|s| *s.borrow_mut() = Some(stream));
}'''

class Stage298SourceTests(unittest.TestCase):
    def test_complete_host_only_instrumentation(self):
        changed=patch(source())
        self.assertIn('VH_MAP02_CPAL_LIFETIME_PATH',changed)
        self.assertIn('P,{nanos},{build_begin},{build_ok}',changed)
        self.assertEqual(changed.count('writeln!(output, "L,{nanos}'),1)
        self.assertEqual(changed.count('writeln!(second,'),1)
        for label in ["BUILD_BEGIN","BUILD_OK","BUILD_FAIL",
                      "PLAY_BEGIN","PLAY_OK","PLAY_FAIL","DROP"]:
            self.assertIn("MAP02_S298_"+label+"_NS",changed)
        self.assertIn("impl Drop for Map02S298RetainedStream",changed)
        self.assertIn("Option<Map02S298StreamSlot>",changed)
        self.assertIn("let stream = Map02S298RetainedStream(stream);",changed)
        self.assertIn('#[cfg(target_os = "linux")]',changed)
        self.assertNotIn("stream.pause()",changed)

    def test_no_real_time_callback_modification(self):
        changed=patch(source())
        for phrase in [
            "MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);",
            "MAP02_CPAL_RETURN.fetch_add(1, Ordering::Relaxed);",
        ]:
            self.assertEqual(source().count(phrase),2)
            self.assertEqual(changed.count(phrase),2)
        self.assertEqual(changed.count("clock_gettime"),1)

    def test_double_patch_is_refused(self):
        with self.assertRaisesRegex(ValueError,"already installed"):
            patch(patch(source()))

    def test_missing_existing_reporter_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"Missing required Stage274/286"):
            patch(source().replace("map02_start_cpal_reporter","renamed_reporter"))

    def test_ambiguous_play_call_anchor_rejected(self):
        src=source().replace('    if let Err(e) = stream.play() {',
                             '    if let Err(e) = stream.play() {\n    if let Err(e) = stream.play() {')
        with self.assertRaisesRegex(ValueError,"Play call begin"):
            patch(src)

    def test_missing_raii_storage_rejected(self):
        src=source().replace("Option<cpal::Stream>","Option<OtherStream>")
        with self.assertRaisesRegex(ValueError,"retained-stream drop"):
            patch(src)

    def test_missing_l_reporter_rejected(self):
        with self.assertRaisesRegex(ValueError,"Separate P reporter"):
            patch(source().replace('L,{nanos}','OTHER,{nanos}'))

    def test_existing_pause_call_is_not_declared_absent(self):
        with self.assertRaisesRegex(ValueError,"cannot claim no pause"):
            patch(source()+"\nstream.pause();\n")

if __name__=="__main__":
    unittest.main()

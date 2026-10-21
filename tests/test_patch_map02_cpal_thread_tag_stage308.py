"""Stage308 synthetic only: anchored Rust callback patch and safety restrictions."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from patch_map02_cpal_thread_tag_stage308 import patch

SOURCE = '''
use std::sync::atomic::{AtomicU64, Ordering};
static MAP02_S298_DROP_NS: AtomicU64 = AtomicU64::new(0);
static MAP02_S298_BUILD_BEGIN_NS: AtomicU64 = AtomicU64::new(0);
static MAP02_S298_PLAY_OK_NS: AtomicU64 = AtomicU64::new(0);
fn map02_start_cpal_reporter() {
    let _ = writeln!(output, "L,{nanos},{lifecycle},{errors}");
    let _ = writeln!(second, "P,{nanos}");
}
fn prepare_stream() {
    MAP02_CPAL_LIFECYCLE.store(1, Ordering::Relaxed);
}
fn f32_callback() {
    MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);
    MAP02_CPAL_RETURN.fetch_add(1, Ordering::Relaxed);
}
fn i16_callback() {
    MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);
    MAP02_CPAL_RETURN.fetch_add(1, Ordering::Relaxed);
}
'''

class SourceOverlayTest(unittest.TestCase):
    def test_two_callbacks_same_hook(self):
        code=patch(SOURCE)
        self.assertEqual(code.count("map02_s308_callback_tag_only();"),2)
        self.assertEqual(code.count("map02_s308_prepare_callback_hook();"),1)
        self.assertEqual(code.count("MAP02_CPAL_ENTER.fetch_add("),2)
        self.assertEqual(code.count("MAP02_CPAL_RETURN.fetch_add("),2)
        self.assertIn("libc::dlsym(libc::RTLD_DEFAULT",code)
        self.assertIn("VH_MAP02_STAGE308_CALLBACK_TAG",code)
        self.assertIn("vh_map02_stage308_cpal_callback_mark",code)

    def test_only_one_prepare_pointer_resolution(self):
        code=patch(SOURCE)
        self.assertEqual(code.count("std::env::var("),1)
        self.assertEqual(code.count("libc::dlsym("),1)
        self.assertEqual(code.count("map02_s308_callback_tag_only();"),2)

    def test_reject_second_overlay(self):
        with self.assertRaisesRegex(ValueError,"already present"):
            patch(patch(SOURCE))

    def test_reject_missing_callbacks(self):
        with self.assertRaisesRegex(ValueError,"both exact"):
            patch(SOURCE.replace("MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);","",1))

    def test_reject_three_callbacks(self):
        with self.assertRaisesRegex(ValueError,"both exact"):
            patch(SOURCE.replace("fn i16_callback() {",'''fn duplicate_callback() {
    MAP02_CPAL_ENTER.fetch_add(1, Ordering::Relaxed);
}
fn i16_callback() {'''))

    def test_reject_source_missing_reporter(self):
        with self.assertRaisesRegex(ValueError,"Missing"):
            patch(SOURCE.replace("map02_start_cpal_reporter","renamed_callback_reporter"))

    def test_reject_source_with_pause(self):
        with self.assertRaisesRegex(ValueError,"stream.pause"):
            patch(SOURCE+"stream.pause();")

    def test_reject_ambiguous_prepare(self):
        with self.assertRaisesRegex(ValueError,"Ambiguous"):
            patch(SOURCE.replace("    MAP02_CPAL_LIFECYCLE.store(1, Ordering::Relaxed);",
                   "    MAP02_CPAL_LIFECYCLE.store(1, Ordering::Relaxed);\n"
                   "    MAP02_CPAL_LIFECYCLE.store(1, Ordering::Relaxed);"))

    def test_no_callback_timing_claim(self):
        code=patch(SOURCE)
        body=code.split("fn map02_s308_callback_tag_only() {")[1].split("\n}")[0]
        for forbidden in ("clock_gettime(", "log::", "println!", "std::fs", "gettid", "std::thread::current"):
            self.assertNotIn(forbidden,body)

if __name__=="__main__":unittest.main()

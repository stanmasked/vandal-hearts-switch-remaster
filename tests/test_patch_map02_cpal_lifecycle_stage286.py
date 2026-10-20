"""ROM-free fail-closed synthetic checks for Stage286 source patch."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from patch_map02_cpal_lifecycle_stage286 import patch


def baseline():
    return """static MAP02_CPAL_FRAMES: AtomicU64 = AtomicU64::new(0);
fn map02_start_cpal_reporter() {
            let calls = MAP02_CPAL_ENTER.load(Ordering::Relaxed);
            let _ = writeln!(output, "T,{nanos},{calls},{returns},{frames},{consumed},{appends},{pushed},{released}");
}
let err_cb = |e| log::error!("cpal stream error: {}", e);
    let stream = match stream_result {
        Ok(s) => s,
        Err(e) => {
    if let Err(e) = stream.play() {
        log::warn!("Audio output disabled: stream.play: {}", e);
    let device_name = device
        .description()
"""


class LifecyclePatchTests(unittest.TestCase):
    def test_valid_anchor_patch_all_events_and_bounded_reporter(self):
        s=patch(baseline())
        self.assertIn("MAP02_CPAL_LIFECYCLE",s)
        self.assertIn("MAP02_CPAL_ERROR_COUNT.fetch_add",s)
        self.assertIn('L,{nanos},{lifecycle},{errors}',s)
        self.assertIn("MAP02_CPAL_LIFECYCLE.store(1",s)
        self.assertIn("MAP02_CPAL_LIFECYCLE.store(2",s)
        self.assertIn("MAP02_CPAL_LIFECYCLE.store(3",s)
        self.assertIn("MAP02_CPAL_LIFECYCLE.store(4",s)
        self.assertIn("MAP02_CPAL_LIFECYCLE.store(5",s)
        self.assertNotIn("std::fs::write",s)
    def test_double_patch_refused(self):
        with self.assertRaisesRegex(ValueError,"already"):
            patch(patch(baseline()))
    def test_missing_stage274_refused(self):
        with self.assertRaisesRegex(ValueError,"Stage274"):
            patch(baseline().replace("MAP02_CPAL_ENTER","NO_COUNTER"))
    def test_duplicate_reporter_anchor_refused(self):
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            patch(baseline().replace("let calls = MAP02_CPAL_ENTER.load(Ordering::Relaxed);",
                "let calls = MAP02_CPAL_ENTER.load(Ordering::Relaxed);\n"
                "let calls = MAP02_CPAL_ENTER.load(Ordering::Relaxed);"))
    def test_missing_play_failure_anchor_refused(self):
        with self.assertRaisesRegex(ValueError,"anchor"):
            patch(baseline().replace('stream.play()','not_playing()'))

if __name__=="__main__":
    unittest.main()

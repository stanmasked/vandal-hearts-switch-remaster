"""Stage341 source NRO monitor vs derived PCM-quality provenance controls."""
from __future__ import annotations
import json,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"));sys.path.insert(0,str(ROOT/"tests"))
from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage336_capture_build_binding import read_json,verify_monitor_quality
from test_audit_nexium_stage336_capture_build_binding import SameRunSourceToNroBindingTests

class OriginalMonitorAndQualityTests(unittest.TestCase):
    def setUp(self):
        base=SameRunSourceToNroBindingTests();base.setUp()
        self.monitor=dict(base.monitor,schema="vh-nexium-pcm-monitor/v1")
        self.quality=dict(schema="vh-nexium-pcm-quality/v1",
            hardware_status="HARDWARE NOT TESTED",format="s16le stereo 48000 Hz",
            bytes=1024,pcm_sha256="d"*64,audible_music_confirmed=False,
            original_soundtrack_confirmed=False)
    def check_bad(self,monitor=None,quality=None):
        with self.assertRaises(ExitTimelineError):
            verify_monitor_quality(self.monitor if monitor is None else monitor,
                                   self.quality if quality is None else quality)
    def test_valid_two_distinct_original_reports(self):
        verify_monitor_quality(self.monitor,self.quality)
    def test_pcm_quality_lacks_NRO_source_pin(self):
        self.assertIn("source_nro_sha256",self.monitor)
        self.assertNotIn("source_nro_sha256",self.quality)
    def test_wrong_pcm_byte_count(self):
        self.check_bad(quality=dict(self.quality,bytes=1028))
    def test_capture_schema_required(self):
        self.check_bad(monitor=dict(self.monitor,schema="other"))
    def test_quality_schema_required(self):
        self.check_bad(quality=dict(self.quality,schema="other"))
    def test_original_soundtrack_false_claim_required(self):
        self.check_bad(quality=dict(self.quality,original_soundtrack_confirmed=True))
    def test_quality_pcm_digest_well_formed(self):
        self.check_bad(quality=dict(self.quality,pcm_sha256="bad"))
    def test_stereo_frame_boundaries(self):
        self.check_bad(monitor=dict(self.monitor,raw_bytes=1025),
                       quality=dict(self.quality,bytes=1025))
    def test_read_original_capture_and_quality_files_separately(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            (root/"pcm-monitor-report.json").write_text(json.dumps(self.monitor))
            (root/"pcm-quality-report.json").write_text(json.dumps(self.quality))
            verify_monitor_quality(read_json(root/"pcm-monitor-report.json"),
                                   read_json(root/"pcm-quality-report.json"))

if __name__=="__main__": unittest.main()

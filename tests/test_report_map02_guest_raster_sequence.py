"""ROM-free host-only tests of calibrated game raster screenshot comparisons."""
import importlib.util
import sys
import unittest
from pathlib import Path
from PIL import Image

p=Path(__file__).resolve().parents[1]/"tools/report_map02_guest_raster_sequence.py"
spec=importlib.util.spec_from_file_location("map02_raster",p)
raster=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=raster
spec.loader.exec_module(raster)

def blank():
    return Image.new("RGB",(1280,720),(0,0,0))

class GuestRasterTests(unittest.TestCase):
    def test_guest_region_change_before_final_but_not_after(self):
        before=blank()
        final=blank()
        final.putpixel((300,200),(5,7,9))
        late=final.copy()
        report=raster.audit(before,final,late)
        self.assertEqual(report["before_to_final"]["changed_rgb_pixels"],1)
        self.assertEqual(report["final_to_late"]["changed_rgb_pixels"],0)
        self.assertEqual(report["before_to_final"]["diff_bbox_within_roi"],
                         [50,40,51,41])
        self.assertFalse(report["audout_call_deadlock_proven"])
        self.assertFalse(report["actual_guest_audio_thread_progress_proven"])
        self.assertFalse(report["neXium_guest_optical_receipt_verified"])

    def test_external_emulator_chrome_does_not_count(self):
        before=blank()
        final=blank()
        final.putpixel((30,90),(255,0,255))
        r=raster.audit(before,final,final)
        self.assertEqual(r["before_to_final"]["changed_rgb_pixels"],0)
        self.assertEqual(r["before_roi_rgb_sha256"],r["final_roi_rgb_sha256"])

    def test_different_late_game_frame_is_detected(self):
        before=blank();final=blank();late=blank()
        late.putpixel((1150,600),(11,12,13))
        r=raster.audit(before,final,late)
        self.assertEqual(r["final_to_late"]["changed_rgb_pixels"],1)

    def test_invalid_dimensions_are_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError,"1280x720"):
            raster.audit(Image.new("RGB",(640,480)),blank(),blank())

if __name__=="__main__":
    unittest.main()

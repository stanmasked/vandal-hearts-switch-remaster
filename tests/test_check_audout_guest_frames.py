"""Synthetic regression tests for the NeXium audout *video-only* gate."""
import unittest

from PIL import Image, ImageDraw
from check_audout_guest_frames import inspect_guest_frames


def frame():
    shot = Image.new("RGB", (900, 600), (13, 20, 27))
    draw = ImageDraw.Draw(shot)
    draw.rectangle((95, 100, 800, 510), fill=(26, 44, 80))
    draw.rectangle((140, 135, 500, 200), fill=(236, 240, 250))
    return shot


class AudoutNeXiumVideoOnlyTests(unittest.TestCase):
    def test_realistic_visual_change_is_only_guest_progress(self):
        before = frame()
        after = before.copy()
        ImageDraw.Draw(after).rectangle((200, 310, 350, 330),
                                        fill=(228, 231, 238))
        report = inspect_guest_frames(before, after)
        self.assertEqual(report["guest_framebuffer"], "visibly_changed")
        self.assertGreaterEqual(report["changed_pixels"], 80)
        for name, verdict in report.items():
            if name.endswith("_verified"):
                self.assertIs(verdict, False, name)

    def test_identical_frames_do_not_prove_progress(self):
        before = frame()
        with self.assertRaisesRegex(ValueError, "did not visibly progress"):
            inspect_guest_frames(before, before.copy())

    def test_single_pixel_change_is_insufficient(self):
        before = frame()
        after = before.copy()
        after.putpixel((190, 300), (255, 0, 0))
        with self.assertRaisesRegex(ValueError, "did not visibly progress"):
            inspect_guest_frames(before, after)

    def test_border_only_changes_are_excluded(self):
        before = frame()
        after = before.copy()
        ImageDraw.Draw(after).rectangle((0, 0, 900, 18),
                                        fill=(250, 0, 0))
        with self.assertRaisesRegex(ValueError, "did not visibly progress"):
            inspect_guest_frames(before, after)

    def test_dimension_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "matching dimensions"):
            inspect_guest_frames(frame(), Image.new("RGB", (901, 600)))

    def test_blank_frames_cannot_pass(self):
        before = Image.new("RGB", (900, 600), (0, 0, 0))
        after = before.copy()
        ImageDraw.Draw(after).rectangle((120, 120, 500, 500),
                                        fill=(250, 250, 250))
        with self.assertRaisesRegex(ValueError, "meaningful visual detail"):
            inspect_guest_frames(before, after)

    def test_small_screenshots_rejected(self):
        with self.assertRaisesRegex(ValueError, "small emulator"):
            inspect_guest_frames(
                Image.new("RGB", (320, 240)),
                Image.new("RGB", (320, 240)))


if __name__ == "__main__":
    unittest.main()

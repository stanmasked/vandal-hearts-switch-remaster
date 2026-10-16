"""Synthetic framebuffer assertions only; never imply actual console audio."""
import unittest

from PIL import Image
from check_native_av_screenshot import inspect_images, HERO, AUDIO_OK, AUDIO_FAIL


def make_frames(audio=AUDIO_OK, advance=True):
    before = Image.new("RGB", (1280, 720), (17, 23, 39))
    before.putpixel((452, 296), HERO)
    before.putpixel((108, 104), audio)
    after = before.copy()
    if advance:
        for x in range(105, 148):
            for y in range(610, 624):
                after.putpixel((x, y), HERO)
    return before, after


class NativeAVScreenshotTests(unittest.TestCase):
    def test_valid_heartbeat_and_no_audible_claim(self):
        first, second = make_frames()
        result = inspect_images(first, second)
        self.assertEqual(result["video_framebuffer"], "observed")
        self.assertEqual(result["audout_status"], "initialized")
        self.assertGreater(result["heartbeat_changed_pixels"], 16)
        self.assertFalse(result["audible_audio_verified"])
        self.assertFalse(result["actual_gameplay_verified"])

    def test_emulator_transformed_green_audio_status_is_still_classified(self):
        first, second = make_frames((60, 212, 91))
        result = inspect_images(first, second)
        self.assertEqual(result["audout_status"], "initialized")
        self.assertFalse(result["audible_audio_verified"])

    def test_ambiguous_color_does_not_pass_audio_classification(self):
        first, second = make_frames((100, 130, 110))
        with self.assertRaisesRegex(ValueError, "status marker absent"):
            inspect_images(first, second)

    def test_audio_error_still_allows_visual_diagnostic(self):
        first, second = make_frames(AUDIO_FAIL)
        result = inspect_images(first, second)
        self.assertEqual(result["audout_status"], "unavailable_or_error")
        self.assertFalse(result["audible_audio_verified"])

    def test_static_heartbeat_is_not_false_positive(self):
        first, second = make_frames(advance=False)
        with self.assertRaisesRegex(ValueError, "heartbeat did not advance"):
            inspect_images(first, second)

    def test_no_audio_status_marker_is_rejected(self):
        first, second = make_frames((20, 20, 20))
        with self.assertRaisesRegex(ValueError, "status marker absent"):
            inspect_images(first, second)

    def test_no_hero_is_rejected(self):
        first, second = make_frames()
        first.putpixel((452, 296), (0, 0, 0))
        with self.assertRaisesRegex(ValueError, "hero marker absent"):
            inspect_images(first, second)


if __name__ == "__main__":
    unittest.main()

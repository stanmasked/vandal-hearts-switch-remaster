"""Synthetic framebuffer assertions only; never imply actual console audio."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
from check_native_av_screenshot import inspect_images, HERO, AUDIO_OK, AUDIO_FAIL


def make_frames(audio=AUDIO_OK, advance=True, source=(83, 100, 119),
                pipeline=None, synthetic_switches=None):
    before = Image.new("RGB", (1280, 720), (17, 23, 39))
    before.putpixel((452, 296), HERO)
    before.putpixel((1050, 160), audio)
    before.putpixel((1050, 218), source)
    before.putpixel((1050, 280), (
        pipeline if pipeline is not None
        else AUDIO_FAIL if audio == AUDIO_FAIL else AUDIO_OK
    ))
    if synthetic_switches is not None:
        before.putpixel((1050, 322), synthetic_switches)
    after = before.copy()
    if advance:
        for x in range(105, 148):
            for y in range(588, 601):
                after.putpixel((x, y), HERO)
    return before, after


class NativeAVScreenshotTests(unittest.TestCase):
    def test_valid_heartbeat_and_no_audible_claim(self):
        first, second = make_frames()
        result = inspect_images(first, second)
        self.assertEqual(result["video_framebuffer"], "observed")
        self.assertEqual(result["audout_status"], "initialized")
        self.assertEqual(result["audio_source"], "synthetic")
        self.assertEqual(result["audio_pipeline_progress"], "buffers_returned")
        self.assertFalse(result["user_music_identity_verified"])
        self.assertGreater(result["heartbeat_changed_pixels"], 16)
        self.assertFalse(result["audible_audio_verified"])
        self.assertFalse(result["actual_gameplay_verified"])

    def test_synthetic_scene_switch_marker_requires_completed_transitions(self):
        first, second = make_frames(synthetic_switches=AUDIO_OK)
        report = inspect_images(first, second)
        self.assertEqual(report["synthetic_scene_switches"], "confirmed")
        pending_first, pending_second = make_frames(
            synthetic_switches=(255, 219, 102))
        pending = inspect_images(pending_first, pending_second)
        self.assertEqual(pending["synthetic_scene_switches"], "pending")
        missing_first, missing_second = make_frames()
        self.assertEqual(inspect_images(missing_first, missing_second)[
            "synthetic_scene_switches"], "not_observed")
        with tempfile.TemporaryDirectory() as folder:
            first_path = Path(folder) / "before.png"
            second_path = Path(folder) / "after.png"
            cmd = [sys.executable, "tests/check_native_av_screenshot.py",
                   str(first_path), str(second_path),
                   "--require-synthetic-scene-switches"]
            first.save(first_path)
            second.save(second_path)
            ok = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            pending_first.save(first_path)
            pending_second.save(second_path)
            denied = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("scene-switch marker not confirmed", denied.stderr)

    def test_retry_marker_is_separate_from_clean_resume(self):
        before,after=make_frames(synthetic_switches=AUDIO_OK)
        before.putpixel((1050,545),AUDIO_OK)
        after.putpixel((1050,545),AUDIO_OK)
        before.putpixel((1180,545),AUDIO_OK)
        after.putpixel((1180,545),AUDIO_OK)
        result=inspect_images(before,after)
        self.assertEqual(result["guest_resume_retry_after_fake_open_failure"],"confirmed")
        self.assertFalse(result["audible_audio_verified"])
        with tempfile.TemporaryDirectory() as directory:
            a=Path(directory)/"before.png"
            b=Path(directory)/"after.png"
            cmd=[sys.executable,"tests/check_native_av_screenshot.py",
                 str(a),str(b),"--require-guest-resume-continuation",
                 "--require-guest-resume-retry",
                 "--require-audio-source","synthetic"]
            before.save(a)
            after.save(b)
            accepted=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(accepted.returncode,0,accepted.stderr)
            after.putpixel((1180,545),(255,219,102))
            after.save(b)
            rejected=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn("guest synthetic failed-open retry not confirmed",rejected.stderr)
            before.putpixel((1180,545),AUDIO_FAIL)
            before.save(a)
            rejected=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)

    def test_clean_resume_marker_cannot_fake_failed_open(self):
        before,after=make_frames(synthetic_switches=AUDIO_OK)
        before.putpixel((1050,545),AUDIO_OK)
        after.putpixel((1050,545),AUDIO_OK)
        with tempfile.TemporaryDirectory() as directory:
            a=Path(directory)/"before.png"
            b=Path(directory)/"after.png"
            before.save(a)
            after.save(b)
            rejected=subprocess.run(
                [sys.executable,"tests/check_native_av_screenshot.py",
                 str(a),str(b),"--require-guest-resume-retry"],
                capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn("guest synthetic failed-open retry not confirmed",rejected.stderr)

    def test_guest_x_y_resume_requires_real_pcm_after_each_roundtrip(self):
        before,after=make_frames(synthetic_switches=AUDIO_OK)
        before.putpixel((1050,545),AUDIO_OK)
        after.putpixel((1050,545),AUDIO_OK)
        report=inspect_images(before,after)
        self.assertEqual(report["guest_resume_x_y_pcm_continuation"],"confirmed")
        self.assertTrue(report["guest_resume_is_not_home_event"])
        self.assertFalse(report["audible_audio_verified"])
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/"before.png"
            b=Path(folder)/"after.png"
            cmd=[sys.executable,"tests/check_native_av_screenshot.py",
                 str(a),str(b),"--require-guest-resume-continuation",
                 "--require-audio-source","synthetic",
                 "--require-audout-status","initialized",
                 "--require-audio-pipeline","buffers_returned"]
            before.save(a)
            after.save(b)
            accepted=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(accepted.returncode,0,accepted.stderr)
            after.putpixel((1050,545),(255,219,102))
            after.save(b)
            denied=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(denied.returncode,0)
            self.assertIn("guest X/Y resume PCM continuation",denied.stderr)
            before.putpixel((1050,545),AUDIO_FAIL)
            before.save(a)
            denied=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(denied.returncode,0)

    def test_guest_x_y_resume_does_not_accept_stalled_audout(self):
        before,after=make_frames(pipeline=(255,219,102),
                                 synthetic_switches=AUDIO_OK)
        before.putpixel((1050,545),AUDIO_OK)
        after.putpixel((1050,545),AUDIO_OK)
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/"before.png"
            b=Path(folder)/"after.png"
            before.save(a)
            after.save(b)
            denied=subprocess.run(
                [sys.executable,"tests/check_native_av_screenshot.py",
                 str(a),str(b),"--require-guest-resume-continuation"],
                capture_output=True,text=True)
            self.assertNotEqual(denied.returncode,0)
            self.assertIn("guest X/Y resume PCM continuation",denied.stderr)

    def test_guest_auto_zl_rejected_clock_is_not_transport_failure(self):
        before,after=make_frames(audio=AUDIO_FAIL,pipeline=AUDIO_FAIL)
        before.putpixel((1050,500),AUDIO_OK)
        after.putpixel((1050,500),AUDIO_OK)
        report=inspect_images(before,after)
        self.assertEqual(report["guest_zl_invalid_clock_no_replay"],"confirmed")
        self.assertTrue(report["guest_zl_is_not_physical_button"])
        self.assertEqual(report["audout_status"],"unavailable_or_error")
        self.assertFalse(report["audible_audio_verified"])
        with tempfile.TemporaryDirectory() as folder:
            first_path=Path(folder)/"before.png"
            second_path=Path(folder)/"after.png"
            cmd=[sys.executable,"tests/check_native_av_screenshot.py",
                 str(first_path),str(second_path),
                 "--require-guest-zl-no-replay",
                 "--require-audio-source","synthetic",
                 "--require-audout-status","unavailable_or_error",
                 "--require-audio-pipeline","inactive_or_error"]
            before.save(first_path)
            after.save(second_path)
            passed=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(passed.returncode,0,passed.stderr)
            after.putpixel((1050,500),(255,219,102))
            after.save(second_path)
            rejected=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn("guest ZL invalid-clock no-replay",rejected.stderr)
            before.putpixel((1050,500),AUDIO_FAIL)
            before.save(first_path)
            rejected=subprocess.run(cmd,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)

    def test_guest_zl_no_replay_does_not_accept_still_healthy_service(self):
        before,after=make_frames(audio=AUDIO_OK)
        before.putpixel((1050,500),AUDIO_OK)
        after.putpixel((1050,500),AUDIO_OK)
        with tempfile.TemporaryDirectory() as folder:
            first_path=Path(folder)/"before.png"
            second_path=Path(folder)/"after.png"
            before.save(first_path)
            after.save(second_path)
            rejected=subprocess.run(
                [sys.executable,"tests/check_native_av_screenshot.py",
                 str(first_path),str(second_path),
                 "--require-guest-zl-no-replay"],
                capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn("guest ZL invalid-clock no-replay",rejected.stderr)

    def test_guest_auto_zr_marker_requires_both_verified_frames(self):
        first,second=make_frames()
        first.putpixel((1050,455),AUDIO_OK)
        second.putpixel((1050,455),AUDIO_OK)
        observed=inspect_images(first,second)
        self.assertEqual(observed["guest_zr_recovery"],"confirmed")
        self.assertTrue(observed["guest_zr_is_not_physical_button"])
        self.assertFalse(observed["audible_audio_verified"])
        with tempfile.TemporaryDirectory() as folder:
            first_path=Path(folder)/"before.png"
            second_path=Path(folder)/"after.png"
            args=[sys.executable,"tests/check_native_av_screenshot.py",
                  str(first_path),str(second_path),
                  "--require-guest-zr-recovery"]
            first.save(first_path)
            second.save(second_path)
            success=subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(success.returncode,0,success.stderr)
            second.putpixel((1050,455),(255,219,102))
            second.save(second_path)
            rejected=subprocess.run(args,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn("guest ZR recovery not confirmed",rejected.stderr)
            first.putpixel((1050,455),AUDIO_FAIL)
            first.save(first_path)
            rejected=subprocess.run(args,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)

    def test_guest_auto_zr_missing_marker_does_not_claim_recovery(self):
        first,second=make_frames()
        self.assertNotEqual(inspect_images(first,second)["guest_zr_recovery"],
                            "confirmed")

    def test_user_bank_never_reports_synthetic_switching(self):
        first, second = make_frames(
            source=AUDIO_OK, synthetic_switches=(83, 100, 119))
        report = inspect_images(first, second)
        self.assertEqual(report["audio_source"], "user_files")
        self.assertEqual(report["synthetic_scene_switches"], "not_applicable")
        with tempfile.TemporaryDirectory() as folder:
            first_path = Path(folder) / "before.png"
            second_path = Path(folder) / "after.png"
            cmd = [sys.executable, "tests/check_native_av_screenshot.py",
                   str(first_path), str(second_path),
                   "--require-audio-source", "user_files",
                   "--require-no-synthetic-switches"]
            first.save(first_path)
            second.save(second_path)
            passed = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            # A mistaken green synthetic-switch marker for user-owned
            # music must fail even when audout and the source are green.
            first.putpixel((1050, 322), AUDIO_OK)
            second.putpixel((1050, 322), AUDIO_OK)
            first.save(first_path)
            second.save(second_path)
            denied = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("unexpected synthetic scene-switch indicator",
                          denied.stderr)

    def test_user_source_is_separate_from_audout_initialization(self):
        first, second = make_frames(source=AUDIO_OK)
        report = inspect_images(first, second)
        self.assertEqual(report["audio_source"], "user_files")
        self.assertEqual(report["audout_status"], "initialized")
        self.assertFalse(report["user_music_identity_verified"])
        self.assertFalse(report["audible_audio_verified"])

    def test_invalid_or_partial_source_is_not_synthetic(self):
        first, second = make_frames(audio=AUDIO_FAIL, source=AUDIO_FAIL)
        report = inspect_images(first, second)
        self.assertEqual(report["audio_source"], "invalid_or_partial")
        self.assertEqual(report["audout_status"], "unavailable_or_error")
        self.assertEqual(report["audio_pipeline_progress"], "inactive_or_error")

    def test_unavailable_sd_mount_is_explicit(self):
        first, second = make_frames(audio=AUDIO_FAIL, source=(255, 219, 102))
        report = inspect_images(first, second)
        self.assertEqual(report["audio_source"], "sd_unavailable")
        self.assertFalse(report["audible_audio_verified"])

    def test_unknown_source_marker_fails_closed(self):
        first, second = make_frames(source=(20, 30, 40))
        with self.assertRaisesRegex(ValueError, "audio-source status marker absent"):
            inspect_images(first, second)

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

    def test_initialized_but_stalled_audio_cannot_pass_progress_gate(self):
        first, second = make_frames(pipeline=(255, 219, 102))
        report = inspect_images(first, second)
        self.assertEqual(report["audout_status"], "initialized")
        self.assertEqual(report["audio_pipeline_progress"], "not_yet_confirmed")
        self.assertFalse(report["audible_audio_verified"])

    def test_missing_pipeline_status_never_silently_passes(self):
        first, second = make_frames(pipeline=(20, 30, 40))
        with self.assertRaisesRegex(ValueError, "audio pipeline status marker absent"):
            inspect_images(first, second)

    def test_no_audio_status_marker_is_rejected(self):
        first, second = make_frames((20, 20, 20))
        with self.assertRaisesRegex(ValueError, "status marker absent"):
            inspect_images(first, second)

    def test_cli_requires_exact_audio_origin_and_audout_status(self):
        with tempfile.TemporaryDirectory() as folder:
            before, after = make_frames(audio=AUDIO_FAIL, source=AUDIO_FAIL)
            first_path = Path(folder) / "before.png"
            second_path = Path(folder) / "after.png"
            before.save(first_path)
            after.save(second_path)
            # Standalone script path avoids assumptions about Python package.
            prefix = [sys.executable, "tests/check_native_av_screenshot.py"]
            args = [str(first_path), str(second_path),
                    "--require-audio-source", "invalid_or_partial",
                    "--require-audout-status", "unavailable_or_error",
                    "--require-audio-pipeline", "inactive_or_error"]
            passed = subprocess.run(prefix + args, capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            report = json.loads(passed.stdout)
            self.assertEqual(report["audio_source"], "invalid_or_partial")
            self.assertFalse(report["user_music_identity_verified"])
            self.assertEqual(report["audio_pipeline_progress"], "inactive_or_error")
            denied = subprocess.run(prefix + args[:2] +
                                    ["--require-audio-source", "user_files"],
                                    capture_output=True, text=True)
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("expected audio source", denied.stderr)
            denied_audio = subprocess.run(
                prefix + args[:2] + ["--require-audout-status", "initialized"],
                capture_output=True, text=True
            )
            self.assertNotEqual(denied_audio.returncode, 0)
            self.assertIn("expected audout status", denied_audio.stderr)

    def test_no_hero_is_rejected(self):
        first, second = make_frames()
        first.putpixel((452, 296), (0, 0, 0))
        with self.assertRaisesRegex(ValueError, "hero marker absent"):
            inspect_images(first, second)


if __name__ == "__main__":
    unittest.main()

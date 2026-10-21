"""Synthetic-only private capture-chain checks. No game, movie or real PNGs."""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from tools.verify_map02_private_neutral_capture_chain import (
    parse_plan, verify,
)

LINES = [
    "VH_MAP02_CAPTURE_PLAN_V1",
    "movie_frames=933949",
    "capture_count=3",
    "1,before,3000,held",
    "1,middle,3250,neutral",
    "1,after,3500,held",
]
PICKS = ((1, "before", 3000, "held"),
         (1, "middle", 3250, "neutral"),
         (1, "after", 3500, "held"))


def chunk(kind, content):
    return (struct.pack(">I", len(content)) + kind + content +
            struct.pack(">I", zlib.crc32(kind + content) & 0xffffffff))


def invented_png(value):
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" + bytes((value, 7, 11))))
            + chunk(b"IEND", b""))


def log_row(group, role, index, held):
    return (
        "VH_PRIVATE_NEUTRAL_CAPTURE window=%d role=%s counter=%d "
        "candidate_input=%d expected_buttons=%s png=written "
        "display_offset=unverified" % (group, role, index + 1, index, held)
    )


class CaptureAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.source = self.base / "invented.bk2"
        self.plan = self.base / "plan-private.txt"
        self.log = self.base / "console-private.txt"
        self.images = self.base / "private-png"
        self.images.mkdir()
        self.plan.write_text("\n".join(LINES) + "\n", encoding="ascii")
        self.records = list(PICKS)
        self.write_log()
        for i, (group, role, index, _) in enumerate(PICKS):
            (self.images / ("vh_review_w%02d_%s_counter_%07d.png" %
                            (group, role, index + 1))).write_bytes(
                                invented_png(i + 1))

    def write_log(self, *, complete=True, process_exit=True, exit_success=1):
        data = ["unrelated pretend emulator console text",
                "VH_PRIVATE_NEUTRAL_MOVIE_SOURCE_PREFLIGHT "
                "source=poweron filename=matched core_identity=unverified",
                "VH_PRIVATE_NEUTRAL_RUNTIME_PREFLIGHT "
                "bizhawk_version=2.11 display=NTSC active_core=unverified",
                "VH_PRIVATE_NEUTRAL_START_PREFLIGHT counter=1662 "
                "candidate_input=1661 first_start_pressed=yes "
                "ps1_input_delivery=unverified"]
        data.extend(log_row(*r) for r in self.records)
        if complete:
            data.append("VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE snapshots=%d "
                        "movie_input_only=yes core_input_poll_observed=yes actual_map02=unverified" %
                        len(self.records))
        if process_exit:
            data.append("VH_PRIVATE_BIZHAWK_LOCAL_PROCESS_EXITED exit_success=%d "
                        "original_ps1_authenticated=0 map02_identified=0" % exit_success)
        self.log.write_text("\n".join(data) + "\n", encoding="utf-8")

    def call(self, *, expected=None, **kwargs):
        with patch(
            "tools.verify_map02_private_neutral_capture_chain.plan_lines",
            return_value=LINES if expected is None else expected,
        ) as mock_source:
            result = verify(
                self.source,
                kwargs.get("plan", self.plan),
                kwargs.get("log", self.log),
                kwargs.get("pictures", self.images),
                minimum=240, maximum=1200, after=1800, before=900000,
            )
        self.assertEqual(mock_source.call_args.kwargs, {
            "limit": 1, "minimum": 240, "maximum": 1200,
            "after": 1800, "before": 900000,
        })
        self.assertEqual(mock_source.call_args.args[0], self.source)
        return result

    def test_complete_synthetic_chain_is_only_metadata_integrity(self):
        value = self.call()
        self.assertTrue(value["private_plan_rebuilt_from_direct_bk2"])
        self.assertTrue(value["capture_logs_match_each_planned_input_and_counter"])
        self.assertTrue(value["owner_log_reports_live_first_start_anchor_before_screenshots"])
        self.assertTrue(value["owner_log_reports_poweron_movie_path_match"])
        self.assertTrue(value["owner_log_reports_input_poll_callback"])
        self.assertEqual(value["reported_bizhawk_version"], "2.11")
        self.assertEqual(value["reported_psx_display_standard"], "NTSC")
        self.assertFalse(value["active_octoshock_core_verified"])
        self.assertFalse(value["savestate_free_real_replay_authenticated"])
        self.assertTrue(value["owner_launcher_reports_successful_process_exit"])
        self.assertTrue(value["all_png_crc_zlib_scanlines_pass"])
        self.assertEqual(value["screenshot_count"], 3)
        for name in ("movie_input_to_actual_ps1_delivery_verified",
                     "real_bizhawk_execution_authenticated",
                     "actual_displayed_frame_offset_verified",
                     "image_scene_identity_verified", "map02_frame_identified",
                     "source_native_gpu_vram_verified", "private_input_or_png_published"):
            self.assertFalse(value[name])
        self.assertNotIn(str(self.base), json.dumps(value))

    def test_lua_reports_no_core_input_polls_without_false_authentication(self):
        source = self.log.read_text(encoding="utf-8")
        self.log.write_text(source.replace(
            "core_input_poll_observed=yes",
            "core_input_poll_observed=no",
        ), encoding="utf-8")
        report = self.call()
        self.assertFalse(report["owner_log_reports_input_poll_callback"])
        self.assertFalse(report["movie_input_to_actual_ps1_delivery_verified"])
        self.assertFalse(report["real_bizhawk_execution_authenticated"])

    def test_malformed_core_input_poll_marker_rejected(self):
        source = self.log.read_text(encoding="utf-8")
        self.log.write_text(source.replace(
            "core_input_poll_observed=yes",
            "core_input_poll_observed=maybe",
        ), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "completion"):
            self.call()

    def test_missing_live_runtime_profile_is_rejected(self):
        original = self.log.read_text(encoding="utf-8")
        self.log.write_text("\n".join(
            line for line in original.splitlines()
            if not line.startswith("VH_PRIVATE_NEUTRAL_RUNTIME_PREFLIGHT")
        ) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "runtime profile"):
            self.call()

    def test_duplicate_live_runtime_profile_is_rejected(self):
        with self.log.open("a", encoding="utf-8") as stream:
            stream.write("VH_PRIVATE_NEUTRAL_RUNTIME_PREFLIGHT "
                         "bizhawk_version=2.11 display=NTSC active_core=unverified\n")
        with self.assertRaisesRegex(ValueError, "runtime profile"):
            self.call()

    def test_reordered_runtime_profile_is_rejected(self):
        source = self.log.read_text(encoding="utf-8")
        profile = ("VH_PRIVATE_NEUTRAL_RUNTIME_PREFLIGHT "
                   "bizhawk_version=2.11 display=NTSC active_core=unverified\n")
        source = source.replace(profile, "")
        source = source.replace(
            "VH_PRIVATE_NEUTRAL_START_PREFLIGHT",
            profile + "VH_PRIVATE_NEUTRAL_START_PREFLIGHT",
        )
        # A valid marker must appear after movie source, before Start:
        # force a profile before the recorded movie source instead.
        source = source.replace(profile, "")
        source = profile + source
        self.log.write_text(source, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "runtime profile"):
            self.call()

    def test_invalid_runtime_profile_values_are_rejected(self):
        original = self.log.read_text(encoding="utf-8")
        for mutation in (
            "bizhawk_version=2.11\tPRIVATE",
            "bizhawk_version=2.11-invalid",
            "bizhawk_version=2.11 display=UNKNOWN",
            "bizhawk_version=2.11 display=PAL active_core=Octoshock",
        ):
            with self.subTest(mutation=mutation):
                changed = original.replace(
                    "bizhawk_version=2.11 display=NTSC active_core=unverified",
                    mutation,
                )
                self.log.write_text(changed, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "runtime profile"):
                    self.call()

    def test_pal_display_is_accepted_without_octoshock_claim(self):
        source = self.log.read_text(encoding="utf-8")
        self.log.write_text(source.replace(
            "bizhawk_version=2.11 display=NTSC",
            "bizhawk_version=2.11.1 display=PAL",
        ), encoding="utf-8")
        report = self.call()
        self.assertEqual(report["reported_bizhawk_version"], "2.11.1")
        self.assertEqual(report["reported_psx_display_standard"], "PAL")
        self.assertFalse(report["active_octoshock_core_verified"])

    def test_missing_poweron_movie_source_marker_refused(self):
        text = self.log.read_text()
        self.log.write_text("\n".join(
            line for line in text.splitlines()
            if not line.startswith("VH_PRIVATE_NEUTRAL_MOVIE_SOURCE_PREFLIGHT")
        ) + "\n")
        with self.assertRaisesRegex(ValueError, "movie"):
            self.call()

    def test_wrong_movie_source_marker_refused(self):
        self.log.write_text(self.log.read_text().replace(
            "source=poweron filename=matched",
            "source=savestate filename=matched",
        ))
        with self.assertRaisesRegex(ValueError, "power-on movie source"):
            self.call()

    def test_duplicate_movie_source_marker_refused(self):
        with self.log.open("a") as stream:
            stream.write(
                "VH_PRIVATE_NEUTRAL_MOVIE_SOURCE_PREFLIGHT "
                "source=poweron filename=matched core_identity=unverified\n"
            )
        with self.assertRaisesRegex(ValueError, "power-on movie source"):
            self.call()

    def test_movie_source_marker_after_start_refused(self):
        text = self.log.read_text()
        marker = ("VH_PRIVATE_NEUTRAL_MOVIE_SOURCE_PREFLIGHT "
                  "source=poweron filename=matched core_identity=unverified")
        text = text.replace(marker + "\n", "")
        anchor = ("VH_PRIVATE_NEUTRAL_START_PREFLIGHT counter=1662 "
                  "candidate_input=1661 first_start_pressed=yes "
                  "ps1_input_delivery=unverified")
        text = text.replace(anchor + "\n", anchor + "\n" + marker + "\n")
        self.log.write_text(text)
        with self.assertRaisesRegex(ValueError, "power-on movie source"):
            self.call()

    def test_missing_live_start_preflight_refused(self):
        text = self.log.read_text()
        self.log.write_text("\n".join(line for line in text.splitlines()
                                     if not line.startswith("VH_PRIVATE_NEUTRAL_START_PREFLIGHT")) + "\n")
        with self.assertRaises(ValueError):
            self.call()

    def test_wrong_counter_in_start_preflight_refused(self):
        self.log.write_text(self.log.read_text().replace(
            "START_PREFLIGHT counter=1662", "START_PREFLIGHT counter=1663"))
        with self.assertRaises(ValueError):
            self.call()

    def test_duplicate_start_preflight_refused(self):
        marker = "VH_PRIVATE_NEUTRAL_START_PREFLIGHT counter=1662 candidate_input=1661 first_start_pressed=yes ps1_input_delivery=unverified\n"
        with self.log.open("a") as stream:
            stream.write(marker)
        with self.assertRaises(ValueError):
            self.call()

    def test_start_preflight_after_first_capture_refused(self):
        text = self.log.read_text()
        marker = "VH_PRIVATE_NEUTRAL_START_PREFLIGHT counter=1662 candidate_input=1661 first_start_pressed=yes ps1_input_delivery=unverified"
        text = text.replace(marker + "\n", "").replace(
            log_row(*PICKS[0]) + "\n",
            log_row(*PICKS[0]) + "\n" + marker + "\n")
        self.log.write_text(text)
        with self.assertRaises(ValueError):
            self.call()

    def test_direct_source_plan_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            self.call(expected=LINES[:-1] + ["1,after,3501,held"])

    def test_modified_plan_with_unchanged_source_rejected(self):
        self.plan.write_text(self.plan.read_text().replace(
            "1,middle,3250,neutral", "1,middle,3251,neutral"))
        with self.assertRaises(ValueError):
            self.call()

    def test_shifted_emu_counter_in_console_refused(self):
        self.log.write_text(self.log.read_text().replace(
            "counter=3251 candidate_input=3250",
            "counter=3252 candidate_input=3250"))
        with self.assertRaises(ValueError):
            self.call()

    def test_recorded_png_role_swapped_refused(self):
        self.records[1] = (1, "after", 3250, "neutral")
        self.write_log()
        with self.assertRaises(ValueError):
            self.call()

    def test_missing_console_marker_refused(self):
        self.records.pop()
        self.write_log()
        with self.assertRaises(ValueError):
            self.call()

    def test_capture_probes_reported_error_refused(self):
        with self.log.open("a") as f:
            f.write("VH_PRIVATE_NEUTRAL_CAPTURE_ERROR movie_playback_left_readonly\n")
        with self.assertRaises(ValueError):
            self.call()

    def test_missing_completion_refused(self):
        self.write_log(complete=False)
        with self.assertRaises(ValueError):
            self.call()

    def test_nonzero_launcher_exit_refused(self):
        self.write_log(exit_success=0)
        with self.assertRaisesRegex(ValueError, "process exit marker is invalid"):
            self.call()

    def test_missing_launcher_exit_marker_refused(self):
        self.write_log(process_exit=False)
        with self.assertRaisesRegex(ValueError, "successful process exit"):
            self.call()

    def test_launcher_exit_before_capture_completion_refused(self):
        self.write_log(complete=False, process_exit=True)
        with self.assertRaises(ValueError):
            self.call()

    def test_duplicate_launcher_exit_marker_refused(self):
        with self.log.open("a") as stream:
            stream.write("VH_PRIVATE_BIZHAWK_LOCAL_PROCESS_EXITED exit_success=1 "
                         "original_ps1_authenticated=0 map02_identified=0\n")
        with self.assertRaises(ValueError):
            self.call()

    def test_malformed_launcher_exit_marker_refused(self):
        self.log.write_text(self.log.read_text().replace(
            "exit_success=1 original_ps1_authenticated=0 map02_identified=0",
            "exit_success=yes original_ps1_authenticated=0 map02_identified=0"))
        with self.assertRaisesRegex(ValueError, "process exit marker is invalid"):
            self.call()

    def test_launcher_error_marker_refused(self):
        with self.log.open("a") as stream:
            stream.write("VH_PRIVATE_BIZHAWK_LAUNCH_ERROR process_started=0 "
                         "original_ps1_authenticated=0\n")
        with self.assertRaisesRegex(ValueError, "launch failed"):
            self.call()

    def test_duplicate_completion_refused(self):
        with self.log.open("a") as f:
            f.write("VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE snapshots=3 "
                    "movie_input_only=yes core_input_poll_observed=yes actual_map02=unverified\n")
        with self.assertRaises(ValueError):
            self.call()

    def test_late_capture_after_completion_refused(self):
        with self.log.open("a") as f:
            f.write(log_row(*PICKS[0]) + "\n")
        with self.assertRaises(ValueError):
            self.call()

    def test_altered_png_crc_refused(self):
        path = self.images / "vh_review_w01_middle_counter_0003251.png"
        data = bytearray(path.read_bytes())
        data[20] ^= 1
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            self.call()

    def test_png_with_valid_crc_but_bad_zlib_refused(self):
        path = self.images / "vh_review_w01_middle_counter_0003251.png"
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", b"not-a-zlib-stream")
            + chunk(b"IEND", b""))
        with self.assertRaises(ValueError):
            self.call()

    def test_missing_png_refused(self):
        (self.images / "vh_review_w01_after_counter_0003501.png").unlink()
        with self.assertRaises((ValueError, OSError)):
            self.call()

    def test_hardlinked_image_reuse_refused(self):
        p = self.images / "vh_review_w01_after_counter_0003501.png"
        other = self.images / "vh_review_w01_before_counter_0003001.png"
        p.unlink()
        os.link(other, p)
        with self.assertRaises(ValueError):
            self.call()

    def test_symlink_png_refused(self):
        p = self.images / "vh_review_w01_after_counter_0003501.png"
        other = self.images / "vh_review_w01_before_counter_0003001.png"
        p.unlink()
        p.symlink_to(other)
        with self.assertRaises(ValueError):
            self.call()

    def test_capture_root_inside_git_checkout_refused(self):
        (self.base / ".git").mkdir()
        with self.assertRaises(ValueError):
            self.call()

    def test_capture_root_under_worktree_git_file_refused(self):
        (self.base / ".git").write_text("gitdir: /other/worktree", encoding="ascii")
        with self.assertRaises(ValueError):
            self.call()

    def test_capture_root_under_symlinked_git_parent_refused(self):
        # The root itself is real, but a parent folder is a symbolic link.
        with tempfile.TemporaryDirectory() as outer:
            actual = Path(outer)
            (actual / ".git").mkdir()
            links = self.base / "alias"
            links.symlink_to(actual, target_is_directory=True)
            real_pictures = actual / "capture"
            real_pictures.mkdir()
            for f in self.images.glob("*.png"):
                (real_pictures / f.name).write_bytes(f.read_bytes())
            with self.assertRaises(ValueError):
                self.call(pictures=links / "capture")

    def test_private_plan_symlink_refused(self):
        other = self.base / "plan-other"
        other.write_bytes(self.plan.read_bytes())
        self.plan.unlink()
        self.plan.symlink_to(other)
        with self.assertRaises(ValueError):
            self.call()

    def test_plan_without_final_newline_refused(self):
        self.plan.write_text("\n".join(LINES), encoding="ascii")
        with self.assertRaises(ValueError):
            self.call()

    def test_plan_missing_group_role_refused(self):
        self.plan.write_text("\n".join(LINES[:-1]) + "\n")
        with self.assertRaises(ValueError):
            self.call()

    def test_plan_reordered_rows_refused(self):
        self.plan.write_text("\n".join(
            LINES[:4] + [LINES[5], LINES[4]]
        ) + "\n")
        with self.assertRaises(ValueError):
            self.call()

    def test_unknown_plan_version_refused(self):
        self.plan.write_text(self.plan.read_text().replace(
            "VH_MAP02_CAPTURE_PLAN_V1", "VH_MAP02_CAPTURE_PLAN_V2"))
        with self.assertRaises(ValueError):
            self.call()


if __name__ == "__main__":
    unittest.main()

"""A truly spawned *synthetic* process exercises private MAP02 launcher."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from tools.run_map02_private_native_capture import capture, _private_create
from tools.verify_map02_private_capture_receipt import replay_receipt


# No copyrighted game executable, assets or scenes are used by these tests.
STUB = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["VH_MAP02_GPU_CAPTURE_DIR"])
if "--hang" in sys.argv:
    import time
    time.sleep(5)
    sys.exit(0)
if "--exit-error" in sys.argv:
    sys.exit(6)
if "--no-capture" in sys.argv:
    sys.exit(0)
frame = int(os.environ["VH_MAP02_GPU_CAPTURE_FRAME"])
span = {
    "stage": "native_dda_span", "step": 0, "frame": frame,
    "primitive_ordinal": 0, "primitive_type": 2, "y": 12,
    "x_start": 10, "x_bound": 20, "clip_l": 5, "clip_r": 25,
    "clip_t": 10, "clip_b": 15
}
(root / "dda-native-spans.jsonl").write_text(json.dumps(span) + "\n")
if "--with-load" in sys.argv:
    (root / "gpu-0001-upload.bin").write_bytes(b"\x1f\x00")
    for i, phase in enumerate(("before", "after")):
        load = {
            "stage": "native_vram", "step": i, "frame": frame - 1,
            "phase": phase, "operation": "load",
            "snapshot": f"gpu-{i:04d}-vram.bin",
            "rect": [0, 0, 1, 1], "dest": [0, 0], "rgb": [0, 0, 0],
            "primitive_type": 0, "semi": 0, "window": [0, 0, 0, 0],
            "draw_mode": [0, 0, 0],
            "upload": "gpu-0001-upload.bin" if phase == "after" else "",
            "ft4": None
        }
        with (root / "gpu-native-events.jsonl").open("a") as log:
            log.write(json.dumps(load) + "\n")
        load_vram = bytearray(1024 * 512 * 2)
        if phase == "after":
            load_vram[:2] = b"\x1f\x00"
        (root / load["snapshot"]).write_bytes(load_vram)
if "--with-move" in sys.argv:
    for i, phase in enumerate(("before", "after")):
        move = {
            "stage": "native_vram", "step": i, "frame": frame - 1,
            "phase": phase, "operation": "move",
            "snapshot": f"gpu-{i:04d}-vram.bin",
            "rect": [0, 0, 3, 1], "dest": [1, 0],
            "rgb": [0, 0, 0], "primitive_type": 0, "semi": 0,
            "window": [0, 0, 0, 0], "draw_mode": [0, 0, 0],
            "upload": "", "ft4": None,
        }
        with (root / "gpu-native-events.jsonl").open("a") as log:
            log.write(json.dumps(move) + "\n")
        move_vram = bytearray(1024 * 512 * 2)
        move_vram[:8] = (b"\x11\x00\x22\x00\x33\x00\x44\x00"
                         if phase == "before" else b"\x11\x00" * 4)
        (root / move["snapshot"]).write_bytes(move_vram)
if "--with-clear" in sys.argv:
    for i, phase in enumerate(("before", "after")):
        clear = {
            "stage": "native_vram", "step": i, "frame": frame - 1,
            "phase": phase, "operation": "clear",
            "snapshot": f"gpu-{i:04d}-vram.bin",
            "rect": [0, 0, 2, 1], "dest": [0, 0],
            "rgb": [248, 0, 0], "primitive_type": 0, "semi": 0,
            "window": [0, 0, 0, 0], "draw_mode": [0, 0, 0],
            "upload": "", "ft4": None,
        }
        with (root / "gpu-native-events.jsonl").open("a") as log:
            log.write(json.dumps(clear) + "\n")
        clear_vram = bytearray(1024 * 512 * 2)
        if phase == "after":
            clear_vram[:4] = b"\x1f\x00" * 2
        (root / clear["snapshot"]).write_bytes(clear_vram)
for i, phase in enumerate(("before", "after"),
                          start=2 if ("--with-load" in sys.argv
                                      or "--with-move" in sys.argv
                                      or "--with-clear" in sys.argv) else 0):
    event = {
        "stage": "native_vram", "step": i, "frame": frame,
        "phase": phase, "operation": "draw",
        "snapshot": f"gpu-{i:04d}-vram.bin",
        "rect": None, "dest": [0, 0], "rgb": [0, 0, 0],
        "primitive_type": 2, "semi": 0, "window": [0, 0, 0, 0],
        "draw_mode": [0, 0, 0], "upload": "",
        "ft4": {"tpage":0, "clut":0,
                 "xy":[0,0,1,0,0,1,1,1],
                 "uv":[0,0,1,0,0,1,1,1]},
    }
    with (root / "gpu-native-events.jsonl").open("a") as log:
        log.write(json.dumps(event) + "\n")
    (root / event["snapshot"]).write_bytes(bytes(1024 * 512 * 2))
if "--two-draws" in sys.argv:
    # Separate DrawOTag primitive pair in the same target frame.
    # Reuse the preceding real synthetic post-VRAM without a hidden write.
    first_draw_step = 2 if ("--with-load" in sys.argv
                            or "--with-move" in sys.argv
                            or "--with-clear" in sys.argv) else 0
    for step, phase in ((first_draw_step + 2, "before"),
                        (first_draw_step + 3, "after")):
        additional = dict(event, step=step, phase=phase,
                          snapshot=f"gpu-{step:04d}-vram.bin")
        with (root / "gpu-native-events.jsonl").open("a") as log:
            log.write(json.dumps(additional) + "\n")
        (root / additional["snapshot"]).write_bytes(bytes(1024 * 512 * 2))
'''


class PrivateNativeLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.capture_dir = self.base / "private-capture"
        self.capture_dir.mkdir(mode=0o700)
        self.capture_dir.chmod(0o700)
        self.executable = self.base / "synthetic-gpu-probe"
        self.executable.write_text(STUB, encoding="utf-8")
        self.executable.chmod(0o700)
        self.preflight = self.base / "preflight.json"
        self.summary = self.base / "summary.json"
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "VH_MAP02_GPU_CAPTURE_DIR": str(self.capture_dir),
            "VH_MAP02_PUTPIXEL_DIR": str(self.capture_dir),
            "VH_MAP02_GPU_CAPTURE_FRAME": "3",
            "VH_MAP02_PUTPIXEL_FRAME": "3",
            "VH_MAP02_PUTPIXEL_X": "12",
            "VH_MAP02_PUTPIXEL_Y": "12",
        }

    def run_synthetic(self, *args):
        return capture(self.executable, self.preflight, self.summary,
                       game_args=list(args), environ=self.env)

    def test_real_subprocess_produces_valid_private_trace(self):
        result = self.run_synthetic()
        self.assertTrue(result["process_started"])
        self.assertEqual(result["process_exit_code"], 0)
        self.assertTrue(result["capture_verified"])
        self.assertIsNone(result["failure_category"])
        self.assertFalse(result["retail_map02_verified"])
        self.assertFalse(result["hd_replacement_authorized"])
        self.assertTrue(result["verification"]["native_gpu_binding"]["verified"])
        self.assertEqual(result["verification"]["dda_observation_mode"], "entered_only")
        self.assertFalse(result["verification"]["all_dda_journal_classes_observed"])
        self.assertEqual(result["verification"]["native_gpu_pairs_verified"], 1)
        self.assertEqual(len(result["verification"]["vram_snapshot_sha256_list_sha256"]), 64)
        for path in (self.preflight, self.summary):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(json.loads(self.summary.read_text())["capture_verified"], True)
        flat = json.dumps(result)
        self.assertNotIn(str(self.capture_dir), flat)
        self.assertNotIn(str(self.executable), flat)
        self.assertNotIn('"x_start"', flat)

    def replay(self):
        return replay_receipt(self.capture_dir, receipt_file=self.summary,
                              preflight_report=self.preflight,
                              executable=self.executable)

    def test_private_receipts_publish_complete_bytes_without_pending_files(self):
        result = self.run_synthetic()
        self.assertTrue(result["capture_verified"])
        for destination in (self.preflight, self.summary):
            raw = destination.read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            self.assertEqual(json.loads(raw), json.loads(destination.read_text()))
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(list(self.base.glob(".*.pending")), [])
        with self.assertRaises(FileExistsError):
            _private_create(self.summary, {"should": "not replace"})
        self.assertEqual(json.loads(self.summary.read_bytes())["capture_verified"], True)

    def test_private_receipt_failed_partial_json_write_never_becomes_visible(self):
        from tools import run_map02_private_native_capture as launcher
        target = self.base / "failed.json"

        def partial_then_fail(obj, stream, **kwargs):
            stream.write('{"incomplete": ')
            raise OSError("synthetic short write")

        with patch.object(launcher.json, "dump", side_effect=partial_then_fail):
            with self.assertRaisesRegex(OSError, "synthetic short write"):
                _private_create(target, {"incomplete": False})
        self.assertFalse(target.exists())
        self.assertEqual(list(self.base.glob(".*.pending")), [])

    def test_private_receipt_post_link_fsync_failure_rolls_back(self):
        from tools import run_map02_private_native_capture as launcher
        target = self.base / "not-published.json"
        original_fsync = launcher.os.fsync
        calls = [0]

        def fail_final_dir_fsync(fd):
            calls[0] += 1
            if calls[0] == 3:
                raise OSError("synthetic final directory fsync failure")
            return original_fsync(fd)

        with patch.object(launcher.os, "fsync", side_effect=fail_final_dir_fsync):
            with self.assertRaisesRegex(OSError, "final directory fsync failure"):
                _private_create(target, {"valid": True})
        self.assertGreaterEqual(calls[0], 3)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.base.glob(".*.pending")), [])

    def test_private_receipt_existing_destination_race_is_fail_closed(self):
        from tools import run_map02_private_native_capture as launcher
        target = self.base / "raced.json"

        def create_rival_file(temporary, destination, **kwargs):
            Path(destination).write_bytes(b"EXISTING PRIVATE RECEIPT")
            raise FileExistsError("exclusive link refused")

        with patch.object(launcher.os, "link", side_effect=create_rival_file):
            with self.assertRaisesRegex(FileExistsError, "exclusive link refused"):
                _private_create(target, {"secret": "should never replace"})
        self.assertEqual(target.read_bytes(), b"EXISTING PRIVATE RECEIPT")
        self.assertEqual(list(self.base.glob(".*.pending")), [])

    def test_private_replay_rejects_forged_interprimitive_vram_gap(self):
        result = self.run_synthetic("--two-draws")
        self.assertTrue(result["capture_verified"])
        self.assertEqual(result["verification"]["draw_boundary_vram_checks"], 1)
        self.assertEqual(result["verification"]["draw_boundary_gpu_state_checks"], 1)
        fresh = self.replay()
        self.assertEqual(fresh["draw_boundary_vram_checks"], 1)
        self.assertTrue(fresh["raw_evidence_matches_original_receipt"])
        # Forge a plausible but isolated second DrawOTag primitive pair.
        # Its before and after bytes agree, so only inter-pair continuity
        # can detect the unrecorded extra write.
        for step in (2, 3):
            snapshot = self.capture_dir / f"gpu-{step:04d}-vram.bin"
            changed = bytearray(snapshot.read_bytes())
            changed[6:8] = b"\xab\x01"
            snapshot.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "discontinuous VRAM"):
            self.replay()

    def test_replay_detects_changed_vram_and_dda_logs(self):
        self.run_synthetic()
        report = self.replay()
        self.assertTrue(report["raw_evidence_matches_original_receipt"])
        self.assertEqual(report["dda_observation_mode"], "entered_only")
        self.assertEqual(report["native_gpu_pairs_verified"], 1)
        self.assertEqual(
            report["native_gpu_event_log_sha256"],
            hashlib.sha256(
                (self.capture_dir / "gpu-native-events.jsonl").read_bytes()
            ).hexdigest(),
        )
        self.assertFalse(report["original_game_assets_authenticated"])
        self.assertFalse(report["hd_replacement_authorized"])
        self.assertNotIn(str(self.capture_dir), json.dumps(report))

        vram = self.capture_dir / "gpu-0001-vram.bin"
        original_vram = vram.read_bytes()
        changed = bytearray(original_vram)
        changed[0] ^= 1
        vram.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            self.replay()
        vram.write_bytes(original_vram)

        span = self.capture_dir / "dda-native-spans.jsonl"
        original_span = span.read_bytes()
        changed_span = original_span.replace(b'"x_start": 10', b'"x_start": 11')
        self.assertNotEqual(original_span, changed_span)
        span.write_bytes(changed_span)
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            self.replay()

    def test_replay_detects_mutated_loadimage_payload_without_vram_change(self):
        result = self.run_synthetic("--with-load")
        self.assertTrue(result["capture_verified"])
        first = self.replay()
        self.assertEqual(first["native_gpu_pairs_verified"], 2)
        self.assertEqual(result["verification"]["load_pairs_with_verified_payload"], 1)
        self.assertEqual(result["verification"]["load_pairs_with_verified_vram_effect"], 1)
        self.assertEqual(result["verification"]["load_pairs_without_payload"], 0)
        self.assertEqual(len(result["verification"]["upload_payload_sha256_list_sha256"]), 64)
        self.assertFalse(first["original_game_assets_authenticated"])
        payload = self.capture_dir / "gpu-0001-upload.bin"
        original = payload.read_bytes()
        self.assertEqual(len(original), 2)
        payload.write_bytes(b"\x1e\x00")  # same-size tampering
        with self.assertRaisesRegex(ValueError, "post-VRAM differs"):
            self.replay()
        payload.write_bytes(original)
        self.assertTrue(self.replay()["raw_evidence_matches_original_receipt"])

    def test_replay_detects_moveimage_overlap_violation(self):
        result = self.run_synthetic("--with-move")
        self.assertTrue(result["capture_verified"])
        self.assertEqual(result["verification"]["move_pairs_with_verified_vram_effect"], 1)
        initial = self.replay()
        self.assertTrue(initial["raw_evidence_matches_original_receipt"])
        self.assertEqual(initial["move_pairs_with_verified_vram_effect"], 1)
        post = self.capture_dir / "gpu-0001-vram.bin"
        corrupted = bytearray(post.read_bytes())
        # Replace the source-ordered overlapping result with an
        # incorrect memcpy-like snapshot that preserves file size.
        corrupted[:8] = b"\x11\x00\x11\x00\x22\x00\x33\x00"
        post.write_bytes(corrupted)
        with self.assertRaisesRegex(ValueError, "MoveImage post-VRAM differs"):
            self.replay()

    def test_replay_detects_clearimage_bgr555_or_outside_vram_change(self):
        result = self.run_synthetic("--with-clear")
        self.assertTrue(result["capture_verified"])
        self.assertEqual(result["verification"]["clear_pairs_with_verified_vram_effect"], 1)
        original_replay = self.replay()
        self.assertTrue(original_replay["raw_evidence_matches_original_receipt"])
        self.assertEqual(original_replay["clear_pairs_with_verified_vram_effect"], 1)
        post = self.capture_dir / "gpu-0001-vram.bin"
        changed = bytearray(post.read_bytes())
        changed[0] ^= 1
        post.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "ClearImage post-VRAM differs"):
            self.replay()

    def test_replay_rejects_same_bytes_inode_swaps_of_all_external_inputs(self):
        # Without path/inode stability, an attacker can substitute a
        # byte-identical receipt, preflight or binary just after the GPU
        # and DDA verification. A SHA-only recheck would miss that swap.
        self.assertTrue(self.run_synthetic()["capture_verified"])
        from tools import verify_map02_private_capture_receipt as verifier
        original = verifier.verify_session
        for path in (self.summary, self.preflight, self.executable):
            with self.subTest(kind=path.name):
                previous = path.stat()
                raw = path.read_bytes()

                def swap_after_valid_replay(*args, **kwargs):
                    verified = original(*args, **kwargs)
                    replacement = path.with_name(path.name + ".same-bytes-replacement")
                    replacement.write_bytes(raw)
                    replacement.chmod(stat.S_IMODE(previous.st_mode))
                    os.replace(replacement, path)
                    self.assertNotEqual(path.stat().st_ino, previous.st_ino)
                    self.assertEqual(path.read_bytes(), raw)
                    return verified

                with patch.object(verifier, "verify_session",
                                  side_effect=swap_after_valid_replay):
                    with self.assertRaisesRegex(
                            ValueError, "changed during replay"):
                        self.replay()
                # Even the untouched content remains independently valid,
                # demonstrating the rejection is about a changed identity.
                self.assertTrue(self.replay()["raw_evidence_matches_original_receipt"])

    def test_replay_rejects_same_bytes_inplace_binary_rewrite_during_verification(self):
        self.assertTrue(self.run_synthetic()["capture_verified"])
        from tools import verify_map02_private_capture_receipt as verifier
        original = verifier.verify_session
        initial = self.executable.stat()
        raw = self.executable.read_bytes()

        def rewrite_after_valid_replay(*args, **kwargs):
            verified = original(*args, **kwargs)
            self.executable.write_bytes(raw)
            # POSIX ctime must change even if the content and length do not.
            self.assertEqual(self.executable.read_bytes(), raw)
            return verified

        with patch.object(verifier, "verify_session",
                          side_effect=rewrite_after_valid_replay):
            with self.assertRaisesRegex(ValueError, "changed during replay"):
                self.replay()
        self.assertEqual(self.executable.stat().st_ino, initial.st_ino)
        self.assertTrue(self.replay()["raw_evidence_matches_original_receipt"])

    def test_replay_rejects_preflight_symlink_injected_during_verification(self):
        self.assertTrue(self.run_synthetic()["capture_verified"])
        from tools import verify_map02_private_capture_receipt as verifier
        original = verifier.verify_session
        backup = self.base / "preflight-backup.json"

        def link_after_valid_replay(*args, **kwargs):
            verified = original(*args, **kwargs)
            self.preflight.rename(backup)
            self.preflight.symlink_to(backup)
            return verified

        with patch.object(verifier, "verify_session",
                          side_effect=link_after_valid_replay):
            with self.assertRaisesRegex(ValueError, "symlink"):
                self.replay()
        self.preflight.unlink()
        backup.rename(self.preflight)
        self.assertTrue(self.replay()["raw_evidence_matches_original_receipt"])

    def test_replay_rejects_fifo_substitution_without_blocking(self):
        self.assertTrue(self.run_synthetic()["capture_verified"])
        for victim in (self.summary, self.preflight):
            with self.subTest(kind=victim.name):
                original = victim.read_bytes()
                victim.unlink()
                os.mkfifo(victim, 0o600)
                # This must raise without trying to read the unconnected
                # named pipe and hanging the CI worker.
                with self.assertRaisesRegex(ValueError, "regular file"):
                    self.replay()
                victim.unlink()
                victim.write_bytes(original)
        self.assertTrue(self.replay()["raw_evidence_matches_original_receipt"])

    def test_replay_refuses_modified_original_process_receipt(self):
        self.run_synthetic()
        original = json.loads(self.summary.read_text())
        original["capture_verified"] = False
        self.summary.write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "did not have"):
            self.replay()
        original["capture_verified"] = True
        original["verification"]["native_gpu_pairs_verified"] = 99
        self.summary.write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            self.replay()
        self.summary.write_text('{"schema":1,"schema":2}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "malformed"):
            self.replay()

    def test_replay_requires_successful_executed_process(self):
        self.run_synthetic("--exit-error")
        with self.assertRaisesRegex(ValueError, "did not have"):
            self.replay()

    def test_exit_nonzero_is_not_success_even_if_process_started(self):
        result = self.run_synthetic("--exit-error")
        self.assertTrue(result["process_started"])
        self.assertEqual(result["process_exit_code"], 6)
        self.assertEqual(result["failure_category"], "process_exit_nonzero")
        self.assertFalse(result["capture_verified"])

    def test_zero_exit_without_gpu_data_is_not_verified(self):
        result = self.run_synthetic("--no-capture")
        self.assertTrue(result["process_started"])
        self.assertEqual(result["process_exit_code"], 0)
        self.assertEqual(result["failure_category"],
                         "incomplete_or_invalid_private_capture")
        self.assertFalse(result["capture_verified"])

    def test_synthetic_process_timeout_is_terminated_and_unverified(self):
        result = capture(self.executable, self.preflight, self.summary,
                         environ=self.env, game_args=("--hang",), timeout=0.2)
        self.assertTrue(result["process_started"])
        self.assertFalse(result["capture_verified"])
        self.assertEqual(result["failure_category"], "process_timeout")
        self.assertIsNone(result["process_exit_code"])
        self.assertTrue(self.summary.exists())

    def test_never_overwrites_receipts_or_reuses_capture_directory(self):
        self.run_synthetic()
        with self.assertRaisesRegex(ValueError, "receipts already exist"):
            self.run_synthetic()
        self.preflight.unlink()
        self.summary.unlink()
        with self.assertRaisesRegex(ValueError, "empty"):
            self.run_synthetic()

    def test_bad_environment_or_receipt_inside_capture_never_launches(self):
        self.env["VH_MAP02_PUTPIXEL_FRAME"] = "4"
        with self.assertRaisesRegex(ValueError, "frames must match"):
            self.run_synthetic()
        self.assertFalse(self.preflight.exists())
        self.assertFalse(self.summary.exists())
        self.env["VH_MAP02_PUTPIXEL_FRAME"] = "3"
        with self.assertRaisesRegex(ValueError, "outside empty capture"):
            capture(self.executable, self.capture_dir / "preflight.json",
                    self.summary, environ=self.env)
        self.assertEqual(list(self.capture_dir.iterdir()), [])

    def test_receipt_parent_symlink_must_not_point_into_capture(self):
        alias = self.base / "capture-alias"
        alias.symlink_to(self.capture_dir, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "outside empty capture"):
            capture(self.executable, alias / "preflight.json",
                    self.summary, environ=self.env)
        with self.assertRaisesRegex(ValueError, "outside empty capture"):
            capture(self.executable, self.preflight,
                    alias / "summary.json", environ=self.env)
        self.assertEqual(list(self.capture_dir.iterdir()), [])
        self.assertFalse(self.preflight.exists())
        self.assertFalse(self.summary.exists())

    def test_args_are_not_reported(self):
        result = self.run_synthetic("--private-game-asset-reference")
        self.assertTrue(result["capture_verified"])
        self.assertNotIn("--private-game-asset-reference", json.dumps(result))
        self.assertNotIn("--private-game-asset-reference", self.summary.read_text())


if __name__ == "__main__":
    unittest.main()

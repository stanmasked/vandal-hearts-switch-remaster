"""Stage541: fictional owner-only Drive end-to-end session (never real OAuth)."""
from __future__ import annotations

import os
from pathlib import Path
import select
import signal
import shutil
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

from tools.map02_linux_octoshock import owner_drive_session

from test_map02_linux_octoshock_private_drive import Stage537TransportTests
from tools.map02_linux_octoshock.owner_drive_session import (
    PrivateOwnerSessionError, complete_owner_archive_session,
)
from tools.map02_linux_octoshock.private_runtime_reaudit import (
    audit_independent_readback,
)


class OwnerDriveSessionTests(unittest.TestCase):
    def setUp(self):
        Stage537TransportTests.setUp(self)
        self.full_session = self.base / "private-owner-full-session"
        self.receipt_pin = self.base / "private-trust-receipt.sha256"
        self.archive_pin = self.base / "private-trust-archive.sha256"

    def execute(self, *, session="owner541001"):
        return complete_owner_archive_session(
            self.source, self.pin, self.private_map, self.full_session,
            self.receipt_pin, "vh_builds", "vh_manifests", session,
            independent_archive_pin_output=self.archive_pin,
            invoke=self.transport,
        )

    def test_successful_complete_fictional_backup_and_independent_restore(self):
        result = self.execute()
        self.assertEqual(result["runtime_files"], 7)
        self.assertTrue(result["full_private_restore_audited"])
        self.assertFalse(result["authenticated_owner_rclone_invoked"])
        self.assertEqual(result["cloud_objects_retrieved"], 5)
        self.assertFalse(result["capture_ready"])
        self.assertTrue(self.receipt_pin.exists())
        self.assertEqual(self.receipt_pin.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.archive_pin.is_file())
        self.assertEqual(self.archive_pin.stat().st_mode & 0o777, 0o600)
        self.assertTrue(result["owner_archive_pin_written"])
        self.assertEqual(self.transport.uploads, 5)
        self.assertTrue(
            (self.full_session / "independent-reaudit/new-copy/restored/runtime/EmuHawk.exe").is_file()
        )
        # Delete original installed runtime and still restore again from
        # same fictional cloud using *independently retained* local pins.
        shutil.rmtree(self.source)
        shutil.rmtree(self.full_session)
        report = audit_independent_readback(
            self.private_map, self.pin, self.archive_pin, self.receipt_pin,
            self.base / "new-audit-after-loss", "vh_builds",
            "vh_manifests", "owner541001",
            invoke=self.transport,
        )
        self.assertFalse(report["original_runtime_required"])
        self.assertFalse(self.full_session.exists())
        self.assertEqual(report["objects_read_back"], 5)

    def test_late_independent_reaudit_failure_discards_both_new_pins(self):
        with patch.object(
            owner_drive_session, "audit_independent_readback",
            side_effect=RuntimeError("fictional interrupted re-audit"),
        ):
            with self.assertRaises(PrivateOwnerSessionError):
                self.execute()
        self.assertEqual(self.transport.uploads, 5)
        self.assertTrue(self.full_session.is_dir())
        self.assertFalse(self.receipt_pin.exists())
        self.assertFalse(self.archive_pin.exists())

    def test_post_write_archive_pin_failure_discards_both_pins(self):
        real_hash = owner_drive_session._hash_file
        tar = self.full_session / "archive/map02-runtime-owner541001.tar"
        calls = 0

        def failed_final_hash(path):
            nonlocal calls
            if path == tar:
                calls += 1
                if calls == 2:
                    raise RuntimeError("fictional owner tar changed after pin")
            return real_hash(path)

        with patch.object(owner_drive_session, "_hash_file", side_effect=failed_final_hash):
            with self.assertRaises(PrivateOwnerSessionError):
                self.execute()
        self.assertEqual(calls, 2)
        self.assertTrue(self.full_session.is_dir())
        self.assertFalse(self.receipt_pin.exists())
        self.assertFalse(self.archive_pin.exists())

    def test_interrupted_cloud_receipt_sealing_discards_partial_pin(self):
        def interrupted_upload(*args, **kwargs):
            self.receipt_pin.write_text("0" * 64 + "\n", encoding="ascii")
            self.receipt_pin.chmod(0o600)
            raise RuntimeError("fictional interrupted owner receipt seal")

        with patch.object(
            owner_drive_session, "archive_to_private_drive",
            side_effect=interrupted_upload,
        ):
            with self.assertRaises(PrivateOwnerSessionError):
                self.execute()
        self.assertFalse(self.receipt_pin.exists())
        self.assertFalse(self.archive_pin.exists())
        self.assertTrue(self.full_session.exists())

    def test_keyboard_interrupt_during_receipt_sealing_discards_new_pins_and_propagates(self):
        def interrupted_upload(*args, **kwargs):
            self.receipt_pin.write_text("0" * 64 + "\n", encoding="ascii")
            self.receipt_pin.chmod(0o600)
            raise KeyboardInterrupt("synthetic owner session interrupt")

        with patch.object(
            owner_drive_session, "archive_to_private_drive",
            side_effect=interrupted_upload,
        ):
            with self.assertRaisesRegex(
                KeyboardInterrupt, "synthetic owner session interrupt",
            ):
                self.execute()
        self.assertFalse(self.receipt_pin.exists())
        self.assertFalse(self.archive_pin.exists())
        # The session tree is intentionally retained for forensic inspection.
        self.assertTrue(self.full_session.is_dir())

    def test_failed_pin_cleanup_preserves_concurrent_replacement(self):
        displaced = self.base / "displaced-partial-receipt-pin"
        original_rename = os.rename

        def interrupted_upload(*args, **kwargs):
            self.receipt_pin.write_text("0" * 64 + "\n", encoding="ascii")
            self.receipt_pin.chmod(0o600)
            raise RuntimeError("synthetic interrupted owner receipt seal")

        def replace_pin_before_quarantine(src, dst, *args, **kwargs):
            src_path = Path(src)
            dst_path = Path(dst)
            if src_path == self.receipt_pin and dst_path.name == "payload":
                original_rename(src_path, displaced)
                src_path.write_text(
                    "concurrent replacement\n", encoding="ascii"
                )
                src_path.chmod(0o600)
            return original_rename(src, dst, *args, **kwargs)

        with patch.object(
            owner_drive_session, "archive_to_private_drive",
            side_effect=interrupted_upload,
        ), patch(
            "tools.map02_linux_octoshock.owner_drive_session.os.rename",
            side_effect=replace_pin_before_quarantine,
        ):
            with self.assertRaises(PrivateOwnerSessionError):
                self.execute()

        self.assertEqual(
            displaced.read_text(encoding="ascii"), "0" * 64 + "\n",
        )
        self.assertEqual(
            self.receipt_pin.read_text(encoding="ascii"),
            "concurrent replacement\n",
        )
        self.assertEqual(self.receipt_pin.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.archive_pin.exists())
        self.assertTrue(self.full_session.is_dir())
        self.assertEqual(
            list(self.base.glob(".map02-pin-cleanup-*")), [],
        )

    def test_pin_cleanup_preserves_replacement_won_before_atomic_quarantine(self):
        pin = self.base / "interrupted-receipt.sha256"
        displaced = self.base / "displaced-original-receipt.sha256"
        pin.write_text("original unaccepted pin\n", encoding="ascii")
        pin.chmod(0o600)
        original_rename = os.rename

        def replace_before_quarantine(src, dst, *args, **kwargs):
            src_path, dst_path = Path(src), Path(dst)
            if src_path == pin and dst_path.name == "payload":
                original_rename(src_path, displaced)
                pin.write_text("concurrent replacement pin\n", encoding="ascii")
                pin.chmod(0o600)
            return original_rename(src, dst, *args, **kwargs)

        with patch.object(
            owner_drive_session.os, "rename",
            side_effect=replace_before_quarantine,
        ):
            owner_drive_session._discard_incomplete_owner_pin(pin)

        self.assertEqual(displaced.read_text(encoding="ascii"), "original unaccepted pin\n")
        self.assertEqual(pin.read_text(encoding="ascii"), "concurrent replacement pin\n")
        self.assertEqual(pin.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.base.glob(".map02-pin-cleanup-*")), [])

    def test_pin_cleanup_preserves_symlink_replacement_without_following_target(self):
        pin = self.base / "interrupted-receipt.sha256"
        displaced = self.base / "displaced-original-receipt.sha256"
        target = self.base / "symlink-target.txt"
        target.write_text("do not follow or remove target\n", encoding="ascii")
        pin.write_text("original unaccepted pin\n", encoding="ascii")
        pin.chmod(0o600)
        original_rename = os.rename

        def replace_with_symlink_before_quarantine(src, dst, *args, **kwargs):
            src_path, dst_path = Path(src), Path(dst)
            if src_path == pin and dst_path.name == "payload":
                original_rename(src_path, displaced)
                pin.symlink_to(target)
            return original_rename(src, dst, *args, **kwargs)

        with patch.object(
            owner_drive_session.os, "rename",
            side_effect=replace_with_symlink_before_quarantine,
        ):
            owner_drive_session._discard_incomplete_owner_pin(pin)

        self.assertEqual(displaced.read_text(encoding="ascii"), "original unaccepted pin\n")
        self.assertTrue(pin.is_symlink())
        self.assertEqual(os.readlink(pin), str(target))
        self.assertEqual(target.read_text(encoding="ascii"), "do not follow or remove target\n")
        self.assertEqual(list(self.base.glob(".map02-pin-cleanup-*")), [])

    def test_pin_cleanup_preserves_quarantine_when_original_name_is_claimed(self):
        pin = self.receipt_pin
        displaced = self.base / "displaced-original-receipt.sha256"
        pin.write_text("original unaccepted pin\n", encoding="ascii")
        pin.chmod(0o600)
        original_rename = os.rename

        def claim_name_during_quarantine(src, dst, *args, **kwargs):
            src_path, dst_path = Path(src), Path(dst)
            if src_path == pin and dst_path.name == "payload":
                original_rename(src_path, displaced)
                pin.write_text("replacement moved to quarantine\n", encoding="ascii")
                pin.chmod(0o600)
                original_rename(pin, dst_path)
                # A different writer claims the original name before cleanup
                # checks whether the moved replacement can be restored.
                pin.write_text("newly claimed pin path\n", encoding="ascii")
                pin.chmod(0o600)
                return None
            return original_rename(src, dst, *args, **kwargs)

        with patch.object(
            owner_drive_session.os, "rename",
            side_effect=claim_name_during_quarantine,
        ):
            owner_drive_session._discard_incomplete_owner_pin(pin)

        self.assertEqual(displaced.read_text(encoding="ascii"), "original unaccepted pin\n")
        self.assertEqual(pin.read_text(encoding="ascii"), "newly claimed pin path\n")
        quarantines = list(self.base.glob(".map02-pin-cleanup-*"))
        self.assertEqual(len(quarantines), 1)
        self.assertEqual(
            (quarantines[0] / "payload").read_text(encoding="ascii"),
            "replacement moved to quarantine\n",
        )

        # Remove the concurrent claimant during simulated owner reconciliation.
        # A fresh session must still refuse to proceed while quarantine remains.
        pin.unlink()
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())
        self.assertEqual(len(list(self.base.glob(".map02-pin-cleanup-*"))), 1)

    def test_multiple_stale_quarantine_markers_block_new_session_without_mutation(self):
        payload_marker = self.base / ".map02-pin-cleanup-stage590-payload"
        empty_marker = self.base / ".map02-pin-cleanup-stage590-empty"
        payload_marker.mkdir(mode=0o700)
        empty_marker.mkdir(mode=0o700)
        payload = payload_marker / "payload"
        payload.write_text("d" * 64 + "\\n", encoding="ascii")
        payload.chmod(0o600)

        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()

        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())
        self.assertFalse(self.receipt_pin.exists())
        self.assertFalse(self.archive_pin.exists())
        markers = sorted(self.base.glob(".map02-pin-cleanup-*"))
        self.assertEqual(markers, [empty_marker, payload_marker])
        self.assertEqual(list(empty_marker.iterdir()), [])
        self.assertEqual(
            payload.read_text(encoding="ascii"), "d" * 64 + "\\n",
        )
        self.assertEqual(payload.stat().st_mode & 0o777, 0o600)
        self.assertEqual(payload_marker.stat().st_mode & 0o777, 0o700)
        self.assertEqual(empty_marker.stat().st_mode & 0o777, 0o700)

    def test_previous_unrelated_owner_pin_survives_failed_session(self):
        old_pin = self.base / "unrelated-owner-reference.sha256"
        old_pin.write_text("a" * 64 + "\n", encoding="ascii")
        old_pin.chmod(0o600)
        self.transport.corrupt_download = True
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(old_pin.read_text(), "a" * 64 + "\n")
        self.assertEqual(old_pin.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.receipt_pin.exists())
        self.assertFalse(self.archive_pin.exists())

    def test_existing_independent_archive_pin_rejected_before_transfer(self):
        self.archive_pin.write_text("0" * 64 + "\n", encoding="ascii")
        self.archive_pin.chmod(0o600)
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())
        self.assertEqual(self.archive_pin.read_text(), "0" * 64 + "\n")

    def test_archive_pin_inside_session_root_rejected_early(self):
        self.archive_pin = self.full_session / "untrusted-tar.sha256"
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())

    def test_duplicate_pin_output_rejected_early(self):
        self.archive_pin = self.receipt_pin
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())

    def test_missing_manifest_owner_pin_does_not_upload(self):
        self.pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_bad_folder_scope_refused(self):
        self.transport.folder_ids["vh_builds"] = "fakeFolderWrongOwner"
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_mutated_remote_download_never_claims_success(self):
        self.transport.corrupt_download = True
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertFalse(self.receipt_pin.exists())
        self.assertFalse(self.archive_pin.exists())

    def test_bad_session_rejected_early(self):
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute(session="../etc")
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())

    def test_previous_session_directory_rejected(self):
        self.full_session.mkdir(mode=0o700)
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_previous_owner_receipt_pin_rejected(self):
        self.receipt_pin.write_text("0" * 64 + "\n", encoding="ascii")
        self.receipt_pin.chmod(0o600)
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_collision_with_existing_archive_object_refuses_overwrite(self):
        self.transport.remote["vh_builds"]["map02-runtime-owner541001.tar"] = b"old"
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_insecure_trust_folder_refused(self):
        self.base.chmod(0o755)
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_owner_runtime_game_file_rejected(self):
        (self.source / "private-bios.BIN").write_bytes(b"not a real BIOS")
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)


    def _start_owner_signal_child(self, *, pause_cleanup=False,
                                  pause_after_quarantine_move=False,
                                  pause_quarantine_unlink=False,
                                  pause_quarantine_receipt_unlink=False,
                                  pause_after_quarantine_receipt_unlink=False,
                                  fail_quarantine_unlink=False,
                                  fail_quarantine_receipt=False,
                                  quarantine_target="receipt", both_pins=False):
        root = self.base / "stage578-owner-signal-child"
        root.mkdir(mode=0o700)
        script = textwrap.dedent(r"""
            import hashlib
            import sys
            import time
            from pathlib import Path
            from unittest.mock import patch
            import tools.map02_linux_octoshock.owner_drive_session as module

            base = Path(sys.argv[1])
            pause_cleanup = "pause-cleanup" in sys.argv[2:]
            pause_after_quarantine_move = "pause-quarantine" in sys.argv[2:]
            pause_quarantine_unlink = "pause-quarantine-unlink" in sys.argv[2:]
            pause_quarantine_receipt_unlink = (
                "pause-quarantine-receipt-unlink" in sys.argv[2:]
            )
            pause_after_quarantine_receipt_unlink = (
                "pause-after-quarantine-receipt-unlink" in sys.argv[2:]
            )
            fail_quarantine_unlink = "fail-quarantine-unlink" in sys.argv[2:]
            fail_quarantine_receipt = "fail-quarantine-receipt" in sys.argv[2:]
            pause_quarantine_archive = "pause-quarantine-archive" in sys.argv[2:]
            both_pins = "both-pins" in sys.argv[2:]
            runtime = base / "runtime"
            runtime.mkdir(mode=0o700)
            trusted_pin = base / "trusted-manifest.sha256"
            trusted_pin.write_text("a" * 64 + "\n", encoding="ascii")
            trusted_pin.chmod(0o600)
            folder_map = base / "private-folder-map.json"
            folder_map.write_text("{}\n", encoding="ascii")
            folder_map.chmod(0o600)
            receipt_pin = base / "owner-receipt.sha256"
            archive_pin = base / "owner-archive.sha256"

            def fake_pack(_runtime, _pin, tar, tar_digest):
                data = b"fictional runtime archive"
                tar.write_bytes(data)
                import hashlib
                digest = hashlib.sha256(data).hexdigest()
                tar_digest.write_text(digest + "\n", encoding="ascii")
                return {"files": 1, "bytes": len(data),
                        "drive_upload_authenticated": False}

            def interrupted_upload(*_args, **_kwargs):
                receipt_pin.write_text("b" * 64 + "\n", encoding="ascii")
                receipt_pin.chmod(0o600)
                if both_pins:
                    archive_pin.write_text("c" * 64 + "\n", encoding="ascii")
                    archive_pin.chmod(0o600)
                print("PIN_READY", flush=True)
                while True:
                    time.sleep(1)

            sys.argv = [
                "owner_drive_session.py",
                "--runtime", str(runtime),
                "--trusted-manifest-pin", str(trusted_pin),
                "--private-folder-map", str(folder_map),
                "--new-session-root", str(base / "session"),
                "--new-owner-receipt-pin", str(receipt_pin),
                "--new-owner-archive-pin", str(archive_pin),
                "--builds-remote", "vh_builds",
                "--manifests-remote", "vh_manifests",
                "--session", "owner578test",
            ]
            real_discard = module._discard_incomplete_owner_pin
            real_rename = module.os.rename
            real_unlink = module.Path.unlink
            last_quarantined_pin = None

            def rename_with_optional_pause(src, dst):
                global last_quarantined_pin
                real_rename(src, dst)
                if (Path(dst).name == "payload"
                        and Path(dst).parent.name.startswith(".map02-pin-cleanup-")):
                    last_quarantined_pin = Path(src)
                target_pin = archive_pin if pause_quarantine_archive else receipt_pin
                if pause_after_quarantine_move and Path(src) == target_pin:
                    print("QUARANTINE_READY", flush=True)
                    while True:
                        time.sleep(1)

            def unlink_with_optional_pause(path, *args, **kwargs):
                is_quarantined_payload = (
                    Path(path).name == "payload"
                    and Path(path).parent.name.startswith(".map02-pin-cleanup-")
                )
                if fail_quarantine_unlink and is_quarantined_payload:
                    fail_target = receipt_pin if fail_quarantine_receipt else archive_pin
                    if last_quarantined_pin == fail_target:
                        print("QUARANTINE_UNLINK_FAILURE_READY", flush=True)
                        raise OSError("synthetic quarantine payload unlink failure")
                pause_this_unlink = (
                    pause_quarantine_unlink
                    or (pause_quarantine_receipt_unlink
                        and last_quarantined_pin == receipt_pin)
                )
                if pause_this_unlink and is_quarantined_payload:
                    print("QUARANTINE_PAYLOAD_READY", flush=True)
                    release = base / "continue-cleanup"
                    deadline = time.monotonic() + 10
                    while not release.exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    if not release.exists():
                        raise RuntimeError("mixed-signal test did not release quarantine unlink")
                result = real_unlink(path, *args, **kwargs)
                if (pause_after_quarantine_receipt_unlink
                        and is_quarantined_payload
                        and last_quarantined_pin == receipt_pin):
                    print("QUARANTINE_PAYLOAD_UNLINKED_READY", flush=True)
                    release = base / "continue-cleanup"
                    deadline = time.monotonic() + 10
                    while not release.exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    if not release.exists():
                        raise RuntimeError(
                            "post-unlink crash-window test did not release cleanup"
                        )
                return result

            def discard_with_optional_pause(path):
                if pause_cleanup:
                    (base / "cleanup-started").write_text("cleanup started", encoding="ascii")
                    time.sleep(2)
                return real_discard(path)

            with patch.object(
                    module.os, "rename", side_effect=rename_with_optional_pause,
                ), patch.object(
                    module.Path, "unlink", new=unlink_with_optional_pause,
                ), patch.object(
                    module, "_discard_incomplete_owner_pin",
                    side_effect=discard_with_optional_pause,
                ), patch.object(module, "verify_runtime", return_value={
                    "verified": True,
                    "trusted_manifest_pin_verified": True,
                    "capture_ready": False,
                }), patch.object(module, "verify_owner_backup_readiness", return_value={
                    "writes_performed": False,
                    "cloud_names_available": True,
                    "capture_ready": False,
                }), patch.object(module, "pack_runtime", side_effect=fake_pack), patch.object(
                    module, "archive_to_private_drive", side_effect=interrupted_upload,
                ):
                raise SystemExit(module.main())
        """)
        command = [sys.executable, "-c", script, str(root)]
        if pause_cleanup:
            command.append("pause-cleanup")
        if pause_after_quarantine_move:
            command.append("pause-quarantine")
        if pause_quarantine_unlink:
            command.append("pause-quarantine-unlink")
        if pause_quarantine_receipt_unlink:
            command.append("pause-quarantine-receipt-unlink")
        if pause_after_quarantine_receipt_unlink:
            command.append("pause-after-quarantine-receipt-unlink")
        if fail_quarantine_unlink:
            command.append("fail-quarantine-unlink")
        if fail_quarantine_receipt:
            command.append("fail-quarantine-receipt")
        if quarantine_target == "archive":
            command.append("pause-quarantine-archive")
        if both_pins:
            command.append("both-pins")
        process = subprocess.Popen(
            command,
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        ready, _, _ = select.select([process.stdout], [], [], 20)
        if not ready:
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
            self.fail(f"owner signal child did not reach pin write; stdout={stdout!r} stderr={stderr!r}")
        marker = process.stdout.readline().strip()
        if marker != "PIN_READY":
            if process.poll() is None:
                process.kill()
            stdout, stderr = process.communicate(timeout=10)
            self.fail(f"owner signal child failed before pin write; marker={marker!r} stdout={stdout!r} stderr={stderr!r}")
        return root, process

    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGKILL"),
                         "requires POSIX process signals")
    def test_sigterm_runs_guarded_cleanup_and_preserves_failed_session(self):
        root, process = self._start_owner_signal_child()
        try:
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        self.assertEqual(list(root.glob(".map02-pin-cleanup-*")), [])

    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGKILL"),
                         "requires POSIX process signals")
    def test_sigkill_leaves_partial_pin_and_retry_fails_closed(self):
        root, process = self._start_owner_signal_child()
        try:
            process.send_signal(signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        self.assertEqual(process.returncode, -signal.SIGKILL, (stdout, stderr))
        receipt_pin = root / "owner-receipt.sha256"
        self.assertEqual(receipt_pin.read_text(encoding="ascii"), "b" * 64 + "\n")
        self.assertEqual(receipt_pin.stat().st_mode & 0o777, 0o600)
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())

        # SIGKILL cannot run cleanup. A retry using the same output path must
        # refuse before transport activity and must not bless or delete the
        # orphaned pin. The owner must inspect/reconcile it manually.
        with self.assertRaises(PrivateOwnerSessionError):
            complete_owner_archive_session(
                root / "runtime",
                root / "trusted-manifest.sha256",
                root / "private-folder-map.json",
                root / "retry-session",
                receipt_pin,
                "vh_builds",
                "vh_manifests",
                "owner578retry",
                independent_archive_pin_output=root / "owner-archive.sha256",
                invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(receipt_pin.read_text(encoding="ascii"), "b" * 64 + "\n")
        self.assertFalse((root / "retry-session").exists())


    @unittest.skipUnless(os.name == "posix", "requires POSIX signal handling")
    def test_main_restores_previous_stop_handlers_after_success(self):
        previous_handlers = {
            signum: signal.getsignal(signum)
            for signum in (signal.SIGINT, signal.SIGTERM)
        }
        argv = [
            "owner_drive_session.py",
            "--runtime", str(self.source),
            "--trusted-manifest-pin", str(self.pin),
            "--private-folder-map", str(self.private_map),
            "--new-session-root", str(self.full_session),
            "--new-owner-receipt-pin", str(self.receipt_pin),
            "--new-owner-archive-pin", str(self.archive_pin),
            "--builds-remote", "vh_builds",
            "--manifests-remote", "vh_manifests",
            "--session", "owner578restore",
        ]

        def successful_session(*_args, **_kwargs):
            for signum, previous_handler in previous_handlers.items():
                self.assertIsNot(signal.getsignal(signum), previous_handler)
            return {
                "authenticated_owner_rclone_invoked": True,
                "owner_archive_pin_written": True,
                "runtime_files": 7,
                "runtime_bytes": 123,
            }

        with patch.object(
            owner_drive_session,
            "complete_owner_archive_session",
            side_effect=successful_session,
        ), patch.object(sys, "argv", argv):
            result = owner_drive_session.main()

        self.assertEqual(result, 0)
        for signum, previous_handler in previous_handlers.items():
            self.assertIs(signal.getsignal(signum), previous_handler)


    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGTERM"),
                         "requires POSIX SIGTERM handling")
    def test_repeated_sigterm_during_cleanup_is_ignored(self):
        import time

        root, process = self._start_owner_signal_child(pause_cleanup=True)
        try:
            process.send_signal(signal.SIGTERM)
            cleanup_marker = root / "cleanup-started"
            deadline = time.monotonic() + 10
            while (not cleanup_marker.exists() and process.poll() is None
                   and time.monotonic() < deadline):
                time.sleep(0.02)
            self.assertTrue(
                cleanup_marker.exists(),
                "first SIGTERM did not enter guarded cleanup",
            )
            # The child is deliberately paused inside cleanup. A second
            # SIGTERM must be ignored until cleanup completes.
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGTERM, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        self.assertEqual(list(root.glob(".map02-pin-cleanup-*")), [])


    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGINT"),
                         "requires POSIX SIGINT handling")
    def test_repeated_sigint_during_cleanup_is_ignored(self):
        import time

        root, process = self._start_owner_signal_child(pause_cleanup=True)
        try:
            process.send_signal(signal.SIGINT)
            cleanup_marker = root / "cleanup-started"
            deadline = time.monotonic() + 10
            while (not cleanup_marker.exists() and process.poll() is None
                   and time.monotonic() < deadline):
                time.sleep(0.02)
            self.assertTrue(
                cleanup_marker.exists(),
                "first SIGINT did not enter guarded cleanup",
            )
            # The child is paused inside cleanup. A second Ctrl+C must not
            # interrupt deletion or leave an unaccepted pin behind.
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGINT, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        self.assertEqual(list(root.glob(".map02-pin-cleanup-*")), [])


    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGKILL"),
                         "requires POSIX SIGKILL handling")
    def test_sigkill_after_pin_quarantine_blocks_retry_and_preserves_payload(self):
        root, process = self._start_owner_signal_child(
            pause_after_quarantine_move=True,
        )
        try:
            process.send_signal(signal.SIGTERM)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "cleanup did not reach atomic quarantine move")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_READY")
            process.send_signal(signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, -signal.SIGKILL, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        quarantines = list(root.glob(".map02-pin-cleanup-*"))
        self.assertEqual(len(quarantines), 1)
        payload = quarantines[0] / "payload"
        self.assertEqual(payload.read_text(encoding="ascii"), "b" * 64 + "\n")
        self.assertEqual(payload.stat().st_mode & 0o777, 0o600)

        # The orphaned quarantine is evidence, not disposable debris. A retry
        # must fail before transport activity and leave its payload untouched.
        with self.assertRaises(PrivateOwnerSessionError):
            complete_owner_archive_session(
                root / "runtime",
                root / "trusted-manifest.sha256",
                root / "private-folder-map.json",
                root / "retry-session",
                root / "owner-receipt.sha256",
                "vh_builds",
                "vh_manifests",
                "owner581retry",
                independent_archive_pin_output=root / "owner-archive.sha256",
                invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(payload.read_text(encoding="ascii"), "b" * 64 + "\n")
        self.assertFalse((root / "retry-session").exists())


    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGKILL"),
                         "requires POSIX SIGKILL handling")
    def test_sigkill_during_first_of_two_pin_cleanups_preserves_both_outputs(self):
        root, process = self._start_owner_signal_child(
            pause_after_quarantine_move=True,
            quarantine_target="archive",
            both_pins=True,
        )
        receipt_pin = root / "owner-receipt.sha256"
        archive_pin = root / "owner-archive.sha256"
        try:
            process.send_signal(signal.SIGTERM)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "cleanup did not reach first pin quarantine")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_READY")
            process.send_signal(signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, -signal.SIGKILL, (stdout, stderr))
        self.assertTrue(receipt_pin.is_file())
        self.assertEqual(receipt_pin.read_text(encoding="ascii"), "b" * 64 + "\n")
        self.assertEqual(receipt_pin.stat().st_mode & 0o777, 0o600)
        self.assertFalse(archive_pin.exists())
        self.assertTrue((root / "session").is_dir())

        quarantines = list(root.glob(".map02-pin-cleanup-*"))
        self.assertEqual(len(quarantines), 1)
        quarantined_archive = quarantines[0] / "payload"
        self.assertEqual(
            quarantined_archive.read_text(encoding="ascii"), "c" * 64 + "\n",
        )
        self.assertEqual(quarantined_archive.stat().st_mode & 0o777, 0o600)

        # An unresolved first-pin quarantine blocks retry, while the second
        # pin stays byte-for-byte intact and no transport is attempted.
        with self.assertRaises(PrivateOwnerSessionError):
            complete_owner_archive_session(
                root / "runtime",
                root / "trusted-manifest.sha256",
                root / "private-folder-map.json",
                root / "retry-session",
                receipt_pin,
                "vh_builds",
                "vh_manifests",
                "owner582retry",
                independent_archive_pin_output=archive_pin,
                invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(receipt_pin.read_text(encoding="ascii"), "b" * 64 + "\n")
        self.assertEqual(
            quarantined_archive.read_text(encoding="ascii"), "c" * 64 + "\n",
        )
        self.assertFalse((root / "retry-session").exists())


    # Whichever stop signal arrives first, the opposite signal must not
    # interrupt the same guarded cleanup path.
    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGINT")
                         and hasattr(signal, "SIGTERM"),
                         "requires POSIX SIGINT/SIGTERM handling")
    def test_sigterm_then_sigint_during_cleanup_is_ignored(self):
        import time

        root, process = self._start_owner_signal_child(pause_cleanup=True)
        try:
            process.send_signal(signal.SIGTERM)
            cleanup_marker = root / "cleanup-started"
            deadline = time.monotonic() + 10
            while (not cleanup_marker.exists() and process.poll() is None
                   and time.monotonic() < deadline):
                time.sleep(0.02)
            self.assertTrue(cleanup_marker.exists(),
                            "SIGTERM did not enter guarded cleanup")
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGTERM, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        self.assertEqual(list(root.glob(".map02-pin-cleanup-*")), [])


    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGINT")
                         and hasattr(signal, "SIGTERM"),
                         "requires POSIX SIGINT/SIGTERM handling")
    def test_sigint_then_sigterm_during_cleanup_is_ignored(self):
        import time

        root, process = self._start_owner_signal_child(pause_cleanup=True)
        try:
            process.send_signal(signal.SIGINT)
            cleanup_marker = root / "cleanup-started"
            deadline = time.monotonic() + 10
            while (not cleanup_marker.exists() and process.poll() is None
                   and time.monotonic() < deadline):
                time.sleep(0.02)
            self.assertTrue(cleanup_marker.exists(),
                            "SIGINT did not enter guarded cleanup")
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGINT, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        self.assertEqual(list(root.glob(".map02-pin-cleanup-*")), [])


    # Stage584: inject the second stop signal after the first pin has already
    # moved into quarantine and while the quarantined payload is being deleted.
    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGINT")
                         and hasattr(signal, "SIGTERM"),
                         "requires POSIX SIGINT/SIGTERM handling")
    def test_sigterm_then_sigint_during_quarantine_payload_unlink_is_ignored(self):
        root, process = self._start_owner_signal_child(
            pause_quarantine_unlink=True, both_pins=True,
        )
        try:
            process.send_signal(signal.SIGTERM)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "cleanup did not reach quarantined payload unlink")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_PAYLOAD_READY")
            process.send_signal(signal.SIGINT)
            (root / "continue-cleanup").write_text("release\n", encoding="ascii")
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGTERM, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        self.assertEqual(list(root.glob(".map02-pin-cleanup-*")), [])


    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGINT")
                         and hasattr(signal, "SIGTERM"),
                         "requires POSIX SIGINT/SIGTERM handling")
    def test_sigint_then_sigterm_during_quarantine_payload_unlink_is_ignored(self):
        root, process = self._start_owner_signal_child(
            pause_quarantine_unlink=True, both_pins=True,
        )
        try:
            process.send_signal(signal.SIGINT)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "cleanup did not reach quarantined payload unlink")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_PAYLOAD_READY")
            process.send_signal(signal.SIGTERM)
            (root / "continue-cleanup").write_text("release\n", encoding="ascii")
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGINT, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        self.assertEqual(list(root.glob(".map02-pin-cleanup-*")), [])


    # Stage585: a failure while deleting the first quarantined pin must not
    # accidentally proceed as though the second pin cleanup had completed.
    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGTERM"),
                         "requires POSIX SIGTERM handling")
    def test_quarantine_unlink_failure_preserves_second_pin_and_blocks_retry(self):
        root, process = self._start_owner_signal_child(
            fail_quarantine_unlink=True, both_pins=True,
        )
        receipt_pin = root / "owner-receipt.sha256"
        archive_pin = root / "owner-archive.sha256"
        try:
            process.send_signal(signal.SIGTERM)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "cleanup did not reach injected unlink failure")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_UNLINK_FAILURE_READY")
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGTERM, (stdout, stderr))
        self.assertFalse(archive_pin.exists())
        self.assertTrue(receipt_pin.is_file())
        self.assertEqual(receipt_pin.read_text(encoding="ascii"), "b" * 64 + "\n")
        self.assertEqual(receipt_pin.stat().st_mode & 0o777, 0o600)
        self.assertTrue((root / "session").is_dir())

        quarantines = list(root.glob(".map02-pin-cleanup-*"))
        self.assertEqual(len(quarantines), 1)
        quarantined_archive = quarantines[0] / "payload"
        self.assertEqual(
            quarantined_archive.read_text(encoding="ascii"), "c" * 64 + "\n",
        )
        self.assertEqual(quarantined_archive.stat().st_mode & 0o777, 0o600)

        # The unresolved quarantine and surviving receipt pin are evidence.
        # A retry must refuse before transport and preserve both objects.
        with self.assertRaises(PrivateOwnerSessionError):
            complete_owner_archive_session(
                root / "runtime",
                root / "trusted-manifest.sha256",
                root / "private-folder-map.json",
                root / "retry-session",
                receipt_pin,
                "vh_builds",
                "vh_manifests",
                "owner585retry",
                independent_archive_pin_output=archive_pin,
                invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(receipt_pin.read_text(encoding="ascii"), "b" * 64 + "\n")
        self.assertEqual(
            quarantined_archive.read_text(encoding="ascii"), "c" * 64 + "\n",
        )
        self.assertFalse((root / "retry-session").exists())


    # Stage586: the first pin is removed successfully, then cleanup of the
    # second pin fails. The surviving quarantined payload must block retry.
    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGTERM"),
                         "requires POSIX SIGTERM handling")
    def test_second_pin_unlink_failure_after_first_cleanup_blocks_retry(self):
        root, process = self._start_owner_signal_child(
            fail_quarantine_unlink=True,
            fail_quarantine_receipt=True,
            both_pins=True,
        )
        receipt_pin = root / "owner-receipt.sha256"
        archive_pin = root / "owner-archive.sha256"
        try:
            process.send_signal(signal.SIGTERM)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "second-pin cleanup did not reach injected unlink failure")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_UNLINK_FAILURE_READY")
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGTERM, (stdout, stderr))
        self.assertFalse(archive_pin.exists())
        self.assertFalse(receipt_pin.exists())
        self.assertTrue((root / "session").is_dir())

        quarantines = list(root.glob(".map02-pin-cleanup-*"))
        self.assertEqual(len(quarantines), 1)
        quarantined_receipt = quarantines[0] / "payload"
        self.assertEqual(
            quarantined_receipt.read_text(encoding="ascii"), "b" * 64 + "\n",
        )
        self.assertEqual(quarantined_receipt.stat().st_mode & 0o777, 0o600)

        # The first pin's cleanup succeeded, but the second pin is unresolved.
        # A retry must fail before transport and preserve the remaining payload.
        with self.assertRaises(PrivateOwnerSessionError):
            complete_owner_archive_session(
                root / "runtime",
                root / "trusted-manifest.sha256",
                root / "private-folder-map.json",
                root / "retry-session",
                receipt_pin,
                "vh_builds",
                "vh_manifests",
                "owner586retry",
                independent_archive_pin_output=archive_pin,
                invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(
            quarantined_receipt.read_text(encoding="ascii"), "b" * 64 + "\n",
        )
        self.assertFalse((root / "retry-session").exists())


    # Stage587: deliver the opposite stop signal while cleanup is deleting
    # the second pin's quarantine payload, after the first pin was removed.
    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGINT")
                         and hasattr(signal, "SIGTERM"),
                         "requires POSIX SIGINT/SIGTERM handling")
    def test_sigterm_then_sigint_during_second_pin_quarantine_unlink_is_ignored(self):
        root, process = self._start_owner_signal_child(
            pause_quarantine_receipt_unlink=True, both_pins=True,
        )
        stdout = stderr = ""
        try:
            process.send_signal(signal.SIGTERM)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "cleanup did not reach second-pin quarantine unlink")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_PAYLOAD_READY")
            process.send_signal(signal.SIGINT)
            (root / "continue-cleanup").write_text("release\n", encoding="ascii")
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGTERM, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        self.assertEqual(list(root.glob(".map02-pin-cleanup-*")), [])


    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGINT")
                         and hasattr(signal, "SIGTERM"),
                         "requires POSIX SIGINT/SIGTERM handling")
    def test_sigint_then_sigterm_during_second_pin_quarantine_unlink_is_ignored(self):
        root, process = self._start_owner_signal_child(
            pause_quarantine_receipt_unlink=True, both_pins=True,
        )
        stdout = stderr = ""
        try:
            process.send_signal(signal.SIGINT)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "cleanup did not reach second-pin quarantine unlink")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_PAYLOAD_READY")
            process.send_signal(signal.SIGTERM)
            (root / "continue-cleanup").write_text("release\n", encoding="ascii")
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, 128 + signal.SIGINT, (stdout, stderr))
        self.assertFalse((root / "owner-receipt.sha256").exists())
        self.assertFalse((root / "owner-archive.sha256").exists())
        self.assertTrue((root / "session").is_dir())
        self.assertEqual(list(root.glob(".map02-pin-cleanup-*")), [])


    # Stage588: SIGKILL after the first pin is gone and the second pin has
    # moved into quarantine must leave recoverable evidence and block retry.
    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGKILL"),
                         "requires POSIX SIGKILL handling")
    def test_sigkill_during_second_pin_quarantine_unlink_preserves_quarantine_and_blocks_retry(self):
        root, process = self._start_owner_signal_child(
            pause_quarantine_receipt_unlink=True, both_pins=True,
        )
        stdout = stderr = ""
        try:
            process.send_signal(signal.SIGTERM)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "cleanup did not reach second-pin quarantine unlink")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_PAYLOAD_READY")
            process.send_signal(signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, -signal.SIGKILL, (stdout, stderr))
        receipt_pin = root / "owner-receipt.sha256"
        archive_pin = root / "owner-archive.sha256"
        self.assertFalse(receipt_pin.exists())
        self.assertFalse(archive_pin.exists())
        self.assertTrue((root / "session").is_dir())

        quarantines = list(root.glob(".map02-pin-cleanup-*"))
        self.assertEqual(len(quarantines), 1)
        quarantined_receipt = quarantines[0] / "payload"
        self.assertEqual(
            quarantined_receipt.read_text(encoding="ascii"), "b" * 64 + "\n",
        )
        self.assertEqual(quarantined_receipt.stat().st_mode & 0o777, 0o600)

        # SIGKILL cannot finish cleanup. The unresolved quarantine alone must
        # be enough to reject a retry before transport and preserve the payload.
        with self.assertRaises(PrivateOwnerSessionError):
            complete_owner_archive_session(
                root / "runtime",
                root / "trusted-manifest.sha256",
                root / "private-folder-map.json",
                root / "retry-session",
                receipt_pin,
                "vh_builds",
                "vh_manifests",
                "owner588retry",
                independent_archive_pin_output=archive_pin,
                invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(
            quarantined_receipt.read_text(encoding="ascii"), "b" * 64 + "\n",
        )
        self.assertFalse((root / "retry-session").exists())


    # Stage589: SIGKILL after the second payload is unlinked but before its
    # quarantine directory is removed leaves an empty quarantine that blocks retry.
    @unittest.skipUnless(os.name == "posix" and hasattr(signal, "SIGKILL"),
                         "requires POSIX SIGKILL handling")
    def test_sigkill_after_second_pin_payload_unlink_preserves_empty_quarantine_and_blocks_retry(self):
        root, process = self._start_owner_signal_child(
            pause_after_quarantine_receipt_unlink=True, both_pins=True,
        )
        stdout = stderr = ""
        try:
            process.send_signal(signal.SIGTERM)
            ready, _, _ = select.select([process.stdout], [], [], 15)
            self.assertTrue(ready, "cleanup did not reach post-unlink crash window")
            marker = process.stdout.readline().strip()
            self.assertEqual(marker, "QUARANTINE_PAYLOAD_UNLINKED_READY")
            process.send_signal(signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

        self.assertEqual(process.returncode, -signal.SIGKILL, (stdout, stderr))
        receipt_pin = root / "owner-receipt.sha256"
        archive_pin = root / "owner-archive.sha256"
        self.assertFalse(receipt_pin.exists())
        self.assertFalse(archive_pin.exists())
        self.assertTrue((root / "session").is_dir())

        quarantines = list(root.glob(".map02-pin-cleanup-*"))
        self.assertEqual(len(quarantines), 1)
        empty_quarantine = quarantines[0]
        self.assertTrue(empty_quarantine.is_dir())
        self.assertEqual(list(empty_quarantine.iterdir()), [])
        self.assertEqual(empty_quarantine.stat().st_mode & 0o777, 0o700)

        # Although the payload unlink completed, the empty quarantine is an
        # unresolved crash marker. Never silently clear it or start a new upload.
        with self.assertRaises(PrivateOwnerSessionError):
            complete_owner_archive_session(
                root / "runtime",
                root / "trusted-manifest.sha256",
                root / "private-folder-map.json",
                root / "retry-session",
                receipt_pin,
                "vh_builds",
                "vh_manifests",
                "owner589retry",
                independent_archive_pin_output=archive_pin,
                invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)
        self.assertTrue(empty_quarantine.is_dir())
        self.assertEqual(list(empty_quarantine.iterdir()), [])
        self.assertFalse((root / "retry-session").exists())


if __name__ == "__main__":
    unittest.main()

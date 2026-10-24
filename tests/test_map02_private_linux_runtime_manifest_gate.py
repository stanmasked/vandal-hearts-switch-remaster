"""Synthetic Stage533 integration guards. No original game media."""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from tools.map02_private_bizhawk_poweron_launch import build_launch, require_linux_owner_runtime_pin, main as child_main
from tools.map02_private_two_replay_runner import capture_twice


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux Mono only")
class LinuxManifestGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.exe = self.root / "EmuHawk.exe"
        self.exe.write_bytes(b"fictional emulator")
        self.mono = self.root / "mono"
        self.mono.write_bytes(b"fictional mono")
        self.mono.chmod(0o700)
        self.pin = self.root / "fictional-external.sha256"
        self.pin.write_text("f"*64+"\n", encoding="ascii")
        self.pin.chmod(0o600)
        self.disc, self.movie, self.plan = (self.root/n for n in ("fake.cue","fake.bk2","fake-plan.txt"))
        for path in (self.disc,self.movie,self.plan):
            path.write_bytes(b"fictional media")
        self.out = self.root / "out"
        self.out.mkdir(mode=0o700)
        self.out.chmod(0o700)

    def test_missing_pin_rejected_before_media(self):
        with patch("tools.map02_private_bizhawk_poweron_launch._resolve_private_file") as opened:
            with self.assertRaisesRegex(ValueError,"requires external trusted manifest pin"):
                build_launch(self.exe,self.disc,self.movie,self.plan,self.out,
                             mono_executable=self.mono)
            opened.assert_not_called()

    def test_runtime_audit_precedes_media(self):
        with patch("tools.map02_private_bizhawk_poweron_launch.verify_runtime",
                   return_value={"verified":True,"trusted_manifest_pin_verified":True,"capture_ready":False}) as audit, patch(
                   "tools.map02_private_bizhawk_poweron_launch._resolve_private_file",
                   side_effect=ValueError("synthetic source blocked")) as opened:
            with self.assertRaisesRegex(ValueError,"synthetic source blocked"):
                build_launch(self.exe,self.disc,self.movie,self.plan,self.out,
                             mono_executable=self.mono,
                             trusted_runtime_manifest_pin_file=self.pin)
            audit.assert_called_once_with(self.exe.parent,
                trusted_manifest_pin_file=self.pin, require_trusted_pin=True)
            opened.assert_called_once()

    def test_false_trust_receipt_rejected(self):
        with patch("tools.map02_private_bizhawk_poweron_launch.verify_runtime",
                   return_value={"verified":True,"trusted_manifest_pin_verified":False,"capture_ready":False}):
            with self.assertRaisesRegex(ValueError,"trust gate rejected"):
                require_linux_owner_runtime_pin(self.exe,self.mono,self.pin)

    def test_parent_guard_blocks_movie_before_preflight(self):
        with patch("tools.map02_private_two_replay_runner._private_movie_identity") as movie:
            with self.assertRaisesRegex(ValueError,"requires external trusted manifest pin"):
                capture_twice(self.exe,self.disc,self.movie,self.out,
                              mono_executable=self.mono)
            movie.assert_not_called()

    def test_parent_rechecks_before_second_subprocess(self):
        calls=[]
        def gate(*_):
            calls.append(1)
            if len(calls)==4:
                raise ValueError("synthetic changed manifest")
        def plan(_movie,dest,**_kwargs):
            Path(dest).write_text("fake plan",encoding="ascii")
            return 3
        with patch("tools.map02_private_two_replay_runner.require_linux_owner_runtime_pin",side_effect=gate), patch(
            "tools.map02_private_two_replay_runner.verify_persistent_private_host",
            return_value={"platform_accepted":True}), patch(
            "tools.map02_private_two_replay_runner.snapshot_private_path_identity",
            return_value=(("synthetic",1,2,3,4),)), patch(
            "tools.map02_private_two_replay_runner.require_unchanged_persistent_host",
            return_value={"platform_accepted":True}), patch(
            "tools.map02_private_two_replay_runner._private_movie_identity",return_value=b"synthetic"), patch(
            "tools.map02_private_two_replay_runner._disc_source_snapshot",return_value=("fakecue","fakebin")), patch(
            "tools.map02_private_two_replay_runner.inspect_pair",return_value={"media_preflight_ready_for_owner_replay":True}), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",side_effect=plan), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",return_value=Mock(returncode=0)) as process, patch(
            "tools.map02_private_two_replay_runner.verify",return_value={"screenshot_count":3}):
            with self.assertRaisesRegex(ValueError,"synthetic changed manifest"):
                capture_twice(self.exe,self.disc,self.movie,self.out,start=True,run_count=2,
                              mono_executable=self.mono,trusted_runtime_manifest_pin_file=self.pin)
            process.assert_called_once()
            self.assertIn("--trusted-runtime-manifest-pin-file",process.call_args.args[0])
        self.assertEqual(len(calls),4)

    def test_parent_rejects_ephemeral_host_before_opening_media(self):
        with patch("tools.map02_private_two_replay_runner.require_linux_owner_runtime_pin",
                   return_value=True), patch(
            "tools.map02_private_two_replay_runner.verify_persistent_private_host",
            side_effect=ValueError("synthetic ephemeral host rejected")), patch(
            "tools.map02_private_two_replay_runner._private_movie_identity") as movie, patch(
            "tools.map02_private_two_replay_runner._disc_source_snapshot") as disc, patch(
            "tools.map02_private_two_replay_runner.subprocess.run") as process:
            with self.assertRaisesRegex(ValueError,"synthetic ephemeral host rejected"):
                capture_twice(self.exe,self.disc,self.movie,self.out,start=True,run_count=1,
                              mono_executable=self.mono,trusted_runtime_manifest_pin_file=self.pin)
        movie.assert_not_called()
        disc.assert_not_called()
        process.assert_not_called()

    def test_parent_rechecks_host_before_second_launch(self):
        rechecks=[]
        def recheck(*_args, **_kwargs):
            rechecks.append(len(rechecks)+1)
            if len(rechecks)==5:
                raise ValueError("synthetic owner host changed")
            return {"platform_accepted":True}
        def plan(_movie,dest,**_kwargs):
            Path(dest).write_text("fake plan",encoding="ascii")
            return 3
        with patch("tools.map02_private_two_replay_runner.require_linux_owner_runtime_pin",
                   return_value=True), patch(
            "tools.map02_private_two_replay_runner.verify_persistent_private_host",
            return_value={"platform_accepted":True}), patch(
            "tools.map02_private_two_replay_runner.snapshot_private_path_identity",
            return_value=(("synthetic",1,2,3,4),)), patch(
            "tools.map02_private_two_replay_runner.require_unchanged_persistent_host",
            side_effect=recheck), patch(
            "tools.map02_private_two_replay_runner._private_movie_identity",
            return_value=b"synthetic"), patch(
            "tools.map02_private_two_replay_runner._disc_source_snapshot",
            return_value=("fakecue","fakebin")), patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay":True}), patch(
            "tools.map02_private_two_replay_runner.plan_lines",
            return_value=["header","length","count","frame1","frame2","frame3"]), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=plan), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            return_value=Mock(returncode=0)) as process, patch(
            "tools.map02_private_two_replay_runner.verify",
            return_value={"screenshot_count":3}):
            with self.assertRaisesRegex(ValueError,"synthetic owner host changed"):
                capture_twice(self.exe,self.disc,self.movie,self.out,start=True,run_count=2,
                              mono_executable=self.mono,trusted_runtime_manifest_pin_file=self.pin)
        self.assertEqual(len(rechecks),5)
        process.assert_called_once()

    def test_child_rejects_ephemeral_host_before_media_or_launch(self):
        argv=["child.py",str(self.exe),str(self.disc),str(self.movie),str(self.plan),str(self.out),
              "--mono-executable",str(self.mono),"--trusted-runtime-manifest-pin-file",str(self.pin),"--launch"]
        with patch.object(sys,"argv",argv), patch(
            "tools.map02_private_bizhawk_poweron_launch.verify_persistent_private_host",
            side_effect=ValueError("synthetic ephemeral host rejected")), patch(
            "tools.map02_private_bizhawk_poweron_launch.build_launch") as build, patch(
            "tools.map02_private_bizhawk_poweron_launch.run_owned_process") as process:
            with self.assertRaises(SystemExit):
                child_main()
        build.assert_not_called()
        process.assert_not_called()

    def test_child_blocks_process_on_last_minute_mismatch(self):
        env={"VH_PRIVATE_CAPTURE_LOG":str(self.out/"vh_private_capture.log"),
             "VH_PRIVATE_PROCESS_LOG":str(self.out/"vh_emuhawk_process.log"),
             "VH_PRIVATE_PNG_DIR":str(self.out)}
        argv=["child.py",str(self.exe),str(self.disc),str(self.movie),str(self.plan),str(self.out),
              "--mono-executable",str(self.mono),"--trusted-runtime-manifest-pin-file",str(self.pin),"--launch"]
        with patch.object(sys,"argv",argv), patch(
            "tools.map02_private_bizhawk_poweron_launch.verify_persistent_private_host",
            return_value={"platform_accepted":True}), patch(
            "tools.map02_private_bizhawk_poweron_launch.snapshot_private_path_identity",
            return_value=(("synthetic",1,2,3,4),)), patch(
            "tools.map02_private_bizhawk_poweron_launch.require_unchanged_persistent_host",
            return_value={"platform_accepted":True}), patch(
            "tools.map02_private_bizhawk_poweron_launch.build_launch",
            return_value=([str(self.mono),str(self.exe)],env,3)), patch(
            "tools.map02_private_bizhawk_poweron_launch.require_linux_owner_runtime_pin",
            side_effect=ValueError("tamper")), patch(
            "tools.map02_private_bizhawk_poweron_launch.run_owned_process") as process:
            self.assertEqual(child_main(),1)
            process.assert_not_called()


if __name__=="__main__":
    unittest.main()

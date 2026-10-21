"""Fictional process-only regression tests for private emulator group cleanup."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from tools.map02_private_process_group import run_owned_process


class OwnerProcessGroupTests(unittest.TestCase):
    def test_real_no_game_subprocess_completes(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "synthetic-only-process.log"
            with output.open("wb") as stream:
                result = run_owned_process(
                    [sys.executable, "-c", "print('FICTIONAL_EMULATOR_EXIT_OK')"],
                    env=os.environ.copy(), stdout=stream, timeout=10,
                )
            self.assertEqual(result.returncode, 0)
            self.assertIn("FICTIONAL_EMULATOR_EXIT_OK",
                          output.read_text(encoding="ascii"))

    @unittest.skipIf(os.name == "nt", "POSIX process group signals only")
    def test_timeout_signals_owned_group_and_reaps_parent(self):
        leader = Mock(pid=123456, returncode=None)
        leader.wait.side_effect = [
            subprocess.TimeoutExpired(cmd=["fictional"], timeout=1), 0, 0,
        ]
        with patch(
            "tools.map02_private_process_group.subprocess.Popen",
            return_value=leader,
        ) as launch, patch(
            "tools.map02_private_process_group._kill_owned_group",
        ) as group_signal:
            with self.assertRaises(subprocess.TimeoutExpired):
                run_owned_process(
                    ["invented-emulator"], env={}, stdout=subprocess.DEVNULL,
                    timeout=1,
                )
        self.assertTrue(launch.call_args.kwargs["start_new_session"])
        self.assertFalse(launch.call_args.kwargs["shell"])
        self.assertEqual(group_signal.call_args_list[0].args,
                         (123456, signal.SIGTERM))
        self.assertEqual(group_signal.call_args_list[1].args,
                         (123456, signal.SIGKILL))
        self.assertEqual(leader.wait.call_count, 3)

    @unittest.skipIf(os.name == "nt", "POSIX process group signals only")
    def test_keyboard_interrupt_still_cleans_up_group(self):
        leader = Mock(pid=654321)
        leader.wait.side_effect = [KeyboardInterrupt(), 0, 0]
        with patch(
            "tools.map02_private_process_group.subprocess.Popen",
            return_value=leader,
        ), patch(
            "tools.map02_private_process_group._kill_owned_group",
        ) as signal_group:
            with self.assertRaises(KeyboardInterrupt):
                run_owned_process(
                    ["fictional"], env={}, stdout=subprocess.DEVNULL,
                    timeout=5,
                )
        self.assertEqual(signal_group.call_count, 2)

    @unittest.skipIf(os.name == "nt", "POSIX process group signals only")
    def test_timeout_stops_synthetic_shell_wrapper_descendant(self):
        # A fictional Python wrapper starts another fictional Python worker
        # in the same POSIX group. The worker writes a harmless heartbeat.
        # After timeout, the heartbeat must stop: process-group termination
        # is verified as an effect, not just a mocked os.killpg call.
        worker_source = (
            "import pathlib, sys, time\n"
            "marker = pathlib.Path(sys.argv[1])\n"
            "while True:\n"
            "    with marker.open('ab') as file: file.write(b'x')\n"
            "    time.sleep(0.04)\n"
        )
        wrapper_source = (
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', sys.argv[2], sys.argv[1]])\n"
            "time.sleep(30)\n"
        )
        with tempfile.TemporaryDirectory() as root:
            heartbeat = Path(root) / "invented-worker-heartbeat.bin"
            with self.assertRaises(subprocess.TimeoutExpired):
                run_owned_process(
                    [sys.executable, "-c", wrapper_source,
                     str(heartbeat), worker_source],
                    env=os.environ.copy(), stdout=subprocess.DEVNULL,
                    timeout=1.5,
                )
            self.assertTrue(heartbeat.is_file())
            self.assertGreater(heartbeat.stat().st_size, 0)
            stopped_size = heartbeat.stat().st_size
            time.sleep(0.25)
            self.assertEqual(heartbeat.stat().st_size, stopped_size)

    @unittest.skipIf(os.name == "nt", "POSIX process group signals only")
    def test_actual_synthetic_timeout_refuses_success(self):
        # Runs ONLY an invented sleeping Python program. No real EmuHawk,
        # ROM, BIOS, BK2 or proprietary image is accessed.
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "fictional.log"
            with output.open("wb") as stream:
                with self.assertRaises(subprocess.TimeoutExpired):
                    run_owned_process(
                        [sys.executable, "-c",
                         "import time; time.sleep(30)"],
                        env=os.environ.copy(), stdout=stream, timeout=0.2,
                    )


if __name__ == "__main__":
    unittest.main()

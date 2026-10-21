"""Launch owner-local EmuHawk in an isolated POSIX process group.

This controls a direct emulator process and descendants that *remain in its
process group*. A launcher that daemonizes or deliberately creates new
sessions can still leave processes running, so successful process cleanup is
not a proof of complete workstation cleanup.
"""
from __future__ import annotations

import os
import signal
import subprocess


TERMINATION_GRACE_SECONDS = 2


def _kill_owned_group(pid: int, sig: int) -> None:
    """Signal only the newly isolated process group; never the caller group."""
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def run_owned_process(command: list[str], *, env: dict[str, str],
                      stdout, timeout: int):
    """Wait for emulator; on timeout stop its POSIX group and fail closed.

    EmuHawk's stderr is redirected into the caller's owner-private stream;
    command, environment, timeout exception and OS errors are not printed.
    Windows retains subprocess.run semantics because POSIX killpg is not
    available. The return value only describes the direct process status.
    """
    if os.name == "nt":
        return subprocess.run(
            command, env=env, shell=False, check=False,
            stdout=stdout, stderr=subprocess.STDOUT, timeout=timeout,
        )
    process = subprocess.Popen(
        command, env=env, shell=False,
        stdout=stdout, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        code = process.wait(timeout=timeout)
    except BaseException:
        # TimeoutExpired, Ctrl-C and unexpected wait errors must not leave
        # the still-active emulator process group behind.
        _kill_owned_group(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        finally:
            # A shell wrapper may exit on SIGTERM while a descendant ignores
            # it: kill the group even when the parent has already returned.
            _kill_owned_group(process.pid, signal.SIGKILL)
            try:
                process.wait(timeout=TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise
    return subprocess.CompletedProcess(command, code)

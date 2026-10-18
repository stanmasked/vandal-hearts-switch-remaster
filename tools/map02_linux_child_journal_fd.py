"""Observe a writable GPU JSONL fd *inside* the pinned live Linux ELF child.

This is one process-state observation before the one-shot stdin release,
not proof that the observed child wrote every journal byte or that any
retail game/PS1 pixels are authentic. A journal digest remains untrusted.
"""
import os
from pathlib import Path
import stat
import time

from tools.verify_map02_native_gpu_capture import LOG


def observe_child_gpu_journal_fd(pid, journal_fd, process, deadline):
    """Fail closed until an actual child writable fd matches journal inode.

    Caller must have already independently confirmed /proc/<pid>/exe
    matches its pinned ELF descriptor. Requires procfs with fdinfo.
    """
    if (type(pid) is not int or pid < 1 or type(journal_fd) is not int
            or journal_fd < 0 or not isinstance(deadline, (int, float))):
        raise ValueError("MAP02 invalid child journal fd observation arguments")
    path = Path(f"/proc/{pid}/fd")
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ValueError("MAP02 native GPU child exited before journal fd observation")
        try:
            journal = os.stat(LOG, dir_fd=journal_fd, follow_symlinks=False)
        except FileNotFoundError:
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))
            continue
        if (not stat.S_ISREG(journal.st_mode)
                or stat.S_IMODE(journal.st_mode) != 0o600
                or journal.st_nlink != 1):
            raise ValueError("MAP02 native GPU journal type/mode invalid during child observation")
        try:
            opened = os.listdir(path)
        except OSError as exc:
            raise ValueError("MAP02 cannot inspect live child fd table") from exc
        for name in opened:
            if not name.isdecimal():
                continue
            child_fd = int(name)
            try:
                entry = os.stat(path / name)
                if ((entry.st_dev, entry.st_ino) !=
                        (journal.st_dev, journal.st_ino)):
                    continue
                with open(f"/proc/{pid}/fdinfo/{child_fd}",
                          encoding="ascii") as stream:
                    info = stream.read(4096)
                fields = [line.split(":", 1)[1].strip()
                          for line in info.splitlines()
                          if line.startswith("flags:")]
                if len(fields) != 1:
                    raise ValueError("MAP02 child journal fd flags unavailable")
                mode = int(fields[0], 8) & os.O_ACCMODE
                if mode in (os.O_WRONLY, os.O_RDWR):
                    # Reconfirm both sides before release; the child
                    # might have closed/reopened one fd while inspecting.
                    live = os.stat(path / name)
                    fixed = os.stat(LOG, dir_fd=journal_fd,
                                    follow_symlinks=False)
                    if ((live.st_dev, live.st_ino) ==
                            (fixed.st_dev, fixed.st_ino) ==
                            (journal.st_dev, journal.st_ino)
                            and process.poll() is None):
                        return True
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                # Per-fd close/open can race with /proc enumerations.
                continue
            except (OSError, ValueError) as exc:
                raise ValueError("MAP02 cannot verify child GPU journal fd") from exc
        time.sleep(min(0.01, max(0, deadline - time.monotonic())))
    raise ValueError("MAP02 timed out observing writable GPU journal fd in child")

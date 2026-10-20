"""Optional strict Linux ELF *process image* observation for private MAP02.

Checks the ELF header on the exact held executable fd and the actual kernel
/proc/<pid>/exe inode while the child process is still alive. This checks
which native image was executed, NOT whether it was the original game, what
shared libraries or resources it loaded, nor which process wrote GPU logs.
"""
import os
import stat
import sys


def require_elf_image(fd):
    if sys.platform != "linux" or not os.path.isdir("/proc/self/fd"):
        raise ValueError("strict ELF process image gate requires Linux procfs")
    head = os.pread(fd, 64, 0)
    # ELF identification: magic, 32- or 64-bit, little endian, current
    # version. Reject scripts, archives, truncated/unknown files.
    if (len(head) != 64 or head[:4] != b"\x7fELF"
            or head[4] not in (1, 2) or head[5] != 1 or head[6] != 1):
        raise ValueError("native ELF executable image required")
    # e_type is ET_EXEC or ET_DYN (PIE); e_machine must be nonzero.
    etype = int.from_bytes(head[16:18], "little")
    machine = int.from_bytes(head[18:20], "little")
    if etype not in (2, 3) or machine == 0:
        raise ValueError("native ELF executable image required")
    identity = os.fstat(fd)
    if not stat.S_ISREG(identity.st_mode):
        raise ValueError("native ELF executable image must be a regular file")


def observe_live_elf_image(pid, pinned_fd):
    """Match kernel-registered /proc/<pid>/exe with the SHA-checked FD.

    A process exiting too quickly, losing procfs access, or exec'ing another
    executable MUST fail this optional strict mode, not silently fall back.
    """
    if type(pid) is not int or pid < 1:
        raise ValueError("invalid native process identifier")
    require_elf_image(pinned_fd)
    pinned = os.fstat(pinned_fd)
    pidfd = None
    try:
        if hasattr(os, "pidfd_open"):
            pidfd = os.pidfd_open(pid, 0)
        actual = os.stat(f"/proc/{pid}/exe")
        if ((actual.st_dev, actual.st_ino) !=
                (pinned.st_dev, pinned.st_ino)
                or not stat.S_ISREG(actual.st_mode)):
            raise ValueError("running ELF process image differs from pinned binary")
    except OSError as exc:
        raise ValueError("cannot attest live native ELF process image") from exc
    finally:
        if pidfd is not None:
            os.close(pidfd)
    return True

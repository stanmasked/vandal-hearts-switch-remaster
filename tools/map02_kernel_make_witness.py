"""Linux ptrace witness for real GNU Make compiler children.

Follows actual Make descendants over fork/exec events and fingerprints
/proc/PID/exe while each execve tracee is stopped. The caller can use this
for the primary compile, rather than an independent replay.
"""

import ctypes
import hashlib
import os
from pathlib import Path
import signal
import stat
import tempfile
import time

PTRACEME = 0
CONT = 7
SETOPTIONS = 0x4200
TRACE_OPTIONS = 2 | 4 | 8 | 16 | 64 | (1 << 20)
TRACE_EXEC_EVENT = 4
LINUX_WAIT_ALL = 0x40000000
MAX_TOOL_SIZE = 128 * 1024 * 1024
TRACE_EXIT_EVENT = 6



def _ptrace(request, pid, data=0):
    libc = ctypes.CDLL(None, use_errno=True)
    fn = libc.ptrace
    fn.argtypes = [ctypes.c_uint, ctypes.c_int,
                   ctypes.c_void_p, ctypes.c_void_p]
    fn.restype = ctypes.c_long
    if fn(request, pid, None, ctypes.c_void_p(data)) == -1:
        raise OSError(ctypes.get_errno(), "MAP02 Make ptrace failed")


def _executed_kernel_digest(pid, expected):
    """Fingerprint the executing kernel inode while the tracee is stopped."""
    fd = os.open("/proc/" + str(pid) + "/exe", os.O_RDONLY | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        pinned = os.stat(expected)
        if (not stat.S_ISREG(st.st_mode) or
                (st.st_dev, st.st_ino) != (pinned.st_dev, pinned.st_ino)):
            raise ValueError("MAP02 Make child executable inode mismatch")
        if not 0 < st.st_size <= MAX_TOOL_SIZE:
            raise ValueError("MAP02 Make child executable size invalid")
        digest, count = hashlib.sha256(), 0
        while True:
            part = os.read(fd, 1024 * 1024)
            if not part:
                break
            count += len(part)
            if count > MAX_TOOL_SIZE:
                raise ValueError("MAP02 Make child executable too large")
            digest.update(part)
        if count != st.st_size:
            raise ValueError("MAP02 Make child executable size changed")
        return digest.hexdigest()
    finally:
        os.close(fd)



def _mapped_shared_objects(map_text, expected):
    """Verify file-backed ELF shared libraries recorded by Linux /proc/PID/maps.

    Only mapped libraries are included, not every library in the ldd profile.
    Both the inode from the kernel map and its file contents must match.
    """
    seen = {}
    for line in map_text.splitlines():
        columns = line.split(maxsplit=5)
        if len(columns) < 6:
            continue
        address, access, offset, device, inode_text, name = columns
        if ".so" not in Path(name).name and not Path(name).name.startswith("ld-linux"):
            continue
        if not name.startswith("/") or name.endswith(" (deleted)"):
            raise ValueError("MAP02 compiler mapped library path invalid")
        try:
            major, minor = (int(x, 16) for x in device.split(":"))
            inode = int(inode_text)
        except (ValueError, TypeError) as exc:
            raise ValueError("MAP02 compiler mapped library metadata invalid") from exc
        if not inode:
            raise ValueError("MAP02 compiler mapped library inode empty")
        canonical = Path(name).resolve(strict=True)
        if not canonical.is_file():
            raise ValueError("MAP02 compiler mapped library is not regular")
        fd = os.open(canonical, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            st = os.fstat(fd)
            if (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino) != (
                    major, minor, inode):
                raise ValueError("MAP02 compiler mapped library inode mismatch")
            expected_digest = expected.get(str(canonical))
            if expected_digest is None:
                raise ValueError("MAP02 compiler mapped library unpinned")
            if str(canonical) not in seen:
                if not 0 < st.st_size <= MAX_TOOL_SIZE:
                    raise ValueError("MAP02 compiler mapped library size invalid")
                sha = hashlib.sha256()
                total = 0
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_TOOL_SIZE:
                        raise ValueError("MAP02 compiler mapped library too large")
                    sha.update(chunk)
                if total != st.st_size or sha.hexdigest() != expected_digest:
                    raise ValueError("MAP02 compiler mapped library SHA-256 mismatch")
                seen[str(canonical)] = expected_digest
        finally:
            os.close(fd)
    return seen


def _observed_maps_receipt(libraries):
    if not libraries:
        raise ValueError("MAP02 compiler had no kernel observed library mappings")
    raw = chr(10).join(k + " " + v for k, v in sorted(libraries.items()))
    return {"count": len(libraries),
            "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}


def trace_make_children(args, *, cwd, env, pass_fds, tools, hashes,
                        expected_libraries=None, mapped_receipt=None, timeout=180):
    """Run real Make under ptrace, reject mismatched GCC child exec inodes."""
    if set(tools) != {"driver", "cc1", "as"} or set(hashes) != set(tools):
        raise ValueError("MAP02 Make child witness tool inventory invalid")
    selected = {role: Path(tool).resolve(strict=True)
                for role, tool in tools.items()}
    if len(set(selected.values())) != 3:
        raise ValueError("MAP02 Make child witness tools must be distinct")
    if not args or not Path(args[0]).is_absolute():
        raise ValueError("MAP02 Make child witness executable must be absolute")
    if not 0 < timeout <= 240:
        raise ValueError("MAP02 Make child witness timeout invalid")
    if (expected_libraries is None) != (mapped_receipt is None):
        raise ValueError("MAP02 compiler mapped witness parameters inconsistent")
    counts = {name: 0 for name in selected}
    pid_roles = {}
    roles_with_maps = {name: 0 for name in selected}
    all_mapped = {}
    with tempfile.TemporaryFile(mode="w+b") as output:
        leader = os.fork()
        if leader == 0:
            try:
                os.setsid()
                os.chdir(cwd)
                os.dup2(output.fileno(), 1)
                os.dup2(output.fileno(), 2)
                for fd in pass_fds:
                    os.set_inheritable(fd, True)
                _ptrace(PTRACEME, 0)
                os.execve(args[0], args, env)
            except BaseException:
                os._exit(125)
        live = {leader}
        root_started = False
        final = None
        deadline = time.monotonic() + timeout
        try:
            while live:
                observed, status = os.waitpid(-1, LINUX_WAIT_ALL | os.WNOHANG)
                if not observed:
                    if time.monotonic() > deadline:
                        raise ValueError("MAP02 Make child witness timed out")
                    time.sleep(0.002)
                    continue
                if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    if observed == leader:
                        final = os.waitstatus_to_exitcode(status)
                    live.discard(observed)
                    continue
                if not os.WIFSTOPPED(status):
                    raise ValueError("MAP02 Make child witness unexpected wait")
                signum, event = os.WSTOPSIG(status), status >> 16
                if observed == leader and not root_started:
                    if signum != signal.SIGTRAP:
                        raise ValueError("MAP02 Make child witness root exec failed")
                    _ptrace(SETOPTIONS, leader, TRACE_OPTIONS)
                    root_started = True
                if event == TRACE_EXIT_EVENT and observed in pid_roles and (
                        expected_libraries is not None):
                    role = pid_roles[observed]
                    with open("/proc/" + str(observed) + "/maps",
                              encoding="utf-8") as stream:
                        snapshot = stream.read(2 * 1024 * 1024 + 1)
                    if len(snapshot) > 2 * 1024 * 1024:
                        raise ValueError("MAP02 compiler maps snapshot too large")
                    mappings = _mapped_shared_objects(snapshot, expected_libraries)
                    if not mappings:
                        raise ValueError("MAP02 compiler process had no shared library mappings")
                    for path, sha in mappings.items():
                        if path in all_mapped and all_mapped[path] != sha:
                            raise ValueError("MAP02 compiler mapped library changed across children")
                        all_mapped[path] = sha
                    roles_with_maps[role] += 1
                if event == TRACE_EXEC_EVENT:
                    executable = Path(os.readlink(
                        "/proc/" + str(observed) + "/exe"))
                    for role, chosen in selected.items():
                        if executable.name == chosen.name:
                            if executable.resolve(strict=True) != chosen:
                                raise ValueError("MAP02 Make child executable path mismatch")
                            if _executed_kernel_digest(observed, chosen) != hashes[role]:
                                raise ValueError("MAP02 Make child executable hash mismatch")
                            counts[role] += 1
                            pid_roles[observed] = role
                            break
                delivered = (signum if event == 0 and signum not in
                             (signal.SIGTRAP, signal.SIGSTOP) else 0)
                _ptrace(CONT, observed, delivered)
            if final != 0:
                raise ValueError("MAP02 traced GNU Make compilation failed")
            for role, count in counts.items():
                if count < 1:
                    raise ValueError("MAP02 Make child kernel exec witness missing: " + role)
            if expected_libraries is not None:
                if not all(roles_with_maps.values()):
                    raise ValueError("MAP02 Make child library maps witness missing")
                mapped_receipt.update(_observed_maps_receipt(all_mapped))
                mapped_receipt["role_processes"] = roles_with_maps
            return counts
        finally:
            if live:
                try:
                    os.killpg(leader, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                for child in live:
                    try:
                        os.kill(child, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                grace = time.monotonic() + 1
                while live and time.monotonic() < grace:
                    try:
                        child, _ = os.waitpid(
                            -1, LINUX_WAIT_ALL | os.WNOHANG)
                    except ChildProcessError:
                        break
                    if child:
                        live.discard(child)
                    else:
                        time.sleep(0.003)

"""Launch an opt-in local PC GPU/DDA capture without publishing game bytes.

Only a user-supplied executable with their own game resources is launched.
This records process completion and checks the same private binary and GPU
journals after exit. It does NOT attest retail MAP02 or approve HD assets.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from tools.preflight_map02_private_dda_capture import (
    preflight, _executable_fingerprint, DIR_KEYS,
)
from tools.verify_map02_private_capture_session import verify_session
from tools.map02_linux_elf_process_image import require_elf_image, observe_live_elf_image
from tools.check_map02_private_pc_binary import inspect_binary


def _private_create(path, obj):
    """Durably publish a complete 0600 JSON receipt; never expose a partial one.

    An O_EXCL temporary file is fsynced *before* its final name is created.
    Hard-linking is exclusive (existing files or symlinks are never replaced).
    A failed write/link/fsync removes only files created by this invocation.
    The private receipt directory must support same-directory hard links and
    directory fsync; no best-effort downgrade is made for other filesystems.
    """
    path = Path(path)
    if path.is_symlink() or path.exists():
        raise FileExistsError("capture receipt already exists")
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".pending", dir=path.parent)
    published = False
    temp_identity = os.fstat(fd)
    dirfd = None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(obj, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if stat.S_IMODE(os.stat(temporary, follow_symlinks=False).st_mode) != 0o600:
            raise ValueError("private receipt mode changed during publication")
        # Same inode, two names: consumers cannot see partially written JSON.
        os.link(temporary, path, follow_symlinks=False)
        published = True
        dirfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.fsync(dirfd)
        os.unlink(temporary)
        os.fsync(dirfd)
        if (path.is_symlink() or
                os.stat(path, follow_symlinks=False).st_ino != temp_identity.st_ino or
                os.stat(path, follow_symlinks=False).st_dev != temp_identity.st_dev):
            raise ValueError("private receipt inode changed before publication completed")
    except BaseException:
        # Never unlink an unrelated file that replaced the destination.
        if published:
            try:
                saved = os.stat(path, follow_symlinks=False)
                if (saved.st_dev, saved.st_ino) == (
                        temp_identity.st_dev, temp_identity.st_ino):
                    os.unlink(path)
                    if dirfd is not None:
                        os.fsync(dirfd)
            except FileNotFoundError:
                pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    finally:
        if dirfd is not None:
            os.close(dirfd)


_PINNED_KEYS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")


def _opened_executable_identity(path, fd):
    """Bind the opened executable to the current no-follow pathname."""
    saved = os.fstat(fd)
    actual = os.stat(path, follow_symlinks=False)
    if (not stat.S_ISREG(saved.st_mode) or not saved.st_mode & 0o111
            or not 0 < saved.st_size <= 1024 * 1024 * 1024
            or not stat.S_ISREG(actual.st_mode)
            or any(getattr(saved, field) != getattr(actual, field)
                   for field in _PINNED_KEYS)):
        raise ValueError("pinned executable file identity changed")
    return tuple(getattr(saved, field) for field in _PINNED_KEYS)


def _open_pinned_executable(path, config):
    """Open and verify the exact Linux file descriptor used for exec.

    No pathname is re-resolved by the child at exec time. The descriptor is
    deliberately inherited through pass_fds and closed by the parent after
    the subprocess completes; this works with both ELF and shebang scripts.
    """
    if sys.platform != "linux" or not os.path.isdir("/proc/self/fd"):
        raise ValueError("pinned launch requires Linux procfs descriptors")
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        identity = _opened_executable_identity(path, fd)
        digest = hashlib.sha256()
        count = 0
        while True:
            part = os.read(fd, 1024 * 1024)
            if not part:
                break
            count += len(part)
            digest.update(part)
        if (count != identity[2]
                or digest.hexdigest() != config["executable_sha256"]
                or count != config["executable_bytes"]):
            raise ValueError("pinned executable differs from preflight fingerprint")
        if _opened_executable_identity(path, fd) != identity:
            raise ValueError("pinned executable changed while hashing")
        os.lseek(fd, 0, os.SEEK_SET)
        return fd, identity
    except BaseException:
        os.close(fd)
        raise


# The FD-pinned executable can still load different code through dynamic
# loader or interpreter environment variables. Refuse inherited code-injection
# controls for this intentionally strict private diagnostic launcher.
# This is NOT a complete runtime sandbox or a proof of binary provenance.
_BLOCKED_EXACT_ENV = frozenset((
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT",
    "PYTHONBREAKPOINT", "BASH_ENV", "ENV", "GCONV_PATH",
    "GLIBC_TUNABLES",
))


def _validate_launch_environment(environ):
    """Fail before creating receipts if the child could load injected code."""
    if type(environ) is not dict:
        raise ValueError("private launch environment must be a string mapping")
    for key, value in environ.items():
        if (type(key) is not str or type(value) is not str
                or not key or "=" in key or "\x00" in key or "\x00" in value):
            raise ValueError("private launch environment requires plain strings")
        if (key in _BLOCKED_EXACT_ENV or key.startswith("LD_")
                or key.startswith("DYLD_")):
            # Do not echo the key's value: it may contain user paths
            # and private process configuration.
            raise ValueError("private launch environment has injection controls")


def capture(executable, preflight_report, summary_report, *,
            game_args=(), environ=None, timeout=None,
            require_native_elf_image=False,
            require_native_probe_symbols=False):
    """Synchronous controlled launcher. Returns an unprivileged receipt dict.

    The launcher does not identify an installed original game nor prove
    which native libraries it used. No stdout, stderr, textures or pixels
    are copied to the report or GitHub.
    """
    if type(require_native_elf_image) is not bool:
        raise ValueError("strict native ELF mode must be boolean")
    if type(require_native_probe_symbols) is not bool:
        raise ValueError("native probe symbol requirement must be boolean")
    if require_native_probe_symbols and not require_native_elf_image:
        raise ValueError("native probe symbols require strict native ELF mode")
    env = dict(os.environ if environ is None else environ)
    _validate_launch_environment(env)
    executable = Path(executable).absolute()
    preflight_report = Path(preflight_report).absolute()
    summary_report = Path(summary_report).absolute()
    if preflight_report == summary_report:
        raise ValueError("preflight and summary must be different files")
    if (preflight_report.is_symlink() or summary_report.is_symlink()
            or preflight_report.exists() or summary_report.exists()):
        raise ValueError("capture receipts already exist; refusing overwrite")
    # Resolve both *parent paths* to prevent a symlink alias from writing
    # the preflight JSON into the recorder's otherwise empty directory.
    for key in DIR_KEYS:
        try:
            root = Path(env.get(key, "")).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("capture output directory does not exist") from exc
        for receipt_path in (preflight_report, summary_report):
            try:
                destination = receipt_path.parent.resolve(strict=True) / receipt_path.name
            except (OSError, RuntimeError) as exc:
                raise ValueError("capture receipt parent is unavailable") from exc
            if destination == root or root in destination.parents:
                raise ValueError("capture receipts must remain outside empty capture directory")
    if timeout is not None and (type(timeout) not in (int, float)
                                or not 0 < timeout <= 86400):
        raise ValueError("invalid capture timeout")
    if not isinstance(game_args, (tuple, list)) or any(
            type(arg) is not str or "\x00" in arg for arg in game_args):
        raise ValueError("game arguments must be plain strings")
    config = preflight(env, executable=executable)
    # The optional production-oriented gate runs *before* any private
    # receipt is published or child is started. No pathname, nm output,
    # game bytes, or pixel selectors become public.
    if require_native_probe_symbols:
        checked = inspect_binary(executable)
        if checked["executable_sha256"] != config["executable_sha256"]:
            raise ValueError("native probe inspection and preflight ELF differ")
    _private_create(preflight_report, config)
    receipt = {
        "schema": ("map02_private_native_process_receipt_v3"
                   if require_native_probe_symbols else
                   "map02_private_native_process_receipt_v2"
                   if require_native_elf_image else
                   "map02_private_native_process_receipt_v1"),
        "capture_frame": config["capture_frame"],
        "executable_sha256": config["executable_sha256"],
        "preflight_created": True,
        "process_started": False,
        "process_exit_code": None,
        "capture_verified": False,
        "verification": None,
        "failure_category": None,
        "retail_map02_verified": False,
        "hd_replacement_authorized": False,
    }
    if require_native_elf_image:
        receipt["native_elf_image_required"] = True
        receipt["native_elf_image_observed"] = False
    if require_native_probe_symbols:
        receipt["native_probe_symbols_required"] = True
        receipt["native_probe_symbols_inspected"] = True
    pinned_fd = None
    pinned_identity = None
    try:
        pinned_fd, pinned_identity = _open_pinned_executable(executable, config)
    except (OSError, ValueError):
        receipt["failure_category"] = "executable_changed"
    if pinned_fd is not None:
        try:
            if require_native_elf_image:
                try:
                    require_elf_image(pinned_fd)
                except ValueError:
                    receipt["failure_category"] = "native_elf_required"
            if receipt["failure_category"] is None:
                try:
                    # Linux exec resolves the already-checked descriptor,
                    # never the pathname. Synthetic shebang fixtures still
                    # run when the strict ELF gate is not requested.
                    proc = subprocess.Popen(
                        [str(executable), *game_args],
                        executable=f"/proc/self/fd/{pinned_fd}",
                        pass_fds=(pinned_fd,),
                        cwd=executable.parent,
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        shell=False,
                    )
                    receipt["process_started"] = True
                    if require_native_elf_image:
                        try:
                            observe_live_elf_image(proc.pid, pinned_fd)
                            receipt["native_elf_image_observed"] = True
                        except ValueError:
                            receipt["failure_category"] = "native_elf_image_unverified"
                    try:
                        receipt["process_exit_code"] = proc.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        receipt["failure_category"] = "process_timeout"
                    except KeyboardInterrupt:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        receipt["failure_category"] = "process_interrupted"
                except OSError:
                    receipt["failure_category"] = "process_launch_failed"
        finally:
            try:
                if _opened_executable_identity(executable, pinned_fd) != pinned_identity:
                    receipt["failure_category"] = "executable_changed"
                after = _executable_fingerprint(executable)
                if (after["executable_sha256"] != config["executable_sha256"]
                        or after["executable_bytes"] != config["executable_bytes"]):
                    receipt["failure_category"] = "executable_changed"
            except (OSError, ValueError):
                receipt["failure_category"] = "executable_changed"
            finally:
                os.close(pinned_fd)
    if (receipt["process_started"] and receipt["process_exit_code"] == 0
            and receipt["failure_category"] is None):
        try:
            receipt["verification"] = verify_session(
                env[DIR_KEYS[0]], native_frame=config["capture_frame"],
                preflight_report=preflight_report, executable=executable,
            )
            receipt["capture_verified"] = True
        except (ValueError, OSError):
            receipt["failure_category"] = "incomplete_or_invalid_private_capture"
    elif receipt["failure_category"] is None:
        receipt["failure_category"] = "process_exit_nonzero"
    _private_create(summary_report, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--summary-report", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--require-native-elf-image", action="store_true",
                        help="Require kernel /proc process executable to match pinned Linux ELF")
    parser.add_argument("--require-native-probe-symbols", action="store_true",
                        help="Also require local static GPU/FT4/two-word ELF instrumentation")
    parser.add_argument("game_args", nargs="*")
    args = parser.parse_args()
    try:
        result = capture(args.executable, args.preflight_report,
                         args.summary_report, game_args=args.game_args,
                         timeout=args.timeout_seconds,
                         require_native_elf_image=args.require_native_elf_image,
                         require_native_probe_symbols=args.require_native_probe_symbols)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["capture_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())

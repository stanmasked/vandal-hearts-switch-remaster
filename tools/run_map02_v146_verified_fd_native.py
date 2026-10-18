#!/usr/bin/env python3
"""Launch exact checked native PCSX ELF inode; never reopen its path for exec.

v145 verifies host ELF before and after native execution, but an attacker
could substitute the pathname between verification and exec. v146 keeps the
verified ELF file descriptor open, passes it to a child, and executes through
/proc/self/fd/N on Linux. An inode/path change is refused on final recheck.
This is native *synthetic* test infrastructure, NOT retail MAP02 execution
or cryptographic runtime attestation. No private paths, hashes, MIPS words,
GPU values or interpreter logs are printed on stdout/stderr.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
from pathlib import Path
import stat
import subprocess

from .analyze_map02_v131_private_mips_mmio import (
    Refused,_open_private_exe_dirfd,_snapshot,_read_exact,read_private_exe,
)
from .check_map02_v145_native_build_binding import (
    _read_manifest,_fields,MAX_BINARY_SIZE,HASH_KEYS,
)
from .make_map02_v129_four_vblank_exe import build

POSITIVE=(
    "-novid","-nodrc","-nothread",
    "--vh129-vblank-04","--vh138-interpreter-pc",
    "--vh139-codewords","--vh140-mmio-values",
    "--vh142-private-receipt",
)
NEGATIVE=POSITIVE+("--vh142-corrupt-receipt",)
GENERIC=POSITIVE+("--vh147-bounded-mmio",)
MAX_TIMEOUT=180


def _read_checked_elf_fd(fd):
    st=os.fstat(fd)
    if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid()
            or st.st_nlink!=1 or (st.st_mode&0o100)==0
            or (st.st_mode&0o022)!=0
            or not 64<=st.st_size<=MAX_BINARY_SIZE):
        raise Refused("verified executable inode metadata refused")
    before=_snapshot(st)
    os.lseek(fd,0,os.SEEK_SET)
    first=_read_exact(fd,st.st_size)
    if _snapshot(os.fstat(fd))!=before:
        raise Refused("verified executable inode changed")
    os.lseek(fd,0,os.SEEK_SET)
    second=_read_exact(fd,st.st_size)
    if (first!=second or not first.startswith(b"\x7fELF")
            or _snapshot(os.fstat(fd))!=before):
        raise Refused("verified executable bytes changed or invalid")
    return hashlib.sha256(first).hexdigest(),(st.st_dev,st.st_ino)


def _open_private_dirfd(path):
    """Reject symlinked and mutable components before creating local logs."""
    raw=os.fspath(path)
    if type(raw) is not str or not raw or "\x00" in raw:
        raise Refused("invalid native private log directory")
    parts=raw.split("/")
    absolute=raw.startswith("/")
    if absolute:
        parts=parts[1:]
    if not parts or any(part in ("",".","..") or len(part)>255 for part in parts):
        raise Refused("native log directory traversal refused")
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=os.open("/" if absolute else ".",flags)
    try:
        for i,part in enumerate(parts):
            nxt=os.open(part,flags,dir_fd=fd)
            st=os.fstat(nxt)
            last=i==len(parts)-1
            if (not stat.S_ISDIR(st.st_mode)
                    or (st.st_uid!=0 and st.st_uid!=os.geteuid())
                    or (st.st_mode&0o022)!=0
                    or (last and (st.st_uid!=os.geteuid()
                                  or stat.S_IMODE(st.st_mode)!=0o700))):
                os.close(nxt)
                raise Refused("unsafe native log parent")
            os.close(fd)
            fd=nxt
        return fd
    except (OSError,Refused):
        os.close(fd)
        raise Refused("native log directory safely inaccessible") from None


def _create_private_log(path):
    raw=os.fspath(path)
    if type(raw) is not str or not raw or "\x00" in raw:
        raise Refused("invalid native private log name")
    p=Path(raw)
    name=p.name
    if not name or name in (".","..") or len(name)>255:
        raise Refused("invalid private native log leaf")
    directory=_open_private_dirfd(p.parent)
    try:
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
        fd=os.open(name,flags,0o600,dir_fd=directory)
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid()
                or st.st_nlink!=1 or stat.S_IMODE(st.st_mode)!=0o600):
            os.close(fd)
            raise Refused("native log leaf ownership refused")
        return fd
    except OSError:
        raise Refused("native log leaf safely inaccessible") from None
    finally:
        os.close(directory)


def execute_exact_inode(binary,manifest,challenge,private_log,args,
                        timeout=75,prelaunch_hook=None):
    """OS executes checked fd, not user-visible pathname. No shell.

    prelaunch_hook is ONLY for an explicitly injected deterministic race
    regression; never exposed through the CLI or native workflow.
    """
    if (not isinstance(timeout,int) or isinstance(timeout,bool)
            or not 1<=timeout<=MAX_TIMEOUT):
        raise Refused("native timeout outside approved bounds")
    argv=tuple(args)
    if (not argv or any(type(arg) is not str or not arg
                        or "\x00" in arg for arg in argv)):
        raise Refused("native interpreter arguments refused")
    manifest_before,raw_before=_read_manifest(manifest)
    reference=_fields(binary,challenge)
    if any(not hmac.compare_digest(reference[key],manifest_before[key])
           for key in HASH_KEYS):
        raise Refused("native host executable not pinned to run manifest")
    descriptor=_open_private_exe_dirfd(binary)
    try:
        fingerprint,inode=_read_checked_elf_fd(descriptor)
        if not hmac.compare_digest(fingerprint,manifest_before["binary_sha256"]):
            raise Refused("native binary inode differs from prepared ELF")
        logfd=_create_private_log(private_log)
        try:
            if prelaunch_hook is not None:
                prelaunch_hook()
            # A path replacement cannot change this fd. argv[0] preserves
            # the conventional PCSX name while the kernel execs fd's inode.
            try:
                with os.fdopen(logfd,"wb",closefd=False) as output:
                    completed=subprocess.run(
                        [os.fspath(binary),*argv],
                        executable=f"/proc/self/fd/{descriptor}",
                        pass_fds=(descriptor,),
                        stdout=output,stderr=subprocess.STDOUT,
                        check=False,timeout=timeout,close_fds=True,
                    )
                    output.flush()
                    os.fsync(output.fileno())
            except (subprocess.TimeoutExpired,OSError):
                raise Refused("pinned native process failed or timed out") from None
            if completed.returncode!=0:
                raise Refused("pinned native process reported failure")
            # Reopen pathname only for a POST-exec identity assertion.
            verify_fd=_open_private_exe_dirfd(binary)
            try:
                final_digest,final_inode=_read_checked_elf_fd(verify_fd)
            finally:
                os.close(verify_fd)
            if (inode!=final_inode or
                    not hmac.compare_digest(fingerprint,final_digest)
                    or _read_checked_elf_fd(descriptor)[0]!=fingerprint
                    or _read_manifest(manifest)!=(manifest_before,raw_before)
                    or _fields(binary,challenge)!=reference):
                raise Refused("native binary, inode or private binding changed")
            return True
        finally:
            os.close(logfd)
    finally:
        os.close(descriptor)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary",required=True,type=Path)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--challenge",required=True,type=Path)
    parser.add_argument("--private-log",required=True,type=Path)
    parser.add_argument("--timeout-seconds",type=int,default=75)
    parser.add_argument("native_args",nargs=argparse.REMAINDER)
    args=parser.parse_args()
    try:
        native=list(args.native_args)
        if native and native[0]=="--":
            native=native[1:]
        if len(native)<2:
            raise Refused("native PS-X executable argument absent")
        flags=tuple(native[:-1])
        if flags not in (POSITIVE,NEGATIVE,GENERIC):
            raise Refused("only pinned v129 synthetic CPU modes allowed")
        if read_private_exe(native[-1])!=build()[0]:
            raise Refused("private EXE does not match source-authored test")
        execute_exact_inode(args.binary,args.manifest,args.challenge,
                            args.private_log,native,
                            timeout=args.timeout_seconds)
    except (Refused,OSError,ValueError,TypeError):
        parser.exit(2,"VH146_VERIFIED_FD_NATIVE_LAUNCH_REFUSED\n")
    print("VH146_VERIFIED_FD_NATIVE_LAUNCH_PASS "
          "same_inode_executed=1 synthetic_only=1 private_log=1 "
          "retail_map02=0")


if __name__=="__main__":
    main()
